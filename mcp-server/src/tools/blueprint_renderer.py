"""blueprint_renderer — 将 codebook_explore 的 report_data 渲染为自包含 HTML 蓝图文件。

设计原则：
- 生成的 HTML 文件零依赖，浏览器双击即可打开
- Mermaid 通过 CDN 加载（唯一的外部依赖，离线时优雅降级为代码块）
- 所有交互（模块展开/折叠、筛选）用原生 JS 实现
- 深色主题，与 CodeBook 品牌一致
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import time
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger()

# 蓝图文件输出目录
_OUTPUT_DIR = Path.home() / ".codebook" / "blueprints"


def _safe(text: str) -> str:
    """HTML 转义（含单引号，防止 onclick 属性中的 XSS）。"""
    return html.escape(str(text), quote=True) if text else ""


def _repo_slug(repo_url: str) -> str:
    """从 repo_url 提取简短的项目名。"""
    # https://github.com/user/repo → user/repo
    # /local/path/to/project → project
    url = repo_url.rstrip("/")
    if "github.com" in url:
        parts = url.split("github.com/")[-1]
        return parts.replace("/", "_").replace(".", "_")
    return Path(url).name or "project"


def _lang_color(lang: str) -> str:
    """编程语言 → 颜色。"""
    colors = {
        "python": "#306998", "javascript": "#f7df1e", "typescript": "#3178c6",
        "java": "#b07219", "go": "#00add8", "rust": "#dea584",
        "bash": "#3e4451", "ruby": "#cc342d", "c": "#555555",
        "cpp": "#f34b7d", "csharp": "#178600", "php": "#4f5d95",
        "swift": "#ffac45", "kotlin": "#a97bff",
    }
    return colors.get(lang.lower(), "#64748b")


def _health_badge_html(health: str) -> str:
    """生成健康状态 badge 的 HTML。"""
    cfg = {
        "green": ("Healthy", "#10b981", "rgba(16,185,129,0.1)"),
        "yellow": ("Needs attention", "#f59e0b", "rgba(245,158,11,0.1)"),
        "red": ("Needs refactor", "#ef4444", "rgba(239,68,68,0.1)"),
    }
    label, color, bg = cfg.get(health, cfg["green"])
    return (
        f'<span style="padding:2px 10px;border-radius:999px;font-size:11px;'
        f'font-weight:600;color:{color};background:{bg};'
        f'border:1px solid {color}30">{label}</span>'
    )


def _build_stats_html(stats: dict) -> str:
    """生成统计卡片区域。"""
    items = [
        ("Files", stats.get("code_files", stats.get("files", 0)), f'of {stats.get("files", 0)} total'),
        ("Modules", stats.get("modules", 0), ""),
        ("Functions", stats.get("functions", 0), ""),
        ("Lines", stats.get("total_lines", 0), ""),
    ]
    # 解析质量
    pq = stats.get("parse_quality", {})
    conf = stats.get("avg_parse_confidence", 0)
    conf_pct = f"{int(conf * 100)}%"
    items.append(("Confidence", conf_pct, "parse quality"))

    cards = []
    for label, value, sub in items:
        val_str = f"{value:,}" if isinstance(value, int) else str(value)
        sub_html = f'<div class="stat-sub">{_safe(sub)}</div>' if sub else ""
        cards.append(
            f'<div class="stat-card">'
            f'<div class="stat-label">{_safe(label)}</div>'
            f'<div class="stat-value">{val_str}</div>'
            f'{sub_html}</div>'
        )
    return '<div class="stats-grid">' + "\n".join(cards) + "</div>"


def _build_lang_bar_html(languages: dict) -> str:
    """生成语言分布条。"""
    if not languages:
        return ""
    total = sum(languages.values())
    if total == 0:
        return ""

    bar_segs = []
    legend_items = []
    for lang, count in sorted(languages.items(), key=lambda x: -x[1]):
        pct = count / total * 100
        color = _lang_color(lang)
        bar_segs.append(
            f'<div style="width:{pct:.1f}%;background:{color};min-width:3px" '
            f'title="{_safe(lang)}: {count} files"></div>'
        )
        legend_items.append(
            f'<span><span class="lang-dot" style="background:{color}"></span>'
            f'{_safe(lang)}: {count}</span>'
        )

    return (
        '<div class="lang-bar">' + "".join(bar_segs) + "</div>\n"
        '<div class="lang-legend">' + "".join(legend_items) + "</div>"
    )


def _build_parse_quality_html(stats: dict) -> str:
    """生成解析质量条。"""
    pq = stats.get("parse_quality", {})
    total = sum(pq.values())
    if total == 0:
        return ""

    segments = [
        ("native", "#10b981", "Native AST"),
        ("full", "#3b82f6", "Tree-sitter"),
        ("partial", "#f59e0b", "Partial"),
        ("basic", "#ef4444", "Regex fallback"),
        ("failed", "#64748b", "Failed"),
    ]

    bar_segs = []
    legend_items = []
    for key, color, label in segments:
        count = pq.get(key, 0)
        if count == 0:
            continue
        pct = count / total * 100
        bar_segs.append(
            f'<div style="width:{pct:.1f}%;background:{color};min-width:3px" '
            f'title="{label}: {count}"></div>'
        )
        legend_items.append(
            f'<span><span class="lang-dot" style="background:{color}"></span>'
            f'{label}: {count}</span>'
        )

    return (
        '<div class="quality-section">'
        '<div class="quality-label">Parse Quality</div>'
        '<div class="quality-bar">' + "".join(bar_segs) + "</div>"
        '<div class="quality-legend">' + "".join(legend_items) + "</div>"
        "</div>"
    )


def _build_module_card_html(card: dict) -> str:
    """生成单个模块卡片的 HTML。"""
    name = card.get("name", "")
    health = card.get("health", "green")
    is_selected = card.get("is_selected", False)
    body = card.get("body", "") or card.get("title", "")
    depends_on = card.get("depends_on", [])
    used_by = card.get("used_by", [])
    chapter = card.get("chapter")
    call_chains = card.get("call_chains", [])

    open_class = "open" if is_selected else ""
    selected_badge = (
        '<span class="badge-selected">Deep analyzed</span>'
        if is_selected else ""
    )

    # 依赖标签（可点击高亮）
    deps_html = ""
    dep_parts = []
    if depends_on:
        dep_tags = " ".join(
            f'<a class="dep-link" data-target="{_safe(d)}" onclick="event.stopPropagation();highlightModule(\'{_safe(d)}\')">{_safe(d)}</a>'
            for d in depends_on
        )
        dep_parts.append(f'<span class="dep-group">Depends on: {dep_tags}</span>')
    if used_by:
        used_tags = " ".join(
            f'<a class="dep-link" data-target="{_safe(u)}" onclick="event.stopPropagation();highlightModule(\'{_safe(u)}\')">{_safe(u)}</a>'
            for u in used_by
        )
        dep_parts.append(f'<span class="dep-group">Used by: {used_tags}</span>')
    if dep_parts:
        deps_html = '<div class="module-deps">' + "".join(dep_parts) + "</div>"

    # 详情区域
    detail_html = ""

    # 函数调用链（来自 dep_graph 交互数据）
    if call_chains:
        fn_rows = []
        for fc in call_chains:
            fn_name = fc.get("function", "")
            if fn_name.startswith("_") or fn_name == "<anonymous>" or fn_name == "<module>":
                continue
            fn_file = fc.get("file", "")
            fn_line = fc.get("line_start", 0)
            callers = fc.get("callers", [])
            callees = fc.get("callees", [])
            caller_html = ""
            if callers:
                caller_html = f'<span class="fn-flow fn-callers" title="Called by">&larr; {_safe(", ".join(callers[:5]))}</span>'
            callee_html = ""
            if callees:
                callee_html = f'<span class="fn-flow fn-callees" title="Calls">&rarr; {_safe(", ".join(callees[:5]))}</span>'
            fn_rows.append(
                f'<div class="fn-row" onclick="event.stopPropagation();toggleFnDetail(this)">'
                f'<code class="fn-name">{_safe(fn_name)}()</code>'
                f'<span class="fn-loc">{_safe(fn_file)}:{fn_line}</span>'
                f'<div class="fn-detail">{caller_html}{callee_html}</div>'
                f'</div>'
            )
        if fn_rows:
            detail_html += (
                '<div class="detail-section">'
                '<div class="detail-label blue">FUNCTIONS &amp; CALL CHAINS</div>'
                + "\n".join(fn_rows[:20]) +
                "</div>"
            )
    elif chapter:
        # 回退到 chapter 数据
        fn_rows = []
        for mc in chapter.get("module_cards", []):
            for fn in mc.get("functions", []):
                fn_name = fn.get("name", "")
                if fn_name.startswith("_") or fn_name == "<anonymous>":
                    continue
                fn_file = mc.get("path", mc.get("name", ""))
                fn_lines = fn.get("lines", "")
                fn_rows.append(
                    f'<div class="fn-row">'
                    f'<code class="fn-name">{_safe(fn_name)}()</code>'
                    f'<span class="fn-loc">{_safe(fn_file)}:{_safe(fn_lines)}</span>'
                    f'</div>'
                )
        if fn_rows:
            detail_html += (
                '<div class="detail-section">'
                '<div class="detail-label blue">FUNCTIONS</div>'
                + "\n".join(fn_rows[:12]) +
                "</div>"
            )

    if chapter:
        # 模块局部 Mermaid
        dep_graph = chapter.get("dependency_graph", "")
        if dep_graph and dep_graph.strip():
            detail_html += (
                '<div class="detail-section">'
                '<div class="detail-label dim">MODULE DEPENDENCY GRAPH</div>'
                f'<pre class="mermaid">{_safe(dep_graph)}</pre>'
                '</div>'
            )

    detail_block = (
        f'<div class="module-detail">{detail_html}</div>'
        if detail_html else ""
    )

    safe_name = _safe(name)
    return f'''<div class="module-card {open_class}" data-name="{safe_name}" data-selected="{str(is_selected).lower()}" data-health="{health}" onclick="toggleCard(this)">
  <div class="module-header">
    <div class="module-top">
      <span class="module-name">{safe_name}</span>
      {_health_badge_html(health)}
      {selected_badge}
      <span class="module-arrow">&#9662;</span>
    </div>
    <div class="module-body">{_safe(body)}</div>
    {deps_html}
  </div>
  {detail_block}
</div>'''


def render_blueprint_html(
    report_data: dict[str, Any],
    repo_url: str = "",
    total_time: float = 0,
) -> str:
    """将 report_data 渲染为完整的自包含 HTML 字符串。

    Args:
        report_data: codebook_explore 生成的 report_data 字典。
        repo_url: 原始仓库地址（用于标题和链接）。
        total_time: 扫描总耗时秒数。

    Returns:
        完整的 HTML 字符串。
    """
    overview = report_data.get("overview", {})
    module_cards = report_data.get("module_cards", [])
    role = report_data.get("role", "pm")
    strategy = report_data.get("selection_strategy", "")
    query = report_data.get("query", "")
    stats = overview.get("stats", {})
    mermaid_diagram = overview.get("mermaid_diagram", "")
    mermaid_overview = overview.get("mermaid_overview", "")
    mermaid_full = overview.get("mermaid_full", "")
    expandable_groups = overview.get("expandable_groups", {}) or {}
    project_overview = overview.get("project_overview", "")
    parse_warnings = overview.get("parse_warnings", [])

    # 仓库显示名
    repo_display = repo_url.rstrip("/").split("/")[-1] if repo_url else "Project"
    repo_owner_name = ""
    if "github.com/" in repo_url:
        repo_owner_name = repo_url.split("github.com/")[-1].rstrip("/")

    selected_count = sum(1 for m in module_cards if m.get("is_selected"))
    attention_count = sum(1 for m in module_cards if m.get("health") != "green")
    strategy_label = {
        "query_driven": "Query-driven analysis",
        "topology_driven": "Topology-driven analysis",
        "topology_fallback": "Auto analysis",
    }.get(strategy, strategy)

    # ── 组装各部分 ──────────────────────────────────────
    stats_html = _build_stats_html(stats)
    lang_bar_html = _build_lang_bar_html(stats.get("languages", {}))
    parse_quality_html = _build_parse_quality_html(stats)

    # 查询提示
    query_html = ""
    if query:
        query_html = (
            f'<div class="query-box">Query: {_safe(query)}</div>'
        )

    # 解析警告
    warnings_html = ""
    if parse_warnings:
        items = "".join(f'<div class="warning-item">{_safe(w)}</div>' for w in parse_warnings)
        warnings_html = f'<div class="warnings-box">{items}</div>'

    # Mermaid — 分层展示
    mermaid_html = ""
    has_layers = bool(mermaid_overview and mermaid_full and expandable_groups)
    if has_layers:
        # 可展开组按钮
        group_btns = []
        for grp, meta in expandable_groups.items():
            sub_n = meta.get("sub_modules", 0)
            group_btns.append(
                f'<button class="layer-btn" onclick="showFocusGroup(\'{_safe(grp)}\')">'
                f'{_safe(grp)} ({sub_n})</button>'
            )
        group_btns_html = "\n".join(group_btns)

        mermaid_html = (
            '<div class="mermaid-box">'
            '<div class="section-label">MODULE DEPENDENCY GRAPH</div>'
            '<div class="layer-tabs">'
            '<button class="layer-btn active" onclick="showLayer(\'overview\',this)">Overview</button>'
            '<button class="layer-btn" onclick="showLayer(\'full\',this)">Full</button>'
            '</div>'
            f'<div class="layer-groups">{group_btns_html}</div>'
            f'<div id="mermaid-overview" class="mermaid-layer"><pre class="mermaid">{_safe(mermaid_overview)}</pre></div>'
            f'<div id="mermaid-full" class="mermaid-layer" style="display:none"><pre class="mermaid">{_safe(mermaid_full)}</pre></div>'
            '<div id="mermaid-focus" class="mermaid-layer" style="display:none"></div>'
            '</div>'
        )
    elif mermaid_diagram and mermaid_diagram.strip():
        mermaid_html = (
            '<div class="mermaid-box">'
            '<div class="section-label">MODULE DEPENDENCY GRAPH</div>'
            f'<pre class="mermaid">{_safe(mermaid_diagram)}</pre>'
            '</div>'
        )

    # 可展开组的 focus Mermaid 数据（JSON 嵌入 JS）
    focus_data_json = json.dumps({}, ensure_ascii=False)
    if has_layers:
        focus_data = report_data.get("focus_diagrams", {})
        focus_data_json = json.dumps(focus_data, ensure_ascii=False).replace("</", "<\\/")

    # 交互式蓝图数据：每个模块的邻接关系（嵌入 JS 供前端高亮用）
    adjacency_map: dict[str, dict] = {}
    for card in module_cards:
        adj = card.get("adjacency")
        if adj:
            adjacency_map[card.get("name", "")] = adj
    adjacency_json = json.dumps(adjacency_map, ensure_ascii=False).replace("</", "<\\/")

    # 模块卡片
    module_cards_html = "\n".join(
        _build_module_card_html(card) for card in module_cards
    )

    # 仓库链接
    repo_link_html = ""
    if repo_url.startswith("http"):
        repo_link_html = (
            f'<a class="repo-link" href="{_safe(repo_url)}" target="_blank">'
            f'{_safe(repo_url)}</a>'
        )

    return f'''<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CodeBook Blueprint — {_safe(repo_display)}</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/mermaid/10.6.1/mermaid.min.js"></script>
<style>
:root {{
  --bg:#0a0b10;--surface:#13151f;--surface-alt:#1a1d2b;
  --border:#252838;--border-hi:#6366f1;
  --text:#e2e8f0;--muted:#8892b0;--dim:#5a6380;
  --accent:#6366f1;--accent-lt:#818cf8;
  --green:#10b981;--green-bg:rgba(16,185,129,0.1);
  --yellow:#f59e0b;--yellow-bg:rgba(245,158,11,0.1);
  --red:#ef4444;--red-bg:rgba(239,68,68,0.1);
  --blue:#3b82f6;
}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:var(--bg);color:var(--text);font-family:'Inter',-apple-system,system-ui,sans-serif;line-height:1.6}}
.container{{max-width:960px;margin:0 auto;padding:28px 32px}}
.logo{{font-size:30px;font-weight:800;background:linear-gradient(135deg,var(--accent),var(--accent-lt));-webkit-background-clip:text;-webkit-text-fill-color:transparent}}
.subtitle{{font-size:14px;color:var(--dim);margin-left:14px}}
.repo-name{{font-size:20px;font-weight:600;margin:12px 0 2px}}
.repo-link{{font-size:13px;color:var(--accent);text-decoration:none}}
.repo-link:hover{{text-decoration:underline}}
.overview-text{{font-size:14px;color:var(--muted);line-height:1.8;margin:16px 0 20px}}
.query-box{{background:rgba(59,130,246,0.08);border:1px solid rgba(59,130,246,0.2);border-radius:8px;padding:10px 16px;font-size:14px;color:var(--blue);margin-bottom:16px}}
.warnings-box{{background:var(--yellow-bg);border:1px solid rgba(245,158,11,0.2);border-radius:8px;padding:12px 16px;margin-bottom:20px}}
.warning-item{{font-size:13px;color:var(--yellow);margin-bottom:4px}}
.stats-grid{{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:12px}}
.stat-card{{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:14px 18px;flex:1 1 130px;min-width:130px}}
.stat-label{{font-size:11px;color:var(--dim);letter-spacing:0.05em;text-transform:uppercase}}
.stat-value{{font-size:26px;font-weight:700;margin-top:2px}}
.stat-sub{{font-size:11px;color:var(--dim);margin-top:2px}}
.lang-bar{{display:flex;border-radius:6px;overflow:hidden;height:8px;margin-top:4px}}
.lang-legend{{display:flex;gap:14px;margin-top:6px;flex-wrap:wrap}}
.lang-legend span{{font-size:11px;color:var(--muted);display:flex;align-items:center;gap:4px}}
.lang-dot{{width:8px;height:8px;border-radius:2px;display:inline-block}}
.quality-section{{margin-top:16px}}
.quality-label{{font-size:11px;color:var(--dim);letter-spacing:0.04em;text-transform:uppercase;margin-bottom:6px}}
.quality-bar{{display:flex;border-radius:6px;overflow:hidden;height:10px}}
.quality-legend{{display:flex;gap:14px;margin-top:6px;flex-wrap:wrap}}
.quality-legend span{{font-size:11px;color:var(--muted);display:flex;align-items:center;gap:4px}}
.mermaid-box{{background:var(--surface-alt);border:1px solid var(--border);border-radius:12px;padding:20px;margin-top:20px}}
.mermaid-box .section-label{{font-size:12px;font-weight:600;color:var(--dim);letter-spacing:0.04em;margin-bottom:12px}}
.layer-tabs{{display:flex;gap:6px;margin-bottom:10px}}
.layer-groups{{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:12px}}
.layer-btn{{padding:4px 14px;border-radius:999px;font-size:12px;font-weight:500;border:1px solid var(--border);background:transparent;color:var(--muted);cursor:pointer;transition:all .15s}}
.layer-btn:hover{{border-color:var(--accent);color:var(--accent-lt)}}
.layer-btn.active{{border-color:var(--accent);background:rgba(99,102,241,0.09);color:var(--accent-lt)}}
.mermaid svg{{max-width:100%}}
.filter-bar{{display:flex;gap:8px;margin-top:28px;margin-bottom:14px}}
.filter-btn{{padding:6px 16px;border-radius:999px;font-size:13px;font-weight:500;border:1px solid var(--border);background:transparent;color:var(--muted);cursor:pointer;transition:all .15s}}
.filter-btn:hover{{border-color:var(--accent);color:var(--accent-lt)}}
.filter-btn.active{{border-color:var(--accent);background:rgba(99,102,241,0.09);color:var(--accent-lt)}}
.module-list{{display:flex;flex-direction:column;gap:12px}}
.search-bar{{margin-top:24px}}
.search-bar input{{width:100%;padding:10px 16px;border-radius:10px;border:1px solid var(--border);background:var(--surface);color:var(--text);font-size:14px;outline:none;transition:border-color .2s}}
.search-bar input:focus{{border-color:var(--accent)}}
.search-bar input::placeholder{{color:var(--dim)}}
.module-card{{background:var(--surface);border:1px solid var(--border);border-radius:14px;overflow:hidden;transition:border-color .25s,box-shadow .25s}}
.module-card.open{{border-color:var(--border-hi)}}
.module-card.highlight-upstream{{border-color:var(--red);box-shadow:0 0 0 1px var(--red)}}
.module-card.highlight-downstream{{border-color:var(--blue);box-shadow:0 0 0 1px var(--blue)}}
.module-card.highlight-self{{border-color:var(--accent);box-shadow:0 0 12px rgba(99,102,241,0.3)}}
.module-header{{padding:16px 20px;cursor:pointer;user-select:none}}
.module-top{{display:flex;align-items:center;gap:10px;flex-wrap:wrap}}
.module-name{{font-size:16px;font-weight:700}}
.badge-selected{{padding:2px 8px;border-radius:999px;font-size:10px;font-weight:600;color:var(--accent);background:rgba(99,102,241,0.08);border:1px solid rgba(99,102,241,0.19)}}
.module-arrow{{color:var(--dim);font-size:16px;transition:transform .2s;margin-left:auto}}
.module-card.open .module-arrow{{transform:rotate(180deg)}}
.module-body{{font-size:13px;color:var(--muted);margin-top:6px;line-height:1.6}}
.module-deps{{display:flex;gap:12px;margin-top:8px;flex-wrap:wrap}}
.dep-group{{font-size:11px;color:var(--dim)}}
.dep-link{{color:var(--accent);cursor:pointer;text-decoration:none;padding:1px 6px;border-radius:4px;transition:background .15s}}
.dep-link:hover{{background:rgba(99,102,241,0.12);text-decoration:underline}}
.module-detail{{padding:0 20px 16px;border-top:1px solid var(--border);max-height:0;overflow:hidden;transition:max-height .3s ease-out,padding .3s ease-out}}
.module-card.open .module-detail{{max-height:2000px;padding:0 20px 16px;overflow:visible}}
.detail-section{{margin-top:14px}}
.detail-label{{font-size:12px;font-weight:600;letter-spacing:0.04em;margin-bottom:8px}}
.detail-label.blue{{color:var(--blue)}}
.detail-label.dim{{color:var(--dim)}}
.fn-row{{display:flex;align-items:baseline;gap:8px;padding:5px 0;border-bottom:1px solid var(--border);flex-wrap:wrap;cursor:pointer;transition:background .15s}}
.fn-row:hover{{background:rgba(99,102,241,0.04)}}
.fn-name{{color:var(--accent-lt);font-size:13px;font-family:'JetBrains Mono','Fira Code',monospace}}
.fn-loc{{font-size:11px;color:var(--dim)}}
.fn-detail{{display:none;width:100%;margin-top:4px;padding:6px 0 2px}}
.fn-row.fn-open .fn-detail{{display:block}}
.fn-flow{{display:block;font-size:11px;padding:2px 0}}
.fn-callers{{color:var(--red)}}
.fn-callees{{color:var(--blue)}}
.module-card.search-hidden{{display:none}}
.footer{{margin-top:40px;padding-top:14px;border-top:1px solid var(--border);font-size:11px;color:var(--dim);text-align:center}}
</style>
</head>
<body>
<div class="container">
  <div style="display:flex;align-items:baseline">
    <span class="logo">CodeBook</span>
    <span class="subtitle">Blueprint Report</span>
  </div>
  <h2 class="repo-name">{_safe(repo_owner_name or repo_display)}</h2>
  {repo_link_html}

  {query_html}
  <p class="overview-text">{_safe(project_overview)}</p>
  {warnings_html}

  {stats_html}
  {lang_bar_html}
  {parse_quality_html}
  {mermaid_html}

  <div class="search-bar">
    <input type="text" id="searchInput" placeholder="Search modules and functions..." oninput="searchModules(this.value)" />
  </div>

  <div class="filter-bar">
    <button class="filter-btn active" onclick="filterModules('all',this)">All ({len(module_cards)})</button>
    <button class="filter-btn" onclick="filterModules('selected',this)">Analyzed ({selected_count})</button>
    <button class="filter-btn" onclick="filterModules('attention',this)">Needs attention ({attention_count})</button>
  </div>

  <div class="module-list" id="moduleList">
    {module_cards_html}
  </div>

  <div class="footer">
    Generated by CodeBook in {total_time:.1f}s &middot; {role.upper()} view &middot; {_safe(strategy_label)}
  </div>
</div>

<script>
mermaid.initialize({{
  theme:'dark',
  themeVariables:{{primaryColor:'#1a1d2b',lineColor:'#6366f1',textColor:'#e2e8f0'}},
  securityLevel:'loose'
}});
var _focusData={focus_data_json};
var _adjacency={adjacency_json};
var _highlightTimer=null;

/* ── Toggle card expand/collapse ── */
function toggleCard(el){{el.classList.toggle('open')}}

/* ── Toggle function detail row ── */
function toggleFnDetail(el){{el.classList.toggle('fn-open')}}

/* ── Filter modules by type ── */
function filterModules(type,btn){{
  document.querySelectorAll('.filter-btn').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  document.querySelectorAll('.module-card').forEach(c=>{{
    const sel=c.dataset.selected==='true';
    const h=c.dataset.health;
    if(type==='all')c.style.display='';
    else if(type==='selected')c.style.display=sel?'':'none';
    else if(type==='attention')c.style.display=h!=='green'?'':'none';
  }});
}}

/* ── Search modules and functions ── */
function searchModules(q){{
  q=q.toLowerCase().trim();
  document.querySelectorAll('.module-card').forEach(c=>{{
    if(!q){{c.classList.remove('search-hidden');return}}
    var name=(c.dataset.name||'').toLowerCase();
    var body=(c.querySelector('.module-body')||{{}}).textContent||'';
    var fns=Array.from(c.querySelectorAll('.fn-name')).map(f=>f.textContent).join(' ').toLowerCase();
    var match=name.includes(q)||body.toLowerCase().includes(q)||fns.includes(q);
    c.classList.toggle('search-hidden',!match);
  }});
}}

/* ── Highlight module + its dependencies ── */
function highlightModule(name){{
  clearHighlights();
  var adj=_adjacency[name];
  if(!adj)return;
  document.querySelectorAll('.module-card').forEach(c=>{{
    var n=c.dataset.name;
    if(n===name)c.classList.add('highlight-self');
    else if(adj.upstream&&adj.upstream.includes(n))c.classList.add('highlight-upstream');
    else if(adj.downstream&&adj.downstream.includes(n))c.classList.add('highlight-downstream');
  }});
  scrollToModule(name);
  if(_highlightTimer)clearTimeout(_highlightTimer);
  _highlightTimer=setTimeout(clearHighlights,5000);
}}
function clearHighlights(){{
  document.querySelectorAll('.module-card').forEach(c=>{{
    c.classList.remove('highlight-self','highlight-upstream','highlight-downstream');
  }});
}}
function scrollToModule(name){{
  var card=document.querySelector('.module-card[data-name="'+name+'"]');
  if(card)card.scrollIntoView({{behavior:'smooth',block:'center'}});
}}

/* ── Mermaid layers ── */
function showLayer(id,btn){{
  document.querySelectorAll('.layer-tabs .layer-btn').forEach(b=>b.classList.remove('active'));
  if(btn)btn.classList.add('active');
  document.querySelectorAll('.layer-groups .layer-btn').forEach(b=>b.classList.remove('active'));
  ['mermaid-overview','mermaid-full','mermaid-focus'].forEach(x=>{{
    var el=document.getElementById(x);if(el)el.style.display='none';
  }});
  var target=document.getElementById('mermaid-'+id);
  if(target){{target.style.display='';var pres=target.querySelectorAll('.mermaid:not([data-processed])');if(pres.length)mermaid.run({{nodes:pres}})}}
}}
function showFocusGroup(group){{
  document.querySelectorAll('.layer-tabs .layer-btn').forEach(b=>b.classList.remove('active'));
  document.querySelectorAll('.layer-groups .layer-btn').forEach(b=>{{
    b.classList.toggle('active',b.textContent.startsWith(group));
  }});
  ['mermaid-overview','mermaid-full','mermaid-focus'].forEach(x=>{{
    var el=document.getElementById(x);if(el)el.style.display='none';
  }});
  var box=document.getElementById('mermaid-focus');
  if(!box)return;
  var diagram=_focusData[group];
  if(diagram){{
    box.innerHTML='<pre class="mermaid">'+diagram.replace(/</g,'&lt;').replace(/>/g,'&gt;')+'</pre>';
    box.style.display='';
    mermaid.run({{nodes:box.querySelectorAll('.mermaid')}}).then(bindMermaidClicks);
  }}else{{
    box.innerHTML='<div style="color:var(--muted);font-size:13px;padding:12px">Use read_chapter to explore this group in detail.</div>';
    box.style.display='';
  }}
}}

/* ── Mermaid node click → scroll to module card ── */
function bindMermaidClicks(){{
  document.querySelectorAll('.mermaid svg .node,.mermaid svg .nodeLabel').forEach(n=>{{
    n.style.cursor='pointer';
    n.addEventListener('click',function(e){{
      e.stopPropagation();
      var text=(this.textContent||'').trim().replace(/\\s*\\(\\d+.*\\)$/,'');
      highlightModule(text);
    }});
  }});
}}

/* ── Keyboard navigation ── */
document.addEventListener('keydown',function(e){{
  if(e.target.tagName==='INPUT')return;
  if(e.key==='Escape'){{clearHighlights();document.getElementById('searchInput').value='';searchModules('')}}
  if(e.key==='/'){{e.preventDefault();document.getElementById('searchInput').focus()}}
}});

/* ── Init: bind Mermaid clicks after render ── */
mermaid.run().then(bindMermaidClicks).catch(function(){{}});
</script>
</body>
</html>'''


def save_blueprint(
    report_data: dict[str, Any],
    repo_url: str = "",
    total_time: float = 0,
    output_dir: str | Path | None = None,
) -> str:
    """渲染并保存蓝图 HTML 文件。

    Args:
        report_data: codebook_explore 生成的 report_data。
        repo_url: 仓库地址。
        total_time: 总耗时。
        output_dir: 输出目录，默认 ~/.codebook/blueprints/。

    Returns:
        生成的 HTML 文件的绝对路径。
    """
    out_dir = Path(output_dir) if output_dir else _OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    slug = _repo_slug(repo_url)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    filename = f"{slug}_blueprint_{timestamp}.html"
    filepath = out_dir / filename

    # 优先使用 v2 画布渲染器（有 blueprint_summary 时）
    html_content = None
    if report_data.get("blueprint_summary"):
        try:
            from src.tools.blueprint_renderer_v2 import render_blueprint_v2
            html_content = render_blueprint_v2(
                report_data=report_data,
                repo_url=repo_url,
                total_time=total_time,
            )
        except Exception as e:
            logger.warning("blueprint.v2_failed", error=str(e))

    # 回退到 v1
    if html_content is None:
        html_content = render_blueprint_html(
            report_data=report_data,
            repo_url=repo_url,
            total_time=total_time,
        )

    filepath.write_text(html_content, encoding="utf-8")
    logger.info(
        "blueprint.saved",
        path=str(filepath),
        size_kb=round(len(html_content) / 1024, 1),
    )

    return str(filepath)

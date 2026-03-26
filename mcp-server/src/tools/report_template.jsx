/**
 * CodeBook Interactive Report — React 组件
 *
 * 由 codebook_explore 工具生成数据，渲染为可交互的项目分析报告。
 * 支持：模块展开/折叠、依赖图、诊断高亮、健康状态指示。
 *
 * 使用方式：将 report_data JSON 传入 <CodeBookReport data={reportData} />
 */

import { useState, useMemo } from "react";

// ── 颜色常量 ─────────────────────────────────────────────
const COLORS = {
  bg: "#0f1117",
  surface: "#1a1d27",
  surfaceHover: "#22263a",
  border: "#2a2e3f",
  borderActive: "#6366f1",
  text: "#e2e8f0",
  textMuted: "#94a3b8",
  textDim: "#64748b",
  accent: "#6366f1",
  accentLight: "#818cf8",
  green: "#22c55e",
  greenBg: "rgba(34,197,94,0.12)",
  yellow: "#eab308",
  yellowBg: "rgba(234,179,8,0.12)",
  red: "#ef4444",
  redBg: "rgba(239,68,68,0.12)",
  blue: "#3b82f6",
  blueBg: "rgba(59,130,246,0.12)",
};

const healthConfig = {
  green: { color: COLORS.green, bg: COLORS.greenBg, label: "健康" },
  yellow: { color: COLORS.yellow, bg: COLORS.yellowBg, label: "需关注" },
  red: { color: COLORS.red, bg: COLORS.redBg, label: "需拆分" },
};

// ── 子组件 ───────────────────────────────────────────────

function HealthBadge({ health }) {
  const cfg = healthConfig[health] || healthConfig.green;
  return (
    <span
      style={{
        padding: "2px 10px",
        borderRadius: "9999px",
        fontSize: "12px",
        fontWeight: 600,
        color: cfg.color,
        background: cfg.bg,
        border: `1px solid ${cfg.color}33`,
      }}
    >
      {cfg.label}
    </span>
  );
}

function StatCard({ label, value, icon }) {
  return (
    <div
      style={{
        background: COLORS.surface,
        border: `1px solid ${COLORS.border}`,
        borderRadius: "12px",
        padding: "16px 20px",
        flex: "1 1 140px",
        minWidth: "140px",
      }}
    >
      <div style={{ fontSize: "12px", color: COLORS.textMuted, marginBottom: 4 }}>
        {icon} {label}
      </div>
      <div style={{ fontSize: "24px", fontWeight: 700, color: COLORS.text }}>
        {typeof value === "number" ? value.toLocaleString() : value}
      </div>
    </div>
  );
}

function MermaidBlock({ code }) {
  if (!code) return null;
  return (
    <div
      style={{
        background: COLORS.surface,
        border: `1px solid ${COLORS.border}`,
        borderRadius: "12px",
        padding: "16px",
        marginTop: "16px",
        overflow: "auto",
      }}
    >
      <div style={{ fontSize: "12px", color: COLORS.textMuted, marginBottom: 8 }}>
        Mermaid Diagram
      </div>
      <pre
        style={{
          fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
          fontSize: "13px",
          color: COLORS.textMuted,
          whiteSpace: "pre-wrap",
          wordBreak: "break-word",
          margin: 0,
        }}
      >
        {code}
      </pre>
    </div>
  );
}

function ChapterDetail({ chapter }) {
  if (!chapter) return null;
  const cards = chapter.module_cards || [];

  return (
    <div style={{ marginTop: 12 }}>
      {chapter.summary && (
        <p style={{ color: COLORS.textMuted, fontSize: 13, lineHeight: 1.6, margin: "0 0 12px" }}>
          {chapter.summary}
        </p>
      )}
      {cards.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {cards.slice(0, 8).map((card, i) => (
            <div
              key={i}
              style={{
                background: COLORS.bg,
                border: `1px solid ${COLORS.border}`,
                borderRadius: 8,
                padding: "10px 14px",
              }}
            >
              <div style={{ fontSize: 13, fontWeight: 600, color: COLORS.accentLight }}>
                {card.name || card.title || `Card ${i + 1}`}
              </div>
              {card.description && (
                <div style={{ fontSize: 12, color: COLORS.textDim, marginTop: 4 }}>
                  {card.description}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
      <MermaidBlock code={chapter.dependency_graph} />
    </div>
  );
}

function DiagnosisDetail({ diagnosis }) {
  if (!diagnosis) return null;
  const matches = diagnosis.matches || [];
  const locations = diagnosis.code_locations || [];

  return (
    <div style={{ marginTop: 12 }}>
      {matches.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <div style={{ fontSize: 12, color: COLORS.textMuted, marginBottom: 6 }}>
            匹配到的代码位置
          </div>
          {matches.slice(0, 5).map((m, i) => (
            <div
              key={i}
              style={{
                background: COLORS.bg,
                border: `1px solid ${COLORS.border}`,
                borderRadius: 6,
                padding: "8px 12px",
                marginBottom: 4,
                fontSize: 13,
              }}
            >
              <span style={{ color: COLORS.accentLight, fontFamily: "monospace" }}>
                {m.node_id || m.name || "unknown"}
              </span>
              {m.file_path && (
                <span style={{ color: COLORS.textDim, marginLeft: 8, fontSize: 11 }}>
                  {m.file_path}:{m.line_start || "?"}
                </span>
              )}
              {m.score != null && (
                <span style={{ color: COLORS.yellow, marginLeft: 8, fontSize: 11 }}>
                  score: {m.score.toFixed(1)}
                </span>
              )}
            </div>
          ))}
        </div>
      )}
      <MermaidBlock code={diagnosis.mermaid} />
    </div>
  );
}

function ModuleCard({ mod, defaultExpanded }) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const hasDetails = mod.chapter || mod.diagnosis;

  return (
    <div
      style={{
        background: COLORS.surface,
        border: `1px solid ${expanded ? COLORS.borderActive : COLORS.border}`,
        borderRadius: "12px",
        overflow: "hidden",
        transition: "border-color 0.2s",
      }}
    >
      <div
        onClick={() => hasDetails && setExpanded(!expanded)}
        style={{
          padding: "16px 20px",
          cursor: hasDetails ? "pointer" : "default",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          userSelect: "none",
        }}
      >
        <div style={{ flex: 1 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{ fontSize: 15, fontWeight: 600, color: COLORS.text }}>
              {mod.name}
            </span>
            <HealthBadge health={mod.health} />
            {mod.is_selected && (
              <span
                style={{
                  padding: "2px 8px",
                  borderRadius: "9999px",
                  fontSize: 11,
                  color: COLORS.accent,
                  background: `${COLORS.accent}15`,
                  border: `1px solid ${COLORS.accent}33`,
                }}
              >
                已深入分析
              </span>
            )}
          </div>
          <div style={{ fontSize: 13, color: COLORS.textMuted, marginTop: 4, lineHeight: 1.5 }}>
            {mod.body || mod.title}
          </div>
          <div style={{ display: "flex", gap: 16, marginTop: 8, flexWrap: "wrap" }}>
            {mod.depends_on?.length > 0 && (
              <span style={{ fontSize: 11, color: COLORS.textDim }}>
                依赖: {mod.depends_on.join(", ")}
              </span>
            )}
            {mod.used_by?.length > 0 && (
              <span style={{ fontSize: 11, color: COLORS.textDim }}>
                被依赖: {mod.used_by.join(", ")}
              </span>
            )}
          </div>
        </div>
        {hasDetails && (
          <span
            style={{
              color: COLORS.textDim,
              fontSize: 18,
              transform: expanded ? "rotate(180deg)" : "rotate(0deg)",
              transition: "transform 0.2s",
              marginLeft: 12,
            }}
          >
            V
          </span>
        )}
      </div>

      {expanded && hasDetails && (
        <div
          style={{
            padding: "0 20px 16px",
            borderTop: `1px solid ${COLORS.border}`,
          }}
        >
          {mod.chapter && (
            <div style={{ marginTop: 12 }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: COLORS.blue, marginBottom: 6 }}>
                模块详情
              </div>
              <ChapterDetail chapter={mod.chapter} />
            </div>
          )}
          {mod.diagnosis && (
            <div style={{ marginTop: 16 }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: COLORS.yellow, marginBottom: 6 }}>
                诊断结果
              </div>
              <DiagnosisDetail diagnosis={mod.diagnosis} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── 主组件 ───────────────────────────────────────────────

export default function CodeBookReport({ data }) {
  const [filter, setFilter] = useState("all"); // all | selected | unhealthy

  // 如果没有数据，显示空状态
  if (!data) {
    return (
      <div
        style={{
          background: COLORS.bg,
          color: COLORS.text,
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontFamily: "'Inter', -apple-system, sans-serif",
        }}
      >
        <div style={{ textAlign: "center" }}>
          <div style={{ fontSize: 48, marginBottom: 16 }}>CB</div>
          <div style={{ fontSize: 18, color: COLORS.textMuted }}>
            等待 CodeBook 分析数据...
          </div>
        </div>
      </div>
    );
  }

  const { overview, module_cards = [], health_overview, query, role, selection_strategy } = data;
  const stats = overview?.stats || {};

  const filteredModules = useMemo(() => {
    switch (filter) {
      case "selected":
        return module_cards.filter((m) => m.is_selected);
      case "unhealthy":
        return module_cards.filter((m) => m.health !== "green");
      default:
        return module_cards;
    }
  }, [module_cards, filter]);

  const filterButtons = [
    { key: "all", label: `全部 (${module_cards.length})` },
    { key: "selected", label: `已分析 (${module_cards.filter((m) => m.is_selected).length})` },
    { key: "unhealthy", label: `需关注 (${module_cards.filter((m) => m.health !== "green").length})` },
  ];

  return (
    <div
      style={{
        background: COLORS.bg,
        color: COLORS.text,
        minHeight: "100vh",
        fontFamily: "'Inter', -apple-system, sans-serif",
        padding: "24px 32px",
        maxWidth: 960,
        margin: "0 auto",
      }}
    >
      {/* Header */}
      <div style={{ marginBottom: 32 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 8 }}>
          <span
            style={{
              fontSize: 28,
              fontWeight: 800,
              background: `linear-gradient(135deg, ${COLORS.accent}, ${COLORS.accentLight})`,
              WebkitBackgroundClip: "text",
              WebkitTextFillColor: "transparent",
            }}
          >
            CodeBook
          </span>
          <span style={{ fontSize: 14, color: COLORS.textDim, fontWeight: 400 }}>
            Interactive Report
          </span>
        </div>

        {query && (
          <div
            style={{
              background: COLORS.blueBg,
              border: `1px solid ${COLORS.blue}33`,
              borderRadius: 8,
              padding: "10px 16px",
              fontSize: 14,
              color: COLORS.blue,
              marginBottom: 16,
            }}
          >
            Query: {query}
          </div>
        )}

        <div style={{ fontSize: 14, color: COLORS.textMuted, lineHeight: 1.8 }}>
          {overview?.project_overview || "项目分析完成"}
        </div>
      </div>

      {/* Stats Grid */}
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 24 }}>
        <StatCard icon="F" label="文件" value={stats.code_files || stats.files || 0} />
        <StatCard icon="M" label="模块" value={stats.modules || 0} />
        <StatCard icon="fn" label="函数" value={stats.functions || 0} />
        <StatCard icon="Cl" label="类" value={stats.classes || 0} />
        <StatCard icon="L" label="代码行" value={stats.total_lines || 0} />
      </div>

      {/* Warnings */}
      {overview?.parse_warnings?.length > 0 && (
        <div
          style={{
            background: COLORS.yellowBg,
            border: `1px solid ${COLORS.yellow}33`,
            borderRadius: 8,
            padding: "12px 16px",
            marginBottom: 24,
          }}
        >
          {overview.parse_warnings.map((w, i) => (
            <div key={i} style={{ fontSize: 13, color: COLORS.yellow, marginBottom: 4 }}>
              {w}
            </div>
          ))}
        </div>
      )}

      {/* Mermaid Diagram */}
      <MermaidBlock code={overview?.mermaid_diagram} />

      {/* Module Filter */}
      <div
        style={{
          display: "flex",
          gap: 8,
          marginTop: 32,
          marginBottom: 16,
        }}
      >
        {filterButtons.map((btn) => (
          <button
            key={btn.key}
            onClick={() => setFilter(btn.key)}
            style={{
              padding: "6px 16px",
              borderRadius: "9999px",
              fontSize: 13,
              fontWeight: 500,
              border: "1px solid",
              borderColor: filter === btn.key ? COLORS.accent : COLORS.border,
              background: filter === btn.key ? `${COLORS.accent}20` : "transparent",
              color: filter === btn.key ? COLORS.accentLight : COLORS.textMuted,
              cursor: "pointer",
              transition: "all 0.15s",
            }}
          >
            {btn.label}
          </button>
        ))}
      </div>

      {/* Module Cards */}
      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        {filteredModules.map((mod) => (
          <ModuleCard key={mod.name} mod={mod} defaultExpanded={mod.is_selected} />
        ))}
      </div>

      {/* Health Overview (when no specific query) */}
      {health_overview && (
        <div style={{ marginTop: 32 }}>
          <div style={{ fontSize: 16, fontWeight: 600, color: COLORS.text, marginBottom: 12 }}>
            项目健康概览
          </div>
          <DiagnosisDetail diagnosis={health_overview} />
        </div>
      )}

      {/* Footer */}
      <div
        style={{
          marginTop: 48,
          paddingTop: 16,
          borderTop: `1px solid ${COLORS.border}`,
          fontSize: 12,
          color: COLORS.textDim,
          textAlign: "center",
        }}
      >
        Generated by CodeBook &middot; {role.toUpperCase()} view &middot;{" "}
        {selection_strategy === "query_driven"
          ? "问题驱动分析"
          : selection_strategy === "topology_driven"
          ? "拓扑驱动分析"
          : "自动分析"}
      </div>
    </div>
  );
}

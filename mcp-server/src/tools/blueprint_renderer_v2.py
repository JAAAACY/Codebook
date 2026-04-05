"""Blueprint renderer v2 — self-contained HTML with SVG canvas, dark theme, UE5-style nodes.

Public API:
    render_blueprint_v2(report_data, repo_url="", total_time=0) -> str
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from src.tools.canvas_layout import layout_flows, layout_module_detail, layout_overview

# ── CSS (module-level constant) ──────────────────────────────

_CSS = """\
* { margin: 0; padding: 0; box-sizing: border-box; }
html, body { height: 100%; overflow: hidden; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0a0b10; color: #e0e2f0; }
#header { position: fixed; top: 0; left: 0; right: 0; height: 48px; background: #13151f; border-bottom: 1px solid #252838; display: flex; align-items: center; padding: 0 16px; z-index: 100; gap: 12px; }
#header .logo { font-weight: 700; font-size: 15px; color: #6366f1; letter-spacing: 0.5px; }
#header .breadcrumb { font-size: 13px; color: #8b8fa8; cursor: pointer; }
#header .breadcrumb span { color: #6366f1; cursor: pointer; }
#header .breadcrumb span:hover { text-decoration: underline; }
#header .sep { color: #3a3f55; margin: 0 4px; }
#header .current { color: #e0e2f0; }
#header .project-name { margin-left: auto; font-size: 12px; color: #5a5f78; }
#canvas-container { position: fixed; top: 48px; left: 0; right: 320px; bottom: 0; overflow: hidden; background: #0a0b10; }
#canvas-container.chat-collapsed { right: 0; }
#canvas { width: 100%; height: 100%; }
#chat-panel { position: fixed; top: 48px; right: 0; bottom: 0; width: 320px; background: #13151f; border-left: 1px solid #252838; display: flex; flex-direction: column; transition: transform 0.2s; z-index: 90; }
#chat-panel.collapsed { transform: translateX(320px); }
#chat-panel .chat-header { height: 40px; display: flex; align-items: center; justify-content: space-between; padding: 0 12px; border-bottom: 1px solid #252838; font-size: 13px; color: #8b8fa8; }
#chat-panel .chat-header button { background: none; border: none; color: #8b8fa8; cursor: pointer; font-size: 16px; }
#chat-panel .chat-body { flex: 1; padding: 16px; overflow-y: auto; font-size: 13px; color: #5a5f78; display: flex; align-items: center; justify-content: center; text-align: center; }
#chat-toggle { position: fixed; top: 56px; right: 8px; background: #13151f; border: 1px solid #252838; color: #8b8fa8; width: 28px; height: 28px; border-radius: 4px; cursor: pointer; font-size: 14px; display: none; z-index: 91; }
#chat-toggle.visible { display: block; }
.node-rect { rx: 8; ry: 8; }
.node-label { font-size: 13px; font-weight: 600; fill: #e0e2f0; pointer-events: none; }
.node-desc { font-size: 11px; fill: #8b8fa8; pointer-events: none; }
.edge-line { fill: none; stroke-width: 1.5; }
.edge-label { font-size: 10px; fill: #5a5f78; }
.pin { r: 4; }
.detail-header { font-size: 12px; font-weight: 600; fill: #e0e2f0; }
.detail-sub { font-size: 10px; fill: #6366f1; }
.detail-body { font-size: 10px; fill: #8b8fa8; }
.flow-name { font-size: 16px; font-weight: 700; }
.flow-desc { font-size: 11px; fill: #5a5f78; }
.flow-step { rx: 8; ry: 8; fill: #1a1d2b; stroke-width: 1.5; }
.flow-step-text { font-size: 12px; fill: #e0e2f0; text-anchor: middle; dominant-baseline: central; }
.flow-arrow { fill: none; stroke-width: 1.5; marker-end: url(#arrowhead); }
"""

# ── JS engine (module-level constant) ────────────────────────

_JS = """\
(function() {
  var data = window.__BLUEPRINT_DATA;
  var overview = data.overview;
  var details = data.details;
  var svg = document.getElementById('canvas');
  var container = document.getElementById('canvas-container');
  var chatPanel = document.getElementById('chat-panel');
  var chatToggle = document.getElementById('chat-toggle');

  var scale = 1, panX = 0, panY = 0;
  var isDragging = false, dragStartX = 0, dragStartY = 0, startPanX = 0, startPanY = 0;
  var currentView = 'overview';
  var root = null;

  function esc(s) {
    if (!s) return '';
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  function wordWrap(text, maxChars) {
    if (!text) return [''];
    maxChars = maxChars || 24;
    var lines = [], current = '';
    for (var i = 0; i < text.length; i++) {
      current += text[i];
      if (current.length >= maxChars && (text[i] === ',' || text[i] === ' ' || text[i] === '，' || text[i] === '、')) {
        lines.push(current);
        current = '';
      }
    }
    if (current) lines.push(current);
    return lines;
  }

  function applyTransform() {
    if (root) root.setAttribute('transform', 'translate(' + panX + ',' + panY + ') scale(' + scale + ')');
  }

  // Zoom
  container.addEventListener('wheel', function(e) {
    e.preventDefault();
    var rect = container.getBoundingClientRect();
    var mx = e.clientX - rect.left;
    var my = e.clientY - rect.top;
    var oldScale = scale;
    var delta = e.deltaY > 0 ? 0.9 : 1.1;
    scale = Math.max(0.2, Math.min(3, scale * delta));
    panX = mx - (mx - panX) * (scale / oldScale);
    panY = my - (my - panY) * (scale / oldScale);
    applyTransform();
  }, {passive: false});

  // Pan
  container.addEventListener('mousedown', function(e) {
    if (e.target.closest('.node-group')) return;
    isDragging = true;
    dragStartX = e.clientX; dragStartY = e.clientY;
    startPanX = panX; startPanY = panY;
    container.style.cursor = 'grabbing';
  });
  window.addEventListener('mousemove', function(e) {
    if (!isDragging) return;
    panX = startPanX + (e.clientX - dragStartX);
    panY = startPanY + (e.clientY - dragStartY);
    applyTransform();
  });
  window.addEventListener('mouseup', function() {
    isDragging = false;
    container.style.cursor = 'default';
  });

  function clearSVG() {
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    root = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    root.id = 'canvas-root';
    svg.appendChild(root);
    applyTransform();
  }

  function makeBezier(x1, y1, x2, y2) {
    var cx = (x1 + x2) / 2;
    return 'M' + x1 + ',' + y1 + ' C' + cx + ',' + y1 + ' ' + cx + ',' + y2 + ' ' + x2 + ',' + y2;
  }

  // ── Flows ──

  window.renderFlows = function() {
    currentView = 'flows';
    scale = 1; panX = 0; panY = 0;
    clearSVG();
    updateBreadcrumb(null);

    var flows = data.flows || [];
    if (!flows.length) return;

    // Add arrowhead marker
    var defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs');
    var marker = document.createElementNS('http://www.w3.org/2000/svg', 'marker');
    marker.setAttribute('id', 'arrowhead');
    marker.setAttribute('markerWidth', '8');
    marker.setAttribute('markerHeight', '6');
    marker.setAttribute('refX', '8');
    marker.setAttribute('refY', '3');
    marker.setAttribute('orient', 'auto');
    var arrow = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    arrow.setAttribute('d', 'M0,0 L8,3 L0,6');
    arrow.setAttribute('fill', 'none');
    arrow.setAttribute('stroke', '#5a5f78');
    arrow.setAttribute('stroke-width', '1');
    marker.appendChild(arrow);
    defs.appendChild(marker);
    root.appendChild(defs);

    flows.forEach(function(fl) {
      var nodeMap = {};
      fl.nodes.forEach(function(n) { nodeMap[n.id] = n; });

      // Flow name label (left of first node)
      var firstNode = fl.nodes[0];
      if (firstNode) {
        var nameText = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        nameText.setAttribute('x', firstNode.x);
        nameText.setAttribute('y', firstNode.y - 28);
        nameText.setAttribute('class', 'flow-name');
        nameText.setAttribute('fill', fl.color);
        nameText.textContent = fl.name;
        root.appendChild(nameText);

        if (fl.description) {
          var descText = document.createElementNS('http://www.w3.org/2000/svg', 'text');
          descText.setAttribute('x', firstNode.x);
          descText.setAttribute('y', firstNode.y - 12);
          descText.setAttribute('class', 'flow-desc');
          descText.textContent = fl.description;
          root.appendChild(descText);
        }
      }

      // Connections (arrows)
      fl.connections.forEach(function(c) {
        var fromN = nodeMap[c.from_id];
        var toN = nodeMap[c.to_id];
        if (!fromN || !toN) return;
        var x1 = fromN.x + fromN.width;
        var y1 = fromN.y + fromN.height / 2;
        var x2 = toN.x;
        var y2 = toN.y + toN.height / 2;
        var line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        line.setAttribute('x1', x1);
        line.setAttribute('y1', y1);
        line.setAttribute('x2', x2);
        line.setAttribute('y2', y2);
        line.setAttribute('class', 'flow-arrow');
        line.setAttribute('stroke', fl.color);
        root.appendChild(line);
      });

      // Step nodes
      fl.nodes.forEach(function(n) {
        var g = document.createElementNS('http://www.w3.org/2000/svg', 'g');

        var rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        rect.setAttribute('x', n.x);
        rect.setAttribute('y', n.y);
        rect.setAttribute('width', n.width);
        rect.setAttribute('height', n.height);
        rect.setAttribute('class', 'flow-step');
        rect.setAttribute('stroke', fl.color);
        g.appendChild(rect);

        var text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        text.setAttribute('x', n.x + n.width / 2);
        text.setAttribute('y', n.y + n.height / 2);
        text.setAttribute('class', 'flow-step-text');
        text.textContent = n.text;
        g.appendChild(text);

        root.appendChild(g);
      });
    });
  };

  // ── Overview ──

  window.renderOverview = function() {
    currentView = 'overview';
    scale = 1; panX = 0; panY = 0;
    clearSVG();
    updateBreadcrumb(null);

    var nodeMap = {};
    overview.nodes.forEach(function(n) { nodeMap[n.id] = n; });

    // Edges
    overview.edges.forEach(function(e) {
      var fromN = nodeMap[e.from_id];
      var toN = nodeMap[e.to_id];
      if (!fromN || !toN) return;
      var x1 = fromN.x + fromN.width;
      var y1 = fromN.y + fromN.height / 2;
      var x2 = toN.x;
      var y2 = toN.y + toN.height / 2;
      var strong = e.call_count > 3;

      var path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      path.setAttribute('d', makeBezier(x1, y1, x2, y2));
      path.setAttribute('class', 'edge-line');
      path.setAttribute('stroke', strong ? '#6366f1' : '#3a3f55');
      root.appendChild(path);

      if (e.verb) {
        var mx = (x1 + x2) / 2, my = (y1 + y2) / 2 - 8;
        var lbl = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        lbl.setAttribute('x', mx); lbl.setAttribute('y', my);
        lbl.setAttribute('text-anchor', 'middle');
        lbl.setAttribute('class', 'edge-label');
        lbl.textContent = e.verb;
        root.appendChild(lbl);
      }
    });

    // Nodes
    overview.nodes.forEach(function(n) {
      var g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
      g.setAttribute('class', 'node-group');
      g.style.cursor = 'pointer';

      var rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
      rect.setAttribute('x', n.x); rect.setAttribute('y', n.y);
      rect.setAttribute('width', n.width); rect.setAttribute('height', n.height);
      rect.setAttribute('fill', '#13151f');
      rect.setAttribute('stroke', n.color);
      rect.setAttribute('stroke-width', '1.5');
      rect.setAttribute('class', 'node-rect');
      g.appendChild(rect);

      var title = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      title.setAttribute('x', n.x + 12); title.setAttribute('y', n.y + 28);
      title.setAttribute('class', 'node-label');
      title.textContent = n.label;
      g.appendChild(title);

      var desc = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      desc.setAttribute('x', n.x + 12); desc.setAttribute('y', n.y + 48);
      desc.setAttribute('class', 'node-desc');
      desc.textContent = n.description.length > 28 ? n.description.substring(0, 26) + '…' : n.description;
      g.appendChild(desc);

      // Left pin
      var lp = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      lp.setAttribute('cx', n.x); lp.setAttribute('cy', n.y + n.height / 2);
      lp.setAttribute('class', 'pin'); lp.setAttribute('fill', '#3a3f55');
      g.appendChild(lp);

      // Right pin
      var rp = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      rp.setAttribute('cx', n.x + n.width); rp.setAttribute('cy', n.y + n.height / 2);
      rp.setAttribute('class', 'pin'); rp.setAttribute('fill', '#3a3f55');
      g.appendChild(rp);

      g.addEventListener('dblclick', function() { enterModule(n.id); });
      root.appendChild(g);
    });
  };

  // ── Detail ──

  window.enterModule = function(moduleId) {
    var d = details[moduleId];
    if (!d) return;
    currentView = moduleId;
    scale = 1; panX = 0; panY = 0;
    clearSVG();

    var modLabel = moduleId;
    overview.nodes.forEach(function(n) { if (n.id === moduleId) modLabel = n.label; });
    updateBreadcrumb(modLabel);

    var nodeMap = {};
    d.nodes.forEach(function(n) { nodeMap[n.id] = n; });

    // Edges
    d.edges.forEach(function(e) {
      var fromN = nodeMap[e.from_id];
      var toN = nodeMap[e.to_id];
      if (!fromN || !toN) return;
      var x1 = fromN.x + fromN.width;
      var y1 = fromN.y + fromN.height / 2;
      var x2 = toN.x;
      var y2 = toN.y + toN.height / 2;
      var path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      path.setAttribute('d', makeBezier(x1, y1, x2, y2));
      path.setAttribute('class', 'edge-line');
      path.setAttribute('stroke', '#3a3f55');
      root.appendChild(path);
    });

    // Function nodes
    d.nodes.forEach(function(n) {
      var g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
      g.setAttribute('class', 'node-group');

      var rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
      rect.setAttribute('x', n.x); rect.setAttribute('y', n.y);
      rect.setAttribute('width', n.width); rect.setAttribute('height', n.height);
      rect.setAttribute('fill', '#13151f');
      rect.setAttribute('stroke', '#252838');
      rect.setAttribute('stroke-width', '1');
      rect.setAttribute('class', 'node-rect');
      g.appendChild(rect);

      // Business name
      var t1 = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      t1.setAttribute('x', n.x + 12); t1.setAttribute('y', n.y + 22);
      t1.setAttribute('class', 'detail-header');
      t1.textContent = n.business_name || n.code_name;
      g.appendChild(t1);

      // Code name + location
      var t2 = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      t2.setAttribute('x', n.x + 12); t2.setAttribute('y', n.y + 40);
      t2.setAttribute('class', 'detail-sub');
      t2.textContent = n.code_name + '()  ' + n.file_path + ':' + n.line_start;
      g.appendChild(t2);

      // Explanation (wrapped)
      var lines = wordWrap(n.explanation, 32);
      for (var i = 0; i < Math.min(lines.length, 3); i++) {
        var tl = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        tl.setAttribute('x', n.x + 12); tl.setAttribute('y', n.y + 60 + i * 14);
        tl.setAttribute('class', 'detail-body');
        tl.textContent = lines[i];
        g.appendChild(tl);
      }

      // Params pin row
      var paramText = (n.params || []).join(', ');
      if (paramText) {
        var tp = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        tp.setAttribute('x', n.x + 12); tp.setAttribute('y', n.y + n.height - 12);
        tp.setAttribute('class', 'detail-body');
        tp.textContent = '→ ' + paramText + (n.return_type ? ' → ' + n.return_type : '');
        g.appendChild(tp);
      }

      root.appendChild(g);
    });
  };

  // ── Breadcrumb ──

  function updateBreadcrumb(moduleName) {
    var bc = document.getElementById('breadcrumb');
    if (!moduleName) {
      bc.innerHTML = '<span class="current">Overview</span>';
    } else {
      bc.innerHTML = '<span onclick="showOverview()">Overview</span><span class="sep"> / </span><span class="current">' + esc(moduleName) + '</span>';
    }
  }

  window.showOverview = function() {
    if (data.flows && data.flows.length) {
      renderFlows();
    } else {
      renderOverview();
    }
  };

  // ── Chat toggle ──

  window.toggleChat = function() {
    chatPanel.classList.toggle('collapsed');
    container.classList.toggle('chat-collapsed');
    chatToggle.classList.toggle('visible');
  };

  // Init — prefer flows view when data available
  if (data.flows && data.flows.length) {
    renderFlows();
  } else {
    renderOverview();
  }
})();
"""


# ── Health string to float ───────────────────────────────────

_HEALTH_MAP: dict[str, float] = {"green": 0.8, "yellow": 0.5, "red": 0.2}


# ── Public API ───────────────────────────────────────────────


def render_blueprint_v2(
    report_data: dict[str, Any],
    repo_url: str = "",
    total_time: float = 0,
) -> str:
    """Render a self-contained HTML page with SVG canvas blueprint.

    Args:
        report_data: Full report dict; ``blueprint_summary`` key is optional.
        repo_url: Repository URL (for display only).
        total_time: Scan duration in seconds.

    Returns:
        Complete HTML string.
    """
    summary = report_data.get("blueprint_summary") or {}
    project_name = summary.get("project_name", "CodeBook")
    modules_raw: list[dict[str, Any]] = summary.get("modules", [])
    connections_raw: list[dict[str, Any]] = summary.get("connections", [])

    # ── Prepare layout input for overview ──
    ov_modules: list[dict[str, Any]] = []
    for m in modules_raw:
        health_str = m.get("health", "green")
        ov_modules.append(
            {
                "id": m["code_path"],
                "label": m.get("business_name", m["code_path"]),
                "description": m.get("description", ""),
                "health": _HEALTH_MAP.get(health_str, 0.5),
            }
        )

    ov_connections: list[dict[str, Any]] = [
        {
            "from": c["from_module"],
            "to": c["to_module"],
            "verb": c.get("verb", ""),
            "call_count": c.get("call_count", 0),
        }
        for c in connections_raw
    ]

    # ── Prepare flow lines (if available) ──
    flows_raw: list[dict[str, Any]] = summary.get("flows", [])
    flow_lines = layout_flows(flows_raw) if flows_raw else []

    if ov_modules:
        ov_nodes, ov_edges = layout_overview(ov_modules, ov_connections)
    else:
        ov_nodes, ov_edges = [], []

    # ── Prepare detail layouts per module ──
    details: dict[str, dict[str, Any]] = {}
    # Build callees map from module_cards
    module_cards = report_data.get("module_cards", [])
    callees_by_module: dict[str, dict[str, list[str]]] = {}
    for card in module_cards:
        card_name = card.get("name", "")
        callees_map: dict[str, list[str]] = {}
        for chain in card.get("call_chains", []):
            fn = chain.get("function", "")
            callees_map[fn] = chain.get("callees", [])
        callees_by_module[card_name] = callees_map

    for m in modules_raw:
        code_path = m["code_path"]
        functions_raw = m.get("functions", [])
        functions_input: list[dict[str, Any]] = []
        for f in functions_raw:
            params = f.get("params", [])
            # Normalize params to list of dicts if they are plain strings
            param_list: list[dict[str, str]] = []
            for p in params:
                if isinstance(p, dict):
                    param_list.append(p)
                else:
                    param_list.append({"name": str(p), "type": ""})
            functions_input.append(
                {
                    "id": f["code_name"],
                    "business_name": f.get("business_name", ""),
                    "code_name": f["code_name"],
                    "file_path": f.get("file_path", ""),
                    "line_start": f.get("line_start", 0),
                    "explanation": f.get("explanation", ""),
                    "params": param_list,
                    "return_type": f.get("return_type", ""),
                }
            )

        callers_map: dict[str, list[str]] = {}
        callees_map_for_mod = callees_by_module.get(code_path, {})

        dt_nodes, dt_edges = layout_module_detail(
            functions_input, callers_map, callees_map_for_mod
        )

        details[code_path] = {
            "nodes": [asdict(n) for n in dt_nodes],
            "edges": [asdict(e) for e in dt_edges],
        }

    # ── Build JSON payload ──
    flows_payload: list[dict[str, Any]] = []
    for fl in flow_lines:
        flows_payload.append({
            "name": fl.name,
            "description": fl.description,
            "color": fl.color,
            "nodes": [asdict(n) for n in fl.nodes],
            "connections": [asdict(c) for c in fl.connections],
        })

    blueprint_data = {
        "projectName": project_name,
        "repoUrl": repo_url,
        "totalTime": total_time,
        "flows": flows_payload,
        "overview": {
            "nodes": [asdict(n) for n in ov_nodes],
            "edges": [asdict(e) for e in ov_edges],
        },
        "details": details,
    }

    data_json = json.dumps(blueprint_data, ensure_ascii=False)
    # Prevent XSS via </script> injection
    data_json = data_json.replace("</", "<\\/")

    # ── Assemble HTML ──
    html = f"""\
<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CodeBook — {_esc(project_name)}</title>
<style>
{_CSS}
</style>
</head>
<body>
<div id="header">
  <div class="logo">CodeBook</div>
  <div id="breadcrumb" class="breadcrumb"><span class="current">Overview</span></div>
  <div class="project-name">{_esc(project_name)}</div>
</div>
<div id="canvas-container">
  <svg id="canvas" xmlns="http://www.w3.org/2000/svg"></svg>
</div>
<button id="chat-toggle" onclick="toggleChat()" title="Show chat">💬</button>
<div id="chat-panel">
  <div class="chat-header">
    <span>MCP Chat</span>
    <button onclick="toggleChat()" title="Hide">✕</button>
  </div>
  <div class="chat-body">
    <p>通过 MCP 对话了解更多项目细节<br><small style="color:#3a3f55">（即将推出）</small></p>
  </div>
</div>
<script>
window.__BLUEPRINT_DATA = {data_json};
{_JS}
</script>
</body>
</html>"""

    return html


# ── Helpers ──────────────────────────────────────────────────


def _esc(s: str) -> str:
    """HTML-escape a string."""
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )

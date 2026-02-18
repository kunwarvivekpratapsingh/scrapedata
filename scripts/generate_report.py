"""Generate a self-contained HTML report from eval_results.json.

Usage:
    py scripts/generate_report.py
    py scripts/generate_report.py --input eval_results.json --output eval_report.html

Reads the JSON produced by run_eval.py and renders a rich, human-readable HTML
page with per-question accordions showing:
  - The conversation timeline (Builder → Critic → Executor)
  - Every DAG iteration with full node code and critic feedback
  - Node outputs from sandbox execution

No external dependencies — pure stdlib only.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from datetime import datetime
from pathlib import Path


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def _e(text: object) -> str:
    """HTML-escape any value for safe insertion into HTML."""
    return html.escape(str(text))


def format_answer(val: object) -> str:
    """Format a final_answer value (any type) as a readable string."""
    if val is None:
        return "—"
    if isinstance(val, bool):
        return str(val)
    if isinstance(val, float):
        # :g strips trailing zeros; handles reasonable ranges without sci notation
        return f"{val:.6g}"
    if isinstance(val, int):
        return str(val)
    if isinstance(val, str):
        return val
    if isinstance(val, list):
        if len(val) <= 20:
            return json.dumps(val, indent=2)
        return json.dumps(val[:20], indent=2) + f"\n... ({len(val)} total items)"
    if isinstance(val, dict):
        if len(val) <= 30:
            return json.dumps(val, indent=2)
        truncated = dict(list(val.items())[:30])
        return json.dumps(truncated, indent=2) + f"\n... ({len(val)} total keys)"
    return repr(val)


def format_node_output(val: object) -> str:
    """Format a single node's output value with truncation for large structures."""
    if val is None:
        return "None"
    if isinstance(val, (bool, int, float, str)):
        return str(val)
    if isinstance(val, list):
        if len(val) <= 10:
            return json.dumps(val, indent=2)
        return json.dumps(val[:10], indent=2) + f"\n... ({len(val)} total items)"
    if isinstance(val, dict):
        if len(val) <= 20:
            return json.dumps(val, indent=2)
        truncated = dict(list(val.items())[:20])
        return json.dumps(truncated, indent=2) + f"\n... ({len(val)} total keys)"
    return repr(val)


def classify_log_entry(role: str, content: str) -> str:
    """Return a CSS class name for a conversation log entry."""
    if role == "dag_builder":
        return "tl-builder-fail" if "FAILED" in content else "tl-builder"
    if role == "critic":
        return "tl-critic-ok" if "APPROVED" in content else "tl-critic-fail"
    if role == "executor":
        return "tl-exec-ok" if "SUCCESS" in content else "tl-exec-fail"
    return "tl-unknown"


def _timeline_label(role: str, content: str) -> str:
    """Produce a short label for a timeline badge."""
    iter_m = re.search(r"Iteration (\d+)", content)
    iter_n = iter_m.group(1) if iter_m else "?"
    issue_m = re.search(r"(\d+) issue", content)
    issues = issue_m.group(1) if issue_m else "?"

    if role == "dag_builder":
        if "FAILED" in content:
            return f"Build {iter_n} ✗"
        return f"Build {iter_n}"
    if role == "critic":
        if "APPROVED" in content:
            return f"Critic {iter_n} ✓"
        return f"Critic {iter_n} ✗ ({issues})"
    if role == "executor":
        return "Execute ✓" if "SUCCESS" in content else "Execute ✗"
    return role


# ---------------------------------------------------------------------------
# Python syntax highlighter (simple, no external libs)
# ---------------------------------------------------------------------------

_KEYWORDS = {
    "def", "return", "for", "if", "else", "elif", "in", "not", "and", "or",
    "while", "import", "from", "class", "with", "as", "None", "True", "False",
    "lambda", "yield", "raise", "try", "except", "finally", "pass", "break",
    "continue", "global", "nonlocal", "del", "assert", "is",
}

_BUILTINS = {
    "len", "range", "sum", "max", "min", "sorted", "dict", "list", "str",
    "int", "float", "bool", "print", "enumerate", "zip", "map", "filter",
    "any", "all", "round", "abs", "type", "isinstance", "hasattr", "getattr",
    "set", "tuple", "reversed", "next", "iter", "repr", "hash", "id",
}

# Regex patterns that operate on HTML-escaped text
_KW_PAT = re.compile(
    r"(?<![&\w])(" + "|".join(re.escape(k) for k in sorted(_KEYWORDS, key=len, reverse=True)) + r")(?!\w)"
)
_BI_PAT = re.compile(
    r"(?<![&\w])(" + "|".join(re.escape(b) for b in sorted(_BUILTINS, key=len, reverse=True)) + r")(?=\(|\s|$)"
)
# String literals in escaped HTML — single quotes become &#x27; double become &quot;
# We match both the escaped forms and the raw forms (for robustness)
_STR_PAT = re.compile(
    r"(&#x27;[^<]*?&#x27;|&quot;[^<]*?&quot;|'[^'\n]*'|\"[^\"\n]*\")"
)


def _highlight_tokens(text: str) -> str:
    """Apply keyword/builtin/string highlighting to an already-HTML-escaped line."""
    # Strings first (to avoid keyword-highlighting inside them)
    text = _STR_PAT.sub(r'<span class="hl-st">\1</span>', text)
    # Keywords
    text = _KW_PAT.sub(r'<span class="hl-kw">\1</span>', text)
    # Builtins (only highlight when followed by ( to avoid false positives)
    text = _BI_PAT.sub(r'<span class="hl-bi">\1</span>', text)
    return text


def highlight_python(code: str) -> str:
    """Return HTML-safe, syntax-highlighted Python code."""
    result = []
    for line in html.escape(code).split("\n"):
        # Find comment start (first # not inside a HTML entity)
        # Simple heuristic: split on # that isn't preceded by &
        comment_idx = None
        i = 0
        in_str = False
        str_char = None
        while i < len(line):
            ch = line[i]
            if not in_str and ch in ('"', "'"):
                in_str = True
                str_char = ch
            elif in_str and ch == str_char:
                in_str = False
            elif not in_str and ch == "#" and (i == 0 or line[i - 1] != "&"):
                comment_idx = i
                break
            i += 1

        if comment_idx is not None:
            code_part = _highlight_tokens(line[:comment_idx])
            comment_part = f'<span class="hl-cm">{line[comment_idx:]}</span>'
            result.append(code_part + comment_part)
        else:
            result.append(_highlight_tokens(line))
    return "\n".join(result)


# ---------------------------------------------------------------------------
# SVG DAG visualizer
# ---------------------------------------------------------------------------

def render_dag_svg(nodes: list, edges: list) -> str:
    """Render a DAG as an inline SVG using layer-based left-to-right layout.

    Each layer is a vertical column of node boxes.
    Edges are bezier curves with arrowheads.
    No JS or external libs needed — pure SVG.
    """
    if not nodes:
        return ""

    # Group nodes by their layer number
    layers: dict[int, list] = {}
    for n in nodes:
        layer = n.get("layer", 0)
        layers.setdefault(layer, []).append(n)

    max_layer = max(layers.keys())
    max_nodes_in_layer = max(len(v) for v in layers.values())

    # Layout constants (pixels)
    NODE_W  = 210
    NODE_H  = 76
    H_GAP   = 70   # horizontal gap between columns
    V_GAP   = 16   # vertical gap between nodes in same column
    PAD     = 24   # outer padding

    col_w   = NODE_W + H_GAP
    row_h   = NODE_H + V_GAP
    svg_w   = PAD * 2 + (max_layer + 1) * col_w - H_GAP
    svg_h   = PAD * 2 + max_nodes_in_layer * row_h - V_GAP

    # Ensure minimum height
    svg_h = max(svg_h, NODE_H + PAD * 2)

    # Assign (x, y) pixel position to each node_id
    positions: dict[str, tuple[float, float]] = {}
    for layer_idx, layer_nodes in sorted(layers.items()):
        x = PAD + layer_idx * col_w
        total_col_h = len(layer_nodes) * row_h - V_GAP
        start_y = (svg_h - total_col_h) / 2
        for i, node in enumerate(layer_nodes):
            y = start_y + i * row_h
            positions[node["node_id"]] = (x, y)

    # Color per layer (cycles if >5 layers)
    LAYER_COLORS = ["#3b82f6", "#0d9488", "#7c3aed", "#d97706", "#dc2626"]

    out: list[str] = []
    out.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{int(svg_w)}" height="{int(svg_h)}" '
        f'style="max-width:100%;display:block;overflow:visible;">'
    )

    # Arrow marker (reused by all edges)
    out.append(
        '<defs>'
        '<marker id="dag-arrow" markerWidth="9" markerHeight="7" refX="9" refY="3.5" orient="auto">'
        '<polygon points="0 0, 9 3.5, 0 7" fill="#94a3b8"/>'
        '</marker>'
        '</defs>'
    )

    # ── Draw edges (behind nodes) ──
    for edge in edges:
        src = edge.get("source", "")
        tgt = edge.get("target", "")
        if src not in positions or tgt not in positions:
            continue
        sx, sy = positions[src]
        tx, ty = positions[tgt]
        # Exit from right-center of source, enter left-center of target
        x1 = sx + NODE_W
        y1 = sy + NODE_H / 2
        x2 = tx
        y2 = ty + NODE_H / 2
        cx = (x1 + x2) / 2
        out.append(
            f'<path d="M{x1:.1f},{y1:.1f} C{cx:.1f},{y1:.1f} {cx:.1f},{y2:.1f} {x2:.1f},{y2:.1f}" '
            f'fill="none" stroke="#94a3b8" stroke-width="1.8" '
            f'marker-end="url(#dag-arrow)"/>'
        )

    # ── Draw node boxes ──
    for node in nodes:
        nid    = node.get("node_id", "")
        layer  = node.get("layer", 0)
        op     = node.get("operation", "")
        if nid not in positions:
            continue

        x, y   = positions[nid]
        color  = LAYER_COLORS[layer % len(LAYER_COLORS)]
        x_i    = int(x)
        y_i    = int(y)

        # Outer box (white fill, colored border)
        out.append(
            f'<rect x="{x_i}" y="{y_i}" width="{NODE_W}" height="{NODE_H}" '
            f'rx="6" ry="6" fill="white" stroke="{color}" stroke-width="1.8"/>'
        )
        # Colored header bar (top 22px)
        HEADER_H = 22
        out.append(
            f'<rect x="{x_i}" y="{y_i}" width="{NODE_W}" height="{HEADER_H}" '
            f'rx="6" ry="6" fill="{color}"/>'
        )
        # Square off the bottom corners of the header bar
        out.append(
            f'<rect x="{x_i}" y="{y_i + HEADER_H - 6}" width="{NODE_W}" height="6" fill="{color}"/>'
        )

        # node_id label (white, monospace, header)
        out.append(
            f'<text x="{x_i + 8}" y="{y_i + 15}" '
            f'font-family="monospace" font-size="12" fill="white" font-weight="bold">'
            f'{_e(nid)}</text>'
        )

        # Operation text: truncate to 2 lines of ~28 chars each
        op_short = op if len(op) <= 56 else op[:55] + "…"
        line1 = _e(op_short[:28])
        line2 = _e(op_short[28:]) if len(op_short) > 28 else ""
        out.append(
            f'<text x="{x_i + 8}" y="{y_i + 38}" '
            f'font-family="system-ui,sans-serif" font-size="11" fill="#374151">'
            f'{line1}</text>'
        )
        if line2:
            out.append(
                f'<text x="{x_i + 8}" y="{y_i + 52}" '
                f'font-family="system-ui,sans-serif" font-size="11" fill="#374151">'
                f'{line2}</text>'
            )

        # Layer label (bottom-left, colored)
        out.append(
            f'<text x="{x_i + 8}" y="{y_i + NODE_H - 6}" '
            f'font-family="monospace" font-size="10" fill="{color}">'
            f'Layer {layer}</text>'
        )

    out.append("</svg>")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------

def render_css() -> str:
    return """
    :root {
        --green:    #22c55e;
        --green-bg: #dcfce7;
        --green-fg: #166534;
        --red:      #ef4444;
        --red-bg:   #fee2e2;
        --red-fg:   #991b1b;
        --blue-bg:  #dbeafe;
        --blue-fg:  #1e40af;
        --amber-bg: #fef3c7;
        --amber-fg: #92400e;
        --gray-50:  #f9fafb;
        --gray-100: #f3f4f6;
        --gray-200: #e5e7eb;
        --gray-500: #6b7280;
        --gray-700: #374151;
        --gray-900: #111827;
        --bg-code:  #1e1e2e;
        --fg-code:  #cdd6f4;
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }

    body {
        font-family: system-ui, -apple-system, sans-serif;
        font-size: 14px;
        color: var(--gray-900);
        background: var(--gray-50);
        line-height: 1.5;
    }

    .page-wrap { max-width: 980px; margin: 0 auto; padding: 24px 16px 64px; }

    /* ── Header ── */
    .page-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 20px 24px;
        background: white;
        border: 1px solid var(--gray-200);
        border-radius: 10px;
        margin-bottom: 20px;
    }
    .page-header h1 { font-size: 1.5rem; font-weight: 700; color: var(--gray-900); }
    .header-meta { color: var(--gray-500); font-size: 0.85rem; margin-top: 4px; }
    .pass-rate-badge {
        padding: 10px 20px;
        border-radius: 999px;
        font-size: 1.1rem;
        font-weight: 700;
    }
    .pass-rate-badge.ok  { background: var(--green-bg); color: var(--green-fg); }
    .pass-rate-badge.bad { background: var(--red-bg);   color: var(--red-fg); }

    /* ── Section ── */
    .section { margin-bottom: 20px; }
    .section-title {
        font-size: 1rem;
        font-weight: 600;
        color: var(--gray-700);
        margin-bottom: 10px;
        padding-bottom: 6px;
        border-bottom: 2px solid var(--gray-200);
    }

    /* ── Summary cards ── */
    .cards-row {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
        gap: 12px;
    }
    .card {
        background: white;
        border: 1px solid var(--gray-200);
        border-radius: 8px;
        padding: 14px 16px;
    }
    .card-label { font-size: 0.75rem; color: var(--gray-500); text-transform: uppercase; letter-spacing: 0.05em; }
    .card-value { font-size: 1.6rem; font-weight: 700; margin-top: 4px; }
    .card-value.green { color: var(--green); }
    .card-value.red   { color: var(--red); }
    .card-value.blue  { color: #3b82f6; }

    /* ── Difficulty table ── */
    .breakdown-table {
        width: 100%;
        border-collapse: collapse;
        background: white;
        border: 1px solid var(--gray-200);
        border-radius: 8px;
        overflow: hidden;
    }
    .breakdown-table th {
        background: var(--gray-100);
        padding: 8px 14px;
        text-align: left;
        font-size: 0.8rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: var(--gray-500);
    }
    .breakdown-table td { padding: 10px 14px; border-top: 1px solid var(--gray-200); }

    /* ── Badges ── */
    .badge {
        display: inline-block;
        padding: 2px 9px;
        border-radius: 999px;
        font-size: 0.72rem;
        font-weight: 600;
        white-space: nowrap;
    }
    .badge-easy   { background: var(--green-bg); color: var(--green-fg); }
    .badge-medium { background: var(--amber-bg); color: var(--amber-fg); }
    .badge-hard   { background: var(--red-bg);   color: var(--red-fg); }
    .badge-ok     { background: var(--green-bg); color: var(--green-fg); }
    .badge-fail   { background: var(--red-bg);   color: var(--red-fg); }
    .badge-layer  { background: var(--blue-bg);  color: var(--blue-fg); font-size: 0.7rem; }
    .badge-iter-ok   { background: var(--green-bg); color: var(--green-fg); }
    .badge-iter-fail { background: var(--red-bg);   color: var(--red-fg); }

    /* ── Question accordion ── */
    details.q-accordion {
        background: white;
        border: 1px solid var(--gray-200);
        border-radius: 8px;
        margin-bottom: 10px;
        overflow: hidden;
    }
    details.q-accordion.q-ok   > summary { border-left: 4px solid var(--green); }
    details.q-accordion.q-fail > summary { border-left: 4px solid var(--red); }

    details.q-accordion > summary {
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 12px 16px;
        cursor: pointer;
        user-select: none;
        list-style: none;
        flex-wrap: wrap;
    }
    details.q-accordion > summary::-webkit-details-marker { display: none; }
    details.q-accordion[open] > summary { background: var(--gray-50); }

    .q-id    { font-weight: 700; color: var(--gray-500); min-width: 32px; }
    .q-text  { flex: 1; font-weight: 500; }
    .q-iters { font-size: 0.75rem; color: var(--gray-500); margin-left: auto; }

    .q-body { padding: 16px; border-top: 1px solid var(--gray-200); }

    /* ── Answer / Error box ── */
    .answer-box {
        border-radius: 6px;
        padding: 12px 14px;
        margin-bottom: 14px;
        font-family: monospace;
        font-size: 0.85rem;
        white-space: pre-wrap;
        word-break: break-all;
    }
    .answer-box.ok   { background: #f0fdf4; border: 1px solid #bbf7d0; color: #166534; }
    .answer-box.fail { background: #fef2f2; border: 1px solid #fecaca; color: #991b1b; }

    /* ── Timeline ── */
    .timeline { margin-bottom: 14px; }
    .timeline-label { font-size: 0.75rem; font-weight: 600; color: var(--gray-500); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 6px; }
    .timeline-strip { display: flex; flex-wrap: wrap; align-items: center; gap: 4px; }
    .tl-arrow { color: var(--gray-500); font-size: 0.8rem; }

    .tl-badge {
        display: inline-block;
        padding: 3px 10px;
        border-radius: 999px;
        font-size: 0.75rem;
        font-weight: 600;
        cursor: default;
        white-space: nowrap;
    }
    .tl-builder      { background: var(--blue-bg);  color: var(--blue-fg); }
    .tl-builder-fail { background: #fce7f3; color: #9d174d; }
    .tl-critic-ok    { background: var(--green-bg); color: var(--green-fg); }
    .tl-critic-fail  { background: var(--red-bg);   color: var(--red-fg); }
    .tl-exec-ok      { background: var(--green-bg); color: var(--green-fg); }
    .tl-exec-fail    { background: var(--red-bg);   color: var(--red-fg); }
    .tl-unknown      { background: var(--gray-100); color: var(--gray-700); }

    /* ── Iteration accordion ── */
    details.iter-block {
        border: 1px solid var(--gray-200);
        border-radius: 6px;
        margin-bottom: 8px;
        overflow: hidden;
        background: var(--gray-50);
    }
    details.iter-block > summary {
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 9px 14px;
        cursor: pointer;
        user-select: none;
        list-style: none;
        font-weight: 600;
        font-size: 0.85rem;
    }
    details.iter-block > summary::-webkit-details-marker { display: none; }
    details.iter-block[open] > summary { background: var(--gray-100); }
    .iter-body { padding: 14px; border-top: 1px solid var(--gray-200); background: white; }

    /* ── Critic block ── */
    .critic-block { margin-bottom: 12px; }
    .critic-reasoning {
        font-size: 0.85rem;
        color: var(--gray-700);
        margin-bottom: 8px;
        padding: 8px 12px;
        background: var(--gray-50);
        border-radius: 4px;
        border-left: 3px solid var(--gray-200);
    }

    details.sub-block {
        border: 1px solid var(--gray-200);
        border-radius: 4px;
        margin-top: 6px;
        background: white;
    }
    details.sub-block > summary {
        padding: 6px 10px;
        cursor: pointer;
        user-select: none;
        list-style: none;
        font-size: 0.8rem;
        font-weight: 600;
        color: var(--gray-700);
    }
    details.sub-block > summary::-webkit-details-marker { display: none; }
    .sub-block-body { padding: 8px 12px; border-top: 1px solid var(--gray-200); }
    .error-list, .suggest-list {
        padding-left: 18px;
        font-size: 0.82rem;
        color: var(--red-fg);
    }
    .suggest-list { color: var(--amber-fg); }
    .error-list li, .suggest-list li { margin-bottom: 4px; }

    /* ── DAG section ── */
    .dag-section { margin-top: 10px; }
    .dag-description {
        font-size: 0.82rem;
        color: var(--gray-500);
        font-style: italic;
        margin-bottom: 10px;
    }
    .dag-failed {
        padding: 10px 14px;
        background: #fff7ed;
        border: 1px solid #fed7aa;
        border-radius: 6px;
        color: #9a3412;
        font-family: monospace;
        font-size: 0.82rem;
        white-space: pre-wrap;
    }

    /* ── DAG node card ── */
    .dag-node {
        border: 1px solid var(--gray-200);
        border-radius: 6px;
        margin-bottom: 8px;
        overflow: hidden;
    }
    .dag-node-header {
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 8px 12px;
        background: var(--gray-100);
        flex-wrap: wrap;
    }
    .node-id     { font-family: monospace; font-weight: 700; font-size: 0.85rem; }
    .output-type { font-size: 0.72rem; color: var(--gray-500); font-family: monospace; margin-left: auto; }
    .dag-node-operation {
        padding: 6px 12px;
        font-size: 0.82rem;
        color: var(--gray-700);
        font-style: italic;
        border-bottom: 1px solid var(--gray-200);
    }
    .dag-node-inputs {
        padding: 6px 12px;
        font-size: 0.82rem;
        color: var(--gray-700);
        border-bottom: 1px solid var(--gray-200);
    }
    .dag-node-inputs ul { padding-left: 16px; margin-top: 2px; }
    .dag-node-inputs li { font-family: monospace; font-size: 0.8rem; color: var(--gray-500); }
    .dag-node-inputs li code { color: var(--gray-700); }

    /* ── Code block ── */
    pre.code-block {
        background: var(--bg-code);
        color: var(--fg-code);
        padding: 14px 16px;
        overflow-x: auto;
        font-family: 'Cascadia Code', 'Fira Code', 'Consolas', monospace;
        font-size: 0.82rem;
        line-height: 1.65;
        margin: 0;
    }
    .hl-kw { color: #cba6f7; }   /* purple  — keywords */
    .hl-bi { color: #89dceb; }   /* cyan    — builtins */
    .hl-st { color: #a6e3a1; }   /* green   — strings */
    .hl-cm { color: #6c7086; }   /* gray    — comments */

    /* ── Edges ── */
    .edges-row {
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
        padding: 8px 12px;
        font-family: monospace;
        font-size: 0.8rem;
        color: var(--gray-700);
        border-top: 1px solid var(--gray-200);
        background: var(--gray-50);
    }
    .edge-item { background: var(--blue-bg); color: var(--blue-fg); padding: 2px 8px; border-radius: 4px; }
    .final-node-label {
        padding: 6px 12px;
        font-size: 0.8rem;
        color: var(--gray-500);
        border-top: 1px solid var(--gray-200);
    }
    .final-node-label code { font-weight: 600; color: var(--gray-700); }

    /* ── DAG SVG visualizer ── */
    .dag-svg-wrap {
        border: 1px solid var(--gray-200);
        border-radius: 6px;
        padding: 14px 16px;
        background: var(--gray-50);
        margin-bottom: 12px;
        overflow-x: auto;
    }
    .dag-svg-title {
        font-size: 0.75rem;
        font-weight: 600;
        color: var(--gray-500);
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-bottom: 8px;
    }

    /* ── Node outputs table ── */
    .outputs-section { margin-top: 14px; }
    .outputs-section strong { font-size: 0.82rem; color: var(--gray-700); display: block; margin-bottom: 6px; }
    .outputs-table {
        width: 100%;
        border-collapse: collapse;
        border: 1px solid var(--gray-200);
        border-radius: 6px;
        overflow: hidden;
        font-size: 0.82rem;
    }
    .outputs-table th {
        background: var(--gray-100);
        padding: 6px 12px;
        text-align: left;
        font-weight: 600;
        color: var(--gray-700);
    }
    .outputs-table td { padding: 8px 12px; border-top: 1px solid var(--gray-200); vertical-align: top; }
    .outputs-table td:first-child { font-family: monospace; font-weight: 600; color: #3b82f6; white-space: nowrap; }
    .outputs-table pre { background: none; color: var(--gray-700); font-size: 0.8rem; white-space: pre-wrap; word-break: break-all; }
    .no-outputs { font-size: 0.82rem; color: var(--gray-500); font-style: italic; padding: 8px 0; }
"""


# ---------------------------------------------------------------------------
# Section renderers
# ---------------------------------------------------------------------------

def render_header(
    summary: dict,
    dataset_name: str,
    generated_at: str,
    pass_rate_pct: str,
    pass_class: str,
) -> str:
    return f"""
<div class="page-header">
  <div>
    <h1>Eval Report</h1>
    <div class="header-meta">
      Dataset: <strong>{_e(dataset_name)}</strong>
      &nbsp;·&nbsp; Generated: {_e(generated_at)}
    </div>
  </div>
  <div class="pass-rate-badge {pass_class}">{pass_rate_pct}% Pass Rate</div>
</div>"""


def render_summary_cards(summary: dict) -> str:
    total = summary.get("total_questions", 0)
    passed = summary.get("successful_executions", 0)
    failed = summary.get("execution_failures", 0)
    exhausted = summary.get("critic_loop_exhausted", 0)
    rate = summary.get("pass_rate", 0)
    rate_pct = f"{rate * 100:.1f}%"

    def card(label: str, value: str, cls: str = "") -> str:
        return f"""<div class="card">
  <div class="card-label">{label}</div>
  <div class="card-value {cls}">{value}</div>
</div>"""

    cards = "".join([
        card("Total Questions", str(total), "blue"),
        card("Pass Rate", rate_pct, "green" if rate >= 0.5 else "red"),
        card("Passed", str(passed), "green"),
        card("Failed", str(failed), "red" if failed else ""),
        card("Critic Exhausted", str(exhausted), "red" if exhausted else ""),
    ])
    return f"""
<div class="section">
  <div class="section-title">Summary</div>
  <div class="cards-row">{cards}</div>
</div>"""


def render_difficulty_table(breakdown: dict) -> str:
    rows = ""
    for level in ("easy", "medium", "hard"):
        data = breakdown.get(level, {})
        total = data.get("total", 0)
        passed = data.get("passed", 0)
        failed = data.get("failed", 0) + data.get("total", 0) - data.get("passed", 0) - data.get("failed", data.get("total", 0) - data.get("passed", 0))
        failed = total - passed
        rate = f"{passed / total * 100:.0f}%" if total else "—"
        badge = f'<span class="badge badge-{level}">{level}</span>'
        rows += f"""<tr>
  <td>{badge}</td>
  <td>{total}</td>
  <td style="color:var(--green-fg);font-weight:600">{passed}</td>
  <td style="color:var(--red-fg);font-weight:600">{failed}</td>
  <td>{rate}</td>
</tr>"""
    return f"""
<div class="section">
  <div class="section-title">Difficulty Breakdown</div>
  <table class="breakdown-table">
    <thead><tr><th>Difficulty</th><th>Total</th><th>Passed</th><th>Failed</th><th>Pass Rate</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</div>"""


def render_conversation_timeline(log: list) -> str:
    if not log:
        return ""
    badges = []
    for i, entry in enumerate(log):
        role = entry.get("role", "")
        content = entry.get("content", "")
        css = classify_log_entry(role, content)
        label = _timeline_label(role, content)
        tip = _e(content)
        if i > 0:
            badges.append('<span class="tl-arrow">→</span>')
        badges.append(f'<span class="tl-badge {css}" title="{tip}">{_e(label)}</span>')
    strip = "\n  ".join(badges)
    return f"""<div class="timeline">
  <div class="timeline-label">Execution Timeline</div>
  <div class="timeline-strip">
  {strip}
  </div>
</div>"""


def render_dag_node(node: dict) -> str:
    node_id = node.get("node_id", "?")
    operation = node.get("operation", "")
    function_name = node.get("function_name", "")
    inputs = node.get("inputs", {})
    expected_output_type = node.get("expected_output_type", "")
    layer = node.get("layer", 0)
    code = node.get("code", "")

    # Inputs list
    input_items = ""
    for param, source in inputs.items():
        input_items += f"<li><code>{_e(param)}</code> ← <code>{_e(source)}</code></li>"

    inputs_section = ""
    if input_items:
        inputs_section = f"""<div class="dag-node-inputs">
  <strong>Inputs:</strong>
  <ul>{input_items}</ul>
</div>"""

    highlighted_code = highlight_python(code)

    return f"""<div class="dag-node">
  <div class="dag-node-header">
    <span class="node-id">{_e(node_id)}</span>
    <span class="badge badge-layer">Layer {layer}</span>
    <span class="output-type">→ {_e(expected_output_type)}</span>
  </div>
  <div class="dag-node-operation">{_e(operation)}</div>
  {inputs_section}
  <pre class="code-block"><code>{highlighted_code}</code></pre>
</div>"""


def render_iteration(iter_data: dict, is_last_and_approved: bool = False) -> str:
    n = iter_data.get("iteration", "?")
    dag = iter_data.get("dag", {})
    feedback = iter_data.get("critic_feedback", {})
    is_approved = feedback.get("is_approved", False)

    verdict_badge_cls = "badge-iter-ok" if is_approved else "badge-iter-fail"
    verdict_label = "APPROVED ✓" if is_approved else "REJECTED ✗"
    iter_cls = "iter-ok" if is_approved else "iter-fail"
    open_attr = " open" if is_last_and_approved else ""

    # Critic block
    reasoning = feedback.get("overall_reasoning", "")
    specific_errors = feedback.get("specific_errors", [])
    suggestions = feedback.get("suggestions", [])

    errors_block = ""
    if specific_errors:
        items = "".join(f"<li>{_e(e)}</li>" for e in specific_errors)
        errors_block = f"""<details class="sub-block" open>
  <summary>Issues ({len(specific_errors)})</summary>
  <div class="sub-block-body"><ul class="error-list">{items}</ul></div>
</details>"""

    suggestions_block = ""
    if suggestions:
        items = "".join(f"<li>{_e(s)}</li>" for s in suggestions)
        suggestions_block = f"""<details class="sub-block">
  <summary>Suggestions ({len(suggestions)})</summary>
  <div class="sub-block-body"><ul class="suggest-list">{items}</ul></div>
</details>"""

    critic_block = f"""<div class="critic-block">
  <div class="critic-reasoning">{_e(reasoning)}</div>
  {errors_block}
  {suggestions_block}
</div>"""

    # DAG section
    nodes = dag.get("nodes", [])
    edges = dag.get("edges", [])
    description = dag.get("description", "")
    final_answer_node = dag.get("final_answer_node", "")

    if not nodes:
        # Broken iteration — structural validation caught an empty DAG
        dag_content = f'<div class="dag-failed">⚠ DAG generation produced no nodes. Description: {_e(description)}</div>'
    else:
        # SVG diagram — appears first so users see the structure before the code
        svg_html = render_dag_svg(nodes, edges)
        svg_wrap = (
            f'<div class="dag-svg-wrap">'
            f'<div class="dag-svg-title">DAG Structure</div>'
            f'{svg_html}'
            f'</div>'
        ) if svg_html else ""

        node_cards = "\n".join(render_dag_node(n) for n in nodes)

        # Edges row (text summary below the SVG)
        edges_html = ""
        if edges:
            edge_items = "".join(
                f'<span class="edge-item">{_e(e.get("source","?"))} → {_e(e.get("target","?"))}</span>'
                for e in edges
            )
            edges_html = f'<div class="edges-row">{edge_items}</div>'

        dag_content = f"""<div class="dag-description">{_e(description)}</div>
{svg_wrap}
{node_cards}
{edges_html}
<div class="final-node-label">Final Answer Node: <code>{_e(final_answer_node)}</code></div>"""

    dag_section = f'<div class="dag-section">{dag_content}</div>'

    return f"""<details class="iter-block {iter_cls}"{open_attr}>
  <summary>
    Iteration {_e(n)} &nbsp;
    <span class="badge {verdict_badge_cls}">{verdict_label}</span>
  </summary>
  <div class="iter-body">
    {critic_block}
    {dag_section}
  </div>
</details>"""


def render_node_outputs_table(node_outputs: dict) -> str:
    if not node_outputs:
        return '<div class="no-outputs">No node outputs recorded (node failed before producing output).</div>'
    rows = ""
    for node_id, val in node_outputs.items():
        formatted = _e(format_node_output(val))
        rows += f"""<tr>
  <td>{_e(node_id)}</td>
  <td><pre>{formatted}</pre></td>
</tr>"""
    return f"""<div class="outputs-section">
  <strong>Node Outputs</strong>
  <table class="outputs-table">
    <thead><tr><th>Node</th><th>Output</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</div>"""


def render_question_accordion(trace: dict) -> str:
    qid = trace.get("question_id", "?")
    qtext = trace.get("question_text", "")
    difficulty = trace.get("difficulty", "easy")
    rank = trace.get("difficulty_rank", 0)
    total_iters = trace.get("total_iterations", 0)
    success = trace.get("success", False)
    final_answer = trace.get("final_answer")
    exec_error = trace.get("execution_error")
    exec_time = trace.get("execution_time_ms", 0.0)
    node_outputs = trace.get("node_outputs", {})
    iterations = trace.get("iterations", [])
    conv_log = trace.get("conversation_log", [])

    q_cls = "q-ok" if success else "q-fail"
    result_badge_cls = "badge-ok" if success else "badge-fail"
    result_label = "✓ PASSED" if success else "✗ FAILED"
    diff_badge = f'<span class="badge badge-{difficulty}">{difficulty}</span>'
    result_badge = f'<span class="badge {result_badge_cls}">{result_label}</span>'
    iter_label = f'<span class="q-iters">{total_iters} iteration{"s" if total_iters != 1 else ""}</span>'

    # Answer / error box
    if success:
        answer_str = _e(format_answer(final_answer))
        time_str = f"{exec_time:.1f}ms" if exec_time else ""
        time_part = f" &nbsp; <span style='color:var(--gray-500);font-size:0.8rem'>({time_str})</span>" if time_str else ""
        answer_box = f'<div class="answer-box ok"><strong>Answer:</strong> {answer_str}{time_part}</div>'
    else:
        err = _e(exec_error or "Unknown error")
        answer_box = f'<div class="answer-box fail"><strong>Error:</strong> {err}</div>'

    # Timeline
    timeline = render_conversation_timeline(conv_log)

    # Iteration blocks
    iter_blocks = []
    for i, it in enumerate(iterations):
        is_last = (i == len(iterations) - 1)
        is_approved = it.get("critic_feedback", {}).get("is_approved", False)
        is_last_and_approved = is_last and is_approved
        iter_blocks.append(render_iteration(it, is_last_and_approved))
    iters_html = "\n".join(iter_blocks)

    # Node outputs
    outputs_table = render_node_outputs_table(node_outputs)

    # Short display ID: use rank number
    display_id = f"Q{rank}"

    return f"""<details class="q-accordion {q_cls}">
  <summary>
    <span class="q-id">{_e(display_id)}</span>
    <span class="q-text">{_e(qtext)}</span>
    {diff_badge}
    {result_badge}
    {iter_label}
  </summary>
  <div class="q-body">
    {answer_box}
    {timeline}
    {iters_html}
    {outputs_table}
  </div>
</details>"""


def render_questions_section(question_traces: list) -> str:
    if not question_traces:
        return '<div class="section"><div class="section-title">Questions</div><p style="color:var(--gray-500);font-size:0.85rem">No question traces found in the report.</p></div>'
    n = len(question_traces)
    accordions = "\n".join(render_question_accordion(t) for t in question_traces)
    return f"""
<div class="section">
  <div class="section-title">Questions ({n})</div>
  {accordions}
</div>"""


# ---------------------------------------------------------------------------
# Top-level assembler
# ---------------------------------------------------------------------------

def generate_html(report_data: dict, dataset_name: str, generated_at: str) -> str:
    """Generate the full HTML report string from report_data."""
    summary = report_data.get("summary", {})
    difficulty_breakdown = report_data.get("difficulty_breakdown", {})
    question_traces = report_data.get("question_traces", [])

    pass_rate = summary.get("pass_rate", 0.0)
    pass_rate_pct = f"{pass_rate * 100:.1f}"
    pass_class = "ok" if pass_rate >= 0.5 else "bad"

    parts = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '  <meta charset="UTF-8">',
        '  <meta name="viewport" content="width=device-width, initial-scale=1.0">',
        f"  <title>Eval Report \u2014 {_e(dataset_name)}</title>",
        f"  <style>{render_css()}</style>",
        "</head>",
        "<body>",
        '<div class="page-wrap">',
        render_header(summary, dataset_name, generated_at, pass_rate_pct, pass_class),
        render_summary_cards(summary),
        render_difficulty_table(difficulty_breakdown),
        render_questions_section(question_traces),
        "</div>",
        "</body>",
        "</html>",
    ]
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a human-readable HTML report from eval_results.json",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--input",
        default="eval_results.json",
        help="Path to eval_results.json",
    )
    parser.add_argument(
        "--output",
        default="eval_report.html",
        help="Path to write the HTML report",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    if not input_path.exists():
        print(f"ERROR: Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    with input_path.open(encoding="utf-8") as f:
        report_data = json.load(f)

    dataset_name = input_path.stem  # e.g. "eval_results"
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    html_content = generate_html(report_data, dataset_name, generated_at)
    output_path.write_text(html_content, encoding="utf-8")

    print(f"Report written to: {output_path}")
    print(f"Open in browser:  file:///{output_path.resolve()}")


if __name__ == "__main__":
    main()

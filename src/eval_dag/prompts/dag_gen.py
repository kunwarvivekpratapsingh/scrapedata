"""Prompt templates for DAG generation."""

from __future__ import annotations

import json
from typing import Any

from eval_dag.state.models import CriticFeedback, GeneratedDAG, Question


DAG_GEN_SYSTEM = """You are an expert computational planner. Given a question about a dataset, you design a Directed Acyclic Graph (DAG) of executable Python steps to answer it.

## DAG Rules:
1. Each node is a Python function that takes inputs and returns a single output
2. Nodes are organized in layers: layer 0 = no dependencies, layer N depends only on layers < N
3. Inputs reference either the dataset ("dataset.<field>") or a previous node's output ("prev_node.<node_id>.output")
4. The final_answer_node must be in the last layer and produce the answer
5. Code must be self-contained — only use: math, statistics, collections, itertools, functools, json, re, datetime, decimal, fractions, random
6. NO imports in node code — safe modules are pre-loaded in the execution environment
7. Each function must be named exactly as specified in function_name

## Response Format (JSON):
{
  "question_id": "q_01",
  "description": "Overall approach explanation",
  "nodes": [
    {
      "node_id": "step_1a",
      "operation": "What this step does",
      "function_name": "my_func",
      "inputs": {"data": "dataset.field_name"},
      "expected_output_type": "dict[str, float]",
      "layer": 0,
      "code": "def my_func(data):\\n    return {item['name']: item['value'] for item in data}"
    }
  ],
  "edges": [
    {"source": "step_1a", "target": "step_2a"}
  ],
  "final_answer_node": "step_2a"
}"""


def build_dag_gen_prompt(
    question: Question,
    dataset: dict[str, Any],
    metadata: dict[str, Any],
    feedback: CriticFeedback | None = None,
    previous_dag: GeneratedDAG | None = None,
) -> str:
    """Build the user prompt for DAG generation.

    On first iteration (feedback=None), generates from scratch.
    On subsequent iterations, includes critic feedback and previous DAG.
    """
    # Dataset schema summary
    schema_summary = _build_schema_summary(dataset, metadata)

    parts = [
        f"## Question\n{question.text}\n",
        f"## Question ID\n{question.id}\n",
        f"## Difficulty\nRank {question.difficulty_rank} ({question.difficulty_level.value})\n",
        f"## Relevant Data Keys\n{', '.join(question.relevant_data_keys)}\n",
        f"## Dataset Schema\n{schema_summary}\n",
    ]

    if feedback is not None and previous_dag is not None:
        parts.append(_build_feedback_section(feedback, previous_dag))

    parts.append(
        "Generate a complete DAG to answer this question. Respond with JSON only."
    )

    return "\n".join(parts)


def _build_feedback_section(
    feedback: CriticFeedback,
    previous_dag: GeneratedDAG,
) -> str:
    """Build the feedback section for regeneration prompts."""
    lines = [
        "## ⚠️ PREVIOUS ATTEMPT REJECTED — YOU MUST FIX THESE ISSUES",
        "",
        f"### Overall Assessment",
        feedback.overall_reasoning,
        "",
    ]

    # Layer-by-layer issues
    for lv in feedback.layer_validations:
        if not lv.is_valid:
            lines.append(f"### Layer {lv.layer_index} Issues (nodes: {', '.join(lv.nodes_in_layer)})")
            for issue in lv.issues:
                lines.append(f"  - {issue}")
            lines.append("")

    # Specific errors
    if feedback.specific_errors:
        lines.append("### Specific Errors")
        for err in feedback.specific_errors:
            lines.append(f"  - {err}")
        lines.append("")

    # Suggestions
    if feedback.suggestions:
        lines.append("### Suggestions for Improvement")
        for sug in feedback.suggestions:
            lines.append(f"  - {sug}")
        lines.append("")

    # Previous DAG for reference
    lines.append("### Previous DAG (for reference — generate a COMPLETE new one)")
    lines.append(f"```json\n{previous_dag.model_dump_json(indent=2)}\n```")
    lines.append("")

    return "\n".join(lines)


def _build_schema_summary(
    dataset: dict[str, Any],
    metadata: dict[str, Any],
) -> str:
    """Build a rich schema summary of the dataset showing inner field names.

    The LLM must see the EXACT field names inside each nested structure.
    Without this, it hallucinates field names like 'transaction_count'
    instead of 'count', causing KeyErrors at runtime.
    """
    lines = []

    if "description" in metadata:
        lines.append(f"Description: {metadata['description']}")
    if "domain" in metadata:
        lines.append(f"Domain: {metadata['domain']}")

    # Bake in explicit field name warnings from metadata important_notes
    important_notes = metadata.get("important_notes", [])
    if important_notes:
        lines.append("\nIMPORTANT NOTES:")
        for note in important_notes:
            lines.append(f"  ⚠ {note}")

    lines.append("\nDataset keys and EXACT field structure:")
    for key, value in dataset.items():
        type_info = _describe_type(value)
        lines.append(f"  - {key}: {type_info}")

    # Append an explicit field-name reference to prevent hallucination
    lines.append("""
## CRITICAL: Exact Field Names — Do NOT guess or invent field names

  state_stats[state_code]     → {count, total_amt, fraud_count}
  category_stats[category]    → {count, total_amt, fraud_count, fraud_rate, avg_amt}
  time_series[YYYY-MM]        → {count, total_amt, fraud_count}
    ⚠ time_series is FLAT monthly totals. It has NO per-category breakdown.
    ⚠ To analyse by category AND time, use the raw `transactions` list.
  gender_breakdown[M/F]       → {count, fraud_count, total_amt}
  top_merchants (list item)   → {merchant, count, total_amt, fraud_count, fraud_rate}
  date_range                  → {start, end}  (YYYY-MM-DD strings)
  amount_distribution         → {min, max, mean, median, std, p25, p75, p95, p99}""")

    # Append per-column field guide for the transactions list (from enriched metadata)
    field_guide = _build_transaction_field_guide(metadata)
    if field_guide:
        lines.append(field_guide)

    return "\n".join(lines)


def _build_transaction_field_guide(metadata: dict[str, Any]) -> str:
    """Build a per-column field guide for the transactions list from enriched metadata.

    Uses the structured `columns` dict in metadata (where each column is a dict
    with keys like type, format, nullable, sensitivity, values, note) to produce
    a concise reference that prevents common bugs like:
    - Wrong date format strings (DD-MM-YYYY vs MM/DD/YYYY)
    - Accessing merch_zipcode without None check
    - Computing on cc_num (scientific notation string)
    - Using merchant name as a fraud signal

    Falls back gracefully if metadata.columns is old flat-string format.
    """
    columns = metadata.get("columns", {})
    if not columns:
        return ""

    # Check if columns are the new structured format (dict values) or old flat strings
    first_val = next(iter(columns.values()), None)
    if not isinstance(first_val, dict):
        # Old flat-string format — no enrichment possible
        return ""

    lines = ["\n## Transaction Row Fields (use when iterating dataset.transactions)"]
    lines.append("Each row in transactions[] is a dict with these fields:\n")

    for field_name, col in columns.items():
        col_type = col.get("type", "")
        description = col.get("description", "")
        fmt = col.get("format", "")
        strptime_fmt = col.get("strptime", "")
        nullable = col.get("nullable", False)
        sensitivity = col.get("sensitivity", "")
        values = col.get("values", [])
        cardinality = col.get("cardinality", "")
        note = col.get("note", "")
        col_range = col.get("range", "")

        # Build a compact single-line entry per field
        parts = [f"  {field_name:<24} {col_type:<18} {description}"]

        extras = []
        if fmt:
            extras.append(f"format: {fmt}")
        if strptime_fmt:
            extras.append(f"parse: strptime('{strptime_fmt}')")
        if col_range:
            extras.append(f"range: {col_range}")
        if values and len(values) <= 10:
            extras.append(f"values: {values}")
        elif cardinality:
            extras.append(f"cardinality: {cardinality}")
        if nullable:
            extras.append("⚠ NULLABLE — check for None before accessing")
        if sensitivity == "pii":
            extras.append("[PII]")

        if extras:
            parts.append(f"    → {', '.join(extras)}")
        if note:
            parts.append(f"    ⚠ {note}")

        lines.append("\n".join(parts))

    return "\n".join(lines)


def _describe_type(value: Any, max_items: int = 3) -> str:
    """Describe the type and shape of a value, showing inner field names for nested dicts."""
    if isinstance(value, list):
        if len(value) == 0:
            return "list (empty)"
        if isinstance(value[0], dict):
            all_keys = list(value[0].keys())
            # Show a concrete example item (first 4 fields only to keep prompt short)
            example = {k: value[0][k] for k in list(value[0].keys())[:4]}
            return (
                f"list of {len(value)} dicts with keys: {all_keys}\n"
                f"    Example item: {json.dumps(example, default=str)}"
            )
        return f"list of {len(value)} {type(value[0]).__name__}s"
    elif isinstance(value, dict):
        if not value:
            return "dict (empty)"
        first_val = next(iter(value.values()))
        if isinstance(first_val, dict):
            # dict-of-dicts: show inner field names + a real example
            inner_keys = list(first_val.keys())
            first_key = next(iter(value))
            example = {k: first_val[k] for k in list(first_val.keys())[:5]}
            return (
                f"dict[key → {{{', '.join(inner_keys)}}}]  ({len(value)} entries)\n"
                f"    Example: [{repr(first_key)}] = {json.dumps(example, default=str)}"
            )
        # Flat dict: just show sample of keys
        sample_keys = list(value.keys())[:6]
        return f"dict with {len(value)} keys, e.g.: {sample_keys}"
    else:
        return f"{type(value).__name__} = {str(value)[:60]}"

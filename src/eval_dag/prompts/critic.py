"""Prompt templates for the critic/validation agent."""

from __future__ import annotations

import json
from typing import Any

from eval_dag.state.models import DAGNodeSpec, GeneratedDAG, Question
from eval_dag.prompts.dag_gen import _build_schema_summary


CRITIC_SYSTEM = """You are an expert code reviewer and computational verifier. You validate DAG execution plans layer by layer.

For each layer, you check:
1. **Logical correctness**: Does each step logically follow from its inputs?
2. **Code correctness**: Is the Python code correct for its stated operation? Will it produce the expected output?
3. **Type compatibility**: Are input/output types compatible with upstream/downstream nodes?
4. **Relevance**: Does each step meaningfully contribute to answering the question?
5. **Edge cases**: Are there potential runtime errors (division by zero, missing keys, empty lists)?
6. **Field name correctness**: Does the code use ONLY the exact field names documented in the Dataset Schema?
   Any field access using an undocumented name (e.g. stats['transaction_count'] when only 'count' exists)
   MUST be flagged as a specific error. This is a critical check — field name guessing causes KeyErrors.

You MUST respond with valid JSON matching this exact schema:
{
  "layer_index": 0,
  "is_valid": true,
  "issues": [],
  "node_assessments": {
    "step_1a": {
      "is_correct": true,
      "issues": []
    }
  }
}

If a node has issues, set is_correct to false and list specific, actionable issues.
Be thorough but fair — only flag genuine problems, not stylistic preferences."""


def build_critic_prompt_for_layer(
    question: Question,
    dag: GeneratedDAG,
    layer_index: int,
    layer_nodes: list[DAGNodeSpec],
    validated_layers_summary: str,
    metadata: dict[str, Any],
    dataset: dict[str, Any] | None = None,
) -> str:
    """Build the user prompt for validating a single layer.

    Args:
        question: The question being answered.
        dag: The complete DAG.
        layer_index: Which layer to validate.
        layer_nodes: Nodes in this layer.
        validated_layers_summary: Summary of already-validated layers.
        metadata: Dataset metadata.
        dataset: Full dataset (used to build the rich schema summary with real field names).
    """
    # Build a rich schema that shows inner field names so the critic can
    # validate field access in code (catches 'transaction_count' vs 'count' etc.)
    if dataset is not None:
        schema_context = _build_schema_summary(dataset, metadata)
    else:
        # Fallback: use raw metadata (less informative but still functional)
        schema_context = json.dumps(metadata, indent=2, default=str)[:2000]

    # Format nodes in this layer
    nodes_detail = []
    for node in layer_nodes:
        nodes_detail.append(
            f"  - **{node.node_id}** ({node.function_name})\n"
            f"    Operation: {node.operation}\n"
            f"    Inputs: {json.dumps(node.inputs)}\n"
            f"    Expected output type: {node.expected_output_type}\n"
            f"    Code:\n    ```python\n{_indent(node.code, 4)}\n    ```"
        )

    nodes_text = "\n\n".join(nodes_detail)

    return f"""## Question
{question.text}

## Dataset Schema (EXACT field names — validate all dict key accesses against this)
{schema_context}

## DAG Overview
{dag.description}
Final answer node: {dag.final_answer_node}
Total nodes: {len(dag.nodes)}, Total layers: {max(n.layer for n in dag.nodes) + 1}

## Previously Validated Layers
{validated_layers_summary if validated_layers_summary else "(This is the first layer)"}

## Layer {layer_index} — VALIDATE THIS
{nodes_text}

Validate this layer. Respond with JSON only."""


def build_validated_layers_summary(
    dag: GeneratedDAG,
    up_to_layer: int,
) -> str:
    """Build a summary of layers validated so far for context."""
    if up_to_layer == 0:
        return ""

    lines = []
    for node in dag.nodes:
        if node.layer < up_to_layer:
            lines.append(
                f"  Layer {node.layer} | {node.node_id}: "
                f"{node.operation} -> {node.expected_output_type}"
            )

    return "\n".join(sorted(lines))


def _indent(text: str, spaces: int) -> str:
    """Indent each line of text."""
    prefix = " " * spaces
    return "\n".join(prefix + line for line in text.split("\n"))

"""Critic node — validates DAGs layer by layer.

Performs two-phase validation:
  Phase 1: Structural (deterministic, no LLM) — syntax, safety, deps, layers
  Phase 2: Semantic (LLM-based) — logic, correctness, type compatibility

All layers are validated even after errors to give the builder maximum
feedback in one cycle.

State reads: current_dag, question, dataset, metadata
State writes: current_feedback, is_approved, dag_history, messages
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from eval_dag.prompts.critic import (
    CRITIC_SYSTEM,
    build_critic_prompt_for_layer,
    build_validated_layers_summary,
)
from eval_dag.state.models import (
    CriticFeedback,
    GeneratedDAG,
    LayerValidation,
)
from eval_dag.state.schemas import CriticLoopState
from eval_dag.utils.dag_utils import (
    extract_layers,
    run_all_structural_validations,
)

logger = logging.getLogger(__name__)


def _get_llm():
    """Get the LLM instance for semantic validation."""
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model="gpt-4o",
        temperature=0.0,
        model_kwargs={"response_format": {"type": "json_object"}},
    )


def _structural_validation(dag: GeneratedDAG) -> tuple[list[str], bool]:
    """Run all structural validations.

    Returns (errors, has_critical_errors).
    Critical errors = empty DAG, cycles, missing final node.
    """
    # Handle empty/malformed DAGs
    if not dag.nodes:
        return ["DAG has no nodes"], True

    if not dag.final_answer_node:
        return ["DAG has no final_answer_node specified"], True

    errors = run_all_structural_validations(dag)
    has_critical = any(
        "cycle" in e.lower() or "does not exist" in e.lower()
        for e in errors
    )
    return errors, has_critical


_RATE_LIMIT_PHRASES = ("rate_limit_exceeded", "rate limit", "tokens per min", "429")

# Maximum retry attempts for rate-limit errors and JSON parse failures
_MAX_SEMANTIC_RETRIES = 3


def _is_rate_limit_error(exc: Exception) -> bool:
    """Return True if the exception is an OpenAI rate-limit (429) error."""
    msg = str(exc).lower()
    return any(phrase.lower() in msg for phrase in _RATE_LIMIT_PHRASES)


def _is_json_parse_error(exc: Exception) -> bool:
    """Return True if the exception is a JSON decode / parse error."""
    return isinstance(exc, (ValueError, KeyError)) or "json" in type(exc).__name__.lower()


def _semantic_validation_for_layer(
    question: Any,
    dag: GeneratedDAG,
    layer_index: int,
    layer_nodes: list,
    validated_summary: str,
    metadata: dict[str, Any],
    dataset: dict[str, Any] | None = None,
) -> LayerValidation:
    """Run LLM-based semantic validation for a single layer.

    Retry policy (up to _MAX_SEMANTIC_RETRIES attempts total):
      - Rate-limit (429): exponential back-off 5s / 10s / 20s, then REJECT.
        Rationale: silently approving on rate-limit hides real bugs; better to
        reject and let the next iteration retry from a clean state.
      - JSON parse failure: immediate retry (LLM output was malformed); if it
        still fails after retries, REJECT with a clear parse-error message.
      - Any other exception: REJECT immediately with the error text.

    Rejecting on infrastructure failure is safer than approving — a subsequent
    run (or the next DAG iteration) will re-validate cleanly.
    """
    llm = _get_llm()

    prompt = build_critic_prompt_for_layer(
        question=question,
        dag=dag,
        layer_index=layer_index,
        layer_nodes=layer_nodes,
        validated_layers_summary=validated_summary,
        metadata=metadata,
        dataset=dataset,
    )

    messages = [
        SystemMessage(content=CRITIC_SYSTEM),
        HumanMessage(content=prompt),
    ]

    node_ids = [n.node_id for n in layer_nodes]
    last_exc: Exception | None = None

    for attempt in range(_MAX_SEMANTIC_RETRIES):
        try:
            response = llm.invoke(messages)
            result = _parse_critic_response(response.content)
            # Success — exit retry loop
            break
        except Exception as e:
            last_exc = e
            is_rate_limit = _is_rate_limit_error(e)
            is_parse_err  = _is_json_parse_error(e)
            retryable     = is_rate_limit or is_parse_err

            if retryable and attempt < _MAX_SEMANTIC_RETRIES - 1:
                wait = 5 * (2 ** attempt)  # 5s, 10s, 20s
                reason = "rate limit" if is_rate_limit else "JSON parse error"
                logger.warning(
                    f"Semantic validation {reason} for layer {layer_index} "
                    f"(attempt {attempt + 1}/{_MAX_SEMANTIC_RETRIES}). "
                    f"Retrying in {wait}s..."
                )
                time.sleep(wait)
                continue
            else:
                # Either non-retryable error, or all retries exhausted.
                # REJECT — never silently approve on infrastructure failure.
                if is_rate_limit:
                    msg = (
                        f"Semantic validation could not complete for layer {layer_index}: "
                        f"rate limit exhausted after {_MAX_SEMANTIC_RETRIES} attempts. "
                        f"Treat this layer as unvalidated and regenerate the DAG."
                    )
                elif is_parse_err:
                    msg = (
                        f"Semantic validation produced malformed JSON for layer {layer_index} "
                        f"after {attempt + 1} attempt(s): {e}. Regenerate the DAG."
                    )
                else:
                    msg = f"Semantic validation error for layer {layer_index}: {e}"

                logger.error(msg)
                return LayerValidation(
                    layer_index=layer_index,
                    nodes_in_layer=node_ids,
                    is_valid=False,
                    issues=[msg],
                )
    else:
        # for-loop exhausted without break — all retries used up
        msg = (
            f"Semantic validation failed for layer {layer_index} after "
            f"{_MAX_SEMANTIC_RETRIES} attempts: {last_exc}"
        )
        logger.error(msg)
        return LayerValidation(
            layer_index=layer_index,
            nodes_in_layer=node_ids,
            is_valid=False,
            issues=[msg],
        )

    node_ids = [n.node_id for n in layer_nodes]
    issues: list[str] = []

    # Collect issues from node assessments
    node_assessments = result.get("node_assessments", {})
    for node_id, assessment in node_assessments.items():
        if not assessment.get("is_correct", True):
            for issue in assessment.get("issues", []):
                issues.append(f"{node_id}: {issue}")

    # Also include any top-level issues
    issues.extend(result.get("issues", []))

    is_valid = result.get("is_valid", len(issues) == 0)

    return LayerValidation(
        layer_index=layer_index,
        nodes_in_layer=node_ids,
        is_valid=is_valid,
        issues=issues,
    )


def _parse_critic_response(content: str) -> dict:
    """Parse critic LLM response, handling markdown fences."""
    text = content.strip()
    if text.startswith("```"):
        first_newline = text.index("\n")
        text = text[first_newline + 1 :]
    if text.endswith("```"):
        text = text[:-3]
    return json.loads(text.strip())


def validate_dag_node(state: CriticLoopState) -> dict[str, Any]:
    """LangGraph node: Validate a DAG layer by layer.

    Combines structural checks (deterministic) with semantic validation
    (LLM-based). Reports ALL errors across ALL layers.

    Returns state updates for: current_feedback, is_approved, dag_history, messages
    """
    dag = state["current_dag"]
    question = state["question"]
    metadata = state.get("metadata", {})
    iteration = state.get("iteration_count", 1)
    emit = state.get("_progress_cb")   # thread-safe SSE callback or None

    logger.info(
        f"Validating DAG for question '{question.id}' (iteration {iteration})"
    )

    # Phase 1: Structural validation
    structural_errors, has_critical = _structural_validation(dag)

    if has_critical:
        # DAG is too broken for semantic validation
        feedback = CriticFeedback(
            is_approved=False,
            overall_reasoning=(
                f"DAG has critical structural errors and cannot be validated further. "
                f"Errors: {'; '.join(structural_errors)}"
            ),
            layer_validations=[],
            specific_errors=structural_errors,
            suggestions=[
                "Ensure the DAG has at least one node",
                "Ensure final_answer_node references an existing node",
                "Ensure there are no cycles in the DAG",
            ],
        )

        return _build_return(feedback, dag, iteration, emit=emit)

    # Phase 2: Semantic validation (layer by layer)
    dataset = state.get("dataset", {})
    layers = extract_layers(dag)
    layer_validations: list[LayerValidation] = []
    all_issues: list[str] = []

    # Add structural errors as issues for context
    all_issues.extend(structural_errors)

    for layer_idx, layer_nodes in enumerate(layers):
        if not layer_nodes:
            continue

        validated_summary = build_validated_layers_summary(dag, layer_idx)

        layer_result = _semantic_validation_for_layer(
            question=question,
            dag=dag,
            layer_index=layer_idx,
            layer_nodes=layer_nodes,
            validated_summary=validated_summary,
            metadata=metadata,
            dataset=dataset,
        )
        layer_validations.append(layer_result)

        if not layer_result.is_valid:
            all_issues.extend(layer_result.issues)

    # Build overall feedback
    is_approved = len(all_issues) == 0
    overall_reasoning = (
        "DAG is valid and approved for execution."
        if is_approved
        else f"DAG has {len(all_issues)} issue(s) that need to be fixed."
    )

    # Build suggestions from issues
    suggestions: list[str] = []
    if structural_errors:
        suggestions.append("Fix structural issues first (dependency ordering, edge references)")
    if any(not lv.is_valid for lv in layer_validations):
        suggestions.append("Review and fix the code logic in flagged nodes")
        suggestions.append("Ensure type compatibility between connected nodes")

    feedback = CriticFeedback(
        is_approved=is_approved,
        overall_reasoning=overall_reasoning,
        layer_validations=layer_validations,
        specific_errors=all_issues,
        suggestions=suggestions,
    )

    return _build_return(feedback, dag, iteration, emit=emit)


def _build_return(
    feedback: CriticFeedback,
    dag: GeneratedDAG,
    iteration: int,
    emit: Any = None,
) -> dict[str, Any]:
    """Build the state update dict for the critic node."""
    status = "APPROVED" if feedback.is_approved else "REJECTED"

    ai_message = AIMessage(
        content=(
            f"[Critic] Iteration {iteration} for {dag.question_id}: "
            f"{status} — {len(feedback.specific_errors)} issue(s)"
        ),
        name="critic",
    )

    # ── Emit SSE progress event ────────────────────────────────────────────
    if emit:
        emit("critic_result", {
            "question_id": dag.question_id,
            "iteration": iteration,
            "is_approved": feedback.is_approved,
            "issues_count": len(feedback.specific_errors),
            "overall_reasoning": feedback.overall_reasoning,
        })

    return {
        "current_feedback": feedback,
        "is_approved": feedback.is_approved,
        "dag_history": [
            {
                "iteration": iteration,
                "dag": dag.model_dump(),
                "feedback": feedback.model_dump(),
            }
        ],
        "messages": [ai_message],
    }

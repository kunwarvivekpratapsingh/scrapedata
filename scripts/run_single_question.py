"""Run a single hard question through the eval-dag critic loop.

Tests the full pipeline: DAG builder -> critic -> sandbox executor
with a deliberately complex 5-step question about fraud rate volatility.

The question requires exactly 5 sequential DAG layers:
  Layer 0: Parse dates and group transactions by (category, month)
  Layer 1: Compute monthly fraud rate per (category, month) bucket
  Layer 2: Pivot to per-category list of monthly fraud rates
  Layer 3: Compute stdev of monthly rates per category (volatility)
  Layer 4: Find category with max volatility, return (name, score)

Ground truth: ("grocery_net", 0.260714)

Usage:
    py scripts/run_single_question.py [--verbose]
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

# Allow running from repo root without install
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from eval_dag.graphs.critic_loop import critic_loop
from eval_dag.state.models import DifficultyLevel, Question


# ── The hard question ─────────────────────────────────────────────────────────

QUESTION = Question(
    id="q_hard_01",
    text=(
        "Which merchant category has the highest month-to-month fraud rate volatility "
        "(measured as the standard deviation of its monthly fraud rate across all months "
        "in the transactions sample), and what is that volatility score rounded to 6 "
        "decimal places? Return a list of [category_name, volatility_score]."
    ),
    difficulty_rank=10,
    difficulty_level=DifficultyLevel.HARD,
    reasoning=(
        "Requires 5 sequential steps: (1) parse DD-MM-YYYY dates and group transactions "
        "by (category, month) counting totals and fraud counts, (2) compute monthly fraud "
        "rate per bucket, (3) pivot to per-category list of monthly rates, (4) compute "
        "statistics.stdev per category (filter out categories with <2 data points), "
        "(5) argmax over stddev values to find the most volatile category. "
        "Tests date format awareness, nested aggregation, stdev edge case handling, "
        "and correct use of pre-loaded statistics module."
    ),
    relevant_data_keys=["transactions"],
)

# Verified ground truth computed from the full 5000-row transactions sample
GROUND_TRUTH_CATEGORY = "grocery_net"
GROUND_TRUTH_SCORE = 0.260714
MATCH_TOLERANCE = 0.0001


# ── Helpers ───────────────────────────────────────────────────────────────────

def _serialize(obj: Any) -> Any:
    """JSON-serializable fallback for complex objects."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "__dict__"):
        return obj.__dict__
    return str(obj)


def _print_dag_summary(dag: Any, label: str) -> None:
    """Print a compact summary of a GeneratedDAG (accepts dict or Pydantic object)."""
    if dag is None:
        print(f"  {label}: <none>")
        return
    # dag_history stores model_dump() dicts; handle both dicts and Pydantic objects
    if isinstance(dag, dict):
        nodes = dag.get("nodes", [])
        layers = [n.get("layer", 0) for n in nodes]
        max_layer = max(layers, default=0)
        print(f"  {label}: {len(nodes)} nodes across {1 + max_layer} layers")
        for node in sorted(nodes, key=lambda n: (n.get("layer", 0), n.get("node_id", ""))):
            print(f"    [L{node.get('layer', 0)}] {node.get('node_id', '?')}: {node.get('operation', '?')}")
    else:
        nodes = dag.nodes
        max_layer = max((n.layer for n in nodes), default=0)
        print(f"  {label}: {len(nodes)} nodes across {1 + max_layer} layers")
        for node in sorted(nodes, key=lambda n: (n.layer, n.node_id)):
            print(f"    [L{node.layer}] {node.node_id}: {node.operation}")


def _print_feedback_summary(feedback: Any) -> None:
    """Print a compact summary of CriticFeedback (accepts dict or Pydantic object)."""
    if feedback is None:
        return
    # dag_history stores model_dump() dicts; handle both dicts and Pydantic objects
    if isinstance(feedback, dict):
        is_approved = feedback.get("is_approved", False)
        verdict = "APPROVED" if is_approved else "REJECTED"
        print(f"  Critic: {verdict}")
        if not is_approved:
            for err in feedback.get("specific_errors", [])[:5]:
                print(f"    - {err}")
            suggestions = feedback.get("suggestions", [])
            if suggestions:
                print(f"    Suggestion: {suggestions[0]}")
    else:
        verdict = "APPROVED" if feedback.is_approved else "REJECTED"
        print(f"  Critic: {verdict}")
        if not feedback.is_approved:
            for err in feedback.specific_errors[:5]:
                print(f"    - {err}")
            if feedback.suggestions:
                print(f"    Suggestion: {feedback.suggestions[0]}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%H:%M:%S",
    )
    logger = logging.getLogger("run_single_question")

    if not os.environ.get("OPENAI_API_KEY"):
        logger.error("OPENAI_API_KEY environment variable is not set")
        sys.exit(1)

    # Load dataset and metadata
    data_path = Path("dataset/data.json")
    meta_path = Path("dataset/metadata.json")

    if not data_path.exists():
        logger.error(f"Dataset not found: {data_path}. Run scripts/prepare_dataset.py first.")
        sys.exit(1)

    logger.info(f"Loading dataset from {data_path}")
    dataset = json.loads(data_path.read_text(encoding="utf-8"))
    metadata: dict = {}
    if meta_path.exists():
        logger.info(f"Loading metadata from {meta_path}")
        metadata = json.loads(meta_path.read_text(encoding="utf-8"))

    # Print question banner
    print("\n" + "=" * 70)
    print("QUESTION (rank 10 / HARD):")
    print(f"  {QUESTION.text}")
    print(f"\nGROUND TRUTH: [{GROUND_TRUTH_CATEGORY!r}, {GROUND_TRUTH_SCORE}]")
    print(f"\nSTEPS REQUIRED:")
    print("  Layer 0: Group transactions by (category, month) — parse DD-MM-YYYY dates")
    print("  Layer 1: Compute monthly fraud rate per (category, month) bucket")
    print("  Layer 2: Pivot to per-category list of monthly fraud rates")
    print("  Layer 3: Compute statistics.stdev per category (skip <2 data points)")
    print("  Layer 4: Find category with max stdev → return [name, round(stdev,6)]")
    print("=" * 70 + "\n")

    # Build initial CriticLoopState
    initial_state = {
        "question": QUESTION,
        "dataset": dataset,
        "metadata": metadata,
        "current_dag": None,
        "current_feedback": None,
        "iteration_count": 0,
        "is_approved": False,
        "dag_history": [],
        "execution_result": None,
        "messages": [],
    }

    logger.info("Invoking critic loop subgraph...")
    final_state = critic_loop.invoke(initial_state)

    # Extract results
    result = final_state.get("execution_result")
    iterations = final_state.get("iteration_count", 0)
    is_approved = final_state.get("is_approved", False)
    dag_history = final_state.get("dag_history", [])

    # Print per-iteration trace
    print("\n── ITERATION TRACE ──────────────────────────────────────────────────")
    for entry in dag_history:
        i = entry.get("iteration", "?")
        dag = entry.get("dag")
        feedback = entry.get("feedback")
        print(f"\nIteration {i}:")
        _print_dag_summary(dag, "DAG")
        _print_feedback_summary(feedback)

    # Print final result
    print("\n── FINAL RESULT ─────────────────────────────────────────────────────")
    print(f"Iterations used : {iterations} / 3")
    print(f"Approved        : {is_approved}")

    correct = False
    if result and result.success:
        answer = result.final_answer
        print(f"Answer          : {answer}")
        print(f"Expected        : [{GROUND_TRUTH_CATEGORY!r}, {GROUND_TRUTH_SCORE}]")
        print(f"Execution time  : {result.execution_time_ms:.1f} ms")

        # Validate answer (accept list or tuple)
        if isinstance(answer, (list, tuple)) and len(answer) == 2:
            ans_cat, ans_score = answer[0], answer[1]
            try:
                correct = (
                    ans_cat == GROUND_TRUTH_CATEGORY
                    and abs(float(ans_score) - GROUND_TRUTH_SCORE) < MATCH_TOLERANCE
                )
            except (TypeError, ValueError):
                correct = False

        print(f"Correct         : {'YES ✓' if correct else 'NO ✗'}")

        # Show intermediate node outputs
        if result.node_outputs and verbose:
            print("\nNode outputs:")
            for node_id, output in result.node_outputs.items():
                out_str = str(output)
                if len(out_str) > 120:
                    out_str = out_str[:120] + "..."
                print(f"  {node_id}: {out_str}")
    else:
        err = result.error if result else "Critic loop exhausted — no execution"
        print(f"FAILED          : {err}")

    print("=" * 70 + "\n")

    # Save to JSON
    out = {
        "question": QUESTION.model_dump(),
        "ground_truth": [GROUND_TRUTH_CATEGORY, GROUND_TRUTH_SCORE],
        "iterations_used": iterations,
        "is_approved": is_approved,
        "correct": correct,
        "execution_result": result.model_dump() if result else None,
        "dag_history": dag_history,
        "messages": [m.content for m in final_state.get("messages", [])],
    }
    output_path = Path("single_question_result.json")
    output_path.write_text(
        json.dumps(out, indent=2, default=_serialize),
        encoding="utf-8",
    )
    logger.info(f"Full result written to {output_path}")


if __name__ == "__main__":
    main()

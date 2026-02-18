"""Run a single hard question through the eval-dag critic loop.

Tests the full pipeline: DAG builder -> critic -> sandbox executor
with a deliberately complex 7-step question about per-gender fraud analysis.

The question requires exactly 7 sequential DAG layers:
  Layer 0: Group transactions by (gender, category) -> count + fraud_count
  Layer 1: Compute per-(gender, category) fraud rate
  Layer 2: Compute total transaction count per gender
  Layer 3: Compute per-gender average transaction count across all categories
  Layer 4: Filter (gender, category) pairs where count > gender average
  Layer 5: For each gender, find category with max fraud rate from filtered set
  Layer 6: Format result as [[gender, category, round(fraud_rate, 6)], ...]
            sorted by fraud_rate descending

Ground truth: [['M', 'shopping_net', 0.536885], ['F', 'grocery_pos', 0.365517]]

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

# Load .env file from project root (if it exists) before anything else reads env vars.
# This means OPENAI_API_KEY in .env is picked up by LangChain/OpenAI automatically.
try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).parent.parent / ".env"
    load_dotenv(dotenv_path=_env_path, override=True)  # override=True: .env key always wins
except ImportError:
    pass  # python-dotenv not installed — fall back to os.environ only

from eval_dag.graphs.critic_loop import critic_loop
from eval_dag.state.models import DifficultyLevel, Question


# ── The hard question (7 DAG layers) ──────────────────────────────────────────

QUESTION = Question(
    id="q_hard_02",
    text=(
        "Using the transactions list, perform the following steps in order: "
        "STEP 1 - group transactions by (gender, category) and count total transactions "
        "and fraud transactions for each (gender, category) pair; "
        "STEP 2 - compute the fraud rate for each (gender, category) pair as "
        "fraud_count divided by total_count; "
        "STEP 3 - using the counts from STEP 1, compute the total transaction count "
        "per gender (sum of counts across all categories for that gender) and the "
        "number of distinct categories per gender, then compute the per-gender average "
        "transaction count as total_for_gender divided by num_categories_for_gender; "
        "STEP 4 - filter the (gender, category) pairs from STEP 1 keeping only those "
        "where the count is strictly greater than the gender average from STEP 3; "
        "STEP 5 - for each gender, find the category with the highest fraud rate "
        "among the filtered pairs from STEP 4; "
        "STEP 6 - build a list of [gender, category, round(fraud_rate, 6)] for each "
        "gender's top category and sort it by fraud_rate descending. "
        "Return the final sorted list."
    ),
    difficulty_rank=10,
    difficulty_level=DifficultyLevel.HARD,
    reasoning=(
        "Requires 6+ sequential steps that MUST be ordered correctly: "
        "(1) group transactions by (gender, category) - this MUST come first to produce raw counts, "
        "(2) compute per-(gender, category) fraud rate from the grouped counts, "
        "(3) compute per-gender average from the same grouped counts (total_count / num_distinct_categories), "
        "(4) filter pairs where count > gender average - depends on both step 1 counts and step 3 averages, "
        "(5) argmax fraud rate per gender from filtered set - depends on step 2 rates and step 4 filter, "
        "(6) format and sort result descending by fraud_rate. "
        "The critical trap: computing averages BEFORE grouping raw data will give wrong results. "
        "Tests nested grouping, sequential multi-step aggregation, per-group threshold filtering, "
        "argmax within a filtered group, and multi-key sorting."
    ),
    relevant_data_keys=["transactions"],
)

# Verified ground truth computed from the full 5000-row transactions sample
# M -> shopping_net (fraud_rate 0.536885), F -> grocery_pos (fraud_rate 0.365517)
GROUND_TRUTH = [["M", "shopping_net", 0.536885], ["F", "grocery_pos", 0.365517]]
MATCH_TOLERANCE = 0.0001


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_serializable(obj: Any) -> Any:
    """Recursively convert an object to a JSON-serializable form."""
    import types
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, (dict, types.MappingProxyType)):
        return {str(k): _make_serializable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set, frozenset)):
        return [_make_serializable(i) for i in obj]
    if hasattr(obj, "model_dump"):
        return _make_serializable(obj.model_dump())
    if hasattr(obj, "__dict__"):
        return _make_serializable(obj.__dict__)
    # Fallback: convert anything else to string
    return str(obj)


def _serialize(obj: Any) -> Any:
    """JSON default() fallback for types json can't handle natively."""
    return _make_serializable(obj)


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
    print("QUESTION (rank 10 / HARD - 7 DAG layers):")
    print(f"  {QUESTION.text}")
    print(f"\nGROUND TRUTH: {GROUND_TRUTH}")
    print(f"\nSTEPS REQUIRED:")
    print("  Layer 0: Group transactions by (gender, category) -> count + fraud_count")
    print("  Layer 1: Compute per-(gender, category) fraud rate = fraud_count / total_count")
    print("  Layer 2: Compute total transaction count per gender")
    print("  Layer 3: Compute per-gender avg count = total_for_gender / num_categories_for_gender")
    print("  Layer 4: Filter (gender, category) pairs where count > gender average")
    print("  Layer 5: For each gender, find category with max fraud rate from filtered set")
    print("  Layer 6: Format as [[gender, category, round(fraud_rate,6)], ...] sorted desc by fraud_rate")
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
    print("\n-- ITERATION TRACE --------------------------------------------------")
    for entry in dag_history:
        i = entry.get("iteration", "?")
        dag = entry.get("dag")
        feedback = entry.get("feedback")
        print(f"\nIteration {i}:")
        _print_dag_summary(dag, "DAG")
        _print_feedback_summary(feedback)

    # Print final result
    print("\n-- FINAL RESULT -----------------------------------------------------")
    print(f"Iterations used : {iterations} / 3")
    print(f"Approved        : {is_approved}")

    correct = False
    if result and result.success:
        answer = result.final_answer
        print(f"Answer          : {answer}")
        print(f"Expected        : {GROUND_TRUTH}")
        print(f"Execution time  : {result.execution_time_ms:.1f} ms")

        # Validate answer: list of [gender, category, fraud_rate] pairs sorted desc
        # Accept either list-of-lists or list-of-tuples, order must match ground truth
        try:
            if isinstance(answer, (list, tuple)) and len(answer) == len(GROUND_TRUTH):
                correct = True
                for ans_row, gt_row in zip(answer, GROUND_TRUTH):
                    ans_row = list(ans_row)
                    if len(ans_row) != 3:
                        correct = False
                        break
                    gender_ok = str(ans_row[0]) == str(gt_row[0])
                    cat_ok    = str(ans_row[1]) == str(gt_row[1])
                    score_ok  = abs(float(ans_row[2]) - float(gt_row[2])) < MATCH_TOLERANCE
                    if not (gender_ok and cat_ok and score_ok):
                        correct = False
                        break
        except (TypeError, ValueError, IndexError):
            correct = False

        print(f"Correct         : {'YES' if correct else 'NO'}")

        # Show intermediate node outputs
        if result.node_outputs and verbose:
            print("\nNode outputs:")
            for node_id, output in result.node_outputs.items():
                out_str = str(output)
                if len(out_str) > 120:
                    out_str = out_str[:120] + "..."
                print(f"  {node_id}: {out_str}")
    else:
        err = result.error if result else "Critic loop exhausted - no execution"
        print(f"FAILED          : {err}")

    print("=" * 70 + "\n")

    # Save to JSON — pre-process the whole structure to handle tuple keys
    # (node_outputs may contain dicts with tuple keys from defaultdict grouping)
    out = _make_serializable({
        "question": QUESTION.model_dump(),
        "ground_truth": GROUND_TRUTH,
        "iterations_used": iterations,
        "is_approved": is_approved,
        "correct": correct,
        "execution_result": result.model_dump() if result else None,
        "dag_history": dag_history,
        "messages": [m.content for m in final_state.get("messages", [])],
    })
    output_path = Path("single_question_result.json")
    output_path.write_text(
        json.dumps(out, indent=2),
        encoding="utf-8",
    )
    logger.info(f"Full result written to {output_path}")


if __name__ == "__main__":
    main()

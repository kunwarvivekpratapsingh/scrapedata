"""Run a single hard question through the eval-dag critic loop.

Tests the full pipeline: DAG builder -> critic -> sandbox executor
with a complex Haversine-distance + fraud-rate analysis question.

The question requires these sequential DAG layers:
  Layer 0: Compute Haversine distance (km) between cardholder and merchant
           for every transaction using lat/long/merch_lat/merch_long
  Layer 1: Assign each transaction to a distance band:
           0-10km, 10-50km, 50-200km, 200+km
  Layer 2: Group by (category, distance_band) -> count, fraud_count, amt_sum
  Layer 3: Filter cells with count >= 20; compute fraud_rate and avg_amt
  Layer 4: Sort by fraud_rate descending, take top 3
  Layer 5: Return list of [category, distance_band, fraud_rate, count, avg_amt]

Ground truth (top 3):
  [['misc_net', '10-50km', 0.5, 66, 435.85],
   ['grocery_pos', '10-50km', 0.415929, 113, 189.28],
   ['shopping_net', '50-200km', 0.414458, 415, 469.43]]

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


# ── The hard question (Haversine + fraud rate by distance band) ───────────────

QUESTION = Question(
    id="q_hard_03",
    text=(
        "Using the transactions list, perform the following steps in order: "
        "STEP 1 - for every transaction compute the Haversine distance in kilometres "
        "between the cardholder location (lat, long) and the merchant location "
        "(merch_lat, merch_long) using the formula: "
        "a = sin((phi2-phi1)/2)^2 + cos(phi1)*cos(phi2)*sin((lam2-lam1)/2)^2, "
        "distance_km = 2 * R * asin(sqrt(a)) where R=6371 and all angles are in radians "
        "(use math.radians, math.sin, math.cos, math.asin, math.sqrt); "
        "STEP 2 - assign each transaction to a distance band based on its distance_km: "
        "'0-10km' if distance_km < 10, '10-50km' if 10 <= distance_km < 50, "
        "'50-200km' if 50 <= distance_km < 200, '200+km' if distance_km >= 200; "
        "STEP 3 - group transactions by (category, distance_band) and for each group "
        "accumulate: total_count, fraud_count (sum of is_fraud), amt_sum (sum of amt); "
        "STEP 4 - keep only groups where total_count >= 20, then for each kept group "
        "compute fraud_rate = fraud_count / total_count and avg_amt = amt_sum / total_count, "
        "rounding fraud_rate to 6 decimal places and avg_amt to 2 decimal places; "
        "STEP 5 - sort the kept groups by fraud_rate descending and take the top 3; "
        "STEP 6 - return the top 3 as a list of "
        "[category, distance_band, fraud_rate, total_count, avg_amt] sorted by fraud_rate descending."
    ),
    difficulty_rank=10,
    difficulty_level=DifficultyLevel.HARD,
    reasoning=(
        "Requires 6 sequential steps: "
        "(1) per-row Haversine calculation using math.radians/sin/cos/asin/sqrt - no imports needed, "
        "(2) band assignment via if/elif thresholds, "
        "(3) group by (category, distance_band) accumulating count, fraud_count, amt_sum using defaultdict, "
        "(4) filter cells with >= 20 rows then compute fraud_rate and avg_amt, "
        "(5) sort filtered cells by fraud_rate descending and slice top 3, "
        "(6) format as list of [category, band, fraud_rate, count, avg_amt]. "
        "Tests Haversine formula implementation, bucketing/banding, multi-field aggregation, "
        "minimum-volume filtering, and combined sort+slice. "
        "Critical: math.* functions are available directly - do NOT import math."
    ),
    relevant_data_keys=["transactions"],
)

# Verified ground truth computed from the full 5000-row transactions sample
# Top 3 (category, distance_band) cells by fraud_rate, min 20 transactions
GROUND_TRUTH = [
    ["misc_net",     "10-50km",   0.5,      66,  435.85],
    ["grocery_pos",  "10-50km",   0.415929, 113, 189.28],
    ["shopping_net", "50-200km",  0.414458, 415, 469.43],
]
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
    print("QUESTION (rank 10 / HARD - Haversine distance + fraud rate):")
    print(f"  {QUESTION.text}")
    print(f"\nGROUND TRUTH (top 3 by fraud_rate):")
    for row in GROUND_TRUTH:
        print(f"  {row}")
    print(f"\nSTEPS REQUIRED:")
    print("  Layer 0: Compute Haversine distance (km) per transaction from lat/long fields")
    print("  Layer 1: Assign distance band: 0-10km / 10-50km / 50-200km / 200+km")
    print("  Layer 2: Group by (category, distance_band) -> total_count, fraud_count, amt_sum")
    print("  Layer 3: Filter cells >= 20 txns; compute fraud_rate and avg_amt")
    print("  Layer 4: Sort by fraud_rate desc, take top 3")
    print("  Layer 5: Return [[category, band, fraud_rate, count, avg_amt], ...]")
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

        # Validate answer: list of [category, distance_band, fraud_rate, count, avg_amt]
        # rows sorted by fraud_rate descending, top 3.
        # Accept list-of-lists or list-of-tuples; order must match ground truth.
        try:
            if isinstance(answer, (list, tuple)) and len(answer) == len(GROUND_TRUTH):
                correct = True
                for ans_row, gt_row in zip(answer, GROUND_TRUTH):
                    ans_row = list(ans_row)
                    if len(ans_row) != 5:
                        correct = False
                        break
                    cat_ok   = str(ans_row[0]) == str(gt_row[0])
                    band_ok  = str(ans_row[1]) == str(gt_row[1])
                    fr_ok    = abs(float(ans_row[2]) - float(gt_row[2])) < MATCH_TOLERANCE
                    cnt_ok   = int(ans_row[3]) == int(gt_row[3])
                    amt_ok   = abs(float(ans_row[4]) - float(gt_row[4])) < 0.05
                    if not (cat_ok and band_ok and fr_ok and cnt_ok and amt_ok):
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

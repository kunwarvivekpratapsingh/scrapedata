"""Generate a self-contained HTML report from single_question_result.json.

Converts the output of run_single_question.py into the same rich HTML
format used by generate_report.py (DAG SVG, syntax-highlighted code,
iteration accordions, node output tables).

Usage:
    py scripts/generate_single_report.py
    py scripts/generate_single_report.py --input single_question_result.json --output single_question_report.html
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# Reuse all rendering logic from generate_report.py
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from generate_report import (
    _e,
    format_answer,
    generate_html,
    render_dag_node,
    render_dag_svg,
    render_iteration,
    render_node_outputs_table,
)


def _convert_single_to_report_format(data: dict) -> dict:
    """Convert single_question_result.json into the eval_results.json shape
    that generate_html() expects."""

    question     = data.get("question", {})
    ground_truth = data.get("ground_truth")
    correct      = data.get("correct", False)
    exec_result  = data.get("execution_result") or {}
    dag_history  = data.get("dag_history", [])
    iters_used   = data.get("iterations_used", 0)

    # ── Build the iteration list in generate_report format ──────────────────
    # dag_history entries look like: {iteration, dag, feedback}
    # generate_report expects:       {iteration, dag, critic_feedback}
    iterations = []
    for entry in dag_history:
        feedback_raw = entry.get("feedback") or {}
        # Normalise: run_single_question stores CriticFeedback as a flat dict
        # generate_report reads fields: is_approved, overall_reasoning,
        #   specific_errors, suggestions
        iterations.append({
            "iteration":      entry.get("iteration", "?"),
            "dag":            entry.get("dag") or {},
            "critic_feedback": {
                "is_approved":      feedback_raw.get("is_approved", False),
                "overall_reasoning": feedback_raw.get("overall_reasoning", ""),
                "specific_errors":  feedback_raw.get("specific_errors", []),
                "suggestions":      feedback_raw.get("suggestions", []),
            },
        })

    # ── Node outputs: strip the defaultdict repr wrapper if present ──────────
    raw_outputs = exec_result.get("node_outputs") or {}

    # ── Build question trace ─────────────────────────────────────────────────
    final_answer = exec_result.get("final_answer")
    exec_time    = exec_result.get("execution_time_ms", 0.0)
    exec_error   = exec_result.get("error")
    success      = bool(exec_result.get("success", False)) and correct

    q_trace = {
        "question_id":     question.get("id", "q_hard"),
        "question_text":   question.get("text", ""),
        "difficulty":      question.get("difficulty_level", "hard"),
        "difficulty_rank": question.get("difficulty_rank", 10),
        "total_iterations": iters_used,
        "success":         success,
        "final_answer":    final_answer,
        "execution_error": exec_error,
        "execution_time_ms": exec_time,
        "node_outputs":    raw_outputs,
        "iterations":      iterations,
        "conversation_log": [],      # run_single_question doesn't populate this
    }

    # ── Build summary ────────────────────────────────────────────────────────
    summary = {
        "total_questions":        1,
        "successful_executions":  1 if success else 0,
        "execution_failures":     0 if success else 1,
        "critic_loop_exhausted":  0,
        "pass_rate":              1.0 if success else 0.0,
    }

    difficulty_level = question.get("difficulty_level", "hard")
    difficulty_breakdown = {
        "easy":   {"total": 0, "passed": 0, "failed": 0},
        "medium": {"total": 0, "passed": 0, "failed": 0},
        "hard":   {"total": 0, "passed": 0, "failed": 0},
    }
    difficulty_breakdown[difficulty_level] = {
        "total":  1,
        "passed": 1 if success else 0,
        "failed": 0 if success else 1,
    }

    return {
        "summary":              summary,
        "difficulty_breakdown": difficulty_breakdown,
        "question_traces":      [q_trace],
        # Extra metadata (not used by generate_html but nice to have)
        "ground_truth":         ground_truth,
        "correct":              correct,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate HTML report from single_question_result.json",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--input",  default="single_question_result.json",
                        help="Path to single_question_result.json")
    parser.add_argument("--output", default="single_question_report.html",
                        help="Path to write the HTML report")
    args = parser.parse_args()

    input_path  = Path(args.input)
    output_path = Path(args.output)

    if not input_path.exists():
        print(f"ERROR: Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    with input_path.open(encoding="utf-8") as f:
        data = json.load(f)

    report_data  = _convert_single_to_report_format(data)
    dataset_name = input_path.stem
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    html_content = generate_html(report_data, dataset_name, generated_at)
    output_path.write_text(html_content, encoding="utf-8")

    print(f"Report written to : {output_path}")
    print(f"Open in browser   : file:///{output_path.resolve()}")


if __name__ == "__main__":
    main()

"""Result collector node — aggregates all results into a final report.

State reads: completed_results, failed_questions, questions
State writes: final_report
"""

from __future__ import annotations

import logging
from typing import Any

from eval_dag.state.models import DifficultyLevel
from eval_dag.state.schemas import OrchestratorState

logger = logging.getLogger(__name__)


def collect_results_node(state: OrchestratorState) -> dict[str, Any]:
    """LangGraph node: Aggregate results into a final evaluation report.

    Combines successful and failed question results with summary statistics
    and difficulty breakdown.

    Returns state updates for: final_report
    """
    completed = state.get("completed_results", [])
    failed = state.get("failed_questions", [])
    questions = state.get("questions", [])

    total = len(questions)
    successful = [r for r in completed if r.success]
    execution_failures = [r for r in completed if not r.success]

    # Build difficulty breakdown
    question_map = {q.id: q for q in questions}
    difficulty_breakdown: dict[str, dict[str, int]] = {
        "easy": {"total": 0, "passed": 0, "failed": 0},
        "medium": {"total": 0, "passed": 0, "failed": 0},
        "hard": {"total": 0, "passed": 0, "failed": 0},
    }

    for q in questions:
        level = q.difficulty_level.value
        difficulty_breakdown[level]["total"] += 1

    for result in successful:
        q = question_map.get(result.question_id)
        if q:
            difficulty_breakdown[q.difficulty_level.value]["passed"] += 1

    for result in execution_failures:
        q = question_map.get(result.question_id)
        if q:
            difficulty_breakdown[q.difficulty_level.value]["failed"] += 1

    for entry in failed:
        q = question_map.get(entry.get("question_id"))
        if q:
            difficulty_breakdown[q.difficulty_level.value]["failed"] += 1

    # Build detailed results
    detailed_results = []
    for result in completed:
        q = question_map.get(result.question_id)
        detailed_results.append({
            "question_id": result.question_id,
            "question_text": q.text if q else "Unknown",
            "difficulty": q.difficulty_level.value if q else "unknown",
            "success": result.success,
            "answer": result.final_answer,
            "error": result.error,
            "execution_time_ms": result.execution_time_ms,
        })

    # Build failure analysis
    failure_analysis = []
    for entry in failed:
        q = question_map.get(entry.get("question_id"))
        failure_analysis.append({
            "question_id": entry.get("question_id"),
            "question_text": q.text if q else "Unknown",
            "iterations_used": entry.get("iterations_used", 0),
            "last_feedback_summary": (
                entry.get("last_feedback", {}).get("overall_reasoning", "N/A")
                if isinstance(entry.get("last_feedback"), dict)
                else "N/A"
            ),
        })

    # Compute pass rate
    pass_rate = len(successful) / total if total > 0 else 0.0

    report = {
        "summary": {
            "total_questions": total,
            "successful_executions": len(successful),
            "execution_failures": len(execution_failures),
            "critic_loop_exhausted": len(failed),
            "pass_rate": round(pass_rate, 4),
        },
        "difficulty_breakdown": difficulty_breakdown,
        "detailed_results": detailed_results,
        "failure_analysis": failure_analysis,
        # Full audit trail — one entry per question containing:
        #   - All iterations: DAG structure with full node code, critic feedback
        #   - Conversation log: dag_builder / critic / executor messages in order
        #   - Execution output: node_outputs, final_answer, errors, timing
        "question_traces": sorted(
            state.get("question_traces", []),
            key=lambda t: t.get("difficulty_rank", 0),
        ),
    }

    logger.info(
        f"Report: {len(successful)}/{total} passed "
        f"({pass_rate:.1%}), "
        f"{len(failed)} exhausted critic loop"
    )

    return {"final_report": report}

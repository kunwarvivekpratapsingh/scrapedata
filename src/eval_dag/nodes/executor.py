"""Executor node — runs approved DAGs in the sandbox.

State reads: current_dag, dataset
State writes: execution_result, messages
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import AIMessage

from eval_dag.sandbox.runner import execute_approved_dag
from eval_dag.state.schemas import CriticLoopState

logger = logging.getLogger(__name__)


def execute_dag_node(state: CriticLoopState) -> dict[str, Any]:
    """LangGraph node: Execute an approved DAG in the sandbox.

    Called only after the critic approves the DAG.
    Runs the DAG layer by layer via the sandbox runner.

    Returns state updates for: execution_result, messages
    """
    dag = state["current_dag"]
    dataset = state["dataset"]

    logger.info(f"Executing approved DAG for question '{dag.question_id}'")

    result = execute_approved_dag(dag, dataset)

    # Detect the silent-failure case: sandbox reported success but the
    # final-answer node produced None.  This usually means the final node
    # forgot to return a value, or final_answer_node points to the wrong node.
    if result.success and result.final_answer is None:
        result = result.model_copy(update={
            "success": False,
            "error": (
                f"Final answer node '{dag.final_answer_node}' returned None. "
                "The node function must explicitly return a value. "
                "Check that final_answer_node is set to the correct node id "
                "and that the function body ends with a return statement."
            ),
        })
        logger.warning(
            f"[Executor] {dag.question_id}: final answer node "
            f"'{dag.final_answer_node}' returned None — marking as FAILED"
        )

    if result.success:
        ai_message = AIMessage(
            content=(
                f"[Executor] {dag.question_id}: SUCCESS — "
                f"answer={result.final_answer} "
                f"({result.execution_time_ms:.1f}ms)"
            ),
            name="executor",
        )
    else:
        ai_message = AIMessage(
            content=(
                f"[Executor] {dag.question_id}: FAILED — {result.error}"
            ),
            name="executor",
        )

    return {
        "execution_result": result,
        "messages": [ai_message],
    }

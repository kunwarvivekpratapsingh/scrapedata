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

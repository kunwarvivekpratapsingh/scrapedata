"""Inner critic loop subgraph.

Flow:
  build_dag -> validate_dag -> (route) -> execute_dag  (if approved)
                                       -> build_dag    (if rejected, < MAX_ITERATIONS)
                                       -> END          (if exhausted)

The compiled subgraph is invoked once per question via Send() from the
orchestrator. It returns CriticLoopState which the orchestrator wrapper
extracts results from.
"""

from __future__ import annotations

import logging
import os
from typing import Literal

from langgraph.graph import END, StateGraph

from eval_dag.nodes.critic import validate_dag_node
from eval_dag.nodes.dag_builder import build_dag_node
from eval_dag.nodes.executor import execute_dag_node
from eval_dag.state.schemas import CriticLoopState

logger = logging.getLogger(__name__)

# Maximum critic-loop iterations per question.
# Override via environment variable: EVAL_MAX_ITERATIONS=5 py scripts/run_eval.py
MAX_ITERATIONS = int(os.environ.get("EVAL_MAX_ITERATIONS", "3"))


def _route_after_validation(
    state: CriticLoopState,
) -> Literal["execute_dag", "build_dag", "__end__"]:
    """Decide next step after critic validates the DAG.

    - APPROVED  -> execute
    - REJECTED, iterations remaining -> rebuild
    - REJECTED, max iterations reached -> end (exhausted)
    """
    if state.get("is_approved", False):
        return "execute_dag"

    iteration = state.get("iteration_count", 1)
    if iteration >= MAX_ITERATIONS:
        logger.warning(
            f"Critic loop exhausted for question "
            f"'{state['question'].id}' after {iteration} iterations"
        )
        return "__end__"

    return "build_dag"


def build_critic_loop_graph() -> StateGraph:
    """Construct (but do not compile) the critic loop subgraph."""
    graph = StateGraph(CriticLoopState)

    graph.add_node("build_dag", build_dag_node)
    graph.add_node("validate_dag", validate_dag_node)
    graph.add_node("execute_dag", execute_dag_node)

    graph.set_entry_point("build_dag")

    graph.add_edge("build_dag", "validate_dag")

    graph.add_conditional_edges(
        "validate_dag",
        _route_after_validation,
        {
            "execute_dag": "execute_dag",
            "build_dag": "build_dag",
            "__end__": END,
        },
    )

    graph.add_edge("execute_dag", END)

    return graph


# Compiled subgraph — used by the orchestrator
critic_loop = build_critic_loop_graph().compile()

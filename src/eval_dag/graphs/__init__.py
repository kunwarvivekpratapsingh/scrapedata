"""Compiled LangGraph graphs for the eval-dag system.

Usage:
    from eval_dag.graphs import orchestrator, critic_loop

    result = orchestrator.invoke({
        "dataset": {...},
        "metadata": {"description": "...", "domain": "..."},
    })
    print(result["final_report"])
"""

from eval_dag.graphs.critic_loop import critic_loop
from eval_dag.graphs.orchestrator import orchestrator

__all__ = ["orchestrator", "critic_loop"]

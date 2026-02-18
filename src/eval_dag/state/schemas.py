"""LangGraph state schemas for the eval system.

Two schemas:
  - OrchestratorState: outer graph (ingest -> questions -> fan-out -> collect)
  - CriticLoopState: inner subgraph (build_dag <-> validate_dag cycle)

Reducer annotations are the critical design element — they determine how
parallel branches merge their outputs without data loss.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

from eval_dag.state.models import (
    CriticFeedback,
    ExecutionResult,
    GeneratedDAG,
    Question,
)


class OrchestratorState(TypedDict):
    """Top-level state for the outer orchestrator graph.

    Flows through: ingest -> generate_questions -> fan_out ->
    [per-question subgraphs] -> fan_in -> collect_results
    """

    # ── INPUT (set once at start, never mutated) ──
    dataset: dict[str, Any]
    metadata: dict[str, Any]

    # ── INTERMEDIATE (set once by generate_questions) ──
    questions: list[Question]

    # ── ACCUMULATING (parallel-safe via operator.add reducer) ──
    # CRITICAL: Without operator.add, Send()-dispatched parallel branches
    # would overwrite each other's results. Only the last branch's output
    # would survive. The reducer merges all branches' lists together.
    completed_results: Annotated[list[ExecutionResult], operator.add]
    failed_questions: Annotated[list[dict], operator.add]
    # Full audit trail — one entry per question with complete iteration history,
    # DAG code, critic feedback, and conversation log. operator.add ensures
    # parallel Send() branches each contribute their entry safely.
    question_traces: Annotated[list[dict], operator.add]

    # ── OUTPUT ──
    final_report: dict[str, Any]

    # ── TRACING ──
    messages: Annotated[list[AnyMessage], add_messages]


class CriticLoopState(TypedDict):
    """State for the inner critic loop subgraph.

    Separate schema from OrchestratorState. Created fresh for each question
    by the fan_out Send() dispatch. The process_question wrapper node
    translates between outer and inner state.
    """

    # ── CONTEXT (set once via Send(), read-only within the loop) ──
    question: Question
    dataset: dict[str, Any]
    metadata: dict[str, Any]

    # ── MUTABLE LOOP STATE (overwrite semantics) ──
    # current_dag: overwrites each iteration because the builder regenerates
    # the COMPLETE DAG (not patches). Old DAGs preserved in dag_history.
    current_dag: GeneratedDAG | None
    # current_feedback: overwrites each iteration. The builder reads this
    # to understand what to fix. None on first iteration.
    current_feedback: CriticFeedback | None
    # iteration_count: simple int, incremented by build_dag each cycle.
    # The routing function checks this against MAX_ITERATIONS.
    iteration_count: int
    # is_approved: set by validate_dag. Routing function uses this to
    # decide: execute, loop back, or mark exhausted.
    is_approved: bool

    # ── APPEND-ONLY HISTORY (reducer for accumulation) ──
    # Each cycle appends {iteration, dag, feedback}. Using operator.add
    # so returning [entry] from a node appends it to the existing list.
    dag_history: Annotated[list[dict], operator.add]

    # ── TERMINAL OUTPUT ──
    execution_result: ExecutionResult | None

    # ── TRACING ──
    messages: Annotated[list[AnyMessage], add_messages]

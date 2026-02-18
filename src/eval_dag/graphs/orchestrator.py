"""Outer orchestrator graph.

Flow:
  ingest_data -> generate_questions -> fan_out (Send per question)
              -> [critic_loop subgraph x N] -> fan_in
              -> collect_results -> END

fan_out uses LangGraph's Send() API to dispatch one CriticLoopState
per question in parallel. Each subgraph runs independently and writes
its result to completed_results or failed_questions (both use
operator.add reducer so parallel writes are safe).
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import HumanMessage
from langgraph.graph import END, StateGraph
from langgraph.types import Send

from eval_dag.graphs.critic_loop import critic_loop
from eval_dag.nodes.question_generator import generate_questions_node
from eval_dag.nodes.result_collector import collect_results_node
from eval_dag.state.models import ExecutionResult
from eval_dag.state.schemas import CriticLoopState, OrchestratorState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Ingest node
# ---------------------------------------------------------------------------

def ingest_data_node(state: OrchestratorState) -> dict[str, Any]:
    """Validate the dataset and metadata are present, pass through.

    This is a lightweight gate — real ingestion (loading from disk, APIs, etc.)
    happens before invoking the graph.
    """
    dataset = state.get("dataset", {})
    metadata = state.get("metadata", {})

    if not dataset:
        raise ValueError("dataset is empty — provide data before running the graph")

    logger.info(
        f"Ingested dataset with {len(dataset)} top-level keys. "
        f"Metadata: {list(metadata.keys())}"
    )

    return {
        "messages": [
            HumanMessage(
                content=f"[Ingest] Dataset ready: {len(dataset)} keys",
                name="ingest",
            )
        ]
    }


# ---------------------------------------------------------------------------
# Fan-out: one Send() per question -> critic_loop subgraph
# ---------------------------------------------------------------------------

def fan_out_node(state: OrchestratorState) -> list[Send]:
    """Dispatch one critic_loop subgraph per question using Send().

    Each Send() creates an independent CriticLoopState with the question,
    dataset, and metadata pre-populated. The subgraph handles the full
    build -> validate -> execute cycle.
    """
    questions = state.get("questions", [])
    dataset = state["dataset"]
    metadata = state.get("metadata", {})

    logger.info(f"Fanning out {len(questions)} questions to critic loops")

    return [
        Send(
            "process_question",
            CriticLoopState(
                question=q,
                dataset=dataset,
                metadata=metadata,
                current_dag=None,
                current_feedback=None,
                iteration_count=0,
                is_approved=False,
                dag_history=[],
                execution_result=None,
                messages=[],
            ),
        )
        for q in questions
    ]


# ---------------------------------------------------------------------------
# Fan-in wrapper: run the critic_loop subgraph and extract results
# ---------------------------------------------------------------------------

def _build_question_trace(question, final_state: dict, execution_result: ExecutionResult | None) -> dict:
    """Build the full audit trace for one question from the final CriticLoopState.

    Captures everything: question metadata, iteration-by-iteration DAG code and
    critic feedback, sandbox outputs, and the full builder↔critic conversation log.
    """
    # Build per-iteration records from dag_history
    iterations = []
    for entry in final_state.get("dag_history", []):
        dag_data = entry.get("dag", {})
        feedback_data = entry.get("feedback", {})
        iterations.append({
            "iteration": entry.get("iteration"),
            "dag": {
                "description": dag_data.get("description"),
                "final_answer_node": dag_data.get("final_answer_node"),
                "nodes": dag_data.get("nodes", []),   # includes code field for every node
                "edges": dag_data.get("edges", []),
            },
            "critic_feedback": {
                "is_approved": feedback_data.get("is_approved"),
                "overall_reasoning": feedback_data.get("overall_reasoning"),
                "layer_validations": feedback_data.get("layer_validations", []),
                "specific_errors": feedback_data.get("specific_errors", []),
                "suggestions": feedback_data.get("suggestions", []),
            },
        })

    # Conversation log: extract named messages from dag_builder, critic, executor
    conversation_log = []
    for msg in final_state.get("messages", []):
        if hasattr(msg, "name") and msg.name in ("dag_builder", "critic", "executor"):
            conversation_log.append({
                "role": msg.name,
                "content": msg.content,
            })

    return {
        "question_id": question.id,
        "question_text": question.text,
        "difficulty": question.difficulty_level.value,
        "difficulty_rank": question.difficulty_rank,
        "total_iterations": final_state.get("iteration_count", 0),
        "final_answer": execution_result.final_answer if execution_result else None,
        "success": execution_result.success if execution_result else False,
        "execution_error": execution_result.error if execution_result else None,
        "execution_time_ms": execution_result.execution_time_ms if execution_result else 0,
        "node_outputs": execution_result.node_outputs if execution_result else {},
        "iterations": iterations,
        "conversation_log": conversation_log,
    }


def process_question_node(state: CriticLoopState) -> dict[str, Any]:
    """Run the critic_loop subgraph for one question, then bubble up results.

    This is the target of each Send(). It:
    1. Invokes the compiled critic_loop subgraph
    2. Extracts execution_result or marks the question as failed
    3. Returns updates targeting OrchestratorState's accumulating fields
    4. Returns a full question_trace with DAG code, critic feedback, and
       conversation log for every iteration — the complete audit trail
    """
    question = state["question"]
    logger.info(f"Processing question '{question.id}'")

    final_state = critic_loop.invoke(state)

    execution_result: ExecutionResult | None = final_state.get("execution_result")

    # Build the full audit trace regardless of success/failure
    trace = _build_question_trace(question, final_state, execution_result)

    if execution_result is not None:
        return {
            "completed_results": [execution_result],
            "question_traces": [trace],
        }

    # Critic loop exhausted without approval
    last_feedback = final_state.get("current_feedback")
    return {
        "failed_questions": [
            {
                "question_id": question.id,
                "iterations_used": final_state.get("iteration_count", 0),
                "last_feedback": last_feedback.model_dump() if last_feedback else None,
            }
        ],
        "question_traces": [trace],
    }


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

def build_orchestrator_graph() -> StateGraph:
    """Construct (but do not compile) the orchestrator graph."""
    graph = StateGraph(OrchestratorState)

    graph.add_node("ingest_data", ingest_data_node)
    graph.add_node("generate_questions", generate_questions_node)
    graph.add_node("process_question", process_question_node)
    graph.add_node("collect_results", collect_results_node)

    graph.set_entry_point("ingest_data")

    graph.add_edge("ingest_data", "generate_questions")

    # fan_out returns Send() objects — LangGraph routes each to process_question
    graph.add_conditional_edges(
        "generate_questions",
        fan_out_node,
        ["process_question"],
    )

    # All process_question branches converge at collect_results
    graph.add_edge("process_question", "collect_results")
    graph.add_edge("collect_results", END)

    return graph


# Compiled graph — import this to run evaluations
orchestrator = build_orchestrator_graph().compile()

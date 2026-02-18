"""DAG builder node — generates or regenerates a DAG for one question.

On first iteration (current_feedback is None): generates from scratch.
On subsequent iterations: reads critic feedback and regenerates the full DAG.

State reads: question, dataset, metadata, current_feedback, current_dag, iteration_count
State writes: current_dag, iteration_count, messages
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from eval_dag.prompts.dag_gen import DAG_GEN_SYSTEM, build_dag_gen_prompt
from eval_dag.state.models import (
    DAGEdge,
    DAGNodeSpec,
    GeneratedDAG,
)
from eval_dag.state.schemas import CriticLoopState

logger = logging.getLogger(__name__)

_RATE_LIMIT_PHRASES = ("rate_limit_exceeded", "rate limit", "tokens per min", "429")


def _is_rate_limit_error(exc: Exception) -> bool:
    """Return True if the exception is an OpenAI rate-limit (429) error."""
    msg = str(exc).lower()
    return any(phrase.lower() in msg for phrase in _RATE_LIMIT_PHRASES)


def _get_llm():
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model="gpt-4o",
        temperature=0.2,
        model_kwargs={"response_format": {"type": "json_object"}},
    )


def _parse_dag(content: str, question_id: str) -> GeneratedDAG:
    """Parse LLM JSON response into a GeneratedDAG."""
    text = content.strip()
    if text.startswith("```"):
        first_newline = text.index("\n")
        text = text[first_newline + 1:]
    if text.endswith("```"):
        text = text[:-3]

    data = json.loads(text.strip())

    nodes = [DAGNodeSpec(**n) for n in data.get("nodes", [])]
    edges = [DAGEdge(**e) for e in data.get("edges", [])]

    return GeneratedDAG(
        question_id=question_id,
        nodes=nodes,
        edges=edges,
        final_answer_node=data["final_answer_node"],
        description=data.get("description", ""),
    )


def build_dag_node(state: CriticLoopState) -> dict[str, Any]:
    """LangGraph node: Generate or regenerate a DAG for the current question.

    Increments iteration_count on each call.
    Passes critic feedback to the LLM on iterations > 1 so it can fix issues.

    Returns state updates for: current_dag, iteration_count, messages
    """
    question = state["question"]
    dataset = state["dataset"]
    metadata = state.get("metadata", {})
    feedback = state.get("current_feedback")
    previous_dag = state.get("current_dag")
    iteration = state.get("iteration_count", 0) + 1

    logger.info(
        f"Building DAG for question '{question.id}' (iteration {iteration})"
    )

    llm = _get_llm()
    prompt = build_dag_gen_prompt(
        question=question,
        dataset=dataset,
        metadata=metadata,
        feedback=feedback,
        previous_dag=previous_dag,
    )

    messages = [
        SystemMessage(content=DAG_GEN_SYSTEM),
        HumanMessage(content=prompt),
    ]

    last_exc: Exception | None = None
    dag = None

    for attempt in range(3):
        try:
            response = llm.invoke(messages)
            dag = _parse_dag(response.content, question.id)
            break  # success
        except Exception as e:
            last_exc = e
            if _is_rate_limit_error(e) and attempt < 2:
                wait = 5 * (2 ** attempt)  # 5s, 10s
                logger.warning(
                    f"Rate limit hit for DAG generation '{question.id}' "
                    f"(attempt {attempt + 1}/3). Waiting {wait}s before retry..."
                )
                time.sleep(wait)
                continue
            # Non-rate-limit error or final rate-limit attempt — break out
            break

    if dag is not None:
        action = "regenerated" if feedback else "generated"
        logger.info(
            f"DAG {action} for '{question.id}': "
            f"{len(dag.nodes)} nodes, {len(dag.edges)} edges"
        )
        ai_message = AIMessage(
            content=(
                f"[DAGBuilder] Iteration {iteration} for {question.id}: "
                f"{action} DAG with {len(dag.nodes)} nodes"
            ),
            name="dag_builder",
        )
    else:
        logger.error(f"DAG generation failed for '{question.id}': {last_exc}")
        # Return an empty DAG so the critic can flag it cleanly
        dag = GeneratedDAG(
            question_id=question.id,
            nodes=[],
            edges=[],
            final_answer_node="",
            description=f"Generation failed: {last_exc}",
        )
        ai_message = AIMessage(
            content=f"[DAGBuilder] Iteration {iteration} for {question.id}: FAILED — {last_exc}",
            name="dag_builder",
        )

    return {
        "current_dag": dag,
        "iteration_count": iteration,
        "messages": [ai_message],
    }

"""Question generator node — generates 10 eval questions from a dataset.

State reads: dataset, metadata
State writes: questions, messages
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from eval_dag.prompts.question_gen import QUESTION_GEN_SYSTEM, build_question_gen_prompt
from eval_dag.state.models import DifficultyLevel, Question
from eval_dag.state.schemas import OrchestratorState

logger = logging.getLogger(__name__)


def _get_llm():
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model="gpt-4o",
        temperature=0.3,
        model_kwargs={"response_format": {"type": "json_object"}},
    )


def _parse_questions(content: str) -> list[Question]:
    """Parse LLM JSON response into Question objects."""
    text = content.strip()
    if text.startswith("```"):
        first_newline = text.index("\n")
        text = text[first_newline + 1:]
    if text.endswith("```"):
        text = text[:-3]

    data = json.loads(text.strip())
    questions_raw = data.get("questions", [])

    questions: list[Question] = []
    for q in questions_raw:
        questions.append(
            Question(
                id=q["id"],
                text=q["text"],
                difficulty_rank=q["difficulty_rank"],
                difficulty_level=DifficultyLevel(q["difficulty_level"]),
                reasoning=q["reasoning"],
                relevant_data_keys=q.get("relevant_data_keys", []),
            )
        )

    return sorted(questions, key=lambda q: q.difficulty_rank)


def generate_questions_node(state: OrchestratorState) -> dict[str, Any]:
    """LangGraph node: Generate 10 evaluation questions from the dataset.

    Calls the LLM once with the dataset structure and metadata to produce
    10 questions ranked easy to hard.

    Returns state updates for: questions, messages
    """
    dataset = state["dataset"]
    metadata = state.get("metadata", {})

    logger.info("Generating questions from dataset...")

    llm = _get_llm()
    prompt = build_question_gen_prompt(dataset, metadata)

    messages = [
        SystemMessage(content=QUESTION_GEN_SYSTEM),
        HumanMessage(content=prompt),
    ]

    response = llm.invoke(messages)
    questions = _parse_questions(response.content)

    logger.info(f"Generated {len(questions)} questions")

    ai_message = AIMessage(
        content=f"[QuestionGenerator] Generated {len(questions)} questions",
        name="question_generator",
    )

    return {
        "questions": questions,
        "messages": [ai_message],
    }

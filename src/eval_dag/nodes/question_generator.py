"""Question generator node — generates 10 eval questions from a dataset.

State reads: dataset, metadata
State writes: questions, messages
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from eval_dag.prompts.question_gen import QUESTION_GEN_SYSTEM, build_question_gen_prompt
from eval_dag.state.models import DifficultyLevel, Question
from eval_dag.state.schemas import OrchestratorState

# ─── Constants ────────────────────────────────────────────────────────────────
_DEFAULT_NUM_QUESTIONS = 10

logger = logging.getLogger(__name__)

_RATE_LIMIT_PHRASES = ("rate_limit_exceeded", "rate limit", "tokens per min", "429")
_MAX_RETRIES = 3


def _is_rate_limit_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(p.lower() in msg for p in _RATE_LIMIT_PHRASES)


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
    """LangGraph node: Generate evaluation questions from the dataset.

    Calls the LLM with the dataset structure and metadata to produce
    questions ranked easy to hard.  When called from the live API runner,
    the optional _difficulty and _num_questions fields in state are used to
    filter and slice the generated list before returning it.

    Retries up to _MAX_RETRIES times on rate-limit or JSON parse errors
    with exponential back-off. Raises on persistent failure so the
    orchestrator can surface a clear error rather than silently producing
    zero questions.

    Returns state updates for: questions, messages
    """
    dataset = state["dataset"]
    metadata = state.get("metadata", {})

    # ── Live runner controls (absent in CLI runs) ──────────────────────────
    difficulty_filter: str = state.get("_difficulty") or "all"
    num_questions: int = state.get("_num_questions") or _DEFAULT_NUM_QUESTIONS
    emit = state.get("_progress_cb")   # thread-safe callback or None

    logger.info(
        f"Generating questions (difficulty={difficulty_filter}, n={num_questions})..."
    )

    llm = _get_llm()
    prompt = build_question_gen_prompt(
        dataset,
        metadata,
        difficulty_hint=difficulty_filter,
        num_questions=num_questions,
    )

    messages = [
        SystemMessage(content=QUESTION_GEN_SYSTEM),
        HumanMessage(content=prompt),
    ]

    last_exc: Exception | None = None
    questions: list[Question] = []

    for attempt in range(_MAX_RETRIES):
        try:
            response = llm.invoke(messages)
            questions = _parse_questions(response.content)
            break  # success
        except Exception as e:
            last_exc = e
            retryable = _is_rate_limit_error(e) or isinstance(e, (ValueError, json.JSONDecodeError))
            if retryable and attempt < _MAX_RETRIES - 1:
                wait = 5 * (2 ** attempt)  # 5s, 10s
                logger.warning(
                    f"Question generation failed (attempt {attempt + 1}/{_MAX_RETRIES}): "
                    f"{e}. Retrying in {wait}s..."
                )
                time.sleep(wait)
                continue
            # Non-retryable or final attempt — propagate
            raise RuntimeError(
                f"Question generation failed after {attempt + 1} attempt(s): {e}"
            ) from e

    if not questions:
        raise RuntimeError(
            f"Question generation produced no questions after {_MAX_RETRIES} attempts. "
            f"Last error: {last_exc}"
        )

    # ── Filter by difficulty ───────────────────────────────────────────────
    if difficulty_filter != "all":
        questions = [
            q for q in questions
            if q.difficulty_level.value == difficulty_filter
        ]
        logger.info(
            f"Filtered to {len(questions)} '{difficulty_filter}' questions"
        )

    # ── Slice to requested count ───────────────────────────────────────────
    questions = questions[:num_questions]

    logger.info(f"Using {len(questions)} questions for this run")

    # ── Emit SSE progress event ────────────────────────────────────────────
    if emit:
        emit("questions_generated", {
            "questions": [
                {
                    "id": q.id,
                    "text": q.text,
                    "difficulty_level": q.difficulty_level.value,
                    "difficulty_rank": q.difficulty_rank,
                }
                for q in questions
            ]
        })

    ai_message = AIMessage(
        content=f"[QuestionGenerator] Generated {len(questions)} questions",
        name="question_generator",
    )

    return {
        "questions": questions,
        "messages": [ai_message],
    }

"""Prompt templates for question generation."""

from __future__ import annotations

import json
from typing import Any


QUESTION_GEN_SYSTEM = """You are an expert evaluation question designer. Given a dataset and its metadata, you generate exactly 10 questions that test analytical and computational skills on the data.

Requirements:
- Generate exactly 10 questions, ranked from easiest (rank 1) to hardest (rank 10)
- Difficulty distribution: ranks 1-3 = "easy", ranks 4-7 = "medium", ranks 8-10 = "hard"
- Each question must be answerable using ONLY the provided dataset
- Questions should require multi-step computation (not simple lookups)
- Easy questions: 1-2 computation steps
- Medium questions: 2-4 computation steps with some data transformation
- Hard questions: 4+ steps, requiring aggregation, filtering, and derived metrics

Question content guidelines:
- PREFER questions about aggregates, rates, statistics, distributions, rankings, and trends
- PREFER questions that use pre-aggregated keys (category_stats, state_stats, time_series, etc.) for global figures
- PREFER questions that compare categories, states, time periods, or genders by fraud rate, amounts, or counts
- AVOID questions that ask to list, extract, or enumerate individual PII values (names, card numbers, DOB, job titles)
- AVOID questions whose answer is a list of person names or identifiers — focus on aggregate metrics
- For questions using the transactions sample: always target computed aggregates (averages, counts, rates) not individual records

You MUST respond with valid JSON matching this exact schema:
{
  "questions": [
    {
      "id": "q_01",
      "text": "What is the average revenue across all regions?",
      "difficulty_rank": 1,
      "difficulty_level": "easy",
      "reasoning": "Simple average of a single column",
      "relevant_data_keys": ["regions", "revenue"]
    }
  ]
}"""


def build_question_gen_prompt(
    dataset: dict[str, Any],
    metadata: dict[str, Any],
    difficulty_hint: str = "all",
    num_questions: int = 10,
) -> str:
    """Build the user prompt for question generation.

    Args:
        dataset: The dataset to generate questions from.
        metadata: Optional dataset metadata.
        difficulty_hint: "easy" | "medium" | "hard" | "all" — narrows the LLM's
            focus so it generates questions of the right difficulty band.
        num_questions: How many questions to generate (1–10).
    """
    dataset_summary = _summarize_dataset(dataset)

    if difficulty_hint == "all":
        difficulty_instruction = (
            f"Generate exactly {num_questions} questions, "
            "spanning easy, medium, and hard difficulties "
            "(ranks 1–10 scaled to the count requested). "
            "Distribute difficulty evenly."
        )
    else:
        difficulty_instruction = (
            f"Generate exactly {num_questions} question(s), ALL at '{difficulty_hint}' difficulty. "
            f"Every question MUST have difficulty_level = \"{difficulty_hint}\"."
        )

    return f"""Generate {num_questions} evaluation question(s) for this dataset.

## Task
{difficulty_instruction}

## Dataset Metadata
{json.dumps(metadata, indent=2, default=str)}

## Dataset Structure
{dataset_summary}

Respond with JSON only. The "questions" array must contain exactly {num_questions} item(s)."""


def _summarize_dataset(dataset: dict[str, Any], max_depth: int = 3) -> str:
    """Create a human-readable summary of dataset structure."""
    lines: list[str] = []
    _summarize_recursive(dataset, lines, prefix="", depth=0, max_depth=max_depth)
    return "\n".join(lines)


def _summarize_recursive(
    obj: Any,
    lines: list[str],
    prefix: str,
    depth: int,
    max_depth: int,
) -> None:
    """Recursively summarize a data structure."""
    if depth >= max_depth:
        lines.append(f"{prefix}... (truncated)")
        return

    if isinstance(obj, dict):
        for key, value in obj.items():
            if isinstance(value, (dict, list)):
                lines.append(f"{prefix}{key}: ({type(value).__name__})")
                _summarize_recursive(
                    value, lines, prefix=prefix + "  ", depth=depth + 1, max_depth=max_depth
                )
            else:
                lines.append(f"{prefix}{key}: {type(value).__name__} = {_truncate(value)}")
    elif isinstance(obj, list):
        if len(obj) == 0:
            lines.append(f"{prefix}(empty list)")
        else:
            lines.append(f"{prefix}(list of {len(obj)} items, showing first)")
            _summarize_recursive(
                obj[0], lines, prefix=prefix + "  ", depth=depth + 1, max_depth=max_depth
            )
    else:
        lines.append(f"{prefix}{type(obj).__name__} = {_truncate(obj)}")


def _truncate(value: Any, max_len: int = 80) -> str:
    """Truncate a value's string representation."""
    s = str(value)
    if len(s) > max_len:
        return s[:max_len] + "..."
    return s

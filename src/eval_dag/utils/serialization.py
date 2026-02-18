"""Serialization utilities for DAG objects."""

from __future__ import annotations

import json
from typing import Any

from eval_dag.state.models import GeneratedDAG, CriticFeedback, ExecutionResult


def dag_to_json(dag: GeneratedDAG) -> str:
    """Serialize a GeneratedDAG to a JSON string."""
    return dag.model_dump_json(indent=2)


def dag_from_json(data: str | dict) -> GeneratedDAG:
    """Deserialize a GeneratedDAG from JSON string or dict."""
    if isinstance(data, str):
        return GeneratedDAG.model_validate_json(data)
    return GeneratedDAG.model_validate(data)


def feedback_to_json(feedback: CriticFeedback) -> str:
    """Serialize CriticFeedback to a JSON string."""
    return feedback.model_dump_json(indent=2)


def feedback_from_json(data: str | dict) -> CriticFeedback:
    """Deserialize CriticFeedback from JSON string or dict."""
    if isinstance(data, str):
        return CriticFeedback.model_validate_json(data)
    return CriticFeedback.model_validate(data)


def result_to_dict(result: ExecutionResult) -> dict[str, Any]:
    """Convert an ExecutionResult to a plain dict for reporting."""
    return result.model_dump()

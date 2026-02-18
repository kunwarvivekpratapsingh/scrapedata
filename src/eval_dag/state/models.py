"""Pydantic data models for the DAG-based eval system.

These are structured data objects that live *inside* LangGraph state fields.
They define the shape of questions, DAG nodes/edges, critic feedback, and
execution results.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class DifficultyLevel(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class Question(BaseModel):
    """A single eval question generated from the dataset."""

    id: str = Field(description="Unique question identifier, e.g. 'q_01'")
    text: str = Field(description="The question text")
    difficulty_rank: int = Field(
        ge=1, le=10, description="Rank from 1 (easiest) to 10 (hardest)"
    )
    difficulty_level: DifficultyLevel
    reasoning: str = Field(description="Why this difficulty was assigned")
    relevant_data_keys: list[str] = Field(
        default_factory=list,
        description="Which dataset keys are relevant to answering this question",
    )


class DAGNodeSpec(BaseModel):
    """A single node in the generated DAG — one executable step.

    Not a LangGraph node — this represents a step in the eval execution plan.
    The `inputs` dict maps parameter names to string references:
      - "dataset.<field>" for raw dataset access
      - "prev_node.<node_id>.output" for upstream node output
      - Literal values (int, str, etc.) for constants
    """

    node_id: str = Field(description="Unique node identifier, e.g. 'step_1a'")
    operation: str = Field(description="Human-readable description of what this step does")
    function_name: str = Field(description="Name of the Python function to call")
    inputs: dict[str, Any] = Field(
        default_factory=dict,
        description="Parameter mapping: param_name -> source reference or literal",
    )
    expected_output_type: str = Field(
        description="Expected return type, e.g. 'float', 'list[str]', 'dict'"
    )
    layer: int = Field(
        ge=0,
        description="Execution layer (0 = no deps, higher = later). "
        "Assigned by the LLM, validated by the critic.",
    )
    code: str = Field(description="The actual Python function code to execute in sandbox")


class DAGEdge(BaseModel):
    """A dependency edge in the generated DAG."""

    source: str = Field(description="node_id of the upstream node")
    target: str = Field(description="node_id of the downstream node")


class GeneratedDAG(BaseModel):
    """Complete DAG structure for one question.

    Contains all nodes, edges, and metadata needed to execute the plan.
    """

    question_id: str
    nodes: list[DAGNodeSpec]
    edges: list[DAGEdge]
    final_answer_node: str = Field(
        description="node_id whose output is the final answer"
    )
    description: str = Field(
        description="LLM's explanation of the overall approach"
    )


class LayerValidation(BaseModel):
    """Critic's verdict on a single layer of the DAG."""

    layer_index: int
    nodes_in_layer: list[str] = Field(description="node_ids in this layer")
    is_valid: bool
    issues: list[str] = Field(
        default_factory=list, description="Error descriptions (empty if valid)"
    )


class CriticFeedback(BaseModel):
    """Complete feedback from the critic for one DAG.

    Includes per-layer validation results plus overall assessment.
    The DAG builder uses this to understand exactly what went wrong
    and regenerate the complete DAG.
    """

    is_approved: bool
    overall_reasoning: str = Field(
        description="High-level summary of the DAG's quality"
    )
    layer_validations: list[LayerValidation] = Field(
        default_factory=list,
        description="Ordered by layer_index",
    )
    specific_errors: list[str] = Field(
        default_factory=list,
        description="Actionable error descriptions for the builder",
    )
    suggestions: list[str] = Field(
        default_factory=list,
        description="Improvement hints for the next iteration",
    )


class ExecutionResult(BaseModel):
    """Result of executing one approved DAG in the sandbox."""

    question_id: str
    success: bool
    final_answer: Any = None
    node_outputs: dict[str, Any] = Field(
        default_factory=dict,
        description="node_id -> output value for each executed node",
    )
    error: str | None = None
    execution_time_ms: float = 0.0

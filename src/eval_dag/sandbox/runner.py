"""Sandbox execution engine for DAG nodes.

Executes LLM-generated Python code in a restricted environment using:
1. AST-level safety checks (pre-validated by critic)
2. Restricted builtins (only safe operations)
3. Pre-imported safe modules (math, statistics, etc.)
4. Timeout enforcement per node
"""

from __future__ import annotations

import time
import signal
import platform
from dataclasses import dataclass
from typing import Any

from eval_dag.sandbox.permissions import build_restricted_builtins, build_safe_module_imports
from eval_dag.state.models import DAGNodeSpec, GeneratedDAG, ExecutionResult
from eval_dag.utils.dag_utils import extract_layers, resolve_input_reference


@dataclass
class NodeResult:
    """Result of executing a single DAG node."""

    success: bool
    output: Any = None
    error: str | None = None


# Timeout is only supported on non-Windows platforms with SIGALRM
_HAS_SIGALRM = hasattr(signal, "SIGALRM")

NODE_TIMEOUT_SECONDS = 30


class TimeoutError(Exception):
    pass


def _timeout_handler(signum, frame):
    raise TimeoutError("Node execution timed out")


def sandbox_execute_node(
    node_spec: DAGNodeSpec,
    resolved_inputs: dict[str, Any],
) -> NodeResult:
    """Execute a single DAG node's code in a restricted environment.

    The node's code defines a function. We compile it, execute the definition,
    then call the function with resolved_inputs as keyword arguments.
    """
    # Build restricted execution environment
    restricted_builtins = build_restricted_builtins()
    safe_modules = build_safe_module_imports()

    restricted_globals = {
        "__builtins__": restricted_builtins,
        "__inputs__": resolved_inputs,
    }
    # Make safe modules available as globals
    restricted_globals.update(safe_modules)

    # Build the execution code:
    # 1. Define the function from node_spec.code
    # 2. Call it with resolved inputs
    exec_code = f"""{node_spec.code}

__result__ = {node_spec.function_name}(**__inputs__)
"""

    # Set up timeout (Unix only)
    if _HAS_SIGALRM:
        old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(NODE_TIMEOUT_SECONDS)

    try:
        exec(exec_code, restricted_globals)  # noqa: S102
        result = restricted_globals.get("__result__")
        return NodeResult(success=True, output=result)
    except TimeoutError:
        return NodeResult(success=False, error="Execution timed out")
    except Exception as e:
        return NodeResult(success=False, error=f"{type(e).__name__}: {e}")
    finally:
        if _HAS_SIGALRM:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)


def execute_approved_dag(
    dag: GeneratedDAG,
    dataset: dict[str, Any],
) -> ExecutionResult:
    """Execute a complete approved DAG layer by layer in the sandbox.

    Each layer's nodes are executed sequentially (could be parallelized later).
    Outputs from earlier layers are fed as inputs to later layers via
    reference resolution.
    """
    node_outputs: dict[str, Any] = {}
    layers = extract_layers(dag)

    start_time = time.monotonic()

    for layer_idx, layer_nodes in enumerate(layers):
        for node_spec in layer_nodes:
            # Resolve input references
            try:
                resolved_inputs: dict[str, Any] = {}
                for param_name, ref in node_spec.inputs.items():
                    resolved_inputs[param_name] = resolve_input_reference(
                        ref, dataset, node_outputs
                    )
            except (KeyError, IndexError, TypeError) as e:
                elapsed = (time.monotonic() - start_time) * 1000
                return ExecutionResult(
                    question_id=dag.question_id,
                    success=False,
                    final_answer=None,
                    node_outputs=node_outputs,
                    error=(
                        f"Input resolution failed for node '{node_spec.node_id}' "
                        f"in layer {layer_idx}: {e}"
                    ),
                    execution_time_ms=elapsed,
                )

            # Execute the node
            result = sandbox_execute_node(node_spec, resolved_inputs)

            if result.success:
                node_outputs[node_spec.node_id] = result.output
            else:
                elapsed = (time.monotonic() - start_time) * 1000
                return ExecutionResult(
                    question_id=dag.question_id,
                    success=False,
                    final_answer=None,
                    node_outputs=node_outputs,
                    error=(
                        f"Node '{node_spec.node_id}' in layer {layer_idx} "
                        f"failed: {result.error}"
                    ),
                    execution_time_ms=elapsed,
                )

    elapsed = (time.monotonic() - start_time) * 1000
    final_answer = node_outputs.get(dag.final_answer_node)

    return ExecutionResult(
        question_id=dag.question_id,
        success=True,
        final_answer=final_answer,
        node_outputs=node_outputs,
        error=None,
        execution_time_ms=elapsed,
    )

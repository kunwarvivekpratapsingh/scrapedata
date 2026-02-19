"""Sandbox execution engine for DAG nodes.

Executes LLM-generated Python code in a restricted environment using:
1. AST-level safety checks (pre-validated by critic)
2. Restricted builtins (only safe operations)
3. Pre-imported safe modules (math, statistics, etc.)
4. Cross-platform timeout enforcement per node (threading.Timer on all OSes)
"""

from __future__ import annotations

import ctypes
import signal
import threading
import time
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


# Per-node wall-clock timeout in seconds. Overridable via env var:
#   EVAL_NODE_TIMEOUT=60 py scripts/run_eval.py ...
import os as _os
NODE_TIMEOUT_SECONDS = int(_os.environ.get("EVAL_NODE_TIMEOUT", "30"))

# SIGALRM is more precise on Unix; we fall back to threading on Windows.
_HAS_SIGALRM = hasattr(signal, "SIGALRM")


class NodeTimeoutError(Exception):
    pass


# ── SIGALRM path (Unix) ──────────────────────────────────────────────────────

def _sigalrm_handler(signum, frame):
    raise NodeTimeoutError("Node execution timed out")


# ── Threading path (Windows + Unix fallback) ─────────────────────────────────

def _raise_in_thread(tid: int, exc_type: type) -> None:
    """Raise an exception in another thread by its id (CPython-specific).

    Uses ctypes.pythonapi.PyThreadState_SetAsyncExc which injects an async
    exception into the target thread. Works on CPython 3.x on all platforms.
    """
    ret = ctypes.pythonapi.PyThreadState_SetAsyncExc(
        ctypes.c_ulong(tid),
        ctypes.py_object(exc_type),
    )
    if ret == 0:
        pass  # Thread already finished — nothing to do
    elif ret > 1:
        # Multiple frames modified — undo to avoid corrupting interpreter state
        ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_ulong(tid), None)


class _ThreadedTimeout:
    """Context manager that injects NodeTimeoutError into the current thread
    after `seconds` wall-clock seconds. Works on all platforms."""

    def __init__(self, seconds: int):
        self._seconds = seconds
        self._tid = threading.current_thread().ident
        self._timer: threading.Timer | None = None

    def __enter__(self):
        self._timer = threading.Timer(
            self._seconds,
            _raise_in_thread,
            args=(self._tid, NodeTimeoutError),
        )
        self._timer.daemon = True
        self._timer.start()
        return self

    def __exit__(self, *_):
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None


def _build_restricted_globals(resolved_inputs: dict[str, Any]) -> dict[str, Any]:
    """Build a fresh isolated execution environment for one node.

    A new dict is constructed on every call so nodes cannot pollute each
    other's globals even if exec() mutates the environment.
    """
    restricted_builtins = build_restricted_builtins()
    safe_modules = build_safe_module_imports()

    # Start with a clean slate — never share globals between nodes
    restricted_globals: dict[str, Any] = {
        "__builtins__": restricted_builtins,
        "__inputs__": resolved_inputs,
    }
    restricted_globals.update(safe_modules)

    # Expose commonly used sub-objects directly so LLM code like
    # `datetime.strptime(s, fmt)` or `stdev(lst)` works without imports.
    import collections as _col
    import datetime as _dt
    import statistics as _stats

    restricted_globals.update({
        "datetime":    _dt.datetime,         # datetime.strptime(...) works
        "timedelta":   _dt.timedelta,        # timedelta(days=1) works
        "date":        _dt.date,             # date.today() works
        "defaultdict": _col.defaultdict,     # defaultdict(int) works
        "Counter":     _col.Counter,         # Counter(lst) works
        "OrderedDict": _col.OrderedDict,     # OrderedDict() works
        "stdev":       _stats.stdev,         # stdev(lst) works
        "mean":        _stats.mean,          # mean(lst) works
        "median":      _stats.median,        # median(lst) works
    })

    return restricted_globals


def sandbox_execute_node(
    node_spec: DAGNodeSpec,
    resolved_inputs: dict[str, Any],
) -> NodeResult:
    """Execute a single DAG node's code in a restricted environment.

    The node's code defines a function. We compile it, execute the definition,
    then call the function with resolved_inputs as keyword arguments.

    Timeout is enforced on ALL platforms:
      - Unix:    SIGALRM (most precise, no thread overhead)
      - Windows: threading.Timer + ctypes async exception injection
    """
    # Fresh isolated globals — never reuse across nodes
    restricted_globals = _build_restricted_globals(resolved_inputs)

    # Build the execution code:
    # 1. Define the function from node_spec.code
    # 2. Call it with resolved inputs and capture result
    exec_code = (
        f"{node_spec.code}\n\n"
        f"__result__ = {node_spec.function_name}(**__inputs__)\n"
    )

    if _HAS_SIGALRM:
        # Unix path: SIGALRM — most reliable, zero threading overhead
        old_handler = signal.signal(signal.SIGALRM, _sigalrm_handler)
        signal.alarm(NODE_TIMEOUT_SECONDS)
        try:
            exec(exec_code, restricted_globals)  # noqa: S102
            return NodeResult(success=True, output=restricted_globals.get("__result__"))
        except NodeTimeoutError:
            return NodeResult(success=False, error=f"Node timed out after {NODE_TIMEOUT_SECONDS}s")
        except Exception as e:
            return NodeResult(success=False, error=f"{type(e).__name__}: {e}")
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)
    else:
        # Windows / non-SIGALRM path: threading.Timer injects async exception
        with _ThreadedTimeout(NODE_TIMEOUT_SECONDS):
            try:
                exec(exec_code, restricted_globals)  # noqa: S102
                return NodeResult(success=True, output=restricted_globals.get("__result__"))
            except NodeTimeoutError:
                return NodeResult(success=False, error=f"Node timed out after {NODE_TIMEOUT_SECONDS}s")
            except Exception as e:
                return NodeResult(success=False, error=f"{type(e).__name__}: {e}")


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

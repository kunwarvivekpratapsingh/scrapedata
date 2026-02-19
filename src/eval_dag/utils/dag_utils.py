"""DAG utility functions.

Pure functions to operate on GeneratedDAG objects:
- Layer extraction and grouping
- Structural validation (acyclicity, layer assignment, connectivity)
- Input reference resolution for execution
"""

from __future__ import annotations

import ast
import graphlib
from collections import defaultdict
from typing import Any

from eval_dag.state.models import DAGNodeSpec, GeneratedDAG


def extract_layers(dag: GeneratedDAG) -> list[list[DAGNodeSpec]]:
    """Group DAG nodes by their layer field, sorted by layer index.

    Returns a list where index i contains all nodes at layer i.
    """
    layer_map: dict[int, list[DAGNodeSpec]] = defaultdict(list)
    for node in dag.nodes:
        layer_map[node.layer].append(node)

    if not layer_map:
        return []

    max_layer = max(layer_map.keys())
    return [layer_map.get(i, []) for i in range(max_layer + 1)]


def validate_layer_assignment(dag: GeneratedDAG) -> list[str]:
    """Check that every node's layer is consistent with its dependencies.

    A node at layer N must have ALL dependencies at layers < N.
    Returns list of error strings (empty if valid).
    """
    errors: list[str] = []
    node_map = {n.node_id: n for n in dag.nodes}

    # Build dependency map from edges
    deps: dict[str, list[str]] = defaultdict(list)
    for edge in dag.edges:
        deps[edge.target].append(edge.source)

    for node in dag.nodes:
        for dep_id in deps.get(node.node_id, []):
            dep_node = node_map.get(dep_id)
            if dep_node is None:
                errors.append(
                    f"Node '{node.node_id}' depends on '{dep_id}' which does not exist"
                )
            elif dep_node.layer >= node.layer:
                errors.append(
                    f"Node '{node.node_id}' (layer {node.layer}) depends on "
                    f"'{dep_id}' (layer {dep_node.layer}) — dependency must be "
                    f"in an earlier layer"
                )

    return errors


def validate_acyclicity(dag: GeneratedDAG) -> tuple[bool, str | None]:
    """Verify the DAG has no cycles using graphlib.TopologicalSorter.

    Returns (True, None) if acyclic, (False, error_message) if cyclic.
    """
    sorter = graphlib.TopologicalSorter()
    for node in dag.nodes:
        sorter.add(node.node_id)
    for edge in dag.edges:
        sorter.add(edge.target, edge.source)

    try:
        # prepare() detects cycles
        sorter.prepare()
        return True, None
    except graphlib.CycleError as e:
        return False, str(e)


def validate_connectivity(dag: GeneratedDAG) -> list[str]:
    """Check that final_answer_node exists and all nodes are reachable or
    contribute to the final answer.

    Returns list of error strings (empty if valid).
    """
    errors: list[str] = []
    node_ids = {n.node_id for n in dag.nodes}

    # Check final_answer_node exists
    if dag.final_answer_node not in node_ids:
        errors.append(
            f"final_answer_node '{dag.final_answer_node}' does not exist in the DAG"
        )
        return errors

    # Build adjacency (forward) and reverse adjacency
    forward: dict[str, set[str]] = defaultdict(set)
    reverse: dict[str, set[str]] = defaultdict(set)
    for edge in dag.edges:
        forward[edge.source].add(edge.target)
        reverse[edge.target].add(edge.source)

    # Find nodes reachable from roots (nodes with no incoming edges)
    roots = node_ids - set(reverse.keys())
    if not roots:
        errors.append("No root nodes found (all nodes have incoming edges)")
        return errors

    # BFS forward from roots
    reachable_from_roots: set[str] = set()
    queue = list(roots)
    while queue:
        current = queue.pop(0)
        if current in reachable_from_roots:
            continue
        reachable_from_roots.add(current)
        queue.extend(forward.get(current, set()))

    # Check final_answer_node is reachable from at least one root
    if dag.final_answer_node not in reachable_from_roots:
        errors.append(
            f"final_answer_node '{dag.final_answer_node}' is not reachable "
            f"from any root node"
        )

    # BFS backward from final_answer_node to find contributing nodes
    contributing: set[str] = set()
    queue = [dag.final_answer_node]
    while queue:
        current = queue.pop(0)
        if current in contributing:
            continue
        contributing.add(current)
        queue.extend(reverse.get(current, set()))

    # Check for orphaned nodes (not contributing to the answer)
    orphaned = node_ids - contributing
    if orphaned:
        errors.append(
            f"Orphaned nodes that don't contribute to the final answer: "
            f"{sorted(orphaned)}"
        )

    return errors


def validate_code_syntax(code: str) -> tuple[bool, str | None]:
    """Check if a code string is valid Python syntax.

    Returns (True, None) if valid, (False, error_message) if invalid.
    """
    try:
        ast.parse(code)
        return True, None
    except SyntaxError as e:
        return False, f"SyntaxError at line {e.lineno}: {e.msg}"


# Patterns that are forbidden in sandbox-executed code
FORBIDDEN_AST_NODES = {
    "Import",
    "ImportFrom",
}

FORBIDDEN_NAMES = {
    "__import__",
    "exec",
    "eval",
    "compile",
    "globals",
    "locals",
    "vars",
    "dir",
    "getattr",
    "setattr",
    "delattr",
    "open",
    "input",
    "breakpoint",
    "exit",
    "quit",
}

FORBIDDEN_MODULE_NAMES = {
    "os",
    "sys",
    "subprocess",
    "importlib",
    "socket",
    "shutil",
    "pathlib",
    "io",
    "pickle",
    "shelve",
    "ctypes",
    "signal",
    "multiprocessing",
    "threading",
}


def validate_code_safety(code: str) -> list[str]:
    """AST-walk to detect forbidden operations in node code.

    Checks:
    1. Import statements (any form)
    2. Calls to forbidden builtins (exec, eval, open, etc.)
    3. Dunder name access as a bare Name node (__builtins__, __class__, etc.)
    4. Dunder attribute access via Attribute nodes (obj.__class__, obj.__dict__)
       — this catches sandbox escapes like ().__class__.__bases__[0].__subclasses__()
    5. Forbidden module names as bare Name references (os, sys, subprocess, etc.)

    Returns list of issues found (empty if safe).
    """
    issues: list[str] = []

    try:
        tree = ast.parse(code)
    except SyntaxError:
        issues.append("Code has syntax errors (cannot analyze safety)")
        return issues

    # Whitelisted dunder names that the sandbox legitimately uses
    _ALLOWED_DUNDERS = {"__name__", "__result__", "__inputs__"}

    for ast_node in ast.walk(tree):
        # ── 1. Import statements ──────────────────────────────────────────────
        if isinstance(ast_node, ast.Import):
            for alias in ast_node.names:
                top = alias.name.split(".")[0]
                if top in FORBIDDEN_MODULE_NAMES:
                    issues.append(f"Forbidden import: '{alias.name}'")
                else:
                    issues.append(
                        f"Import statement not allowed in sandbox: 'import {alias.name}'"
                    )

        elif isinstance(ast_node, ast.ImportFrom):
            module = ast_node.module or ""
            top = module.split(".")[0]
            if top in FORBIDDEN_MODULE_NAMES:
                issues.append(f"Forbidden import: 'from {module}'")
            else:
                issues.append(
                    f"Import statement not allowed in sandbox: 'from {module} import ...'"
                )

        # ── 2. Calls to forbidden builtins ────────────────────────────────────
        elif isinstance(ast_node, ast.Call):
            func = ast_node.func
            if isinstance(func, ast.Name) and func.id in FORBIDDEN_NAMES:
                issues.append(f"Forbidden function call: '{func.id}()'")
            elif isinstance(func, ast.Attribute) and func.attr in FORBIDDEN_NAMES:
                issues.append(f"Forbidden method call: '.{func.attr}()'")

        # ── 3. Dunder bare Name references ────────────────────────────────────
        elif isinstance(ast_node, ast.Name):
            name = ast_node.id
            if name.startswith("__") and name not in _ALLOWED_DUNDERS:
                issues.append(f"Suspicious dunder name access: '{name}'")
            elif name in FORBIDDEN_MODULE_NAMES:
                # Catches: os.getcwd(), sys.exit() where module used as a name
                issues.append(f"Forbidden module reference: '{name}'")

        # ── 4. Dunder attribute access (sandbox escape vectors) ───────────────
        elif isinstance(ast_node, ast.Attribute):
            attr = ast_node.attr
            if attr.startswith("__") and attr.endswith("__"):
                # Allow only a handful of safe dunders that appear in normal code
                _SAFE_DUNDER_ATTRS = {"__class__", "__dict__", "__doc__"} - {
                    # Actually block class/dict/doc too — they're escape vectors
                }
                issues.append(
                    f"Dunder attribute access not allowed: '.{attr}' "
                    f"(potential sandbox escape vector)"
                )

    return issues


def validate_edges_reference_existing_nodes(dag: GeneratedDAG) -> list[str]:
    """Check that all edge source/target reference existing node_ids."""
    errors: list[str] = []
    node_ids = {n.node_id for n in dag.nodes}

    for edge in dag.edges:
        if edge.source not in node_ids:
            errors.append(f"Edge source '{edge.source}' does not exist")
        if edge.target not in node_ids:
            errors.append(f"Edge target '{edge.target}' does not exist")

    return errors


def validate_input_references(dag: GeneratedDAG) -> list[str]:
    """Check that all node input references point to valid sources.

    Valid sources:
      - "dataset.<field>"
      - "prev_node.<node_id>.output"
      - Literal values (non-string, or strings that don't match patterns)
    """
    errors: list[str] = []
    node_ids = {n.node_id for n in dag.nodes}
    node_map = {n.node_id: n for n in dag.nodes}

    # Build upstream deps from edges
    upstream: dict[str, set[str]] = defaultdict(set)
    for edge in dag.edges:
        upstream[edge.target].add(edge.source)

    for node in dag.nodes:
        for param_name, ref in node.inputs.items():
            if not isinstance(ref, str):
                continue  # Literal value, skip

            if ref.startswith("dataset."):
                continue  # Dataset reference, validated at runtime

            if ref.startswith("prev_node."):
                parts = ref.split(".")
                if len(parts) < 3:
                    errors.append(
                        f"Node '{node.node_id}', input '{param_name}': "
                        f"malformed reference '{ref}' (expected 'prev_node.<id>.output')"
                    )
                    continue

                ref_node_id = parts[1]
                if ref_node_id not in node_ids:
                    errors.append(
                        f"Node '{node.node_id}', input '{param_name}': "
                        f"references non-existent node '{ref_node_id}'"
                    )
                elif ref_node_id not in upstream.get(node.node_id, set()):
                    errors.append(
                        f"Node '{node.node_id}', input '{param_name}': "
                        f"references '{ref_node_id}' but there's no edge from it"
                    )

    return errors


def resolve_input_reference(
    ref: Any,
    dataset: dict[str, Any],
    node_outputs: dict[str, Any],
) -> Any:
    """Resolve a string reference to an actual value.

    Handles:
      - "dataset.<field>" -> dataset[field]
      - "prev_node.<node_id>.output" -> node_outputs[node_id]
      - Non-string values returned as-is (literals)
    """
    if not isinstance(ref, str):
        return ref

    if ref.startswith("dataset."):
        field = ref[len("dataset."):]
        # Support nested access with dots
        obj = dataset
        for key in field.split("."):
            if isinstance(obj, dict):
                obj = obj[key]
            elif isinstance(obj, (list, tuple)):
                obj = obj[int(key)]
            else:
                raise KeyError(f"Cannot access '{key}' on {type(obj)}")
        return obj

    if ref.startswith("prev_node."):
        parts = ref.split(".")
        node_id = parts[1]
        if node_id not in node_outputs:
            raise KeyError(
                f"Node '{node_id}' output not found. "
                f"Available: {list(node_outputs.keys())}"
            )
        return node_outputs[node_id]

    # Treat as a literal string
    return ref


def run_all_structural_validations(dag: GeneratedDAG) -> list[str]:
    """Run all structural (non-LLM) validations on a DAG.

    Returns a combined list of all errors found.
    """
    errors: list[str] = []

    # 1. Edge references
    errors.extend(validate_edges_reference_existing_nodes(dag))

    # 2. Acyclicity
    is_acyclic, cycle_err = validate_acyclicity(dag)
    if not is_acyclic:
        errors.append(f"DAG contains a cycle: {cycle_err}")

    # 3. Layer assignment
    errors.extend(validate_layer_assignment(dag))

    # 4. Connectivity
    errors.extend(validate_connectivity(dag))

    # 5. Input references
    errors.extend(validate_input_references(dag))

    # 6. Per-node code validation
    for node in dag.nodes:
        is_valid, syntax_err = validate_code_syntax(node.code)
        if not is_valid:
            errors.append(f"Node '{node.node_id}': {syntax_err}")
        else:
            safety_issues = validate_code_safety(node.code)
            for issue in safety_issues:
                errors.append(f"Node '{node.node_id}': {issue}")

    return errors

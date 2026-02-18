"""Tests for DAG utility functions."""

from __future__ import annotations

import pytest

from eval_dag.state.models import DAGEdge, DAGNodeSpec, GeneratedDAG
from eval_dag.utils.dag_utils import (
    extract_layers,
    resolve_input_reference,
    run_all_structural_validations,
    validate_acyclicity,
    validate_code_safety,
    validate_code_syntax,
    validate_connectivity,
    validate_layer_assignment,
)


def _make_node(node_id, layer, inputs=None, code=None):
    return DAGNodeSpec(
        node_id=node_id,
        operation=f"op for {node_id}",
        function_name=f"fn_{node_id}",
        inputs=inputs or {},
        expected_output_type="float",
        layer=layer,
        code=code or f"def fn_{node_id}():\n    return 1.0",
    )


def _make_dag(nodes, edges, final_answer_node="step_2"):
    return GeneratedDAG(
        question_id="q_01",
        nodes=nodes,
        edges=edges,
        final_answer_node=final_answer_node,
        description="test dag",
    )


class TestExtractLayers:
    def test_single_layer(self):
        dag = _make_dag([_make_node("n1", 0), _make_node("n2", 0)], [], "n1")
        layers = extract_layers(dag)
        assert len(layers) == 1
        assert {n.node_id for n in layers[0]} == {"n1", "n2"}

    def test_multiple_layers(self):
        dag = _make_dag(
            [_make_node("n0", 0), _make_node("n1", 1), _make_node("n2", 2)],
            [DAGEdge(source="n0", target="n1"), DAGEdge(source="n1", target="n2")],
            "n2",
        )
        layers = extract_layers(dag)
        assert len(layers) == 3
        assert layers[0][0].node_id == "n0"
        assert layers[1][0].node_id == "n1"
        assert layers[2][0].node_id == "n2"

    def test_empty_dag(self):
        dag = _make_dag([], [], "")
        assert extract_layers(dag) == []


class TestValidateAcyclicity:
    def test_acyclic(self):
        dag = _make_dag(
            [_make_node("a", 0), _make_node("b", 1)],
            [DAGEdge(source="a", target="b")],
            "b",
        )
        ok, err = validate_acyclicity(dag)
        assert ok
        assert err is None

    def test_cyclic(self):
        dag = _make_dag(
            [_make_node("a", 0), _make_node("b", 1)],
            [DAGEdge(source="a", target="b"), DAGEdge(source="b", target="a")],
            "b",
        )
        ok, err = validate_acyclicity(dag)
        assert not ok
        assert err is not None


class TestValidateLayerAssignment:
    def test_valid(self):
        dag = _make_dag(
            [_make_node("a", 0), _make_node("b", 1)],
            [DAGEdge(source="a", target="b")],
            "b",
        )
        assert validate_layer_assignment(dag) == []

    def test_same_layer_dep(self):
        dag = _make_dag(
            [_make_node("a", 0), _make_node("b", 0)],
            [DAGEdge(source="a", target="b")],
            "b",
        )
        errors = validate_layer_assignment(dag)
        assert any("earlier layer" in e for e in errors)


class TestValidateConnectivity:
    def test_valid(self):
        dag = _make_dag(
            [_make_node("a", 0), _make_node("b", 1)],
            [DAGEdge(source="a", target="b")],
            "b",
        )
        assert validate_connectivity(dag) == []

    def test_missing_final_node(self):
        dag = _make_dag([_make_node("a", 0)], [], "missing")
        errors = validate_connectivity(dag)
        assert any("does not exist" in e for e in errors)

    def test_orphaned_node(self):
        dag = _make_dag(
            [_make_node("a", 0), _make_node("b", 1), _make_node("orphan", 0)],
            [DAGEdge(source="a", target="b")],
            "b",
        )
        errors = validate_connectivity(dag)
        assert any("orphan" in e.lower() for e in errors)


class TestValidateCodeSyntax:
    def test_valid(self):
        ok, err = validate_code_syntax("def f():\n    return 1")
        assert ok
        assert err is None

    def test_invalid(self):
        ok, err = validate_code_syntax("def f(:\n    pass")
        assert not ok
        assert err is not None


class TestValidateCodeSafety:
    def test_safe_code(self):
        code = "def f(data):\n    return sum(data) / len(data)"
        assert validate_code_safety(code) == []

    def test_import_forbidden(self):
        code = "import os\ndef f():\n    return os.getcwd()"
        issues = validate_code_safety(code)
        assert any("import" in i.lower() for i in issues)

    def test_eval_forbidden(self):
        code = "def f(x):\n    return eval(x)"
        issues = validate_code_safety(code)
        assert any("eval" in i for i in issues)


class TestResolveInputReference:
    def test_dataset_ref(self):
        val = resolve_input_reference("dataset.prices", {"prices": [1, 2, 3]}, {})
        assert val == [1, 2, 3]

    def test_nested_dataset_ref(self):
        val = resolve_input_reference(
            "dataset.data.items",
            {"data": {"items": [10, 20]}},
            {},
        )
        assert val == [10, 20]

    def test_prev_node_ref(self):
        val = resolve_input_reference(
            "prev_node.step_1.output",
            {},
            {"step_1": 42},
        )
        assert val == 42

    def test_literal_int(self):
        val = resolve_input_reference(5, {}, {})
        assert val == 5

    def test_literal_string(self):
        val = resolve_input_reference("just a string", {}, {})
        assert val == "just a string"

    def test_missing_prev_node_raises(self):
        with pytest.raises(KeyError):
            resolve_input_reference("prev_node.missing.output", {}, {})


class TestRunAllStructuralValidations:
    def test_clean_dag(self):
        code_a = "def fn_a(x):\n    return x * 2"
        node_a = _make_node("a", 0, inputs={"x": "dataset.vals"}, code=code_a)
        code_b = "def fn_b(y):\n    return y + 1"
        node_b = _make_node("b", 1, inputs={"y": "prev_node.a.output"}, code=code_b)
        dag = _make_dag([node_a, node_b], [DAGEdge(source="a", target="b")], "b")
        assert run_all_structural_validations(dag) == []

    def test_dag_with_unsafe_code(self):
        code = "import os\ndef fn_bad():\n    return os.getcwd()"
        node = _make_node("bad", 0, code=code)
        dag = _make_dag([node], [], "bad")
        errors = run_all_structural_validations(dag)
        assert any("import" in e.lower() for e in errors)

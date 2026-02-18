"""Tests for the sandbox execution engine."""

from __future__ import annotations

import pytest

from eval_dag.sandbox.runner import execute_approved_dag, sandbox_execute_node
from eval_dag.state.models import DAGEdge, DAGNodeSpec, GeneratedDAG


def _make_node(node_id, layer, function_name, code, inputs=None, expected_output_type="float"):
    return DAGNodeSpec(
        node_id=node_id,
        operation=f"op {node_id}",
        function_name=function_name,
        inputs=inputs or {},
        expected_output_type=expected_output_type,
        layer=layer,
        code=code,
    )


class TestSandboxExecuteNode:
    def test_simple_addition(self):
        node = _make_node(
            "add", 0, "add_vals",
            code="def add_vals(a, b):\n    return a + b",
        )
        result = sandbox_execute_node(node, {"a": 3, "b": 4})
        assert result.success
        assert result.output == 7

    def test_list_sum(self):
        node = _make_node(
            "sumnode", 0, "sum_list",
            code="def sum_list(values):\n    return sum(values)",
            expected_output_type="float",
        )
        result = sandbox_execute_node(node, {"values": [1, 2, 3, 4, 5]})
        assert result.success
        assert result.output == 15

    def test_uses_math_module(self):
        node = _make_node(
            "sqrt", 0, "compute_sqrt",
            code="def compute_sqrt(x):\n    return math.sqrt(x)",
        )
        result = sandbox_execute_node(node, {"x": 16.0})
        assert result.success
        assert result.output == 4.0

    def test_uses_statistics_module(self):
        node = _make_node(
            "mean", 0, "compute_mean",
            code="def compute_mean(data):\n    return statistics.mean(data)",
        )
        result = sandbox_execute_node(node, {"data": [10, 20, 30]})
        assert result.success
        assert result.output == 20

    def test_runtime_error_returns_failure(self):
        node = _make_node(
            "div", 0, "divide",
            code="def divide(a, b):\n    return a / b",
        )
        result = sandbox_execute_node(node, {"a": 1, "b": 0})
        assert not result.success
        assert "ZeroDivisionError" in result.error

    def test_forbidden_import_fails(self):
        node = _make_node(
            "bad", 0, "do_bad",
            code="import os\ndef do_bad():\n    return os.getcwd()",
        )
        result = sandbox_execute_node(node, {})
        assert not result.success

    def test_dict_output(self):
        node = _make_node(
            "grp", 0, "group_by_key",
            code=(
                "def group_by_key(items):\n"
                "    out = {}\n"
                "    for item in items:\n"
                "        k = item['cat']\n"
                "        out.setdefault(k, []).append(item['val'])\n"
                "    return out"
            ),
            expected_output_type="dict",
        )
        data = [{"cat": "a", "val": 1}, {"cat": "b", "val": 2}, {"cat": "a", "val": 3}]
        result = sandbox_execute_node(node, {"items": data})
        assert result.success
        assert result.output == {"a": [1, 3], "b": [2]}


class TestExecuteApprovedDag:
    def _build_two_node_dag(self):
        """A simple two-node DAG: sum -> divide_by_count."""
        node_sum = _make_node(
            "sum_node", 0, "compute_sum",
            code="def compute_sum(values):\n    return sum(values)",
            inputs={"values": "dataset.numbers"},
        )
        node_avg = _make_node(
            "avg_node", 1, "compute_avg",
            code="def compute_avg(total, count):\n    return total / count",
            inputs={"total": "prev_node.sum_node.output", "count": "dataset.count"},
        )
        dag = GeneratedDAG(
            question_id="q_test",
            nodes=[node_sum, node_avg],
            edges=[DAGEdge(source="sum_node", target="avg_node")],
            final_answer_node="avg_node",
            description="Compute average",
        )
        return dag

    def test_successful_execution(self):
        dag = self._build_two_node_dag()
        dataset = {"numbers": [10, 20, 30], "count": 3}
        result = execute_approved_dag(dag, dataset)
        assert result.success
        assert result.final_answer == 20.0
        assert "sum_node" in result.node_outputs
        assert "avg_node" in result.node_outputs
        assert result.execution_time_ms >= 0

    def test_node_failure_propagates(self):
        node_bad = _make_node(
            "bad", 0, "do_fail",
            code="def do_fail(x):\n    return x / 0",
            inputs={"x": "dataset.val"},
        )
        dag = GeneratedDAG(
            question_id="q_fail",
            nodes=[node_bad],
            edges=[],
            final_answer_node="bad",
            description="Will fail",
        )
        result = execute_approved_dag(dag, {"val": 5})
        assert not result.success
        assert "bad" in result.error
        assert "ZeroDivisionError" in result.error

    def test_input_resolution_failure(self):
        node = _make_node(
            "n", 0, "fn",
            code="def fn(x):\n    return x",
            inputs={"x": "dataset.nonexistent_key"},
        )
        dag = GeneratedDAG(
            question_id="q_miss",
            nodes=[node],
            edges=[],
            final_answer_node="n",
            description="Missing key",
        )
        result = execute_approved_dag(dag, {"other": 1})
        assert not result.success
        assert "Input resolution failed" in result.error

    def test_chained_three_nodes(self):
        n1 = _make_node(
            "n1", 0, "fn1",
            code="def fn1(vals):\n    return [v * 2 for v in vals]",
            inputs={"vals": "dataset.data"},
            expected_output_type="list",
        )
        n2 = _make_node(
            "n2", 1, "fn2",
            code="def fn2(doubled):\n    return sum(doubled)",
            inputs={"doubled": "prev_node.n1.output"},
        )
        n3 = _make_node(
            "n3", 2, "fn3",
            code="def fn3(total):\n    return round(total, 2)",
            inputs={"total": "prev_node.n2.output"},
        )
        dag = GeneratedDAG(
            question_id="q_chain",
            nodes=[n1, n2, n3],
            edges=[DAGEdge(source="n1", target="n2"), DAGEdge(source="n2", target="n3")],
            final_answer_node="n3",
            description="chain test",
        )
        result = execute_approved_dag(dag, {"data": [1, 2, 3]})
        assert result.success
        assert result.final_answer == 12

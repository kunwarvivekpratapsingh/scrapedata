# eval-dag — LLM-Powered Dataset Evaluation System

A fully automated evaluation pipeline that takes any structured dataset, generates analytical questions ranked by difficulty, builds Python execution graphs (DAGs) to answer each question, validates them through a critic feedback loop, and executes them in a sandboxed environment — producing a rich HTML report with pass rates, execution traces, and full audit trails.

---

## Table of Contents

1. [How It Works — High-Level Flow](#1-how-it-works--high-level-flow)
2. [Architecture Overview](#2-architecture-overview)
3. [Project Structure](#3-project-structure)
4. [Data Models](#4-data-models)
5. [LangGraph State Schemas](#5-langgraph-state-schemas)
6. [Graph Architecture](#6-graph-architecture)
   - [Orchestrator Graph](#orchestrator-graph)
   - [Critic Loop Subgraph](#critic-loop-subgraph)
7. [Node Reference — Every Node in Detail](#7-node-reference--every-node-in-detail)
   - [ingest_data_node](#ingest_data_node)
   - [generate_questions_node](#generate_questions_node)
   - [fan_out_node](#fan_out_node)
   - [process_question_node](#process_question_node)
   - [build_dag_node](#build_dag_node)
   - [validate_dag_node (Critic)](#validate_dag_node-critic)
   - [execute_dag_node](#execute_dag_node)
   - [collect_results_node](#collect_results_node)
8. [Prompt Engineering](#8-prompt-engineering)
9. [Sandbox Execution Engine](#9-sandbox-execution-engine)
10. [DAG Utilities & Validators](#10-dag-utilities--validators)
11. [Dataset & Metadata Format](#11-dataset--metadata-format)
12. [Output Format](#12-output-format)
13. [Quick Start](#13-quick-start)
14. [Extending the System](#14-extending-the-system)
15. [Design Decisions & Trade-offs](#15-design-decisions--trade-offs)

---

## 1. How It Works — High-Level Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         ORCHESTRATOR GRAPH                              │
│                                                                         │
│  dataset.json ──► ingest_data ──► generate_questions ──► fan_out       │
│  metadata.json         │                  │                  │          │
│                        ▼                  ▼                  ▼          │
│                   (validate)        10 Questions        Send() × 10     │
│                                                              │          │
│                              ┌───────────────────────────────┘          │
│                              ▼  (runs in parallel per question)         │
│                    ┌─────────────────────────┐                          │
│                    │    CRITIC LOOP SUBGRAPH  │                          │
│                    │                         │                          │
│                    │  build_dag ──► validate  │                          │
│                    │      ▲            │      │                          │
│                    │      │   REJECT   │      │                          │
│                    │      └───(< 3x)───┘      │                          │
│                    │              │           │                          │
│                    │           APPROVE        │                          │
│                    │              │           │                          │
│                    │         execute_dag      │                          │
│                    └─────────────────────────┘                          │
│                              │                                          │
│                              ▼                                          │
│                       collect_results ──► eval_results.json             │
│                              │                                          │
│                              ▼                                          │
│                       generate_report ──► eval_report.html              │
└─────────────────────────────────────────────────────────────────────────┘
```

**In plain English:**

1. You provide a **dataset** (structured JSON) and its **metadata** (field descriptions, types, notes)
2. An LLM **generates 10 questions** about the dataset, ranked from easy to hard
3. For each question, an LLM **designs a Python DAG** — a graph of executable steps to compute the answer
4. A **critic** validates the DAG (structurally and semantically), rejecting and requesting fixes up to 3 times
5. Once approved, the DAG **executes in a sandbox** with restricted Python builtins
6. All results are **aggregated** into a JSON report and a visual HTML page

---

## 2. Architecture Overview

```
eval-dag/
├── src/eval_dag/
│   ├── state/          # Pydantic models + LangGraph state schemas
│   ├── graphs/         # LangGraph graph definitions (orchestrator + critic loop)
│   ├── nodes/          # Individual LangGraph node functions
│   ├── prompts/        # LLM system prompts + user prompt builders
│   ├── sandbox/        # Restricted Python execution environment
│   └── utils/          # DAG structural validators + input resolution
├── scripts/
│   ├── run_eval.py         # CLI entry point
│   ├── prepare_dataset.py  # CSV → data.json + metadata.json
│   └── generate_report.py  # eval_results.json → HTML report
├── dataset/
│   ├── metadata.json        # Dataset schema with per-field annotations
│   └── data.json            # Pre-aggregated dataset (generated)
└── tests/
    ├── test_dag_utils.py
    └── test_sandbox.py
```

**Technology stack:**
| Layer | Technology |
|---|---|
| Orchestration | [LangGraph](https://github.com/langchain-ai/langgraph) (StateGraph + Send API) |
| LLM | OpenAI GPT-4o via LangChain |
| Data models | Pydantic v2 |
| Sandbox | Custom restricted exec + AST safety analysis |
| Reporting | Pure Python HTML/SVG generation (no external deps) |
| Python | 3.11+ |

---

## 3. Project Structure

```
src/eval_dag/
│
├── state/
│   ├── models.py      # Core domain models: Question, DAGNodeSpec, GeneratedDAG,
│   │                  #   CriticFeedback, ExecutionResult, LayerValidation
│   └── schemas.py     # LangGraph TypedDicts: OrchestratorState, CriticLoopState
│
├── graphs/
│   ├── orchestrator.py  # Outer graph: ingest → questions → fan-out → collect
│   └── critic_loop.py   # Inner subgraph: build → validate → (loop or execute)
│
├── nodes/
│   ├── question_generator.py  # Node 1: LLM generates 10 ranked questions
│   ├── dag_builder.py         # Node 2: LLM designs Python execution DAG
│   ├── critic.py              # Node 3: Validates DAG (structural + semantic)
│   ├── executor.py            # Node 4: Runs approved DAG in sandbox
│   └── result_collector.py   # Node 5: Aggregates all results into final report
│
├── prompts/
│   ├── question_gen.py  # System prompt + user prompt for question generation
│   ├── dag_gen.py       # System prompt + user prompt for DAG generation
│   └── critic.py        # System prompt + user prompt for per-layer validation
│
├── sandbox/
│   ├── permissions.py   # Allowlisted builtins and safe modules
│   └── runner.py        # sandbox_execute_node() + execute_approved_dag()
│
└── utils/
    ├── dag_utils.py       # Layer extraction, all structural validators, input resolver
    └── serialization.py   # JSON serialization helpers
```

---

## 4. Data Models

**File:** `src/eval_dag/state/models.py`

All models are Pydantic v2 classes. They flow through LangGraph state and are serialized to JSON in the final report.

### `Question`
Represents a single evaluation question generated by the LLM.

```python
class Question(BaseModel):
    id: str                        # "q_01" through "q_10"
    text: str                      # The actual question text
    difficulty_rank: int           # 1 (easiest) to 10 (hardest)
    difficulty_level: DifficultyLevel  # EASY (1-3), MEDIUM (4-7), HARD (8-10)
    reasoning: str                 # Why this question has this difficulty
    relevant_data_keys: list[str]  # Which dataset keys are needed to answer it
```

### `DAGNodeSpec`
One executable step in a computation graph.

```python
class DAGNodeSpec(BaseModel):
    node_id: str               # Unique ID, e.g. "step_1a"
    operation: str             # Human-readable description of what this step does
    function_name: str         # Python function name (must match def in code)
    inputs: dict[str, str]    # Maps param name → reference ("dataset.X" or "prev_node.Y.output")
    expected_output_type: str  # e.g. "dict[str, float]", "float", "list[tuple]"
    layer: int                 # Execution layer (0 = no deps, N depends on layers < N)
    code: str                  # Complete Python function definition
```

### `GeneratedDAG`
The complete computation graph for one question.

```python
class GeneratedDAG(BaseModel):
    question_id: str           # Links back to the Question
    description: str           # Overall approach explanation
    nodes: list[DAGNodeSpec]   # All computation steps
    edges: list[DAGEdge]       # DAGEdge(source, target) — directed dependencies
    final_answer_node: str     # node_id whose output IS the answer
```

### `CriticFeedback`
The critic's verdict after validating a DAG.

```python
class CriticFeedback(BaseModel):
    is_approved: bool                       # True = execute, False = rebuild
    overall_reasoning: str                  # Summary of what's right/wrong
    layer_validations: list[LayerValidation]  # Per-layer results
    specific_errors: list[str]             # Actionable error messages
    suggestions: list[str]                 # Hints for the next rebuild attempt
```

### `ExecutionResult`
The outcome of running an approved DAG in the sandbox.

```python
class ExecutionResult(BaseModel):
    question_id: str
    success: bool
    final_answer: Any | None      # The computed answer value
    node_outputs: dict[str, Any]  # Intermediate outputs keyed by node_id
    error: str | None             # Exception message if failed
    execution_time_ms: float      # Wall-clock time for full DAG execution
```

---

## 5. LangGraph State Schemas

**File:** `src/eval_dag/state/schemas.py`

LangGraph passes state between nodes as typed dictionaries. Fields with `operator.add` reducers are **parallel-safe** — multiple concurrent nodes can write to them without overwriting each other.

### `OrchestratorState`
The shared state of the outer (orchestrator) graph.

```python
class OrchestratorState(TypedDict):
    # ── Inputs (set once at pipeline start) ──
    dataset: dict[str, Any]         # The loaded dataset JSON
    metadata: dict[str, Any]        # The loaded metadata JSON

    # ── Intermediate (written by one node, read by next) ──
    questions: list[Question]        # Generated by question_generator, consumed by fan_out

    # ── Accumulating (operator.add reducer — safe for parallel writes) ──
    completed_results: Annotated[list[ExecutionResult], operator.add]
    failed_questions: Annotated[list[str], operator.add]       # question_ids that failed
    question_traces: Annotated[list[dict], operator.add]       # Full audit trail per question

    # ── Output (written by collect_results) ──
    final_report: dict[str, Any]    # The aggregated JSON report

    # ── Tracing ──
    messages: Annotated[list[BaseMessage], operator.add]
```

### `CriticLoopState`
The isolated state of each question's critic loop subgraph. One instance per question, created by `fan_out`.

```python
class CriticLoopState(TypedDict):
    # ── Read-only context (copied from OrchestratorState) ──
    question: Question
    dataset: dict[str, Any]
    metadata: dict[str, Any]

    # ── Mutable within the loop ──
    current_dag: GeneratedDAG | None        # Latest generated DAG
    current_feedback: CriticFeedback | None # Critic's verdict on current_dag
    iteration_count: int                    # How many build+validate cycles so far
    is_approved: bool                       # True = DAG passed critic

    # ── Accumulating (full history of all iterations) ──
    dag_history: Annotated[list[dict], operator.add]  # [{iteration, dag, feedback}]

    # ── Terminal result ──
    execution_result: ExecutionResult | None  # Set after sandbox execution

    # ── Tracing ──
    messages: Annotated[list[BaseMessage], operator.add]
```

---

## 6. Graph Architecture

### Orchestrator Graph

**File:** `src/eval_dag/graphs/orchestrator.py`

```
ingest_data_node
      │
      ▼
generate_questions_node
      │
      ▼
fan_out_node  ──── Send("process_question", state_for_q01) ──┐
                ── Send("process_question", state_for_q02) ──┤
                ── Send("process_question", state_for_q03) ──┤  (parallel)
                ...                                           │
                ── Send("process_question", state_for_q10) ──┘
                                                             │
                              process_question_node ◄────────┘
                              (runs critic_loop subgraph)
                                          │
                                          ▼
                                 collect_results_node
                                          │
                                          ▼
                                       END
```

The `fan_out_node` uses LangGraph's `Send()` API to dispatch all 10 questions **in parallel**. Each question gets its own isolated `CriticLoopState`, and results are merged back into `OrchestratorState` via the `operator.add` reducers.

---

### Critic Loop Subgraph

**File:** `src/eval_dag/graphs/critic_loop.py`

```
build_dag_node
      │
      ▼
validate_dag_node
      │
      ├─── APPROVED ──────────────► execute_dag_node ──► END
      │
      ├─── REJECTED (iter < 3) ──► build_dag_node  (loop back)
      │
      └─── REJECTED (iter >= 3) ─► END  (exhausted — question marked as failed)
```

The routing function `_route_after_validation()` reads `is_approved` and `iteration_count` from state:

```python
def _route_after_validation(state: CriticLoopState) -> str:
    if state["is_approved"]:
        return "execute_dag"
    elif state["iteration_count"] >= MAX_ITERATIONS:  # MAX_ITERATIONS = 3
        return END
    else:
        return "build_dag"  # loop back for a rebuild
```

---

## 7. Node Reference — Every Node in Detail

### `ingest_data_node`

**File:** `src/eval_dag/graphs/orchestrator.py`
**Role:** Pipeline gatekeeper. Validates that required inputs are present before the pipeline starts.

**What it does:**
- Checks that `dataset` is a non-empty dict
- Checks that `metadata` is a non-empty dict
- Logs a warning if metadata is missing (pipeline continues with empty metadata)
- Returns state unchanged — purely a validation gate

**State reads:** `dataset`, `metadata`
**State writes:** `messages` (adds an informational AIMessage)

**How to extend:** Add dataset schema validation here (e.g., check for required keys like `transactions`, raise `ValueError` if missing).

---

### `generate_questions_node`

**File:** `src/eval_dag/nodes/question_generator.py`
**Role:** Uses an LLM to generate 10 evaluation questions ranked by difficulty.

**What it does:**
1. Builds a prompt containing: full metadata JSON + summarized dataset structure (key names, types, sample values)
2. Calls GPT-4o with `response_format: json_object` and `temperature=0.3`
3. Parses the JSON response into a list of `Question` objects
4. Sorts questions by `difficulty_rank` (1 → 10)
5. Returns `{"questions": [...]}`

**LLM config:** `gpt-4o`, temperature=0.3, json_object response format

**State reads:** `dataset`, `metadata`
**State writes:** `questions`, `messages`

**Prompt system:** `QUESTION_GEN_SYSTEM` (in `prompts/question_gen.py`)
- Instructs the LLM to generate exactly 10 questions
- Enforces difficulty distribution: ranks 1-3 = easy, 4-7 = medium, 8-10 = hard
- Tells it to PREFER aggregate/statistical questions and AVOID PII extraction
- Tells it to use pre-aggregated keys (`category_stats`, `state_stats`, etc.) for global figures

**How to extend:**
- Change `temperature` to get more/less creative questions
- Change `10` to any N for a different number of questions
- Add domain-specific question guidelines to `QUESTION_GEN_SYSTEM`
- Swap GPT-4o for a different model in `_get_llm()`

---

### `fan_out_node`

**File:** `src/eval_dag/graphs/orchestrator.py`
**Role:** Dispatches one independent critic-loop subgraph invocation per question, in parallel.

**What it does:**
```python
def fan_out_node(state: OrchestratorState) -> list[Send]:
    return [
        Send("process_question", {
            "question": q,
            "dataset": state["dataset"],
            "metadata": state["metadata"],
            "current_dag": None,
            "current_feedback": None,
            "iteration_count": 0,
            "is_approved": False,
            "dag_history": [],
            "execution_result": None,
            "messages": [],
        })
        for q in state["questions"]
    ]
```

Each `Send()` creates an independent `CriticLoopState` with fresh mutable fields but shared read-only context (`dataset`, `metadata`, `question`).

**Why `operator.add` matters here:** Since all 10 `process_question` invocations run concurrently and all write to `completed_results`, `failed_questions`, and `question_traces` in `OrchestratorState`, those fields use `operator.add` as their reducer. LangGraph merges the lists from all parallel branches safely.

**State reads:** `questions`, `dataset`, `metadata`
**State writes:** (none directly — creates new CriticLoopState instances via Send)

**How to extend:**
- Add a `question_filter` to skip questions above/below a difficulty threshold
- Limit parallelism by batching questions (e.g., `Send` 5 at a time)

---

### `process_question_node`

**File:** `src/eval_dag/graphs/orchestrator.py`
**Role:** Runs the full critic-loop subgraph for one question and extracts its result into the orchestrator state.

**What it does:**
1. Invokes the `CriticLoopSubgraph` with the question's `CriticLoopState`
2. Extracts `execution_result` from the final subgraph state
3. Classifies as success or failure
4. Builds a `question_trace` dict (full audit trail: all iterations, DAG code, critic feedback, conversation log)
5. Returns updates to `completed_results`, `failed_questions`, `question_traces`, `messages`

**The `question_trace` structure:**
```json
{
  "question_id": "q_05",
  "question_text": "...",
  "difficulty": "medium",
  "difficulty_rank": 5,
  "total_iterations": 2,
  "final_answer": 42.7,
  "success": true,
  "execution_error": null,
  "execution_time_ms": 12.4,
  "node_outputs": { "step_1a": {...}, "step_2a": 42.7 },
  "iterations": [
    {
      "iteration": 1,
      "dag": { "nodes": [...], "edges": [...] },
      "critic_feedback": { "is_approved": false, "specific_errors": [...] }
    },
    {
      "iteration": 2,
      "dag": { "nodes": [...], "edges": [...] },
      "critic_feedback": { "is_approved": true }
    }
  ],
  "conversation_log": [
    {"role": "dag_builder", "content": "[DAGBuilder] Iteration 1 ..."},
    {"role": "critic", "content": "[Critic] Iteration 1: REJECTED — 2 issue(s)"},
    {"role": "dag_builder", "content": "[DAGBuilder] Iteration 2 ..."},
    {"role": "critic", "content": "[Critic] Iteration 2: APPROVED — 0 issue(s)"},
    {"role": "executor", "content": "[Executor] q_05: SUCCESS — 12.4ms"}
  ]
}
```

**State reads:** (receives full `CriticLoopState`)
**State writes:** `completed_results`, `failed_questions`, `question_traces`, `messages`

---

### `build_dag_node`

**File:** `src/eval_dag/nodes/dag_builder.py`
**Role:** LLM designs a Python execution DAG to answer the question. On retries, incorporates critic feedback.

**What it does:**

*First iteration (no feedback):*
1. Builds a prompt with: question text, difficulty, relevant data keys, full dataset schema
2. Calls GPT-4o with json_object format
3. Parses JSON → `GeneratedDAG` (nodes, edges, final_answer_node)

*Subsequent iterations (with feedback):*
1. Builds the same prompt PLUS a detailed feedback section:
   - Overall rejection reasoning
   - Per-layer issues
   - Specific error messages
   - Suggestions for the fix
   - The previous DAG in full (so the LLM can see what to improve)
2. Instructs the LLM to generate a **complete new DAG** (not a patch)

**Rate limit handling:**
```python
for attempt in range(3):
    try:
        response = llm.invoke(messages)
        dag = _parse_dag(response.content, question.id)
        break
    except Exception as e:
        if _is_rate_limit_error(e) and attempt < 2:
            time.sleep(5 * (2 ** attempt))  # 5s, 10s
            continue
        break  # non-rate-limit or final attempt
```

If all retries fail → returns an **empty DAG** so the critic can handle it gracefully.

**LLM config:** `gpt-4o`, temperature=0.2 (low for deterministic code generation), json_object

**State reads:** `question`, `dataset`, `metadata`, `current_feedback`, `current_dag`, `iteration_count`
**State writes:** `current_dag`, `iteration_count`, `messages`

**How to extend:**
- Change temperature: lower (0.0) for more deterministic code, higher (0.5) for creative approaches
- Add a "code style" section to `DAG_GEN_SYSTEM` (e.g., "prefer list comprehensions over loops")
- Swap to a different model for cost savings (gpt-4o-mini) or quality (o1)
- Add few-shot examples of good DAGs to `DAG_GEN_SYSTEM`

---

### `validate_dag_node` (Critic)

**File:** `src/eval_dag/nodes/critic.py`
**Role:** Two-phase validator. First checks structure deterministically, then uses an LLM to validate logic layer by layer.

**Phase 1 — Structural Validation (deterministic, no LLM):**

Runs all checks in `run_all_structural_validations()`:
- `validate_edges_reference_existing_nodes` — every edge's source/target exists
- `validate_layer_assignment` — a node's dependencies must be in strictly earlier layers
- `validate_acyclicity` — no cycles using `graphlib.TopologicalSorter`
- `validate_connectivity` — final_answer_node is reachable; no orphaned nodes
- `validate_input_references` — input refs use valid `dataset.X` or `prev_node.X.output` patterns
- `validate_code_syntax` — `ast.parse()` on every node's code
- `validate_code_safety` — AST walk for forbidden imports, builtins, dunder access

If **critical errors** are found (empty DAG, cycles, missing final node) → skip Phase 2 and return immediately with rejection.

**Phase 2 — Semantic Validation (LLM-based, layer by layer):**

For each layer (group of nodes at the same depth):
1. Builds a prompt with: the question, the full dataset schema (including EXACT field names), all previously validated layers, the nodes in THIS layer with their code
2. Calls GPT-4o to check:
   - Logical correctness of each step
   - Code correctness (will it produce the right output?)
   - Type compatibility with upstream/downstream nodes
   - Relevance (does this step contribute to the answer?)
   - Edge cases (division by zero, missing keys, empty lists)
   - **Field name correctness** (does it use only documented field names?)
3. Collects issues across all node assessments

**Rate limit handling (approve on exhaustion):**
```python
for attempt in range(3):
    try:
        response = llm.invoke(messages)
        result = _parse_critic_response(response.content)
        break
    except Exception as e:
        if _is_rate_limit_error(e) and attempt < 2:
            time.sleep(5 * (2 ** attempt))
            continue
        elif _is_rate_limit_error(e):
            # Rate limits = infrastructure failure, not DAG failure
            # Approve this layer rather than penalising a potentially correct DAG
            return LayerValidation(is_valid=True, issues=[])
        else:
            return LayerValidation(is_valid=False, issues=[f"Validation error: {e}"])
```

**Final verdict:**
- `is_approved = True` if zero issues across all layers
- Returns `CriticFeedback` with full per-layer breakdown

**LLM config:** `gpt-4o`, temperature=0.0 (fully deterministic for consistent reviews)

**State reads:** `current_dag`, `question`, `dataset`, `metadata`, `iteration_count`
**State writes:** `current_feedback`, `is_approved`, `dag_history`, `messages`

**How to extend:**
- Add new structural validators in `dag_utils.py` and register them in `run_all_structural_validations()`
- Add new semantic checks to `CRITIC_SYSTEM` (e.g., "check for off-by-one errors in date ranges")
- Lower `temperature` is recommended for the critic — keep it at 0.0
- To allow more iterations before giving up, increase `MAX_ITERATIONS` in `critic_loop.py`

---

### `execute_dag_node`

**File:** `src/eval_dag/nodes/executor.py`
**Role:** Executes an approved DAG in the sandboxed Python environment.

**What it does:**
1. Reads the approved `current_dag` from state
2. Calls `execute_approved_dag(dag, dataset)` from `sandbox/runner.py`
3. Returns the `ExecutionResult` with success flag, final answer, node outputs, error message, timing

**State reads:** `current_dag`, `dataset`, `question`
**State writes:** `execution_result`, `messages`

**How to extend:** Add pre/post execution hooks here (e.g., log to LangSmith, cache results).

---

### `collect_results_node`

**File:** `src/eval_dag/nodes/result_collector.py`
**Role:** Aggregates all question results into the final report JSON.

**What it does:**
1. Collects `completed_results` (successful executions) and `failed_questions` (question IDs that exhausted the critic loop)
2. Computes per-difficulty breakdown (easy/medium/hard: pass count, fail count, pass rate)
3. Builds `detailed_results` — one summary row per question (question text, answer, pass/fail, time)
4. Builds `failure_analysis` — details on all failures with error messages
5. Combines `question_traces` — full per-question audit trails sorted by difficulty rank
6. Returns `final_report` dict

**State reads:** `completed_results`, `failed_questions`, `questions`, `question_traces`
**State writes:** `final_report`, `messages`

**How to extend:**
- Add custom metrics (e.g., average execution time by difficulty, answer type distribution)
- Add a `ground_truth` comparison if you have known correct answers
- Emit the report to a database or API instead of (or in addition to) JSON

---

## 8. Prompt Engineering

### Question Generator Prompt (`prompts/question_gen.py`)

**System prompt key instructions:**
- Generate exactly 10 questions ranked 1-10
- Easy (1-3): 1-2 computation steps | Medium (4-7): 2-4 steps with transforms | Hard (8-10): 4+ steps with aggregation + filtering + derived metrics
- PREFER aggregate/statistical questions using pre-aggregated dataset keys
- AVOID PII extraction (names, card numbers, DOB)

**User prompt contains:**
- Full `metadata.json` as JSON
- Dataset structure summary (key names, types, inner field names, example values)

### DAG Generator Prompt (`prompts/dag_gen.py`)

**System prompt key rules:**
1. Each node is a Python function — inputs → single output
2. Layer 0 = no dependencies; Layer N depends only on layers < N
3. Inputs use `"dataset.<field>"` or `"prev_node.<node_id>.output"` references
4. Code must be self-contained — no imports (safe modules pre-loaded)
5. `final_answer_node` must be in the last layer

**User prompt contains:**
- Question text + difficulty
- Relevant data keys hint
- Rich dataset schema with EXACT field names and inner dict structures (prevents hallucinated field names like `transaction_count` instead of `count`)
- Per-column field guide from `metadata.json`:
  - Type, format, strptime pattern for date fields
  - Nullable flag + null rate for nullable fields
  - PII sensitivity flags
  - Value enumerations for categoricals

**On feedback iterations:**
- Full previous DAG is included
- All issues are listed with per-layer breakdowns
- Suggestions for the fix
- Instruction to generate a COMPLETE new DAG (not a patch)

### Critic Prompt (`prompts/critic.py`)

**System prompt checks:**
1. Logical correctness
2. Code correctness
3. Type compatibility
4. Relevance
5. Edge cases (division by zero, missing keys, empty lists)
6. **Field name correctness** — any undocumented dict key access is a critical error

**User prompt (per layer) contains:**
- The question text
- Full dataset schema (same rich format as DAG generator)
- DAG overview (description, final node, total nodes/layers)
- Previously validated layers (summary of already-approved nodes)
- THIS layer's nodes with full code

---

## 9. Sandbox Execution Engine

**Files:** `src/eval_dag/sandbox/permissions.py`, `src/eval_dag/sandbox/runner.py`

The sandbox prevents LLM-generated code from doing anything harmful.

### Allowed Builtins (53 total)

```python
SAFE_BUILTINS = {
    "abs", "all", "any", "bin", "bool", "chr", "dict", "divmod",
    "enumerate", "filter", "float", "format", "frozenset", "getattr",
    "hasattr", "hash", "hex", "int", "isinstance", "issubclass", "iter",
    "len", "list", "map", "max", "min", "next", "oct", "ord", "pow",
    "print", "range", "repr", "reversed", "round", "set", "slice",
    "sorted", "str", "sum", "tuple", "type", "zip",
    "True", "False", "None",
    # Exceptions
    "ValueError", "TypeError", "KeyError", "IndexError",
    "AttributeError", "StopIteration", "ZeroDivisionError", "Exception"
}
```

### Allowed Modules (13 total)

```python
SAFE_MODULES = [
    "math", "statistics", "collections", "itertools",
    "functools", "json", "re", "datetime", "decimal",
    "fractions", "random", "operator", "string"
]
```

These are **pre-imported** into the execution namespace. Node code must NOT import them — they're already available.

### Forbidden (will cause AST rejection or runtime error)

- All `import` statements (both `import X` and `from X import Y`)
- Dangerous modules: `os`, `sys`, `subprocess`, `socket`, `pickle`, `ctypes`, `threading`, `multiprocessing`, `shutil`, `pathlib`, `io`, `builtins`, `importlib`
- Dangerous builtins: `exec`, `eval`, `open`, `__import__`, `compile`, `globals`, `locals`, `vars`, `dir`, `delattr`, `setattr`
- Dunder attribute access: `__class__`, `__bases__`, `__mro__`, etc.

### Execution Flow

```python
def execute_approved_dag(dag: GeneratedDAG, dataset: dict) -> ExecutionResult:
    layers = extract_layers(dag)          # Group nodes by layer number
    node_outputs = {}

    for layer in layers:
        for node in layer:
            # Resolve inputs: "dataset.transactions" → actual list
            #                 "prev_node.step_1a.output" → node_outputs["step_1a"]
            inputs = {
                k: resolve_input_reference(v, dataset, node_outputs)
                for k, v in node.inputs.items()
            }
            result = sandbox_execute_node(node, inputs)
            if not result.success:
                return ExecutionResult(success=False, error=result.error, ...)
            node_outputs[node.node_id] = result.output

    final_answer = node_outputs[dag.final_answer_node]
    return ExecutionResult(success=True, final_answer=final_answer, ...)
```

### Input Reference Resolution

DAG nodes reference inputs with two patterns:

| Pattern | Resolves to |
|---|---|
| `"dataset.transactions"` | `dataset["transactions"]` |
| `"dataset.category_stats"` | `dataset["category_stats"]` |
| `"prev_node.step_1a.output"` | `node_outputs["step_1a"]` |

---

## 10. DAG Utilities & Validators

**File:** `src/eval_dag/utils/dag_utils.py`

### `extract_layers(dag) → list[list[DAGNodeSpec]]`
Groups nodes by their `layer` field. Layer 0 nodes have no dependencies. Used by both the executor (for execution order) and the critic (for per-layer validation).

### Structural Validators (all called by `run_all_structural_validations`)

| Validator | What it checks |
|---|---|
| `validate_edges_reference_existing_nodes` | Every edge source/target is a real node_id |
| `validate_layer_assignment` | For every edge A→B: A.layer < B.layer |
| `validate_acyclicity` | No directed cycles (uses `graphlib.TopologicalSorter`) |
| `validate_connectivity` | `final_answer_node` is reachable from at least one layer-0 node; no nodes exist that can never contribute to the answer |
| `validate_input_references` | All input values match `dataset.<key>` or `prev_node.<id>.output` patterns, and the referenced node_id exists |
| `validate_code_syntax` | `ast.parse()` succeeds on every node's code string |
| `validate_code_safety` | AST walk: no `Import`/`ImportFrom`, no calls to forbidden functions, no dunder attribute access |

### Adding a New Validator

```python
# In dag_utils.py:
def validate_my_new_rule(dag: GeneratedDAG) -> list[str]:
    """Returns list of error strings (empty = valid)."""
    errors = []
    for node in dag.nodes:
        if some_condition(node):
            errors.append(f"{node.node_id}: description of problem")
    return errors

# Register it:
def run_all_structural_validations(dag: GeneratedDAG) -> list[str]:
    errors = []
    errors.extend(validate_edges_reference_existing_nodes(dag))
    errors.extend(validate_layer_assignment(dag))
    # ... existing validators ...
    errors.extend(validate_my_new_rule(dag))   # ← add here
    return errors
```

---

## 11. Dataset & Metadata Format

### `data.json` — The Dataset

A flat dict with pre-aggregated keys for efficient LLM access:

```json
{
  "transactions": [ ...5000 sample rows... ],
  "total_transactions": 1048575,
  "total_fraudulent": 6006,
  "fraud_rate": 0.005728,
  "date_range": { "start": "2019-01-01", "end": "2020-03-10" },
  "amount_distribution": { "min": 0.0, "max": 28000.0, "mean": 70.28, "median": 47.17, "std": 159.61, "p25": 9.63, "p75": 83.19, "p95": 310.67, "p99": 914.05 },
  "category_stats": {
    "grocery_pos": { "count": 99906, "total_amt": 5234567.0, "fraud_count": 97, "fraud_rate": 0.00097, "avg_amt": 52.4 }
  },
  "state_stats": {
    "CA": { "count": 42000, "total_amt": 2800000.0, "fraud_count": 240 }
  },
  "top_merchants": [ { "merchant": "fraud_Kling...", "count": 42, "total_amt": 2100.0, "fraud_count": 0, "fraud_rate": 0.0 } ],
  "gender_breakdown": { "M": { "count": 530000, "fraud_count": 3000, "total_amt": 38000000.0 }, "F": {...} },
  "time_series": { "2019-01": { "count": 45000, "total_amt": 3200000.0, "fraud_count": 210 } },
  "sample_info": { "sample_size": 5000, "fraud_in_sample": 998, "fraud_rate_in_sample": 0.1996, "note": "..." }
}
```

### `metadata.json` — The Schema

Describes the dataset so the LLM understands what it's working with:

```json
{
  "description": "...",
  "domain": "Financial fraud detection",
  "columns": {
    "trans_date_trans_time": {
      "description": "Transaction datetime",
      "type": "datetime_string",
      "format": "DD-MM-YYYY HH:MM",
      "strptime": "%d-%m-%Y %H:%M",
      "note": "Day-first format — NOT month-first."
    },
    "merch_zipcode": {
      "description": "Merchant zip code",
      "type": "string",
      "nullable": true,
      "null_rate": "~15%",
      "note": "Always check for None before accessing."
    },
    "is_fraud": {
      "description": "Fraud label",
      "type": "binary_integer",
      "values": [0, 1],
      "note": "1=fraudulent. Use ONLY this field for fraud detection."
    }
  },
  "dataset_keys": {
    "transactions": "Stratified sample of 5000 rows...",
    "category_stats": "Dict: category_name → {count, total_amt, fraud_count, fraud_rate, avg_amt}..."
  },
  "important_notes": [
    "All merchant names begin with 'fraud_' — naming convention only, NOT a fraud signal.",
    "Sandbox has no pandas/numpy — use list comprehensions, sum(), statistics, math."
  ]
}
```

**Column annotation fields:**
| Field | Purpose |
|---|---|
| `type` | Machine-readable type (datetime_string, float, categorical, binary_integer, identifier, string) |
| `format` | Human-readable format (e.g., "DD-MM-YYYY HH:MM") |
| `strptime` | Exact Python strptime format string — copy-paste ready |
| `nullable` + `null_rate` | Warns LLM to add None checks |
| `sensitivity: "pii"` | Flags PII fields — question generator avoids extracting these |
| `values` | Full enumeration for categoricals |
| `range` | Numeric range for floats/integers |
| `note` | Critical warnings that override any other assumption |

---

## 12. Output Format

### `eval_results.json`

```json
{
  "summary": {
    "total_questions": 10,
    "passed": 7,
    "failed": 3,
    "pass_rate": 0.7,
    "generated_at": "2026-02-18T12:44:00"
  },
  "difficulty_breakdown": {
    "easy":   { "total": 3, "passed": 3, "failed": 0, "pass_rate": 1.0 },
    "medium": { "total": 4, "passed": 3, "failed": 1, "pass_rate": 0.75 },
    "hard":   { "total": 3, "passed": 1, "failed": 2, "pass_rate": 0.33 }
  },
  "detailed_results": [
    {
      "question_id": "q_01",
      "question_text": "What is the overall fraud rate?",
      "difficulty_level": "easy",
      "difficulty_rank": 1,
      "success": true,
      "final_answer": 0.005728,
      "execution_time_ms": 3.2
    }
  ],
  "failure_analysis": [
    {
      "question_id": "q_07",
      "question_text": "...",
      "error": "KeyError: 'transaction_count'"
    }
  ],
  "question_traces": [ ...full audit trail per question... ]
}
```

### `eval_report.html`

A self-contained HTML file (no external dependencies) with:
- Summary stats and difficulty breakdown table
- Per-question expandable sections showing:
  - All DAG iterations (each collapsible)
  - SVG graph visualization (nodes as colored boxes, edges as bezier curves)
  - Syntax-highlighted Python code per node
  - Node outputs table
  - Critic feedback (issues, suggestions)
  - Conversation log

---

## 13. Quick Start

### Prerequisites

- Python 3.11+
- OpenAI API key
- A dataset CSV file (or use the included credit card fraud dataset)

### Install

```bash
cd "path/to/eval"
pip install -e .[dev]
pip install pandas   # only needed for prepare_dataset.py
```

### Prepare Dataset

```bash
# Convert your CSV to the required data.json + metadata.json format
python scripts/prepare_dataset.py \
    --input dataset/credit_card_transactions.csv \
    --output-dir dataset/
```

### Run the Evaluation

```bash
# Windows PowerShell
$env:OPENAI_API_KEY = "sk-..."
python scripts/run_eval.py `
    --dataset dataset/data.json `
    --metadata dataset/metadata.json `
    --output eval_results.json `
    --verbose

# Linux/macOS
export OPENAI_API_KEY="sk-..."
python scripts/run_eval.py \
    --dataset dataset/data.json \
    --metadata dataset/metadata.json \
    --output eval_results.json \
    --verbose
```

### Generate HTML Report

```bash
python scripts/generate_report.py \
    --input eval_results.json \
    --output eval_report.html
```

Open `eval_report.html` in your browser.

### Run Tests

```bash
pytest tests/ -v
```

---

## 14. Extending the System

### Use a Different Dataset

1. Create `data.json` with your dataset's pre-aggregated structure (see [Dataset & Metadata Format](#11-dataset--metadata-format))
2. Create `metadata.json` with per-field annotations
3. Run the pipeline — the question generator and DAG builder read from metadata dynamically

### Add a New LLM

Each node has a `_get_llm()` function. Swap it to any LangChain-compatible model:

```python
# In nodes/dag_builder.py
def _get_llm():
    from langchain_anthropic import ChatAnthropic
    return ChatAnthropic(model="claude-3-5-sonnet-20241022", temperature=0.2)
```

### Add a New Structural Validator

In `utils/dag_utils.py`:

```python
def validate_max_nodes_per_layer(dag: GeneratedDAG, max_nodes: int = 5) -> list[str]:
    """Prevent overly wide DAGs."""
    errors = []
    for layer_idx, nodes in enumerate(extract_layers(dag)):
        if len(nodes) > max_nodes:
            errors.append(f"Layer {layer_idx} has {len(nodes)} nodes (max {max_nodes})")
    return errors
```

Then add it to `run_all_structural_validations()`.

### Add a New Semantic Check to the Critic

Edit `CRITIC_SYSTEM` in `prompts/critic.py`:

```
7. **Performance**: Avoid O(n²) or worse operations on large lists.
   Flag any nested loop over the transactions list as a performance concern.
```

### Change Maximum Critic Iterations

In `src/eval_dag/graphs/critic_loop.py`:

```python
MAX_ITERATIONS = 5  # default is 3
```

### Add Ground Truth Comparison

In `nodes/result_collector.py`, add ground truth loading and comparison:

```python
if ground_truth and question_id in ground_truth:
    expected = ground_truth[question_id]
    is_correct = abs(float(result.final_answer) - float(expected)) < 0.01
```

### Enable LangSmith Tracing

No code changes needed — just set environment variables:

```bash
export LANGCHAIN_TRACING_V2=true
export LANGCHAIN_API_KEY="ls__..."
export LANGCHAIN_PROJECT="eval-dag"
```

All LangGraph nodes will automatically appear in your LangSmith dashboard.

---

## 15. Design Decisions & Trade-offs

### Why DAGs instead of a single code block?

DAGs allow the critic to validate **layer by layer**, giving targeted feedback ("step_2a has a wrong field name") rather than a monolithic code dump. It also enables parallelism within a layer and clear audit trails showing exactly where computation goes wrong.

### Why structural validation before semantic?

Structural validation is deterministic (no LLM cost, no rate limits, instant). It catches critical errors (cycles, missing nodes, syntax errors) that would make semantic validation pointless. This avoids wasting LLM tokens on broken DAGs.

### Why `operator.add` reducers on OrchestratorState?

LangGraph's `Send()` API runs all 10 questions in parallel. Without reducers, concurrent writes to `completed_results` would overwrite each other. `operator.add` on lists concatenates them safely regardless of execution order.

### Why approve a layer on rate limit exhaustion?

Rate limit errors are transient infrastructure failures — they say nothing about the DAG's correctness. Treating them as validation failures would penalize correct DAGs and waste rebuild iterations. Approving on exhaustion is the pragmatic choice; the sandbox execution serves as the true correctness check.

### Why no pandas/numpy in the sandbox?

Security and simplicity. Pandas/numpy have large attack surfaces and complex import chains. The sandbox is designed for simple analytical computations that are fully expressible with Python builtins and the 13 allowed safe modules. This constraint also forces the LLM to write more transparent, auditable code.

### Why pre-aggregate the dataset into `data.json`?

The LLM context window is limited. Passing 1 million raw transaction rows is impossible. Pre-aggregating into `category_stats`, `state_stats`, `time_series`, etc. means most questions can be answered with simple dict lookups rather than iterating 1M rows. The 5000-row `transactions` sample covers cross-dimensional questions that require raw data.

---

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Add tests for any new validators or nodes
4. Run `pytest tests/ -v` to verify nothing is broken
5. Submit a pull request

---

## License

MIT

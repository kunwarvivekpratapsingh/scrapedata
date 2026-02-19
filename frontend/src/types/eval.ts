// TypeScript interfaces mirroring Python Pydantic models
// from eval_dag/state/models.py and eval_dag/state/schemas.py

export type DifficultyLevel = 'easy' | 'medium' | 'hard'

export interface Question {
  id: string
  text: string
  difficulty_rank: number
  difficulty_level: DifficultyLevel
  reasoning: string
  relevant_data_keys: string[]
}

// ── DAG models ──────────────────────────────────────────────────────────────

export interface DAGEdge {
  source: string
  target: string
}

export interface DAGNodeSpec {
  node_id: string
  operation: string
  function_name: string
  inputs: Record<string, unknown>
  expected_output_type: string
  layer: number
  code: string
}

export interface GeneratedDAG {
  question_id?: string
  description: string
  nodes: DAGNodeSpec[]
  edges: DAGEdge[]
  final_answer_node: string
}

// ── Critic models ────────────────────────────────────────────────────────────

export interface LayerValidation {
  layer_index: number
  nodes_in_layer: string[]
  is_valid: boolean
  issues: string[]
}

export interface CriticFeedback {
  is_approved: boolean
  overall_reasoning: string
  layer_validations: LayerValidation[]
  specific_errors: string[]
  suggestions: string[]
}

// ── Execution models ─────────────────────────────────────────────────────────

export interface NodeExecutionResult {
  node_id: string
  success: boolean
  output: unknown
  error: string | null
  execution_time_ms: number
}

export interface ExecutionResult {
  question_id: string
  success: boolean
  final_answer: unknown
  error: string | null
  execution_time_ms: number
  node_results: NodeExecutionResult[]
}

// ── Per-question trace (normalised, used everywhere in UI) ────────────────────

export interface QuestionTrace {
  question: Question
  is_approved: boolean
  iterations: number
  execution_result: ExecutionResult | null
  dag_history: GeneratedDAG[]
  feedback_history: CriticFeedback[]
  messages: string[]
  ground_truth?: unknown
}

// ── Top-level normalised shape used everywhere in UI ─────────────────────────

export interface EvalSummary {
  total_questions: number
  passed: number
  failed: number
  pass_rate: number
  avg_execution_time_ms: number
  total_iterations: number
  timestamp?: string
  dataset?: string
}

export interface EvalResults {
  summary: EvalSummary
  questions: QuestionTrace[]
}

// ── Live runner types ─────────────────────────────────────────────────────────

export type RunDifficulty = 'all' | 'easy' | 'medium' | 'hard'

export interface RunConfig {
  difficulty: RunDifficulty
  num_questions: number
}

// Discriminated union — one type per SSE event type
export type RunEvent =
  | { type: 'run_started';          ts: string; payload: { run_id: string; num_questions: number; difficulty: string } }
  | { type: 'questions_generated';  ts: string; payload: { questions: Array<{ id: string; text: string; difficulty_level: string; difficulty_rank: number }> } }
  | { type: 'dag_built';            ts: string; payload: { question_id: string; iteration: number; description: string; node_count: number; edge_count: number } }
  | { type: 'critic_result';        ts: string; payload: { question_id: string; iteration: number; is_approved: boolean; issues_count: number; overall_reasoning: string } }
  | { type: 'execution_done';       ts: string; payload: { question_id: string; success: boolean; final_answer: unknown; execution_time_ms: number; error: string | null } }
  | { type: 'question_complete';    ts: string; payload: { question_id: string; success: boolean; total_iterations: number } }
  | { type: 'run_complete';         ts: string; payload: { output_file: string; summary: { total: number; passed: number; failed: number; pass_rate: number } } }
  | { type: 'error';                ts: string; payload: { message: string; question_id?: string } }

// ── Raw shape of single_question_result.json (before normalisation) ───────────

export interface RawSingleResult {
  question: Question
  ground_truth: unknown
  iterations_used: number      // NOT "iterations"
  is_approved: boolean
  correct?: boolean
  execution_result: {
    question_id: string
    success: boolean
    final_answer: unknown
    node_outputs: Record<string, unknown>  // dict keyed by node_id
    error?: string | null
    execution_time_ms?: number
  } | null
  dag_history: Array<{
    iteration: number
    dag: GeneratedDAG       // actual DAG nested one level deep
    feedback: CriticFeedback
  }>
  messages: string[]
}

// ── Raw shape of eval_results.json (before normalisation) ────────────────────

export interface RawEvalResults {
  summary: {
    total_questions: number
    successful_executions: number
    execution_failures: number
    critic_loop_exhausted: number
    pass_rate: number
  }
  question_traces: Array<{    // NOT "questions"
    question_id: string
    question_text: string
    difficulty: DifficultyLevel
    difficulty_rank: number
    total_iterations: number
    final_answer: unknown
    success: boolean
    execution_error: string | null
    execution_time_ms: number
    node_outputs: Record<string, unknown>
    iterations: Array<{
      iteration: number
      dag: GeneratedDAG
      critic_feedback: CriticFeedback   // NOT "feedback"
    }>
    conversation_log: Array<{ role: string; content: string }>
  }>
}

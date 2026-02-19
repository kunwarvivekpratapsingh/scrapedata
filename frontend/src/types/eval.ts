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
  question_id: string
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

// ── Per-question trace (from eval_results.json) ───────────────────────────────

export interface QuestionTrace {
  question: Question
  is_approved: boolean
  iterations: number
  execution_result: ExecutionResult | null
  dag_history: GeneratedDAG[]
  feedback_history: CriticFeedback[]
  messages: string[]
  // ground_truth present in single_question_result.json
  ground_truth?: unknown
}

// ── Top-level eval_results.json shape ────────────────────────────────────────

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

// ── single_question_result.json shape ────────────────────────────────────────
// (raw shape before normalisation)

export interface SingleQuestionResult {
  question: Question
  ground_truth: unknown
  iterations: number
  is_approved: boolean
  execution_result: ExecutionResult | null
  dag_history: GeneratedDAG[]
  messages: string[]
}

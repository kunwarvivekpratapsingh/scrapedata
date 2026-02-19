/**
 * Normalise raw JSON (either single_question_result.json or eval_results.json)
 * into the unified EvalResults shape used by the UI.
 *
 * Both JSON files have different schemas from what the UI types expect, so we
 * explicitly detect and convert each format here.
 */
import type {
  EvalResults,
  EvalSummary,
  QuestionTrace,
  Question,
  ExecutionResult,
  NodeExecutionResult,
  RawSingleResult,
  RawEvalResults,
} from '../types/eval'

// ── Type guards ──────────────────────────────────────────────────────────────

/**
 * single_question_result.json: has "question" + "dag_history" + "iterations_used"
 */
function isRawSingle(raw: unknown): raw is RawSingleResult {
  return (
    typeof raw === 'object' &&
    raw !== null &&
    'question' in raw &&
    'dag_history' in raw &&
    'iterations_used' in raw
  )
}

/**
 * eval_results.json: has "summary" + "question_traces"
 */
function isRawEval(raw: unknown): raw is RawEvalResults {
  return (
    typeof raw === 'object' &&
    raw !== null &&
    'summary' in raw &&
    'question_traces' in raw
  )
}

// ── node_outputs dict → NodeExecutionResult[] ────────────────────────────────

function nodeOutputsToResults(
  nodeOutputs: Record<string, unknown>
): NodeExecutionResult[] {
  return Object.entries(nodeOutputs ?? {}).map(([node_id, output]) => ({
    node_id,
    success: true,
    output,
    error: null,
    execution_time_ms: 0,
  }))
}

// ── Converters ───────────────────────────────────────────────────────────────

function convertSingle(sq: RawSingleResult, filename: string): EvalResults {
  // dag_history[i].dag  → GeneratedDAG (unwrap the wrapper)
  // dag_history[i].feedback → CriticFeedback (unwrap the wrapper)
  const dagHistory = sq.dag_history.map((h) => h.dag)
  const feedbackHistory = sq.dag_history.map((h) => h.feedback)

  const nodeResults = nodeOutputsToResults(
    sq.execution_result?.node_outputs ?? {}
  )

  const execResult: ExecutionResult | null = sq.execution_result
    ? {
        question_id: sq.execution_result.question_id,
        success: sq.execution_result.success,
        final_answer: sq.execution_result.final_answer,
        error: sq.execution_result.error ?? null,
        execution_time_ms: sq.execution_result.execution_time_ms ?? 0,
        node_results: nodeResults,
      }
    : null

  const trace: QuestionTrace = {
    question: sq.question,
    is_approved: sq.is_approved,
    iterations: sq.iterations_used, // ← actual field name in file
    execution_result: execResult,
    dag_history: dagHistory,
    feedback_history: feedbackHistory,
    messages: sq.messages ?? [],
    ground_truth: sq.ground_truth,
  }

  const passed = execResult?.success ? 1 : 0
  const summary: EvalSummary = {
    total_questions: 1,
    passed,
    failed: 1 - passed,
    pass_rate: passed,
    avg_execution_time_ms: execResult?.execution_time_ms ?? 0,
    total_iterations: sq.iterations_used,
    dataset: filename,
  }

  return { summary, questions: [trace] }
}

function convertEval(raw: RawEvalResults, filename: string): EvalResults {
  const questions: QuestionTrace[] = raw.question_traces.map((qt) => {
    // Reconstruct Question object from the flat fields in each trace
    const question: Question = {
      id: qt.question_id,
      text: qt.question_text,
      difficulty_rank: qt.difficulty_rank,
      difficulty_level: qt.difficulty,
      reasoning: '',
      relevant_data_keys: [],
    }

    // iterations[i].dag → GeneratedDAG
    // iterations[i].critic_feedback → CriticFeedback (note: NOT "feedback")
    const dagHistory = qt.iterations.map((it) => it.dag)
    const feedbackHistory = qt.iterations.map((it) => it.critic_feedback)

    const nodeResults = nodeOutputsToResults(qt.node_outputs ?? {})

    const execResult: ExecutionResult = {
      question_id: qt.question_id,
      success: qt.success,
      final_answer: qt.final_answer,
      error: qt.execution_error,
      execution_time_ms: qt.execution_time_ms,
      node_results: nodeResults,
    }

    // conversation_log is [{role, content}] — flatten to strings
    const messages = (qt.conversation_log ?? []).map(
      (m) => `[${m.role}] ${m.content}`
    )

    return {
      question,
      is_approved: qt.success,
      iterations: qt.total_iterations,
      execution_result: execResult,
      dag_history: dagHistory,
      feedback_history: feedbackHistory,
      messages,
    }
  })

  const s = raw.summary
  const summary: EvalSummary = {
    total_questions: s.total_questions,
    passed: s.successful_executions,
    failed: s.execution_failures,
    pass_rate: s.pass_rate,
    avg_execution_time_ms: 0,
    total_iterations: 0,
    dataset: filename,
  }

  return { summary, questions }
}

// ── Public entry point ────────────────────────────────────────────────────────

export function convertToEvalResults(raw: unknown, filename: string): EvalResults {
  if (isRawSingle(raw)) {
    return convertSingle(raw, filename)
  }

  if (isRawEval(raw)) {
    return convertEval(raw, filename)
  }

  // Unknown format — return empty shell so the UI doesn't crash
  console.warn('Unknown result file shape for', filename, '— top-level keys:',
    typeof raw === 'object' && raw !== null ? Object.keys(raw) : raw)
  return {
    summary: {
      total_questions: 0,
      passed: 0,
      failed: 0,
      pass_rate: 0,
      avg_execution_time_ms: 0,
      total_iterations: 0,
      dataset: filename,
    },
    questions: [],
  }
}

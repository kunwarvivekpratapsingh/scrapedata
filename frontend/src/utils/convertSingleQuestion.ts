/**
 * Normalize raw JSON (either eval_results.json or single_question_result.json)
 * into the unified EvalResults shape.
 */
import type {
  EvalResults,
  EvalSummary,
  QuestionTrace,
  SingleQuestionResult,
} from '../types/eval'

function isSingleQuestion(raw: unknown): raw is SingleQuestionResult {
  return (
    typeof raw === 'object' &&
    raw !== null &&
    'question' in raw &&
    !('summary' in raw) &&
    !('questions' in raw)
  )
}

function isEvalResults(raw: unknown): raw is EvalResults {
  return (
    typeof raw === 'object' &&
    raw !== null &&
    'summary' in raw &&
    'questions' in raw
  )
}

export function convertToEvalResults(raw: unknown, filename: string): EvalResults {
  if (isEvalResults(raw)) {
    return raw
  }

  if (isSingleQuestion(raw)) {
    const sq = raw as SingleQuestionResult
    const passed = sq.execution_result?.success ? 1 : 0

    const trace: QuestionTrace = {
      question: sq.question,
      is_approved: sq.is_approved,
      iterations: sq.iterations,
      execution_result: sq.execution_result,
      dag_history: sq.dag_history ?? [],
      feedback_history: [],
      messages: sq.messages ?? [],
      ground_truth: sq.ground_truth,
    }

    const summary: EvalSummary = {
      total_questions: 1,
      passed,
      failed: 1 - passed,
      pass_rate: passed,
      avg_execution_time_ms: sq.execution_result?.execution_time_ms ?? 0,
      total_iterations: sq.iterations,
      dataset: filename,
    }

    return { summary, questions: [trace] }
  }

  // Unknown shape — return empty
  console.warn('Unknown result file shape for', filename)
  const summary: EvalSummary = {
    total_questions: 0,
    passed: 0,
    failed: 0,
    pass_rate: 0,
    avg_execution_time_ms: 0,
    total_iterations: 0,
    dataset: filename,
  }
  return { summary, questions: [] }
}

import type { QuestionTrace } from '../../types/eval'
import { formatAnswer } from '../../utils/formatAnswer'

export function AnswerBox({ trace }: { trace: QuestionTrace }) {
  const result = trace.execution_result
  const answer = result?.final_answer
  const hasGT = trace.ground_truth !== undefined && trace.ground_truth !== null

  if (!result) {
    return (
      <div className="bg-red-950/40 border border-red-800/60 rounded-lg px-4 py-3 text-sm text-red-300">
        No execution result — critic loop exhausted without approval.
      </div>
    )
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
      <div
        className={`rounded-lg p-4 border ${
          result.success
            ? 'bg-gray-900 border-gray-700'
            : 'bg-red-950/40 border-red-800/60'
        }`}
      >
        <p className="text-xs text-gray-500 uppercase tracking-wider mb-2">
          Answer {result.success ? '✓' : '✗'}
        </p>
        {result.success ? (
          <pre className="text-sm text-green-300 font-mono whitespace-pre-wrap break-all">
            {formatAnswer(answer)}
          </pre>
        ) : (
          <p className="text-sm text-red-300 font-mono whitespace-pre-wrap">
            {result.error ?? 'Unknown error'}
          </p>
        )}
        {result.execution_time_ms > 0 && (
          <p className="text-xs text-gray-600 mt-2">
            {result.execution_time_ms.toFixed(1)} ms
          </p>
        )}
      </div>

      {hasGT && (
        <div className="bg-gray-900 border border-gray-700 rounded-lg p-4">
          <p className="text-xs text-gray-500 uppercase tracking-wider mb-2">
            Ground Truth
          </p>
          <pre className="text-sm text-amber-300 font-mono whitespace-pre-wrap break-all">
            {formatAnswer(trace.ground_truth)}
          </pre>
        </div>
      )}
    </div>
  )
}

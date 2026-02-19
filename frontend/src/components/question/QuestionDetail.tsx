import type { QuestionTrace } from '../../types/eval'
import { AnswerBox } from './AnswerBox'
import { IterationPanel } from './IterationPanel'
import { ConversationTimeline } from './ConversationTimeline'
import { Collapsible } from '../ui/Collapsible'

interface QuestionDetailProps {
  trace: QuestionTrace
}

export function QuestionDetail({ trace }: QuestionDetailProps) {
  const dagHistory = trace.dag_history ?? []
  const feedbackHistory = trace.feedback_history ?? []

  // If dag_history is empty but we have an execution_result, synthesize one entry
  // This handles single_question_result.json which has dag_history embedded
  const iterations = dagHistory.length > 0 ? dagHistory : []

  return (
    <div className="space-y-5 py-4">
      {/* Answer box */}
      <div>
        <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">
          Result
        </p>
        <AnswerBox trace={trace} />
      </div>

      {/* Reasoning */}
      {trace.question.reasoning && (
        <Collapsible
          trigger={
            <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
              Reasoning
            </span>
          }
          defaultOpen={false}
        >
          <p className="text-sm text-gray-400 leading-relaxed mt-2 bg-gray-900 rounded-lg p-3">
            {trace.question.reasoning}
          </p>
        </Collapsible>
      )}

      {/* Critic loop iterations */}
      {iterations.length > 0 ? (
        <div>
          <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">
            Critic Loop ({iterations.length} iteration{iterations.length !== 1 ? 's' : ''})
          </p>
          <div className="space-y-3">
            {iterations.map((dag, i) => {
              const feedback = feedbackHistory[i] ?? null
              const isLastIteration = i === iterations.length - 1
              return (
                <IterationPanel
                  key={i}
                  iteration={i}
                  dag={dag}
                  feedback={feedback}
                  execResult={isLastIteration ? trace.execution_result : null}
                  isApproved={isLastIteration && (trace.is_approved ?? false)}
                />
              )
            })}
          </div>
        </div>
      ) : trace.execution_result ? (
        // No dag_history, but we have result — show a minimal panel
        <p className="text-xs text-gray-500">
          DAG history not recorded in this result file.
        </p>
      ) : null}

      {/* Conversation timeline */}
      {(trace.messages ?? []).length > 0 && (
        <Collapsible
          trigger={
            <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
              Message Log ({trace.messages.length})
            </span>
          }
          defaultOpen={false}
        >
          <div className="mt-2 bg-gray-900 rounded-lg p-3 max-h-64 overflow-y-auto">
            <ConversationTimeline messages={trace.messages} />
          </div>
        </Collapsible>
      )}
    </div>
  )
}

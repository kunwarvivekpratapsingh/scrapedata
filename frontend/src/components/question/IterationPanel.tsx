import type { GeneratedDAG, CriticFeedback, ExecutionResult } from '../../types/eval'
import { Collapsible } from '../ui/Collapsible'
import { Badge } from '../ui/Badge'
import { DAGViewer } from '../dag/DAGViewer'
import { CriticFeedback as CriticFeedbackComp } from './CriticFeedback'
import { NodeOutputsTable } from './NodeOutputsTable'

interface IterationPanelProps {
  iteration: number
  dag: GeneratedDAG
  feedback: CriticFeedback | null
  execResult: ExecutionResult | null
  isApproved: boolean
}

export function IterationPanel({
  iteration,
  dag,
  feedback,
  execResult,
  isApproved,
}: IterationPanelProps) {
  const isFinalApproved = isApproved && iteration === 0 // single-iter case
  const verdict = feedback?.is_approved ?? isApproved

  return (
    <div className="border border-gray-800 rounded-xl overflow-hidden">
      {/* Iteration header */}
      <div className="flex items-center gap-3 px-4 py-3 bg-gray-900/60 border-b border-gray-800">
        <span className="text-xs font-mono text-gray-500">Iteration {iteration + 1}</span>
        <Badge variant={verdict ? 'green' : 'red'} size="sm">
          {verdict ? '✓ APPROVED' : '✗ REJECTED'}
        </Badge>
        {dag.description && (
          <span className="text-xs text-gray-500 truncate max-w-sm">{dag.description}</span>
        )}
        <span className="ml-auto text-xs text-gray-600 font-mono">
          {dag.nodes.length} nodes · {dag.edges.length} edges
        </span>
      </div>

      <div className="p-4 space-y-4">
        {/* DAG visualization */}
        <Collapsible
          trigger={
            <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
              DAG Structure
            </span>
          }
          defaultOpen={true}
        >
          <DAGViewer dag={dag} execResult={verdict ? execResult : null} />
        </Collapsible>

        {/* Critic feedback (if rejected) */}
        {feedback && !feedback.is_approved && (
          <Collapsible
            trigger={
              <span className="text-xs font-semibold text-amber-400 uppercase tracking-wider">
                Critic Feedback
              </span>
            }
            defaultOpen={true}
          >
            <CriticFeedbackComp feedback={feedback} />
          </Collapsible>
        )}

        {/* Execution results (only on approved run) */}
        {verdict && execResult && (
          <Collapsible
            trigger={
              <span className="text-xs font-semibold text-teal-400 uppercase tracking-wider">
                Node Execution Results
              </span>
            }
            defaultOpen={false}
          >
            <NodeOutputsTable execResult={execResult} />
          </Collapsible>
        )}
      </div>
    </div>
  )
}

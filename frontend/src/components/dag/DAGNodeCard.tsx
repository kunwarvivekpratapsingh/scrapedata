import { memo } from 'react'
import { Handle, Position } from '@xyflow/react'
import type { DAGNodeData } from './layerLayout'

type NodeExecResult = DAGNodeData['executionResult']

function statusDot(execResult: NodeExecResult): string {
  if (!execResult) return ''
  return execResult.success ? '✓' : '✗'
}

function statusColor(execResult: NodeExecResult): string {
  if (!execResult) return 'text-gray-500'
  return execResult.success ? 'text-green-400' : 'text-red-400'
}

// React Flow v12 passes data as the raw DAGNodeData object via the `data` prop
export const DAGNodeCard = memo(function DAGNodeCard({
  data,
}: {
  data: DAGNodeData
  id?: string
  selected?: boolean
}) {
  const { spec, color, isFinalAnswer, executionResult, onClickNode } = data

  return (
    <div
      onClick={() => onClickNode(spec.node_id)}
      className={`w-[220px] bg-gray-900 border rounded-lg overflow-hidden cursor-pointer
        transition-all duration-150 hover:scale-[1.02] hover:shadow-lg hover:shadow-black/40
        ${isFinalAnswer ? 'border-yellow-500/60' : 'border-gray-700'}`}
      style={{ borderTopColor: color, borderTopWidth: 3 }}
    >
      {/* Target handle (left) */}
      <Handle
        type="target"
        position={Position.Left}
        style={{ background: '#4b5563', width: 8, height: 8 }}
      />

      {/* Header */}
      <div
        className="px-3 py-1.5 flex items-center justify-between gap-2"
        style={{ background: color + '22' }}
      >
        <span
          className="text-[11px] font-mono font-semibold truncate"
          style={{ color }}
        >
          {spec.node_id}
        </span>
        <div className="flex items-center gap-1.5 shrink-0">
          {isFinalAnswer && (
            <span className="text-yellow-400 text-[10px]">★</span>
          )}
          {executionResult && (
            <span className={`text-[11px] font-bold ${statusColor(executionResult)}`}>
              {statusDot(executionResult)}
            </span>
          )}
          <span
            className="text-[9px] font-mono px-1 py-0.5 rounded"
            style={{ background: color + '33', color }}
          >
            L{spec.layer}
          </span>
        </div>
      </div>

      {/* Operation */}
      <div className="px-3 py-2">
        <p className="text-[11px] text-gray-300 leading-tight line-clamp-2">
          {spec.operation}
        </p>
      </div>

      {/* Footer */}
      <div className="px-3 pb-2 flex items-center gap-1.5 flex-wrap">
        <span className="text-[10px] font-mono text-blue-400 bg-blue-900/30 px-1.5 py-0.5 rounded">
          {spec.function_name}()
        </span>
        <span className="text-[10px] font-mono text-gray-500 truncate max-w-[130px]">
          → {spec.expected_output_type}
        </span>
      </div>

      {/* Source handle (right) */}
      <Handle
        type="source"
        position={Position.Right}
        style={{ background: '#4b5563', width: 8, height: 8 }}
      />
    </div>
  )
})

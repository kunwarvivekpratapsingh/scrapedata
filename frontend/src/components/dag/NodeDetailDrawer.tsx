import type { DAGNodeSpec, NodeExecutionResult } from '../../types/eval'
import { CodeBlock } from '../ui/CodeBlock'
import { Badge } from '../ui/Badge'
import { layerColor } from './layerLayout'
import { formatAnswer } from '../../utils/formatAnswer'

interface NodeDetailDrawerProps {
  node: DAGNodeSpec | null
  execResult: NodeExecutionResult | null
  onClose: () => void
}

export function NodeDetailDrawer({ node, execResult, onClose }: NodeDetailDrawerProps) {
  if (!node) return null

  const color = layerColor(node.layer)

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/50 z-40"
        onClick={onClose}
      />

      {/* Drawer */}
      <div className="fixed right-0 top-0 h-full w-[480px] bg-gray-950 border-l border-gray-800 z-50 flex flex-col overflow-hidden shadow-2xl">
        {/* Header */}
        <div
          className="px-5 py-4 border-b border-gray-800 flex items-center justify-between"
          style={{ borderTopColor: color, borderTopWidth: 3 }}
        >
          <div>
            <div className="flex items-center gap-2">
              <span className="font-mono font-bold text-sm" style={{ color }}>
                {node.node_id}
              </span>
              <Badge variant="gray" size="sm">Layer {node.layer}</Badge>
              {execResult && (
                <Badge variant={execResult.success ? 'green' : 'red'} size="sm">
                  {execResult.success ? '✓' : '✗'} {execResult.execution_time_ms.toFixed(1)}ms
                </Badge>
              )}
            </div>
            <p className="text-gray-400 text-xs mt-0.5">{node.operation}</p>
          </div>
          <button
            onClick={onClose}
            className="text-gray-500 hover:text-gray-300 text-xl leading-none"
          >
            ×
          </button>
        </div>

        {/* Scrollable content */}
        <div className="flex-1 overflow-y-auto p-5 space-y-5">
          {/* Metadata */}
          <div className="grid grid-cols-2 gap-3 text-xs">
            <div className="bg-gray-900 rounded-lg p-3">
              <p className="text-gray-500 mb-1">Function</p>
              <p className="font-mono text-blue-300">{node.function_name}()</p>
            </div>
            <div className="bg-gray-900 rounded-lg p-3">
              <p className="text-gray-500 mb-1">Output Type</p>
              <p className="font-mono text-teal-300 break-all">{node.expected_output_type}</p>
            </div>
          </div>

          {/* Inputs */}
          {Object.keys(node.inputs).length > 0 && (
            <div>
              <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">
                Inputs
              </p>
              <div className="bg-gray-900 rounded-lg divide-y divide-gray-800">
                {Object.entries(node.inputs).map(([k, v]) => (
                  <div key={k} className="px-3 py-2 flex items-start gap-3 text-xs font-mono">
                    <span className="text-violet-300 shrink-0">{k}</span>
                    <span className="text-gray-400 break-all">{String(v)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Code */}
          <div>
            <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">
              Code
            </p>
            <CodeBlock code={node.code} language="python" />
          </div>

          {/* Execution output */}
          {execResult && (
            <div>
              <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">
                Execution Output
              </p>
              {execResult.success ? (
                <div className="bg-gray-900 rounded-lg p-3">
                  <pre className="text-xs text-green-300 font-mono whitespace-pre-wrap break-all">
                    {formatAnswer(execResult.output)}
                  </pre>
                </div>
              ) : (
                <div className="bg-red-950/50 border border-red-800 rounded-lg p-3">
                  <p className="text-xs text-red-300 font-mono whitespace-pre-wrap">
                    {execResult.error ?? 'Unknown error'}
                  </p>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </>
  )
}

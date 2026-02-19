import type { ExecutionResult } from '../../types/eval'
import { formatNodeOutput } from '../../utils/formatNodeOutput'

export function NodeOutputsTable({ execResult }: { execResult: ExecutionResult }) {
  if (!execResult.node_results?.length) {
    return <p className="text-xs text-gray-500">No node execution data.</p>
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs font-mono">
        <thead>
          <tr className="text-gray-500 border-b border-gray-800">
            <th className="text-left py-2 pr-4">Node</th>
            <th className="text-left py-2 pr-4">Status</th>
            <th className="text-left py-2 pr-4">Output</th>
            <th className="text-right py-2">Time</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-800/50">
          {execResult.node_results.map((nr) => (
            <tr key={nr.node_id} className="hover:bg-gray-800/20">
              <td className="py-2 pr-4 text-blue-300">{nr.node_id}</td>
              <td className="py-2 pr-4">
                {nr.success ? (
                  <span className="text-green-400">✓ OK</span>
                ) : (
                  <span className="text-red-400">✗ ERR</span>
                )}
              </td>
              <td className="py-2 pr-4 text-gray-400 max-w-xs truncate">
                {nr.success
                  ? formatNodeOutput(nr.output)
                  : <span className="text-red-400">{formatNodeOutput(nr.error)}</span>
                }
              </td>
              <td className="py-2 text-right text-gray-500">
                {nr.execution_time_ms.toFixed(1)}ms
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

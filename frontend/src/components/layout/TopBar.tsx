import type { EvalSummary } from '../../types/eval'

interface TopBarProps {
  selectedFile: string | null
  summary: EvalSummary | null
}

export function TopBar({ selectedFile, summary }: TopBarProps) {
  return (
    <header className="h-12 bg-gray-950 border-b border-gray-800 flex items-center px-5 gap-4 shrink-0">
      <div className="flex items-center gap-2">
        <span className="text-blue-400 font-bold text-sm tracking-tight">
          Eval-DAG
        </span>
        <span className="text-gray-700">·</span>
        <span className="text-gray-400 text-xs">Inspector</span>
      </div>

      {selectedFile && (
        <>
          <span className="text-gray-700">·</span>
          <span className="text-gray-400 font-mono text-xs truncate max-w-xs">
            {selectedFile}
          </span>
        </>
      )}

      {summary && (
        <div className="ml-auto flex items-center gap-4 text-xs text-gray-500">
          <span>
            <span className="text-green-400 font-semibold">{summary.passed}</span>
            /{summary.total_questions} passed
          </span>
          <span className="text-gray-700">|</span>
          <span>
            <span className="text-gray-300">{(summary.pass_rate * 100).toFixed(0)}%</span>
          </span>
          {summary.avg_execution_time_ms > 0 && (
            <>
              <span className="text-gray-700">|</span>
              <span>
                avg{' '}
                <span className="text-gray-300">
                  {summary.avg_execution_time_ms.toFixed(0)}ms
                </span>
              </span>
            </>
          )}
        </div>
      )}
    </header>
  )
}

import { useEvalRun } from '../hooks/useEvalRun'
import { RunConfigForm } from '../components/run/RunConfigForm'
import { EventFeed } from '../components/run/EventFeed'
import { RunProgressBar } from '../components/run/RunProgressBar'
import type { RunConfig } from '../types/eval'

export function RunEvalPage() {
  const { phase, events, progress, error, run, reset } = useEvalRun()

  const isRunning = phase === 'submitting' || phase === 'streaming'
  const isDone = phase === 'done'
  const isError = phase === 'error'

  function handleRun(config: RunConfig) {
    run(config)
  }

  return (
    <div className="max-w-3xl mx-auto px-6 py-8 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-100">Run Evaluation</h1>
        <p className="text-sm text-gray-500 mt-1">
          Select difficulty and question count, then watch live progress via SSE.
        </p>
      </div>

      {/* Config form */}
      <RunConfigForm disabled={isRunning || isDone} onRun={handleRun} />

      {/* Progress bar */}
      {(isRunning || isDone) && (
        <RunProgressBar done={progress.done} total={progress.total} />
      )}

      {/* Status banners */}
      {isDone && (
        <div className="flex items-center justify-between px-4 py-3 rounded-xl bg-green-900/30 border border-green-700 text-green-300">
          <span className="text-sm font-semibold">
            ✅ Run complete — navigating to results…
          </span>
          <button
            onClick={reset}
            className="text-xs text-green-500 hover:text-green-300 underline"
          >
            Run again
          </button>
        </div>
      )}

      {isError && (
        <div className="flex items-start gap-3 px-4 py-3 rounded-xl bg-red-900/30 border border-red-700 text-red-300">
          <span className="text-lg">⚠️</span>
          <div className="flex-1">
            <p className="text-sm font-semibold">Run failed</p>
            {error && <p className="text-xs text-red-400 mt-0.5">{error}</p>}
          </div>
          <button
            onClick={reset}
            className="text-xs text-red-400 hover:text-red-200 underline"
          >
            Try again
          </button>
        </div>
      )}

      {/* Live event feed */}
      {events.length > 0 && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-800 flex items-center justify-between">
            <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
              Live Events
            </span>
            <span className="text-xs text-gray-600 font-mono">{events.length} events</span>
          </div>
          <div className="max-h-[60vh] overflow-y-auto">
            <EventFeed events={events} />
          </div>
        </div>
      )}
    </div>
  )
}

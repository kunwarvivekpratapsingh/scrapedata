import { useResultFiles } from '../../hooks/useResultFiles'
import { useEvalStore } from '../../store/useEvalStore'
import { Spinner } from '../ui/Spinner'

function fileLabel(name: string): string {
  if (name.startsWith('single_question')) return '🔍 ' + name
  if (name.startsWith('eval_results')) return '📊 ' + name
  return '📄 ' + name
}

export function Sidebar() {
  const { files, isLoading, error, refresh } = useResultFiles()
  const { selectedFile, setSelectedFile, currentPage, setCurrentPage } = useEvalStore()

  return (
    <aside className="w-60 shrink-0 bg-gray-950 border-r border-gray-800 flex flex-col">
      {/* Run Eval CTA */}
      <div className="px-4 py-4 border-b border-gray-800">
        <button
          onClick={() => setCurrentPage('run')}
          className={`w-full flex items-center justify-center gap-2 px-3 py-2.5 rounded-lg text-sm font-semibold transition-colors ${
            currentPage === 'run'
              ? 'bg-blue-600 text-white'
              : 'bg-gray-800 text-gray-300 hover:bg-blue-600/20 hover:text-blue-300 border border-gray-700 hover:border-blue-600'
          }`}
        >
          <span>▶</span>
          <span>Run Eval</span>
        </button>
      </div>

      <div className="px-4 py-3 border-b border-gray-800 flex items-center justify-between">
        <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
          Result Files
        </span>
        <button
          onClick={() => refresh()}
          title="Refresh file list"
          className="text-gray-500 hover:text-gray-300 transition-colors text-sm"
        >
          ↺
        </button>
      </div>

      <div className="flex-1 overflow-y-auto py-2">
        {isLoading && (
          <div className="flex justify-center py-8">
            <Spinner size="sm" />
          </div>
        )}
        {error && (
          <p className="text-red-400 text-xs px-4 py-3">
            Failed to load files. Is the API server running?
          </p>
        )}
        {!isLoading && !error && files.length === 0 && (
          <p className="text-gray-600 text-xs px-4 py-3">
            No result files found. Run a pipeline first.
          </p>
        )}
        {files.map((f) => (
          <button
            key={f}
            onClick={() => { setSelectedFile(f); setCurrentPage('dashboard') }}
            className={`w-full text-left px-4 py-2.5 text-sm font-mono truncate transition-colors ${
              selectedFile === f && currentPage === 'dashboard'
                ? 'bg-blue-900/40 text-blue-300 border-r-2 border-blue-500'
                : 'text-gray-400 hover:bg-gray-800/50 hover:text-gray-200'
            }`}
          >
            {fileLabel(f)}
          </button>
        ))}
      </div>

      <div className="px-4 py-3 border-t border-gray-800">
        <p className="text-xs text-gray-600">
          Files auto-refresh every 5s
        </p>
      </div>
    </aside>
  )
}

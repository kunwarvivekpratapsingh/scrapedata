import { useState } from 'react'
import type { QuestionTrace } from '../../types/eval'
import { DifficultyBadge, PassFailBadge } from '../ui/Badge'
import { QuestionDetail } from './QuestionDetail'

interface QuestionRowProps {
  trace: QuestionTrace
  index: number
}

export function QuestionRow({ trace, index }: QuestionRowProps) {
  const [expanded, setExpanded] = useState(false)
  const passed = trace.execution_result?.success ?? false

  return (
    <div
      className={`border rounded-xl overflow-hidden transition-all duration-150 ${
        expanded ? 'border-gray-700' : 'border-gray-800 hover:border-gray-700'
      }`}
    >
      {/* Collapsed header */}
      <button
        className="w-full text-left px-5 py-4 flex items-start gap-4 bg-gray-900/60 hover:bg-gray-900/80 transition-colors"
        onClick={() => setExpanded((v) => !v)}
        type="button"
      >
        {/* Index + id */}
        <div className="shrink-0 flex items-center gap-2 mt-0.5">
          <span className="text-gray-600 font-mono text-xs w-5 text-right">
            {index + 1}
          </span>
          <span className="font-mono text-xs text-blue-400 bg-blue-900/30 px-2 py-0.5 rounded">
            {trace.question.id}
          </span>
        </div>

        {/* Question text */}
        <p
          className={`flex-1 text-sm leading-snug ${
            expanded ? 'text-gray-200' : 'text-gray-300 line-clamp-2'
          }`}
        >
          {trace.question.text}
        </p>

        {/* Badges */}
        <div className="shrink-0 flex items-center gap-2 ml-2">
          <span className="text-xs text-gray-600 font-mono">
            {trace.iterations}×
          </span>
          <DifficultyBadge level={trace.question.difficulty_level} />
          <PassFailBadge passed={passed} />
          <span
            className={`text-gray-500 transition-transform duration-150 text-xs ${
              expanded ? 'rotate-180' : ''
            }`}
          >
            ▼
          </span>
        </div>
      </button>

      {/* Expanded detail */}
      {expanded && (
        <div className="px-5 border-t border-gray-800 bg-gray-950/60">
          <QuestionDetail trace={trace} />
        </div>
      )}
    </div>
  )
}

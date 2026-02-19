import type { QuestionTrace } from '../../types/eval'

interface Row {
  level: string
  total: number
  passed: number
  rate: string
  color: string
}

export function DifficultyTable({ questions }: { questions: QuestionTrace[] }) {
  const levels = ['easy', 'medium', 'hard']
  const rows: Row[] = levels.map((level) => {
    const inLevel = questions.filter(
      (q) => q.question.difficulty_level === level
    )
    const passed = inLevel.filter((q) => q.execution_result?.success).length
    const rate =
      inLevel.length > 0
        ? `${((passed / inLevel.length) * 100).toFixed(0)}%`
        : '—'
    const color =
      level === 'easy'
        ? 'text-green-400'
        : level === 'medium'
        ? 'text-amber-400'
        : 'text-red-400'
    return { level, total: inLevel.length, passed, rate, color }
  })

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
      <div className="px-5 py-3 border-b border-gray-800">
        <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
          By Difficulty
        </p>
      </div>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-xs text-gray-500 border-b border-gray-800">
            <th className="text-left px-5 py-2">Difficulty</th>
            <th className="text-right px-5 py-2">Questions</th>
            <th className="text-right px-5 py-2">Passed</th>
            <th className="text-right px-5 py-2">Pass Rate</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-800/50">
          {rows.map((r) => (
            <tr key={r.level} className="hover:bg-gray-800/30 transition-colors">
              <td className="px-5 py-3">
                <span className={`capitalize font-medium ${r.color}`}>{r.level}</span>
              </td>
              <td className="px-5 py-3 text-right text-gray-300 font-mono">{r.total}</td>
              <td className="px-5 py-3 text-right text-gray-300 font-mono">{r.passed}</td>
              <td className="px-5 py-3 text-right font-mono font-semibold">
                <span className={r.total > 0 ? r.color : 'text-gray-600'}>{r.rate}</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

import type { EvalSummary } from '../../types/eval'

interface CardProps {
  label: string
  value: string | number
  sub?: string
  color?: string
}

function StatCard({ label, value, sub, color = 'text-gray-100' }: CardProps) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
      <p className="text-xs text-gray-500 uppercase tracking-wider mb-2">{label}</p>
      <p className={`text-3xl font-bold font-mono ${color}`}>{value}</p>
      {sub && <p className="text-xs text-gray-500 mt-1">{sub}</p>}
    </div>
  )
}

export function SummaryCards({ summary }: { summary: EvalSummary }) {
  const pct = (summary.pass_rate * 100).toFixed(1)
  const passColor =
    summary.pass_rate >= 0.8
      ? 'text-green-400'
      : summary.pass_rate >= 0.5
      ? 'text-amber-400'
      : 'text-red-400'

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
      <StatCard
        label="Total Questions"
        value={summary.total_questions}
        sub="in this run"
      />
      <StatCard
        label="Pass Rate"
        value={`${pct}%`}
        sub={`${summary.passed} passed · ${summary.failed} failed`}
        color={passColor}
      />
      <StatCard
        label="Avg Exec Time"
        value={
          summary.avg_execution_time_ms > 0
            ? `${summary.avg_execution_time_ms.toFixed(0)}ms`
            : '—'
        }
        sub="per question"
        color="text-teal-400"
      />
      <StatCard
        label="Total Iterations"
        value={summary.total_iterations}
        sub="critic loop iterations"
        color="text-violet-400"
      />
    </div>
  )
}

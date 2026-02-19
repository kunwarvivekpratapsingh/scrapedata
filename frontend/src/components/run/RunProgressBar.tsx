interface RunProgressBarProps {
  done: number
  total: number
}

export function RunProgressBar({ done, total }: RunProgressBarProps) {
  if (total === 0) return null

  const pct = Math.round((done / total) * 100)

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-xs text-gray-400">
        <span className="font-semibold">Questions</span>
        <span className="font-mono">
          {done} / {total}
        </span>
      </div>
      <div className="w-full bg-gray-800 rounded-full h-2 overflow-hidden">
        <div
          className="h-2 rounded-full bg-blue-500 transition-all duration-500"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}

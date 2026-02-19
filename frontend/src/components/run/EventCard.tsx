import type { RunEvent } from '../../types/eval'

interface EventCardProps {
  event: RunEvent
}

function Timestamp({ ts }: { ts: string }) {
  const d = new Date(ts)
  const time = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  return <span className="text-gray-600 font-mono text-xs shrink-0">{time}</span>
}

function QBadge({ id }: { id: string }) {
  return (
    <span className="px-1.5 py-0.5 rounded text-xs font-mono bg-gray-800 text-gray-400 border border-gray-700">
      {id}
    </span>
  )
}

export function EventCard({ event }: EventCardProps) {
  switch (event.type) {
    case 'run_started':
      return (
        <div className="flex items-start gap-3 px-4 py-3 border-b border-gray-800/60">
          <span className="text-lg leading-none">🚀</span>
          <div className="flex-1 min-w-0">
            <p className="text-sm text-gray-200">
              Starting eval —{' '}
              <span className="font-mono text-blue-400">{event.payload.num_questions}</span>{' '}
              questions,{' '}
              <span className="font-mono text-purple-400">{event.payload.difficulty}</span>{' '}
              difficulty
            </p>
          </div>
          <Timestamp ts={event.ts} />
        </div>
      )

    case 'questions_generated':
      return (
        <div className="flex items-start gap-3 px-4 py-3 border-b border-gray-800/60">
          <span className="text-lg leading-none">📋</span>
          <div className="flex-1 min-w-0">
            <p className="text-sm text-gray-200 mb-1.5">
              Generated{' '}
              <span className="font-mono text-blue-400">{event.payload.questions.length}</span>{' '}
              questions
            </p>
            <div className="flex flex-wrap gap-1.5">
              {event.payload.questions.map((q) => (
                <span
                  key={q.id}
                  className={`px-2 py-0.5 rounded text-xs font-mono border ${
                    q.difficulty_level === 'easy'
                      ? 'bg-green-900/30 border-green-700 text-green-400'
                      : q.difficulty_level === 'medium'
                      ? 'bg-yellow-900/30 border-yellow-700 text-yellow-400'
                      : 'bg-red-900/30 border-red-700 text-red-400'
                  }`}
                >
                  {q.id}
                </span>
              ))}
            </div>
          </div>
          <Timestamp ts={event.ts} />
        </div>
      )

    case 'dag_built':
      return (
        <div className="flex items-start gap-3 px-4 py-3 border-b border-gray-800/60">
          <span className="text-lg leading-none">🔧</span>
          <div className="flex-1 min-w-0">
            <p className="text-sm text-gray-300 flex items-center gap-2 flex-wrap">
              <QBadge id={event.payload.question_id} />
              <span>Iter {event.payload.iteration} — DAG built</span>
              <span className="text-gray-500 font-mono text-xs">
                {event.payload.node_count}n · {event.payload.edge_count}e
              </span>
            </p>
            {event.payload.description && (
              <p className="text-xs text-gray-500 mt-0.5 truncate">
                {event.payload.description}
              </p>
            )}
          </div>
          <Timestamp ts={event.ts} />
        </div>
      )

    case 'critic_result':
      return (
        <div className="flex items-start gap-3 px-4 py-3 border-b border-gray-800/60">
          <span className="text-lg leading-none">
            {event.payload.is_approved ? '✅' : '❌'}
          </span>
          <div className="flex-1 min-w-0">
            <p className="text-sm text-gray-300 flex items-center gap-2 flex-wrap">
              <QBadge id={event.payload.question_id} />
              <span>Iter {event.payload.iteration}</span>
              <span
                className={`font-semibold ${
                  event.payload.is_approved ? 'text-green-400' : 'text-red-400'
                }`}
              >
                {event.payload.is_approved ? 'APPROVED' : 'REJECTED'}
              </span>
              {!event.payload.is_approved && (
                <span className="text-xs text-gray-500">
                  {event.payload.issues_count} issue{event.payload.issues_count !== 1 ? 's' : ''}
                </span>
              )}
            </p>
            {event.payload.overall_reasoning && (
              <p className="text-xs text-gray-500 mt-0.5 line-clamp-2">
                {event.payload.overall_reasoning}
              </p>
            )}
          </div>
          <Timestamp ts={event.ts} />
        </div>
      )

    case 'execution_done':
      return (
        <div className="flex items-start gap-3 px-4 py-3 border-b border-gray-800/60">
          <span className="text-lg leading-none">⚡</span>
          <div className="flex-1 min-w-0">
            <p className="text-sm text-gray-300 flex items-center gap-2 flex-wrap">
              <QBadge id={event.payload.question_id} />
              <span
                className={
                  event.payload.success ? 'text-green-400' : 'text-red-400'
                }
              >
                {event.payload.success ? 'Executed' : 'Exec failed'}
              </span>
              {event.payload.success && (
                <span className="text-xs text-gray-500 font-mono">
                  {event.payload.execution_time_ms.toFixed(0)}ms
                </span>
              )}
            </p>
            {event.payload.success && event.payload.final_answer !== null && (
              <p className="text-xs text-teal-400 font-mono mt-0.5 truncate">
                → {JSON.stringify(event.payload.final_answer)}
              </p>
            )}
            {!event.payload.success && event.payload.error && (
              <p className="text-xs text-red-500 mt-0.5 line-clamp-2">
                {event.payload.error}
              </p>
            )}
          </div>
          <Timestamp ts={event.ts} />
        </div>
      )

    case 'question_complete':
      return (
        <div className="flex items-start gap-3 px-4 py-3 border-b border-gray-800/60 bg-gray-900/40">
          <span className="text-lg leading-none">
            {event.payload.success ? '🏆' : '💔'}
          </span>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold flex items-center gap-2 flex-wrap">
              <QBadge id={event.payload.question_id} />
              <span
                className={
                  event.payload.success ? 'text-green-300' : 'text-red-300'
                }
              >
                Complete
              </span>
              <span className="text-gray-500 text-xs font-normal">
                in {event.payload.total_iterations} iteration
                {event.payload.total_iterations !== 1 ? 's' : ''}
              </span>
            </p>
          </div>
          <Timestamp ts={event.ts} />
        </div>
      )

    case 'run_complete': {
      const s = event.payload.summary
      return (
        <div className="flex items-start gap-3 px-4 py-4 border-b border-gray-800/60 bg-blue-950/30">
          <span className="text-lg leading-none">🏁</span>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-bold text-blue-300 mb-1">Run complete</p>
            <div className="flex gap-4 text-xs font-mono">
              <span className="text-green-400">{s.passed} passed</span>
              <span className="text-red-400">{s.failed} failed</span>
              <span className="text-gray-400">
                {(s.pass_rate * 100).toFixed(0)}% pass rate
              </span>
            </div>
            <p className="text-xs text-gray-500 mt-1">
              Saved: {event.payload.output_file}
            </p>
          </div>
          <Timestamp ts={event.ts} />
        </div>
      )
    }

    case 'error':
      return (
        <div className="flex items-start gap-3 px-4 py-3 border-b border-red-900/40 bg-red-950/20">
          <span className="text-lg leading-none">⚠️</span>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold text-red-400">Error</p>
            <p className="text-xs text-red-500 mt-0.5">{event.payload.message}</p>
          </div>
          <Timestamp ts={event.ts} />
        </div>
      )

    default:
      return null
  }
}

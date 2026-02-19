import { classifyLog, LOG_ROLE_DOT } from '../../utils/classifyLog'

export function ConversationTimeline({ messages }: { messages: string[] }) {
  if (!messages.length) {
    return <p className="text-xs text-gray-500 py-2">No messages recorded.</p>
  }

  return (
    <div className="space-y-2">
      {messages.map((msg, i) => {
        const role = classifyLog(msg)
        const dot = LOG_ROLE_DOT[role]
        return (
          <div key={i} className="flex gap-3 items-start">
            <div className="mt-1.5 shrink-0">
              <span className={`inline-block w-2 h-2 rounded-full ${dot}`} />
            </div>
            <p className="text-xs text-gray-400 font-mono leading-relaxed break-all">
              {msg}
            </p>
          </div>
        )
      })}
    </div>
  )
}

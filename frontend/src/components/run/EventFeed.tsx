import { useEffect, useRef } from 'react'
import type { RunEvent } from '../../types/eval'
import { EventCard } from './EventCard'

interface EventFeedProps {
  events: RunEvent[]
}

export function EventFeed({ events }: EventFeedProps) {
  const bottomRef = useRef<HTMLDivElement>(null)

  // Auto-scroll to bottom on each new event
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [events.length])

  if (events.length === 0) {
    return (
      <div className="flex items-center justify-center h-40 text-gray-600 text-sm">
        Events will appear here once the run starts…
      </div>
    )
  }

  return (
    <div className="divide-y divide-gray-800/40">
      {events.map((ev, i) => (
        <EventCard key={i} event={ev} />
      ))}
      <div ref={bottomRef} />
    </div>
  )
}

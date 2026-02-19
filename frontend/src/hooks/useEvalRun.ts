/**
 * useEvalRun — orchestrates POST /api/run + SSE stream.
 *
 * State machine: idle → submitting → streaming → done | error
 *
 * Key design decisions:
 * - EventSource.onerror fires both on genuine network errors AND on normal
 *   stream close (when the server sends the None sentinel). We track whether
 *   we intentionally closed the stream via a ref so we can ignore expected
 *   close events.
 * - The error phase is set via onmessage (from the "error" SSE event type)
 *   before the stream closes, so onerror must not overwrite it.
 */
import { useState, useRef, useCallback } from 'react'
import { startRun, openRunEventSource } from '../api/client'
import { useEvalStore } from '../store/useEvalStore'
import type { RunConfig, RunEvent } from '../types/eval'

export type RunPhase = 'idle' | 'submitting' | 'streaming' | 'done' | 'error'

export interface RunProgress {
  done: number
  total: number
}

export interface RunState {
  phase: RunPhase
  runId: string | null
  events: RunEvent[]
  progress: RunProgress
  outputFile: string | null
  error: string | null
}

const INITIAL_STATE: RunState = {
  phase: 'idle',
  runId: null,
  events: [],
  progress: { done: 0, total: 0 },
  outputFile: null,
  error: null,
}

export function useEvalRun() {
  const [state, setState] = useState<RunState>(INITIAL_STATE)
  const esRef = useRef<EventSource | null>(null)
  // Track intentional closes so onerror doesn't mis-fire
  const intentionalCloseRef = useRef(false)
  const { setCurrentPage, setSelectedFile } = useEvalStore()

  const closeStream = useCallback((intentional = true) => {
    if (esRef.current) {
      intentionalCloseRef.current = intentional
      esRef.current.close()
      esRef.current = null
    }
  }, [])

  const reset = useCallback(() => {
    closeStream(true)
    setState(INITIAL_STATE)
  }, [closeStream])

  const run = useCallback(async (config: RunConfig) => {
    closeStream(true)
    intentionalCloseRef.current = false
    setState({ ...INITIAL_STATE, phase: 'submitting' })

    let runId: string
    try {
      runId = await startRun(config)
    } catch (err) {
      setState((s) => ({
        ...s,
        phase: 'error',
        error: err instanceof Error ? err.message : String(err),
      }))
      return
    }

    setState((s) => ({ ...s, phase: 'streaming', runId }))

    const es = openRunEventSource(runId)
    esRef.current = es
    intentionalCloseRef.current = false

    es.onmessage = (ev: MessageEvent) => {
      let event: RunEvent
      try {
        event = JSON.parse(ev.data) as RunEvent
      } catch {
        return // ignore malformed frames
      }

      setState((s) => {
        const events = [...s.events, event]
        let progress = { ...s.progress }
        let phase: RunPhase = s.phase
        let outputFile = s.outputFile
        let error = s.error

        switch (event.type) {
          case 'run_started':
            progress = { done: 0, total: event.payload.num_questions }
            break
          case 'question_complete':
            progress = { ...progress, done: progress.done + 1 }
            break
          case 'run_complete':
            outputFile = event.payload.output_file
            phase = 'done'
            break
          case 'error':
            phase = 'error'
            error = event.payload.message
            break
        }

        return { ...s, events, progress, phase, outputFile, error }
      })

      // On completion: intentionally close and auto-load result
      if (event.type === 'run_complete') {
        closeStream(true)
        const file = event.payload.output_file
        setTimeout(() => {
          setSelectedFile(file)
          setCurrentPage('dashboard')
        }, 1500)
      }

      // On error event from pipeline: intentionally close
      if (event.type === 'error') {
        closeStream(true)
      }
    }

    es.onerror = () => {
      // If we intentionally closed the stream (after run_complete or error event),
      // the EventSource will fire onerror as the connection drops — ignore it.
      if (intentionalCloseRef.current) return

      // Genuine unexpected disconnection
      setState((s) => {
        // Never overwrite a terminal phase set by onmessage
        if (s.phase === 'done' || s.phase === 'error') return s
        return { ...s, phase: 'error', error: 'Lost connection to server. Is the API running?' }
      })
      closeStream(true)
    }
  }, [closeStream, setCurrentPage, setSelectedFile])

  return { ...state, run, reset }
}

/**
 * useEvalRun — orchestrates POST /api/run + SSE stream.
 *
 * State machine: idle → submitting → streaming → done | error
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
  const { setCurrentPage, setSelectedFile } = useEvalStore()

  // Close any existing SSE connection
  const closeStream = useCallback(() => {
    if (esRef.current) {
      esRef.current.close()
      esRef.current = null
    }
  }, [])

  const reset = useCallback(() => {
    closeStream()
    setState(INITIAL_STATE)
  }, [closeStream])

  const run = useCallback(async (config: RunConfig) => {
    closeStream()
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
            break
        }

        return { ...s, events, progress, phase, outputFile }
      })

      // On completion: switch back to dashboard and auto-load result
      if (event.type === 'run_complete') {
        closeStream()
        const file = event.payload.output_file
        // Brief delay so the "done" state renders first
        setTimeout(() => {
          setSelectedFile(file)
          setCurrentPage('dashboard')
        }, 1500)
      }

      if (event.type === 'error') {
        closeStream()
      }
    }

    es.onerror = () => {
      // If already done, ignore the connection-close error
      setState((s) => {
        if (s.phase === 'done') return s
        return { ...s, phase: 'error', error: 'Connection to server lost.' }
      })
      closeStream()
    }
  }, [closeStream, setCurrentPage, setSelectedFile])

  return { ...state, run, reset }
}

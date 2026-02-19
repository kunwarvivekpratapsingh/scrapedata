// API client — thin fetch wrappers for /api/* endpoints
import type { RunConfig } from '../types/eval'

export async function fetchFiles(): Promise<string[]> {
  const res = await fetch('/api/files')
  if (!res.ok) throw new Error(`Failed to list files: ${res.statusText}`)
  const data = await res.json()
  return data.files as string[]
}

export async function fetchResults(filename: string): Promise<unknown> {
  const res = await fetch(`/api/results/${encodeURIComponent(filename)}`)
  if (!res.ok) throw new Error(`Failed to load ${filename}: ${res.statusText}`)
  return res.json()
}

// ── Live eval runner ──────────────────────────────────────────────────────────

/**
 * POST /api/run — start a new eval run.
 * Returns the run_id to open the SSE stream.
 */
export async function startRun(config: RunConfig): Promise<string> {
  const res = await fetch('/api/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  })
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(detail.detail ?? `Failed to start run: ${res.statusText}`)
  }
  const data = await res.json()
  return data.run_id as string
}

/**
 * Open an SSE stream for a run.
 * Returns an EventSource — caller is responsible for closing it.
 */
export function openRunEventSource(runId: string): EventSource {
  return new EventSource(`/api/run/${runId}/events`)
}

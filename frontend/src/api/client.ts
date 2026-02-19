// API client — thin fetch wrappers for /api/* endpoints

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

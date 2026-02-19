import useSWR from 'swr'
import { fetchFiles } from '../api/client'

export function useResultFiles() {
  const { data, error, isLoading, mutate } = useSWR<string[]>(
    '/api/files',
    fetchFiles,
    { refreshInterval: 5000 } // auto-refresh every 5s to pick up new runs
  )
  return {
    files: data ?? [],
    isLoading,
    error,
    refresh: mutate,
  }
}

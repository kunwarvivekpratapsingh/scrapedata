import useSWR from 'swr'
import { fetchResults } from '../api/client'
import type { EvalResults } from '../types/eval'
import { convertToEvalResults } from '../utils/convertSingleQuestion'

async function fetcher(filename: string): Promise<EvalResults> {
  const raw = await fetchResults(filename)
  return convertToEvalResults(raw, filename)
}

export function useEvalResults(filename: string | null) {
  const { data, error, isLoading } = useSWR<EvalResults>(
    filename ? filename : null,
    fetcher,
    { revalidateOnFocus: false }
  )
  return { results: data ?? null, isLoading, error }
}

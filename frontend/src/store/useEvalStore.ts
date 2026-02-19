import { create } from 'zustand'
import type { EvalResults } from '../types/eval'

interface EvalStore {
  selectedFile: string | null
  evalResults: EvalResults | null
  setSelectedFile: (file: string | null) => void
  setEvalResults: (results: EvalResults | null) => void
}

export const useEvalStore = create<EvalStore>((set) => ({
  selectedFile: null,
  evalResults: null,
  setSelectedFile: (file) => set({ selectedFile: file, evalResults: null }),
  setEvalResults: (results) => set({ evalResults: results }),
}))

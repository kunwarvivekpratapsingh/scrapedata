import { create } from 'zustand'
import type { EvalResults } from '../types/eval'

export type Page = 'dashboard' | 'run'

interface EvalStore {
  // ── Navigation ──────────────────────────────────────────────────────────
  currentPage: Page
  setCurrentPage: (page: Page) => void

  // ── Dashboard state ──────────────────────────────────────────────────────
  selectedFile: string | null
  evalResults: EvalResults | null
  setSelectedFile: (file: string | null) => void
  setEvalResults: (results: EvalResults | null) => void
}

export const useEvalStore = create<EvalStore>((set) => ({
  currentPage: 'dashboard',
  setCurrentPage: (page) => set({ currentPage: page }),

  selectedFile: null,
  evalResults: null,
  setSelectedFile: (file) => set({ selectedFile: file, evalResults: null }),
  setEvalResults: (results) => set({ evalResults: results }),
}))

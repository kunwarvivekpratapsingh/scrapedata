import { useEffect } from 'react'
import { useEvalStore } from '../store/useEvalStore'
import { useEvalResults } from '../hooks/useEvalResults'
import { SummaryCards } from '../components/dashboard/SummaryCards'
import { DifficultyTable } from '../components/dashboard/DifficultyTable'
import { QuestionList } from '../components/dashboard/QuestionList'
import { Spinner } from '../components/ui/Spinner'
import { EmptyState } from '../components/ui/EmptyState'

export function DashboardPage() {
  const { selectedFile, setEvalResults } = useEvalStore()
  const { results, isLoading, error } = useEvalResults(selectedFile)

  useEffect(() => {
    setEvalResults(results)
  }, [results, setEvalResults])

  if (!selectedFile) {
    return (
      <EmptyState
        icon="📂"
        title="Select a result file"
        description="Choose an eval_results.json or single_question_result.json from the sidebar to inspect results."
      />
    )
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Spinner size="lg" />
      </div>
    )
  }

  if (error) {
    return (
      <EmptyState
        icon="⚠️"
        title="Failed to load results"
        description={String(error?.message ?? error)}
      />
    )
  }

  if (!results) return null

  const { summary, questions } = results

  return (
    <div className="px-6 py-6 space-y-6 max-w-7xl mx-auto">
      {/* Summary cards */}
      <SummaryCards summary={summary} />

      {/* Difficulty breakdown + question list side-by-side on wide screens */}
      <div className="grid grid-cols-1 lg:grid-cols-[280px_1fr] gap-6">
        <DifficultyTable questions={questions} />
        <div>
          <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">
            Questions ({questions.length})
          </p>
          <QuestionList questions={questions} />
        </div>
      </div>
    </div>
  )
}

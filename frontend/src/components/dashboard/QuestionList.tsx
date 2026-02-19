import type { QuestionTrace } from '../../types/eval'
import { QuestionRow } from '../question/QuestionRow'

interface QuestionListProps {
  questions: QuestionTrace[]
}

export function QuestionList({ questions }: QuestionListProps) {
  if (!questions.length) {
    return <p className="text-sm text-gray-500 py-4">No questions found.</p>
  }

  return (
    <div className="space-y-2">
      {questions.map((trace, i) => (
        <QuestionRow key={trace.question.id} trace={trace} index={i} />
      ))}
    </div>
  )
}

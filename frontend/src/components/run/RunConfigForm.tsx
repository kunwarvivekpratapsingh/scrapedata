/**
 * RunConfigForm — difficulty selector + question count slider + run button.
 * Disabled while a run is in progress.
 */
import { useState } from 'react'
import type { RunConfig, RunDifficulty } from '../../types/eval'
import { Spinner } from '../ui/Spinner'

interface RunConfigFormProps {
  disabled: boolean
  onRun: (config: RunConfig) => void
}

const DIFFICULTIES: { value: RunDifficulty; label: string }[] = [
  { value: 'all',    label: 'All' },
  { value: 'easy',   label: 'Easy' },
  { value: 'medium', label: 'Medium' },
  { value: 'hard',   label: 'Hard' },
]

export function RunConfigForm({ disabled, onRun }: RunConfigFormProps) {
  const [difficulty, setDifficulty] = useState<RunDifficulty>('all')
  const [numQuestions, setNumQuestions] = useState(5)

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!disabled) onRun({ difficulty, num_questions: numQuestions })
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="bg-gray-900 border border-gray-800 rounded-xl p-6 space-y-6"
    >
      {/* Difficulty */}
      <div className="space-y-2">
        <label className="text-xs font-semibold text-gray-400 uppercase tracking-wider block">
          Difficulty
        </label>
        <div className="flex gap-2 flex-wrap">
          {DIFFICULTIES.map(({ value, label }) => (
            <button
              key={value}
              type="button"
              disabled={disabled}
              onClick={() => setDifficulty(value)}
              className={`px-4 py-1.5 rounded-lg text-sm font-medium border transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${
                difficulty === value
                  ? 'bg-blue-600 border-blue-500 text-white'
                  : 'bg-gray-800 border-gray-700 text-gray-300 hover:border-gray-600 hover:text-white'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Question count */}
      <div className="space-y-2">
        <label className="text-xs font-semibold text-gray-400 uppercase tracking-wider block">
          Questions&nbsp;
          <span className="text-blue-400 font-mono">{numQuestions} / 10</span>
        </label>
        <input
          type="range"
          min={1}
          max={10}
          step={1}
          value={numQuestions}
          disabled={disabled}
          onChange={(e) => setNumQuestions(Number(e.target.value))}
          className="w-full accent-blue-500 disabled:opacity-40"
        />
        <div className="flex justify-between text-xs text-gray-600 font-mono">
          <span>1</span>
          <span>10</span>
        </div>
      </div>

      {/* Run button */}
      <button
        type="submit"
        disabled={disabled}
        className="w-full flex items-center justify-center gap-2 px-6 py-3 rounded-xl bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700 disabled:cursor-not-allowed text-white font-semibold transition-colors"
      >
        {disabled ? (
          <>
            <Spinner size="sm" />
            <span>Running…</span>
          </>
        ) : (
          <>
            <span>▶</span>
            <span>Run Evaluation</span>
          </>
        )}
      </button>
    </form>
  )
}

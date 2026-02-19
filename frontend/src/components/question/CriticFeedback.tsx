import type { CriticFeedback as CriticFeedbackType } from '../../types/eval'

export function CriticFeedback({ feedback }: { feedback: CriticFeedbackType }) {
  const rejectedLayers = feedback.layer_validations.filter((lv) => !lv.is_valid)

  return (
    <div className="space-y-3 text-sm">
      {/* Overall reasoning */}
      <div className="bg-gray-900 rounded-lg p-3 text-gray-300 text-xs leading-relaxed">
        {feedback.overall_reasoning}
      </div>

      {/* Layer issues */}
      {rejectedLayers.map((lv) => (
        <div
          key={lv.layer_index}
          className="bg-amber-950/30 border border-amber-800/40 rounded-lg p-3"
        >
          <p className="text-xs font-semibold text-amber-300 mb-2">
            Layer {lv.layer_index} — {lv.nodes_in_layer.join(', ')}
          </p>
          <ul className="space-y-1">
            {lv.issues.map((issue, i) => (
              <li key={i} className="text-xs text-amber-200/80 flex gap-2">
                <span className="shrink-0 text-amber-500">·</span>
                {issue}
              </li>
            ))}
          </ul>
        </div>
      ))}

      {/* Specific errors */}
      {feedback.specific_errors.length > 0 && (
        <div className="bg-red-950/30 border border-red-800/40 rounded-lg p-3">
          <p className="text-xs font-semibold text-red-300 mb-2">Specific Errors</p>
          <ul className="space-y-1">
            {feedback.specific_errors.map((e, i) => (
              <li key={i} className="text-xs text-red-200/80 flex gap-2">
                <span className="shrink-0 text-red-500">·</span>
                {e}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Suggestions */}
      {feedback.suggestions.length > 0 && (
        <div className="bg-blue-950/30 border border-blue-800/40 rounded-lg p-3">
          <p className="text-xs font-semibold text-blue-300 mb-2">Suggestions</p>
          <ul className="space-y-1">
            {feedback.suggestions.map((s, i) => (
              <li key={i} className="text-xs text-blue-200/80 flex gap-2">
                <span className="shrink-0 text-blue-400">→</span>
                {s}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

/**
 * Pretty-print any answer value for display.
 */
export function formatAnswer(value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'string') return value
  if (typeof value === 'number') return String(value)
  if (typeof value === 'boolean') return value ? 'true' : 'false'
  if (Array.isArray(value)) {
    // Nested arrays → table-like formatting
    if (value.length > 0 && Array.isArray(value[0])) {
      return value
        .map((row, i) =>
          Array.isArray(row) ? `[${i}] ${row.join('  |  ')}` : String(row)
        )
        .join('\n')
    }
    return JSON.stringify(value, null, 2)
  }
  return JSON.stringify(value, null, 2)
}

export function formatAnswerShort(value: unknown, maxLen = 80): string {
  const full = formatAnswer(value)
  if (full.length <= maxLen) return full
  return full.slice(0, maxLen) + '…'
}

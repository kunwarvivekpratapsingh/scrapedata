/**
 * Format a node's output for display in the outputs table.
 */
export function formatNodeOutput(output: unknown, maxLen = 120): string {
  if (output === null || output === undefined) return '—'
  const str = typeof output === 'string' ? output : JSON.stringify(output)
  if (str.length <= maxLen) return str
  return str.slice(0, maxLen) + '…'
}

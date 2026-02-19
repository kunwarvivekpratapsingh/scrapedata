/**
 * Classify a log message string into a role for color-coding.
 */
export type LogRole = 'builder' | 'critic' | 'executor' | 'system' | 'other'

export function classifyLog(message: string): LogRole {
  const m = message.toLowerCase()
  if (m.includes('[dagbuilder]') || m.includes('dag_builder') || m.includes('building dag')) return 'builder'
  if (m.includes('[critic]') || m.includes('critic') || m.includes('approved') || m.includes('rejected')) return 'critic'
  if (m.includes('[executor]') || m.includes('executing') || m.includes('success') || m.includes('failed')) return 'executor'
  if (m.includes('[system]') || m.includes('[orchestrator]') || m.includes('[questiongenerator]')) return 'system'
  return 'other'
}

export const LOG_ROLE_STYLES: Record<LogRole, string> = {
  builder:  'bg-blue-950 border-blue-700 text-blue-200',
  critic:   'bg-violet-950 border-violet-700 text-violet-200',
  executor: 'bg-teal-950 border-teal-700 text-teal-200',
  system:   'bg-gray-800 border-gray-600 text-gray-300',
  other:    'bg-gray-900 border-gray-700 text-gray-400',
}

export const LOG_ROLE_DOT: Record<LogRole, string> = {
  builder:  'bg-blue-400',
  critic:   'bg-violet-400',
  executor: 'bg-teal-400',
  system:   'bg-gray-400',
  other:    'bg-gray-600',
}

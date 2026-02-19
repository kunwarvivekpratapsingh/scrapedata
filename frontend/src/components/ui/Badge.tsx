import type { ReactNode } from 'react'

interface BadgeProps {
  children: ReactNode
  variant?: 'green' | 'red' | 'blue' | 'violet' | 'amber' | 'teal' | 'gray'
  size?: 'sm' | 'md'
}

const VARIANT_STYLES = {
  green:  'bg-green-900/60 text-green-300 border border-green-700/50',
  red:    'bg-red-900/60 text-red-300 border border-red-700/50',
  blue:   'bg-blue-900/60 text-blue-300 border border-blue-700/50',
  violet: 'bg-violet-900/60 text-violet-300 border border-violet-700/50',
  amber:  'bg-amber-900/60 text-amber-300 border border-amber-700/50',
  teal:   'bg-teal-900/60 text-teal-300 border border-teal-700/50',
  gray:   'bg-gray-800 text-gray-400 border border-gray-700',
}

const SIZE_STYLES = {
  sm: 'px-1.5 py-0.5 text-xs',
  md: 'px-2.5 py-1 text-xs font-medium',
}

export function Badge({ children, variant = 'gray', size = 'md' }: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center rounded-full font-mono ${VARIANT_STYLES[variant]} ${SIZE_STYLES[size]}`}
    >
      {children}
    </span>
  )
}

export function DifficultyBadge({ level }: { level: string }) {
  const map: Record<string, { variant: BadgeProps['variant']; label: string }> = {
    easy:   { variant: 'green',  label: 'Easy' },
    medium: { variant: 'amber',  label: 'Medium' },
    hard:   { variant: 'red',    label: 'Hard' },
  }
  const cfg = map[level.toLowerCase()] ?? { variant: 'gray', label: level }
  return <Badge variant={cfg.variant}>{cfg.label}</Badge>
}

export function PassFailBadge({ passed }: { passed: boolean }) {
  return (
    <Badge variant={passed ? 'green' : 'red'}>
      {passed ? '✓ PASS' : '✗ FAIL'}
    </Badge>
  )
}

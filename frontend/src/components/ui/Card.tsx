import type { ReactNode } from 'react'

interface CardProps {
  children: ReactNode
  className?: string
  padding?: 'none' | 'sm' | 'md' | 'lg'
}

const PAD = {
  none: '',
  sm:   'p-3',
  md:   'p-5',
  lg:   'p-6',
}

export function Card({ children, className = '', padding = 'md' }: CardProps) {
  return (
    <div
      className={`bg-gray-900 border border-gray-800 rounded-xl ${PAD[padding]} ${className}`}
    >
      {children}
    </div>
  )
}

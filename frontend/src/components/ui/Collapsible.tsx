import { useState, type ReactNode } from 'react'

interface CollapsibleProps {
  trigger: ReactNode
  children: ReactNode
  defaultOpen?: boolean
  className?: string
}

export function Collapsible({
  trigger,
  children,
  defaultOpen = false,
  className = '',
}: CollapsibleProps) {
  const [open, setOpen] = useState(defaultOpen)

  return (
    <div className={className}>
      <button
        className="w-full text-left flex items-center gap-2 focus:outline-none"
        onClick={() => setOpen((v) => !v)}
        type="button"
      >
        <span
          className="text-gray-500 transition-transform duration-150"
          style={{ transform: open ? 'rotate(90deg)' : 'rotate(0deg)' }}
        >
          ▶
        </span>
        {trigger}
      </button>
      {open && <div className="mt-2">{children}</div>}
    </div>
  )
}

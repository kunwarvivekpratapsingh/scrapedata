import { useEffect, useRef } from 'react'
import hljs from 'highlight.js/lib/core'
import python from 'highlight.js/lib/languages/python'
import json from 'highlight.js/lib/languages/json'
import 'highlight.js/styles/base16/mocha.css'

hljs.registerLanguage('python', python)
hljs.registerLanguage('json', json)

interface CodeBlockProps {
  code: string
  language?: 'python' | 'json' | 'text'
  className?: string
}

export function CodeBlock({ code, language = 'python', className = '' }: CodeBlockProps) {
  const ref = useRef<HTMLElement>(null)

  useEffect(() => {
    if (ref.current) {
      ref.current.removeAttribute('data-highlighted')
      ref.current.textContent = code
      if (language !== 'text') {
        hljs.highlightElement(ref.current)
      }
    }
  }, [code, language])

  return (
    <pre
      className={`overflow-auto rounded-lg text-xs leading-relaxed font-mono ${className}`}
      style={{ background: '#1e1e2e', padding: '12px 16px' }}
    >
      <code ref={ref} className={`language-${language}`} />
    </pre>
  )
}

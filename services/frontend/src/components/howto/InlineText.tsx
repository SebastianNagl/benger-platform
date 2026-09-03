'use client'

import Link from 'next/link'
import { Fragment } from 'react'

/**
 * Minimal inline formatting for guide copy: `code`, **bold**, *italic* and
 * [label](href). Internal hrefs render as Next links; anything else as a
 * plain anchor. Deliberately tiny — guides are short, hand-written strings.
 */
const TOKEN = /(`[^`]+`|\*\*[^*]+\*\*|\*[^*\s][^*]*\*|\[[^\]]+\]\([^)]+\))/g

export function InlineText({ text }: { text: string }) {
  const parts = text.split(TOKEN)
  return (
    <>
      {parts.map((part, i) => {
        if (part.startsWith('`') && part.endsWith('`')) {
          return (
            <code
              key={i}
              className="rounded bg-zinc-100 px-1 py-0.5 font-mono text-[0.85em] text-zinc-800 dark:bg-zinc-800 dark:text-zinc-200"
            >
              {part.slice(1, -1)}
            </code>
          )
        }
        if (part.startsWith('**') && part.endsWith('**')) {
          return (
            <strong key={i} className="font-semibold text-zinc-900 dark:text-white">
              {part.slice(2, -2)}
            </strong>
          )
        }
        if (part.length > 2 && part.startsWith('*') && part.endsWith('*')) {
          return <em key={i}>{part.slice(1, -1)}</em>
        }
        const link = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(part)
        if (link) {
          const [, label, href] = link
          const cls =
            'font-medium text-emerald-600 underline decoration-emerald-300 underline-offset-2 hover:text-emerald-500 dark:text-emerald-400 dark:decoration-emerald-800'
          return href.startsWith('/') ? (
            <Link key={i} href={href} className={cls}>
              {label}
            </Link>
          ) : (
            <a key={i} href={href} className={cls} target="_blank" rel="noopener noreferrer">
              {label}
            </a>
          )
        }
        return <Fragment key={i}>{part}</Fragment>
      })}
    </>
  )
}

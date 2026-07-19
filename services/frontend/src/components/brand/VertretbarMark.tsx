import type { SVGProps } from 'react'

/**
 * Vertretbar brand mark: a solid circle with a white checkmark – the
 * "vertretbar = defensible" seal. Lives in platform because the open-core
 * shell renders it too (login/register wordmarks on vertretbar.net); the
 * extended student shell imports it via `@/components/brand/VertretbarMark`.
 *
 * The circle takes `currentColor`, so callers tint it with a text-* class
 * (canonically text-emerald-500); the check stays white in both themes.
 * Keep in sync with the favicon at public/vertretbar-icon.svg.
 */
export function VertretbarMarkIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true" {...props}>
      <circle cx="12" cy="12" r="11" fill="currentColor" />
      <path
        d="M7 12.5l3.2 3.2L17 9"
        stroke="#fff"
        strokeWidth={2.5}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

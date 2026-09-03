/**
 * @jest-environment jsdom
 *
 * /architecture renders every section of data/architecture.ts in the
 * active locale, with anchors, the overview diagram and a table of contents.
 */
import '@testing-library/jest-dom'
import { render, screen } from '@testing-library/react'

import { ARCHITECTURE_SECTIONS } from '@/data/architecture'

import ArchitecturePage from '../page'

let mockLocale = 'de'
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({ locale: mockLocale, t: (key: string, fallback?: string) => fallback ?? key }),
}))
jest.mock('@/components/shared/ResponsiveContainer', () => ({
  ResponsiveContainer: ({ children }: any) => <div>{children}</div>,
}))
jest.mock('@/components/shared/Breadcrumb', () => ({ Breadcrumb: () => <nav data-testid="breadcrumb" /> }))
jest.mock('next/link', () => ({
  __esModule: true,
  default: ({ href, children, ...rest }: any) => <a href={href} {...rest}>{children}</a>,
}))

beforeEach(() => {
  mockLocale = 'de'
})

describe('ArchitecturePage', () => {
  it('renders every section with its anchor and German title', () => {
    render(<ArchitecturePage />)
    for (const s of ARCHITECTURE_SECTIONS) {
      const section = screen.getByTestId(`architecture-${s.id}`)
      expect(section).toHaveAttribute('id', s.id)
      expect(section.querySelector('h2')).toHaveTextContent(s.title.de)
    }
  })

  it('shows the overview diagram with the two repositories and the three stores', () => {
    render(<ArchitecturePage />)
    const pre = screen.getByTestId('architecture-overview').querySelector('pre')
    expect(pre).toHaveTextContent('benger-platform')
    expect(pre).toHaveTextContent('benger-extended')
    expect(pre).toHaveTextContent('PostgreSQL')
    expect(pre).toHaveTextContent('MinIO')
  })

  it('links every section from the table of contents', () => {
    render(<ArchitecturePage />)
    const toc = screen.getByTestId('architecture-toc')
    for (const s of ARCHITECTURE_SECTIONS) {
      expect(toc.querySelector(`a[href="#${s.id}"]`)).toBeInTheDocument()
    }
  })

  it('renders inline formatting and the English copy when the locale is en', () => {
    mockLocale = 'en'
    render(<ArchitecturePage />)
    const overview = screen.getByTestId('architecture-overview')
    expect(overview).toHaveTextContent('open-core system')
    expect(overview.querySelector('strong')).toHaveTextContent('open-core system')
    expect(overview.querySelector('code')).toHaveTextContent('benger-platform')
  })
})

describe('ARCHITECTURE_SECTIONS content rules', () => {
  it('has unique ids and parallel bilingual bullet lists', () => {
    const ids = ARCHITECTURE_SECTIONS.map((s) => s.id)
    expect(new Set(ids).size).toBe(ids.length)
    for (const s of ARCHITECTURE_SECTIONS) {
      expect(s.bullets.de.length).toBe(s.bullets.en.length)
      expect(s.bullets.de.length).toBeGreaterThan(0)
    }
  })

  it('does not advertise things that do not exist', () => {
    const text = JSON.stringify(ARCHITECTURE_SECTIONS)
    expect(text).not.toMatch(/COCO|CoNLL|Horizontal Pod Autoscal/i)
  })
})

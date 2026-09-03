/**
 * Tests for the report reader page (/reports/[id]).
 *
 * Renders the page from `{ report, snapshot }` with the shared snapshot
 * fixture and asserts header, stat tiles, sections, ranking/config behaviour,
 * chart wiring and the empty/draft states.
 */

import React from 'react'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: jest.fn(), replace: jest.fn(), prefetch: jest.fn() }),
}))

jest.mock('next/link', () => ({
  __esModule: true,
  default: ({ href, children, ...rest }: any) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}))

jest.mock('recharts', () => require('@/components/reports/view/__mocks__/testUtils').rechartsMock())

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    locale: 'de',
    t: (key: string, fallback?: string | Record<string, any>, vars?: Record<string, any>) => {
      const base = typeof fallback === 'string' ? fallback : key
      const v = typeof fallback === 'string' ? vars : fallback
      if (!v) return base
      return base.replace(/\{(\w+)\}/g, (m, name) => (v[name] !== undefined ? String(v[name]) : m))
    },
  }),
}))

let mockAuth: any = null
jest.mock('@/contexts/AuthContext', () => ({
  useOptionalAuth: () => mockAuth,
}))

jest.mock('@/lib/api/evaluation-types', () => ({
  getMetricDefinitions: () => ({
    llm_judge_falloesung: { display_name: 'Falllösung LLM Judge', display_scale: '0-100' },
    llm_judge_falloesung_grade_points: { display_name: 'Notenpunkte (Falllösung)', display_scale: '0-18' },
  }),
}))

jest.mock('@/components/shared/ResponsiveContainer', () => ({
  ResponsiveContainer: ({ children }: any) => <div data-testid="responsive-container">{children}</div>,
}))

jest.mock('@/components/shared/Breadcrumb', () => ({
  Breadcrumb: ({ items }: any) => (
    <nav data-testid="breadcrumb">
      {items.map((item: any, i: number) => (
        <span key={i}>{item.label}</span>
      ))}
    </nav>
  ),
}))

jest.mock('@/lib/api/reports', () => ({
  getReportData: jest.fn(),
}))

let mockUseResult = { id: 'report-1' }
jest.mock('react', () => ({
  ...jest.requireActual('react'),
  use: (promise: any) => (promise && typeof promise.then === 'function' ? mockUseResult : promise),
}))

import { REPORT_SNAPSHOT_FIXTURE } from '@/lib/reports/fixture'
import { getReportData } from '@/lib/api/reports'
import ReportViewerPage, { classifyLoadError } from '../page'

const mockGetReportData = getReportData as jest.Mock

function makeReport(overrides: any = {}) {
  const base = {
    id: 'report-1',
    project_id: 'project-1',
    project_title: 'Benchathon 2026',
    is_published: true,
    is_public: true,
    published_at: '2026-09-01T10:00:00Z',
    published_by: 'u',
    created_by: 'u',
    created_at: '2026-08-01T10:00:00Z',
    updated_at: null,
    can_publish: true,
    can_publish_reason: '',
    content: {
      sections: {
        project_info: {
          status: 'completed',
          editable: true,
          visible: true,
          title: 'Benchathon 2026',
          description: 'Projektbeschreibung',
          custom_title: null,
          custom_description: null,
        },
        data: { status: 'completed', editable: true, visible: true, task_count: 15, custom_text: null, show_count: true },
        annotations: {
          status: 'completed',
          editable: true,
          visible: true,
          annotation_count: 224,
          custom_text: null,
          show_count: true,
          show_participants: true,
          acknowledgment_text: 'Danke an alle.',
        },
        generation: { status: 'completed', editable: true, visible: true, custom_text: null, show_models: true, show_config: false },
        evaluation: {
          status: 'completed',
          editable: true,
          visible: true,
          charts_config: {},
          custom_interpretation: 'Die Modelle schlagen den Median.',
          conclusions: 'Fazit hier.',
        },
      },
      metadata: { last_auto_update: '', sections_completed: [], can_publish: true },
    },
  }
  const merged = { ...base, ...overrides }
  if (overrides.sections) {
    merged.content = {
      ...base.content,
      sections: Object.fromEntries(
        Object.entries(base.content.sections).map(([k, v]) => [k, { ...(v as any), ...(overrides.sections[k] ?? {}) }]),
      ) as any,
    }
  }
  return merged
}

function mockData(report: any = makeReport(), snapshot: any = REPORT_SNAPSHOT_FIXTURE) {
  mockGetReportData.mockResolvedValue({ report, snapshot })
}

async function renderPage() {
  const params = Promise.resolve({ id: 'report-1' })
  const utils = render(<ReportViewerPage params={params} />)
  await waitFor(() => expect(screen.queryByTestId('report-loading')).not.toBeInTheDocument())
  return utils
}

const modelRowsOf = (tableId = 'ranking-table-models') =>
  within(screen.getByTestId(tableId)).getAllByTestId('ranking-row')

describe('ReportViewerPage', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockAuth = null
    mockUseResult = { id: 'report-1' }
  })

  it('shows the loading state first', () => {
    mockGetReportData.mockReturnValue(new Promise(() => {}))
    render(<ReportViewerPage params={Promise.resolve({ id: 'report-1' })} />)
    expect(screen.getByTestId('report-loading')).toBeInTheDocument()
  })

  it('renders header, tiles and prose sections from snapshot + content', async () => {
    mockData()
    await renderPage()
    expect(mockGetReportData).toHaveBeenCalledWith('report-1')
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Benchathon 2026')
    expect(screen.getByText('Projektbeschreibung')).toBeInTheDocument()
    expect(screen.getByText(/Veröffentlicht am/)).toBeInTheDocument()
    expect(screen.getByTestId('data-as-of')).toHaveTextContent('Datenstand:')
    expect(screen.queryByTestId('draft-badge')).not.toBeInTheDocument()
    expect(screen.getByTestId('breadcrumb')).toHaveTextContent('Berichte')

    expect(screen.getByTestId('stat-tasks')).toHaveTextContent('15')
    expect(screen.getByTestId('stat-annotations')).toHaveTextContent('224')
    expect(screen.getByTestId('stat-participants')).toHaveTextContent('36')
    expect(screen.getByTestId('stat-models')).toHaveTextContent('4')
    expect(screen.getByTestId('stat-evaluations')).toHaveTextContent('3.626')

    expect(screen.getByTestId('section-data')).toHaveTextContent('Der Datensatz umfasst 15 Aufgaben.')
    expect(screen.getByTestId('section-annotations')).toHaveTextContent('224 Abgaben von 36 Teilnehmenden wurden erfasst.')
    expect(screen.getByText('Danke an alle.')).toBeInTheDocument()
    expect(screen.getByTestId('section-generation')).toHaveTextContent('4 Sprachmodellen')
    expect(screen.getAllByTestId('model-chip')).toHaveLength(4)
    expect(screen.getByTestId('section-evaluation')).toBeInTheDocument()
    expect(screen.getByText('Die Modelle schlagen den Median.')).toBeInTheDocument()
    expect(screen.getByText('Fazit hier.')).toBeInTheDocument()
    expect(screen.getByTestId('participants-list')).toBeInTheDocument()
    expect(within(screen.getByTestId('participants-list')).getByText('KindAlly')).toBeInTheDocument()
    expect(screen.getByText('Erstellt mit')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'BenGER' })).toHaveAttribute('href', '/')
    expect(screen.queryByRole('link', { name: 'Bearbeiten' })).not.toBeInTheDocument()
  })

  it('ranks models by mean with badges computed from the sort', async () => {
    mockData(makeReport(), { ...REPORT_SNAPSHOT_FIXTURE, series: [...REPORT_SNAPSHOT_FIXTURE.series].reverse() })
    await renderPage()
    const rows = modelRowsOf()
    expect(rows).toHaveLength(4)
    expect(rows[0]).toHaveTextContent('GPT-5.4')
    expect(within(rows[0]).getByTestId('rank-badge')).toHaveTextContent('1')
    expect(rows[0]).toHaveTextContent('84,7 / 100')
    expect(rows[0]).toHaveTextContent('13,9 / 18 NP')
    expect(rows[3]).toHaveTextContent('Llama 4 Maverick')
    expect(within(rows[3]).getByTestId('rank-badge')).toHaveTextContent('4')
    const headers = within(screen.getByTestId('ranking-table-models')).getAllByRole('columnheader').map((h) => h.textContent)
    expect(headers).toEqual(['Rang', 'Modell', 'Falllösung LLM Judge', 'Notenpunkte', 'Bestanden', 'n'])
  })

  it('switches rows when another judge config is selected', async () => {
    mockData()
    await renderPage()
    expect(screen.getByTestId('config-selector')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('radio', { name: 'GPT-5 mini' }))
    const rows = modelRowsOf()
    expect(rows).toHaveLength(1)
    expect(rows[0]).toHaveTextContent('79,1 / 100')
    fireEvent.click(screen.getByRole('radio', { name: 'Claude Sonnet 4.6' }))
    expect(modelRowsOf()).toHaveLength(4)
  })

  it('removes hidden subjects from the ranking', async () => {
    mockData(makeReport({ sections: { evaluation: { charts_config: { hidden_subjects: ['gpt-5.4'] } } } }))
    await renderPage()
    const rows = modelRowsOf()
    expect(rows).toHaveLength(3)
    expect(rows[0]).toHaveTextContent('Claude Opus 4.7')
    expect(within(rows[0]).getByTestId('rank-badge')).toHaveTextContent('1')
  })

  it('hides the humans table when show_humans is false', async () => {
    mockData(makeReport({ sections: { evaluation: { charts_config: { show_humans: false } } } }))
    await renderPage()
    expect(screen.queryByTestId('ranking-table-humans')).not.toBeInTheDocument()
    expect(screen.getByTestId('ranking-table-models')).toBeInTheDocument()
  })

  it('renders the humans table separately ranked by default', async () => {
    mockData()
    await renderPage()
    const rows = modelRowsOf('ranking-table-humans')
    expect(rows.map((r) => r.getAttribute('data-subject'))).toEqual(['annotator:KindAlly', 'annotator:BraveOtter'])
    expect(within(rows[0]).getByTestId('rank-badge')).toHaveTextContent('1')
  })

  it('renders the distribution chart with model and human series', async () => {
    mockData()
    await renderPage()
    const chart = screen.getByTestId('distribution-chart')
    const bars = within(chart).getAllByTestId('bar')
    expect(bars.map((b) => b.getAttribute('data-key'))).toEqual(['modelPct', 'humanPct'])
    expect(screen.getByTestId('per-subject-distribution')).toBeInTheDocument()
    expect(screen.getByTestId('mean-bar-chart')).toBeInTheDocument()
  })

  it('shows the empty evaluation state without a snapshot', async () => {
    mockData(makeReport(), null)
    await renderPage()
    expect(screen.getByText('Für diesen Bericht liegt noch keine Auswertung vor.')).toBeInTheDocument()
    expect(screen.queryByTestId('stat-tiles')).not.toBeInTheDocument()
    expect(screen.queryByTestId('rank-badge')).not.toBeInTheDocument()
    expect(screen.queryByTestId('participants-list')).not.toBeInTheDocument()
    expect(screen.queryByTestId('section-annotations')).not.toBeInTheDocument()
    expect(screen.getByTestId('section-data')).toHaveTextContent('0 Aufgaben')
    expect(screen.queryByTestId('data-as-of')).not.toBeInTheDocument()
  })

  it('shows the draft badge and edit link for a superadmin on an unpublished report', async () => {
    mockAuth = { user: { is_superadmin: true } }
    mockData(makeReport({ is_published: false, published_at: null }))
    await renderPage()
    expect(screen.getByTestId('draft-badge')).toHaveTextContent('Entwurf')
    expect(screen.getByRole('link', { name: 'Bearbeiten' })).toHaveAttribute('href', '/projects/project-1/report/edit')
    expect(screen.queryByText(/Veröffentlicht am/)).not.toBeInTheDocument()
  })

  it('honours custom texts and section visibility flags', async () => {
    mockData(
      makeReport({
        sections: {
          project_info: { custom_title: 'Eigener Titel', custom_description: 'Eigene Beschreibung' },
          data: { visible: false },
          annotations: { custom_text: 'Eigener Abgabentext', show_participants: false, acknowledgment_text: null },
          generation: { custom_text: 'Eigener Modelltext', show_models: false },
          evaluation: { visible: false },
        },
      }),
    )
    await renderPage()
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Eigener Titel')
    expect(screen.getByText('Eigene Beschreibung')).toBeInTheDocument()
    expect(screen.queryByTestId('section-data')).not.toBeInTheDocument()
    expect(screen.getByText('Eigener Abgabentext')).toBeInTheDocument()
    expect(screen.getByText('Eigener Modelltext')).toBeInTheDocument()
    expect(screen.queryByTestId('model-chip')).not.toBeInTheDocument()
    expect(screen.queryByTestId('section-evaluation')).not.toBeInTheDocument()
    expect(screen.queryByTestId('stat-participants')).not.toBeInTheDocument()
    expect(screen.queryByTestId('participants-list')).not.toBeInTheDocument()
  })

  it('keeps the annotations section for custom text even with zero submissions', async () => {
    mockData(
      makeReport({ sections: { annotations: { custom_text: 'Nur Text' } } }),
      { ...REPORT_SNAPSHOT_FIXTURE, statistics: { ...REPORT_SNAPSHOT_FIXTURE.statistics, annotation_count: 0, participant_count: 0 } },
    )
    await renderPage()
    expect(screen.getByText('Nur Text')).toBeInTheDocument()
    expect(screen.queryByTestId('stat-annotations')).not.toBeInTheDocument()
    expect(screen.queryByTestId('stat-participants')).not.toBeInTheDocument()
  })

  it('shows an in-layout error card with reload and back link', async () => {
    mockGetReportData.mockRejectedValueOnce(new Error('Kaputt')).mockResolvedValueOnce({ report: makeReport(), snapshot: null })
    await renderPage()
    // breadcrumb + fallback title stay around the card
    expect(screen.getByTestId('breadcrumb')).toHaveTextContent('Berichte')
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Bericht')
    const card = screen.getByTestId('report-error')
    expect(card).toHaveTextContent('Der Bericht konnte nicht geladen werden.')
    expect(card).toHaveTextContent('Kaputt')
    expect(within(card).getByRole('link', { name: 'Zurück zu den Berichten' })).toHaveAttribute('href', '/reports')
    fireEvent.click(within(card).getByRole('button', { name: 'Erneut laden' }))
    await waitFor(() => expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Benchathon 2026'))
    expect(screen.queryByTestId('report-error')).not.toBeInTheDocument()
  })

  it('falls back to a generic hint for non-Error rejections', async () => {
    mockGetReportData.mockRejectedValueOnce('nope')
    await renderPage()
    expect(screen.getByTestId('report-error')).toHaveTextContent('Bitte versuchen Sie es in einem Moment erneut.')
  })

  it('shows not-found inside the error card when the API returns nothing', async () => {
    mockGetReportData.mockResolvedValueOnce(null)
    await renderPage()
    expect(screen.getByTestId('report-error')).toHaveTextContent('Bericht nicht gefunden.')
  })

  it.each([401, 403])('shows the not-public card with a login link on %s', async (status) => {
    const err = Object.assign(new Error(`HTTP error! status: ${status}`), { response: { status } })
    mockGetReportData.mockRejectedValueOnce(err)
    await renderPage()
    const card = screen.getByTestId('report-forbidden')
    expect(card).toHaveTextContent('Dieser Bericht ist nicht öffentlich.')
    expect(card).toHaveTextContent('Melden Sie sich an')
    expect(within(card).getByRole('link', { name: 'Anmelden' })).toHaveAttribute('href', '/login?next=%2Freports%2Freport-1')
    expect(within(card).getByRole('link', { name: 'Zurück zu den Berichten' })).toHaveAttribute('href', '/reports')
    expect(screen.queryByTestId('report-error')).not.toBeInTheDocument()
    expect(screen.getByTestId('breadcrumb')).toBeInTheDocument()
  })

  it('renders the loading card inside the layout', () => {
    mockGetReportData.mockReturnValue(new Promise(() => {}))
    render(<ReportViewerPage params={Promise.resolve({ id: 'report-1' })} />)
    expect(screen.getByTestId('report-loading')).toHaveTextContent('Bericht wird geladen')
    expect(screen.getByTestId('breadcrumb')).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Bericht')
  })
})

describe('classifyLoadError', () => {
  it('detects 401/403 via response.status, status or message text', () => {
    expect(classifyLoadError(Object.assign(new Error('x'), { response: { status: 403 } }))).toEqual({ forbidden: true, message: null })
    expect(classifyLoadError(Object.assign(new Error('x'), { status: 401 }))).toEqual({ forbidden: true, message: null })
    expect(classifyLoadError(new Error('Unauthenticated'))).toEqual({ forbidden: true, message: null })
    expect(classifyLoadError(new Error('HTTP error! status: 403 - Forbidden'))).toEqual({ forbidden: true, message: null })
  })

  it('keeps other errors with their message', () => {
    expect(classifyLoadError(Object.assign(new Error('Boom'), { response: { status: 500 } }))).toEqual({ forbidden: false, message: 'Boom' })
    expect(classifyLoadError(new Error('HTTP error! status: 404'))).toEqual({ forbidden: false, message: 'HTTP error! status: 404' })
    expect(classifyLoadError('nope')).toEqual({ forbidden: false, message: null })
    expect(classifyLoadError(null)).toEqual({ forbidden: false, message: null })
    expect(classifyLoadError(new Error(''))).toEqual({ forbidden: false, message: null })
  })
})

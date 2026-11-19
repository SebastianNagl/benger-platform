/**
 * The report's Analyses section and its exhibits, rendered from the
 * synthetic REPORT_ANALYSES_FIXTURE with the German catalog: numbers from
 * the snapshot, prose from the content, figures and tables numbered across
 * the section.
 */
import { REPORT_ANALYSES_FIXTURE as ANALYSES } from '@/lib/reports/fixture'
import { render, screen, within } from '@testing-library/react'
import { AnalysesSection, AnalysisExhibit, hasAnalyses } from '..'
import { t } from '../__mocks__/testUtils'

jest.mock('@/contexts/I18nContext', () =>
  require('@/test-utils/i18nMock').i18nMock('de'),
)

jest.mock('next/link', () => ({
  __esModule: true,
  default: ({ href, children, ...rest }: any) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}))

const [RUN] = ANALYSES.runs

describe('AnalysesSection', () => {
  it('renders nothing without runs', () => {
    const { container } = render(
      <AnalysesSection analyses={{ runs: [] }} locale="de" t={t} />,
    )
    expect(container).toBeEmptyDOMElement()
    expect(hasAnalyses(undefined)).toBe(false)
    expect(hasAnalyses(ANALYSES)).toBe(true)
  })

  it('shows each run with the author prose, metadata, families and warnings', () => {
    render(
      <AnalysesSection
        analyses={ANALYSES}
        content={{
          custom_text: 'Wir prüfen zwei Effekte.',
          runs: [
            {
              run_id: 'run-1',
              title: 'Framing-Effekt',
              text: 'Der Lauf zeigt den Effekt.',
              exhibits: [
                {
                  id: 'exhibit-1',
                  type: 'forest',
                  title: 'Effekt je System',
                  caption: 'Punkte sind Schätzungen.',
                },
              ],
            },
          ],
        }}
        locale="de"
        t={t}
      />,
    )
    const section = screen.getByTestId('section-analyses')
    expect(section).toHaveTextContent('Analysen')
    expect(section).toHaveTextContent('Wir prüfen zwei Effekte.')
    const run = within(screen.getByTestId('report-analysis-run'))
    expect(run.getByRole('heading', { name: 'Framing-Effekt' })).toBeVisible()
    expect(run.getByText('Der Lauf zeigt den Effekt.')).toBeVisible()
    expect(
      run.getByText(
        'Lauf framing main · abgeschlossen am 1. November 2026 · 48 Frame-Zeilen · 6 Schätzungen · Engine 1.1.0',
      ),
    ).toBeVisible()
    expect(run.getByText('a'.repeat(64))).toBeVisible()
    expect(screen.getByTestId('report-analysis-families')).toHaveTextContent(
      'Familien: primary (Holm, 2 Tests)',
    )
    expect(screen.getByTestId('report-analysis-warnings')).toHaveTextContent(
      'one cluster has a single unit',
    )
    // No link to the run for a reader.
    expect(run.queryByText('Lauf öffnen')).not.toBeInTheDocument()
  })

  it('numbers figures and tables and draws each exhibit from its positions', () => {
    render(<AnalysesSection analyses={ANALYSES} locale="de" t={t} />)
    const [forest, table] = screen.getAllByTestId('report-analysis-exhibit')
    expect(forest).toHaveAttribute('data-exhibit-type', 'forest')
    expect(within(forest).getByText('Abbildung 1')).toBeVisible()
    // One forest per contrast; three rows: pooled and the two systems.
    expect(
      within(forest).getByText('framing_effect · loaded_vs_neutral'),
    ).toBeVisible()
    expect(within(forest).getAllByTestId('forest-plot')).toHaveLength(1)
    expect(within(forest).getByText('Gepoolt')).toBeInTheDocument()
    expect(within(forest).getByText('system = sys_a')).toBeInTheDocument()
    expect(within(forest).getByText('system = sys_b')).toBeInTheDocument()

    expect(table).toHaveAttribute('data-exhibit-type', 'table')
    expect(within(table).getByText('Tabelle 1')).toBeVisible()
    const rows = within(table).getAllByTestId('estimate-row')
    expect(rows).toHaveLength(1)
    expect(rows[0]).toHaveTextContent('length_effect')
    // The compact table has no filters.
    expect(
      within(table).queryByTestId('estimates-estimand-filter'),
    ).not.toBeInTheDocument()
  })

  it('falls back to the run name, notes a truncated run and links authors to the run', () => {
    render(
      <AnalysesSection
        analyses={{
          runs: [{ ...RUN, truncated: true, warnings: [], families: [] }],
        }}
        locale="de"
        t={t}
        runHref={(id) => `/projects/p/analysis/${id}`}
      />,
    )
    expect(screen.getByRole('heading', { name: 'framing main' })).toBeVisible()
    expect(
      screen.getByText(
        /wählen mehr Schätzungen aus, als ein Bericht je Lauf aufnimmt/,
      ),
    ).toBeVisible()
    expect(
      screen.queryByTestId('report-analysis-families'),
    ).not.toBeInTheDocument()
    expect(
      screen.queryByTestId('report-analysis-warnings'),
    ).not.toBeInTheDocument()
    expect(screen.getByText('Lauf öffnen')).toHaveAttribute(
      'href',
      '/projects/p/analysis/run-1',
    )
  })
})

describe('AnalysisExhibit', () => {
  it('says so when no estimate matches', () => {
    render(
      <AnalysisExhibit
        type="table"
        estimates={[]}
        band={null}
        label="Tabelle 1"
        t={t}
      />,
    )
    expect(
      screen.getByText('Keine Schätzung passt zu dieser Darstellung.'),
    ).toBeVisible()
  })

  it('draws the chosen equivalence band, or none', () => {
    const rows = RUN.estimates.slice(0, 3)
    const { rerender } = render(
      <AnalysisExhibit
        type="forest"
        estimates={rows}
        band={0}
        label="Abbildung 1"
        title="Mit Band"
        t={t}
      />,
    )
    expect(screen.getByText(': Mit Band')).toBeVisible()
    expect(screen.getByTestId('forest-plot-band')).toBeInTheDocument()
    rerender(
      <AnalysisExhibit
        type="forest"
        estimates={rows}
        band={null}
        label="Abbildung 1"
        t={t}
      />,
    )
    expect(screen.queryByTestId('forest-plot-band')).not.toBeInTheDocument()
  })
})

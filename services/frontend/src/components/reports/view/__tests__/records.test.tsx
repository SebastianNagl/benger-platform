/**
 * The record parts of the report: data provenance, generation details,
 * human evaluation, the reproducibility appendix and the citation block.
 * Rendered from the synthetic REPORT_RECORDS_FIXTURE with the German catalog.
 */
import { REPORT_RECORDS_FIXTURE as REC } from '@/lib/reports/fixture'
import { fireEvent, render, screen, within } from '@testing-library/react'
import {
  buildBibtex,
  CitationBlock,
  DataProvenance,
  GenerationDetails,
  hasHumanEvaluations,
  HumanEvaluationSection,
  ReproducibilitySection,
} from '..'
import { t } from '../__mocks__/testUtils'

describe('DataProvenance', () => {
  it('lists the variant design with its factors, counts and frozen date', () => {
    render(<DataProvenance data={REC.data} locale="de" t={t} />)
    const [row] = screen.getAllByTestId('variant-design-row')
    expect(row).toHaveTextContent('Synthetic framing design')
    expect(row).toHaveTextContent('framing')
    expect(row).toHaveTextContent('(manipuliert)')
    expect(row).toHaveTextContent('(ausbalanciert)')
    expect(row).toHaveTextContent('neutral, loaded')
    // 60 levels declared, 2 listed
    expect(row).toHaveTextContent('und 58 weitere')
    expect(row).toHaveTextContent('Eingefroren am 20. August 2026')
    expect(row).toHaveTextContent('Einheit: case')
    const cells = within(row).getAllByRole('cell')
    expect(cells.slice(2).map((c) => c.textContent)).toEqual(['2', '4', '8'])
  })

  it('lists imports with payload hash, size, no-op repeats and the truncation note', () => {
    render(<DataProvenance data={REC.data} locale="de" t={t} />)
    const rows = screen.getAllByTestId('import-row')
    expect(rows).toHaveLength(2)
    expect(rows[0]).toHaveTextContent('b'.repeat(64))
    expect(rows[0]).toHaveTextContent('2 KB')
    expect(rows[0]).toHaveTextContent('Angegebenes Manifest')
    expect(rows[1]).toHaveTextContent(
      'Wiederholung eines früheren Imports, nichts geschrieben',
    )
    expect(rows[1]).toHaveTextContent('zu groß')
    expect(
      screen.getByText('Die ersten 2 von 3 Importen werden angezeigt.'),
    ).toBeInTheDocument()
  })

  it('lists imports without provenance columns in a snapshot without them', () => {
    const data = {
      ...REC.data,
      variant_designs: [],
      imports: REC.data.imports.map(({ format, completed_at }) => ({
        format,
        completed_at,
      })),
    }
    render(<DataProvenance data={data} locale="de" t={t} />)
    const rows = screen.getAllByTestId('import-row')
    expect(rows).toHaveLength(2)
    for (const row of rows) {
      expect(within(row).getAllByRole('cell')).toHaveLength(2)
    }
    expect(screen.queryByText('SHA-256 der Datei')).not.toBeInTheDocument()
    expect(screen.queryByTestId('variant-designs')).not.toBeInTheDocument()
  })

  it('shows only the manifest hash when the public view leaves the content out', () => {
    const [first, ...rest] = REC.data.imports
    render(
      <DataProvenance
        data={{
          ...REC.data,
          imports: [
            {
              ...first,
              declared_manifest: { sha256: 'd'.repeat(64) },
            },
            ...rest,
          ],
        }}
        locale="de"
        t={t}
      />,
    )
    const [row] = screen.getAllByTestId('import-row')
    expect(row).toHaveTextContent('Angegebenes Manifest')
    expect(row).toHaveTextContent('d'.repeat(64))
    expect(row).not.toHaveTextContent('cases.csv')
    expect(row).not.toHaveTextContent('zu groß')
  })

  it('renders nothing without designs and imports or for an old snapshot', () => {
    const { container, rerender } = render(
      <DataProvenance
        data={{ ...REC.data, variant_designs: [], imports: [] }}
        locale="de"
        t={t}
      />,
    )
    expect(container).toBeEmptyDOMElement()
    rerender(<DataProvenance data={undefined} locale="de" t={t} />)
    expect(container).toBeEmptyDOMElement()
  })
})

describe('GenerationDetails', () => {
  it('shows per-model counts and rates', () => {
    render(<GenerationDetails generation={REC.generation} locale="de" t={t} />)
    const row = screen.getByTestId('generation-row')
    const cells = within(row)
      .getAllByRole('cell')
      .map((c) => c.textContent)
    expect(cells[0]).toBe('GPT-5.4openai')
    expect(cells[1]).toBe('302 fehlgeschlagen')
    expect(cells.slice(2)).toEqual([
      '2',
      '25 %',
      '50 %',
      '10 %',
      '100 %',
      'plain',
    ])
  })

  it('has no refusal, retry or request record columns in a snapshot without them', () => {
    // A snapshot built without variant_experiments carries none of the three.
    const strip = <T extends object>(row: T) => {
      const {
        refusal_rate: _r,
        retry_rate: _y,
        request_record_share: _q,
        ...rest
      } = row as T & {
        refusal_rate?: unknown
        retry_rate?: unknown
        request_record_share?: unknown
      }
      return rest as T
    }
    const generation = {
      ...REC.generation,
      models: REC.generation.models.map(strip),
      totals: strip(REC.generation.totals),
    }
    render(<GenerationDetails generation={generation} locale="de" t={t} />)
    const cells = within(screen.getByTestId('generation-row'))
      .getAllByRole('cell')
      .map((c) => c.textContent)
    expect(cells.slice(2)).toEqual(['2', '50 %', 'plain'])
    expect(screen.queryByText('Gespeicherte Anfragen')).not.toBeInTheDocument()
  })

  it('drops the parse column when nothing was parsed and renders nothing without models', () => {
    const generation = {
      ...REC.generation,
      models: [{ ...REC.generation.models[0], parse_attempted: 0 }],
    }
    const { rerender, container } = render(
      <GenerationDetails generation={generation} locale="de" t={t} />,
    )
    expect(screen.queryByText('Parse-Fehler')).not.toBeInTheDocument()
    rerender(
      <GenerationDetails
        generation={{ ...REC.generation, models: [] }}
        locale="de"
        t={t}
      />,
    )
    expect(container).toBeEmptyDOMElement()
  })
})

describe('HumanEvaluationSection', () => {
  it('shows Likert dimensions, the per-model matrix and preference results', () => {
    render(
      <HumanEvaluationSection
        human={REC.human_evaluations}
        locale="de"
        t={t}
      />,
    )
    expect(
      screen.getByText('Bewertungen (Likert-Skala 1 bis 5)'),
    ).toBeInTheDocument()
    expect(
      screen.getByText('Bewertungen: 4 · Bewertende: 2'),
    ).toBeInTheDocument()
    const [accuracy, clarity] = screen.getAllByTestId('likert-row')
    expect(accuracy).toHaveTextContent('accuracy')
    expect(accuracy).toHaveTextContent('4,00 ± 1,00')
    expect(
      within(accuracy).getByRole('img', {
        name: /1: 0, 2: 0, 3: 1, 4: 1, 5: 1/,
      }),
    ).toBeInTheDocument()
    expect(clarity).toHaveTextContent('2,00')
    expect(clarity).not.toHaveTextContent('±')
    expect(screen.getByTestId('likert-model-row')).toHaveTextContent(
      'GPT-5.44,00 (n = 3)–',
    )

    expect(
      screen.getByText('Paarvergleiche: 3 · Bewertende: 1 · Unentschieden: 1'),
    ).toBeInTheDocument()
    const prefRows = screen.getAllByTestId('preference-row')
    expect(prefRows[0]).toHaveTextContent('GPT-5.467 %2013')
    expect(screen.getByTestId('preference-pairs')).toHaveTextContent(
      'Claude Opus 4.7 vs. GPT-5.4012',
    )
  })

  it('hides itself without ratings or comparisons', () => {
    const empty = {
      likert: { ...REC.human_evaluations.likert, dimensions: [] },
      preference: { ...REC.human_evaluations.preference, comparisons: 0 },
    }
    expect(hasHumanEvaluations(empty)).toBe(false)
    expect(hasHumanEvaluations(undefined)).toBe(false)
    expect(hasHumanEvaluations(REC.human_evaluations)).toBe(true)
    const { container } = render(
      <HumanEvaluationSection human={empty} locale="de" t={t} />,
    )
    expect(container).toBeEmptyDOMElement()
  })
})

describe('ReproducibilitySection', () => {
  it('lists versions and hashes of every part', () => {
    render(
      <ReproducibilitySection
        repro={REC.reproducibility}
        generatedAt="2026-09-02T12:00:00Z"
        note="Run the spec again."
        locale="de"
        t={t}
      />,
    )
    expect(screen.getByText('Run the spec again.')).toBeInTheDocument()
    expect(screen.getByTestId('repro-snapshot-hash')).toBeInTheDocument()
    expect(screen.getAllByText('9'.repeat(64))).toHaveLength(1)
    expect(
      screen.getByText('BenGER v20260901-aaaa-bbbb, CORE 2.66'),
    ).toBeInTheDocument()
    expect(screen.getByText('Version v3')).toBeInTheDocument()
    expect(screen.getByTestId('repro-models')).toHaveTextContent(
      'gpt-5.4 (openai)',
    )
    expect(screen.getByTestId('repro-structures')).toHaveTextContent(
      'f'.repeat(64),
    )
    const configs = screen.getByTestId('repro-eval-configs')
    expect(configs).toHaveTextContent('Judge config')
    expect(configs).toHaveTextContent('judge-model')
    expect(configs).toHaveTextContent('a'.repeat(64))
    expect(screen.getByTestId('repro-designs')).toHaveTextContent(
      'c'.repeat(64),
    )
    expect(screen.getByTestId('repro-imports')).toHaveTextContent(
      'b'.repeat(64),
    )
    const run = screen.getByTestId('repro-analysis-run')
    expect(run).toHaveTextContent('Framing effect')
    expect(run).toHaveTextContent('1'.repeat(64))
    expect(run).toHaveTextContent('3'.repeat(64))
    expect(run).toHaveTextContent('1.1.0, Spezifikationsformat 1')
    expect(run).toHaveTextContent('16 Zeilen, 4 Schätzungen')
    expect(run).toHaveTextContent('numpy 2.0.0, scipy 1.14.0')
  })

  it('leaves out empty blocks', () => {
    render(
      <ReproducibilitySection
        repro={{
          ...REC.reproducibility,
          models: [],
          prompt_structures: [],
          evaluation_configs: [],
          variant_designs: [],
          imports: [],
          analysis_runs: [],
          platform: { app_version: null, core_api_version: '2.66' },
        }}
        locale="de"
        t={t}
      />,
    )
    for (const id of [
      'repro-models',
      'repro-structures',
      'repro-eval-configs',
      'repro-designs',
      'repro-imports',
      'repro-analysis-runs',
    ]) {
      expect(screen.queryByTestId(id)).not.toBeInTheDocument()
    }
    expect(screen.getByText('CORE 2.66')).toBeInTheDocument()
  })
})

describe('CitationBlock', () => {
  const props = {
    reportId: 'abcd1234-ffff',
    title: 'A {study}',
    url: 'https://example.org/reports/abcd1234-ffff',
    publishedAt: '2026-09-01T10:00:00Z',
    snapshotSha256: '9'.repeat(64),
    locale: 'de',
    t,
  }

  it('cites title, date, URL and snapshot hash, and links the data', () => {
    render(<CitationBlock {...props} />)
    expect(screen.getByTestId('citation-text')).toHaveTextContent(
      `A {study}. BenGER-Projektbericht, veröffentlicht am 1. September 2026. https://example.org/reports/abcd1234-ffff. SHA-256 des Datenstands: ${'9'.repeat(64)}.`,
    )
    expect(screen.getByTestId('report-data-link')).toHaveAttribute(
      'href',
      '/api/reports/abcd1234-ffff/data',
    )
    const print = jest.fn()
    window.print = print
    fireEvent.click(screen.getByTestId('print-report'))
    expect(print).toHaveBeenCalled()
  })

  it('copies the citation', async () => {
    const writeText = jest.fn().mockResolvedValue(undefined)
    Object.assign(navigator, { clipboard: { writeText } })
    render(<CitationBlock {...props} />)
    fireEvent.click(screen.getByTestId('copy-citation'))
    expect(writeText).toHaveBeenCalledWith(
      expect.stringContaining('BenGER-Projektbericht'),
    )
    expect(await screen.findByText('Kopiert')).toBeInTheDocument()
  })

  it('builds a BibTeX entry without braces from the title', () => {
    const bib = buildBibtex(props)
    expect(bib).toContain('@misc{benger-report-2026-abcd1234,')
    expect(bib).toContain('title        = {A study},')
    expect(bib).toContain(
      'howpublished = {\\url{https://example.org/reports/abcd1234-ffff}},',
    )
    expect(bib).toContain('date         = {2026-09-01},')
    expect(bib).toContain(`snapshot SHA-256 ${'9'.repeat(64)}`)
    const undated = buildBibtex({
      ...props,
      publishedAt: null,
      snapshotSha256: null,
    })
    expect(undated).toContain('@misc{benger-report-nd-abcd1234,')
    expect(undated).not.toContain('year')
    expect(undated).toContain('note         = {BenGER project report},')
  })

  it('cites without a hash for an older snapshot', () => {
    render(<CitationBlock {...props} snapshotSha256={null} />)
    expect(screen.getByTestId('citation-text')).not.toHaveTextContent('SHA-256')
  })
})

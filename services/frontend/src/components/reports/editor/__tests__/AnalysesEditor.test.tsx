/**
 * The report editor's Analyses card: offers the runs the API offers, adds
 * runs and exhibits, previews the live estimates an exhibit's filters
 * select, and says which exhibits the stored snapshot holds.
 */

import '@testing-library/jest-dom'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useEffect, useState } from 'react'

import { AnalysesEditor } from '@/components/reports/editor/AnalysesEditor'
import { analysisAPI } from '@/lib/api/analysis'
import {
  listReportAnalysisRuns,
  type AnalysisRunContent,
} from '@/lib/api/reports'
import {
  makeEstimate,
  makeEstimates,
  makeRun,
} from '@/test-utils/analysisFixtures'
import type { ReportAnalysesSnapshot } from '@/types/report'

jest.mock('@/contexts/I18nContext', () =>
  require('@/test-utils/i18nMock').i18nMock('en'),
)

jest.mock('@/lib/api/reports', () => ({
  listReportAnalysisRuns: jest.fn(),
}))

jest.mock('@/lib/api/analysis', () => ({
  ...jest.requireActual('@/lib/api/analysis'),
  analysisAPI: { listEstimates: jest.fn(), getRun: jest.fn() },
}))

const mockRuns = listReportAnalysisRuns as jest.Mock
const mockEstimates = analysisAPI.listEstimates as jest.Mock
const mockGetRun = analysisAPI.getRun as jest.Mock

const RUN_OPTION = {
  id: 'run-1',
  name: 'Role swap',
  spec_hash: 'e'.repeat(64),
  engine_version: '1.1.0',
  frame_rows: 288,
  estimates_count: 4,
  completed_at: '2026-11-19T08:18:00Z',
  member_only: false,
}

let lastRuns: AnalysisRunContent[] = []
let lastText = ''

function Harness({
  initial = [],
  snapshot = null,
  isPublic = false,
}: {
  initial?: AnalysisRunContent[]
  snapshot?: ReportAnalysesSnapshot | null
  isPublic?: boolean
}) {
  const [runs, setRuns] = useState(initial)
  const [text, setText] = useState('')
  useEffect(() => {
    lastRuns = runs
    lastText = text
  }, [runs, text])
  return (
    <AnalysesEditor
      projectId="project-1"
      customText={text}
      runs={runs}
      onCustomTextChange={setText}
      onRunsChange={setRuns}
      snapshot={snapshot}
      isPublic={isPublic}
    />
  )
}

const forestRun = (
  filters: AnalysisRunContent['exhibits'][number]['filters'] = {},
): AnalysisRunContent => ({
  run_id: 'run-1',
  title: null,
  text: null,
  exhibits: [{ id: 'exhibit-1', type: 'forest', filters, band: 0 }],
})

beforeEach(() => {
  jest.clearAllMocks()
  mockRuns.mockResolvedValue([RUN_OPTION])
  mockEstimates.mockResolvedValue(makeEstimates())
  mockGetRun.mockResolvedValue(
    makeRun({ normalized_spec: { estimands: [] }, fits: [] }),
  )
})

describe('AnalysesEditor', () => {
  it('offers only the runs the API offers and says why', async () => {
    mockRuns.mockResolvedValue([])
    render(<Harness />)
    expect(
      await screen.findByText(
        'This project has no completed analysis run that reads only this project.',
      ),
    ).toBeVisible()
    expect(
      screen.getByText(/because a report must not publish another project/),
    ).toBeVisible()
    expect(mockRuns).toHaveBeenCalledWith('project-1')
  })

  it('marks member-only runs and offers them only for a non-public report', async () => {
    const secret = {
      ...RUN_OPTION,
      id: 'run-2',
      name: 'With a private model',
      member_only: true,
    }
    mockRuns.mockResolvedValue([RUN_OPTION, secret])
    const { unmount } = render(
      <Harness initial={[{ ...forestRun(), run_id: 'run-2' }]} />,
    )
    expect(
      await screen.findByTestId('analysis-run-member-only'),
    ).toHaveTextContent('Members only')
    expect(screen.getByTestId('analysis-run-member-only')).toHaveTextContent(
      'cannot be made public while it holds this run',
    )
    unmount()

    render(<Harness isPublic />)
    const picker = await screen.findByTestId('analysis-run-add')
    expect(
      Array.from((picker as HTMLSelectElement).options).map((o) => o.value),
    ).not.toContain('run-2')
  })

  it('says why no run can be added when only member-only runs are left for a public report', async () => {
    mockRuns.mockResolvedValue([{ ...RUN_OPTION, member_only: true }])
    render(<Harness isPublic />)
    expect(
      await screen.findByText(/The remaining runs are members only/),
    ).toBeVisible()
    expect(
      screen.queryByText('Every available run is in the report.'),
    ).not.toBeInTheDocument()
  })

  it('says a member-only run of a public report is withheld from readers outside the project', async () => {
    mockRuns.mockResolvedValue([{ ...RUN_OPTION, member_only: true }])
    render(<Harness initial={[forestRun()]} isPublic />)
    expect(
      await screen.findByTestId('analysis-run-member-only'),
    ).toHaveTextContent('readers outside the project do not see this run')
  })

  it('reports a failed run list', async () => {
    mockRuns.mockRejectedValue(new Error('boom'))
    render(<Harness />)
    expect(
      await screen.findByText('The analysis runs could not be loaded.'),
    ).toBeVisible()
  })

  it('adds a run with a forest exhibit and previews its live estimates', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    const picker = await screen.findByTestId('analysis-run-add')
    expect(
      Array.from((picker as HTMLSelectElement).options).map((o) => o.value),
    ).toContain('run-1')
    await user.selectOptions(picker, 'run-1')
    await user.click(screen.getByText('Add run'))

    expect(lastRuns).toEqual([
      {
        run_id: 'run-1',
        title: null,
        text: null,
        exhibits: [{ id: 'exhibit-1', type: 'forest', filters: {}, band: 0 }],
      },
    ])
    const card = screen.getByTestId('analysis-run-editor')
    expect(
      within(card).getByRole('heading', { name: 'Role swap' }),
    ).toBeVisible()
    await waitFor(() =>
      expect(
        within(card).getByTestId('exhibit-preview-count'),
      ).toHaveTextContent('Preview of the live estimates: 4 of 4'),
    )
    expect(mockEstimates).toHaveBeenCalledWith('run-1')
    expect(within(card).getByText('Figure 1')).toBeVisible()
    // Every run is in the section now.
    expect(
      screen.getByText('Every available run is in the report.'),
    ).toBeVisible()
  })

  it('narrows the preview with the filters and stores them sorted', async () => {
    const user = userEvent.setup()
    render(<Harness initial={[forestRun()]} />)
    const card = await screen.findByTestId('analysis-run-editor')
    await waitFor(() =>
      expect(
        within(card).getByTestId('exhibit-preview-count'),
      ).toHaveTextContent('4 of 4'),
    )
    const systems = screen.getByTestId('exhibit-run-1-exhibit-1-systems')
    expect(
      Array.from((systems as HTMLSelectElement).options).map((o) => o.value),
    ).toEqual(['sys_a', 'sys_b'])
    await user.selectOptions(systems, ['sys_b', 'sys_a'])
    await user.selectOptions(
      screen.getByTestId('exhibit-run-1-exhibit-1-families'),
      ['per_system'],
    )
    expect(lastRuns[0].exhibits[0].filters).toEqual({
      families: ['per_system'],
      systems: ['sys_a', 'sys_b'],
    })
    // per_system holds the two system estimates only.
    expect(within(card).getByTestId('exhibit-preview-count')).toHaveTextContent(
      '2 of 4',
    )
    await user.selectOptions(
      screen.getByTestId('exhibit-run-1-exhibit-1-estimands'),
      ['by_system'],
    )
    expect(within(card).getByTestId('exhibit-preview-count')).toHaveTextContent(
      '0 of 4',
    )
    expect(
      within(card).getByText('No estimates match this exhibit.'),
    ).toBeVisible()
  })

  it('selects by the systems the run spec says an estimate involves', async () => {
    // The pooled did estimate weights a parameter of sys_a, so a filter on
    // sys_a shows it next to the sys_a estimate.
    mockGetRun.mockResolvedValue(
      makeRun({
        normalized_spec: {
          estimands: [
            {
              id: 'by_system',
              contrasts: [
                { id: 'did sys_a', weights: { 'x_p:system[sys_a]': 1 } },
              ],
            },
          ],
        },
        fits: [],
      }),
    )
    render(<Harness initial={[forestRun({ systems: ['sys_a'] })]} />)
    const card = await screen.findByTestId('analysis-run-editor')
    await waitFor(() =>
      expect(
        within(card).getByTestId('exhibit-preview-count'),
      ).toHaveTextContent('2 of 4'),
    )
    expect(mockGetRun).toHaveBeenCalledWith('run-1')
  })

  it('switches the type, edits texts, adds, moves and removes exhibits and runs', async () => {
    const user = userEvent.setup()
    mockRuns.mockResolvedValue([
      RUN_OPTION,
      { ...RUN_OPTION, id: 'run-2', name: 'Second' },
    ])
    render(
      <Harness
        initial={[
          forestRun(),
          { ...forestRun(), run_id: 'run-2', exhibits: [] },
        ]}
      />,
    )
    const [first, second] = await screen.findAllByTestId('analysis-run-editor')
    await user.type(
      within(first).getByLabelText('Title', {
        selector: '#analysis-run-0-title',
      }),
      'Main',
    )
    await user.type(within(first).getByLabelText('Text'), 'Shows it')
    await user.type(screen.getByLabelText('Introduction'), 'Intro')
    expect(lastRuns[0].title).toBe('Main')
    expect(lastRuns[0].text).toBe('Shows it')
    expect(lastText).toBe('Intro')

    await user.selectOptions(within(first).getByTestId('exhibit-type'), 'table')
    expect(lastRuns[0].exhibits[0]).toMatchObject({ type: 'table', band: null })
    expect(within(first).getByText('Table 1')).toBeVisible()

    await user.click(within(first).getByText('Add forest plot'))
    await user.click(within(first).getByText('Add table'))
    expect(lastRuns[0].exhibits.map((e) => [e.id, e.type])).toEqual([
      ['exhibit-1', 'table'],
      ['exhibit-2', 'forest'],
      ['exhibit-3', 'table'],
    ])
    const exhibits = within(first).getAllByTestId('analysis-exhibit-editor')
    await user.click(within(exhibits[2]).getByLabelText('Move up'))
    expect(lastRuns[0].exhibits.map((e) => e.id)).toEqual([
      'exhibit-1',
      'exhibit-3',
      'exhibit-2',
    ])
    await user.click(
      within(
        within(first).getAllByTestId('analysis-exhibit-editor')[0],
      ).getByLabelText('Remove exhibit'),
    )
    expect(lastRuns[0].exhibits.map((e) => e.id)).toEqual([
      'exhibit-3',
      'exhibit-2',
    ])

    await user.click(within(second).getByLabelText('Move up'))
    expect(lastRuns.map((r) => r.run_id)).toEqual(['run-2', 'run-1'])
    await user.click(
      within(screen.getAllByTestId('analysis-run-editor')[0]).getByLabelText(
        'Remove run',
      ),
    )
    expect(lastRuns.map((r) => r.run_id)).toEqual(['run-1'])
  })

  it('offers the declared equivalence bands of a forest', async () => {
    const user = userEvent.setup()
    render(<Harness initial={[forestRun()]} />)
    const band = await screen.findByLabelText('Equivalence band')
    await waitFor(() =>
      expect(
        Array.from((band as HTMLSelectElement).options).map((o) => o.text),
      ).toEqual(['No band', 'Bound set 1: [-3, 3]', 'Bound set 2: [-2, 2]']),
    )
    await user.selectOptions(band, 'none')
    expect(lastRuns[0].exhibits[0].band).toBeNull()
    await user.selectOptions(band, '1')
    expect(lastRuns[0].exhibits[0].band).toBe(1)
  })

  it('says which exhibits the stored snapshot holds as defined', async () => {
    const snapshot: ReportAnalysesSnapshot = {
      runs: [
        {
          id: 'run-1',
          name: 'Role swap',
          spec_hash: 'e'.repeat(64),
          spec_version: 1,
          engine_version: '1.1.0',
          frame_hash: null,
          frame_sha256: null,
          frame_rows: 288,
          estimates_count: 4,
          completed_at: null,
          warnings: [],
          families: [],
          truncated: false,
          estimates: [],
          exhibits: [
            {
              id: 'exhibit-1',
              type: 'forest',
              filters: { systems: ['sys_a'] },
              band: 0,
              row_count: 2,
              positions: [0, 1],
            },
          ],
        },
      ],
    }
    const { unmount } = render(
      <Harness
        initial={[forestRun({ systems: ['sys_a'] })]}
        snapshot={snapshot}
      />,
    )
    expect(await screen.findByText('In the current snapshot')).toBeVisible()
    unmount()
    render(
      <Harness
        initial={[forestRun({ systems: ['sys_b'] })]}
        snapshot={snapshot}
      />,
    )
    expect(
      await screen.findByText(
        'Enters the report on the next publish or refresh',
      ),
    ).toBeVisible()
  })

  it('reads a stored forest exhibit without a band as the first bound set', async () => {
    const snapshot: ReportAnalysesSnapshot = {
      runs: [
        {
          id: 'run-1',
          name: 'Role swap',
          spec_hash: 'e'.repeat(64),
          spec_version: 1,
          engine_version: '1.1.0',
          frame_hash: null,
          frame_sha256: null,
          frame_rows: 288,
          estimates_count: 4,
          completed_at: null,
          warnings: [],
          families: [],
          truncated: false,
          estimates: [],
          exhibits: [
            {
              id: 'exhibit-1',
              type: 'forest',
              filters: {},
              band: 0,
              row_count: 4,
              positions: [0, 1, 2, 3],
            },
          ],
        },
      ],
    }
    const stored: AnalysisRunContent = {
      run_id: 'run-1',
      title: null,
      text: null,
      exhibits: [{ id: 'exhibit-1', type: 'forest', filters: {} }],
    }
    render(<Harness initial={[stored]} snapshot={snapshot} />)
    expect(await screen.findByText('In the current snapshot')).toBeVisible()
  })

  it('warns about a run the report cannot show and has no preview for it', async () => {
    render(
      <Harness
        initial={[{ ...forestRun(), run_id: 'run-gone' }]}
        snapshot={{
          runs: [],
          omitted: [{ run_id: 'run-gone', reason: 'reads_other_projects' }],
        }}
      />,
    )
    expect(
      await screen.findByTestId('analysis-run-unavailable'),
    ).toHaveTextContent('Remove it to publish.')
    await waitFor(() =>
      expect(screen.getByTestId('exhibit-preview-count')).toHaveTextContent(
        "The run's estimates are not available.",
      ),
    )
    expect(mockEstimates).not.toHaveBeenCalled()
  })

  it('warns when a run selects more estimates than a report keeps', async () => {
    mockEstimates.mockResolvedValue(
      Array.from({ length: 1001 }, (_, i) => makeEstimate({ position: i })),
    )
    render(
      <Harness
        initial={[
          {
            ...forestRun(),
            exhibits: [
              { id: 'exhibit-1', type: 'table', filters: {}, band: null },
            ],
          },
        ]}
      />,
    )
    expect(
      await screen.findByTestId('analysis-run-too-many'),
    ).toHaveTextContent(
      'select 1,001 estimates; a report keeps the first 1,000',
    )
  })

  it('reports estimates that fail to load', async () => {
    mockEstimates.mockRejectedValue(new Error('nope'))
    render(<Harness initial={[forestRun()]} />)
    await waitFor(() =>
      expect(screen.getByTestId('exhibit-preview-count')).toHaveTextContent(
        "The run's estimates are not available.",
      ),
    )
  })
})

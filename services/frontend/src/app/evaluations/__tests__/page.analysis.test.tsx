/**
 * The Analyses result type of the evaluations page: the result type switch,
 * the run, systems, estimands and family filters acting on the forest plot
 * and the estimates table alike, the URL state round trip, the statistics
 * blocks, the compliance findings slot (only with the overlay flag on), the
 * start dialog for editors (and its `newRunFrom` prefill), polling of a
 * running run, and the searchable, paged project picker.
 *
 * @jest-environment jsdom
 */

import '@testing-library/jest-dom'
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import EvaluationDashboard from '@/app/evaluations/page'
import {
  _resetActiveExtensionsForTests,
  setActiveExtensions,
} from '@/lib/extensions/active'
import { setRegistrationOwner } from '@/lib/extensions/owner'
import { registerSlot } from '@/lib/extensions/slots'
import { makeEstimates, makePlan, makeRun } from '@/test-utils/analysisFixtures'

jest.mock('@/contexts/I18nContext', () =>
  require('@/test-utils/i18nMock').i18nMock('en'),
)

const mockReplace = jest.fn()
const mockPush = jest.fn()
let mockSearch = new URLSearchParams()
jest.mock('next/navigation', () => ({
  useRouter: () => ({ replace: mockReplace, push: mockPush }),
  useSearchParams: () => mockSearch,
}))

let mockUser: { id: string; is_superadmin?: boolean } = { id: 'u1' }
jest.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({ user: mockUser, isLoading: false, organizations: [] }),
}))

jest.mock('@/utils/permissions', () => ({
  canAccessProjectData: () => true,
}))

let mockVariantExperiments = true
jest.mock('@/lib/featureFlags', () => ({
  ...jest.requireActual('@/lib/featureFlags'),
  useActiveExtensionsReady: () => true,
  useFeatureFlag: (name: string) =>
    name === 'variant_experiments' && mockVariantExperiments,
  useFeatureFlagStatus: (name: string) =>
    name === 'variant_experiments' && mockVariantExperiments ? 'on' : 'off',
}))

// The Metrics view has its own suites; here it only shows the shell's lead.
jest.mock('@/app/evaluations/_components/MetricResultsView', () => ({
  MetricResultsView: ({ filterBarLead }: any) => (
    <div data-testid="metric-view">{filterBarLead}</div>
  ),
}))

const mockList = jest.fn()
const mockGetProject = jest.fn()
jest.mock('@/lib/api/projects', () => ({
  projectsAPI: {
    list: (...a: unknown[]) => mockList(...a),
    get: (...a: unknown[]) => mockGetProject(...a),
  },
}))

const mockListRuns = jest.fn()
const mockGetRun = jest.fn()
const mockListEstimates = jest.fn()
const mockDesigns = jest.fn()
const mockPlans = jest.fn()
const mockValidate = jest.fn()
const mockStart = jest.fn()
jest.mock('@/lib/api/analysis', () => ({
  ...jest.requireActual('@/lib/api/analysis'),
  analysisAPI: {
    listRuns: (...a: unknown[]) => mockListRuns(...a),
    getRun: (...a: unknown[]) => mockGetRun(...a),
    listEstimates: (...a: unknown[]) => mockListEstimates(...a),
    listDesignKeys: (...a: unknown[]) => mockDesigns(...a),
    listPlans: (...a: unknown[]) => mockPlans(...a),
    validateSpec: (...a: unknown[]) => mockValidate(...a),
    startRun: (...a: unknown[]) => mockStart(...a),
  },
}))

const project = (overrides = {}) => ({
  id: 'project-1',
  title: 'Variants',
  task_count: 24,
  effective_role: 'CONTRIBUTOR',
  can_edit: true,
  ...overrides,
})

const summary = (overrides = {}) => {
  const { spec, normalized_spec, fits, ...rest } = makeRun(overrides)
  void spec
  void normalized_spec
  void fits
  return rest
}

function Findings({
  run,
  estimates,
}: {
  run: { id: string }
  estimates: unknown[]
}) {
  return (
    <div data-testid="overlay-findings">
      {run.id}: {estimates.length} estimates
    </div>
  )
}

beforeAll(() => {
  setRegistrationOwner('compliance')
  registerSlot('AnalysisRunFindings', Findings)
  setRegistrationOwner(null)
})

beforeEach(() => {
  jest.clearAllMocks()
  _resetActiveExtensionsForTests()
  localStorage.clear()
  mockUser = { id: 'u1' }
  mockSearch = new URLSearchParams('projectId=project-1&type=analysis')
  mockList.mockResolvedValue({ items: [project()], total: 1 })
  mockGetProject.mockResolvedValue(project())
  mockDesigns.mockResolvedValue(['role_swap'])
  mockPlans.mockResolvedValue([])
  mockListRuns.mockResolvedValue({
    items: [
      summary({ id: 'run-3', name: 'Pending one', status: 'pending' }),
      summary({ id: 'run-2', name: 'Role swap' }),
      summary({ id: 'run-1', name: 'Older', status: 'completed' }),
    ],
    total: 3,
  })
  mockGetRun.mockImplementation((id: string) =>
    Promise.resolve(
      makeRun({
        id,
        name: id === 'run-2' ? 'Role swap' : id,
        status: id === 'run-3' ? 'pending' : 'completed',
      }),
    ),
  )
  mockListEstimates.mockResolvedValue(makeEstimates())
})

afterEach(() => {
  jest.useRealTimers()
})

const lastUrl = () => {
  const calls = mockReplace.mock.calls
  return calls.length > 0 ? (calls[calls.length - 1][0] as string) : ''
}

const lastParams = () => new URLSearchParams(lastUrl().split('?')[1] ?? '')

async function renderReady() {
  const view = render(<EvaluationDashboard />)
  await screen.findByTestId('estimates-table')
  return view
}

const forestLabels = () =>
  within(screen.getByTestId('contrast-forest-plot'))
    .getAllByTestId('forest-plot-row')
    .map((row) => row.textContent)

describe('Evaluations page, Analyses result type', () => {
  it('selects the newest completed run and shows its forest plot', async () => {
    await renderReady()
    expect(mockListRuns).toHaveBeenCalledWith('project-1', 50)
    expect(mockGetRun).toHaveBeenCalledWith('run-2')
    expect(screen.getByTestId('analysis-run-strip')).toHaveTextContent(
      'Role swap',
    )
    expect(screen.getByTestId('analysis-run-strip')).toHaveTextContent('288')
    expect(screen.getByTestId('analysis-run-strip')).toHaveTextContent(
      'e8b39e3aff6d',
    )
    expect(screen.getByTestId('analysis-run-details')).toHaveAttribute(
      'href',
      '/evaluations/analysis/run-2',
    )
    expect(screen.getByTestId('contrast-forest-plot')).toBeInTheDocument()
    expect(screen.getByTestId('analysis-inference-block')).toBeInTheDocument()
    expect(screen.getByTestId('analysis-fit-block')).toBeInTheDocument()
    expect(screen.getAllByTestId('estimate-row')).toHaveLength(4)
    // The page filters replace the table's own filters.
    expect(screen.queryByTestId('estimates-family-filter')).toBeNull()
    await waitFor(() =>
      expect(lastUrl()).toBe(
        '/evaluations?projectId=project-1&type=analysis&run=run-2',
      ),
    )
    expect(screen.getByTestId('result-type-analysis')).toHaveAttribute(
      'aria-checked',
      'true',
    )
  })

  it('changes the forest plot and the table consistently with the filters', async () => {
    const user = userEvent.setup()
    await renderReady()
    expect(forestLabels()).toHaveLength(3)

    await user.click(screen.getByTestId('analysis-systems-filter'))
    const panel = screen.getByTestId('analysis-systems-filter-panel')
    await user.click(within(panel).getByLabelText('sys_a'))
    // sys_b stays: one system plus the pooled fit
    expect(forestLabels()).toHaveLength(2)
    expect(forestLabels().join(' ')).not.toContain('sys_a')
    expect(screen.getAllByTestId('estimate-row')).toHaveLength(3)
    await waitFor(() => expect(lastParams().get('systems')).toBe('sys_b'))

    await user.selectOptions(
      screen.getByTestId('analysis-family-filter'),
      'per_system',
    )
    expect(screen.getAllByTestId('estimate-row')).toHaveLength(1)
    expect(forestLabels()).toEqual([expect.stringContaining('system = sys_b')])
    await waitFor(() => expect(lastParams().get('family')).toBe('per_system'))

    await user.click(screen.getByTestId('analysis-clear-filters'))
    expect(screen.getAllByTestId('estimate-row')).toHaveLength(4)
    await waitFor(() =>
      expect(lastUrl()).toBe(
        '/evaluations?projectId=project-1&type=analysis&run=run-2',
      ),
    )
  })

  it('filters by estimand and switches the view to bars and the table', async () => {
    const user = userEvent.setup()
    await renderReady()
    await user.click(screen.getByTestId('analysis-estimands-filter'))
    const panel = screen.getByTestId('analysis-estimands-filter-panel')
    await user.click(within(panel).getByText('Clear All'))
    await user.click(within(panel).getByLabelText('by_system'))
    expect(screen.getAllByTestId('estimate-row')).toHaveLength(1)
    await waitFor(() => expect(lastParams().get('estimands')).toBe('by_system'))
    await user.click(within(panel).getByText('Select All'))
    expect(screen.getAllByTestId('estimate-row')).toHaveLength(4)

    // The chart type selector lists exactly the analysis views.
    await user.click(screen.getByText('Forest plot'))
    const menu = screen.getAllByRole('button').map((b) => b.textContent ?? '')
    expect(menu.some((m) => m.startsWith('Radar'))).toBe(false)
    await user.click(screen.getByText('Bar Chart'))
    expect(
      (await screen.findAllByTestId('forest-plot-bar')).length,
    ).toBeGreaterThan(0)
    await waitFor(() => expect(lastParams().get('chartType')).toBe('bar'))
  })

  it('restores run, view and filters from the URL', async () => {
    mockSearch = new URLSearchParams(
      'projectId=project-1&type=analysis&run=run-1&chartType=table&systems=sys_a&estimands=role&family=per_system',
    )
    render(<EvaluationDashboard />)
    await screen.findByTestId('estimates-table')
    expect(mockGetRun).toHaveBeenCalledWith('run-1')
    expect(mockGetRun).not.toHaveBeenCalledWith('run-2')
    expect(screen.getAllByTestId('estimate-row')).toHaveLength(1)
    expect(await screen.findByTestId('interval-table')).toBeInTheDocument()
    await waitFor(() =>
      expect(Object.fromEntries(lastParams())).toEqual({
        projectId: 'project-1',
        type: 'analysis',
        run: 'run-1',
        chartType: 'table',
        systems: 'sys_a',
        estimands: 'role',
        family: 'per_system',
      }),
    )
  })

  it('keeps chartType=data from the URL over a saved chart preference', async () => {
    localStorage.setItem('benger-preferred-chart-type', 'table')
    mockSearch = new URLSearchParams(
      'projectId=project-1&type=analysis&chartType=data',
    )
    const user = userEvent.setup()
    await renderReady()
    await waitFor(() => expect(lastParams().get('chartType')).toBe('data'))
    expect(screen.queryByTestId('interval-table')).toBeNull()
    expect(screen.queryByTestId('contrast-forest-plot')).toBeNull()

    // Choosing a view here leaves the metrics view's preference alone.
    await user.click(screen.getByText('Data View'))
    await user.click(screen.getByText('Bar Chart'))
    await waitFor(() => expect(lastParams().get('chartType')).toBe('bar'))
    expect(localStorage.getItem('benger-preferred-chart-type')).toBe('table')
  })

  it('drops URL filters the run does not have', async () => {
    mockSearch = new URLSearchParams(
      'projectId=project-1&type=analysis&systems=nope&family=nope&estimands=role,nope&chartType=radar',
    )
    render(<EvaluationDashboard />)
    await screen.findByTestId('estimates-table')
    await waitFor(() =>
      expect(Object.fromEntries(lastParams())).toEqual({
        projectId: 'project-1',
        type: 'analysis',
        run: 'run-2',
        estimands: 'role',
      }),
    )
    expect(screen.getByTestId('contrast-forest-plot')).toBeInTheDocument()
  })

  it('switches runs with the run filter', async () => {
    const user = userEvent.setup()
    await renderReady()
    const select = screen.getByTestId('analysis-run-filter')
    expect(
      within(select as HTMLElement)
        .getAllByRole('option')
        .map((o) => o.textContent),
    ).toEqual([
      'Pending one (Pending)',
      'Role swap (Completed)',
      'Older (Completed)',
    ])
    await user.selectOptions(select, 'run-1')
    await waitFor(() => expect(mockGetRun).toHaveBeenCalledWith('run-1'))
    await waitFor(() => expect(lastParams().get('run')).toBe('run-1'))
  })

  it('renders the findings slot inline only with the compliance flag on', async () => {
    const { unmount } = await renderReady()
    expect(screen.queryByTestId('overlay-findings')).toBeNull()
    unmount()

    act(() => setActiveExtensions(['compliance']))
    await renderReady()
    expect(await screen.findByTestId('overlay-findings')).toHaveTextContent(
      'run-2: 4 estimates',
    )
  })

  it('polls a running run until it completes', async () => {
    jest.useFakeTimers()
    mockSearch = new URLSearchParams(
      'projectId=project-1&type=analysis&run=run-3',
    )
    let calls = 0
    mockGetRun.mockImplementation(() => {
      calls += 1
      return Promise.resolve(
        makeRun({ id: 'run-3', status: calls < 2 ? 'running' : 'completed' }),
      )
    })
    render(<EvaluationDashboard />)
    expect(await screen.findByTestId('analysis-run-active')).toHaveTextContent(
      'The run is being computed',
    )
    expect(mockListEstimates).not.toHaveBeenCalled()
    await act(async () => {
      jest.advanceTimersByTime(3100)
    })
    await waitFor(() => expect(mockListEstimates).toHaveBeenCalledWith('run-3'))
    expect(await screen.findByTestId('estimates-table')).toBeInTheDocument()
  })

  it('ignores a slow poll of the previous run after another is selected', async () => {
    jest.useFakeTimers()
    mockSearch = new URLSearchParams(
      'projectId=project-1&type=analysis&run=run-3',
    )
    let resolveStalePoll: (run: unknown) => void = () => {}
    let run3Calls = 0
    mockGetRun.mockImplementation((id: string) => {
      if (id === 'run-3') {
        run3Calls += 1
        if (run3Calls === 1)
          return Promise.resolve(makeRun({ id: 'run-3', status: 'running' }))
        return new Promise((resolve) => {
          resolveStalePoll = resolve
        })
      }
      return Promise.resolve(makeRun({ id, status: 'completed' }))
    })
    render(<EvaluationDashboard />)
    expect(await screen.findByTestId('analysis-run-active')).toBeInTheDocument()
    await act(async () => {
      jest.advanceTimersByTime(3100)
    })
    expect(run3Calls).toBe(2)

    fireEvent.change(screen.getByTestId('analysis-run-filter'), {
      target: { value: 'run-1' },
    })
    expect(await screen.findByTestId('estimates-table')).toBeInTheDocument()
    expect(mockListEstimates).toHaveBeenCalledWith('run-1')

    await act(async () => {
      resolveStalePoll(makeRun({ id: 'run-3', status: 'running' }))
    })
    await act(async () => {
      jest.advanceTimersByTime(3100)
    })
    expect(screen.queryByTestId('analysis-run-active')).toBeNull()
    expect(screen.getByTestId('estimates-table')).toBeInTheDocument()
    expect(run3Calls).toBe(2)
  })

  it('shows a failed run and a run that cannot be read', async () => {
    mockGetRun.mockResolvedValue(
      makeRun({ id: 'run-2', status: 'failed', error_message: 'bad column' }),
    )
    const { unmount } = render(<EvaluationDashboard />)
    expect(await screen.findByTestId('analysis-run-failed')).toHaveTextContent(
      'bad column',
    )
    expect(mockListEstimates).not.toHaveBeenCalled()
    unmount()

    mockGetRun.mockResolvedValue(makeRun({ project_id: 'other-project' }))
    render(<EvaluationDashboard />)
    expect(await screen.findByTestId('analysis-run-error')).toHaveTextContent(
      'This analysis run does not exist',
    )
  })

  it('shows the empty state and a refused run list', async () => {
    mockListRuns.mockResolvedValue({ items: [], total: 0 })
    const { unmount } = render(<EvaluationDashboard />)
    expect(await screen.findByTestId('analysis-empty')).toHaveTextContent(
      'No analysis runs yet.',
    )
    unmount()

    mockListRuns.mockRejectedValue(
      Object.assign(new Error('403'), { response: { status: 403 } }),
    )
    render(<EvaluationDashboard />)
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'You cannot see the analysis runs of this project.',
    )
  })

  it('lets editors start a run in a dialog and selects it', async () => {
    const user = userEvent.setup()
    mockStart.mockResolvedValue(makeRun({ id: 'run-9', status: 'pending' }))
    await renderReady()
    await user.click(screen.getByTestId('analysis-start'))
    const dialog = await screen.findByTestId('start-analysis-dialog')
    await waitFor(() => expect(mockDesigns).toHaveBeenCalled())
    await user.click(within(dialog).getByText('Insert a starting spec'))
    await user.click(within(dialog).getByTestId('new-analysis-run-start'))
    await waitFor(() => expect(mockStart).toHaveBeenCalled())
    expect(mockStart.mock.calls[0][0]).toBe('project-1')
    await waitFor(() => expect(mockGetRun).toHaveBeenCalledWith('run-9'))
    await waitFor(() => expect(lastParams().get('run')).toBe('run-9'))
  })

  it('offers the saved plans in the start dialog and starts one', async () => {
    const user = userEvent.setup()
    const plan = makePlan()
    mockPlans.mockResolvedValue([plan])
    mockStart.mockResolvedValue(makeRun({ id: 'run-7', status: 'pending' }))
    await renderReady()
    await user.click(screen.getByTestId('analysis-start'))
    const dialog = await screen.findByTestId('start-analysis-dialog')
    const picker = (await within(dialog).findByLabelText(
      'Source',
    )) as HTMLSelectElement
    await user.selectOptions(picker, 'plan:plan-1')
    await user.click(within(dialog).getByTestId('new-analysis-run-start'))
    await waitFor(() =>
      expect(mockStart).toHaveBeenCalledWith('project-1', plan.spec, plan.name),
    )
    await waitFor(() => expect(lastParams().get('run')).toBe('run-7'))
  })

  it('opens the start dialog prefilled from newRunFrom', async () => {
    mockSearch = new URLSearchParams(
      'projectId=project-1&type=analysis&newRunFrom=run-1',
    )
    await renderReady()
    const dialog = await screen.findByTestId('start-analysis-dialog')
    const spec = (await within(dialog).findByLabelText(
      'Analysis spec (JSON)',
    )) as HTMLTextAreaElement
    await waitFor(() => expect(spec.value).toContain('"Role swap"'))
    // newRunFrom is consumed, not written back.
    expect(lastParams().get('newRunFrom')).toBeNull()
  })

  it('keeps run controls from annotators', async () => {
    mockList.mockResolvedValue({
      items: [project({ effective_role: 'ANNOTATOR', can_edit: false })],
      total: 1,
    })
    mockSearch = new URLSearchParams(
      'projectId=project-1&type=analysis&newRunFrom=run-1',
    )
    await renderReady()
    expect(screen.queryByTestId('analysis-start')).toBeNull()
    expect(screen.queryByTestId('start-analysis-dialog')).toBeNull()
  })

  it('follows the edit decision, not the role, for run controls', async () => {
    mockList.mockResolvedValue({
      items: [project({ effective_role: 'CONTRIBUTOR', can_edit: false })],
      total: 1,
    })
    mockSearch = new URLSearchParams(
      'projectId=project-1&type=analysis&newRunFrom=run-1',
    )
    await renderReady()
    expect(screen.queryByTestId('analysis-start')).toBeNull()
    expect(screen.queryByTestId('start-analysis-dialog')).toBeNull()
  })

  it('offers run controls to superadmins without edit rights', async () => {
    mockUser = { id: 'u1', is_superadmin: true }
    mockList.mockResolvedValue({
      items: [project({ effective_role: 'ANNOTATOR', can_edit: false })],
      total: 1,
    })
    await renderReady()
    expect(screen.getByTestId('analysis-start')).toBeInTheDocument()
  })
})

describe('Evaluations page with variant_experiments off', () => {
  afterEach(() => {
    mockVariantExperiments = true
  })

  it('offers no Analyses and shows the metrics for ?type=analysis', async () => {
    mockVariantExperiments = false
    mockSearch = new URLSearchParams('projectId=project-1&type=analysis')
    render(<EvaluationDashboard />)
    expect(await screen.findByTestId('metric-view')).toBeInTheDocument()
    expect(screen.queryByTestId('result-type-switch')).toBeNull()
    expect(screen.queryByTestId('estimates-table')).toBeNull()
    expect(mockListRuns).not.toHaveBeenCalled()
    expect(mockDesigns).not.toHaveBeenCalled()
  })
})

describe('Evaluations page, result type switch', () => {
  it('offers Analyses for a project with runs or designs and switches', async () => {
    const user = userEvent.setup()
    mockSearch = new URLSearchParams('projectId=project-1')
    render(<EvaluationDashboard />)
    expect(await screen.findByTestId('metric-view')).toBeInTheDocument()
    await user.click(await screen.findByTestId('result-type-analysis'))
    expect(mockReplace).toHaveBeenCalledWith(
      '/evaluations?projectId=project-1&type=analysis',
      { scroll: false },
    )
    expect(await screen.findByTestId('estimates-table')).toBeInTheDocument()

    await user.click(screen.getByTestId('result-type-metrics'))
    expect(mockReplace).toHaveBeenLastCalledWith(
      '/evaluations?projectId=project-1',
      { scroll: false },
    )
    expect(screen.getByTestId('metric-view')).toBeInTheDocument()
  })

  it('hides the switch for a project without runs or designs', async () => {
    mockSearch = new URLSearchParams('projectId=project-1')
    mockListRuns.mockResolvedValue({ items: [], total: 0 })
    mockDesigns.mockResolvedValue([])
    render(<EvaluationDashboard />)
    expect(await screen.findByTestId('metric-view')).toBeInTheDocument()
    await waitFor(() => expect(mockDesigns).toHaveBeenCalled())
    expect(screen.queryByTestId('result-type-switch')).toBeNull()
  })
})

describe('Evaluations page, project picker', () => {
  it('searches projects on the server and loads further pages', async () => {
    jest.useFakeTimers()
    const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime })
    mockSearch = new URLSearchParams()
    mockList.mockImplementation(
      (page: number, _size: number, search?: string) =>
        Promise.resolve(
          search
            ? { items: [project({ id: 'p-found', title: 'Found' })], total: 1 }
            : {
                items: [project({ id: `p-${page}`, title: `Page ${page}` })],
                total: 2,
              },
        ),
    )
    render(<EvaluationDashboard />)
    await waitFor(() => expect(mockList).toHaveBeenCalledWith(1, 100))
    await user.click(screen.getByText('Select project...'))
    expect(await screen.findByText('Page 1')).toBeInTheDocument()
    await user.click(screen.getByTestId('project-picker-more'))
    expect(await screen.findByText('Page 2')).toBeInTheDocument()
    expect(mockList).toHaveBeenCalledWith(2, 100)
    expect(screen.queryByTestId('project-picker-more')).toBeNull()

    await user.type(screen.getByTestId('project-picker-search'), 'fou')
    await act(async () => {
      jest.advanceTimersByTime(400)
    })
    await waitFor(() => expect(mockList).toHaveBeenCalledWith(1, 100, 'fou'))
    expect(await screen.findByText('Found')).toBeInTheDocument()
    expect(screen.queryByText('Page 1')).toBeNull()

    mockList.mockResolvedValue({ items: [], total: 0 })
    await user.type(screen.getByTestId('project-picker-search'), 'x')
    await act(async () => {
      jest.advanceTimersByTime(400)
    })
    expect(await screen.findByText('No projects found.')).toBeInTheDocument()
  })

  it('opens a project beyond the first page by its id', async () => {
    mockSearch = new URLSearchParams('projectId=project-far&type=analysis')
    mockGetProject.mockResolvedValue(
      project({ id: 'project-far', title: 'Far away' }),
    )
    mockGetRun.mockResolvedValue(makeRun({ project_id: 'project-far' }))
    render(<EvaluationDashboard />)
    await waitFor(() =>
      expect(mockGetProject).toHaveBeenCalledWith('project-far'),
    )
    expect(await screen.findByText('Far away')).toBeInTheDocument()
    await waitFor(() =>
      expect(mockListRuns).toHaveBeenCalledWith('project-far', 50),
    )
    expect(localStorage.getItem('evaluations_lastProjectId')).toBe(
      'project-far',
    )
  })

  it('selects another project and resets the analysis view', async () => {
    const user = userEvent.setup()
    mockList.mockResolvedValue({
      items: [project(), project({ id: 'project-2', title: 'Second' })],
      total: 2,
    })
    await renderReady()
    await user.click(screen.getByText('Variants'))
    await user.click(await screen.findByText('Second'))
    await waitFor(() =>
      expect(mockListRuns).toHaveBeenCalledWith('project-2', 50),
    )
  })
})

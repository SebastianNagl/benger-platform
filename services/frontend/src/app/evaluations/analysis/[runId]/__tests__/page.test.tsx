/**
 * The analysis run page: a completed run with forest plot, estimates,
 * provenance, spec and fits; the compliance findings slot only with the
 * overlay flag on; polling of a running run; a failed run; the frame
 * download; the run's own project in the breadcrumb; a missing run.
 */

import '@/test-utils/locationMock'
import '@testing-library/jest-dom'
import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import AnalysisRunPage from '@/app/evaluations/analysis/[runId]/page'
import {
  _resetActiveExtensionsForTests,
  setActiveExtensions,
} from '@/lib/extensions/active'
import { setRegistrationOwner } from '@/lib/extensions/owner'
import { registerSlot } from '@/lib/extensions/slots'
import { makeEstimates, makeRun } from '@/test-utils/analysisFixtures'

jest.mock('@/contexts/I18nContext', () =>
  require('@/test-utils/i18nMock').i18nMock('en'),
)

jest.mock('next/navigation', () => ({
  useParams: () => ({ runId: 'run-1' }),
  useRouter: () => ({ push: jest.fn() }),
}))

jest.mock('@/lib/featureFlags', () => ({
  ...jest.requireActual('@/lib/featureFlags'),
  useActiveExtensionsReady: () => true,
}))

const mockGetRun = jest.fn()
const mockListEstimates = jest.fn()
const mockGetFrameDownload = jest.fn()
jest.mock('@/lib/api/analysis', () => ({
  ...jest.requireActual('@/lib/api/analysis'),
  analysisAPI: {
    getRun: (...a: unknown[]) => mockGetRun(...a),
    listEstimates: (...a: unknown[]) => mockListEstimates(...a),
    getFrameDownload: (...a: unknown[]) => mockGetFrameDownload(...a),
  },
}))

const mockGetProject = jest.fn()
jest.mock('@/lib/api/projects', () => ({
  projectsAPI: {
    get: (...a: unknown[]) => mockGetProject(...a),
  },
}))

const mockUseAuth = jest.fn()
jest.mock('@/contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}))

function project(effectiveRole: string | null, canEdit = true) {
  return {
    id: 'project-1',
    title: 'Variants',
    effective_role: effectiveRole,
    can_edit: canEdit,
  }
}

function httpError(status: number) {
  return Object.assign(new Error(`HTTP ${status}`), {
    response: { status, data: null },
  })
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
  mockGetRun.mockResolvedValue(makeRun())
  mockListEstimates.mockResolvedValue(makeEstimates())
  mockGetProject.mockResolvedValue(project('CONTRIBUTOR'))
  mockUseAuth.mockReturnValue({ user: { id: 'u1', is_superadmin: false } })
})

afterEach(() => {
  jest.useRealTimers()
})

describe('AnalysisRunPage', () => {
  it('shows a completed run with plot, estimates, provenance, spec and fits', async () => {
    render(<AnalysisRunPage />)
    expect(
      await screen.findByRole('heading', { name: 'Role swap' }),
    ).toBeInTheDocument()
    expect(screen.getByTestId('run-status-badge')).toHaveTextContent(
      'Completed',
    )
    expect(await screen.findByTestId('estimates-table')).toBeInTheDocument()
    expect(screen.getAllByTestId('estimate-row')).toHaveLength(4)
    expect(
      screen.getByRole('img', { name: 'Forest plot of role' }),
    ).toBeInTheDocument()
    expect(screen.getByTestId('forest-plot-band')).toBeInTheDocument()

    const provenance = within(screen.getByTestId('run-provenance'))
    expect(provenance.getByText('e8b39e3aff6d')).toHaveAttribute(
      'title',
      makeRun().spec_hash,
    )
    expect(provenance.getByText('28e684e10d0d')).toBeInTheDocument()
    expect(provenance.getByText('288 rows, 17.3 kB')).toBeInTheDocument()
    expect(
      provenance.getByText('engine 1.0.0, spec format 1'),
    ).toBeInTheDocument()
    expect(provenance.getByText('numpy 2.5.5')).toBeInTheDocument()
    expect(provenance.getByText('fit 0.64 s')).toBeInTheDocument()

    expect(screen.getByTestId('analysis-run-warnings')).toHaveTextContent(
      'by_system [pooled]: collinear regressors',
    )
    expect(screen.getByTestId('run-spec')).toHaveTextContent(
      '"ssc": "statsmodels"',
    )
    expect(
      within(screen.getByTestId('run-fits')).getByText('x_p, first_x'),
    ).toBeInTheDocument()
    expect(mockListEstimates).toHaveBeenCalledWith('run-1')
    expect(screen.getByText('Variants')).toBeInTheDocument()
  })

  it('switches the spec between normalized and as submitted', async () => {
    const user = userEvent.setup()
    render(<AnalysisRunPage />)
    const spec = await screen.findByTestId('run-spec')
    expect(spec).toHaveTextContent('conventions')
    await user.click(within(spec).getByRole('tab', { name: 'As submitted' }))
    expect(spec).not.toHaveTextContent('conventions')
  })

  it('renders the compliance findings slot only with the overlay flag on', async () => {
    render(<AnalysisRunPage />)
    await screen.findByTestId('estimates-table')
    expect(screen.queryByTestId('overlay-findings')).toBeNull()
    expect(
      screen.getByTestId('analysis-run-findings-slot'),
    ).toBeEmptyDOMElement()

    act(() => setActiveExtensions(['compliance']))
    expect(screen.getByTestId('overlay-findings')).toHaveTextContent(
      'run-1: 4 estimates',
    )

    act(() => setActiveExtensions([]))
    expect(screen.queryByTestId('overlay-findings')).toBeNull()
  })

  it('polls a running run until it completes, then loads the estimates', async () => {
    jest.useFakeTimers()
    mockGetRun
      .mockResolvedValueOnce(
        makeRun({
          status: 'running',
          completed_at: null,
          frame_available: false,
        }),
      )
      .mockResolvedValue(makeRun())
    render(<AnalysisRunPage />)
    expect(await screen.findByTestId('analysis-run-active')).toHaveTextContent(
      'The run is being computed.',
    )
    expect(mockListEstimates).not.toHaveBeenCalled()
    expect(screen.queryByTestId('analysis-frame-download')).toBeNull()

    await act(async () => {
      jest.advanceTimersByTime(3000)
    })
    await waitFor(() => expect(mockGetRun).toHaveBeenCalledTimes(2))
    expect(await screen.findByTestId('estimates-table')).toBeInTheDocument()
    expect(screen.queryByTestId('analysis-run-active')).toBeNull()
    expect(mockListEstimates).toHaveBeenCalledTimes(1)
  })

  it('keeps the run on screen when a poll fails and polls again', async () => {
    jest.useFakeTimers()
    mockGetRun
      .mockResolvedValueOnce(makeRun({ status: 'running', completed_at: null }))
      .mockRejectedValueOnce(httpError(502))
      .mockResolvedValue(makeRun())
    render(<AnalysisRunPage />)
    expect(await screen.findByTestId('analysis-run-active')).toBeInTheDocument()

    await act(async () => {
      jest.advanceTimersByTime(3000)
    })
    await waitFor(() => expect(mockGetRun).toHaveBeenCalledTimes(2))
    expect(screen.queryByTestId('analysis-run-error')).toBeNull()
    expect(
      screen.getByRole('heading', { name: 'Role swap' }),
    ).toBeInTheDocument()
    expect(screen.getByTestId('analysis-run-active')).toBeInTheDocument()

    await act(async () => {
      jest.advanceTimersByTime(3000)
    })
    await waitFor(() => expect(mockGetRun).toHaveBeenCalledTimes(3))
    expect(await screen.findByTestId('estimates-table')).toBeInTheDocument()
    expect(screen.queryByTestId('analysis-run-active')).toBeNull()
  })

  it('shows an error when the first load fails', async () => {
    mockGetRun.mockRejectedValue(httpError(502))
    render(<AnalysisRunPage />)
    expect(await screen.findByTestId('analysis-run-error')).toHaveTextContent(
      'HTTP 502',
    )
  })

  it('shows the error of a failed run and no estimates', async () => {
    mockGetRun.mockResolvedValue(
      makeRun({
        status: 'failed',
        error_message: 'unknown column(s) no_such_column',
        frame_available: false,
        fits: [],
        warnings: [],
      }),
    )
    render(<AnalysisRunPage />)
    expect(await screen.findByTestId('analysis-run-failed')).toHaveTextContent(
      'unknown column(s) no_such_column',
    )
    expect(screen.queryByTestId('estimates-table')).toBeNull()
    expect(mockListEstimates).not.toHaveBeenCalled()
    // provenance and spec stay visible for a failed run
    expect(screen.getByTestId('run-provenance')).toBeInTheDocument()
  })

  it('downloads the frame through a short-lived URL', async () => {
    const user = userEvent.setup()
    const assign = jest
      .spyOn(window.location, 'assign')
      .mockImplementation(() => undefined)
    mockGetFrameDownload.mockResolvedValue({
      url: 'http://storage.test/analysis/frame.parquet?sig=1',
      frame_hash: 'f',
      frame_sha256: 'a',
    })
    render(<AnalysisRunPage />)
    await user.click(await screen.findByTestId('analysis-frame-download'))
    expect(mockGetFrameDownload).toHaveBeenCalledWith('run-1')
    await waitFor(() =>
      expect(assign).toHaveBeenCalledWith(
        'http://storage.test/analysis/frame.parquet?sig=1',
      ),
    )
  })

  it('hides the frame download from roles the API refuses it to', async () => {
    mockGetProject.mockResolvedValue(project('ANNOTATOR'))
    render(<AnalysisRunPage />)
    await screen.findByTestId('estimates-table')
    await waitFor(() => expect(mockGetProject).toHaveBeenCalled())
    expect(screen.getByText('Variants')).toBeInTheDocument()
    expect(screen.queryByTestId('analysis-frame-download')).toBeNull()
  })

  it('offers the frame download to an org admin and a superadmin', async () => {
    mockGetProject.mockResolvedValue(project('ORG_ADMIN'))
    const { unmount } = render(<AnalysisRunPage />)
    expect(
      await screen.findByTestId('analysis-frame-download'),
    ).toBeInTheDocument()
    unmount()

    mockGetProject.mockResolvedValue(project(null))
    mockUseAuth.mockReturnValue({ user: { id: 'u0', is_superadmin: true } })
    render(<AnalysisRunPage />)
    expect(
      await screen.findByTestId('analysis-frame-download'),
    ).toBeInTheDocument()
  })

  it('offers a new run from this spec only to editors and superadmins', async () => {
    const reuse = { name: 'New run from this spec' }
    mockGetProject.mockResolvedValue(project('ANNOTATOR', false))
    const first = render(<AnalysisRunPage />)
    await screen.findByTestId('estimates-table')
    await waitFor(() =>
      expect(screen.getByText('Variants')).toBeInTheDocument(),
    )
    expect(screen.queryByRole('link', reuse)).toBeNull()
    first.unmount()

    mockGetProject.mockResolvedValue(project('CONTRIBUTOR', true))
    const second = render(<AnalysisRunPage />)
    expect(await screen.findByRole('link', reuse)).toHaveAttribute(
      'href',
      '/evaluations?projectId=project-1&type=analysis&newRunFrom=run-1',
    )
    second.unmount()

    mockGetProject.mockResolvedValue(project(null, false))
    mockUseAuth.mockReturnValue({ user: { id: 'u0', is_superadmin: true } })
    render(<AnalysisRunPage />)
    expect(await screen.findByRole('link', reuse)).toBeInTheDocument()
  })

  it('explains a refused frame download', async () => {
    const user = userEvent.setup()
    mockGetFrameDownload.mockRejectedValue(httpError(403))
    render(<AnalysisRunPage />)
    await user.click(await screen.findByTestId('analysis-frame-download'))
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Downloading the frame needs the org admin or contributor role',
    )
  })

  it('reads the project from the run and links back to its Analyses view', async () => {
    mockGetRun.mockResolvedValue(makeRun({ project_id: 'other-project' }))
    render(<AnalysisRunPage />)
    await screen.findByTestId('estimates-table')
    expect(mockGetProject).toHaveBeenCalledWith('other-project')
    const crumb = await screen.findByRole('link', { name: 'Variants' })
    expect(crumb).toHaveAttribute(
      'href',
      '/evaluations?projectId=other-project&type=analysis',
    )
    expect(screen.getByRole('link', { name: 'Evaluations' })).toHaveAttribute(
      'href',
      '/evaluations',
    )
  })

  it('treats a 404 as not found', async () => {
    mockGetRun.mockRejectedValue(httpError(404))
    render(<AnalysisRunPage />)
    expect(await screen.findByTestId('analysis-run-error')).toHaveTextContent(
      'This analysis run does not exist',
    )
  })
})

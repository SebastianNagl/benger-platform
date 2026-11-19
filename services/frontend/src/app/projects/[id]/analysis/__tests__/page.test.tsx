/**
 * The project's analysis runs: the list, the new-run form for editors
 * (validation errors from the engine, starting a run), the prefill from an
 * earlier run and the read-only view for members without edit rights.
 */

import '@testing-library/jest-dom'
import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import ProjectAnalysisPage from '@/app/projects/[id]/analysis/page'
import { makeRun } from '@/test-utils/analysisFixtures'

jest.mock('@/contexts/I18nContext', () =>
  require('@/test-utils/i18nMock').i18nMock('en'),
)

const mockPush = jest.fn()
let mockSearch = new URLSearchParams()
jest.mock('next/navigation', () => ({
  useParams: () => ({ id: 'project-1' }),
  useRouter: () => ({ push: mockPush }),
  useSearchParams: () => mockSearch,
}))

let mockUser: { is_superadmin?: boolean } | null = { is_superadmin: false }
jest.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({ user: mockUser }),
}))

const mockProject = jest.fn()
jest.mock('@/lib/api/projects', () => ({
  projectsAPI: { get: (...a: unknown[]) => mockProject(...a) },
}))

const mockListRuns = jest.fn()
const mockGetRun = jest.fn()
const mockValidate = jest.fn()
const mockStart = jest.fn()
const mockDesigns = jest.fn()
jest.mock('@/lib/api/analysis', () => ({
  ...jest.requireActual('@/lib/api/analysis'),
  analysisAPI: {
    listRuns: (...a: unknown[]) => mockListRuns(...a),
    getRun: (...a: unknown[]) => mockGetRun(...a),
    validateSpec: (...a: unknown[]) => mockValidate(...a),
    startRun: (...a: unknown[]) => mockStart(...a),
    listDesignKeys: (...a: unknown[]) => mockDesigns(...a),
  },
}))

function specError(errors: string[]) {
  return Object.assign(new Error('The analysis spec is invalid'), {
    response: {
      status: 422,
      data: {
        detail: {
          code: 'invalid_analysis_spec',
          message: 'The analysis spec is invalid',
          errors,
        },
      },
    },
  })
}

const summary = (overrides = {}) => {
  const { spec, normalized_spec, fits, ...rest } = makeRun(overrides)
  void spec
  void normalized_spec
  void fits
  return rest
}

beforeEach(() => {
  jest.clearAllMocks()
  mockSearch = new URLSearchParams()
  mockUser = { is_superadmin: false }
  mockProject.mockResolvedValue({
    id: 'project-1',
    title: 'Variants',
    can_edit: true,
  })
  mockDesigns.mockResolvedValue(['role_swap'])
  mockListRuns.mockResolvedValue({
    items: [
      summary(),
      summary({
        id: 'run-2',
        name: 'Broken',
        status: 'failed',
        error_message: 'unknown column(s) x',
        frame_rows: null,
        estimates_count: null,
      }),
    ],
    total: 2,
  })
})

describe('ProjectAnalysisPage', () => {
  it('lists the runs newest first and opens one', async () => {
    const user = userEvent.setup()
    render(<ProjectAnalysisPage />)
    const rows = await screen.findAllByTestId('analysis-run-row')
    expect(rows).toHaveLength(2)
    expect(within(rows[0]).getByText('Role swap')).toBeInTheDocument()
    expect(within(rows[0]).getByText('Completed')).toBeInTheDocument()
    expect(within(rows[0]).getByText('288')).toBeInTheDocument()
    expect(within(rows[0]).getByText('e8b39e3aff6d')).toBeInTheDocument()
    expect(within(rows[1]).getByText('Failed')).toBeInTheDocument()
    expect(within(rows[1]).getByText('unknown column(s) x')).toBeInTheDocument()
    await user.click(rows[0])
    expect(mockPush).toHaveBeenCalledWith('/projects/project-1/analysis/run-1')
  })

  it('shows the empty state', async () => {
    mockListRuns.mockResolvedValue({ items: [], total: 0 })
    render(<ProjectAnalysisPage />)
    expect(await screen.findByText('No analysis runs yet.')).toBeInTheDocument()
  })

  it('lists the engine problems of an invalid spec', async () => {
    const user = userEvent.setup()
    mockValidate.mockRejectedValue(
      specError(['/estimands: must have at least 1 item']),
    )
    render(<ProjectAnalysisPage />)
    await user.click(await screen.findByTestId('analysis-new-run'))
    await user.click(
      screen.getByRole('button', { name: 'Insert a starting spec' }),
    )
    const spec = screen.getByLabelText('Analysis spec (JSON)')
    expect((spec as HTMLTextAreaElement).value).toContain('"role_swap"')
    await user.click(screen.getByRole('button', { name: 'Validate' }))
    expect(
      await screen.findByTestId('new-analysis-run-errors'),
    ).toHaveTextContent('/estimands: must have at least 1 item')
    expect(mockValidate).toHaveBeenCalledWith(
      expect.objectContaining({ inputs: { designs: ['role_swap'] } }),
    )
  })

  it('rejects text that is not JSON before calling the API', async () => {
    const user = userEvent.setup()
    render(<ProjectAnalysisPage />)
    await user.click(await screen.findByTestId('analysis-new-run'))
    await user.type(screen.getByLabelText('Analysis spec (JSON)'), 'not json')
    await user.click(screen.getByRole('button', { name: 'Validate' }))
    expect(
      await screen.findByTestId('new-analysis-run-errors'),
    ).toHaveTextContent('Not valid JSON')
    expect(mockValidate).not.toHaveBeenCalled()
  })

  it('validates and starts a run, then opens it', async () => {
    const user = userEvent.setup()
    mockValidate.mockResolvedValue({
      valid: true,
      spec_hash: 'abcdef0123456789',
      normalized_spec: {},
      engine_version: '1.0.0',
    })
    mockStart.mockResolvedValue(makeRun({ id: 'run-9', status: 'pending' }))
    render(<ProjectAnalysisPage />)
    await user.click(await screen.findByTestId('analysis-new-run'))
    const spec = screen.getByLabelText('Analysis spec (JSON)')
    await user.click(spec)
    await user.paste('{"spec_version": 1}')
    await user.type(screen.getByLabelText('Name (optional)'), 'First')
    await user.click(screen.getByRole('button', { name: 'Validate' }))
    expect(
      await screen.findByText('The spec is valid (spec hash abcdef012345).'),
    ).toBeInTheDocument()
    await user.click(screen.getByTestId('new-analysis-run-start'))
    await waitFor(() =>
      expect(mockStart).toHaveBeenCalledWith(
        'project-1',
        { spec_version: 1 },
        'First',
      ),
    )
    expect(mockPush).toHaveBeenCalledWith('/projects/project-1/analysis/run-9')
  })

  it('prefills the form from an earlier run', async () => {
    mockSearch = new URLSearchParams('from=run-1')
    mockGetRun.mockResolvedValue(makeRun())
    render(<ProjectAnalysisPage />)
    const spec = await screen.findByLabelText('Analysis spec (JSON)')
    await waitFor(() =>
      expect((spec as HTMLTextAreaElement).value).toContain('"Role swap"'),
    )
    expect(screen.getByLabelText('Name (optional)')).toHaveValue('Role swap')
    expect(mockGetRun).toHaveBeenCalledWith('run-1')
  })

  it('offers no new run to members without edit rights', async () => {
    mockProject.mockResolvedValue({
      id: 'project-1',
      title: 'Variants',
      can_edit: false,
    })
    render(<ProjectAnalysisPage />)
    await screen.findAllByTestId('analysis-run-row')
    expect(screen.queryByTestId('analysis-new-run')).toBeNull()
  })

  it('keeps the runs on screen when a refresh fails and refreshes again', async () => {
    jest.useFakeTimers()
    try {
      mockListRuns
        .mockResolvedValueOnce({
          items: [summary({ status: 'running', completed_at: null })],
          total: 1,
        })
        .mockRejectedValueOnce(new Error('HTTP 502'))
        .mockResolvedValue({ items: [summary()], total: 1 })
      render(<ProjectAnalysisPage />)
      const row = await screen.findByTestId('analysis-run-row')
      expect(within(row).getByText('Running')).toBeInTheDocument()

      await act(async () => {
        jest.advanceTimersByTime(4000)
      })
      await waitFor(() => expect(mockListRuns).toHaveBeenCalledTimes(2))
      expect(screen.queryByRole('alert')).toBeNull()
      expect(screen.getByTestId('analysis-run-row')).toHaveTextContent(
        'Running',
      )

      await act(async () => {
        jest.advanceTimersByTime(4000)
      })
      await waitFor(() => expect(mockListRuns).toHaveBeenCalledTimes(3))
      expect(
        await within(screen.getByTestId('analysis-run-row')).findByText(
          'Completed',
        ),
      ).toBeInTheDocument()
    } finally {
      jest.useRealTimers()
    }
  })

  it('explains a refused list', async () => {
    mockListRuns.mockRejectedValue(
      Object.assign(new Error('x'), { response: { status: 404 } }),
    )
    render(<ProjectAnalysisPage />)
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'You cannot see the analysis runs of this project.',
    )
  })
})

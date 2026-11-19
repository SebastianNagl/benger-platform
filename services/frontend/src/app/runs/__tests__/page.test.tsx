/**
 * @jest-environment jsdom
 *
 * Tests for the /runs single-run inventory page (multi-run feature).
 *
 * Verifies:
 *  - Loads via apiClient.get with correct query params per tab/filter
 *  - Switching tabs writes type= to the URL
 *  - Status filter resets pagination + appends ?status=
 *  - Project filter writes ?project_id= to the URL
 *  - Clicking a row routes to /evaluations/{id}, /generations/{id} or the
 *    analysis run page
 *  - The analysis tab lists name, frame rows, estimates and spec hash
 *  - Empty / error state renders the proper message
 */
import '@testing-library/jest-dom'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

const mockPush = jest.fn()
const mockReplace = jest.fn()
let mockSearchParams = new URLSearchParams('type=evaluation')

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush, replace: mockReplace }),
  useSearchParams: () => mockSearchParams,
}))

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    locale: 'de',
    t: (key: string, vars?: Record<string, unknown>) =>
      require('@/lib/i18n/catalog').translateKey('de', key, vars),
  }),
}))

const mockGet = jest.fn()
jest.mock('@/lib/api', () => ({
  __esModule: true,
  default: { get: (...args: any[]) => mockGet(...args) },
}))

jest.mock('@/lib/api/projects', () => ({
  projectsAPI: {
    list: jest.fn().mockResolvedValue({
      items: [
        { id: 'p1', title: 'Benchaton 2' },
        { id: 'p2', title: 'Benchathon' },
      ],
    }),
  },
}))

import RunsPage from '../page'

const evalRun = {
  id: 'eval-1',
  type: 'evaluation' as const,
  project_id: 'p1',
  project_title: 'Benchaton 2',
  status: 'completed',
  created_at: '2026-05-06T10:00:00Z',
  completed_at: '2026-05-06T10:05:00Z',
  model_id: 'gpt-4o-mini',
  judge_models: ['gpt-4o', 'claude-opus'],
  metrics: ['llm_judge_falloesung'],
  samples_evaluated: 13,
}

const genRun = {
  id: 'gen-1',
  type: 'generation' as const,
  project_id: 'p1',
  project_title: 'Benchaton 2',
  status: 'completed',
  created_at: '2026-05-06T09:00:00Z',
  completed_at: '2026-05-06T09:01:00Z',
  model_id: 'gpt-5.4',
  structure_key: 'test-prompt',
  runs_requested: 3,
  runs_completed: 3,
  runs_failed: 0,
}

const analysisRun = {
  id: 'an-1',
  type: 'analysis' as const,
  project_id: 'p2',
  project_title: 'Benchathon',
  status: 'completed',
  created_at: '2026-05-06T08:00:00Z',
  completed_at: '2026-05-06T08:00:30Z',
  name: 'synthetic contrast',
  frame_rows: 480,
  estimates_count: 12,
  spec_hash: 'abcdef0123456789abcdef',
  engine_version: '1.0.0',
}

beforeEach(() => {
  mockGet.mockReset()
  mockPush.mockReset()
  mockReplace.mockReset()
  mockSearchParams = new URLSearchParams('type=evaluation')
})

describe('RunsPage', () => {
  it('loads evaluations on mount and renders rows', async () => {
    mockGet.mockResolvedValueOnce({
      items: [evalRun],
      total: 1,
      page: 1,
      page_size: 25,
    })
    render(<RunsPage />)
    await waitFor(() => expect(mockGet).toHaveBeenCalled())
    const url: string = mockGet.mock.calls[0][0]
    expect(url).toContain('type=evaluation')
    expect(url).toContain('page=1')
    expect(url).toContain('page_size=25')
    // Eval-tab columns are visible.
    await waitFor(() =>
      expect(screen.getByText('gpt-4o-mini')).toBeInTheDocument(),
    )
    expect(screen.getByText(/gpt-4o, claude-opus/)).toBeInTheDocument()
    // "Benchaton 2" appears both in the project filter dropdown <option>
    // and in the row's project column — both expected.
    expect(screen.getAllByText('Benchaton 2').length).toBeGreaterThan(0)
  })

  it('names every model of an evaluation run over several models', async () => {
    mockGet.mockResolvedValueOnce({
      items: [
        {
          ...evalRun,
          model_id: 'unknown',
          evaluated_model_ids: ['gpt-5.4', 'gemini-2.5-pro'],
        },
        { ...evalRun, id: 'eval-2', model_id: 'unknown', judge_models: [] },
      ],
      total: 2,
      page: 1,
      page_size: 25,
    })
    render(<RunsPage />)
    const models = await screen.findByText('gpt-5.4, gemini-2.5-pro')
    expect(models).toHaveAttribute('title', 'gpt-5.4, gemini-2.5-pro')
    // A run that graded no model shows a dash, never the 'unknown' label.
    expect(screen.queryByText('unknown')).not.toBeInTheDocument()
  })

  it('shows a dash for a finished run that graded no model', async () => {
    mockGet.mockResolvedValueOnce({
      items: [{ ...evalRun, model_id: 'gpt-5.4', evaluated_model_ids: [] }],
      total: 1,
      page: 1,
      page_size: 25,
    })
    render(<RunsPage />)
    expect(await screen.findByTitle('—')).toHaveTextContent('—')
    expect(screen.queryByText('gpt-5.4')).not.toBeInTheDocument()
  })

  it('switches to generation tab and updates URL', async () => {
    mockGet
      .mockResolvedValueOnce({
        items: [evalRun],
        total: 1,
        page: 1,
        page_size: 25,
      })
      .mockResolvedValueOnce({
        items: [genRun],
        total: 1,
        page: 1,
        page_size: 25,
      })
    render(<RunsPage />)
    await waitFor(() => expect(mockGet).toHaveBeenCalledTimes(1))

    fireEvent.click(screen.getByRole('button', { name: 'Generierungen' }))
    await waitFor(() =>
      expect(mockReplace).toHaveBeenCalledWith(
        expect.stringContaining('type=generation'),
        expect.any(Object),
      ),
    )
    await waitFor(() => expect(mockGet).toHaveBeenCalledTimes(2))
    expect(mockGet.mock.calls[1][0]).toContain('type=generation')
  })

  it('filters by status and resets to page 1', async () => {
    mockGet.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 25 })
    render(<RunsPage />)
    await waitFor(() => expect(mockGet).toHaveBeenCalledTimes(1))

    const statusSelect = screen.getAllByRole('combobox')[1] // 0=project, 1=status
    fireEvent.change(statusSelect, { target: { value: 'failed' } })
    await waitFor(() => expect(mockGet).toHaveBeenCalledTimes(2))
    expect(mockGet.mock.calls[1][0]).toContain('status=failed')
    expect(mockGet.mock.calls[1][0]).toContain('page=1')
  })

  it('filters by project and writes ?project_id=', async () => {
    mockGet.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 25 })
    render(<RunsPage />)
    // Wait for projects to load.
    await waitFor(() =>
      expect(screen.getAllByRole('combobox')[0]).toBeInTheDocument(),
    )
    const projectSelect = screen.getAllByRole('combobox')[0]
    fireEvent.change(projectSelect, { target: { value: 'p1' } })
    await waitFor(() =>
      expect(mockReplace).toHaveBeenCalledWith(
        expect.stringContaining('project_id=p1'),
        expect.any(Object),
      ),
    )
  })

  it('clicking an evaluation row navigates to /evaluations/{id}', async () => {
    mockGet.mockResolvedValueOnce({
      items: [evalRun],
      total: 1,
      page: 1,
      page_size: 25,
    })
    render(<RunsPage />)
    await waitFor(() =>
      expect(screen.getByText('gpt-4o-mini')).toBeInTheDocument(),
    )

    fireEvent.click(screen.getByText('gpt-4o-mini').closest('tr')!)
    expect(mockPush).toHaveBeenCalledWith('/evaluations/eval-1')
  })

  it('clicking a generation row navigates to /generations/{id}', async () => {
    mockSearchParams = new URLSearchParams('type=generation')
    mockGet.mockResolvedValueOnce({
      items: [genRun],
      total: 1,
      page: 1,
      page_size: 25,
    })
    render(<RunsPage />)
    await waitFor(() => expect(screen.getByText('gpt-5.4')).toBeInTheDocument())

    fireEvent.click(screen.getByText('gpt-5.4').closest('tr')!)
    expect(mockPush).toHaveBeenCalledWith('/generations/gen-1')
  })

  it('renders empty-state row when API returns no items', async () => {
    mockGet.mockResolvedValueOnce({
      items: [],
      total: 0,
      page: 1,
      page_size: 25,
    })
    render(<RunsPage />)
    await waitFor(() =>
      expect(screen.getByText('Keine Einträge')).toBeInTheDocument(),
    )
  })

  it('renders an error banner on API failure', async () => {
    mockGet.mockRejectedValueOnce({ message: 'unreachable' })
    render(<RunsPage />)
    await waitFor(() =>
      expect(screen.getByText('unreachable')).toBeInTheDocument(),
    )
  })

  it('lists analysis runs on the analysis tab and opens their run page', async () => {
    mockSearchParams = new URLSearchParams(
      'type=analysis&project_id=p2&status=completed',
    )
    mockGet.mockResolvedValueOnce({
      items: [analysisRun],
      total: 1,
      page: 1,
      page_size: 25,
    })
    render(<RunsPage />)
    const name = await screen.findByText('synthetic contrast')
    const url: string = mockGet.mock.calls[0][0]
    expect(url).toContain('type=analysis')
    expect(url).toContain('project_id=p2')
    expect(url).toContain('status=completed')
    expect(screen.getByTestId('runs-tab-analysis')).toHaveAttribute(
      'aria-pressed',
      'true',
    )
    expect(screen.getByText('Analysen')).toBeInTheDocument()
    expect(
      screen.getByRole('columnheader', { name: 'Name' }),
    ).toBeInTheDocument()
    expect(screen.queryByText('analysis.list.col.name')).toBeNull()
    expect(screen.getByText('480')).toBeInTheDocument()
    expect(screen.getByText('12')).toBeInTheDocument()
    expect(screen.getByTitle('abcdef0123456789abcdef')).toHaveTextContent(
      'abcdef012345',
    )

    fireEvent.click(name.closest('tr')!)
    expect(mockPush).toHaveBeenCalledWith('/evaluations/analysis/an-1')
  })

  it('switches to the analysis tab and pages through its runs', async () => {
    mockGet.mockResolvedValue({
      items: [analysisRun],
      total: 30,
      page: 1,
      page_size: 25,
    })
    render(<RunsPage />)
    await waitFor(() => expect(mockGet).toHaveBeenCalledTimes(1))

    fireEvent.click(screen.getByTestId('runs-tab-analysis'))
    await waitFor(() => expect(mockGet).toHaveBeenCalledTimes(2))
    expect(mockGet.mock.calls[1][0]).toContain('type=analysis')
    expect(mockReplace).toHaveBeenCalledWith(
      expect.stringContaining('type=analysis'),
      expect.any(Object),
    )

    fireEvent.click(await screen.findByRole('button', { name: 'Weiter' }))
    await waitFor(() => expect(mockGet).toHaveBeenCalledTimes(3))
    expect(mockGet.mock.calls[2][0]).toContain('page=2')
  })

  it('writes the status filter to the URL and ignores an unknown type', async () => {
    mockSearchParams = new URLSearchParams('type=bogus')
    mockGet.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 25 })
    render(<RunsPage />)
    await waitFor(() => expect(mockGet).toHaveBeenCalledTimes(1))
    expect(mockGet.mock.calls[0][0]).toContain('type=evaluation')

    const statusSelect = screen.getAllByRole('combobox')[1]
    fireEvent.change(statusSelect, { target: { value: 'running' } })
    await waitFor(() =>
      expect(mockReplace).toHaveBeenCalledWith(
        expect.stringContaining('status=running'),
        expect.any(Object),
      ),
    )
  })
})

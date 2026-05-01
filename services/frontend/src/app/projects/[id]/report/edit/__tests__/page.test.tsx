/**
 * @jest-environment jsdom
 */

import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useRouter } from 'next/navigation'
import ReportEditorPage from '../../edit/page'

jest.mock('next/navigation', () => ({
  useRouter: jest.fn(),
}))

jest.mock('@/contexts/AuthContext', () => ({
  useAuth: jest.fn(),
}))

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: jest.fn(),
}))

jest.mock('@/components/shared/Toast', () => ({
  useToast: jest.fn(() => ({ addToast: jest.fn() })),
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

jest.mock('@/components/shared/Button', () => ({
  Button: ({ children, onClick, disabled, variant }: any) => (
    <button onClick={onClick} disabled={disabled} data-variant={variant}>
      {children}
    </button>
  ),
}))

jest.mock('@/components/shared/Label', () => ({
  Label: ({ children, htmlFor }: any) => (
    <label htmlFor={htmlFor}>{children}</label>
  ),
}))

jest.mock('@/components/shared/Textarea', () => ({
  Textarea: ({ id, value, onChange, placeholder, rows }: any) => (
    <textarea
      id={id}
      value={value}
      onChange={onChange}
      placeholder={placeholder}
      rows={rows}
      data-testid={`textarea-${id}`}
    />
  ),
}))

jest.mock('@heroicons/react/24/outline', () => ({
  ArrowLeftIcon: () => <svg data-testid="arrow-left-icon" />,
}))

const mockRouter = { push: jest.fn(), replace: jest.fn() }
const mockAddToast = jest.fn()
const mockT = (key: string, params?: any) => key

const mockSuperadmin = {
  id: 'user-1',
  username: 'admin',
  email: 'admin@test.com',
  is_superadmin: true,
  is_active: true,
  role: 'ORG_ADMIN',
}

const mockContributor = {
  id: 'user-2',
  username: 'contributor',
  email: 'contributor@test.com',
  is_superadmin: false,
  is_active: true,
  role: 'CONTRIBUTOR',
}

const mockAnnotator = {
  id: 'user-3',
  username: 'annotator',
  email: 'annotator@test.com',
  is_superadmin: false,
  is_active: true,
  role: 'ANNOTATOR',
}

const mockReport = {
  id: 'report-1',
  project_id: 'proj-1',
  project_title: 'Test Project',
  is_published: false,
  content: {
    sections: {
      project_info: {
        custom_title: 'Custom Title',
        custom_description: 'Custom Description',
      },
      data: { custom_text: 'Data text' },
      annotations: {
        custom_text: 'Annotations text',
        acknowledgment_text: 'Thanks everyone',
      },
      generation: { custom_text: 'Generation text' },
      evaluation: {
        custom_interpretation: 'Interpretation text',
        conclusions: 'Conclusion text',
      },
    },
    metadata: {},
  },
}

function createParams(id: string) {
  return Promise.resolve({ id })
}

describe('ReportEditorPage', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    ;(useRouter as jest.Mock).mockReturnValue(mockRouter)
    ;(useAuth as jest.Mock).mockReturnValue({ user: mockSuperadmin })
    ;(useI18n as jest.Mock).mockReturnValue({ t: mockT })

    // Reset the useToast mock
    const { useToast } = require('@/components/shared/Toast')
    ;(useToast as jest.Mock).mockReturnValue({ addToast: mockAddToast })

    // Mock global fetch
    global.fetch = jest.fn()
  })

  afterEach(() => {
    jest.restoreAllMocks()
  })

  it('should show loading state initially', async () => {
    ;(global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockReport),
    })

    render(<ReportEditorPage params={createParams('proj-1')} />)

    expect(
      screen.getByText('project.report.editor.loading')
    ).toBeInTheDocument()
  })

  it('should load and display report data', async () => {
    ;(global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockReport),
    })

    render(<ReportEditorPage params={createParams('proj-1')} />)

    await waitFor(() => {
      expect(
        screen.getByText('project.report.editor.projectInfo.title')
      ).toBeInTheDocument()
    })

    // Check section headings
    expect(
      screen.getByText('project.report.editor.dataSection.title')
    ).toBeInTheDocument()
    expect(
      screen.getByText('project.report.editor.annotationsSection.title')
    ).toBeInTheDocument()
    expect(
      screen.getByText('project.report.editor.generationSection.title')
    ).toBeInTheDocument()
    expect(
      screen.getByText('project.report.editor.evaluationSection.title')
    ).toBeInTheDocument()
    // Check the h1 title appears (may also be in breadcrumb)
    expect(
      screen.getAllByText('project.report.editor.title').length
    ).toBeGreaterThanOrEqual(1)
  })

  it('should populate fields from report content', async () => {
    ;(global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockReport),
    })

    render(<ReportEditorPage params={createParams('proj-1')} />)

    await waitFor(() => {
      const titleInput = screen.getByPlaceholderText(
        'Test Project'
      ) as HTMLInputElement
      expect(titleInput.value).toBe('Custom Title')
    })
  })

  it('should handle fetch error and redirect', async () => {
    ;(global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: false,
      status: 500,
    })

    render(<ReportEditorPage params={createParams('proj-1')} />)

    await waitFor(() => {
      expect(mockAddToast).toHaveBeenCalledWith(
        'project.report.editor.failedToLoad',
        'error'
      )
    })

    expect(mockRouter.push).toHaveBeenCalledWith('/projects/proj-1')
  })

  it('should redirect non-permitted users', async () => {
    ;(useAuth as jest.Mock).mockReturnValue({ user: mockAnnotator })

    render(<ReportEditorPage params={createParams('proj-1')} />)

    await waitFor(() => {
      expect(mockRouter.push).toHaveBeenCalledWith('/projects')
    })
  })

  it('should save report on button click', async () => {
    // Mount-time fetches: (1) the main report, (2) the report-data feed used to
    // populate the available-metrics checkboxes. Then (3) the PUT on save.
    ;(global.fetch as jest.Mock)
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockReport),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ evaluation_charts: { by_model: {}, metric_metadata: {} } }),
      })
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve({}) })

    const user = userEvent.setup()
    render(<ReportEditorPage params={createParams('proj-1')} />)

    await waitFor(() => {
      expect(
        screen.getByText('project.report.editor.saveReport')
      ).toBeInTheDocument()
    })

    await user.click(screen.getByText('project.report.editor.saveReport'))

    await waitFor(() => {
      expect(mockAddToast).toHaveBeenCalledWith(
        'project.report.editor.savedSuccessfully',
        'success'
      )
    })

    // Three fetches in order: GET report, GET report data, PUT report.
    expect(global.fetch).toHaveBeenCalledTimes(3)
    const calls = (global.fetch as jest.Mock).mock.calls
    expect(calls[0][0]).toBe('/api/projects/proj-1/report')
    expect(calls[2][0]).toBe('/api/projects/proj-1/report')
    expect(calls[2][1]).toMatchObject({ method: 'POST' })
  })

  it('should handle save error', async () => {
    ;(global.fetch as jest.Mock)
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockReport),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ evaluation_charts: { by_model: {}, metric_metadata: {} } }),
      })
      .mockResolvedValueOnce({ ok: false, status: 500 })

    const user = userEvent.setup()
    render(<ReportEditorPage params={createParams('proj-1')} />)

    await waitFor(() => {
      expect(
        screen.getByText('project.report.editor.saveReport')
      ).toBeInTheDocument()
    })

    await user.click(screen.getByText('project.report.editor.saveReport'))

    await waitFor(() => {
      expect(mockAddToast).toHaveBeenCalledWith(
        'project.report.editor.failedToSave',
        'error'
      )
    })
  })

  it('should navigate back when cancel clicked', async () => {
    ;(global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockReport),
    })

    const user = userEvent.setup()
    render(<ReportEditorPage params={createParams('proj-1')} />)

    await waitFor(() => {
      expect(
        screen.getByText('project.report.editor.cancel')
      ).toBeInTheDocument()
    })

    await user.click(screen.getByText('project.report.editor.cancel'))

    expect(mockRouter.push).toHaveBeenCalledWith('/projects/proj-1')
  })

  it('should navigate back when back button clicked', async () => {
    ;(global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockReport),
    })

    const user = userEvent.setup()
    render(<ReportEditorPage params={createParams('proj-1')} />)

    await waitFor(() => {
      expect(
        screen.getByText('project.report.editor.backToProject')
      ).toBeInTheDocument()
    })

    await user.click(screen.getByText('project.report.editor.backToProject'))

    expect(mockRouter.push).toHaveBeenCalledWith('/projects/proj-1')
  })

  it('should show loading when user is null', () => {
    ;(useAuth as jest.Mock).mockReturnValue({ user: null })

    render(<ReportEditorPage params={createParams('proj-1')} />)

    expect(
      screen.getByText('project.report.editor.loading')
    ).toBeInTheDocument()
  })

  it('should render nothing for non-superadmin after load', async () => {
    ;(useAuth as jest.Mock).mockReturnValue({
      user: { ...mockContributor, is_superadmin: false, role: 'ANNOTATOR' },
    })

    const { container } = render(
      <ReportEditorPage params={createParams('proj-1')} />
    )

    await waitFor(() => {
      expect(mockRouter.push).toHaveBeenCalledWith('/projects')
    })
  })

  it('should update text fields on change', async () => {
    ;(global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockReport),
    })

    const user = userEvent.setup()
    render(<ReportEditorPage params={createParams('proj-1')} />)

    await waitFor(() => {
      expect(screen.getByTestId('textarea-customDescription')).toBeInTheDocument()
    })

    const descTextarea = screen.getByTestId('textarea-customDescription')
    await user.clear(descTextarea)
    await user.type(descTextarea, 'New description')

    expect(descTextarea).toHaveValue('New description')
  })

  it('should render breadcrumb with correct items', async () => {
    ;(global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockReport),
    })

    render(<ReportEditorPage params={createParams('proj-1')} />)

    await waitFor(() => {
      expect(screen.getByTestId('breadcrumb')).toBeInTheDocument()
    })

    expect(screen.getByText('Test Project')).toBeInTheDocument()
  })

  describe('charts_config persistence', () => {
    const reportWith = (chartsConfig: any) => ({
      ...mockReport,
      content: {
        ...mockReport.content,
        sections: {
          ...mockReport.content.sections,
          evaluation: {
            ...mockReport.content.sections.evaluation,
            charts_config: chartsConfig,
          },
        },
      },
    })

    const reportDataResp = (byModel: Record<string, Record<string, number>>) => ({
      evaluation_charts: {
        by_model: byModel,
        metric_metadata: Object.keys(
          Object.values(byModel)[0] ?? {}
        ).reduce(
          (acc, m) => ({ ...acc, [m]: { name: m, range: [0, 1] } }),
          {} as Record<string, any>
        ),
      },
    })

    it('saves visible_metrics + available_views + default_view to charts_config', async () => {
      const fetches = global.fetch as jest.Mock
      // GET project report
      fetches.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(reportWith({})),
      })
      // GET report data (drives the metric checklist)
      fetches.mockResolvedValueOnce({
        ok: true,
        json: () =>
          Promise.resolve(
            reportDataResp({
              'gpt-4': { bleu: 0.5, rouge: 0.6, exact_match: 0.7 },
            })
          ),
      })
      // POST save
      fetches.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({}),
      })

      const userE = userEvent.setup()
      render(<ReportEditorPage params={createParams('proj-1')} />)

      await waitFor(() => {
        expect(
          screen.getByText('project.report.editor.evaluationSection.title')
        ).toBeInTheDocument()
      })
      // Wait for the metric checklist to load.
      await waitFor(() => {
        expect(screen.getByLabelText('bleu')).toBeInTheDocument()
      })

      // Uncheck "rouge" — only bleu + exact_match should persist.
      await userE.click(screen.getByLabelText('rouge'))

      const saveBtn = screen.getByText('project.report.editor.saveReport')
      await userE.click(saveBtn)

      await waitFor(() => {
        const postCall = fetches.mock.calls.find(
          (c: any[]) => c[1]?.method === 'POST'
        )
        expect(postCall).toBeDefined()
        const body = JSON.parse(postCall![1].body)
        const cfg = body.content.sections.evaluation.charts_config
        expect(cfg.visible_metrics.sort()).toEqual(['bleu', 'exact_match'])
        // Defaults: only 'data' available, default = 'data'.
        expect(cfg.default_view).toBe('data')
        expect(cfg.available_views).toEqual(['data'])
      })
    })

    it('initialises checkboxes from persisted visible_metrics', async () => {
      const fetches = global.fetch as jest.Mock
      fetches.mockResolvedValueOnce({
        ok: true,
        json: () =>
          Promise.resolve(
            reportWith({
              visible_metrics: ['bleu'], // only bleu pre-selected
              available_views: ['data', 'bar'],
              default_view: 'bar',
            })
          ),
      })
      fetches.mockResolvedValueOnce({
        ok: true,
        json: () =>
          Promise.resolve(
            reportDataResp({ 'gpt-4': { bleu: 0.5, rouge: 0.6 } })
          ),
      })

      render(<ReportEditorPage params={createParams('proj-1')} />)

      await waitFor(() => {
        expect(screen.getByLabelText('bleu')).toBeChecked()
      })
      expect(screen.getByLabelText('rouge')).not.toBeChecked()
    })
  })
})

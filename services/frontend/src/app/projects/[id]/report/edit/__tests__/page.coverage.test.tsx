/**
 * Coverage-focused tests for ReportEditorPage
 *
 * Targets branches the main suite does not exercise:
 * - Non-superadmin roles (CONTRIBUTOR / ORG_ADMIN / null user) never fetch
 * - Report with empty/missing sections (defensive reads)
 * - Save with empty field values (empty string -> null)
 * - Saving text while the request is pending
 * - Config select hidden when the primary metric has no configuration
 * - Refresh when the previously chosen primary metric disappears
 */

/**
 * @jest-environment jsdom
 */

import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import {
  getProjectReport,
  refreshReport,
  updateProjectReport,
} from '@/lib/api/reports'
import { REPORT_SNAPSHOT_FIXTURE } from '@/lib/reports/fixture'
import { render, screen, waitFor, within } from '@testing-library/react'
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

jest.mock('@/lib/api/reports', () => ({
  getProjectReport: jest.fn(),
  updateProjectReport: jest.fn(),
  refreshReport: jest.fn(),
}))

jest.mock('@/lib/api/evaluation-types', () => ({
  getMetricDefinitions: () => ({}),
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

jest.mock('@/components/shared/ToggleSwitch', () => ({
  ToggleSwitch: ({ enabled, onChange, label }: any) => (
    <button
      type="button"
      role="switch"
      aria-checked={enabled}
      aria-label={label}
      onClick={() => onChange(!enabled)}
    >
      {label}
    </button>
  ),
}))

jest.mock('@heroicons/react/24/outline', () => ({
  ArrowLeftIcon: () => <svg data-testid="arrow-left-icon" />,
  ArrowPathIcon: () => <svg data-testid="arrow-path-icon" />,
  ArrowTopRightOnSquareIcon: () => <svg data-testid="external-icon" />,
}))

const mockRouter = { push: jest.fn(), replace: jest.fn() }
const mockAddToast = jest.fn()
const mockT = (key: string) => key
const mockGet = getProjectReport as jest.Mock
const mockUpdate = updateProjectReport as jest.Mock
const mockRefresh = refreshReport as jest.Mock

function createParams(id: string) {
  return Promise.resolve({ id })
}

const mockContributor = {
  id: 'user-2',
  username: 'contributor',
  email: 'contributor@test.com',
  is_superadmin: false,
  is_active: true,
  role: 'CONTRIBUTOR',
}

const mockOrgAdmin = {
  id: 'user-4',
  username: 'orgadmin',
  email: 'orgadmin@test.com',
  is_superadmin: false,
  is_active: true,
  role: 'ORG_ADMIN',
}

const mockSuperadmin = {
  id: 'user-1',
  username: 'admin',
  email: 'admin@test.com',
  is_superadmin: true,
  is_active: true,
  role: 'ORG_ADMIN',
}

const mockReportEmptySections = {
  id: 'report-1',
  project_id: 'proj-1',
  project_title: 'Test Project',
  is_published: false,
  is_public: false,
  content: {
    sections: {},
    metadata: {},
  },
}

const mockReportFullSections = {
  id: 'report-2',
  project_id: 'proj-1',
  project_title: 'Test Project',
  is_published: false,
  is_public: false,
  content: {
    sections: {
      project_info: {
        custom_title: 'My Title',
        custom_description: 'My Description',
      },
      data: { custom_text: 'Data text' },
      annotations: {
        custom_text: 'Ann text',
        acknowledgment_text: 'Thanks',
      },
      generation: { custom_text: 'Gen text' },
      evaluation: {
        custom_interpretation: 'Interp',
        conclusions: 'Concl',
      },
    },
    metadata: {},
    snapshot: REPORT_SNAPSHOT_FIXTURE,
  },
}

describe('ReportEditorPage - branch coverage', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    ;(useRouter as jest.Mock).mockReturnValue(mockRouter)
    ;(useI18n as jest.Mock).mockReturnValue({ t: mockT })
    ;(useAuth as jest.Mock).mockReturnValue({
      user: mockSuperadmin,
      isLoading: false,
    })

    const { useToast } = require('@/components/shared/Toast')
    ;(useToast as jest.Mock).mockReturnValue({ addToast: mockAddToast })
    mockUpdate.mockImplementation(async (_id: string, content: any) => ({
      ...mockReportFullSections,
      content,
    }))
  })

  afterEach(() => {
    jest.restoreAllMocks()
  })

  describe('Role-based access', () => {
    it.each([
      ['CONTRIBUTOR', mockContributor],
      ['ORG_ADMIN', mockOrgAdmin],
    ])('%s gets the superadmin-only notice and no fetch', async (_role, user) => {
      ;(useAuth as jest.Mock).mockReturnValue({ user, isLoading: false })

      render(<ReportEditorPage params={createParams('proj-1')} />)

      await waitFor(() => {
        expect(
          screen.getByText('reports.editor.notSuperadmin')
        ).toBeInTheDocument()
      })
      expect(screen.getByText('reports.editor.notSuperadminHint')).toBeInTheDocument()
      expect(mockGet).not.toHaveBeenCalled()
      expect(mockRouter.push).not.toHaveBeenCalled()
      expect(document.querySelector('h1')).not.toBeNull()
    })

    it('shows the notice for an anonymous (null) user once auth settled', async () => {
      ;(useAuth as jest.Mock).mockReturnValue({ user: null, isLoading: false })

      render(<ReportEditorPage params={createParams('proj-1')} />)

      await waitFor(() => {
        expect(
          screen.getByText('reports.editor.notSuperadmin')
        ).toBeInTheDocument()
      })
      expect(mockGet).not.toHaveBeenCalled()
    })

    it('keeps loading while user is null and the auth state is unknown', () => {
      ;(useAuth as jest.Mock).mockReturnValue({ user: null })

      render(<ReportEditorPage params={createParams('proj-1')} />)

      expect(
        screen.getByText('project.report.editor.loading')
      ).toBeInTheDocument()
    })
  })

  describe('Report with empty sections', () => {
    it('handles report with no section data (all defaults)', async () => {
      mockGet.mockResolvedValue(mockReportEmptySections)

      render(<ReportEditorPage params={createParams('proj-1')} />)

      await waitFor(() => {
        expect(
          screen.getByText('project.report.editor.projectInfo.title')
        ).toBeInTheDocument()
      })

      const titleInput = screen.getByPlaceholderText(
        'Test Project'
      ) as HTMLInputElement
      expect(titleInput.value).toBe('')
      // Every section switch defaults to visible.
      screen
        .getAllByRole('switch', { name: 'reports.editor.showSection' })
        .forEach((sw) => expect(sw).toHaveAttribute('aria-checked', 'true'))
      expect(screen.getByText('reports.editor.noSnapshot')).toBeInTheDocument()
    })

    it('handles report with no content.sections at all and saves it', async () => {
      mockGet.mockResolvedValue({
        id: 'report-3',
        project_id: 'proj-1',
        project_title: 'Test Project',
        is_published: false,
        content: {
          metadata: {},
        },
      })
      const user = userEvent.setup()

      render(<ReportEditorPage params={createParams('proj-1')} />)

      await waitFor(() => {
        expect(
          screen.getByText('project.report.editor.projectInfo.title')
        ).toBeInTheDocument()
      })

      await user.click(screen.getByText('project.report.editor.saveReport'))

      await waitFor(() => expect(mockUpdate).toHaveBeenCalled())
      const content = mockUpdate.mock.calls[0][1]
      expect(content.metadata).toEqual({})
      expect(content.sections.project_info.visible).toBe(true)
      expect(content.sections.project_info.custom_title).toBeNull()
      expect(content.sections.evaluation.charts_config.visible_metrics).toBeUndefined()
    })
  })

  describe('Save edge cases', () => {
    it('shows saving text on the save button while saving', async () => {
      mockGet.mockResolvedValue(mockReportFullSections)
      mockUpdate.mockImplementation(() => new Promise(() => {}))
      const user = userEvent.setup()

      render(<ReportEditorPage params={createParams('proj-1')} />)

      await waitFor(() => {
        expect(
          screen.getByText('project.report.editor.saveReport')
        ).toBeInTheDocument()
      })

      await user.click(screen.getByText('project.report.editor.saveReport'))

      await waitFor(() => {
        expect(
          screen.getByText('project.report.editor.saving')
        ).toBeInTheDocument()
      })
    })

    it('sends null for cleared text fields', async () => {
      mockGet.mockResolvedValue(mockReportFullSections)
      const user = userEvent.setup()

      render(<ReportEditorPage params={createParams('proj-1')} />)

      await waitFor(() => {
        expect(screen.getByPlaceholderText('Test Project')).toBeInTheDocument()
      })

      await user.clear(screen.getByPlaceholderText('Test Project'))
      await user.clear(screen.getByTestId('textarea-acknowledgment'))
      await user.click(screen.getByText('project.report.editor.saveReport'))

      await waitFor(() => expect(mockUpdate).toHaveBeenCalledTimes(1))
      const content = mockUpdate.mock.calls[0][1]
      expect(content.sections.project_info.custom_title).toBeNull()
      expect(content.sections.project_info.custom_description).toBe(
        'My Description'
      )
      expect(content.sections.annotations.acknowledgment_text).toBeNull()
      expect(content.sections.annotations.custom_text).toBe('Ann text')
    })

    it('does nothing when the primary metric is cleared to "none"', async () => {
      mockGet.mockResolvedValue(mockReportFullSections)
      const user = userEvent.setup()

      render(<ReportEditorPage params={createParams('proj-1')} />)

      await waitFor(() => {
        expect(screen.getByLabelText('reports.editor.primaryMetric')).toBeInTheDocument()
      })

      await user.selectOptions(
        screen.getByLabelText('reports.editor.primaryMetric'),
        ''
      )
      expect(
        screen.getByText('reports.editor.noConfigsForMetric')
      ).toBeInTheDocument()
      expect(
        screen.queryByLabelText('reports.editor.primaryConfig')
      ).not.toBeInTheDocument()

      await user.click(screen.getByText('project.report.editor.saveReport'))

      await waitFor(() => expect(mockUpdate).toHaveBeenCalled())
      const cfg = mockUpdate.mock.calls[0][1].sections.evaluation.charts_config
      expect(cfg.primary_metric).toBeNull()
      expect(cfg.primary_config_id).toBeNull()
    })
  })

  describe('Refresh reconciliation', () => {
    it('falls back to the new snapshot defaults when the chosen metric disappears', async () => {
      mockGet.mockResolvedValue({
        ...mockReportFullSections,
        content: {
          ...mockReportFullSections.content,
          sections: {
            ...mockReportFullSections.content.sections,
            evaluation: {
              ...mockReportFullSections.content.sections.evaluation,
              charts_config: { primary_metric: 'bleu', primary_config_id: 'cfg-bleu' },
            },
          },
        },
      })
      const withoutBleu = {
        ...REPORT_SNAPSHOT_FIXTURE,
        methods: REPORT_SNAPSHOT_FIXTURE.methods.filter((m) => m.id !== 'bleu'),
        configs: REPORT_SNAPSHOT_FIXTURE.configs.filter((c) => c.id !== 'cfg-bleu'),
      }
      mockRefresh.mockResolvedValue({
        ...mockReportFullSections,
        content: { ...mockReportFullSections.content, snapshot: withoutBleu },
      })
      const user = userEvent.setup()

      render(<ReportEditorPage params={createParams('proj-1')} />)

      await waitFor(() => {
        expect(
          (screen.getByLabelText('reports.editor.primaryMetric') as HTMLSelectElement).value
        ).toBe('bleu')
      })

      await user.click(screen.getByText('reports.editor.refresh'))

      await waitFor(() => {
        expect(
          (screen.getByLabelText('reports.editor.primaryMetric') as HTMLSelectElement).value
        ).toBe('llm_judge_falloesung')
      })
      expect(
        (screen.getByLabelText('reports.editor.primaryConfig') as HTMLSelectElement).value
      ).toBe('cfg-judge-sonnet')
      expect(
        within(screen.getByTestId('visible-metrics')).queryByLabelText('BLEU')
      ).not.toBeInTheDocument()
    })

    it('derives a fresh state when refreshing before anything loaded into state', async () => {
      // Report without snapshot, then refresh brings one.
      mockGet.mockResolvedValue({
        ...mockReportFullSections,
        content: { ...mockReportFullSections.content, snapshot: null },
      })
      mockRefresh.mockResolvedValue(mockReportFullSections)
      const user = userEvent.setup()

      render(<ReportEditorPage params={createParams('proj-1')} />)

      await waitFor(() => {
        expect(screen.getByText('reports.editor.noSnapshot')).toBeInTheDocument()
      })

      await user.click(screen.getByText('reports.editor.refresh'))

      await waitFor(() => {
        expect(screen.getByLabelText('reports.editor.primaryMetric')).toBeInTheDocument()
      })
      // All metrics of the new snapshot are visible by default.
      within(screen.getByTestId('visible-metrics'))
        .getAllByRole('checkbox')
        .forEach((cb) => expect(cb).toBeChecked())
      expect(screen.getByText('reports.editor.snapshotGeneratedAt')).toBeInTheDocument()
    })
  })
})

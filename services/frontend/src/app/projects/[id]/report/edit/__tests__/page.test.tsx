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
import type { ReportSnapshot } from '@/types/report'
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
  getMetricDefinitions: () => ({
    bleu: { name: 'bleu', display_name: 'BLEU Score' },
  }),
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

/** Fixture + an internal `_raw` metric and a custom (BYOM) model. */
const snapshot: ReportSnapshot = {
  ...REPORT_SNAPSHOT_FIXTURE,
  methods: [
    ...REPORT_SNAPSHOT_FIXTURE.methods,
    {
      id: 'llm_judge_falloesung_raw',
      name: 'Raw judge output',
      category: 'llm_judge',
      scale: 'raw',
      higher_is_better: true,
    },
  ],
  models: [
    ...REPORT_SNAPSHOT_FIXTURE.models,
    {
      id: 'byom-custom-1',
      kind: 'model',
      label: 'Custom Model',
      provider: 'custom',
      is_custom: true,
    },
  ],
}

const baseReport = {
  id: 'report-1',
  project_id: 'proj-1',
  project_title: 'Test Project',
  is_published: false,
  is_public: false,
  can_publish: true,
  can_publish_reason: '',
  created_by: 'user-1',
  created_at: '2026-09-01T00:00:00Z',
  content: {
    sections: {
      project_info: {
        status: 'completed',
        editable: true,
        visible: true,
        title: 'Test Project',
        description: 'Auto description',
        custom_title: 'Custom Title',
        custom_description: 'Custom Description',
      },
      data: {
        status: 'completed',
        editable: true,
        visible: true,
        task_count: 15,
        show_count: true,
        custom_text: 'Data text',
      },
      annotations: {
        status: 'completed',
        editable: true,
        visible: true,
        annotation_count: 224,
        show_count: true,
        show_participants: true,
        custom_text: 'Annotations text',
        acknowledgment_text: 'Thanks everyone',
      },
      generation: {
        status: 'completed',
        editable: true,
        visible: true,
        models: ['gpt-5.4'],
        show_models: true,
        show_config: false,
        custom_text: 'Generation text',
      },
      evaluation: {
        status: 'completed',
        editable: true,
        visible: true,
        methods: ['llm_judge_falloesung'],
        custom_interpretation: 'Interpretation text',
        conclusions: 'Conclusion text',
        charts_config: {},
      },
    },
    metadata: {
      last_auto_update: '2026-09-01T00:00:00Z',
      sections_completed: ['project_info'],
      can_publish: true,
    },
    snapshot,
  },
}

function createParams(id: string) {
  return Promise.resolve({ id })
}

const reportWith = (chartsConfig: any, extra: Record<string, any> = {}) => ({
  ...baseReport,
  ...extra,
  content: {
    ...baseReport.content,
    ...(extra.content ?? {}),
    sections: {
      ...baseReport.content.sections,
      evaluation: {
        ...baseReport.content.sections.evaluation,
        charts_config: chartsConfig,
      },
    },
  },
})

async function renderLoaded(report: any = baseReport) {
  mockGet.mockResolvedValue(report)
  const user = userEvent.setup()
  render(<ReportEditorPage params={createParams('proj-1')} />)
  await waitFor(() => {
    expect(
      screen.getByText('project.report.editor.saveReport')
    ).toBeInTheDocument()
  })
  return user
}

describe('ReportEditorPage', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    ;(useRouter as jest.Mock).mockReturnValue(mockRouter)
    ;(useAuth as jest.Mock).mockReturnValue({
      user: mockSuperadmin,
      isLoading: false,
    })
    ;(useI18n as jest.Mock).mockReturnValue({ t: mockT })

    const { useToast } = require('@/components/shared/Toast')
    ;(useToast as jest.Mock).mockReturnValue({ addToast: mockAddToast })
    mockUpdate.mockImplementation(async (_id: string, content: any) => ({
      ...baseReport,
      content,
    }))
  })

  afterEach(() => {
    jest.restoreAllMocks()
  })

  it('shows loading state initially', () => {
    mockGet.mockReturnValue(new Promise(() => {}))

    render(<ReportEditorPage params={createParams('proj-1')} />)

    expect(
      screen.getByText('project.report.editor.loading')
    ).toBeInTheDocument()
  })

  it('shows loading while the session is resolving', () => {
    ;(useAuth as jest.Mock).mockReturnValue({ user: null, isLoading: true })

    render(<ReportEditorPage params={createParams('proj-1')} />)

    expect(
      screen.getByText('project.report.editor.loading')
    ).toBeInTheDocument()
    expect(mockGet).not.toHaveBeenCalled()
  })

  it('loads and displays all section headings and populated fields', async () => {
    await renderLoaded()

    expect(mockGet).toHaveBeenCalledWith('proj-1')
    expect(
      screen.getByText('project.report.editor.projectInfo.title')
    ).toBeInTheDocument()
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

    const titleInput = screen.getByPlaceholderText(
      'Test Project'
    ) as HTMLInputElement
    expect(titleInput.value).toBe('Custom Title')
    expect(screen.getByTestId('textarea-customDescription')).toHaveValue(
      'Custom Description'
    )
    expect(screen.getByTestId('textarea-dataText')).toHaveValue('Data text')
    expect(screen.getByTestId('textarea-acknowledgment')).toHaveValue(
      'Thanks everyone'
    )
    expect(screen.getByTestId('textarea-conclusions')).toHaveValue(
      'Conclusion text'
    )
    expect(screen.getByTestId('breadcrumb')).toHaveTextContent('Test Project')
  })

  describe('permissions', () => {
    it('shows a clear message (no blank page, no redirect) for non-superadmins', async () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: mockContributor,
        isLoading: false,
      })

      render(<ReportEditorPage params={createParams('proj-1')} />)

      await waitFor(() => {
        expect(screen.getByRole('alert')).toHaveTextContent(
          'reports.editor.notSuperadmin'
        )
      })
      expect(mockGet).not.toHaveBeenCalled()
      expect(mockRouter.push).not.toHaveBeenCalled()
    })

    it('offers the back-to-project button in the message', async () => {
      ;(useAuth as jest.Mock).mockReturnValue({
        user: { ...mockContributor, role: 'ORG_ADMIN' },
        isLoading: false,
      })
      const user = userEvent.setup()

      render(<ReportEditorPage params={createParams('proj-1')} />)

      await user.click(
        await screen.findByText('project.report.editor.backToProject')
      )
      expect(mockRouter.push).toHaveBeenCalledWith('/projects/proj-1')
    })
  })

  it('handles a load error: toast + redirect to the project', async () => {
    mockGet.mockRejectedValue(new Error('boom'))

    render(<ReportEditorPage params={createParams('proj-1')} />)

    await waitFor(() => {
      expect(mockAddToast).toHaveBeenCalledWith(
        'project.report.editor.failedToLoad',
        'error'
      )
    })
    expect(mockRouter.push).toHaveBeenCalledWith('/projects/proj-1')
  })

  describe('presentation controls from the snapshot', () => {
    it('offers non-derived metrics as primary metric, preselected from the snapshot', async () => {
      await renderLoaded()

      const select = screen.getByLabelText(
        'reports.editor.primaryMetric'
      ) as HTMLSelectElement
      expect(select.value).toBe('llm_judge_falloesung')
      const values = Array.from(select.options).map((o) => o.value)
      expect(values).toEqual([
        '',
        'llm_judge_falloesung',
        'korrektur_falloesung',
        'bleu',
      ])
      // Registry display name wins over the snapshot name.
      expect(
        Array.from(select.options).find((o) => o.value === 'bleu')?.textContent
      ).toBe('BLEU Score')
    })

    it('lists judge configurations of the primary metric with judge label and n', async () => {
      await renderLoaded()

      const select = screen.getByLabelText(
        'reports.editor.primaryConfig'
      ) as HTMLSelectElement
      expect(select.value).toBe('cfg-judge-sonnet')
      const labels = Array.from(select.options).map((o) => o.textContent)
      expect(labels).toEqual([
        'Notenpunkte (Abo-Modell) · Claude Sonnet 4.6 (n=900)',
        'Notenpunkte (Gratis-Modell) · GPT-5 mini (n=420)',
      ])
    })

    it('switching the primary metric picks the config with most samples for it', async () => {
      const user = await renderLoaded()

      await user.selectOptions(
        screen.getByLabelText('reports.editor.primaryMetric'),
        'korrektur_falloesung'
      )

      const cfgSelect = screen.getByLabelText(
        'reports.editor.primaryConfig'
      ) as HTMLSelectElement
      expect(cfgSelect.value).toBe('cfg-korrektur')
      expect(Array.from(cfgSelect.options).map((o) => o.textContent)).toEqual([
        'Korrektur (n=184)',
      ])
    })

    it('lists visible metrics with display names and hides *_raw/_details keys', async () => {
      await renderLoaded()

      const box = within(screen.getByTestId('visible-metrics'))
      expect(box.getByLabelText('Falllösung LLM Judge')).toBeChecked()
      expect(box.getByLabelText('Notenpunkte (Falllösung)')).toBeChecked()
      expect(box.getByLabelText('BLEU Score')).toBeChecked()
      expect(box.queryByLabelText('Raw judge output')).not.toBeInTheDocument()
      expect(box.getAllByRole('checkbox')).toHaveLength(5)
    })

    it('lists all judge configurations as visible-config checkboxes', async () => {
      await renderLoaded()

      const box = within(screen.getByTestId('visible-configs'))
      expect(box.getAllByRole('checkbox')).toHaveLength(4)
      expect(box.getByLabelText('Korrektur (n=184)')).toBeChecked()
      expect(box.getByLabelText('bleu (n=300)')).toBeChecked()
    })

    it('lists subjects de-duplicated, models first, with a custom hint for BYOM', async () => {
      await renderLoaded()

      const box = within(screen.getByTestId('hidden-subjects'))
      const labels = box
        .getAllByRole('checkbox')
        .map((cb) => cb.closest('label')?.textContent)
      // gpt-5.4 appears in several series but only once here
      expect(labels.filter((l) => l?.startsWith('GPT-5.4'))).toHaveLength(1)
      // models (5) first, then humans (2)
      expect(labels.slice(0, 5)).toEqual([
        'GPT-5.4',
        'Claude Opus 4.7',
        'DeepSeek V4 Flash',
        'Llama 4 Maverick',
        'Custom Model(reports.editor.customModel)',
      ])
      expect(labels.slice(5)).toEqual(['KindAlly', 'BraveOtter'])
      box.getAllByRole('checkbox').forEach((cb) => expect(cb).not.toBeChecked())
    })

    it('initialises controls from a persisted charts_config', async () => {
      await renderLoaded(
        reportWith({
          primary_metric: 'bleu',
          primary_config_id: 'cfg-bleu',
          visible_metrics: ['bleu'],
          visible_configs: ['cfg-bleu'],
          hidden_subjects: ['annotator:KindAlly'],
          show_distribution: false,
          show_humans: false,
        })
      )

      expect(
        (screen.getByLabelText('reports.editor.primaryMetric') as HTMLSelectElement)
          .value
      ).toBe('bleu')
      expect(
        (screen.getByLabelText('reports.editor.primaryConfig') as HTMLSelectElement)
          .value
      ).toBe('cfg-bleu')
      const metrics = within(screen.getByTestId('visible-metrics'))
      expect(metrics.getByLabelText('BLEU Score')).toBeChecked()
      expect(metrics.getByLabelText('Falllösung LLM Judge')).not.toBeChecked()
      const configs = within(screen.getByTestId('visible-configs'))
      expect(configs.getByLabelText('bleu (n=300)')).toBeChecked()
      expect(configs.getByLabelText('Korrektur (n=184)')).not.toBeChecked()
      expect(
        within(screen.getByTestId('hidden-subjects')).getByLabelText('KindAlly')
      ).toBeChecked()
      expect(
        screen.getByRole('switch', { name: 'reports.editor.showDistribution' })
      ).toHaveAttribute('aria-checked', 'false')
      expect(
        screen.getByRole('switch', { name: 'reports.editor.showHumans' })
      ).toHaveAttribute('aria-checked', 'false')
    })

    it('shows the no-metrics hint when there is no snapshot', async () => {
      await renderLoaded({
        ...baseReport,
        content: { ...baseReport.content, snapshot: null },
      })

      expect(
        screen.getByText(
          'project.report.editor.evaluationSection.noMetricsAvailable'
        )
      ).toBeInTheDocument()
      expect(screen.getByText('reports.editor.noSnapshot')).toBeInTheDocument()
      expect(
        screen.queryByLabelText('reports.editor.primaryMetric')
      ).not.toBeInTheDocument()
    })
  })

  describe('save', () => {
    it('round-trips the whole content and overlays edited fields', async () => {
      const user = await renderLoaded()

      // Edit a text, hide a section, flip flags, adjust presentation.
      await user.clear(screen.getByTestId('textarea-conclusions'))
      await user.type(screen.getByTestId('textarea-conclusions'), 'New conclusions')
      await user.click(
        within(screen.getByTestId('section-data')).getByRole('switch', {
          name: 'reports.editor.showSection',
        })
      )
      await user.click(
        screen.getByRole('switch', { name: 'reports.editor.showParticipants' })
      )
      await user.click(
        screen.getByRole('switch', { name: 'reports.editor.showDistribution' })
      )
      await user.click(
        within(screen.getByTestId('visible-metrics')).getByLabelText('BLEU Score')
      )
      await user.click(
        within(screen.getByTestId('visible-configs')).getByLabelText('bleu (n=300)')
      )
      await user.click(
        within(screen.getByTestId('hidden-subjects')).getByLabelText(
          'Llama 4 Maverick'
        )
      )
      await user.selectOptions(
        screen.getByLabelText('reports.editor.primaryConfig'),
        'cfg-judge-mini'
      )

      await user.click(screen.getByText('project.report.editor.saveReport'))

      await waitFor(() => {
        expect(mockUpdate).toHaveBeenCalledTimes(1)
      })
      const [projectId, content] = mockUpdate.mock.calls[0]
      expect(projectId).toBe('proj-1')

      // Snapshot + metadata + auto-populated fields survive.
      expect(content.snapshot).toEqual(snapshot)
      expect(content.metadata).toEqual(baseReport.content.metadata)
      expect(content.sections.project_info.title).toBe('Test Project')
      expect(content.sections.project_info.status).toBe('completed')
      expect(content.sections.data.task_count).toBe(15)
      expect(content.sections.generation.models).toEqual(['gpt-5.4'])
      expect(content.sections.generation.show_config).toBe(false)
      expect(content.sections.evaluation.methods).toEqual([
        'llm_judge_falloesung',
      ])

      // Edited fields.
      expect(content.sections.project_info.custom_title).toBe('Custom Title')
      expect(content.sections.evaluation.conclusions).toBe('New conclusions')
      expect(content.sections.data.visible).toBe(false)
      expect(content.sections.project_info.visible).toBe(true)
      expect(content.sections.annotations.show_participants).toBe(false)
      expect(content.sections.data.show_count).toBe(true)
      expect(content.sections.generation.show_models).toBe(true)

      const cfg = content.sections.evaluation.charts_config
      expect(cfg.primary_metric).toBe('llm_judge_falloesung')
      expect(cfg.primary_config_id).toBe('cfg-judge-mini')
      expect(cfg.visible_metrics).toEqual([
        'llm_judge_falloesung',
        'llm_judge_falloesung_grade_points',
        'llm_judge_falloesung_passed',
        'korrektur_falloesung',
      ])
      expect(cfg.visible_configs).toEqual([
        'cfg-judge-sonnet',
        'cfg-judge-mini',
        'cfg-korrektur',
      ])
      expect(cfg.hidden_subjects).toEqual([
        'meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8',
      ])
      expect(cfg.show_distribution).toBe(false)
      expect(cfg.show_humans).toBe(true)

      expect(mockAddToast).toHaveBeenCalledWith(
        'project.report.editor.savedSuccessfully',
        'success'
      )
      // Stays on the editor (preview/iterate) instead of bouncing away.
      expect(mockRouter.push).not.toHaveBeenCalled()
    })

    it('preserves unknown charts_config keys stored by older editors', async () => {
      const user = await renderLoaded(
        reportWith({ available_views: ['data', 'bar'], default_view: 'bar' })
      )

      await user.click(screen.getByText('project.report.editor.saveReport'))

      await waitFor(() => expect(mockUpdate).toHaveBeenCalled())
      const cfg = mockUpdate.mock.calls[0][1].sections.evaluation.charts_config
      expect(cfg.available_views).toEqual(['data', 'bar'])
      expect(cfg.default_view).toBe('bar')
    })

    it('refuses to save with no visible metric (warns instead of blanking)', async () => {
      const user = await renderLoaded()

      await user.click(
        screen.getByText('project.report.editor.evaluationSection.clearAll')
      )
      await user.click(screen.getByText('project.report.editor.saveReport'))

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(
          'reports.editor.noMetricsVisible',
          'warning'
        )
      })
      expect(mockUpdate).not.toHaveBeenCalled()
    })

    it('select all re-enables every metric', async () => {
      const user = await renderLoaded(reportWith({ visible_metrics: ['bleu'] }))

      await user.click(
        screen.getByText('project.report.editor.evaluationSection.selectAll')
      )
      await user.click(screen.getByText('project.report.editor.saveReport'))

      await waitFor(() => expect(mockUpdate).toHaveBeenCalled())
      const cfg = mockUpdate.mock.calls[0][1].sections.evaluation.charts_config
      expect(cfg.visible_metrics).toHaveLength(5)
    })

    it('keeps stored visible_metrics/visible_configs when there is no snapshot', async () => {
      const user = await renderLoaded(
        reportWith(
          { visible_metrics: ['bleu'], visible_configs: ['cfg-bleu'] },
          { content: { snapshot: null } }
        )
      )

      await user.click(screen.getByText('project.report.editor.saveReport'))

      await waitFor(() => expect(mockUpdate).toHaveBeenCalled())
      const content = mockUpdate.mock.calls[0][1]
      expect(content.snapshot).toBeNull()
      const cfg = content.sections.evaluation.charts_config
      expect(cfg.visible_metrics).toEqual(['bleu'])
      expect(cfg.visible_configs).toEqual(['cfg-bleu'])
      expect(mockAddToast).toHaveBeenCalledWith(
        'project.report.editor.savedSuccessfully',
        'success'
      )
    })

    it('handles save errors', async () => {
      mockUpdate.mockRejectedValue(new Error('boom'))
      const user = await renderLoaded()

      await user.click(screen.getByText('project.report.editor.saveReport'))

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(
          'project.report.editor.failedToSave',
          'error'
        )
      })
    })
  })

  describe('refresh', () => {
    it('recomputes the snapshot, keeps edits and shows new metrics', async () => {
      const refreshedSnapshot: ReportSnapshot = {
        ...snapshot,
        generated_at: '2026-09-03T00:00:00Z',
        methods: [
          ...snapshot.methods,
          {
            id: 'rouge',
            name: 'ROUGE',
            category: 'lexical',
            scale: '0-1',
            higher_is_better: true,
          },
        ],
      }
      mockRefresh.mockResolvedValue({
        ...baseReport,
        content: { ...baseReport.content, snapshot: refreshedSnapshot },
      })
      const user = await renderLoaded()

      await user.clear(screen.getByTestId('textarea-dataText'))
      await user.type(screen.getByTestId('textarea-dataText'), 'Kept edit')
      await user.click(
        within(screen.getByTestId('visible-metrics')).getByLabelText('BLEU Score')
      )

      await user.click(screen.getByText('reports.editor.refresh'))

      await waitFor(() => {
        expect(mockRefresh).toHaveBeenCalledWith('proj-1')
      })
      expect(mockAddToast).toHaveBeenCalledWith(
        'reports.editor.refreshed',
        'success'
      )
      // Edit survived, previously unchecked metric stays unchecked, new one visible.
      expect(screen.getByTestId('textarea-dataText')).toHaveValue('Kept edit')
      const box = within(screen.getByTestId('visible-metrics'))
      expect(box.getByLabelText('BLEU Score')).not.toBeChecked()
      expect(box.getByLabelText('ROUGE')).toBeChecked()
    })

    it('shows an error toast when refresh fails', async () => {
      mockRefresh.mockRejectedValue(new Error('boom'))
      const user = await renderLoaded()

      await user.click(screen.getByText('reports.editor.refresh'))

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(
          'reports.editor.refreshFailed',
          'error'
        )
      })
    })
  })

  it('links to the viewer as preview', async () => {
    await renderLoaded()

    const preview = screen.getByRole('link', { name: /reports.editor.preview/ })
    expect(preview).toHaveAttribute('href', '/reports/report-1')
    expect(preview).toHaveAttribute('target', '_blank')
  })

  it('navigates back on cancel and on the back button', async () => {
    const user = await renderLoaded()

    await user.click(screen.getByText('project.report.editor.cancel'))
    expect(mockRouter.push).toHaveBeenCalledWith('/projects/proj-1')

    await user.click(screen.getByText('project.report.editor.backToProject'))
    expect(mockRouter.push).toHaveBeenCalledTimes(2)
  })

  it('updates text fields on change', async () => {
    const user = await renderLoaded()

    const descTextarea = screen.getByTestId('textarea-customDescription')
    await user.clear(descTextarea)
    await user.type(descTextarea, 'New description')

    expect(descTextarea).toHaveValue('New description')
  })
})

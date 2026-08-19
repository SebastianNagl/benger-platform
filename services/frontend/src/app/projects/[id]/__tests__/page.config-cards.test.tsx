/**
 * Behavioral coverage for the Project Detail page's Generation and
 * Evaluation ConfigCards plus the Annotation card auto-save lifecycle.
 *
 * The cards are ALWAYS editable for users with edit permission: any change
 * marks its card dirty and schedules a debounced flush (AUTOSAVE_DEBOUNCE_MS
 * = 2000ms) through the card's save handler. There is no Bearbeiten /
 * Speichern / Abbrechen lifecycle anymore. Tests drive the page's own
 * orchestration handlers:
 *  - handleModelToggle / computeModeBasedPrefill (recommended/minimum/custom)
 *  - saveGenerationCard → handleSaveModels + handleSaveGenDefaults payloads,
 *    triggered by the debounce timer
 *  - generation/evaluation "start" footer CTAs opening the page-level modals
 *  - the korrektur blind toggles + immediate-evaluation buffer →
 *    saveEvaluationCard payloads (config-shaped, NOT extended logic; the
 *    persistence lives in platform, see workspace split rule)
 *  - the annotation card auto-save wiring through LabelConfigEditor's
 *    onConfigChange + imperative ref save
 *  - instructions + conditional-instructions editing
 *
 * ConfigCard / SubSection are reduced to pass-through wrappers that expose
 * the dirty/saving status flags, so the always-collapsed real shells don't
 * hide the inner content we need to interact with. modelConstraints is REAL —
 * the prefill math is the behavior under test.
 *
 * Timer strategy: tests that need the debounced flush switch to fake timers
 * AFTER initial render/hydration (so findBy queries run on real timers),
 * then advance past the debounce inside act. Assertions after the flush are
 * direct (no waitFor) — the async save chain is drained by the act passes.
 *
 * @jest-environment jsdom
 */

import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { useModels } from '@/hooks/useModels'
import { apiClient } from '@/lib/api/client'
import { useUIStore } from '@/stores'
import { useProjectStore } from '@/stores/projectStore'
import '@testing-library/jest-dom'
import { render, screen, waitFor, act, fireEvent, within } from '@testing-library/react'
import { useRouter } from 'next/navigation'

const mockPush = jest.fn()
jest.mock('next/navigation', () => ({
  useRouter: jest.fn(),
  useParams: jest.fn(() => ({ id: 'proj-1' })),
  useSearchParams: jest.fn(() => new URLSearchParams()),
  usePathname: jest.fn(() => '/projects/proj-1'),
}))

jest.mock('@/contexts/AuthContext')
jest.mock('@/contexts/I18nContext')
jest.mock('@/hooks/useModels')
jest.mock('@/stores')
jest.mock('@/stores/projectStore')

const mockAddToast = jest.fn()
jest.mock('@/components/shared/Toast', () => ({
  useToast: () => ({ addToast: mockAddToast }),
}))

jest.mock('@/lib/api/client', () => ({
  apiClient: {
    get: jest.fn(),
    put: jest.fn(),
    post: jest.fn(),
    evaluations: {
      getAvailableEvaluationFields: jest.fn(),
    },
  },
}))

// ConfigCard reduced to a wrapper that surfaces the dirty/saving status the
// page computes for each card (the real card renders a role="status" chip).
jest.mock('@/components/projects/ConfigCard', () => ({
  ConfigCard: ({ title, children, dirty, saving }: any) => (
    <section data-testid={`config-card-${title}`}>
      <h2>{title}</h2>
      {dirty && <span data-testid={`card-dirty-${title}`} />}
      {saving && <span data-testid={`card-saving-${title}`} />}
      {children}
    </section>
  ),
}))
jest.mock('@/components/projects/SubSection', () => ({
  SubSection: ({ title, children, badge }: any) => (
    <div data-testid={`subsection-${title}`}>
      <h3>{title}</h3>
      {badge != null && <span data-testid={`badge-${title}`}>{badge}</span>}
      {children}
    </div>
  ),
}))

jest.mock('@/components/shared/Breadcrumb', () => ({
  Breadcrumb: ({ items }: any) => (
    <nav>{items.map((it: any, i: number) => <span key={i}>{it.label}</span>)}</nav>
  ),
}))
jest.mock('@/components/shared/Button', () => ({
  Button: ({ children, onClick, disabled, href, ...props }: any) =>
    href ? (
      <a href={href} {...props}>{children}</a>
    ) : (
      <button onClick={onClick} disabled={disabled} {...props}>{children}</button>
    ),
}))
jest.mock('@/components/shared/Card', () => ({
  Card: ({ children }: any) => <div>{children}</div>,
}))
jest.mock('@/components/shared/Input', () => ({
  Input: (props: any) => <input {...props} />,
}))
jest.mock('@/components/shared/Textarea', () => ({
  Textarea: (props: any) => <textarea {...props} />,
}))
jest.mock('@/components/shared/Label', () => ({
  Label: ({ children, ...props }: any) => <label {...props}>{children}</label>,
}))
jest.mock('@/components/shared/Tooltip', () => ({
  Tooltip: ({ children }: any) => <>{children}</>,
}))

// LabelConfigEditor: imperative ref save() captured so we can assert the
// annotation card's debounced flush awaits it. onConfigChange (the page's
// markAnnotationDirty) is surfaced as a button; isDirty/hasErrors are
// swappable per test so the flush's guard logic can be pinned.
const mockLabelSave = jest.fn().mockResolvedValue(undefined)
let mockLabelIsDirty: () => boolean = () => true
let mockLabelHasErrors: () => boolean = () => false
jest.mock('@/components/projects/LabelConfigEditor', () => {
  const React = require('react')
  const LabelConfigEditor = React.forwardRef((props: any, ref: any) => {
      React.useImperativeHandle(ref, () => ({
        save: mockLabelSave,
        isDirty: () => mockLabelIsDirty(),
        hasErrors: () => mockLabelHasErrors(),
      }))
      return (
        <div data-testid="label-config-editor">
          <button
            data-testid="label-config-change"
            onClick={() => props.onConfigChange?.()}
          >
            change
          </button>
        </div>
      )
  })
  LabelConfigEditor.displayName = 'LabelConfigEditorMock'
  return { LabelConfigEditor }
})
jest.mock('@/components/projects/PromptStructuresManager', () => ({
  PromptStructuresManager: () => <div data-testid="prompt-structures-manager" />,
}))
jest.mock('@/components/projects/ProjectPermissionsPanel', () => ({
  ProjectPermissionsPanel: () => <div data-testid="permissions-panel" />,
}))
// data-count mirrors the config list length; the add button drives
// onEvaluationsChange like the real builder's add-metric flow does, so tests
// can assert the page's change→debounced-save orchestration (issue #289).
jest.mock('@/components/evaluation/EvaluationBuilder', () => ({
  EvaluationBuilder: (props: any) => (
    <div
      data-testid="evaluation-builder"
      data-defaults-mode={props.defaultsMode}
      data-count={props.evaluations?.length ?? 0}
    >
      <button
        data-testid="eval-builder-add"
        onClick={() =>
          props.onEvaluationsChange([
            ...(props.evaluations || []),
            {
              id: `new-${(props.evaluations || []).length + 1}`,
              metric: 'bleu',
              enabled: true,
            },
          ])
        }
      >
        add
      </button>
    </div>
  ),
}))
jest.mock('@/components/generation/GenerationControlModal', () => ({
  GenerationControlModal: ({ isOpen, models }: any) =>
    isOpen ? (
      <div data-testid="generation-control-modal" data-models={JSON.stringify(models)} />
    ) : null,
}))
jest.mock('@/components/evaluation/EvaluationControlModal', () => ({
  EvaluationControlModal: ({ isOpen, evaluationConfigs }: any) =>
    isOpen ? (
      <div
        data-testid="evaluation-control-modal"
        data-count={evaluationConfigs?.length ?? 0}
      />
    ) : null,
}))
jest.mock('@/components/reports/PublicationToggle', () => ({
  PublicationToggle: () => <div data-testid="publication-toggle" />,
}))
jest.mock('date-fns', () => ({ formatDistanceToNow: () => '2 days ago' }))

const recommendedModel = {
  id: 'claude-x',
  name: 'Claude X',
  provider: 'Anthropic',
  description: 'A reasoning model',
  parameter_constraints: {
    temperature: { supported: true, min: 0, max: 1, default: 0.5 },
    max_tokens: { default: 8000 },
  },
  recommended_parameters: {
    generation: { temperature: 0.3, max_tokens: 4096 },
    evaluation: { temperature: 0.0 },
    default: {},
  },
}

const baseProject = {
  id: 'proj-1',
  title: 'Legal Benchmark',
  description: 'desc',
  created_by: 'user-1',
  created_by_name: 'Alice',
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-02T00:00:00Z',
  task_count: 10,
  annotation_count: 4,
  generation_count: 0,
  evaluation_count: 0,
  progress_percentage: 50,
  label_config: '<View/>',
  instructions: '',
  show_instruction: true,
  show_skip_button: true,
  show_submit_button: true,
  require_comment_on_skip: false,
  require_confirm_before_submit: false,
  maximum_annotations: 1,
  min_annotations_per_task: 1,
  assignment_mode: 'open',
  organizations: [{ id: 'org-1', name: 'TUM' }],
  generation_config: {},
  llm_model_ids: [],
  evaluation_config: {},
  enable_annotation: true,
  enable_generation: true,
  enable_evaluation: true,
  is_public: false,
  is_private: false,
  public_role: null,
}

const superadmin = {
  id: 'user-1',
  username: 'admin',
  email: 'a@b.c',
  role: 'admin',
  is_superadmin: true,
}

function setStore(overrides: Record<string, any> = {}) {
  const store = {
    currentProject: baseProject,
    loading: false,
    fetchProject: jest.fn(),
    updateProject: jest.fn().mockResolvedValue({}),
    deleteProject: jest.fn().mockResolvedValue({}),
    ...overrides,
  }
  ;(useProjectStore as jest.Mock).mockReturnValue(store)
  return store
}

function setModels(models: any[]) {
  ;(useModels as jest.Mock).mockReturnValue({
    models,
    loading: false,
    error: null,
    refetch: jest.fn(),
    hasApiKeys: true,
    apiKeyStatus: {},
  })
}

let ProjectDetailPage: any
beforeAll(async () => {
  ProjectDetailPage = (await import('../page')).default
})

const params = () => Promise.resolve({ id: 'proj-1' })

// Advance past AUTOSAVE_DEBOUNCE_MS (2000ms) so the pending card flush
// fires, then drain the async save chain. Requires jest.useFakeTimers()
// to be active (tests enable it AFTER render/hydration).
const flushAutosave = async () => {
  await act(async () => {
    await jest.advanceTimersByTimeAsync(2100)
  })
  // One more turn so state updates from the tail of the save chain land.
  await act(async () => {})
}

beforeEach(() => {
  jest.clearAllMocks()
  mockLabelSave.mockClear().mockResolvedValue(undefined)
  mockLabelIsDirty = () => true
  mockLabelHasErrors = () => false
  ;(useRouter as jest.Mock).mockReturnValue({ push: mockPush })
  ;(useAuth as jest.Mock).mockReturnValue({ user: superadmin, currentOrganization: null })
  ;(useI18n as jest.Mock).mockReturnValue({
    // A string 2nd arg is a defaultValue fallback (the page passes both
    // forms): collapse those to the bare key so SubSection/CTA titles like
    // t('…runsTitle', 'Multi-Run') resolve to their key. An object 2nd arg
    // is an interpolation map ({count}, {error}, {selected,total}) we DO
    // want to surface for assertions.
    t: (key: string, vars?: any) =>
      vars && typeof vars === 'object' ? `${key}:${JSON.stringify(vars)}` : key,
  })
  ;(useUIStore as jest.Mock).mockReturnValue({ isSidebarHidden: false })
  setModels([])
  setStore()
  ;(apiClient.get as jest.Mock).mockResolvedValue({ task: { id: 't' }, remaining: 5 })
  ;(apiClient.put as jest.Mock).mockResolvedValue({})
  ;(apiClient.evaluations.getAvailableEvaluationFields as jest.Mock).mockResolvedValue({
    model_response_fields: [],
    human_annotation_fields: [],
    reference_fields: [],
    all_fields: [],
  })
  global.fetch = jest.fn().mockResolvedValue({ ok: false, status: 404, json: jest.fn() }) as any
})

afterEach(() => {
  // Drop any pending fake debounce timers before the next test.
  jest.useRealTimers()
})

// ── Generation card: model selection ──────────────────────────────────────
describe('Generation card — model selection', () => {
  it('expands Modellauswahl, lists models with provider badges + selected count', async () => {
    setModels([recommendedModel])
    setStore({ currentProject: { ...baseProject, generation_config: { selected_configuration: { models: ['claude-x'] } } } })
    render(<ProjectDetailPage params={params()} />)
    await screen.findByTestId('config-card-project.generationConfiguration.title')

    // Collapsed badge shows the selected/total count interpolation.
    expect(
      screen.getByText('project.modelSelection.selectedCount:{"selected":1,"total":1}'),
    ).toBeInTheDocument()

    // Expand the model list.
    fireEvent.click(screen.getByText('project.modelSelection.title'))
    expect(screen.getByText('Claude X')).toBeInTheDocument()
    expect(screen.getByText('Anthropic')).toBeInTheDocument()
    // The model is preselected → its checkbox is checked.
    expect(screen.getByLabelText('Claude X')).toBeChecked()
  })

  it('toggling a model marks the card dirty, prefills recommended params, and auto-saves after the debounce', async () => {
    setModels([recommendedModel])
    const store = setStore()
    render(<ProjectDetailPage params={params()} />)
    await screen.findByTestId('config-card-project.generationConfiguration.title')

    fireEvent.click(screen.getByText('project.modelSelection.title'))
    const checkbox = screen.getByLabelText('Claude X')
    expect(checkbox).not.toBeChecked()

    jest.useFakeTimers()
    await act(async () => {
      fireEvent.click(checkbox)
    })
    // The change marks the card dirty (auto-save pending) — no manual Save.
    expect(
      screen.getByTestId('card-dirty-project.generationConfiguration.title'),
    ).toBeInTheDocument()
    expect(checkbox).toBeChecked()

    // Recommended mode (default) pre-filled the per-model temperature input
    // from recommended_parameters.generation.temperature (0.3).
    expect(screen.getByDisplayValue('0.3')).toBeInTheDocument()
    // And the recommended max_tokens (4096).
    expect(screen.getByDisplayValue('4096')).toBeInTheDocument()

    // Nothing persists before the debounce elapses.
    expect(store.updateProject).not.toHaveBeenCalled()

    // The debounced flush persists the selection + configs via updateProject.
    await flushAutosave()
    expect(store.updateProject).toHaveBeenCalledWith(
      'proj-1',
      expect.objectContaining({
        generation_config: expect.objectContaining({
          selected_configuration: expect.objectContaining({
            models: ['claude-x'],
            model_configs: expect.objectContaining({
              'claude-x': expect.objectContaining({ temperature: 0.3, max_tokens: 4096 }),
            }),
          }),
        }),
      }),
    )
    expect(mockAddToast).toHaveBeenCalledWith('toasts.project.modelsSaved', 'success')
    // Successful flush clears the dirty flag.
    expect(
      screen.queryByTestId('card-dirty-project.generationConfiguration.title'),
    ).not.toBeInTheDocument()
  })

  it('minimum mode prefills the constraint minimum temperature on toggle', async () => {
    setModels([recommendedModel])
    const store = setStore()
    render(<ProjectDetailPage params={params()} />)
    await screen.findByTestId('config-card-project.generationConfiguration.title')

    jest.useFakeTimers()
    // Switch the GENERATION defaults mode to "minimum" (scope the radio to
    // the gen-defaults subsection; the eval card has a same-valued radio).
    const genDefaults = screen.getByTestId('subsection-project.generationDefaults.title')
    const minRadio = within(genDefaults).getByDisplayValue('minimum')
    await act(async () => {
      fireEvent.click(minRadio)
    })

    fireEvent.click(screen.getByText('project.modelSelection.title'))
    await act(async () => {
      fireEvent.click(screen.getByLabelText('Claude X'))
    })

    // Flush the debounce and assert the persisted per-model temperature is
    // the constraint minimum (0), NOT the recommended 0.3 — proves minimum
    // mode took effect.
    await flushAutosave()
    expect(store.updateProject).toHaveBeenCalledWith(
      'proj-1',
      expect.objectContaining({
        generation_config: expect.objectContaining({
          selected_configuration: expect.objectContaining({
            model_configs: expect.objectContaining({
              'claude-x': expect.objectContaining({ temperature: 0 }),
            }),
          }),
        }),
      }),
    )
  })

  it('deselecting a model removes it and the auto-save persists the empty list', async () => {
    setModels([recommendedModel])
    const store = setStore({
      currentProject: { ...baseProject, generation_config: { selected_configuration: { models: ['claude-x'] } } },
    })
    render(<ProjectDetailPage params={params()} />)
    await screen.findByTestId('config-card-project.generationConfiguration.title')
    fireEvent.click(screen.getByText('project.modelSelection.title'))

    const checkbox = screen.getByLabelText('Claude X')
    expect(checkbox).toBeChecked()
    jest.useFakeTimers()
    await act(async () => {
      fireEvent.click(checkbox)
    })
    expect(checkbox).not.toBeChecked()

    await flushAutosave()
    expect(store.updateProject).toHaveBeenCalledWith(
      'proj-1',
      expect.objectContaining({
        generation_config: expect.objectContaining({
          selected_configuration: expect.objectContaining({ models: [] }),
        }),
      }),
    )
  })

  it('shows the models loading state', async () => {
    ;(useModels as jest.Mock).mockReturnValue({
      models: null,
      loading: true,
      error: null,
      refetch: jest.fn(),
      hasApiKeys: false,
      apiKeyStatus: {},
    })
    setStore()
    render(<ProjectDetailPage params={params()} />)
    await screen.findByTestId('config-card-project.generationConfiguration.title')
    fireEvent.click(screen.getByText('project.modelSelection.title'))
    expect(screen.getByText('project.modelSelection.loadingModels')).toBeInTheDocument()
  })

  it('shows the NO_API_KEYS error with a configure-keys CTA that routes to /profile', async () => {
    ;(useModels as jest.Mock).mockReturnValue({
      models: null,
      loading: false,
      error: { type: 'NO_API_KEYS', message: 'no keys' },
      refetch: jest.fn(),
      hasApiKeys: false,
      apiKeyStatus: {},
    })
    setStore()
    render(<ProjectDetailPage params={params()} />)
    await screen.findByTestId('config-card-project.generationConfiguration.title')
    fireEvent.click(screen.getByText('project.modelSelection.title'))
    expect(screen.getByText('project.modelSelection.noApiKeys')).toBeInTheDocument()
    fireEvent.click(screen.getByText('project.modelSelection.configureApiKeys'))
    expect(mockPush).toHaveBeenCalledWith('/profile')
  })
})

// ── Generation card: defaults + start CTA ─────────────────────────────────
describe('Generation card — defaults and start CTA', () => {
  it('custom mode enables the temperature input and auto-saves the typed default', async () => {
    setModels([recommendedModel])
    const store = setStore()
    render(<ProjectDetailPage params={params()} />)
    await screen.findByTestId('config-card-project.generationConfiguration.title')

    // Default mode is "recommended" → temperature input disabled.
    const genDefaults = screen.getByTestId('subsection-project.generationDefaults.title')
    const tempInput = within(genDefaults).getByDisplayValue('0')
    expect(tempInput).toBeDisabled()

    jest.useFakeTimers()
    // Switch to custom (scope the radio to the gen-defaults subsection),
    // then type a value. Both changes mark the card dirty.
    await act(async () => {
      fireEvent.click(within(genDefaults).getByDisplayValue('custom'))
    })
    const tempInputNow = within(genDefaults).getByDisplayValue('0')
    expect(tempInputNow).not.toBeDisabled()
    await act(async () => {
      fireEvent.change(tempInputNow, { target: { value: '0.9' } })
    })
    expect(
      screen.getByTestId('card-dirty-project.generationConfiguration.title'),
    ).toBeInTheDocument()

    await flushAutosave()
    expect(store.updateProject).toHaveBeenCalledWith(
      'proj-1',
      expect.objectContaining({
        generation_config: expect.objectContaining({
          defaults_mode: 'custom',
          selected_configuration: expect.objectContaining({
            parameters: expect.objectContaining({ temperature: 0.9 }),
          }),
        }),
      }),
    )
    expect(mockAddToast).toHaveBeenCalledWith('toasts.project.generationDefaultsSaved', 'success')
  })

  it('editing runs-per-task marks the card dirty and persists runs_per_task', async () => {
    const store = setStore()
    render(<ProjectDetailPage params={params()} />)
    await screen.findByTestId('config-card-project.generationConfiguration.title')

    jest.useFakeTimers()
    const runsSub = screen.getByTestId('subsection-project.generationDefaults.runsTitle')
    const runsInput = within(runsSub).getByDisplayValue('1')
    await act(async () => {
      fireEvent.change(runsInput, { target: { value: '5' } })
    })
    expect(
      screen.getByTestId('card-dirty-project.generationConfiguration.title'),
    ).toBeInTheDocument()

    await flushAutosave()
    expect(store.updateProject).toHaveBeenCalledWith(
      'proj-1',
      expect.objectContaining({
        generation_config: expect.objectContaining({ runs_per_task: 5 }),
      }),
    )
  })

  it('the "Generierung starten" footer CTA opens the generation control modal', async () => {
    setStore({
      currentProject: { ...baseProject, generation_config: { selected_configuration: { models: ['claude-x'] } } },
    })
    render(<ProjectDetailPage params={params()} />)
    await screen.findByTestId('config-card-project.generationConfiguration.title')

    expect(screen.queryByTestId('generation-control-modal')).not.toBeInTheDocument()
    fireEvent.click(screen.getByText('project.generation.runCta'))
    const modal = await screen.findByTestId('generation-control-modal')
    // Modal receives the project's configured models.
    expect(modal).toHaveAttribute('data-models', JSON.stringify(['claude-x']))
  })
})

// ── Evaluation card ───────────────────────────────────────────────────────
describe('Evaluation card', () => {
  it('hydrates the korrektur blind toggles from the saved metric_parameters', async () => {
    // evaluation-config GET returns a korrektur_falloesung config with one
    // explicit false → that toggle should render unchecked, others default true.
    ;(apiClient.get as jest.Mock).mockImplementation((url: string) => {
      if (url.includes('/evaluation-config')) {
        return Promise.resolve({
          evaluation_configs: [
            {
              id: 'e1',
              metric: 'korrektur_falloesung',
              enabled: true,
              metric_parameters: { blind_to_llm_judge: false },
            },
          ],
        })
      }
      return Promise.resolve({ task: { id: 't' }, remaining: 5 })
    })
    setStore()
    render(<ProjectDetailPage params={params()} />)
    await screen.findByTestId('config-card-project.evaluation.title')

    // The blind sub-toggles only render when a korrektur_falloesung config
    // exists — wait for hydration.
    const blindLlm = await screen.findByText(
      'project.evaluationSettings.korrekturBlindToLlm',
    )
    const evalSettings = screen.getByTestId(
      'subsection-project.evaluationSettings.title',
    )
    const checkboxes = within(evalSettings).getAllByRole('checkbox')
    // Order: immediate-eval, blindToPeers(true), blindToLlm(false), blindToNonJudge(true), keepBlind(false)
    expect(blindLlm).toBeInTheDocument()
    expect(checkboxes[2]).not.toBeChecked() // blind_to_llm_judge: false
    expect(checkboxes[1]).toBeChecked() // blind_to_peer_correctors defaults true
    // Always-editable: none of the toggles is disabled (no edit mode).
    for (const cb of checkboxes) {
      expect(cb).not.toBeDisabled()
    }
  })

  it('flipping immediate-eval auto-saves immediate-eval + eval defaults + blind params', async () => {
    ;(apiClient.get as jest.Mock).mockImplementation((url: string) => {
      if (url.includes('/evaluation-config')) {
        return Promise.resolve({
          evaluation_configs: [
            { id: 'e1', metric: 'korrektur_falloesung', enabled: true, metric_parameters: {} },
          ],
        })
      }
      return Promise.resolve({ task: { id: 't' }, remaining: 5 })
    })
    const store = setStore()
    render(<ProjectDetailPage params={params()} />)
    await screen.findByTestId('config-card-project.evaluation.title')
    await screen.findByText('project.evaluationSettings.korrekturBlindToLlm')

    // Flip immediate-eval on — no edit mode, the checkbox is live.
    jest.useFakeTimers()
    const evalSettings = screen.getByTestId('subsection-project.evaluationSettings.title')
    const checkboxes = within(evalSettings).getAllByRole('checkbox')
    await act(async () => {
      fireEvent.click(checkboxes[0]) // immediate_evaluation_enabled
    })
    // The change marks the card dirty (auto-save pending).
    expect(
      screen.getByTestId('card-dirty-project.evaluation.title'),
    ).toBeInTheDocument()

    await flushAutosave()
    // immediate-eval buffer PATCH
    expect(store.updateProject).toHaveBeenCalledWith(
      'proj-1',
      expect.objectContaining({ immediate_evaluation_enabled: true }),
    )
    // eval defaults PATCH (separate call)
    expect(store.updateProject).toHaveBeenCalledWith(
      'proj-1',
      expect.objectContaining({
        evaluation_config: expect.objectContaining({ defaults_mode: 'recommended' }),
      }),
    )
    // blind params written back to the korrektur config via PUT
    expect(apiClient.put).toHaveBeenCalledWith(
      expect.stringContaining('/evaluation-config'),
      expect.objectContaining({
        evaluation_configs: expect.arrayContaining([
          expect.objectContaining({
            metric: 'korrektur_falloesung',
            metric_parameters: expect.objectContaining({
              blind_to_peer_correctors: true,
              blind_to_llm_judge: true,
            }),
          }),
        ]),
      }),
    )
  })

  it('hides blind toggles when no korrektur_falloesung config is present', async () => {
    ;(apiClient.get as jest.Mock).mockImplementation((url: string) => {
      if (url.includes('/evaluation-config')) {
        return Promise.resolve({ evaluation_configs: [{ id: 'e2', metric: 'bleu', enabled: true }] })
      }
      return Promise.resolve({ task: { id: 't' }, remaining: 5 })
    })
    setStore()
    render(<ProjectDetailPage params={params()} />)
    await screen.findByTestId('config-card-project.evaluation.title')
    await waitFor(() => {
      expect(screen.getByTestId('evaluation-builder')).toBeInTheDocument()
    })
    expect(
      screen.queryByText('project.evaluationSettings.korrekturBlindToLlm'),
    ).not.toBeInTheDocument()
  })

  it('the "Evaluierung starten" CTA opens the eval modal with only enabled configs', async () => {
    ;(apiClient.get as jest.Mock).mockImplementation((url: string) => {
      if (url.includes('/evaluation-config')) {
        return Promise.resolve({
          evaluation_configs: [
            { id: 'a', metric: 'bleu', enabled: true, prediction_fields: [], reference_fields: [] },
            { id: 'b', metric: 'rouge', enabled: false, prediction_fields: [], reference_fields: [] },
          ],
        })
      }
      return Promise.resolve({ task: { id: 't' }, remaining: 5 })
    })
    setStore()
    render(<ProjectDetailPage params={params()} />)
    await screen.findByTestId('config-card-project.evaluation.title')

    const cta = await screen.findByText('project.evaluation.runCta')
    fireEvent.click(cta)
    const modal = await screen.findByTestId('evaluation-control-modal')
    // Only the enabled config flows into the modal.
    expect(modal).toHaveAttribute('data-count', '1')
  })

  it('does not render the eval start CTA when no config is enabled', async () => {
    ;(apiClient.get as jest.Mock).mockImplementation((url: string) => {
      if (url.includes('/evaluation-config')) {
        return Promise.resolve({
          evaluation_configs: [{ id: 'b', metric: 'rouge', enabled: false }],
        })
      }
      return Promise.resolve({ task: { id: 't' }, remaining: 5 })
    })
    setStore()
    render(<ProjectDetailPage params={params()} />)
    await screen.findByTestId('config-card-project.evaluation.title')
    await waitFor(() => {
      expect(screen.getByTestId('evaluation-builder')).toBeInTheDocument()
    })
    expect(screen.queryByText('project.evaluation.runCta')).not.toBeInTheDocument()
  })

  it('passes the eval defaults mode down to the EvaluationBuilder', async () => {
    setStore({
      currentProject: { ...baseProject, evaluation_config: { defaults_mode: 'minimum' } },
    })
    render(<ProjectDetailPage params={params()} />)
    await screen.findByTestId('config-card-project.evaluation.title')
    await waitFor(() => {
      expect(screen.getByTestId('evaluation-builder')).toHaveAttribute(
        'data-defaults-mode',
        'minimum',
      )
    })
  })
})

// ── Issue #289: lost-update regressions (change→debounced-save orchestration)
describe('Evaluation card — save orchestration (issue #289)', () => {
  const bleuConfig = { id: 'e2', metric: 'bleu', enabled: true }

  const mockEvalConfigGet = (configs: any[]) => {
    ;(apiClient.get as jest.Mock).mockImplementation((url: string) => {
      if (url.includes('/evaluation-config')) {
        return Promise.resolve({ evaluation_configs: configs })
      }
      return Promise.resolve({ task: { id: 't' }, remaining: 5 })
    })
  }

  it('a builder change stays local until the debounce elapses, then flushes one PUT', async () => {
    mockEvalConfigGet([bleuConfig])
    setStore()
    render(<ProjectDetailPage params={params()} />)
    await screen.findByTestId('config-card-project.evaluation.title')
    await waitFor(() => {
      expect(screen.getByTestId('evaluation-builder')).toHaveAttribute('data-count', '1')
    })

    // No fire-and-forget autosave: within the debounce window the builder
    // change stays local…
    jest.useFakeTimers()
    await act(async () => {
      fireEvent.click(screen.getByTestId('eval-builder-add'))
    })
    expect(apiClient.put).not.toHaveBeenCalled()
    expect(screen.getByTestId('evaluation-builder')).toHaveAttribute('data-count', '2')
    // …and marks the card dirty so the pending flush is visible.
    expect(screen.getByTestId('card-dirty-project.evaluation.title')).toBeInTheDocument()

    // The debounce elapses → the flush persists the new list automatically.
    await flushAutosave()
    expect(apiClient.put).toHaveBeenCalledTimes(1)
    expect(apiClient.put).toHaveBeenCalledWith(
      '/evaluations/projects/proj-1/evaluation-config',
      {
        evaluation_configs: [
          bleuConfig,
          { id: 'new-2', metric: 'bleu', enabled: true },
        ],
      },
    )
  })

  it('the debounced flush sends one minimal PUT sequenced after both PATCH legs', async () => {
    mockEvalConfigGet([bleuConfig])
    const store = setStore()
    const resolvers: Array<(v: any) => void> = []
    ;(store.updateProject as jest.Mock).mockImplementation(
      () => new Promise((res) => resolvers.push(res)),
    )
    render(<ProjectDetailPage params={params()} />)
    await screen.findByTestId('config-card-project.evaluation.title')
    await waitFor(() => {
      expect(screen.getByTestId('evaluation-builder')).toHaveAttribute('data-count', '1')
    })

    jest.useFakeTimers()
    await act(async () => {
      fireEvent.click(screen.getByTestId('eval-builder-add'))
    })
    // Nothing fires before the debounce elapses.
    expect(store.updateProject).not.toHaveBeenCalled()

    await act(async () => {
      await jest.advanceTimersByTimeAsync(2100)
    })
    // Settings PATCH in flight — configs PUT must wait. The card reports the
    // in-flight save.
    expect(store.updateProject).toHaveBeenCalledTimes(1)
    expect(apiClient.put).not.toHaveBeenCalled()
    expect(screen.getByTestId('card-saving-project.evaluation.title')).toBeInTheDocument()
    await act(async () => {
      resolvers[0]({})
    })

    // Eval-defaults PATCH in flight — configs PUT still waits.
    expect(store.updateProject).toHaveBeenCalledTimes(2)
    expect(apiClient.put).not.toHaveBeenCalled()
    await act(async () => {
      resolvers[1]({})
    })
    await act(async () => {})

    // Exactly one PUT, minimal body (no read-modify-write spread of the
    // stored doc), fired without any korrektur_falloesung config present.
    expect(apiClient.put).toHaveBeenCalledTimes(1)
    expect(apiClient.put).toHaveBeenCalledWith(
      '/evaluations/projects/proj-1/evaluation-config',
      {
        evaluation_configs: [
          bleuConfig,
          { id: 'new-2', metric: 'bleu', enabled: true },
        ],
      },
    )
    // Successful flush clears the dirty + saving flags.
    expect(
      screen.queryByTestId('card-dirty-project.evaluation.title'),
    ).not.toBeInTheDocument()
    expect(
      screen.queryByTestId('card-saving-project.evaluation.title'),
    ).not.toBeInTheDocument()
  })

  it('a failed configs PUT toasts and keeps the card dirty', async () => {
    mockEvalConfigGet([bleuConfig])
    setStore()
    ;(apiClient.put as jest.Mock).mockRejectedValue(new Error('boom'))
    render(<ProjectDetailPage params={params()} />)
    await screen.findByTestId('config-card-project.evaluation.title')
    await waitFor(() => {
      expect(screen.getByTestId('evaluation-builder')).toHaveAttribute('data-count', '1')
    })

    jest.useFakeTimers()
    await act(async () => {
      fireEvent.click(screen.getByTestId('eval-builder-add'))
    })
    await flushAutosave()

    expect(mockAddToast).toHaveBeenCalledWith(
      'toasts.project.evaluationConfigsSaveFailed:{"error":"boom"}',
      'error',
    )
    // The card must not pretend the save succeeded — the dirty flag stays.
    expect(screen.getByTestId('card-dirty-project.evaluation.title')).toBeInTheDocument()
    expect(
      screen.queryByTestId('card-saving-project.evaluation.title'),
    ).not.toBeInTheDocument()
  })

  it('a failed eval-defaults PATCH aborts the sequence: no PUT, card stays dirty', async () => {
    mockEvalConfigGet([bleuConfig])
    const store = setStore()
    ;(store.updateProject as jest.Mock)
      .mockResolvedValueOnce({})
      .mockRejectedValueOnce(new Error('defaults down'))
    render(<ProjectDetailPage params={params()} />)
    await screen.findByTestId('config-card-project.evaluation.title')
    await waitFor(() => {
      expect(screen.getByTestId('evaluation-builder')).toHaveAttribute('data-count', '1')
    })

    jest.useFakeTimers()
    await act(async () => {
      fireEvent.click(screen.getByTestId('eval-builder-add'))
    })
    await flushAutosave()

    expect(mockAddToast).toHaveBeenCalledWith(
      'toasts.project.evaluationDefaultsSaveFailed:{"error":"defaults down"}',
      'error',
    )
    expect(apiClient.put).not.toHaveBeenCalled()
    expect(screen.getByTestId('card-dirty-project.evaluation.title')).toBeInTheDocument()
  })
})

describe('Generation card — save orchestration (issue #289)', () => {
  it('model save sends a minimal patch and the defaults PATCH waits for it', async () => {
    setModels([recommendedModel])
    const store = setStore({
      currentProject: {
        ...baseProject,
        generation_config: {
          selected_configuration: { models: [], parameters: { temperature: 0.7 } },
        },
      },
    })
    const resolvers: Array<(v: any) => void> = []
    ;(store.updateProject as jest.Mock).mockImplementation(
      () => new Promise((res) => resolvers.push(res)),
    )
    render(<ProjectDetailPage params={params()} />)
    await screen.findByTestId('config-card-project.generationConfiguration.title')

    fireEvent.click(screen.getByText('project.modelSelection.title'))
    jest.useFakeTimers()
    await act(async () => {
      fireEvent.click(screen.getByLabelText('Claude X'))
    })
    expect(store.updateProject).not.toHaveBeenCalled()

    await act(async () => {
      await jest.advanceTimersByTimeAsync(2100)
    })
    // Models PATCH in flight — the defaults PATCH must not start yet.
    expect(store.updateProject).toHaveBeenCalledTimes(1)
    const modelsPayload = (store.updateProject as jest.Mock).mock.calls[0][1]
    // Minimal patch: no re-sent stale `parameters` snapshot; the server-side
    // deep-merge preserves it.
    expect(modelsPayload.generation_config.selected_configuration).toEqual({
      models: ['claude-x'],
      model_configs: expect.any(Object),
    })
    await act(async () => {
      resolvers[0]({})
    })

    expect(store.updateProject).toHaveBeenCalledTimes(2)
    const defaultsPayload = (store.updateProject as jest.Mock).mock.calls[1][1]
    expect(
      defaultsPayload.generation_config.selected_configuration.parameters,
    ).toBeDefined()
    await act(async () => {
      resolvers[1]({})
    })
    await act(async () => {})

    // Successful flush clears the dirty flag.
    expect(
      screen.queryByTestId('card-dirty-project.generationConfiguration.title'),
    ).not.toBeInTheDocument()
  })

  it('a failed models PATCH keeps the card dirty and skips the defaults PATCH', async () => {
    setModels([recommendedModel])
    const store = setStore()
    ;(store.updateProject as jest.Mock).mockRejectedValueOnce(new Error('models down'))
    render(<ProjectDetailPage params={params()} />)
    await screen.findByTestId('config-card-project.generationConfiguration.title')

    fireEvent.click(screen.getByText('project.modelSelection.title'))
    jest.useFakeTimers()
    await act(async () => {
      fireEvent.click(screen.getByLabelText('Claude X'))
    })
    await flushAutosave()

    expect(mockAddToast).toHaveBeenCalledWith(
      'toasts.project.modelsSaveFailed:{"error":"models down"}',
      'error',
    )
    expect(store.updateProject).toHaveBeenCalledTimes(1)
    expect(
      screen.getByTestId('card-dirty-project.generationConfiguration.title'),
    ).toBeInTheDocument()
  })
})

// ── Annotation card auto-save + instructions ──────────────────────────────
describe('Annotation card — auto-save & instructions', () => {
  it('a label-config change marks the card dirty; the flush awaits LabelConfigEditor.save()', async () => {
    const store = setStore()
    render(<ProjectDetailPage params={params()} />)
    await screen.findByTestId('config-card-project.annotationConfiguration.title')

    // The editor mounts as soon as the label config section is expanded —
    // no edit mode needed.
    fireEvent.click(screen.getByText('project.labelConfiguration.title'))
    expect(screen.getByTestId('label-config-editor')).toBeInTheDocument()

    jest.useFakeTimers()
    // The editor's onConfigChange (markAnnotationDirty) fires on each edit.
    await act(async () => {
      fireEvent.click(screen.getByTestId('label-config-change'))
    })
    expect(
      screen.getByTestId('card-dirty-project.annotationConfiguration.title'),
    ).toBeInTheDocument()

    await flushAutosave()
    // The imperative label save() fired (isDirty → true, hasErrors → false)…
    expect(mockLabelSave).toHaveBeenCalled()
    // …while the untouched instructions/settings legs produced no PATCH.
    expect(store.updateProject).not.toHaveBeenCalled()
    // Successful flush clears the dirty flag.
    expect(
      screen.queryByTestId('card-dirty-project.annotationConfiguration.title'),
    ).not.toBeInTheDocument()
  })

  it('a label config with validation errors is skipped and keeps the card dirty', async () => {
    mockLabelHasErrors = () => true
    setStore()
    render(<ProjectDetailPage params={params()} />)
    await screen.findByTestId('config-card-project.annotationConfiguration.title')

    fireEvent.click(screen.getByText('project.labelConfiguration.title'))
    jest.useFakeTimers()
    await act(async () => {
      fireEvent.click(screen.getByTestId('label-config-change'))
    })
    await flushAutosave()

    // Blocked: no imperative save, and the card stays dirty until it parses.
    expect(mockLabelSave).not.toHaveBeenCalled()
    expect(
      screen.getByTestId('card-dirty-project.annotationConfiguration.title'),
    ).toBeInTheDocument()
  })

  it('saves edited instructions through updateProject when the card flushes', async () => {
    const store = setStore({ currentProject: { ...baseProject, instructions: 'Old text' } })
    render(<ProjectDetailPage params={params()} />)
    await screen.findByTestId('config-card-project.annotationConfiguration.title')

    // Expand instructions — the textarea is always editable for editors.
    fireEvent.click(screen.getByText('project.annotationInstructions.title'))
    const textarea = await screen.findByDisplayValue('Old text')

    jest.useFakeTimers()
    await act(async () => {
      fireEvent.change(textarea, { target: { value: 'New instructions' } })
    })
    expect(
      screen.getByTestId('card-dirty-project.annotationConfiguration.title'),
    ).toBeInTheDocument()

    await flushAutosave()
    expect(store.updateProject).toHaveBeenCalledWith('proj-1', {
      instructions: 'New instructions',
    })
    // The label config section was never expanded → no imperative label save.
    expect(mockLabelSave).not.toHaveBeenCalled()
  })

  it('saves conditional instructions and rejects weights that do not sum to 100', async () => {
    const store = setStore()
    render(<ProjectDetailPage params={params()} />)
    await screen.findByTestId('config-card-project.annotationConfiguration.title')

    fireEvent.click(screen.getByText('project.annotationInstructions.title'))

    // Open the conditional-instructions editor and add a single 50% variant.
    // These controls pass a { defaultValue } 2nd arg to t(), so match by the
    // key prefix (the i18n mock appends the serialized vars).
    fireEvent.click(screen.getByText(/^project\.conditionalInstructions\.add:/))
    fireEvent.click(screen.getByText(/^project\.conditionalInstructions\.addVariant/))

    // One variant @ weight 50 ≠ 100 → save shows the weight error, no PATCH.
    await act(async () => {
      fireEvent.click(screen.getByText(/^project\.conditionalInstructions\.save/))
    })
    await waitFor(() => {
      expect(mockAddToast).toHaveBeenCalledWith(
        expect.stringContaining('project.conditionalInstructions.weightError'),
        'error',
      )
    })
    expect(store.updateProject).not.toHaveBeenCalledWith(
      'proj-1',
      expect.objectContaining({ conditional_instructions: expect.anything() }),
    )
  })
})

// ── Read-only (non-editor) gating ─────────────────────────────────────────
describe('Read-only gating for non-editors', () => {
  it('renders creator-only read-only notices when the user cannot edit', async () => {
    // Different user, not superadmin, not creator, non-org project → no edit.
    ;(useAuth as jest.Mock).mockReturnValue({
      user: { id: 'other', is_superadmin: false, role: 'ANNOTATOR' },
      currentOrganization: null,
    })
    setStore()
    render(<ProjectDetailPage params={params()} />)
    await screen.findByTestId('config-card-project.annotationConfiguration.title')

    // The annotation card shows the creatorOnly read-only message instead of
    // the editable instructions UI.
    const notices = screen.getAllByText(/project\.permissions\.creatorOnly/)
    expect(notices.length).toBeGreaterThan(0)
    // The model-selection edit UI is replaced by a read-only notice too, so
    // no model checkboxes exist for a non-editor.
    expect(screen.queryByText('project.modelSelection.title')).not.toBeInTheDocument()
  })
})

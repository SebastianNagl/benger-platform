/**
 * ProjectCreationWizard — extended-edition KI-Generator step wiring.
 *
 * The feature checkbox row comes from the ProjectWizardSyntheticEntry slot
 * (rendered by StepProjectInfo) and toggles `features.synthetic`; when
 * checked, a 'synthetic' step appears right after projectInfo and renders the
 * ProjectWizardSyntheticStep slot. Community builds register neither slot, so
 * the wizard is unchanged there (covered by the main wizard suites, which run
 * with an empty registry).
 *
 * @jest-environment jsdom
 */

import '@testing-library/jest-dom'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ProjectCreationWizard } from '../ProjectCreationWizard'

const mockPush = jest.fn()
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush, replace: jest.fn(), back: jest.fn() }),
}))

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string) => key,
  }),
}))

const mockRunNestedImportJob = jest.fn()
const mockProjectUpdate = jest.fn()
jest.mock('@/lib/api/projects', () => ({
  projectsAPI: {
    importData: jest.fn(),
    update: (...a: any[]) => mockProjectUpdate(...a),
    updateVisibility: jest.fn(),
    runNestedImportJob: (...a: any[]) => mockRunNestedImportJob(...a),
  },
}))

jest.mock('@/lib/api/client', () => ({
  apiClient: { put: jest.fn() },
}))

const mockCreateProject = jest.fn()
jest.mock('@/stores/projectStore', () => ({
  useProjectStore: () => ({
    createProject: mockCreateProject,
    fetchProject: jest.fn(),
    loading: false,
  }),
}))

jest.mock('@/hooks/useModels', () => ({
  useModels: () => ({
    models: [],
    loading: false,
    error: null,
    refetch: jest.fn(),
    hasApiKeys: true,
    apiKeyStatus: null,
  }),
  default: () => ({}),
}))

jest.mock('@/components/shared/Toast', () => ({
  useToast: () => ({
    addToast: jest.fn(),
    showToast: jest.fn(),
    removeToast: jest.fn(),
  }),
  ToastProvider: ({ children }: { children: React.ReactNode }) => children,
}))

// Both wizard slots registered (extended edition). The entry stub mirrors the
// real row's contract: a checkbox wired to onToggle.
jest.mock('@/lib/extensions/slots', () => ({
  useSlot: (name: string) => {
    if (name === 'ProjectWizardSyntheticEntry') {
      return ({ checked, onToggle }: any) => (
        <div data-testid="wizard-feature-synthetic">
          <input
            type="checkbox"
            data-testid="wizard-synthetic-checkbox"
            checked={!!checked}
            onChange={() => onToggle?.()}
          />
        </div>
      )
    }
    if (name === 'ProjectWizardSyntheticStep') {
      // Mirrors the real step's contract: it receives the wizard state and
      // feeds generated rows back through onChange (pastedData/dataColumns).
      return ({ data, onChange }: any) => (
        <div data-testid="synthetic-step-stub">
          <span data-testid="synthetic-step-wired">
            {String(!!data && typeof onChange === 'function')}
          </span>
          <button
            data-testid="synthetic-step-inject"
            onClick={() =>
              onChange({
                pastedData: JSON.stringify([
                  { title: 'Fall A', sachverhalt: 's', musterloesung: 'm' },
                ]),
                dataColumns: ['title', 'sachverhalt', 'musterloesung'],
              })
            }
          >
            inject
          </button>
        </div>
      )
    }
    return null
  },
  getSlot: () => null,
  hasSlot: () => false,
  registerSlot: jest.fn(),
}))

const currentStepId = () =>
  screen
    .getByTestId('project-create-step-indicator')
    .getAttribute('data-current-step-id')

describe('ProjectCreationWizard — synthetic step (extended)', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('adds the synthetic step right after projectInfo when the row is checked', async () => {
    const user = userEvent.setup()
    render(<ProjectCreationWizard />)

    await user.type(
      screen.getByTestId('project-create-name-input'),
      'Synthetic Demo'
    )
    await user.click(screen.getByTestId('wizard-synthetic-checkbox'))
    await user.click(screen.getByTestId('project-create-next-button'))

    await waitFor(() => {
      expect(currentStepId()).toBe('synthetic')
    })
    expect(screen.getByTestId('synthetic-step-stub')).toBeInTheDocument()
    // The step gets the wizard state + updater like every other step.
    expect(screen.getByTestId('synthetic-step-wired')).toHaveTextContent(
      'true'
    )
  })

  it('imports generated rows on finish even without the dataImport feature', async () => {
    mockCreateProject.mockResolvedValue({ id: 'proj-1' })
    mockProjectUpdate.mockResolvedValue({})
    mockRunNestedImportJob.mockResolvedValue({})

    const user = userEvent.setup()
    render(<ProjectCreationWizard />)

    await user.type(
      screen.getByTestId('project-create-name-input'),
      'Generated Project'
    )
    await user.click(screen.getByTestId('wizard-synthetic-checkbox'))
    await user.click(screen.getByTestId('project-create-next-button'))
    await waitFor(() => {
      expect(currentStepId()).toBe('synthetic')
    })

    // The step feeds generated rows into the wizard state...
    await user.click(screen.getByTestId('synthetic-step-inject'))
    // ...then the user walks to the end and finishes.
    await user.click(screen.getByTestId('project-create-next-button'))
    await waitFor(() => {
      expect(currentStepId()).toBe('settings')
    })
    await user.click(screen.getByTestId('project-create-submit-button'))

    await waitFor(() => {
      expect(mockRunNestedImportJob).toHaveBeenCalledTimes(1)
    })
    const [projectId, file] = mockRunNestedImportJob.mock.calls[0]
    expect(projectId).toBe('proj-1')
    const uploaded = JSON.parse(await (file as File).text())
    expect(uploaded.data).toEqual([
      { title: 'Fall A', sachverhalt: 's', musterloesung: 'm' },
    ])
  })

  it('skips the synthetic step when the row is left unchecked', async () => {
    const user = userEvent.setup()
    render(<ProjectCreationWizard />)

    await user.type(
      screen.getByTestId('project-create-name-input'),
      'Plain Project'
    )
    await user.click(screen.getByTestId('project-create-next-button'))

    await waitFor(() => {
      expect(currentStepId()).toBe('settings')
    })
    expect(
      screen.queryByTestId('synthetic-step-stub')
    ).not.toBeInTheDocument()
  })

  it('unchecking the feature removes the step again', async () => {
    const user = userEvent.setup()
    render(<ProjectCreationWizard />)

    await user.click(screen.getByTestId('wizard-synthetic-checkbox'))
    await user.click(screen.getByTestId('wizard-synthetic-checkbox'))
    await user.type(
      screen.getByTestId('project-create-name-input'),
      'Toggled Off'
    )
    await user.click(screen.getByTestId('project-create-next-button'))

    await waitFor(() => {
      expect(currentStepId()).toBe('settings')
    })
  })
})

/**
 * ProjectCreationWizard — extended-edition AI-Bewertungsbogen step wiring.
 *
 * The feature checkbox row comes from the ProjectWizardRubricEntry slot
 * (rendered by StepProjectInfo) and toggles `features.rubric`; when checked, a
 * 'rubric' step appears after 'evaluation' (or wherever the preceding enabled
 * steps end) and before 'settings', rendering the ProjectWizardRubricStep
 * slot. Community builds register neither slot, so the wizard is unchanged
 * there (covered by the main wizard suites, which run with an empty registry).
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

jest.mock('@/lib/api/projects', () => ({
  projectsAPI: {
    importData: jest.fn(),
    update: jest.fn().mockResolvedValue({}),
    updateVisibility: jest.fn(),
    runNestedImportJob: jest.fn().mockResolvedValue({}),
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

// Rubric slots registered (extended edition); a toggle to simulate the
// community edition (both absent). `mock` prefix = hoist-safe.
let mockSlotsRegistered = true
jest.mock('@/lib/extensions/slots', () => ({
  useSlot: (name: string) => {
    if (!mockSlotsRegistered) return null
    if (name === 'ProjectWizardRubricEntry') {
      return ({ checked, onToggle }: any) => (
        <div data-testid="wizard-feature-rubric">
          <input
            type="checkbox"
            data-testid="wizard-rubric-checkbox"
            checked={!!checked}
            onChange={() => onToggle?.()}
          />
        </div>
      )
    }
    if (name === 'ProjectWizardRubricStep') {
      return ({ data, onChange }: any) => (
        <div data-testid="rubric-step-stub">
          <span data-testid="rubric-step-wired">
            {String(!!data && typeof onChange === 'function')}
          </span>
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

describe('ProjectCreationWizard — rubric step (extended)', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockSlotsRegistered = true
  })

  it('adds the rubric step before settings when the row is checked', async () => {
    const user = userEvent.setup()
    render(<ProjectCreationWizard />)

    await user.type(
      screen.getByTestId('project-create-name-input'),
      'Rubric Demo'
    )
    await user.click(screen.getByTestId('wizard-rubric-checkbox'))
    await user.click(screen.getByTestId('project-create-next-button'))

    // No other feature enabled → the rubric step follows projectInfo
    // directly (it always sits right before settings).
    await waitFor(() => {
      expect(currentStepId()).toBe('rubric')
    })
    expect(screen.getByTestId('rubric-step-stub')).toBeInTheDocument()
    expect(screen.getByTestId('rubric-step-wired')).toHaveTextContent('true')

    await user.click(screen.getByTestId('project-create-next-button'))
    await waitFor(() => {
      expect(currentStepId()).toBe('settings')
    })
  })

  it('orders the rubric step after the evaluation step when both are enabled', async () => {
    const user = userEvent.setup()
    render(<ProjectCreationWizard />)

    await user.type(screen.getByTestId('project-create-name-input'), 'R2')
    // Enable the core evaluation feature + the rubric feature.
    await user.click(
      screen
        .getByTestId('wizard-feature-evaluation')
        .querySelector('input[type="checkbox"]') as HTMLElement
    )
    await user.click(screen.getByTestId('wizard-rubric-checkbox'))

    await user.click(screen.getByTestId('project-create-next-button'))
    await waitFor(() => expect(currentStepId()).toBe('evaluation'))
    await user.click(screen.getByTestId('project-create-next-button'))
    await waitFor(() => expect(currentStepId()).toBe('rubric'))
    await user.click(screen.getByTestId('project-create-next-button'))
    await waitFor(() => expect(currentStepId()).toBe('settings'))
  })

  it('renders nothing rubric-related in the community edition (no slots)', () => {
    mockSlotsRegistered = false
    render(<ProjectCreationWizard />)
    expect(screen.queryByTestId('wizard-feature-rubric')).not.toBeInTheDocument()
    expect(screen.queryByTestId('rubric-step-stub')).not.toBeInTheDocument()
  })
})

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

jest.mock('@/lib/api/projects', () => ({
  projectsAPI: { importData: jest.fn(), update: jest.fn() },
}))

jest.mock('@/lib/api/client', () => ({
  apiClient: { put: jest.fn() },
}))

jest.mock('@/stores/projectStore', () => ({
  useProjectStore: () => ({
    createProject: jest.fn(),
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
      return () => <div data-testid="synthetic-step-stub" />
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

/**
 * ProjectCreationWizard — cloud-storage import wiring.
 *
 * The dataImport step's cloud tab renders the select-mode CloudImportPanel;
 * the selection lands in wizardData.cloudImport, satisfies the finish-time
 * import gate, and is imported via runCloudImportJobs after project creation.
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
const mockRunCloudImportJobs = jest.fn()
const mockProjectUpdate = jest.fn()
jest.mock('@/lib/api/projects', () => ({
  projectsAPI: {
    importData: jest.fn(),
    update: (...a: any[]) => mockProjectUpdate(...a),
    updateVisibility: jest.fn(),
    runNestedImportJob: (...a: any[]) => mockRunNestedImportJob(...a),
    runCloudImportJobs: (...a: any[]) => mockRunCloudImportJobs(...a),
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

const mockAddToast = jest.fn()
jest.mock('@/components/shared/Toast', () => ({
  useToast: () => ({
    addToast: mockAddToast,
    showToast: jest.fn(),
    removeToast: jest.fn(),
  }),
  ToastProvider: ({ children }: { children: React.ReactNode }) => children,
}))

// Community build: no extended wizard slots.
jest.mock('@/lib/extensions/slots', () => ({
  useSlot: () => null,
  getSlot: () => null,
  hasSlot: () => false,
  registerSlot: jest.fn(),
}))

// The panel itself is covered by its own suite — here it's a stub whose
// button feeds a fixed selection through onSelectionChange, exactly like
// the real select-mode panel does.
const CLOUD_SELECTION = {
  organizationId: 'org-1',
  connectionId: 'conn-1',
  objectKeys: ['imports/a.json', 'imports/b.csv'],
}
jest.mock('@/components/projects/import/CloudImportPanel', () => ({
  CloudImportPanel: ({ mode, onSelectionChange }: any) => (
    <div data-testid="cloud-import-panel-stub" data-mode={mode}>
      <button
        data-testid="cloud-import-select-stub"
        onClick={() =>
          onSelectionChange?.({
            organizationId: 'org-1',
            connectionId: 'conn-1',
            objectKeys: ['imports/a.json', 'imports/b.csv'],
          })
        }
      >
        select
      </button>
    </div>
  ),
}))

const currentStepId = () =>
  screen
    .getByTestId('project-create-step-indicator')
    .getAttribute('data-current-step-id')

async function enableDataImportFeature(
  user: ReturnType<typeof userEvent.setup>
) {
  const wrapper = screen.getByTestId('wizard-feature-dataImport')
  const checkbox = wrapper.querySelector('input[type="checkbox"]')!
  await user.click(checkbox)
}

describe('ProjectCreationWizard — cloud import', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockCreateProject.mockResolvedValue({ id: 'proj-1' })
    mockProjectUpdate.mockResolvedValue({})
    mockRunNestedImportJob.mockResolvedValue({})
    mockRunCloudImportJobs.mockResolvedValue([])
  })

  async function walkToDataImportCloudTab(
    user: ReturnType<typeof userEvent.setup>
  ) {
    await user.type(
      screen.getByTestId('project-create-name-input'),
      'Cloud Project'
    )
    await enableDataImportFeature(user)
    await user.click(screen.getByTestId('project-create-next-button'))
    await waitFor(() => expect(currentStepId()).toBe('dataImport'))
    await user.click(screen.getByTestId('project-create-cloud-tab'))
    await screen.findByTestId('cloud-import-panel-stub')
  }

  it('renders the select-mode panel on the cloud tab of the wizard step', async () => {
    const user = userEvent.setup()
    render(<ProjectCreationWizard />)
    await walkToDataImportCloudTab(user)
    expect(screen.getByTestId('cloud-import-panel-stub')).toHaveAttribute(
      'data-mode',
      'select'
    )
  })

  it('imports the cloud selection after project creation', async () => {
    const user = userEvent.setup()
    render(<ProjectCreationWizard />)
    await walkToDataImportCloudTab(user)

    // The panel reports a selection → cloudImport lands in wizard state.
    await user.click(screen.getByTestId('cloud-import-select-stub'))

    // Walk to the end (no pasted data, no file — the cloud selection alone
    // must satisfy the finish-time import gate).
    await user.click(screen.getByTestId('project-create-next-button'))
    await waitFor(() => expect(currentStepId()).toBe('settings'))
    await user.click(screen.getByTestId('project-create-submit-button'))

    await waitFor(() =>
      expect(mockRunCloudImportJobs).toHaveBeenCalledWith('proj-1', {
        connection_id: CLOUD_SELECTION.connectionId,
        object_keys: CLOUD_SELECTION.objectKeys,
      })
    )
    // No upload-based import ran for a pure cloud selection.
    expect(mockRunNestedImportJob).not.toHaveBeenCalled()
    await waitFor(() => expect(mockPush).toHaveBeenCalledWith('/projects/proj-1'))
  })

  it('does not run any import when nothing was selected', async () => {
    const user = userEvent.setup()
    render(<ProjectCreationWizard />)
    await walkToDataImportCloudTab(user)

    await user.click(screen.getByTestId('project-create-next-button'))
    await waitFor(() => expect(currentStepId()).toBe('settings'))
    await user.click(screen.getByTestId('project-create-submit-button'))

    await waitFor(() => expect(mockCreateProject).toHaveBeenCalled())
    await waitFor(() => expect(mockPush).toHaveBeenCalledWith('/projects/proj-1'))
    expect(mockRunCloudImportJobs).not.toHaveBeenCalled()
    expect(mockRunNestedImportJob).not.toHaveBeenCalled()
  })

  it('toasts (but still finishes) when the cloud import fails', async () => {
    mockRunCloudImportJobs.mockRejectedValue(
      new Error('imports/a.json: bad payload')
    )
    const user = userEvent.setup()
    render(<ProjectCreationWizard />)
    await walkToDataImportCloudTab(user)
    await user.click(screen.getByTestId('cloud-import-select-stub'))

    await user.click(screen.getByTestId('project-create-next-button'))
    await waitFor(() => expect(currentStepId()).toBe('settings'))
    await user.click(screen.getByTestId('project-create-submit-button'))

    await waitFor(() => expect(mockRunCloudImportJobs).toHaveBeenCalled())
    // Same error handling as the nested import: toast, then carry on.
    await waitFor(() =>
      expect(mockAddToast).toHaveBeenCalledWith(
        'projects.wizard.importDataFailed',
        'error'
      )
    )
    await waitFor(() => expect(mockPush).toHaveBeenCalledWith('/projects/proj-1'))
  })
})

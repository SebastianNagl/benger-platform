/**
 * Branch coverage tests for ProjectCreationWizard (dynamic wizard)
 *
 * @jest-environment jsdom
 */

import '@testing-library/jest-dom'
import { render, screen, waitFor, act, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ProjectCreationWizard } from '../ProjectCreationWizard'

const mockPush = jest.fn()
jest.mock('next/navigation', () => ({
  useRouter: () => ({
    push: mockPush,
    replace: jest.fn(),
    back: jest.fn(),
  }),
}))

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, params?: any) => {
      const translations: Record<string, string> = {
        'projects.creation.wizard.steps.projectInfo.name': 'Project Info',
        'projects.creation.wizard.steps.projectInfo.description': 'Basic information',
        'projects.creation.wizard.steps.dataImport.name': 'Data Import',
        'projects.creation.wizard.steps.dataImport.description': 'Upload data',
        'projects.creation.wizard.steps.labelingSetup.name': 'Labeling Setup',
        'projects.creation.wizard.steps.labelingSetup.description': 'Configure labels',
        'projects.creation.wizard.steps.annotationInstructions.name': 'Instructions',
        'projects.creation.wizard.steps.annotationInstructions.description': 'Annotation instructions',
        'projects.creation.wizard.steps.models.name': 'Models',
        'projects.creation.wizard.steps.models.description': 'Select models',
        'projects.creation.wizard.steps.prompts.name': 'Prompts',
        'projects.creation.wizard.steps.prompts.description': 'Configure prompts',
        'projects.creation.wizard.steps.evaluation.name': 'Evaluation',
        'projects.creation.wizard.steps.evaluation.description': 'Select metrics',
        'projects.creation.wizard.steps.settings.name': 'Settings',
        'projects.creation.wizard.steps.settings.description': 'Configure settings',
        'projects.creation.wizard.step1.title': 'Project Information',
        'projects.creation.wizard.step1.subtitle': 'Enter basic project details',
        'projects.creation.wizard.step1.projectName': 'Project Name',
        'projects.creation.wizard.step1.projectNamePlaceholder': 'Enter project name',
        'projects.creation.wizard.step1.description': 'Description',
        'projects.creation.wizard.step1.optional': '(Optional)',
        'projects.creation.wizard.step1.descriptionPlaceholder': 'Enter description',
        'projects.creation.wizard.step1.validation.nameRequired': 'Project name is required',
        'projects.creation.wizard.features.title': 'Project Features',
        'projects.creation.wizard.features.editLater': 'Can be edited later',
        'projects.creation.wizard.features.annotation': 'Annotation',
        'projects.creation.wizard.features.annotationDescription': 'Labels and instructions',
        'projects.creation.wizard.features.dataImport': 'Data Import',
        'projects.creation.wizard.features.dataImportDescription': 'Upload or paste data',
        'projects.creation.wizard.features.llmGeneration': 'LLM Generation',
        'projects.creation.wizard.features.llmGenerationDescription': 'Models and prompts',
        'projects.creation.wizard.features.evaluation': 'Evaluation',
        'projects.creation.wizard.features.evaluationDescription': 'Metrics and methods',
        'projects.creation.wizard.step2.title': 'Import Data',
        'projects.creation.wizard.step2.subtitle': 'Upload or paste data',
        'projects.creation.wizard.step2.tabs.upload': 'Upload',
        'projects.creation.wizard.step2.tabs.paste': 'Paste',
        'projects.creation.wizard.step2.tabs.cloud': 'Cloud',
        'projects.creation.wizard.step2.upload.dropzone': 'Drop files here',
        'projects.creation.wizard.step2.upload.supportedFormats': 'JSON, CSV, TSV',
        'projects.creation.wizard.step2.upload.chooseFiles': 'Choose Files',
        'projects.creation.wizard.step2.upload.selectedFile': `Selected: ${params?.filename ?? ''}`,
        'projects.creation.wizard.step2.upload.removeFile': 'Remove file',
        'projects.creation.wizard.step2.paste.label': 'Paste Data',
        'projects.creation.wizard.step2.paste.placeholder': 'Paste data here',
        'projects.creation.wizard.step2.paste.lines': `${params?.count ?? 0} lines`,
        'projects.creation.wizard.step2.paste.noData': 'No data',
        'projects.creation.wizard.step2.paste.clear': 'Clear',
        'projects.creation.wizard.step2.paste.validate': 'Validate',
        'projects.creation.wizard.step2.paste.formatDetected': `Format: ${params?.format ?? ''}`,
        'projects.creation.wizard.step2.paste.invalidFormat': 'Invalid format',
        'projects.creation.wizard.step2.cloud.comingSoon': 'Coming soon',
        'projects.creation.wizard.step2.note': 'You can add data later',
        'projects.creation.wizard.step3.title': 'Labeling Setup',
        'projects.creation.wizard.step3.subtitle': 'Configure labeling interface',
        'projects.creation.wizard.step3.tabs.templates': 'Templates',
        'projects.creation.wizard.step3.tabs.custom': 'Custom',
        'projects.creation.wizard.step3.templates.label': 'Choose a template',
        'projects.creation.wizard.step3.templates.description': 'Select from templates',
        'projects.creation.wizard.step3.templates.selected': 'Selected',
        'projects.creation.wizard.step3.custom.label': 'Custom Configuration',
        'projects.creation.wizard.step3.custom.description': 'Write your own config',
        'projects.creation.wizard.step3.custom.helpTitle': 'Help',
        'projects.creation.wizard.step3.custom.helpText': 'Learn more at',
        'projects.creation.wizard.step3.preview.title': 'Preview',
        'projects.creation.wizard.step3.preview.viewXml': 'View XML',
        'projects.creation.wizard.navigation.cancel': 'Cancel',
        'projects.creation.wizard.navigation.back': 'Back',
        'projects.creation.wizard.navigation.next': 'Next',
        'projects.creation.wizard.navigation.skip': 'Skip',
        'projects.creation.wizard.navigation.create': 'Create Project',
        'projects.creation.wizard.navigation.creating': 'Creating...',
        'projects.creation.wizard.templates.questionAnswering.name': 'Question Answering',
        'projects.creation.wizard.templates.questionAnswering.description': 'QA tasks',
        'projects.creation.wizard.templates.multipleChoice.name': 'Multiple Choice',
        'projects.creation.wizard.templates.multipleChoice.description': 'MC tasks',
        'projects.creation.wizard.templates.examSolving.name': 'Exam Solving',
        'projects.creation.wizard.templates.examSolving.description': 'Legal exams',
        'projects.creation.wizard.templates.spanAnnotation.name': 'Span Annotation',
        'projects.creation.wizard.templates.spanAnnotation.description': 'NER tasks',
        'projects.creation.wizard.templates.custom.name': 'Custom',
        'projects.creation.wizard.templates.custom.description': 'Custom setup',
        'projects.wizard.note': 'Note',
        'projects.wizard.projectCreatedWithTasks': `Project created with ${params?.count ?? 0} tasks`,
        'projects.wizard.projectCreated': 'Project created successfully',
        'projects.wizard.importDataFailed': `Import failed: ${params?.error ?? ''}`,
        'projects.wizard.unknownError': 'Unknown error',
        'projects.wizard.createFailed': 'Failed to create project',
        'projects.wizard.customConfigName': 'Custom Config',
        'projects.wizard.customConfigDescription': 'Custom configuration',
        'projects.wizard.labelStudioDocs': 'Label Studio docs',
        'projects.creation.wizard.stepSettings.title': 'Project Settings',
        'projects.creation.wizard.stepSettings.subtitle': 'Configure settings',
        'projects.creation.wizard.stepSettings.assignmentMode': 'Assignment Mode',
        'projects.creation.wizard.stepSettings.assignmentModeHint': 'How tasks are distributed',
        'projects.creation.wizard.stepSettings.modes.open': 'Open',
        'projects.creation.wizard.stepSettings.modes.manual': 'Manual',
        'projects.creation.wizard.stepSettings.modes.auto': 'Auto',
        'projects.creation.wizard.stepSettings.modesHint.open': 'Pick freely',
        'projects.creation.wizard.stepSettings.modesHint.manual': 'Admins assign',
        'projects.creation.wizard.stepSettings.modesHint.auto': 'Auto-assigned',
        'projects.creation.wizard.stepSettings.maxAnnotations': 'Max Annotations',
        'projects.creation.wizard.stepSettings.minAnnotations': 'Min Annotations',
        'projects.creation.wizard.stepSettings.unlimited': 'Unlimited',
        'projects.creation.wizard.stepSettings.showSkipButton': 'Show Skip Button',
        'projects.creation.wizard.stepSettings.showSkipButtonHint': 'Allow skipping',
        'projects.creation.wizard.stepSettings.showInstructions': 'Show Instructions',
        'projects.creation.wizard.stepSettings.showInstructionsHint': 'Display instructions',
        'projects.creation.wizard.stepSettings.randomizeOrder': 'Randomize Order',
        'projects.creation.wizard.stepSettings.randomizeOrderHint': 'Random order',
        'projects.creation.wizard.stepSettings.advancedNote': 'More settings on project page.',
      }
      return translations[key] || key
    },
  }),
}))

const mockCreateProject = jest.fn()
const mockFetchProject = jest.fn()

jest.mock('@/stores/projectStore', () => ({
  useProjectStore: () => ({
    createProject: mockCreateProject,
    fetchProject: mockFetchProject,
    loading: false,
  }),
}))

jest.mock('@/lib/api/projects', () => ({
  projectsAPI: {
    importData: jest.fn().mockResolvedValue({}),
    update: jest.fn().mockResolvedValue({}),
  },
}))

jest.mock('@/lib/api/client', () => ({
  apiClient: {
    put: jest.fn().mockResolvedValue({}),
  },
}))

jest.mock('@/hooks/useModels', () => ({
  useModels: () => ({
    models: [],
    loading: false,
    error: null,
    refetch: jest.fn(),
    hasApiKeys: false,
    apiKeyStatus: null,
  }),
  default: () => ({}),
}))

const mockToastSuccess = jest.fn()
const mockToastError = jest.fn()
const mockAddToast = jest.fn(
  (message: string, type: 'success' | 'error' | 'info' | 'warning' = 'info') => {
    if (type === 'success') mockToastSuccess(message)
    if (type === 'error') mockToastError(message)
    return 'mock-toast-id'
  }
)
jest.mock('@/components/shared/Toast', () => ({
  useToast: () => ({
    addToast: mockAddToast,
    showToast: mockAddToast,
    removeToast: jest.fn(),
  }),
  ToastProvider: ({ children }: { children: React.ReactNode }) => children,
}))

describe('ProjectCreationWizard branch coverage', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockCreateProject.mockResolvedValue({ id: 'new-project-id' })
  })

  // Helper to navigate to Settings (always last) and click Create
  async function navigateToSettingsAndSubmit(user: ReturnType<typeof userEvent.setup>) {
    // Click Next until we reach the submit button (Settings is always last)
    for (let i = 0; i < 10; i++) {
      const submitBtn = screen.queryByTestId('project-create-submit-button')
      if (submitBtn) {
        await user.click(submitBtn)
        return
      }
      const nextBtn = screen.queryByTestId('project-create-next-button')
      if (nextBtn) {
        await user.click(nextBtn)
        await waitFor(() => {})
      } else {
        break
      }
    }
  }

  // Helper to enable a feature and navigate to data import paste tab
  async function navigateToPasteTab(user: ReturnType<typeof userEvent.setup>, title: string) {
    const titleInput = screen.getByTestId('project-create-name-input')
    await user.type(titleInput, title)

    // Enable data import feature
    await user.click(screen.getByTestId('wizard-feature-dataImport').querySelector('input[type="checkbox"]')!)

    await user.click(screen.getByTestId('project-create-next-button'))

    await waitFor(() => {
      expect(screen.getByText('Import Data')).toBeInTheDocument()
    })

    const pasteTab = screen.getByText('Paste')
    await user.click(pasteTab)

    await waitFor(() => {
      expect(screen.getByTestId('project-create-paste-data-textarea')).toBeInTheDocument()
    })
  }

  it('creates project with TSV pasted data', async () => {
    const user = userEvent.setup()
    render(<ProjectCreationWizard />)

    await navigateToPasteTab(user, 'TSV Project')
    const pasteArea = screen.getByTestId('project-create-paste-data-textarea')
    await user.type(pasteArea, 'col1\tcol2\nval1\tval2')

    await navigateToSettingsAndSubmit(user)

    await waitFor(() => {
      expect(mockCreateProject).toHaveBeenCalled()
    })
  })

  it('creates project with CSV pasted data', async () => {
    const user = userEvent.setup()
    render(<ProjectCreationWizard />)

    await navigateToPasteTab(user, 'CSV Project')
    const pasteArea = screen.getByTestId('project-create-paste-data-textarea')
    await user.type(pasteArea, 'col1,col2\nval1,val2')

    await navigateToSettingsAndSubmit(user)

    await waitFor(() => {
      expect(mockCreateProject).toHaveBeenCalled()
    })
  })

  it('creates project with JSON pasted data', async () => {
    const user = userEvent.setup()
    render(<ProjectCreationWizard />)

    await navigateToPasteTab(user, 'JSON Project')
    const pasteArea = screen.getByTestId('project-create-paste-data-textarea')
    fireEvent.change(pasteArea, { target: { value: '[{"text":"hello"}]' } })

    await navigateToSettingsAndSubmit(user)

    await waitFor(() => {
      expect(mockCreateProject).toHaveBeenCalled()
    })
  })

  it('creates project with plain text pasted data', async () => {
    const user = userEvent.setup()
    render(<ProjectCreationWizard />)

    await navigateToPasteTab(user, 'Text Project')
    const pasteArea = screen.getByTestId('project-create-paste-data-textarea')
    await user.type(pasteArea, 'line one\nline two\nline three')

    await navigateToSettingsAndSubmit(user)

    await waitFor(() => {
      expect(mockCreateProject).toHaveBeenCalled()
    })
  })

  it('detects TSV format on validate', async () => {
    const user = userEvent.setup()
    render(<ProjectCreationWizard />)

    await navigateToPasteTab(user, 'Test')
    const pasteArea = screen.getByTestId('project-create-paste-data-textarea')
    await user.type(pasteArea, 'col1\tcol2\nval1\tval2')

    await user.click(screen.getByTestId('project-create-validate-data-button'))

    await waitFor(() => {
      expect(mockToastSuccess).toHaveBeenCalledWith(
        expect.stringContaining('TSV')
      )
    })
  })

  it('detects CSV format on validate', async () => {
    const user = userEvent.setup()
    render(<ProjectCreationWizard />)

    await navigateToPasteTab(user, 'Test')
    const pasteArea = screen.getByTestId('project-create-paste-data-textarea')
    await user.type(pasteArea, 'col1,col2\nval1,val2')

    await user.click(screen.getByTestId('project-create-validate-data-button'))

    await waitFor(() => {
      expect(mockToastSuccess).toHaveBeenCalledWith(
        expect.stringContaining('CSV')
      )
    })
  })

  it('shows generic error when createProject throws non-Error', async () => {
    const user = userEvent.setup()
    mockCreateProject.mockRejectedValue('string error')

    render(<ProjectCreationWizard />)

    const titleInput = screen.getByTestId('project-create-name-input')
    await user.type(titleInput, 'Error Project')

    await navigateToSettingsAndSubmit(user)

    await waitFor(() => {
      expect(mockToastError).toHaveBeenCalledWith('Failed to create project')
    })
  })

  it('shows error message when createProject throws Error', async () => {
    const user = userEvent.setup()
    mockCreateProject.mockRejectedValue(new Error('Server error'))

    render(<ProjectCreationWizard />)

    const titleInput = screen.getByTestId('project-create-name-input')
    await user.type(titleInput, 'Error Project')

    await navigateToSettingsAndSubmit(user)

    await waitFor(() => {
      expect(mockToastError).toHaveBeenCalledWith('Server error')
    })
  })

  it('creates project without data import when no features checked', async () => {
    const user = userEvent.setup()
    render(<ProjectCreationWizard />)

    const titleInput = screen.getByTestId('project-create-name-input')
    await user.type(titleInput, 'Simple Project')

    await navigateToSettingsAndSubmit(user)

    await waitFor(() => {
      expect(mockToastSuccess).toHaveBeenCalledWith('Project created successfully')
    })
    expect(mockPush).toHaveBeenCalledWith('/projects/new-project-id')
  })

  it('shows validation error when title is empty', async () => {
    const user = userEvent.setup()
    render(<ProjectCreationWizard />)

    // Enable a feature so the Next button appears instead of Create
    await user.click(screen.getByTestId('wizard-feature-dataImport').querySelector('input[type="checkbox"]')!)
    await user.click(screen.getByTestId('project-create-next-button'))

    expect(screen.getByText('Project name is required')).toBeInTheDocument()
  })

  it('navigates to projects on cancel', async () => {
    const user = userEvent.setup()
    render(<ProjectCreationWizard />)

    await user.click(screen.getByTestId('project-create-cancel-button'))
    expect(mockPush).toHaveBeenCalledWith('/projects')
  })

  it('handles file drop on data import step', async () => {
    const user = userEvent.setup()
    render(<ProjectCreationWizard />)

    const titleInput = screen.getByTestId('project-create-name-input')
    await user.type(titleInput, 'Drop Project')
    await user.click(screen.getByTestId('wizard-feature-dataImport').querySelector('input[type="checkbox"]')!)
    await user.click(screen.getByTestId('project-create-next-button'))

    await waitFor(() => {
      expect(screen.getByText('Drop files here')).toBeInTheDocument()
    })

    const dropZone = screen.getByRole('button', { name: /Drop files here/i })
    const file = new File(['data'], 'test.json', { type: 'application/json' })

    const dropEvent = new Event('drop', { bubbles: true })
    Object.defineProperty(dropEvent, 'preventDefault', { value: jest.fn() })
    Object.defineProperty(dropEvent, 'dataTransfer', {
      value: { files: [file] },
    })
    await act(async () => {
      dropZone.dispatchEvent(dropEvent)
    })
  })
})

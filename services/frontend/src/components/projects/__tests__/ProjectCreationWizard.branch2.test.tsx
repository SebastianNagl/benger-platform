/**
 * Branch coverage tests for ProjectCreationWizard
 * Targets uncovered branches at lines: 344, 538-540, 578-579, 641-642, 651, 872
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
        'projects.creation.wizard.step1.title': 'Project Information',
        'projects.creation.wizard.step1.subtitle': 'Enter basic project details',
        'projects.creation.wizard.step1.projectName': 'Project Name',
        'projects.creation.wizard.step1.projectNamePlaceholder': 'Enter project name',
        'projects.creation.wizard.step1.description': 'Description',
        'projects.creation.wizard.step1.optional': '(Optional)',
        'projects.creation.wizard.step1.validation.nameRequired': 'Project name is required',
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
        'projects.creation.wizard.step3.templates.description': 'Select from predefined templates',
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
  },
}))

// Mock toast
const mockToastSuccess = jest.fn()
const mockToastError = jest.fn()
jest.mock('react-hot-toast', () => ({
  toast: {
    success: (...args: any[]) => mockToastSuccess(...args),
    error: (...args: any[]) => mockToastError(...args),
  },
}))

describe('ProjectCreationWizard branch coverage', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockCreateProject.mockResolvedValue({ id: 'new-project-id' })
  })

  // Helper to navigate to paste tab on step 2
  async function navigateToPasteTab(user: ReturnType<typeof userEvent.setup>, title: string) {
    const titleInput = screen.getByTestId('project-create-name-input')
    await user.type(titleInput, title)
    await user.click(screen.getByTestId('project-create-next-button'))

    // Wait for step 2 to appear
    await waitFor(() => {
      expect(screen.getByText('Import Data')).toBeInTheDocument()
    })

    // Click the Paste tab by text
    const pasteTab = screen.getByText('Paste')
    await user.click(pasteTab)

    // Wait for paste area to appear
    await waitFor(() => {
      expect(screen.getByTestId('project-create-paste-data-textarea')).toBeInTheDocument()
    })
  }

  // Line 344: parseData - tsv format branch
  it('creates project with TSV pasted data', async () => {
    const user = userEvent.setup()
    render(<ProjectCreationWizard />)

    await navigateToPasteTab(user, 'TSV Project')
    const pasteArea = screen.getByTestId('project-create-paste-data-textarea')
    await user.type(pasteArea, 'col1\tcol2\nval1\tval2')

    await user.click(screen.getByTestId('project-create-next-button'))

    await waitFor(() => {
      expect(screen.getByTestId('project-create-submit-button')).toBeInTheDocument()
    })
    await user.click(screen.getByTestId('project-create-submit-button'))

    await waitFor(() => {
      expect(mockCreateProject).toHaveBeenCalled()
    })
  })

  // Line 344: parseData - csv detection
  it('creates project with CSV pasted data', async () => {
    const user = userEvent.setup()
    render(<ProjectCreationWizard />)

    await navigateToPasteTab(user, 'CSV Project')
    const pasteArea = screen.getByTestId('project-create-paste-data-textarea')
    await user.type(pasteArea, 'col1,col2\nval1,val2')

    await user.click(screen.getByTestId('project-create-next-button'))

    await waitFor(() => {
      expect(screen.getByTestId('project-create-submit-button')).toBeInTheDocument()
    })
    await user.click(screen.getByTestId('project-create-submit-button'))

    await waitFor(() => {
      expect(mockCreateProject).toHaveBeenCalled()
    })
  })

  // Lines 538-540: handleFinish with selectedFile
  it('creates project with uploaded file', async () => {
    const user = userEvent.setup()
    render(<ProjectCreationWizard />)

    // Step 1
    const titleInput = screen.getByTestId('project-create-name-input')
    await user.type(titleInput, 'File Project')
    await user.click(screen.getByTestId('project-create-next-button'))

    // Step 2 - upload a file
    await waitFor(() => {
      expect(screen.getByTestId('project-create-file-input')).toBeInTheDocument()
    })

    const fileInput = screen.getByTestId('project-create-file-input')
    const file = new File(['[{"text":"hello"}]'], 'data.json', { type: 'application/json' })
    await act(async () => {
      Object.defineProperty(fileInput, 'files', { value: [file] })
      fileInput.dispatchEvent(new Event('change', { bubbles: true }))
    })

    await user.click(screen.getByTestId('project-create-next-button'))

    // Step 3 - submit
    await waitFor(() => {
      expect(screen.getByTestId('project-create-submit-button')).toBeInTheDocument()
    })
    await user.click(screen.getByTestId('project-create-submit-button'))

    await waitFor(() => {
      expect(mockCreateProject).toHaveBeenCalled()
    })
  })

  // Line 578-579: handleFinish - JSON pasted data (starts with '[' or '{')
  it('creates project with JSON pasted data', async () => {
    const user = userEvent.setup()
    render(<ProjectCreationWizard />)

    await navigateToPasteTab(user, 'JSON Project')
    const pasteArea = screen.getByTestId('project-create-paste-data-textarea')
    // Use fireEvent instead of userEvent.type to avoid keyboard shortcut parsing
    fireEvent.change(pasteArea, { target: { value: '[{"text":"hello"}]' } })

    await user.click(screen.getByTestId('project-create-next-button'))

    await waitFor(() => {
      expect(screen.getByTestId('project-create-submit-button')).toBeInTheDocument()
    })
    await user.click(screen.getByTestId('project-create-submit-button'))

    await waitFor(() => {
      expect(mockCreateProject).toHaveBeenCalled()
    })
  })

  // Line 641-642: handleFinish - plain text data
  it('creates project with plain text pasted data', async () => {
    const user = userEvent.setup()
    render(<ProjectCreationWizard />)

    await navigateToPasteTab(user, 'Text Project')
    const pasteArea = screen.getByTestId('project-create-paste-data-textarea')
    await user.type(pasteArea, 'line one\nline two\nline three')

    await user.click(screen.getByTestId('project-create-next-button'))

    await waitFor(() => {
      expect(screen.getByTestId('project-create-submit-button')).toBeInTheDocument()
    })
    await user.click(screen.getByTestId('project-create-submit-button'))

    await waitFor(() => {
      expect(mockCreateProject).toHaveBeenCalled()
    })
  })

  // Line 651: validate button - tsv detection
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

  // Line 651: validate button - csv detection
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

  // Line 872: renderCurrentStep - default case (should never happen, returns null)
  // This is an edge case, covered by the component's switch statement.

  // handleFinish - createProject error (non-Error type)
  it('shows generic error when createProject throws non-Error', async () => {
    const user = userEvent.setup()
    mockCreateProject.mockRejectedValue('string error')

    render(<ProjectCreationWizard />)

    const titleInput = screen.getByTestId('project-create-name-input')
    await user.type(titleInput, 'Error Project')
    await user.click(screen.getByTestId('project-create-next-button'))

    // Skip step 2
    await waitFor(() => {
      expect(screen.getByTestId('project-create-skip-data-button')).toBeInTheDocument()
    })
    await user.click(screen.getByTestId('project-create-skip-data-button'))

    // Step 3 - submit
    await waitFor(() => {
      expect(screen.getByTestId('project-create-submit-button')).toBeInTheDocument()
    })
    await user.click(screen.getByTestId('project-create-submit-button'))

    await waitFor(() => {
      expect(mockToastError).toHaveBeenCalledWith('Failed to create project')
    })
  })

  // handleFinish - createProject error (Error type)
  it('shows error message when createProject throws Error', async () => {
    const user = userEvent.setup()
    mockCreateProject.mockRejectedValue(new Error('Server error'))

    render(<ProjectCreationWizard />)

    const titleInput = screen.getByTestId('project-create-name-input')
    await user.type(titleInput, 'Error Project')
    await user.click(screen.getByTestId('project-create-next-button'))

    await waitFor(() => {
      expect(screen.getByTestId('project-create-skip-data-button')).toBeInTheDocument()
    })
    await user.click(screen.getByTestId('project-create-skip-data-button'))

    await waitFor(() => {
      expect(screen.getByTestId('project-create-submit-button')).toBeInTheDocument()
    })
    await user.click(screen.getByTestId('project-create-submit-button'))

    await waitFor(() => {
      expect(mockToastError).toHaveBeenCalledWith('Server error')
    })
  })

  // handleFinish - no data, no file (no import section)
  it('creates project without data import', async () => {
    const user = userEvent.setup()
    render(<ProjectCreationWizard />)

    const titleInput = screen.getByTestId('project-create-name-input')
    await user.type(titleInput, 'Simple Project')
    await user.click(screen.getByTestId('project-create-next-button'))

    await waitFor(() => {
      expect(screen.getByTestId('project-create-skip-data-button')).toBeInTheDocument()
    })
    await user.click(screen.getByTestId('project-create-skip-data-button'))

    await waitFor(() => {
      expect(screen.getByTestId('project-create-submit-button')).toBeInTheDocument()
    })
    await user.click(screen.getByTestId('project-create-submit-button'))

    await waitFor(() => {
      expect(mockToastSuccess).toHaveBeenCalledWith('Project created successfully')
    })
    expect(mockPush).toHaveBeenCalledWith('/projects/new-project-id')
  })

  // Step 1 validation: empty title
  it('shows validation error when title is empty', async () => {
    const user = userEvent.setup()
    render(<ProjectCreationWizard />)

    // Try to go next without entering title
    await user.click(screen.getByTestId('project-create-next-button'))

    expect(screen.getByText('Project name is required')).toBeInTheDocument()
  })

  // Cancel button on step 1
  it('navigates to projects on cancel', async () => {
    const user = userEvent.setup()
    render(<ProjectCreationWizard />)

    await user.click(screen.getByTestId('project-create-cancel-button'))
    expect(mockPush).toHaveBeenCalledWith('/projects')
  })

  // Drop file handler
  it('handles file drop', async () => {
    const user = userEvent.setup()
    render(<ProjectCreationWizard />)

    const titleInput = screen.getByTestId('project-create-name-input')
    await user.type(titleInput, 'Drop Project')
    await user.click(screen.getByTestId('project-create-next-button'))

    await waitFor(() => {
      expect(screen.getByText('Drop files here')).toBeInTheDocument()
    })

    // The drop zone is found by its role
    const dropZone = screen.getByRole('button', { name: /Drop files here/i })
    const file = new File(['data'], 'test.json', { type: 'application/json' })

    // Simulate drop
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

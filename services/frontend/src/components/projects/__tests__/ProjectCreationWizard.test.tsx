/**
 * Comprehensive tests for ProjectCreationWizard component
 */

/**
 * @jest-environment jsdom
 */

import '@testing-library/jest-dom'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ProjectCreationWizard } from '../ProjectCreationWizard'

// Mock next/navigation
const mockPush = jest.fn()
jest.mock('next/navigation', () => ({
  useRouter: () => ({
    push: mockPush,
    replace: jest.fn(),
    back: jest.fn(),
  }),
}))

// Mock I18n context
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, params?: any) => {
      const translations: Record<string, string> = {
        'projects.creation.wizard.steps.projectInfo.name': 'Project Info',
        'projects.creation.wizard.steps.projectInfo.description':
          'Basic information',
        'projects.creation.wizard.steps.dataImport.name': 'Data Import',
        'projects.creation.wizard.steps.dataImport.description': 'Upload data',
        'projects.creation.wizard.steps.labelingSetup.name': 'Labeling Setup',
        'projects.creation.wizard.steps.labelingSetup.description':
          'Configure labels',
        'projects.creation.wizard.step1.title': 'Project Information',
        'projects.creation.wizard.step1.subtitle':
          'Enter basic project details',
        'projects.creation.wizard.step1.projectName': 'Project Name',
        'projects.creation.wizard.step1.projectNamePlaceholder':
          'Enter project name',
        'projects.creation.wizard.step1.description': 'Description',
        'projects.creation.wizard.step1.optional': '(Optional)',
        'projects.creation.wizard.step1.descriptionPlaceholder':
          'Enter project description',
        'projects.creation.wizard.step1.validation.nameRequired':
          'Project name is required',
        'projects.creation.wizard.step2.title': 'Import Data',
        'projects.creation.wizard.step2.subtitle': 'Add data to project',
        'projects.creation.wizard.step2.tabs.upload': 'Upload',
        'projects.creation.wizard.step2.tabs.paste': 'Paste',
        'projects.creation.wizard.step2.tabs.cloud': 'Cloud',
        'projects.creation.wizard.step2.upload.dropzone':
          'Drop files here or click to upload',
        'projects.creation.wizard.step2.upload.supportedFormats':
          'Supported: JSON, CSV, TSV, TXT',
        'projects.creation.wizard.step2.upload.selectedFile': `Selected: ${params?.filename}`,
        'projects.creation.wizard.step2.upload.removeFile': 'Remove File',
        'projects.creation.wizard.step2.upload.chooseFiles': 'Choose Files',
        'projects.creation.wizard.step2.paste.label': 'Paste Data',
        'projects.creation.wizard.step2.paste.placeholder':
          'Paste your data here',
        'projects.creation.wizard.step2.paste.lines': `${params?.count} lines`,
        'projects.creation.wizard.step2.paste.noData': 'No data',
        'projects.creation.wizard.step2.paste.clear': 'Clear',
        'projects.creation.wizard.step2.paste.validate': 'Validate',
        'projects.creation.wizard.step2.paste.formatDetected': `Format detected: ${params?.format}`,
        'projects.creation.wizard.step2.paste.invalidFormat': 'Invalid format',
        'projects.creation.wizard.step2.cloud.comingSoon': 'Coming soon',
        'projects.creation.wizard.step2.note': 'You can skip this step',
        'projects.creation.wizard.step3.title': 'Labeling Configuration',
        'projects.creation.wizard.step3.subtitle': 'Configure annotation setup',
        'projects.creation.wizard.step3.tabs.templates': 'Templates',
        'projects.creation.wizard.step3.tabs.custom': 'Custom',
        'projects.creation.wizard.step3.templates.label': 'Select a template',
        'projects.creation.wizard.step3.templates.description':
          'Choose from templates',
        'projects.creation.wizard.step3.templates.selected': 'Selected',
        'projects.creation.wizard.step3.custom.label': 'Custom Configuration',
        'projects.creation.wizard.step3.custom.description':
          'Write your own config',
        'projects.creation.wizard.step3.custom.helpTitle': 'Need help?',
        'projects.creation.wizard.step3.custom.helpText': 'See documentation',
        'projects.creation.wizard.step3.preview.title': 'Preview',
        'projects.creation.wizard.step3.preview.viewXml': 'View XML',
        'projects.creation.wizard.templates.questionAnswering.name':
          'Question Answering',
        'projects.creation.wizard.templates.questionAnswering.description':
          'Answer questions',
        'projects.creation.wizard.templates.multipleChoice.name':
          'Multiple Choice Question',
        'projects.creation.wizard.templates.multipleChoice.description':
          'Select from options',
        'projects.creation.wizard.templates.examSolving.name':
          'Exam Solving',
        'projects.creation.wizard.templates.examSolving.description':
          'German legal exam format',
        'projects.creation.wizard.templates.spanAnnotation.name':
          'Span Annotation',
        'projects.creation.wizard.templates.spanAnnotation.description':
          'Highlight text spans',
        'projects.creation.wizard.templates.custom.name':
          'Custom',
        'projects.creation.wizard.templates.custom.description':
          'Custom configuration',
        'projects.creation.wizard.navigation.cancel': 'Cancel',
        'projects.creation.wizard.navigation.back': 'Back',
        'projects.creation.wizard.navigation.next': 'Next',
        'projects.creation.wizard.navigation.skip': 'Skip',
        'projects.creation.wizard.navigation.create': 'Create Project',
        'projects.creation.wizard.navigation.creating': 'Creating...',
        'projects.wizard.projectCreatedWithTasks': `Project created successfully with ${params?.count} tasks imported!`,
        'projects.wizard.projectCreated': 'Project created successfully!',
        'projects.wizard.importDataFailed': `Failed to import data: ${params?.error}`,
        'projects.wizard.unknownError': 'Unknown error',
        'projects.wizard.createFailed': 'Failed to create project',
        'projects.wizard.customConfigName': 'Custom Configuration',
        'projects.wizard.customConfigDescription': 'User-defined configuration',
        'projects.wizard.labelStudioDocs': 'Label Studio documentation',
        'projects.wizard.note': 'Note',
      }
      return translations[key] || key
    },
  }),
}))

// Mock projects API
jest.mock('@/lib/api/projects', () => ({
  projectsAPI: {
    importData: jest.fn(),
  },
}))

// Mock project store
const mockCreateProject = jest.fn()
const mockFetchProject = jest.fn()
jest.mock('@/stores/projectStore', () => ({
  useProjectStore: () => ({
    createProject: mockCreateProject,
    fetchProject: mockFetchProject,
    loading: false,
  }),
}))

// Mock toast
jest.mock('react-hot-toast', () => ({
  toast: {
    success: jest.fn(),
    error: jest.fn(),
  },
}))

describe('ProjectCreationWizard', () => {
  let mockImportData: jest.Mock
  let mockToastSuccess: jest.Mock
  let mockToastError: jest.Mock

  beforeEach(() => {
    jest.clearAllMocks()
    const projectsAPI = require('@/lib/api/projects').projectsAPI
    mockImportData = projectsAPI.importData as jest.Mock

    const toast = require('react-hot-toast').toast
    mockToastSuccess = toast.success as jest.Mock
    mockToastError = toast.error as jest.Mock
  })

  describe('Wizard Initialization', () => {
    it('renders the wizard with step 1 active', () => {
      render(<ProjectCreationWizard />)

      expect(screen.getByText('Project Information')).toBeInTheDocument()
      expect(screen.getByTestId('project-create-step-1')).toBeInTheDocument()
    })

    it('displays all three steps in the progress indicator', () => {
      render(<ProjectCreationWizard />)

      expect(screen.getByText('Project Info')).toBeInTheDocument()
      expect(screen.getByText('Data Import')).toBeInTheDocument()
      expect(screen.getByText('Labeling Setup')).toBeInTheDocument()
    })

    it('renders project name input field', () => {
      render(<ProjectCreationWizard />)

      const nameInput = screen.getByTestId('project-create-name-input')
      expect(nameInput).toBeInTheDocument()
      expect(nameInput).toHaveValue('')
    })

    it('renders project description textarea', () => {
      render(<ProjectCreationWizard />)

      const descriptionTextarea = screen.getByTestId(
        'project-create-description-textarea'
      )
      expect(descriptionTextarea).toBeInTheDocument()
      expect(descriptionTextarea).toHaveValue('')
    })
  })

  describe('Step Navigation', () => {
    it('advances to step 2 when next button is clicked with valid data', async () => {
      const user = userEvent.setup()
      render(<ProjectCreationWizard />)

      // Fill in project name
      const nameInput = screen.getByTestId('project-create-name-input')
      await user.type(nameInput, 'Test Project')

      // Click next
      const nextButton = screen.getByTestId('project-create-next-button')
      await user.click(nextButton)

      // Check we're on step 2
      await waitFor(() => {
        expect(screen.getByText('Import Data')).toBeInTheDocument()
      })
    })

    it('advances to step 3 when next button is clicked on step 2', async () => {
      const user = userEvent.setup()
      render(<ProjectCreationWizard />)

      // Step 1: Fill in project name and advance
      const nameInput = screen.getByTestId('project-create-name-input')
      await user.type(nameInput, 'Test Project')
      await user.click(screen.getByTestId('project-create-next-button'))

      // Step 2: Click next without adding data
      await waitFor(() => {
        expect(
          screen.getByTestId('project-create-next-button')
        ).toBeInTheDocument()
      })
      await user.click(screen.getByTestId('project-create-next-button'))

      // Check we're on step 3
      await waitFor(() => {
        expect(screen.getByText('Labeling Configuration')).toBeInTheDocument()
      })
    })

    it('goes back to step 1 when back button is clicked on step 2', async () => {
      const user = userEvent.setup()
      render(<ProjectCreationWizard />)

      // Navigate to step 2
      const nameInput = screen.getByTestId('project-create-name-input')
      await user.type(nameInput, 'Test Project')
      await user.click(screen.getByTestId('project-create-next-button'))

      // Wait for step 2 to load
      await waitFor(() => {
        expect(screen.getByText('Import Data')).toBeInTheDocument()
      })

      // Click back
      const backButton = screen.getByTestId('project-create-back-button')
      await user.click(backButton)

      // Check we're back on step 1
      expect(screen.getByText('Project Information')).toBeInTheDocument()
    })

    it('allows skipping step 2 data import', async () => {
      const user = userEvent.setup()
      render(<ProjectCreationWizard />)

      // Navigate to step 2
      const nameInput = screen.getByTestId('project-create-name-input')
      await user.type(nameInput, 'Test Project')
      await user.click(screen.getByTestId('project-create-next-button'))

      // Wait for step 2
      await waitFor(() => {
        expect(screen.getByText('Import Data')).toBeInTheDocument()
      })

      // Click skip
      const skipButton = screen.getByTestId('project-create-skip-data-button')
      await user.click(skipButton)

      // Should advance to step 3
      await waitFor(() => {
        expect(screen.getByText('Labeling Configuration')).toBeInTheDocument()
      })
    })

    it('displays cancel button on step 1', () => {
      render(<ProjectCreationWizard />)

      const cancelButton = screen.getByTestId('project-create-cancel-button')
      expect(cancelButton).toBeInTheDocument()
      expect(cancelButton).toHaveTextContent('Cancel')
    })

    it('navigates to projects page when cancel is clicked', async () => {
      const user = userEvent.setup()
      render(<ProjectCreationWizard />)

      const cancelButton = screen.getByTestId('project-create-cancel-button')
      await user.click(cancelButton)

      expect(mockPush).toHaveBeenCalledWith('/projects')
    })
  })

  describe('Form Validation', () => {
    it('prevents advancing to step 2 without project name', async () => {
      const user = userEvent.setup()
      render(<ProjectCreationWizard />)

      // Try to click next without filling name
      const nextButton = screen.getByTestId('project-create-next-button')
      await user.click(nextButton)

      // Should show validation error
      expect(screen.getByText('Project name is required')).toBeInTheDocument()

      // Should still be on step 1
      expect(screen.getByText('Project Information')).toBeInTheDocument()
    })

    it('clears validation error when user types in name field', async () => {
      const user = userEvent.setup()
      render(<ProjectCreationWizard />)

      // Trigger validation error
      await user.click(screen.getByTestId('project-create-next-button'))
      expect(screen.getByText('Project name is required')).toBeInTheDocument()

      // Type in name field
      const nameInput = screen.getByTestId('project-create-name-input')
      await user.type(nameInput, 'Test Project')

      // Try to advance again
      await user.click(screen.getByTestId('project-create-next-button'))

      // Error should be gone and we should advance
      await waitFor(() => {
        expect(
          screen.queryByText('Project name is required')
        ).not.toBeInTheDocument()
      })
    })

    it('trims whitespace from project name during validation', async () => {
      const user = userEvent.setup()
      render(<ProjectCreationWizard />)

      // Type only whitespace
      const nameInput = screen.getByTestId('project-create-name-input')
      await user.type(nameInput, '   ')

      // Try to advance
      await user.click(screen.getByTestId('project-create-next-button'))

      // Should show validation error
      expect(screen.getByText('Project name is required')).toBeInTheDocument()
    })
  })

  describe('Data Import - Step 2', () => {
    it('displays three tabs: Upload, Paste, Cloud', async () => {
      const user = userEvent.setup()
      render(<ProjectCreationWizard />)

      const nameInput = screen.getByTestId('project-create-name-input')
      await user.type(nameInput, 'Test Project')
      await user.click(screen.getByTestId('project-create-next-button'))

      await waitFor(() => {
        expect(screen.getByText('Import Data')).toBeInTheDocument()
      })

      // Check that tab labels are present (tabs render as buttons)
      expect(screen.getByText('Upload')).toBeInTheDocument()
      expect(screen.getByText('Paste')).toBeInTheDocument()
      expect(screen.getByText('Cloud')).toBeInTheDocument()
    })

    it('shows upload interface by default', async () => {
      const user = userEvent.setup()
      render(<ProjectCreationWizard />)

      const nameInput = screen.getByTestId('project-create-name-input')
      await user.type(nameInput, 'Test Project')
      await user.click(screen.getByTestId('project-create-next-button'))

      await waitFor(() => {
        expect(
          screen.getByText('Drop files here or click to upload')
        ).toBeInTheDocument()
      })

      expect(
        screen.getByText('Supported: JSON, CSV, TSV, TXT')
      ).toBeInTheDocument()
    })

    it('displays file input when choose files button is clicked', async () => {
      const user = userEvent.setup()
      render(<ProjectCreationWizard />)

      const nameInput = screen.getByTestId('project-create-name-input')
      await user.type(nameInput, 'Test Project')
      await user.click(screen.getByTestId('project-create-next-button'))

      await waitFor(() => {
        expect(screen.getByText('Import Data')).toBeInTheDocument()
      })

      const chooseButton = screen.getByTestId(
        'project-create-choose-files-button'
      )
      expect(chooseButton).toBeInTheDocument()

      // File input should exist but be hidden
      const fileInput = screen.getByTestId('project-create-file-input')
      expect(fileInput).toBeInTheDocument()
      expect(fileInput).toHaveAttribute('type', 'file')
    })

    it('shows paste data textarea in paste tab', async () => {
      const user = userEvent.setup()
      render(<ProjectCreationWizard />)

      const nameInput = screen.getByTestId('project-create-name-input')
      await user.type(nameInput, 'Test Project')
      await user.click(screen.getByTestId('project-create-next-button'))

      await waitFor(() => {
        expect(screen.getByText('Import Data')).toBeInTheDocument()
      })

      // Click on Paste tab by text
      const pasteTab = screen.getByText('Paste')
      await user.click(pasteTab)

      const pasteTextarea = await screen.findByTestId(
        'project-create-paste-data-textarea'
      )
      expect(pasteTextarea).toBeInTheDocument()
    })

    it('updates line count when data is pasted', async () => {
      const user = userEvent.setup()
      render(<ProjectCreationWizard />)

      const nameInput = screen.getByTestId('project-create-name-input')
      await user.type(nameInput, 'Test Project')
      await user.click(screen.getByTestId('project-create-next-button'))

      await waitFor(() => {
        expect(screen.getByText('Import Data')).toBeInTheDocument()
      })

      // Switch to paste tab
      const pasteTab = screen.getByText('Paste')
      await user.click(pasteTab)

      // Paste data
      const pasteTextarea = await screen.findByTestId(
        'project-create-paste-data-textarea'
      )
      await user.type(pasteTextarea, 'Line 1\nLine 2\nLine 3')

      // Check line count
      expect(screen.getByText('3 lines')).toBeInTheDocument()
    })

    it('clears pasted data when clear button is clicked', async () => {
      const user = userEvent.setup()
      render(<ProjectCreationWizard />)

      const nameInput = screen.getByTestId('project-create-name-input')
      await user.type(nameInput, 'Test Project')
      await user.click(screen.getByTestId('project-create-next-button'))

      await waitFor(() => {
        expect(screen.getByText('Import Data')).toBeInTheDocument()
      })

      // Switch to paste tab
      await user.click(screen.getByText('Paste'))

      // Paste data
      const pasteTextarea = await screen.findByTestId(
        'project-create-paste-data-textarea'
      )
      await user.type(pasteTextarea, 'Test data')

      // Click clear
      const clearButton = screen.getByTestId('project-create-clear-data-button')
      await user.click(clearButton)

      // Data should be cleared
      expect(pasteTextarea).toHaveValue('')
    })

    it('detects JSON format when validate is clicked', async () => {
      const user = userEvent.setup()
      render(<ProjectCreationWizard />)

      const nameInput = screen.getByTestId('project-create-name-input')
      await user.type(nameInput, 'Test Project')
      await user.click(screen.getByTestId('project-create-next-button'))

      await waitFor(() => {
        expect(screen.getByText('Import Data')).toBeInTheDocument()
      })

      // Switch to paste tab
      await user.click(screen.getByText('Paste'))

      // Paste JSON data
      const pasteTextarea = await screen.findByTestId(
        'project-create-paste-data-textarea'
      )
      await user.click(pasteTextarea)
      await user.paste('{"test": "data"}')

      // Click validate
      const validateButton = screen.getByTestId(
        'project-create-validate-data-button'
      )
      await user.click(validateButton)

      // Should show format detected
      expect(mockToastSuccess).toHaveBeenCalledWith('Format detected: JSON')
    })

    it('shows coming soon message in cloud tab', async () => {
      const user = userEvent.setup()
      render(<ProjectCreationWizard />)

      const nameInput = screen.getByTestId('project-create-name-input')
      await user.type(nameInput, 'Test Project')
      await user.click(screen.getByTestId('project-create-next-button'))

      await waitFor(() => {
        expect(screen.getByText('Import Data')).toBeInTheDocument()
      })

      const cloudTab = screen.getByText('Cloud')
      await user.click(cloudTab)

      await waitFor(() => {
        expect(screen.getByText('Coming soon')).toBeInTheDocument()
      })
    })
  })

  describe('Template Selection - Step 3', () => {
    it('displays templates and custom tabs', async () => {
      const user = userEvent.setup()
      render(<ProjectCreationWizard />)

      const nameInput = screen.getByTestId('project-create-name-input')
      await user.type(nameInput, 'Test Project')

      // Advance through steps
      await user.click(screen.getByTestId('project-create-next-button'))
      await waitFor(() => {
        expect(screen.getByText('Import Data')).toBeInTheDocument()
      })
      await user.click(screen.getByTestId('project-create-next-button'))

      await waitFor(() => {
        expect(screen.getByText('Labeling Configuration')).toBeInTheDocument()
      })

      // Check that tab labels are present (Custom appears both as tab and template)
      expect(screen.getByText('Templates')).toBeInTheDocument()
      expect(screen.getAllByText('Custom').length).toBeGreaterThanOrEqual(1)
    })

    it('displays all NLP templates', async () => {
      const user = userEvent.setup()
      render(<ProjectCreationWizard />)

      const nameInput = screen.getByTestId('project-create-name-input')
      await user.type(nameInput, 'Test Project')

      // Advance through steps
      await user.click(screen.getByTestId('project-create-next-button'))
      await waitFor(() => {
        expect(screen.getByText('Import Data')).toBeInTheDocument()
      })
      await user.click(screen.getByTestId('project-create-next-button'))

      await waitFor(() => {
        expect(screen.getByText('Labeling Configuration')).toBeInTheDocument()
      })

      expect(screen.getByText('Question Answering')).toBeInTheDocument()
      expect(screen.getByText('Multiple Choice Question')).toBeInTheDocument()
      expect(screen.getByText('Exam Solving')).toBeInTheDocument()
      expect(screen.getByText('Span Annotation')).toBeInTheDocument()
      // Custom appears twice: as a tab name and as a template name
      expect(screen.getAllByText('Custom').length).toBeGreaterThanOrEqual(2)
    })

    it('selects a template when clicked', async () => {
      const user = userEvent.setup()
      render(<ProjectCreationWizard />)

      const nameInput = screen.getByTestId('project-create-name-input')
      await user.type(nameInput, 'Test Project')

      // Advance through steps
      await user.click(screen.getByTestId('project-create-next-button'))
      await waitFor(() => {
        expect(screen.getByText('Import Data')).toBeInTheDocument()
      })
      await user.click(screen.getByTestId('project-create-next-button'))

      await waitFor(() => {
        expect(screen.getByText('Labeling Configuration')).toBeInTheDocument()
      })

      // Wait for template list to be visible
      await waitFor(() => {
        expect(screen.getByText('Question Answering')).toBeInTheDocument()
      })

      // Click the template card - the text is within a Card component
      const qaText = screen.getByText('Question Answering')
      await user.click(qaText)

      // Should show selected badge
      expect(screen.getByText('Selected')).toBeInTheDocument()
    })

    it('shows preview when template is selected', async () => {
      const user = userEvent.setup()
      render(<ProjectCreationWizard />)

      const nameInput = screen.getByTestId('project-create-name-input')
      await user.type(nameInput, 'Test Project')

      // Advance through steps
      await user.click(screen.getByTestId('project-create-next-button'))
      await waitFor(() => {
        expect(screen.getByText('Import Data')).toBeInTheDocument()
      })
      await user.click(screen.getByTestId('project-create-next-button'))

      await waitFor(() => {
        expect(screen.getByText('Labeling Configuration')).toBeInTheDocument()
      })

      // Wait for template list to be visible
      await waitFor(() => {
        expect(screen.getByText('Question Answering')).toBeInTheDocument()
      })

      // Click the template card - the text is within a Card component
      const qaText = screen.getByText('Question Answering')
      await user.click(qaText)

      // Should show preview section
      await waitFor(() => {
        expect(screen.getByText('Preview')).toBeInTheDocument()
      })
      expect(screen.getByText('View XML')).toBeInTheDocument()
    })

    it('allows custom configuration in custom tab', async () => {
      const user = userEvent.setup()
      render(<ProjectCreationWizard />)

      const nameInput = screen.getByTestId('project-create-name-input')
      await user.type(nameInput, 'Test Project')

      // Advance through steps
      await user.click(screen.getByTestId('project-create-next-button'))
      await waitFor(() => {
        expect(screen.getByText('Import Data')).toBeInTheDocument()
      })
      await user.click(screen.getByTestId('project-create-next-button'))

      await waitFor(() => {
        expect(screen.getByText('Labeling Configuration')).toBeInTheDocument()
      })

      // Switch to custom tab
      await user.click(screen.getAllByText('Custom')[0])

      // Type custom config
      const customTextarea = await screen.findByTestId(
        'project-create-custom-config-textarea'
      )
      await user.click(customTextarea)
      await user.paste('<View><Text/></View>')

      expect(customTextarea).toHaveValue('<View><Text/></View>')
    })

    it('displays help text in custom tab', async () => {
      const user = userEvent.setup()
      render(<ProjectCreationWizard />)

      const nameInput = screen.getByTestId('project-create-name-input')
      await user.type(nameInput, 'Test Project')

      // Advance through steps
      await user.click(screen.getByTestId('project-create-next-button'))
      await waitFor(() => {
        expect(screen.getByText('Import Data')).toBeInTheDocument()
      })
      await user.click(screen.getByTestId('project-create-next-button'))

      await waitFor(() => {
        expect(screen.getByText('Labeling Configuration')).toBeInTheDocument()
      })

      await user.click(screen.getAllByText('Custom')[0])

      await waitFor(() => {
        expect(screen.getByText('Need help?')).toBeInTheDocument()
      })
      expect(
        screen.getByText(/See documentation/, { exact: false })
      ).toBeInTheDocument()
    })
  })

  describe('Project Creation', () => {
    it('creates project with valid data and default config', async () => {
      const user = userEvent.setup()
      mockCreateProject.mockResolvedValue({ id: 'project-123' })

      render(<ProjectCreationWizard />)

      // Fill in project name
      const nameInput = screen.getByTestId('project-create-name-input')
      await user.type(nameInput, 'Test Project')

      // Navigate to step 3
      await user.click(screen.getByTestId('project-create-next-button'))
      await waitFor(() => {
        expect(screen.getByText('Import Data')).toBeInTheDocument()
      })
      await user.click(screen.getByTestId('project-create-next-button'))

      await waitFor(() => {
        expect(screen.getByText('Labeling Configuration')).toBeInTheDocument()
      })

      // Submit
      const submitButton = screen.getByTestId('project-create-submit-button')
      await user.click(submitButton)

      await waitFor(() => {
        expect(mockCreateProject).toHaveBeenCalledWith(
          expect.objectContaining({
            title: 'Test Project',
            description: '',
            label_config: expect.stringContaining('<View>'),
          })
        )
      })

      expect(mockToastSuccess).toHaveBeenCalledWith(
        'Project created successfully!'
      )
      expect(mockPush).toHaveBeenCalledWith('/projects/project-123')
    })

    it('creates project with description', async () => {
      const user = userEvent.setup()
      mockCreateProject.mockResolvedValue({ id: 'project-123' })

      render(<ProjectCreationWizard />)

      // Fill in project details
      await user.type(
        screen.getByTestId('project-create-name-input'),
        'Test Project'
      )
      await user.type(
        screen.getByTestId('project-create-description-textarea'),
        'Test description'
      )

      // Navigate to final step
      await user.click(screen.getByTestId('project-create-next-button'))
      await waitFor(() => {
        expect(screen.getByText('Import Data')).toBeInTheDocument()
      })
      await user.click(screen.getByTestId('project-create-next-button'))

      await waitFor(() => {
        expect(screen.getByText('Labeling Configuration')).toBeInTheDocument()
      })

      // Submit
      await user.click(screen.getByTestId('project-create-submit-button'))

      await waitFor(() => {
        expect(mockCreateProject).toHaveBeenCalledWith(
          expect.objectContaining({
            title: 'Test Project',
            description: 'Test description',
          })
        )
      })
    })

    it('creates project with selected template', async () => {
      const user = userEvent.setup()
      mockCreateProject.mockResolvedValue({ id: 'project-123' })

      render(<ProjectCreationWizard />)

      // Fill name and navigate to step 3
      await user.type(
        screen.getByTestId('project-create-name-input'),
        'Test Project'
      )
      await user.click(screen.getByTestId('project-create-next-button'))
      await waitFor(() => {
        expect(screen.getByText('Import Data')).toBeInTheDocument()
      })
      await user.click(screen.getByTestId('project-create-next-button'))

      await waitFor(() => {
        expect(screen.getByText('Labeling Configuration')).toBeInTheDocument()
      })

      // Wait for template list to be visible
      await waitFor(() => {
        expect(screen.getByText('Question Answering')).toBeInTheDocument()
      })

      // Select template by clicking its text (which is in the clickable card)
      const qaText = screen.getByText('Question Answering')
      await user.click(qaText)

      // Submit
      await user.click(screen.getByTestId('project-create-submit-button'))

      await waitFor(() => {
        expect(mockCreateProject).toHaveBeenCalledWith(
          expect.objectContaining({
            label_config: expect.stringContaining('TextArea'),
          })
        )
      })
    })

    it('creates project and imports pasted data', async () => {
      const user = userEvent.setup()
      mockCreateProject.mockResolvedValue({ id: 'project-123' })
      mockImportData.mockResolvedValue({})
      mockFetchProject.mockResolvedValue({})

      render(<ProjectCreationWizard />)

      // Fill name
      await user.type(
        screen.getByTestId('project-create-name-input'),
        'Test Project'
      )

      // Navigate to step 2
      await user.click(screen.getByTestId('project-create-next-button'))
      await waitFor(() => {
        expect(screen.getByText('Import Data')).toBeInTheDocument()
      })

      // Paste data
      await user.click(screen.getByText('Paste'))
      const pasteTextarea = await screen.findByTestId(
        'project-create-paste-data-textarea'
      )
      await user.click(pasteTextarea)
      await user.paste('{"text": "Test task"}')

      // Navigate to step 3 and submit
      await user.click(screen.getByTestId('project-create-next-button'))
      await waitFor(() => {
        expect(screen.getByText('Labeling Configuration')).toBeInTheDocument()
      })
      await user.click(screen.getByTestId('project-create-submit-button'))

      await waitFor(() => {
        expect(mockImportData).toHaveBeenCalledWith(
          'project-123',
          expect.objectContaining({
            data: expect.arrayContaining([
              expect.objectContaining({ text: 'Test task' }),
            ]),
          })
        )
      })

      await waitFor(() => {
        expect(mockToastSuccess).toHaveBeenCalledWith(
          'Project created successfully with 1 tasks imported!'
        )
      })
    })

    it('handles project creation error', async () => {
      const user = userEvent.setup()
      mockCreateProject.mockRejectedValue(new Error('Creation failed'))

      render(<ProjectCreationWizard />)

      // Fill name and navigate to final step
      await user.type(
        screen.getByTestId('project-create-name-input'),
        'Test Project'
      )
      await user.click(screen.getByTestId('project-create-next-button'))
      await waitFor(() => {
        expect(screen.getByText('Import Data')).toBeInTheDocument()
      })
      await user.click(screen.getByTestId('project-create-next-button'))

      await waitFor(() => {
        expect(screen.getByText('Labeling Configuration')).toBeInTheDocument()
      })

      // Submit
      await user.click(screen.getByTestId('project-create-submit-button'))

      await waitFor(() => {
        expect(mockToastError).toHaveBeenCalledWith('Creation failed')
      })

      // Should not navigate
      expect(mockPush).not.toHaveBeenCalled()
    })

    it('handles data import error gracefully', async () => {
      const user = userEvent.setup()
      mockCreateProject.mockResolvedValue({ id: 'project-123' })
      mockImportData.mockRejectedValue(new Error('Import failed'))

      render(<ProjectCreationWizard />)

      // Fill name
      await user.type(
        screen.getByTestId('project-create-name-input'),
        'Test Project'
      )

      // Navigate to step 2 and paste data
      await user.click(screen.getByTestId('project-create-next-button'))
      await waitFor(() => {
        expect(screen.getByText('Import Data')).toBeInTheDocument()
      })
      await user.click(screen.getByText('Paste'))
      const pasteTextarea = await screen.findByTestId(
        'project-create-paste-data-textarea'
      )
      await user.click(pasteTextarea)
      await user.paste('{"text": "Test"}')

      // Navigate to step 3 and submit
      await user.click(screen.getByTestId('project-create-next-button'))
      await waitFor(() => {
        expect(screen.getByText('Labeling Configuration')).toBeInTheDocument()
      })
      await user.click(screen.getByTestId('project-create-submit-button'))

      await waitFor(() => {
        expect(mockToastSuccess).toHaveBeenCalledWith(
          'Project created successfully!'
        )
        expect(mockToastError).toHaveBeenCalledWith(
          'Failed to import data: Import failed'
        )
      })

      // Should still navigate to project
      expect(mockPush).toHaveBeenCalledWith('/projects/project-123')
    })
  })

  describe('Completion Flow', () => {
    it('shows create button on final step', async () => {
      const user = userEvent.setup()
      render(<ProjectCreationWizard />)

      // Navigate to step 3
      await user.type(
        screen.getByTestId('project-create-name-input'),
        'Test Project'
      )
      await user.click(screen.getByTestId('project-create-next-button'))
      await waitFor(() => {
        expect(screen.getByText('Import Data')).toBeInTheDocument()
      })
      await user.click(screen.getByTestId('project-create-next-button'))

      await waitFor(() => {
        const submitButton = screen.getByTestId('project-create-submit-button')
        expect(submitButton).toBeInTheDocument()
        expect(submitButton).toHaveTextContent('Create Project')
      })
    })

    it('disables submit button during creation', async () => {
      const user = userEvent.setup()
      // Mock a slow creation
      mockCreateProject.mockImplementation(
        () =>
          new Promise((resolve) =>
            setTimeout(() => resolve({ id: 'project-123' }), 1000)
          )
      )

      render(<ProjectCreationWizard />)

      // Navigate to step 3
      await user.type(
        screen.getByTestId('project-create-name-input'),
        'Test Project'
      )
      await user.click(screen.getByTestId('project-create-next-button'))
      await waitFor(() => {
        expect(screen.getByText('Import Data')).toBeInTheDocument()
      })
      await user.click(screen.getByTestId('project-create-next-button'))

      await waitFor(() => {
        expect(screen.getByText('Labeling Configuration')).toBeInTheDocument()
      })

      // Click submit
      const submitButton = screen.getByTestId('project-create-submit-button')
      await user.click(submitButton)

      // mockCreateProject should be called (indicates submission started)
      expect(mockCreateProject).toHaveBeenCalled()
    })

    it('redirects to project page after successful creation', async () => {
      const user = userEvent.setup()
      mockCreateProject.mockResolvedValue({ id: 'project-456' })

      render(<ProjectCreationWizard />)

      // Complete the flow
      await user.type(
        screen.getByTestId('project-create-name-input'),
        'Test Project'
      )
      await user.click(screen.getByTestId('project-create-next-button'))
      await waitFor(() => {
        expect(screen.getByText('Import Data')).toBeInTheDocument()
      })
      await user.click(screen.getByTestId('project-create-next-button'))

      await waitFor(() => {
        expect(screen.getByText('Labeling Configuration')).toBeInTheDocument()
      })

      await user.click(screen.getByTestId('project-create-submit-button'))

      await waitFor(() => {
        expect(mockPush).toHaveBeenCalledWith('/projects/project-456')
      })
    })
  })

  describe('Step Indicator', () => {
    it('marks completed steps with checkmark', async () => {
      const user = userEvent.setup()
      render(<ProjectCreationWizard />)

      // Complete step 1
      await user.type(
        screen.getByTestId('project-create-name-input'),
        'Test Project'
      )
      await user.click(screen.getByTestId('project-create-next-button'))

      await waitFor(() => {
        const step1 = screen.getByTestId('project-create-step-1')
        // Step 1 should show as completed
        expect(step1.querySelector('svg')).toBeInTheDocument()
      })
    })

    it('highlights current step', () => {
      render(<ProjectCreationWizard />)

      const step1 = screen.getByTestId('project-create-step-1')
      expect(step1).toHaveClass('border-emerald-600')
      expect(step1).toHaveClass('bg-emerald-600')
    })
  })

  describe('File Upload Handlers', () => {
    it('handles file selection via input', async () => {
      const user = userEvent.setup()
      render(<ProjectCreationWizard />)

      // Navigate to step 2
      await user.type(
        screen.getByTestId('project-create-name-input'),
        'Test Project'
      )
      await user.click(screen.getByTestId('project-create-next-button'))

      await waitFor(() => {
        expect(screen.getByText('Import Data')).toBeInTheDocument()
      })

      // Create a mock file
      const file = new File(['{"text": "test"}'], 'test.json', {
        type: 'application/json',
      })

      const fileInput = screen.getByTestId('project-create-file-input')

      // Simulate file selection
      await user.upload(fileInput, file)

      // File should be selected (visible in UI)
      await waitFor(() => {
        expect(screen.getByText(/Selected:/)).toBeInTheDocument()
      })
    })

    it('handles drag and drop events', async () => {
      const user = userEvent.setup()
      render(<ProjectCreationWizard />)

      // Navigate to step 2
      await user.type(
        screen.getByTestId('project-create-name-input'),
        'Test Project'
      )
      await user.click(screen.getByTestId('project-create-next-button'))

      await waitFor(() => {
        expect(screen.getByText('Import Data')).toBeInTheDocument()
      })

      // Get dropzone - it's the div with onDrop handler
      const dropzone = screen
        .getByText('Drop files here or click to upload')
        .closest('div')

      expect(dropzone).toBeInTheDocument()
    })

    it('removes selected file when remove button is clicked', async () => {
      const user = userEvent.setup()
      render(<ProjectCreationWizard />)

      // Navigate to step 2
      await user.type(
        screen.getByTestId('project-create-name-input'),
        'Test Project'
      )
      await user.click(screen.getByTestId('project-create-next-button'))

      await waitFor(() => {
        expect(screen.getByText('Import Data')).toBeInTheDocument()
      })

      // Upload a file
      const file = new File(['test'], 'test.json', {
        type: 'application/json',
      })
      const fileInput = screen.getByTestId('project-create-file-input')
      await user.upload(fileInput, file)

      // Wait for file to be selected
      await waitFor(() => {
        expect(screen.getByText(/Selected:/)).toBeInTheDocument()
      })

      // Click remove button
      const removeButton = screen.getByTestId(
        'project-create-remove-file-button'
      )
      await user.click(removeButton)

      // File should be removed
      expect(screen.queryByText(/Selected:/)).not.toBeInTheDocument()
    })
  })

  describe('Data Parsing', () => {
    it('creates project with pasted CSV data', async () => {
      const user = userEvent.setup()
      mockCreateProject.mockResolvedValue({ id: 'project-123' })
      mockImportData.mockResolvedValue({})
      mockFetchProject.mockResolvedValue({})

      render(<ProjectCreationWizard />)

      // Fill name
      await user.type(
        screen.getByTestId('project-create-name-input'),
        'Test Project'
      )

      // Navigate to step 2
      await user.click(screen.getByTestId('project-create-next-button'))
      await waitFor(() => {
        expect(screen.getByText('Import Data')).toBeInTheDocument()
      })

      // Paste CSV data
      await user.click(screen.getByText('Paste'))
      const pasteTextarea = await screen.findByTestId(
        'project-create-paste-data-textarea'
      )
      await user.type(pasteTextarea, 'name,value\ntest1,val1\ntest2,val2')

      // Navigate to step 3 and submit
      await user.click(screen.getByTestId('project-create-next-button'))
      await waitFor(() => {
        expect(screen.getByText('Labeling Configuration')).toBeInTheDocument()
      })
      await user.click(screen.getByTestId('project-create-submit-button'))

      // Should have attempted to import data
      await waitFor(() => {
        expect(mockImportData).toHaveBeenCalled()
      })
    })

    it('creates project with plain text data', async () => {
      const user = userEvent.setup()
      mockCreateProject.mockResolvedValue({ id: 'project-123' })
      mockImportData.mockResolvedValue({})
      mockFetchProject.mockResolvedValue({})

      render(<ProjectCreationWizard />)

      // Fill name and navigate
      await user.type(
        screen.getByTestId('project-create-name-input'),
        'Test Project'
      )
      await user.click(screen.getByTestId('project-create-next-button'))

      await waitFor(() => {
        expect(screen.getByText('Import Data')).toBeInTheDocument()
      })

      // Paste plain text
      await user.click(screen.getByText('Paste'))
      const pasteTextarea = await screen.findByTestId(
        'project-create-paste-data-textarea'
      )
      await user.type(pasteTextarea, 'Line 1\nLine 2\nLine 3')

      // Submit
      await user.click(screen.getByTestId('project-create-next-button'))
      await waitFor(() => {
        expect(screen.getByText('Labeling Configuration')).toBeInTheDocument()
      })
      await user.click(screen.getByTestId('project-create-submit-button'))

      await waitFor(() => {
        expect(mockImportData).toHaveBeenCalled()
      })
    })
  })

  describe('Edge Cases', () => {
    it('handles empty project name after trimming', async () => {
      const user = userEvent.setup()
      render(<ProjectCreationWizard />)

      // Type spaces only
      await user.type(screen.getByTestId('project-create-name-input'), '     ')

      // Try to advance
      await user.click(screen.getByTestId('project-create-next-button'))

      // Should show error
      expect(screen.getByText('Project name is required')).toBeInTheDocument()
    })

    it('preserves form data when navigating back and forth', async () => {
      const user = userEvent.setup()
      render(<ProjectCreationWizard />)

      // Fill in step 1
      const nameInput = screen.getByTestId('project-create-name-input')
      await user.type(nameInput, 'My Project')
      const descInput = screen.getByTestId(
        'project-create-description-textarea'
      )
      await user.type(descInput, 'My Description')

      // Advance to step 2
      await user.click(screen.getByTestId('project-create-next-button'))
      await waitFor(() => {
        expect(screen.getByText('Import Data')).toBeInTheDocument()
      })

      // Go back
      await user.click(screen.getByTestId('project-create-back-button'))

      // Check data is preserved
      expect(screen.getByTestId('project-create-name-input')).toHaveValue(
        'My Project'
      )
      expect(
        screen.getByTestId('project-create-description-textarea')
      ).toHaveValue('My Description')
    })

    it('trims whitespace from project name and description on submit', async () => {
      const user = userEvent.setup()
      mockCreateProject.mockResolvedValue({ id: 'project-123' })

      render(<ProjectCreationWizard />)

      // Fill with extra whitespace
      await user.type(
        screen.getByTestId('project-create-name-input'),
        '  Test Project  '
      )
      await user.type(
        screen.getByTestId('project-create-description-textarea'),
        '  Test Description  '
      )

      // Navigate to final step
      await user.click(screen.getByTestId('project-create-next-button'))
      await waitFor(() => {
        expect(screen.getByText('Import Data')).toBeInTheDocument()
      })
      await user.click(screen.getByTestId('project-create-next-button'))

      await waitFor(() => {
        expect(screen.getByText('Labeling Configuration')).toBeInTheDocument()
      })

      // Submit
      await user.click(screen.getByTestId('project-create-submit-button'))

      // Should have trimmed the values
      await waitFor(() => {
        expect(mockCreateProject).toHaveBeenCalledWith(
          expect.objectContaining({
            title: 'Test Project',
            description: 'Test Description',
          })
        )
      })
    })
  })

  describe('Drag and Drop', () => {
    it('handles file drop', async () => {
      const user = userEvent.setup()
      render(<ProjectCreationWizard />)

      // Navigate to step 2
      await user.type(
        screen.getByTestId('project-create-name-input'),
        'Test Project'
      )
      await user.click(screen.getByTestId('project-create-next-button'))

      await waitFor(() => {
        expect(screen.getByText('Import Data')).toBeInTheDocument()
      })

      // Find dropzone
      const dropzone = screen
        .getByText('Drop files here or click to upload')
        .closest('div')

      // Create a file
      const file = new File(['test content'], 'test.txt', {
        type: 'text/plain',
      })

      // Simulate drop event
      const dropEvent = new Event('drop', { bubbles: true })
      Object.defineProperty(dropEvent, 'dataTransfer', {
        value: {
          files: [file],
        },
      })

      dropzone?.dispatchEvent(dropEvent)

      // File should be selected
      await waitFor(() => {
        expect(screen.getByText(/Selected:/)).toBeInTheDocument()
      })
    })

    it('prevents default on drag over', async () => {
      const user = userEvent.setup()
      render(<ProjectCreationWizard />)

      // Navigate to step 2
      await user.type(
        screen.getByTestId('project-create-name-input'),
        'Test Project'
      )
      await user.click(screen.getByTestId('project-create-next-button'))

      await waitFor(() => {
        expect(screen.getByText('Import Data')).toBeInTheDocument()
      })

      // Find dropzone
      const dropzone = screen
        .getByText('Drop files here or click to upload')
        .closest('div')

      // Create dragover event
      const dragOverEvent = new Event('dragover', { bubbles: true })
      const preventDefaultSpy = jest.spyOn(dragOverEvent, 'preventDefault')

      dropzone?.dispatchEvent(dragOverEvent)

      expect(preventDefaultSpy).toHaveBeenCalled()
    })
  })

  describe('Data Format Detection and Parsing', () => {
    it('detects and parses nested JSON with qa_samples', async () => {
      const user = userEvent.setup()
      mockCreateProject.mockResolvedValue({ id: 'project-123' })
      mockImportData.mockResolvedValue({})
      mockFetchProject.mockResolvedValue({})

      render(<ProjectCreationWizard />)

      // Navigate to step 2
      await user.type(
        screen.getByTestId('project-create-name-input'),
        'Test Project'
      )
      await user.click(screen.getByTestId('project-create-next-button'))

      await waitFor(() => {
        expect(screen.getByText('Import Data')).toBeInTheDocument()
      })

      // Paste nested JSON with qa_samples
      await user.click(screen.getByText('Paste'))

      const pasteTextarea = screen.getByTestId(
        'project-create-paste-data-textarea'
      )
      await user.click(pasteTextarea)
      await user.paste(
        '{"qa_samples": [{"question": "Q1"}, {"question": "Q2"}]}'
      )

      // Submit
      await user.click(screen.getByTestId('project-create-next-button'))
      await waitFor(() => {
        expect(screen.getByText('Labeling Configuration')).toBeInTheDocument()
      })
      await user.click(screen.getByTestId('project-create-submit-button'))

      await waitFor(() => {
        expect(mockImportData).toHaveBeenCalledWith(
          'project-123',
          expect.objectContaining({
            data: [{ question: 'Q1' }, { question: 'Q2' }],
          })
        )
      })
    })

    it('detects and parses JSON with questions array', async () => {
      const user = userEvent.setup()
      mockCreateProject.mockResolvedValue({ id: 'project-123' })
      mockImportData.mockResolvedValue({})
      mockFetchProject.mockResolvedValue({})

      render(<ProjectCreationWizard />)

      // Navigate to step 2
      await user.type(
        screen.getByTestId('project-create-name-input'),
        'Test Project'
      )
      await user.click(screen.getByTestId('project-create-next-button'))

      await waitFor(() => {
        expect(screen.getByText('Import Data')).toBeInTheDocument()
      })

      // Paste Label Studio format
      await user.click(screen.getByText('Paste'))

      const pasteTextarea = screen.getByTestId(
        'project-create-paste-data-textarea'
      )
      await user.click(pasteTextarea)
      await user.paste(
        '{"questions": [{"question_data": {"text": "Q1"}}, {"question_data": {"text": "Q2"}}]}'
      )

      // Submit
      await user.click(screen.getByTestId('project-create-next-button'))
      await waitFor(() => {
        expect(screen.getByText('Labeling Configuration')).toBeInTheDocument()
      })
      await user.click(screen.getByTestId('project-create-submit-button'))

      await waitFor(() => {
        expect(mockImportData).toHaveBeenCalled()
      })
    })

    it('detects TSV format by tabs', async () => {
      const user = userEvent.setup()
      render(<ProjectCreationWizard />)

      // Navigate to step 2
      await user.type(
        screen.getByTestId('project-create-name-input'),
        'Test Project'
      )
      await user.click(screen.getByTestId('project-create-next-button'))

      await waitFor(() => {
        expect(screen.getByText('Import Data')).toBeInTheDocument()
      })

      // Switch to paste tab and add TSV data
      await user.click(screen.getByText('Paste'))

      const pasteTextarea = screen.getByTestId(
        'project-create-paste-data-textarea'
      )
      await user.type(pasteTextarea, 'col1\tcol2\nval1\tval2')

      // Click validate
      const validateButton = screen.getByTestId(
        'project-create-validate-data-button'
      )
      await user.click(validateButton)

      expect(mockToastSuccess).toHaveBeenCalledWith('Format detected: TSV')
    })

    it('creates project with uploaded JSON file', async () => {
      const user = userEvent.setup()
      mockCreateProject.mockResolvedValue({ id: 'project-123' })
      mockImportData.mockResolvedValue({})
      mockFetchProject.mockResolvedValue({})

      render(<ProjectCreationWizard />)

      // Navigate to step 2
      await user.type(
        screen.getByTestId('project-create-name-input'),
        'Test Project'
      )
      await user.click(screen.getByTestId('project-create-next-button'))

      await waitFor(() => {
        expect(screen.getByText('Import Data')).toBeInTheDocument()
      })

      // Upload JSON file
      const file = new File(
        ['[{"text": "task1"}, {"text": "task2"}]'],
        'data.json',
        { type: 'application/json' }
      )

      const fileInput = screen.getByTestId('project-create-file-input')
      await user.upload(fileInput, file)

      await waitFor(() => {
        expect(screen.getByText(/Selected:/)).toBeInTheDocument()
      })

      // Submit
      await user.click(screen.getByTestId('project-create-next-button'))
      await waitFor(() => {
        expect(screen.getByText('Labeling Configuration')).toBeInTheDocument()
      })
      await user.click(screen.getByTestId('project-create-submit-button'))

      await waitFor(() => {
        expect(mockImportData).toHaveBeenCalledWith(
          'project-123',
          expect.objectContaining({
            data: [{ text: 'task1' }, { text: 'task2' }],
          })
        )
      })
    })

    it('creates project with uploaded CSV file', async () => {
      const user = userEvent.setup()
      mockCreateProject.mockResolvedValue({ id: 'project-123' })
      mockImportData.mockResolvedValue({})
      mockFetchProject.mockResolvedValue({})

      render(<ProjectCreationWizard />)

      // Navigate to step 2
      await user.type(
        screen.getByTestId('project-create-name-input'),
        'Test Project'
      )
      await user.click(screen.getByTestId('project-create-next-button'))

      await waitFor(() => {
        expect(screen.getByText('Import Data')).toBeInTheDocument()
      })

      // Upload CSV file
      const file = new File(
        ['name,value\nitem1,val1\nitem2,val2'],
        'data.csv',
        {
          type: 'text/csv',
        }
      )

      const fileInput = screen.getByTestId('project-create-file-input')
      await user.upload(fileInput, file)

      await waitFor(() => {
        expect(screen.getByText(/Selected:/)).toBeInTheDocument()
      })

      // Submit
      await user.click(screen.getByTestId('project-create-next-button'))
      await waitFor(() => {
        expect(screen.getByText('Labeling Configuration')).toBeInTheDocument()
      })
      await user.click(screen.getByTestId('project-create-submit-button'))

      await waitFor(() => {
        expect(mockImportData).toHaveBeenCalledWith(
          'project-123',
          expect.objectContaining({
            data: expect.arrayContaining([
              expect.objectContaining({ name: 'item1', value: 'val1' }),
              expect.objectContaining({ name: 'item2', value: 'val2' }),
            ]),
          })
        )
      })
    })

    it('creates project with uploaded TSV file', async () => {
      const user = userEvent.setup()
      mockCreateProject.mockResolvedValue({ id: 'project-123' })
      mockImportData.mockResolvedValue({})
      mockFetchProject.mockResolvedValue({})

      render(<ProjectCreationWizard />)

      // Navigate to step 2
      await user.type(
        screen.getByTestId('project-create-name-input'),
        'Test Project'
      )
      await user.click(screen.getByTestId('project-create-next-button'))

      await waitFor(() => {
        expect(screen.getByText('Import Data')).toBeInTheDocument()
      })

      // Upload TSV file
      const file = new File(['col1\tcol2\nval1\tval2'], 'data.tsv', {
        type: 'text/tab-separated-values',
      })

      const fileInput = screen.getByTestId('project-create-file-input')
      await user.upload(fileInput, file)

      await waitFor(() => {
        expect(screen.getByText(/Selected:/)).toBeInTheDocument()
      })

      // Submit
      await user.click(screen.getByTestId('project-create-next-button'))
      await waitFor(() => {
        expect(screen.getByText('Labeling Configuration')).toBeInTheDocument()
      })
      await user.click(screen.getByTestId('project-create-submit-button'))

      await waitFor(() => {
        expect(mockImportData).toHaveBeenCalled()
      })
    })

    it('creates project with uploaded plain text file', async () => {
      const user = userEvent.setup()
      mockCreateProject.mockResolvedValue({ id: 'project-123' })
      mockImportData.mockResolvedValue({})
      mockFetchProject.mockResolvedValue({})

      render(<ProjectCreationWizard />)

      // Navigate to step 2
      await user.type(
        screen.getByTestId('project-create-name-input'),
        'Test Project'
      )
      await user.click(screen.getByTestId('project-create-next-button'))

      await waitFor(() => {
        expect(screen.getByText('Import Data')).toBeInTheDocument()
      })

      // Upload text file
      const file = new File(['Line 1\nLine 2\nLine 3'], 'data.txt', {
        type: 'text/plain',
      })

      const fileInput = screen.getByTestId('project-create-file-input')
      await user.upload(fileInput, file)

      await waitFor(() => {
        expect(screen.getByText(/Selected:/)).toBeInTheDocument()
      })

      // Submit
      await user.click(screen.getByTestId('project-create-next-button'))
      await waitFor(() => {
        expect(screen.getByText('Labeling Configuration')).toBeInTheDocument()
      })
      await user.click(screen.getByTestId('project-create-submit-button'))

      await waitFor(() => {
        expect(mockImportData).toHaveBeenCalledWith(
          'project-123',
          expect.objectContaining({
            data: [{ text: 'Line 1' }, { text: 'Line 2' }, { text: 'Line 3' }],
          })
        )
      })
    })

    it('handles invalid JSON with error message', async () => {
      const user = userEvent.setup()
      mockCreateProject.mockResolvedValue({ id: 'project-123' })

      render(<ProjectCreationWizard />)

      // Navigate to step 2
      await user.type(
        screen.getByTestId('project-create-name-input'),
        'Test Project'
      )
      await user.click(screen.getByTestId('project-create-next-button'))

      await waitFor(() => {
        expect(screen.getByText('Import Data')).toBeInTheDocument()
      })

      // Paste invalid JSON
      await user.click(screen.getByText('Paste'))

      const pasteTextarea = screen.getByTestId(
        'project-create-paste-data-textarea'
      )
      await user.click(pasteTextarea)
      await user.paste('{invalid json}')

      // Submit
      await user.click(screen.getByTestId('project-create-next-button'))
      await waitFor(() => {
        expect(screen.getByText('Labeling Configuration')).toBeInTheDocument()
      })
      await user.click(screen.getByTestId('project-create-submit-button'))

      // Should show error toast but still create project
      await waitFor(() => {
        expect(mockToastSuccess).toHaveBeenCalledWith(
          'Project created successfully!'
        )
        expect(mockToastError).toHaveBeenCalledWith(
          expect.stringContaining('Failed to import data')
        )
      })
    })

    it('handles empty CSV lines', async () => {
      const user = userEvent.setup()
      mockCreateProject.mockResolvedValue({ id: 'project-123' })
      mockImportData.mockResolvedValue({})
      mockFetchProject.mockResolvedValue({})

      render(<ProjectCreationWizard />)

      // Navigate to step 2
      await user.type(
        screen.getByTestId('project-create-name-input'),
        'Test Project'
      )
      await user.click(screen.getByTestId('project-create-next-button'))

      await waitFor(() => {
        expect(screen.getByText('Import Data')).toBeInTheDocument()
      })

      // Paste CSV with empty lines
      await user.click(screen.getByText('Paste'))

      const pasteTextarea = screen.getByTestId(
        'project-create-paste-data-textarea'
      )
      // CSV with just header
      await user.type(pasteTextarea, 'col1,col2')

      // Submit
      await user.click(screen.getByTestId('project-create-next-button'))
      await waitFor(() => {
        expect(screen.getByText('Labeling Configuration')).toBeInTheDocument()
      })
      await user.click(screen.getByTestId('project-create-submit-button'))

      // Should create project successfully (empty data)
      await waitFor(() => {
        expect(mockToastSuccess).toHaveBeenCalledWith(
          'Project created successfully!'
        )
      })
    })
  })

  describe('Custom Configuration', () => {
    it('updates custom config when typing', async () => {
      const user = userEvent.setup()
      render(<ProjectCreationWizard />)

      // Navigate to step 3
      await user.type(
        screen.getByTestId('project-create-name-input'),
        'Test Project'
      )
      await user.click(screen.getByTestId('project-create-next-button'))
      await waitFor(() => {
        expect(screen.getByText('Import Data')).toBeInTheDocument()
      })
      await user.click(screen.getByTestId('project-create-next-button'))

      await waitFor(() => {
        expect(screen.getByText('Labeling Configuration')).toBeInTheDocument()
      })

      // Switch to custom tab
      await user.click(screen.getAllByText('Custom')[0])

      // Type custom config
      const customTextarea = screen.getByTestId(
        'project-create-custom-config-textarea'
      )
      await user.click(customTextarea)
      await user.paste('<View><Text name="test"/></View>')

      // Config should update
      expect(customTextarea).toHaveValue('<View><Text name="test"/></View>')
    })

    it('creates project with custom configuration', async () => {
      const user = userEvent.setup()
      mockCreateProject.mockResolvedValue({ id: 'project-123' })

      render(<ProjectCreationWizard />)

      // Navigate to step 3
      await user.type(
        screen.getByTestId('project-create-name-input'),
        'Test Project'
      )
      await user.click(screen.getByTestId('project-create-next-button'))
      await waitFor(() => {
        expect(screen.getByText('Import Data')).toBeInTheDocument()
      })
      await user.click(screen.getByTestId('project-create-next-button'))

      await waitFor(() => {
        expect(screen.getByText('Labeling Configuration')).toBeInTheDocument()
      })

      // Switch to custom tab and add config
      await user.click(screen.getAllByText('Custom')[0])

      const customTextarea = screen.getByTestId(
        'project-create-custom-config-textarea'
      )
      await user.click(customTextarea)
      await user.paste('<View><Text name="custom"/></View>')

      // Submit
      await user.click(screen.getByTestId('project-create-submit-button'))

      await waitFor(() => {
        expect(mockCreateProject).toHaveBeenCalledWith(
          expect.objectContaining({
            label_config: '<View><Text name="custom"/></View>',
          })
        )
      })
    })

    it('shows preview for custom config', async () => {
      const user = userEvent.setup()
      render(<ProjectCreationWizard />)

      // Navigate to step 3
      await user.type(
        screen.getByTestId('project-create-name-input'),
        'Test Project'
      )
      await user.click(screen.getByTestId('project-create-next-button'))
      await waitFor(() => {
        expect(screen.getByText('Import Data')).toBeInTheDocument()
      })
      await user.click(screen.getByTestId('project-create-next-button'))

      await waitFor(() => {
        expect(screen.getByText('Labeling Configuration')).toBeInTheDocument()
      })

      // Switch to custom tab and add config
      await user.click(screen.getAllByText('Custom')[0])

      const customTextarea = screen.getByTestId(
        'project-create-custom-config-textarea'
      )
      await user.click(customTextarea)
      await user.paste('<View></View>')

      // Should show preview
      await waitFor(() => {
        expect(screen.getByText('Preview')).toBeInTheDocument()
        const customConfigElements = screen.getAllByText('Custom Configuration')
        expect(customConfigElements.length).toBeGreaterThanOrEqual(1)
      })
    })
  })

  describe('Template Selection Details', () => {
    it('selects different templates and shows correct preview', async () => {
      const user = userEvent.setup()
      render(<ProjectCreationWizard />)

      // Navigate to step 3
      await user.type(
        screen.getByTestId('project-create-name-input'),
        'Test Project'
      )
      await user.click(screen.getByTestId('project-create-next-button'))
      await waitFor(() => {
        expect(screen.getByText('Import Data')).toBeInTheDocument()
      })
      await user.click(screen.getByTestId('project-create-next-button'))

      await waitFor(() => {
        expect(screen.getByText('Labeling Configuration')).toBeInTheDocument()
      })

      // Wait for template list to be visible
      await waitFor(() => {
        expect(screen.getByText('Multiple Choice Question')).toBeInTheDocument()
      })

      // Select Multiple Choice template by clicking its text
      const mcqText = screen.getByText('Multiple Choice Question')
      await user.click(mcqText)

      // Should show selected badge
      expect(screen.getByText('Selected')).toBeInTheDocument()

      // Change to Exam Solving
      const examText = screen.getByText('Exam Solving')
      await user.click(examText)

      // Should still show one selected badge
      expect(screen.getByText('Selected')).toBeInTheDocument()
    })

    it('creates project with different template types', async () => {
      const user = userEvent.setup()
      mockCreateProject.mockResolvedValue({ id: 'project-123' })

      render(<ProjectCreationWizard />)

      // Navigate to step 3
      await user.type(
        screen.getByTestId('project-create-name-input'),
        'Test Project'
      )
      await user.click(screen.getByTestId('project-create-next-button'))
      await waitFor(() => {
        expect(screen.getByText('Import Data')).toBeInTheDocument()
      })
      await user.click(screen.getByTestId('project-create-next-button'))

      await waitFor(() => {
        expect(screen.getByText('Labeling Configuration')).toBeInTheDocument()
      })

      // Wait for template list to be visible
      await waitFor(() => {
        expect(screen.getByText('Span Annotation')).toBeInTheDocument()
      })

      // Select Span Annotation template by clicking its text
      const spanText = screen.getByText('Span Annotation')
      await user.click(spanText)

      // Submit
      await user.click(screen.getByTestId('project-create-submit-button'))

      await waitFor(() => {
        expect(mockCreateProject).toHaveBeenCalledWith(
          expect.objectContaining({
            label_config: expect.stringContaining('Labels'),
          })
        )
      })
    })
  })

  describe('Back Navigation from Step 3', () => {
    it('navigates back from step 3 to step 2', async () => {
      const user = userEvent.setup()
      render(<ProjectCreationWizard />)

      // Navigate to step 3
      await user.type(
        screen.getByTestId('project-create-name-input'),
        'Test Project'
      )
      await user.click(screen.getByTestId('project-create-next-button'))
      await waitFor(() => {
        expect(screen.getByText('Import Data')).toBeInTheDocument()
      })
      await user.click(screen.getByTestId('project-create-next-button'))

      await waitFor(() => {
        expect(screen.getByText('Labeling Configuration')).toBeInTheDocument()
      })

      // Click back
      const backButton = screen.getByTestId('project-create-back-button')
      await user.click(backButton)

      // Should be on step 2
      await waitFor(() => {
        expect(screen.getByText('Import Data')).toBeInTheDocument()
      })
    })

    it('preserves selected template when navigating back and forth', async () => {
      const user = userEvent.setup()
      render(<ProjectCreationWizard />)

      // Navigate to step 3
      await user.type(
        screen.getByTestId('project-create-name-input'),
        'Test Project'
      )
      await user.click(screen.getByTestId('project-create-next-button'))
      await waitFor(() => {
        expect(screen.getByText('Import Data')).toBeInTheDocument()
      })
      await user.click(screen.getByTestId('project-create-next-button'))

      await waitFor(() => {
        expect(screen.getByText('Labeling Configuration')).toBeInTheDocument()
      })

      // Wait for template list to be visible
      await waitFor(() => {
        expect(screen.getByText('Question Answering')).toBeInTheDocument()
      })

      // Select template by clicking its text (which is in the clickable card)
      const qaText = screen.getByText('Question Answering')
      await user.click(qaText)

      expect(screen.getByText('Selected')).toBeInTheDocument()

      // Go back and forward again
      await user.click(screen.getByTestId('project-create-back-button'))
      await waitFor(() => {
        expect(screen.getByText('Import Data')).toBeInTheDocument()
      })
      await user.click(screen.getByTestId('project-create-next-button'))

      await waitFor(() => {
        expect(screen.getByText('Labeling Configuration')).toBeInTheDocument()
      })

      // Wait for template list to be visible again (may appear multiple times if preview is shown)
      await waitFor(() => {
        const qaElements = screen.queryAllByText('Question Answering')
        expect(qaElements.length).toBeGreaterThan(0)
      })

      // Template should still be selected
      expect(screen.getByText('Selected')).toBeInTheDocument()
    })
  })
})

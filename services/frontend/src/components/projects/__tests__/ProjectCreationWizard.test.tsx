/**
 * Tests for ProjectCreationWizard with dynamic feature-based steps
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
        // Step names
        'projects.creation.wizard.steps.projectInfo.name': 'Project Info',
        'projects.creation.wizard.steps.projectInfo.description':
          'Basic information',
        'projects.creation.wizard.steps.dataImport.name': 'Data Import',
        'projects.creation.wizard.steps.dataImport.description': 'Upload data',
        'projects.creation.wizard.steps.labelingSetup.name': 'Labeling Setup',
        'projects.creation.wizard.steps.labelingSetup.description':
          'Configure labels',
        'projects.creation.wizard.steps.annotationInstructions.name':
          'Instructions',
        'projects.creation.wizard.steps.annotationInstructions.description':
          'Annotation instructions',
        'projects.creation.wizard.steps.models.name': 'Models',
        'projects.creation.wizard.steps.models.description': 'Select models',
        'projects.creation.wizard.steps.prompts.name': 'Prompts',
        'projects.creation.wizard.steps.prompts.description':
          'Configure prompts',
        'projects.creation.wizard.steps.evaluation.name': 'Evaluation',
        'projects.creation.wizard.steps.evaluation.description':
          'Select metrics',
        'projects.creation.wizard.steps.settings.name': 'Settings',
        'projects.creation.wizard.steps.settings.description':
          'Configure settings',
        // Step 1
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
        // Features
        'projects.creation.wizard.features.title': 'Project Features',
        'projects.creation.wizard.features.editLater': 'Can be edited later',
        'projects.creation.wizard.features.annotation': 'Annotation',
        'projects.creation.wizard.features.annotationDescription':
          'Labels and instructions',
        'projects.creation.wizard.features.dataImport': 'Data Import',
        'projects.creation.wizard.features.dataImportDescription':
          'Upload or paste data',
        'projects.creation.wizard.features.llmGeneration': 'LLM Generation',
        'projects.creation.wizard.features.llmGenerationDescription':
          'Models and prompts',
        'projects.creation.wizard.features.evaluation': 'Evaluation',
        'projects.creation.wizard.features.evaluationDescription':
          'Metrics and methods',
        // Step 2 (data import)
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
        // Step 3 (labeling)
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
        // Step 4 (instructions)
        'projects.creation.wizard.step4.title': 'Annotation Instructions',
        'projects.creation.wizard.step4.subtitle':
          'Provide instructions for annotators',
        'projects.creation.wizard.step4.instructionsLabel':
          'General Instructions',
        'projects.creation.wizard.step4.instructionsPlaceholder':
          'Enter instructions...',
        'projects.creation.wizard.step4.variantsTitle': 'Conditional Variants',
        'projects.creation.wizard.step4.variantsDescription':
          'Define variants for A/B testing',
        'projects.creation.wizard.step4.variant': 'Variant',
        'projects.creation.wizard.step4.variantId': 'Variant ID',
        'projects.creation.wizard.step4.variantWeight': 'Weight',
        'projects.creation.wizard.step4.variantContent': 'Content',
        'projects.creation.wizard.step4.variantContentPlaceholder':
          'Instructions for this variant...',
        'projects.creation.wizard.step4.aiAllowed': 'AI assistance allowed',
        'projects.creation.wizard.step4.weightError': `Weights must sum to 100% (currently ${params?.sum}%)`,
        'projects.creation.wizard.step4.addVariant': 'Add Variant',
        // Step 5 (models)
        'projects.creation.wizard.step5.title': 'Select LLM Models',
        'projects.creation.wizard.step5.subtitle':
          'Choose models for generation',
        'projects.creation.wizard.step5.loading': 'Loading models...',
        'projects.creation.wizard.step5.noApiKeys': 'No API keys configured',
        'projects.creation.wizard.step5.noApiKeysHint':
          'Configure API keys in settings',
        'projects.creation.wizard.step5.selectedCount': `${params?.count} of ${params?.total} selected`,
        'projects.creation.wizard.step5.temperature': 'Temperature',
        'projects.creation.wizard.step5.maxTokens': 'Max Tokens',
        // Step 6 (prompts)
        'projects.creation.wizard.step6.title': 'Configure Prompts',
        'projects.creation.wizard.step6.subtitle': 'Set up generation prompts',
        'projects.creation.wizard.step6.systemPromptLabel': 'System Prompt',
        'projects.creation.wizard.step6.systemPromptHint':
          'Defines AI role and behavior',
        'projects.creation.wizard.step6.systemPromptPlaceholder':
          'You are a legal expert...',
        'projects.creation.wizard.step6.instructionPromptLabel':
          'Instruction Prompt',
        'projects.creation.wizard.step6.instructionPromptHint':
          'Instructions for the task',
        'projects.creation.wizard.step6.instructionPromptPlaceholder':
          'Given the following text...',
        'projects.creation.wizard.step6.templateVarsTitle':
          'Template variables:',
        'projects.creation.wizard.step6.templateVarsHint':
          'Use $field_name syntax',
        // Step 7 (evaluation)
        'projects.creation.wizard.step7.title': 'Evaluation Setup',
        'projects.creation.wizard.step7.subtitle': 'Select evaluation metrics',
        'projects.creation.wizard.step7.advancedNote':
          'Advanced configuration available on project page.',
        'projects.creation.wizard.stepSettings.title': 'Project Settings',
        'projects.creation.wizard.stepSettings.subtitle': 'Configure settings',
        'projects.creation.wizard.stepSettings.assignmentMode': 'Assignment Mode',
        'projects.creation.wizard.stepSettings.assignmentModeHint': 'How tasks are distributed',
        'projects.creation.wizard.stepSettings.modes.open': 'Open',
        'projects.creation.wizard.stepSettings.modes.manual': 'Manual',
        'projects.creation.wizard.stepSettings.modes.auto': 'Auto',
        'projects.creation.wizard.stepSettings.modesHint.open': 'Annotators pick freely',
        'projects.creation.wizard.stepSettings.modesHint.manual': 'Admins assign tasks',
        'projects.creation.wizard.stepSettings.modesHint.auto': 'Auto-assigned',
        'projects.creation.wizard.stepSettings.maxAnnotations': 'Max Annotations',
        'projects.creation.wizard.stepSettings.minAnnotations': 'Min Annotations',
        'projects.creation.wizard.stepSettings.unlimited': 'Unlimited',
        'projects.creation.wizard.stepSettings.showSkipButton': 'Show Skip Button',
        'projects.creation.wizard.stepSettings.showSkipButtonHint': 'Allow skipping tasks',
        'projects.creation.wizard.stepSettings.showInstructions': 'Show Instructions',
        'projects.creation.wizard.stepSettings.showInstructionsHint': 'Display instructions',
        'projects.creation.wizard.stepSettings.randomizeOrder': 'Randomize Order',
        'projects.creation.wizard.stepSettings.randomizeOrderHint': 'Random task order',
        'projects.creation.wizard.stepSettings.advancedNote': 'Additional settings available on project page.',
        'projects.creation.wizard.evalSaveFailed':
          'Failed to save evaluation config',
        // Templates
        'projects.creation.wizard.templates.questionAnswering.name':
          'Question Answering',
        'projects.creation.wizard.templates.questionAnswering.description':
          'Answer questions',
        'projects.creation.wizard.templates.multipleChoice.name':
          'Multiple Choice Question',
        'projects.creation.wizard.templates.multipleChoice.description':
          'Select from options',
        'projects.creation.wizard.templates.examSolving.name': 'Exam Solving',
        'projects.creation.wizard.templates.examSolving.description':
          'German legal exam format',
        'projects.creation.wizard.templates.spanAnnotation.name':
          'Span Annotation',
        'projects.creation.wizard.templates.spanAnnotation.description':
          'Highlight text spans',
        'projects.creation.wizard.templates.custom.name': 'Custom',
        'projects.creation.wizard.templates.custom.description':
          'Custom configuration',
        // Navigation
        'projects.creation.wizard.navigation.cancel': 'Cancel',
        'projects.creation.wizard.navigation.back': 'Back',
        'projects.creation.wizard.navigation.next': 'Next',
        'projects.creation.wizard.navigation.skip': 'Skip',
        'projects.creation.wizard.navigation.create': 'Create Project',
        'projects.creation.wizard.navigation.creating': 'Creating...',
        // Wizard messages
        'projects.wizard.projectCreatedWithTasks': `Project created with ${params?.count} tasks!`,
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
    update: jest.fn(),
  },
}))

// Mock API client
jest.mock('@/lib/api/client', () => ({
  apiClient: {
    put: jest.fn(),
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

// Mock useModels hook
jest.mock('@/hooks/useModels', () => ({
  useModels: () => ({
    models: [
      {
        id: 'gpt-4',
        name: 'GPT-4',
        provider: 'openai',
        model_type: 'chat',
        capabilities: [],
        is_active: true,
        created_at: null,
        parameter_constraints: {
          temperature: { min: 0, max: 2, default: 0.7 },
          max_tokens: { min: 1, max: 32768, default: 4096 },
        },
      },
      {
        id: 'claude-3-sonnet',
        name: 'Claude 3 Sonnet',
        provider: 'anthropic',
        model_type: 'chat',
        capabilities: [],
        is_active: true,
        created_at: null,
        parameter_constraints: {
          temperature: { min: 0, max: 1, default: 0.7 },
          max_tokens: { min: 1, max: 200000, default: 4096 },
        },
      },
    ],
    loading: false,
    error: null,
    refetch: jest.fn(),
    hasApiKeys: true,
    apiKeyStatus: null,
  }),
  default: () => ({}),
}))

// Mock toast — ProjectCreationWizard uses the app's useToast() hook.
const mockToastSuccessFn = jest.fn()
const mockToastErrorFn = jest.fn()
const mockAddToastFn = jest.fn(
  (message: string, type: 'success' | 'error' | 'info' | 'warning' = 'info') => {
    if (type === 'success') mockToastSuccessFn(message)
    if (type === 'error') mockToastErrorFn(message)
    return 'mock-toast-id'
  }
)
jest.mock('@/components/shared/Toast', () => ({
  useToast: () => ({
    addToast: mockAddToastFn,
    showToast: mockAddToastFn,
    removeToast: jest.fn(),
  }),
  ToastProvider: ({ children }: { children: React.ReactNode }) => children,
}))
// Helper to enable features on step 1
async function enableFeature(
  user: ReturnType<typeof userEvent.setup>,
  featureKey: string
) {
  const wrapper = screen.getByTestId(`wizard-feature-${featureKey}`)
  const checkbox = wrapper.querySelector('input[type="checkbox"]')!
  await user.click(checkbox)
}

// Helper to navigate to a specific step by enabling features and clicking Next
async function navigateToStep(
  user: ReturnType<typeof userEvent.setup>,
  stepId: string,
  projectName = 'Test Project'
) {
  // Fill in name
  await user.type(
    screen.getByTestId('project-create-name-input'),
    projectName
  )

  // Enable features based on target step
  const featureMap: Record<string, string[]> = {
    labelingSetup: ['annotation'],
    annotationInstructions: ['annotation'],
    dataImport: ['dataImport'],
    models: ['llmGeneration'],
    prompts: ['llmGeneration'],
    evaluation: ['evaluation'],
  }

  const features = featureMap[stepId] || []
  for (const feature of features) {
    await enableFeature(user, feature)
  }

  // Click Next until we reach the target step
  let found = false
  for (let i = 0; i < 10 && !found; i++) {
    const nextButton = screen.queryByTestId('project-create-next-button')
    const submitButton = screen.queryByTestId('project-create-submit-button')

    if (!nextButton && !submitButton) break

    // Check if we're on the right step by looking for its title
    const stepTitles: Record<string, string> = {
      labelingSetup: 'Labeling Configuration',
      annotationInstructions: 'Annotation Instructions',
      dataImport: 'Import Data',
      models: 'Select LLM Models',
      prompts: 'Configure Prompts',
      evaluation: 'Evaluation Setup',
    }

    const title = stepTitles[stepId]
    if (title && screen.queryByText(title)) {
      found = true
      break
    }

    if (nextButton) {
      await user.click(nextButton)
      await waitFor(() => {})
    } else {
      break
    }
  }
}

describe('ProjectCreationWizard', () => {
  let mockImportData: jest.Mock
  let mockUpdate: jest.Mock
  let mockApiClientPut: jest.Mock
  let mockToastSuccess: jest.Mock
  let mockToastError: jest.Mock

  beforeEach(() => {
    jest.clearAllMocks()
    const projectsAPI = require('@/lib/api/projects').projectsAPI
    mockImportData = projectsAPI.importData as jest.Mock
    mockUpdate = projectsAPI.update as jest.Mock
    mockUpdate.mockResolvedValue({})

    const { apiClient } = require('@/lib/api/client')
    mockApiClientPut = apiClient.put as jest.Mock
    mockApiClientPut.mockResolvedValue({})

    // Wire mockToastSuccess / mockToastError to the new useToast-based
    // mock declared at the top of the file. Keeps existing assertions on
    // mockToastSuccess / mockToastError working without rewriting them.
    mockToastSuccess = mockToastSuccessFn
    mockToastError = mockToastErrorFn
  })

  describe('Wizard Initialization', () => {
    it('renders with step 1 active', () => {
      render(<ProjectCreationWizard />)
      expect(screen.getByText('Project Information')).toBeInTheDocument()
    })

    it('shows step 1 and settings when no features are checked', () => {
      render(<ProjectCreationWizard />)

      // Info + Settings = 2 step dots
      expect(screen.getByTestId('wizard-step-dot-1')).toBeInTheDocument()
      expect(screen.getByTestId('wizard-step-dot-2')).toBeInTheDocument()
      expect(screen.queryByTestId('wizard-step-dot-3')).not.toBeInTheDocument()
    })

    it('renders project name input and description textarea', () => {
      render(<ProjectCreationWizard />)
      expect(screen.getByTestId('project-create-name-input')).toHaveValue('')
      expect(
        screen.getByTestId('project-create-description-textarea')
      ).toHaveValue('')
    })

    it('renders feature checkboxes', () => {
      render(<ProjectCreationWizard />)
      expect(screen.getByText(/Project Features/)).toBeInTheDocument()
      expect(screen.getByText(/Can be edited later/)).toBeInTheDocument()
      expect(screen.getByTestId('wizard-feature-annotation')).toBeInTheDocument()
      expect(screen.getByTestId('wizard-feature-dataImport')).toBeInTheDocument()
      expect(
        screen.getByTestId('wizard-feature-llmGeneration')
      ).toBeInTheDocument()
      expect(screen.getByTestId('wizard-feature-evaluation')).toBeInTheDocument()
    })

    it('shows Next button on step 1 leading to Settings step', async () => {
      const user = userEvent.setup()
      render(<ProjectCreationWizard />)

      await user.type(
        screen.getByTestId('project-create-name-input'),
        'Test'
      )

      // With no features, step 1 has Next (Settings is step 2)
      expect(
        screen.getByTestId('project-create-next-button')
      ).toBeInTheDocument()
    })
  })

  describe('Dynamic Steps from Feature Checkboxes', () => {
    it('adds labeling + instructions steps when Annotation is checked', async () => {
      const user = userEvent.setup()
      render(<ProjectCreationWizard />)

      await enableFeature(user, 'annotation')

      // Info + Labeling + Instructions + Settings = 4 dots
      for (let i = 1; i <= 4; i++) {
        expect(screen.getByTestId(`wizard-step-dot-${i}`)).toBeInTheDocument()
      }
      expect(screen.queryByTestId('wizard-step-dot-5')).not.toBeInTheDocument()
    })

    it('adds data import step when Data Import is checked', async () => {
      const user = userEvent.setup()
      render(<ProjectCreationWizard />)

      await enableFeature(user, 'dataImport')

      // Info + DataImport + Settings = 3 dots
      expect(screen.getByTestId('wizard-step-dot-3')).toBeInTheDocument()
      expect(screen.queryByTestId('wizard-step-dot-4')).not.toBeInTheDocument()
    })

    it('adds models + prompts steps when LLM Generation is checked', async () => {
      const user = userEvent.setup()
      render(<ProjectCreationWizard />)

      await enableFeature(user, 'llmGeneration')

      // Info + Models + Prompts + Settings = 4 dots
      for (let i = 1; i <= 4; i++) {
        expect(screen.getByTestId(`wizard-step-dot-${i}`)).toBeInTheDocument()
      }
      expect(screen.queryByTestId('wizard-step-dot-5')).not.toBeInTheDocument()
    })

    it('shows all 8 steps when all features are checked', async () => {
      const user = userEvent.setup()
      render(<ProjectCreationWizard />)

      await enableFeature(user, 'annotation')
      await enableFeature(user, 'dataImport')
      await enableFeature(user, 'llmGeneration')
      await enableFeature(user, 'evaluation')

      // 7 feature steps + settings = 8
      for (let i = 1; i <= 8; i++) {
        expect(
          screen.getByTestId(`wizard-step-dot-${i}`)
        ).toBeInTheDocument()
      }
      expect(screen.queryByTestId('wizard-step-dot-9')).not.toBeInTheDocument()
    })

    it('removes steps when features are unchecked', async () => {
      const user = userEvent.setup()
      render(<ProjectCreationWizard />)

      await enableFeature(user, 'annotation')
      // Info + Labeling + Instructions + Settings = 4
      expect(screen.getByTestId('wizard-step-dot-4')).toBeInTheDocument()

      // Uncheck annotation -> Info + Settings = 2
      await enableFeature(user, 'annotation')
      expect(screen.queryByTestId('wizard-step-dot-3')).not.toBeInTheDocument()
    })
  })

  describe('Step Navigation', () => {
    it('advances to labeling step when Annotation is checked', async () => {
      const user = userEvent.setup()
      render(<ProjectCreationWizard />)

      await user.type(
        screen.getByTestId('project-create-name-input'),
        'Test Project'
      )
      await enableFeature(user, 'annotation')

      await user.click(screen.getByTestId('project-create-next-button'))

      await waitFor(() => {
        expect(
          screen.getByText('Labeling Configuration')
        ).toBeInTheDocument()
      })
    })

    it('navigates back preserving state', async () => {
      const user = userEvent.setup()
      render(<ProjectCreationWizard />)

      await user.type(
        screen.getByTestId('project-create-name-input'),
        'My Project'
      )
      await user.type(
        screen.getByTestId('project-create-description-textarea'),
        'My Description'
      )
      await enableFeature(user, 'dataImport')

      await user.click(screen.getByTestId('project-create-next-button'))
      await waitFor(() => {
        expect(screen.getByText('Import Data')).toBeInTheDocument()
      })

      await user.click(screen.getByTestId('project-create-back-button'))

      expect(screen.getByTestId('project-create-name-input')).toHaveValue(
        'My Project'
      )
      expect(
        screen.getByTestId('project-create-description-textarea')
      ).toHaveValue('My Description')
    })

    it('prevents advancing without project name', async () => {
      const user = userEvent.setup()
      render(<ProjectCreationWizard />)

      await enableFeature(user, 'dataImport')
      await user.click(screen.getByTestId('project-create-next-button'))

      expect(screen.getByText('Project name is required')).toBeInTheDocument()
      expect(screen.getByText('Project Information')).toBeInTheDocument()
    })

    it('navigates to projects page on cancel', async () => {
      const user = userEvent.setup()
      render(<ProjectCreationWizard />)

      await user.click(screen.getByTestId('project-create-cancel-button'))
      expect(mockPush).toHaveBeenCalledWith('/projects')
    })
  })

  describe('Data Import Step', () => {
    it('displays upload/paste/cloud tabs', async () => {
      const user = userEvent.setup()
      render(<ProjectCreationWizard />)

      await navigateToStep(user, 'dataImport')

      expect(screen.getByText('Upload')).toBeInTheDocument()
      expect(screen.getByText('Paste')).toBeInTheDocument()
      expect(screen.getByText('Cloud')).toBeInTheDocument()
    })

    it('handles pasted data', async () => {
      const user = userEvent.setup()
      render(<ProjectCreationWizard />)

      await navigateToStep(user, 'dataImport')

      await user.click(screen.getByText('Paste'))
      const textarea = await screen.findByTestId(
        'project-create-paste-data-textarea'
      )
      await user.type(textarea, 'Line 1\nLine 2')

      expect(screen.getByText('2 lines')).toBeInTheDocument()
    })

    it('handles file selection', async () => {
      const user = userEvent.setup()
      render(<ProjectCreationWizard />)

      await navigateToStep(user, 'dataImport')

      const file = new File(['{"text": "test"}'], 'test.json', {
        type: 'application/json',
      })
      const fileInput = screen.getByTestId('project-create-file-input')
      await user.upload(fileInput, file)

      await waitFor(() => {
        expect(screen.getByText(/Selected:/)).toBeInTheDocument()
      })
    })
  })

  describe('Labeling Setup Step', () => {
    it('displays templates', async () => {
      const user = userEvent.setup()
      render(<ProjectCreationWizard />)

      await navigateToStep(user, 'labelingSetup')

      expect(screen.getByText('Question Answering')).toBeInTheDocument()
      expect(
        screen.getByText('Multiple Choice Question')
      ).toBeInTheDocument()
      // 'Exam Solving' (Klausurlösung) is registered by benger-extended via
      // registerWizardTemplate at runtime; not present in the public wizard.
      expect(screen.queryByText('Exam Solving')).not.toBeInTheDocument()
      expect(screen.getByText('Span Annotation')).toBeInTheDocument()
    })

    it('selects template and shows preview', async () => {
      const user = userEvent.setup()
      render(<ProjectCreationWizard />)

      await navigateToStep(user, 'labelingSetup')

      await user.click(screen.getByText('Question Answering'))

      expect(screen.getByText('Selected')).toBeInTheDocument()
      expect(screen.getByText('Preview')).toBeInTheDocument()
    })
  })

  describe('Annotation Instructions Step', () => {
    it('displays instructions textarea', async () => {
      const user = userEvent.setup()
      render(<ProjectCreationWizard />)

      await navigateToStep(user, 'annotationInstructions')

      expect(
        screen.getByText('Annotation Instructions')
      ).toBeInTheDocument()
      expect(
        screen.getByTestId('wizard-instructions-textarea')
      ).toBeInTheDocument()
    })

    it('shows conditional variants section', async () => {
      const user = userEvent.setup()
      render(<ProjectCreationWizard />)

      await navigateToStep(user, 'annotationInstructions')

      const toggle = screen.getByTestId('wizard-variants-toggle')
      await user.click(toggle)

      expect(screen.getByText('Add Variant')).toBeInTheDocument()
    })

    it('adds and configures a variant', async () => {
      const user = userEvent.setup()
      render(<ProjectCreationWizard />)

      await navigateToStep(user, 'annotationInstructions')

      // Open variants section
      await user.click(screen.getByTestId('wizard-variants-toggle'))
      await user.click(screen.getByTestId('wizard-add-variant'))

      expect(screen.getByTestId('wizard-variant-0')).toBeInTheDocument()
    })
  })

  describe('Models Step', () => {
    it('displays available models', async () => {
      const user = userEvent.setup()
      render(<ProjectCreationWizard />)

      await navigateToStep(user, 'models')

      expect(screen.getByText('Select LLM Models')).toBeInTheDocument()
      expect(screen.getByText('GPT-4')).toBeInTheDocument()
      expect(screen.getByText('Claude 3 Sonnet')).toBeInTheDocument()
    })

    it('allows selecting models', async () => {
      const user = userEvent.setup()
      render(<ProjectCreationWizard />)

      await navigateToStep(user, 'models')

      await user.click(screen.getByTestId('wizard-model-gpt-4'))

      expect(screen.getByText(/1 of 2 selected/)).toBeInTheDocument()
    })
  })

  describe('Prompts Step', () => {
    it('displays prompt textareas', async () => {
      const user = userEvent.setup()
      render(<ProjectCreationWizard />)

      await navigateToStep(user, 'prompts')

      expect(screen.getByText('Configure Prompts')).toBeInTheDocument()
      expect(screen.getByTestId('wizard-system-prompt')).toBeInTheDocument()
      expect(
        screen.getByTestId('wizard-instruction-prompt')
      ).toBeInTheDocument()
    })
  })

  describe('Evaluation Step', () => {
    it('displays metric groups', async () => {
      const user = userEvent.setup()
      render(<ProjectCreationWizard />)

      await navigateToStep(user, 'evaluation')

      expect(screen.getByText('Evaluation Setup')).toBeInTheDocument()
      expect(screen.getByText('Lexical Metrics')).toBeInTheDocument()
      expect(screen.getByText('Semantic Metrics')).toBeInTheDocument()
    })

    it('allows selecting metrics', async () => {
      const user = userEvent.setup()
      render(<ProjectCreationWizard />)

      await navigateToStep(user, 'evaluation')

      const bleuRow = screen.getByTestId('wizard-metric-bleu')
      await user.click(bleuRow.querySelector('input[type="checkbox"]')!)

      // Should show badge
      expect(screen.getAllByText('BLEU').length).toBeGreaterThanOrEqual(2)
    })
  })

  describe('Project Creation', () => {
    it('creates bare project when no features checked', async () => {
      const user = userEvent.setup()
      mockCreateProject.mockResolvedValue({ id: 'project-123' })
      mockFetchProject.mockResolvedValue({})

      render(<ProjectCreationWizard />)

      await user.type(
        screen.getByTestId('project-create-name-input'),
        'Bare Project'
      )

      // Navigate to Settings (step 2, always last)
      await user.click(screen.getByTestId('project-create-next-button'))
      await waitFor(() => {
        expect(screen.getByTestId('project-create-submit-button')).toBeInTheDocument()
      })

      await user.click(screen.getByTestId('project-create-submit-button'))

      await waitFor(() => {
        expect(mockCreateProject).toHaveBeenCalledWith(
          expect.objectContaining({
            title: 'Bare Project',
            description: '',
          })
        )
      })

      await waitFor(() => {
        expect(mockPush).toHaveBeenCalledWith('/projects/project-123')
      })
    })

    it('creates project with all configuration when all features are set', async () => {
      const user = userEvent.setup()
      mockCreateProject.mockResolvedValue({ id: 'project-full' })
      mockImportData.mockResolvedValue({})
      mockFetchProject.mockResolvedValue({})

      render(<ProjectCreationWizard />)

      // Step 1: Project info + all features
      await user.type(
        screen.getByTestId('project-create-name-input'),
        'Full Project'
      )
      await enableFeature(user, 'annotation')
      await enableFeature(user, 'dataImport')
      await enableFeature(user, 'llmGeneration')
      await enableFeature(user, 'evaluation')

      // Step 2: Data Import - skip (just advance)
      await user.click(screen.getByTestId('project-create-next-button'))
      await waitFor(() => {
        expect(screen.getByText('Import Data')).toBeInTheDocument()
      })

      // Step 3: Labeling - select template
      await user.click(screen.getByTestId('project-create-next-button'))
      await waitFor(() => {
        expect(
          screen.getByText('Labeling Configuration')
        ).toBeInTheDocument()
      })
      await user.click(screen.getByText('Question Answering'))

      // Step 4: Instructions
      await user.click(screen.getByTestId('project-create-next-button'))
      await waitFor(() => {
        expect(
          screen.getByText('Annotation Instructions')
        ).toBeInTheDocument()
      })
      await user.type(
        screen.getByTestId('wizard-instructions-textarea'),
        'Please annotate carefully'
      )

      // Step 5: Models
      await user.click(screen.getByTestId('project-create-next-button'))
      await waitFor(() => {
        expect(screen.getByText('Select LLM Models')).toBeInTheDocument()
      })
      await user.click(screen.getByTestId('wizard-model-gpt-4'))

      // Step 6: Prompts
      await user.click(screen.getByTestId('project-create-next-button'))
      await waitFor(() => {
        expect(screen.getByText('Configure Prompts')).toBeInTheDocument()
      })

      // Step 7: Evaluation
      await user.click(screen.getByTestId('project-create-next-button'))
      await waitFor(() => {
        expect(screen.getByText('Evaluation Setup')).toBeInTheDocument()
      })
      await user.click(screen.getByTestId('wizard-metric-rouge').querySelector('input[type="checkbox"]')!)

      // Step 8: Settings (always last)
      await user.click(screen.getByTestId('project-create-next-button'))
      await waitFor(() => {
        expect(screen.getByTestId('project-create-submit-button')).toBeInTheDocument()
      })

      // Create
      await user.click(screen.getByTestId('project-create-submit-button'))

      await waitFor(() => {
        expect(mockCreateProject).toHaveBeenCalledWith(
          expect.objectContaining({
            title: 'Full Project',
            label_config: expect.stringContaining('TextArea'),
          })
        )
      })

      // Should update project with instructions + generation config
      await waitFor(() => {
        expect(mockUpdate).toHaveBeenCalledWith(
          'project-full',
          expect.objectContaining({
            instructions: 'Please annotate carefully',
            generation_config: expect.objectContaining({
              selected_configuration: expect.objectContaining({
                models: ['gpt-4'],
              }),
            }),
          })
        )
      })

      // Should save evaluation config
      await waitFor(() => {
        expect(mockApiClientPut).toHaveBeenCalledWith(
          '/evaluations/projects/project-full/evaluation-config',
          expect.objectContaining({
            evaluation_configs: expect.arrayContaining([
              expect.objectContaining({ metric: 'rouge' }),
            ]),
          })
        )
      })

      await waitFor(() => {
        expect(mockPush).toHaveBeenCalledWith('/projects/project-full')
      })
    })

    it('handles creation error', async () => {
      const user = userEvent.setup()
      mockCreateProject.mockRejectedValue(new Error('Creation failed'))

      render(<ProjectCreationWizard />)

      await user.type(
        screen.getByTestId('project-create-name-input'),
        'Test'
      )

      // Navigate to Settings (last step)
      await user.click(screen.getByTestId('project-create-next-button'))
      await waitFor(() => {
        expect(screen.getByTestId('project-create-submit-button')).toBeInTheDocument()
      })
      await user.click(screen.getByTestId('project-create-submit-button'))

      await waitFor(() => {
        expect(mockToastError).toHaveBeenCalledWith('Creation failed')
      })

      expect(mockPush).not.toHaveBeenCalled()
    })

    it('handles import error gracefully', async () => {
      const user = userEvent.setup()
      mockCreateProject.mockResolvedValue({ id: 'project-123' })
      mockImportData.mockRejectedValue(new Error('Import failed'))
      mockFetchProject.mockResolvedValue({})

      render(<ProjectCreationWizard />)

      await user.type(
        screen.getByTestId('project-create-name-input'),
        'Test'
      )
      await enableFeature(user, 'dataImport')

      await user.click(screen.getByTestId('project-create-next-button'))
      await waitFor(() => {
        expect(screen.getByText('Import Data')).toBeInTheDocument()
      })

      await user.click(screen.getByText('Paste'))
      const textarea = await screen.findByTestId(
        'project-create-paste-data-textarea'
      )
      await user.click(textarea)
      await user.paste('{"text": "test"}')

      // Navigate to Settings (last step)
      await user.click(screen.getByTestId('project-create-next-button'))
      await waitFor(() => {
        expect(screen.getByTestId('project-create-submit-button')).toBeInTheDocument()
      })

      await user.click(screen.getByTestId('project-create-submit-button'))

      await waitFor(() => {
        expect(mockToastError).toHaveBeenCalledWith(
          expect.stringContaining('Failed to import data')
        )
      })

      // Should still redirect
      await waitFor(() => {
        expect(mockPush).toHaveBeenCalledWith('/projects/project-123')
      })
    })
  })

  describe('Back/Forth Navigation', () => {
    it('preserves data when navigating back and forth through all steps', async () => {
      const user = userEvent.setup()
      render(<ProjectCreationWizard />)

      // Step 1: fill data and enable annotation
      await user.type(
        screen.getByTestId('project-create-name-input'),
        'Nav Test'
      )
      await enableFeature(user, 'annotation')

      // Go to step 2 (labeling)
      await user.click(screen.getByTestId('project-create-next-button'))
      await waitFor(() => {
        expect(
          screen.getByText('Labeling Configuration')
        ).toBeInTheDocument()
      })

      // Select template
      await user.click(screen.getByText('Question Answering'))
      expect(screen.getByText('Selected')).toBeInTheDocument()

      // Go to step 3 (instructions)
      await user.click(screen.getByTestId('project-create-next-button'))
      await waitFor(() => {
        expect(
          screen.getByText('Annotation Instructions')
        ).toBeInTheDocument()
      })

      // Type instructions
      await user.type(
        screen.getByTestId('wizard-instructions-textarea'),
        'Some instructions'
      )

      // Go back to step 2
      await user.click(screen.getByTestId('project-create-back-button'))
      await waitFor(() => {
        expect(
          screen.getByText('Labeling Configuration')
        ).toBeInTheDocument()
      })

      // Template should still be selected
      expect(screen.getByText('Selected')).toBeInTheDocument()

      // Go back to step 1
      await user.click(screen.getByTestId('project-create-back-button'))
      expect(screen.getByTestId('project-create-name-input')).toHaveValue(
        'Nav Test'
      )

      // Go forward to step 3 again
      await user.click(screen.getByTestId('project-create-next-button'))
      await user.click(screen.getByTestId('project-create-next-button'))
      await waitFor(() => {
        expect(
          screen.getByText('Annotation Instructions')
        ).toBeInTheDocument()
      })

      // Instructions should be preserved
      expect(
        screen.getByTestId('wizard-instructions-textarea')
      ).toHaveValue('Some instructions')
    })
  })
})

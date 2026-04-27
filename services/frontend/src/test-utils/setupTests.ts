/**
 * Global test setup file
 * This file is automatically run before all tests
 */

import '@testing-library/jest-dom'
import { configure } from '@testing-library/react'
import React from 'react'
import { TextDecoder, TextEncoder } from 'util'

// Increase waitFor timeout for CI environments (slower runners)
configure({ asyncUtilTimeout: process.env.CI ? 5000 : 1000 })

// Set up TextEncoder/TextDecoder for tests
global.TextEncoder = TextEncoder as any
global.TextDecoder = TextDecoder as any

// Polyfill Headers.append if it doesn't exist (for Next.js route handlers in tests)
if (typeof Headers !== 'undefined' && !Headers.prototype.append) {
  Headers.prototype.append = function (name: string, value: string) {
    const existing = this.get(name)
    if (existing) {
      this.set(name, `${existing}, ${value}`)
    } else {
      this.set(name, value)
    }
  }
}

// Set up React for tests
global.React = React

// Mock React.use for Next.js async params (React 19 feature)
if (!React.use) {
  ;(React as any).use = (promise: Promise<any> | any) => {
    if (promise && typeof promise.then === 'function') {
      // If it's a promise, throw it to trigger Suspense
      throw promise
    }
    // If it's already resolved (plain object), return it
    return promise
  }
}

// Mock fetch globally
global.fetch = jest.fn(() =>
  Promise.resolve({
    ok: true,
    status: 200,
    json: () => Promise.resolve({}),
    text: () => Promise.resolve(''),
    blob: () => Promise.resolve(new Blob()),
    arrayBuffer: () => Promise.resolve(new ArrayBuffer(0)),
    headers: new Headers(),
    redirected: false,
    statusText: 'OK',
    type: 'basic',
    url: '',
  })
) as jest.Mock

// Mock Next.js navigation globally
jest.mock('next/navigation', () => ({
  useRouter: () => ({
    push: jest.fn(),
    back: jest.fn(),
    forward: jest.fn(),
    refresh: jest.fn(),
    replace: jest.fn(),
    prefetch: jest.fn(),
    pathname: '/',
  }),
  usePathname: () => '/',
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({}),
}))

// Mock Next.js dynamic globally
jest.mock('next/dynamic', () => ({
  __esModule: true,
  default: (fn: () => Promise<any>) => {
    const React = require('react')
    const Component = typeof fn === 'function' ? fn : React.lazy(fn)
    Component.preload = () => {}
    return Component
  },
}))

// Mock contexts globally but allow individual tests to override
jest.mock('@/contexts/AuthContext', () => {
  const actual = jest.requireActual('@/contexts/AuthContext')
  return {
    ...actual,
    useAuth: jest.fn(() => ({
      user: null,
      login: jest.fn(),
      signup: jest.fn(),
      logout: jest.fn(),
      updateUser: jest.fn(),
      isLoading: false,
      refreshAuth: jest.fn(),
      apiClient: {
        getAllUsers: jest.fn().mockResolvedValue([]),
        getOrganizationMembers: jest.fn().mockResolvedValue([]),
        listInvitations: jest.fn().mockResolvedValue([]),
        getOrganizationInvitations: jest.fn().mockResolvedValue([]),
        getOrganizations: jest.fn().mockResolvedValue([]),
        getTasks: jest.fn().mockResolvedValue({ tasks: [], total: 0 }),
        getTask: jest.fn().mockResolvedValue(null),
        // Add HTTP methods that annotation API needs
        get: jest.fn().mockResolvedValue({}),
        post: jest.fn().mockResolvedValue({}),
        put: jest.fn().mockResolvedValue({}),
        patch: jest.fn().mockResolvedValue({}),
        delete: jest.fn().mockResolvedValue({}),
      },
      organizations: [],
      currentOrganization: null,
      setCurrentOrganization: jest.fn(),
      refreshOrganizations: jest.fn(),
    })),
  }
})

jest.mock('@/contexts/I18nContext', () => {
  const translations: Record<string, string> = {
    'auth.signIn': 'Sign In',
    'auth.signUp': 'Sign Up',
    'auth.signOut': 'Sign Out',
    'auth.profileSettings': 'Profile Settings',
    'auth.notificationSettings': 'Notification Settings',
    'auth.userManagement': 'User Management',
    'navigation.organizations': 'Organizations',
    'navigation.projects': 'Projects',
    'navigation.data': 'Data',
    'navigation.generations': 'Generations',
    'navigation.evaluations': 'Evaluations',
    'navigation.reports': 'Reports',
    'navigation.howTo': 'How-To',
    'navigation.dashboard': 'Dashboard',
    'navigation.leaderboards': 'Leaderboards',
    'navigation.dataManagement': 'Data Management',
    'navigation.generation': 'Generation',
    'navigation.evaluation': 'Evaluation',
    'navigation.architecture': 'Architecture',
    'navigation.about': 'About',
    'navigation.quickStart': 'Quick Start',
    'navigation.projectsAndData': 'Projects & Data',
    'navigation.knowledge': 'Knowledge',
    'navigation.signIn': 'Sign in',
    'navigation.templates': 'Templates',
    'navigation.notifications': 'Notifications',
    'navigation.settings': 'Settings',
    'navigation.previous': 'Previous',
    'navigation.next': 'Next',
    'admin.usersOrganizations': 'Users & Organizations',
    'admin.defaultConfiguration': 'Default Configuration',
    'admin.featureFlags': 'Feature Flags',
    'fields.pdf.previousPage': 'Previous page',
    'fields.pdf.nextPage': 'Next page',
    'fields.pdf.zoomOut': 'Zoom out',
    'fields.pdf.zoomIn': 'Zoom in',
    'fields.pdf.fullscreen': 'Fullscreen',
    'fields.pdf.downloadPdf': 'Download PDF',
    'fields.pdf.noFile': 'No PDF loaded',
    'fields.pdf.placeholder': 'PDF Viewer Placeholder',
    'fields.pdf.placeholderDescription':
      'In a production implementation, this would render the actual PDF using a library like react-pdf or pdf.js. For demonstration purposes, we show a placeholder with the current state.',
    'fields.pdf.currentSettings': 'Current Settings:',
    'fields.pdf.url': 'URL',
    'fields.pdf.page': 'Page',
    'fields.pdf.zoom': 'Zoom',
    'fields.pdf.highlights': 'Highlights',
    'fields.pdf.sampleTextLabel': 'Sample text for selection:',
    'fields.pdf.sampleTextContent':
      'This is selectable text that would normally be part of the PDF content. In a real implementation, users could select this text to create highlights.',
    'fields.pdf.keyboardShortcuts':
      'Keyboard shortcuts: Arrow keys (navigate pages), Ctrl/Cmd +/- (zoom), Ctrl/Cmd+0 (reset zoom)',
    'fields.pdf.loadError': 'Error loading PDF',
    'fields.pdf.removeHighlight': 'Remove highlight',
    'fields.pdf.highlightsCount': 'Highlights ({{count}})',
    'fields.pdf.pageLabel': 'Page {{page}}:',
    'admin.performanceDashboard': 'Performance Dashboard',
    'admin.emailVerification': 'Email Verification',
    'admin.testNotifications': 'Test Notifications',
    'common.search': 'Search',
    'common.loading': 'Loading...',
    'common.save': 'Save',
    'common.cancel': 'Cancel',
    'common.delete': 'Delete',
    'common.edit': 'Edit',
    'common.create': 'Create',
    'common.update': 'Update',
    'common.close': 'Close',
    'common.confirm': 'Confirm',
    'common.yes': 'Yes',
    'common.no': 'No',
    'common.back': 'Back',
    'common.next': 'Next',
    'common.submit': 'Submit',
    'common.actions': 'Actions',
    'common.status': 'Status',
    'common.name': 'Name',
    'common.description': 'Description',
    'common.settings': 'Settings',
    'common.refresh': 'Refresh',
    'common.add': 'Add',
    'common.remove': 'Remove',
    'common.error': 'Error',
    'common.success': 'Success',
    'common.warning': 'Warning',
    'common.info': 'Info',
    'projects.searchPlaceholder': 'Search projects...',
    'projects.noProjects': 'No projects found',
    'projects.loading': 'Loading projects...',
    'evaluations.card.unknownTask': 'Unknown Task',
    'evaluations.card.status.completed': 'Completed',
    'evaluations.card.status.running': 'Running',
    'evaluations.card.status.failed': 'Failed',
    'evaluations.card.status.pending': 'Pending',
    'evaluations.filters.model': 'Model',
    'evaluations.filters.status': 'Status',
    'tasks.description.clickToEdit': 'Click to edit description',
    'tasks.description.editDescription': 'Edit description',
    'tasks.description.save': 'Save',
    'tasks.description.cancel': 'Cancel',
    'tasks.detail.loading': 'Loading task...',
    'tasks.detail.notFound': 'Task not found',
    'tasks.detail.notFoundDescription': "The task you're looking for doesn't exist or has been deleted.",
    'tasks.detail.backToDataManager': 'Back to Data Manager',
    'tasks.detail.taskData': 'Task Data',
    'tasks.detail.edit': 'Edit',
    'tasks.detail.save': 'Save',
    'tasks.detail.saving': 'Saving...',
    'tasks.detail.cancel': 'Cancel',
    'tasks.detail.status': 'Status',
    'tasks.detail.labeled': 'Labeled',
    'tasks.detail.unlabeled': 'Unlabeled',
    'tasks.detail.annotations': 'Annotations',
    'tasks.detail.generations': 'Generations',
    'tasks.detail.startLabeling': 'Start Labeling',
    'tasks.detail.viewAnnotations': 'View Annotations',
    'tasks.detail.skipTask': 'Skip Task',
    'tasks.detail.existingAnnotations': 'Existing Annotations',
    'tasks.detail.editDataPlaceholder': 'Enter valid JSON data...',
    'tasks.detail.editHelpText': "Edit the JSON data above. Make sure it's valid JSON format.",
    'tasks.detail.dataUpdated': 'Task data updated successfully',
    'tasks.detail.dataUpdateFailed': 'Failed to update task data',
    'tasks.detail.invalidJson': 'Invalid JSON format',
    'tasks.detail.loadFailed': 'Failed to load task',
    'tasks.detail.noAnnotationsAvailable': 'No annotations available for this task',
    'tasks.detail.taskIdNotAvailable': 'Task ID not available',
    'tasks.detail.loadAnnotationsFailed': 'Failed to load annotations',
    'tasks.detail.projectOrTaskIdNotAvailable': 'Project ID or Task ID not available',
    'tasks.metadata.loading': 'Loading task...',
    'tasks.metadata.notFound': 'Task not found',
    'tasks.metadata.notFoundDescription': "The task you're looking for doesn't exist.",
    'tasks.metadata.backToDataManager': 'Back to Data Manager',
    'tasks.metadata.title': 'Task Metadata',
    'tasks.metadata.edit': 'Edit',
    'tasks.metadata.saving': 'Saving...',
    'tasks.metadata.save': 'Save',
    'tasks.metadata.cancel': 'Cancel',
    'tasks.metadata.jsonPlaceholder': 'Enter valid JSON data...',
    'tasks.metadata.jsonHelpText': 'Edit the metadata as JSON. Ensure proper JSON formatting.',
    'tasks.metadata.status': 'Status:',
    'tasks.metadata.completed': 'Completed',
    'tasks.metadata.unlabeled': 'Unlabeled',
    'tasks.metadata.loadFailed': 'Failed to load task',
    'tasks.metadata.updated': 'Metadata updated successfully',
    'tasks.metadata.updateFailed': 'Failed to update metadata',
    'tasks.metadata.invalidJson': 'Invalid JSON format. Please check your syntax.',
    'error.pageNotFound': 'Page not found',
    'error.404': '404',
    'error.returnToDashboard': 'Return to Dashboard',
    'error.tryAgain': 'Try Again',
    'error.somethingWentWrong': 'Something went wrong',
    'error.technicalDetails': 'Technical Details',
    'admin.dashboard': 'Admin Dashboard',
    'project.promptStructures.title': 'Prompt Structures',
    'project.promptStructures.loadingStructures':
      'Loading prompt structures...',
    'project.promptStructures.notConfigured': 'Not configured',
    'project.promptStructures.configured': 'Configured',
    'data.title': 'Data Management',
    'data.upload': 'Upload',
    'data.download': 'Download',
    'generations.title': 'Generations',
    'generations.run': 'Run Generation',
    'generations.stop': 'Stop Generation',
    'templates.title': 'Templates',
    'templates.create': 'Create Template',
    'reports.title': 'Reports',
    // Register page translations
    'register.redirecting': 'Redirecting...',
    'register.title': 'Create Account',
    'register.email': 'Email',
    'register.password': 'Password',
    'register.confirmPassword': 'Confirm Password',
    'register.submit': 'Register',
    'register.alreadyHaveAccount': 'Already have an account?',
    'register.success': 'Registration successful',
    // Data management translations
    'dataManagement.accessDenied': 'Access Denied',
    'dataManagement.accessDeniedDescription':
      'You do not have permission to access this page',
    'common.backToProjects': 'Back to Projects',
    // Labeling translations
    'labeling.title': 'Labeling',
    'labeling.task': 'Task',
    'labeling.submit': 'Submit',
    'labeling.skip': 'Skip',
    'labeling.previous': 'Previous',
    'labeling.next': 'Next',
    // Template translations
    'templates.import': 'Import',
    'templates.export': 'Export',
    'templates.importSuccess': 'Template imported successfully',
    'templates.exportSuccess': 'Template exported successfully',
    // Evaluation translations
    'evaluation.title': 'Evaluation',
    'evaluation.run': 'Run Evaluation',
    'evaluation.results': 'Results',
    'evaluation.configuration': 'Configuration',
    'evaluation.automated': 'Automated Metrics',
    'evaluation.human': 'Human Evaluation',
    // Generation translations
    'generation.title': 'Generation',
    'generation.selectProject': 'Select Project',
    'generation.run': 'Run Generation',
    'generation.progress': 'Progress',
    'generation.results': 'Results',

    // Toast translations - Human Evaluation
    'toasts.humanEvaluation.noProjectOrSession': 'No project or session specified',
    'toasts.humanEvaluation.sessionCreateFailed': 'Failed to create evaluation session',
    'toasts.humanEvaluation.sessionLoadFailed': 'Failed to load evaluation session',
    'toasts.humanEvaluation.itemLoadFailed': 'Failed to load next evaluation item',
    'toasts.humanEvaluation.selectWinner': 'Please select a winner or mark as tie',
    'toasts.humanEvaluation.submitFailed': 'Failed to submit evaluation',
    'toasts.humanEvaluation.skipFailed': 'Failed to skip item',

    // Toast translations - Generation
    'toasts.generation.selectModel': 'Please select a model',
    'toasts.generation.selectStructure': 'Please select a prompt structure',
    'toasts.generation.configSaved': 'Configuration saved',
    'toasts.generation.resultsFailed': 'Failed to load generation results',
    'toasts.generation.exported': 'Results exported successfully',
    'toasts.generation.exportFailed': 'Failed to export results',
    'toasts.generation.refreshed': 'Generations refreshed',
    'toasts.generation.refreshFailed': 'Failed to refresh generations',
    'toasts.generation.featureNotEnabled': 'Generation feature is not enabled',
    'toasts.generation.invalidProject': 'Invalid project',
    'toasts.generation.needsModels': 'Please configure models first',

    // Toast translations - Evaluation
    'toasts.evaluation.resultsFailed': 'Failed to load evaluation results',
    'toasts.evaluation.exportedFormat': 'Exported as {{format}}',
    'toasts.evaluation.exportFailed': 'Failed to export results',
    'toasts.evaluation.configLoadFailed': 'Failed to load configuration',
    'toasts.evaluation.configSaved': 'Configuration saved',
    'toasts.evaluation.configFailed': 'Failed to save configuration',
    'toasts.evaluation.refreshed': 'Evaluations refreshed',
    'toasts.evaluation.refreshFailed': 'Failed to refresh evaluations',
    'toasts.evaluation.latexCodeCopied': 'LaTeX code copied to clipboard',
    'toasts.evaluation.latexCopyFailed': 'Failed to copy LaTeX code',
    'toasts.evaluation.selectJudgeModel': 'Please select a judge model',
    'toasts.evaluation.selectCriterion': 'Please select at least one criterion',
    'toasts.evaluation.started': 'Evaluation started',
    'toasts.evaluation.startFailed': 'Failed to start evaluation',

    // Toast translations - Projects
    'toasts.projects.deleted': '{{count}} project(s) deleted',
    'toasts.projects.deleteFailed': 'Failed to delete projects',
    'toasts.projects.selectJsonOrZip': 'Please select a JSON or ZIP file',
    'toasts.projects.archiveFailed': 'Failed to archive project',
    'toasts.projects.unarchiveFailed': 'Failed to unarchive project',
    'toasts.project.instructionsUpdateFailed': 'Failed to update instructions: {{error}}',
    'toasts.project.modelsSaved': 'Models saved',
    'toasts.project.modelsSaveFailed': 'Failed to save models: {{error}}',
    'toasts.project.settingsSaved': 'Settings saved',
    'toasts.project.settingsSaveFailed': 'Failed to save settings: {{error}}',

    // Toast translations - Admin
    'toasts.admin.orgCreated': 'Organization created successfully',
    'toasts.admin.orgUpdated': 'Organization updated successfully',
    'toasts.admin.orgDeleted': 'Organization deleted successfully',
    'toasts.admin.invitationSent': 'Invitation sent',
    'toasts.admin.invitationCancelled': 'Invitation cancelled',
    'toasts.admin.memberRemoved': 'Member removed',
    'toasts.admin.memberRoleUpdated': 'Member role updated',
    'toasts.admin.userAdded': 'User added to organization',

    // Toast translations - Template
    'toasts.template.annotationUpdated': 'Annotation template updated',

    // Toast translations - Error
    'toasts.error.saveFailed': 'Failed to save',
    'toasts.error.updateFailed': 'Failed to update',

    // Toast translations - Clipboard
    'toasts.clipboard.copied': 'Copied to clipboard',
    'toasts.clipboard.copyFailed': 'Failed to copy to clipboard',

    // Projects create page translations
    'projects.create.title': 'Create',
    'projects.create.accessDenied': 'Access Denied',
    'projects.create.permissionDenied': 'Only superadmins, organization admins, and contributors can create projects.',
    'projects.backToProjects': 'Back to Projects',

    // Evaluation human setup translations
    'evaluation.human.setup.evaluatorCount': 'Number of Evaluators',
    'evaluation.human.setup.evaluatorCountHelp': 'Target number of human evaluators (typically 3-5 for good reliability)',
    'evaluation.human.setup.blindingLabel': 'Enable Response Blinding',
    'evaluation.human.setup.blindingHelp': 'Recommended: Hide model identities from evaluators to prevent bias',
    'evaluation.human.setup.includeHumanLabel': 'Include Human Responses',
    'evaluation.human.setup.includeHumanHelp': 'Mix human-written responses with AI responses for comparison (if available)',
    'evaluation.human.setup.nextStepsTitle': 'What happens next?',
    'evaluation.human.setup.nextStep1': '\u2022 A dedicated annotation project will be created',
    'evaluation.human.setup.nextStep2': '\u2022 LLM responses will be anonymized and imported',
    'evaluation.human.setup.nextStep3': '\u2022 Evaluators can assess responses on 4 criteria using 5-point scales',
    'evaluation.human.setup.nextStep4': '\u2022 Results will include inter-rater reliability statistics',

    // Task question modal translations
    'tasks.questions.addTitle': 'Add Questions',
    'tasks.questions.editTitle': 'Edit Question',
    'tasks.questions.questionNumber': 'Question #{{number}}',
    'tasks.questions.removeQuestion': 'Remove question',
    'tasks.questions.questionLabel': 'Question *',
    'tasks.questions.questionPlaceholder': 'Enter the question...',
    'tasks.questions.caseLabel': 'Case (Optional)',
    'tasks.questions.casePlaceholder': 'Enter case background...',
    'tasks.questions.answerLabel': 'Answer *',
    'tasks.questions.addAnswer': 'Add Answer',
    'tasks.questions.answerPlaceholder': 'Answer {{number}}...',
    'tasks.questions.removeAnswer': 'Remove answer',
    'tasks.questions.reasoningLabel': 'Reasoning (Optional)',
    'tasks.questions.reasoningPlaceholder': 'Enter reasoning or explanation...',
    'tasks.questions.addAnother': 'Add Another Question',
    'tasks.questions.addCount': 'Add {{count}} Question(s)',
    'tasks.questions.contextLabel': 'Context (Optional)',
    'tasks.questions.contextPlaceholder': 'Enter additional context...',
    'tasks.questions.referenceAnswersLabel': 'Reference Answers *',
    'tasks.questions.referenceAnswerPlaceholder': 'Reference answer {{number}}...',
    'tasks.questions.validation.questionRequired': 'Question is required',
    'tasks.questions.validation.answerRequired': 'At least one answer is required',
    'tasks.questions.validation.referenceAnswerRequired': 'At least one reference answer is required',
    'common.saveChanges': 'Save Changes',
    'annotation.viewTaskData': 'View complete task data',
  }

  const actual = jest.requireActual('@/contexts/I18nContext')
  return {
    ...actual,
    useI18n: jest.fn(() => ({
      t: (key: string, params?: Record<string, any>) => {
        let translation = translations[key] || key
        if (params) {
          // Simple interpolation: replace {{key}} with params[key]
          Object.entries(params).forEach(([paramKey, value]) => {
            translation = translation.replace(
              new RegExp(`\\{\\{${paramKey}\\}\\}`, 'g'),
              String(value)
            )
          })
        }
        return translation
      },
      changeLanguage: jest.fn(),
      currentLanguage: 'en',
      languages: ['en', 'de'],
    })),
  }
})

// Mock hooks
jest.mock('@/hooks/useDialogs', () => ({
  useErrorAlert: () => jest.fn(),
  useDeleteConfirm: () => jest.fn().mockResolvedValue(true),
  useConfirm: () => jest.fn().mockResolvedValue(true),
}))

// Mock BaseApiClient so all API clients have HTTP methods (Issue #360)
jest.mock('@/lib/api/base', () => ({
  BaseApiClient: class MockBaseApiClient {
    get = jest.fn().mockResolvedValue({})
    post = jest.fn().mockResolvedValue({})
    put = jest.fn().mockResolvedValue({})
    patch = jest.fn().mockResolvedValue({})
    delete = jest.fn().mockResolvedValue({})
    request = jest.fn().mockResolvedValue({})
    setAuthFailureHandler = jest.fn()
  },
}))

// Mock specific components mentioned in Issue #360
jest.mock('@/components/shared/LoadingSpinner', () => {
  const React = require('react')
  return {
    LoadingSpinner: ({ size = 'md' }: { size?: 'sm' | 'md' | 'lg' }) =>
      React.createElement(
        'div',
        {
          'data-testid': 'loading-spinner',
          className: `loading-spinner-${size}`,
        },
        'Loading...'
      ),

    TaskDataSkeleton: ({ rows = 5 }: { rows?: number }) =>
      React.createElement(
        'div',
        {
          'data-testid': 'task-data-skeleton',
        },
        `Loading ${rows} rows...`
      ),

    PageLoading: ({ message = 'Loading...' }: { message?: string }) =>
      React.createElement(
        'div',
        {
          'data-testid': 'page-loading',
        },
        message
      ),
  }
})

// Create stable toast mock references that persist across calls
// This prevents tests from failing due to mock reference instability
// Variables MUST be prefixed with 'mock' for Jest to allow them in jest.mock() factories
const mockStableAddToast = jest.fn()
const mockStableRemoveToast = jest.fn()
const mockStableToastSuccess = jest.fn()
const mockStableToastError = jest.fn()
const mockStableToastInfo = jest.fn()
const mockStableToastWarning = jest.fn()

// Export for tests that need direct access
export const mockToast = {
  addToast: mockStableAddToast,
  removeToast: mockStableRemoveToast,
  success: mockStableToastSuccess,
  error: mockStableToastError,
  info: mockStableToastInfo,
  warning: mockStableToastWarning,
}

jest.mock('@/components/shared/Toast', () => {
  const React = require('react')
  return {
    ToastProvider: ({ children }: { children: React.ReactNode }) =>
      React.createElement(
        'div',
        {
          'data-testid': 'toast-provider',
        },
        children
      ),

    // Return stable mock references instead of creating new ones each call
    useToast: jest.fn(() => ({
      addToast: mockStableAddToast,
      removeToast: mockStableRemoveToast,
      toasts: [],
    })),

    toast: {
      success: mockStableToastSuccess,
      error: mockStableToastError,
      info: mockStableToastInfo,
      warning: mockStableToastWarning,
    },
  }
})

// Mock API client to fix "ApiClient is not a constructor" errors
jest.mock('@/lib/api', () => {
  // Create comprehensive mock API client
  const createMockApiClient = () => {
    const mockMethods = [
      'getAllUsers',
      'getOrganizationMembers',
      'listInvitations',
      'getOrganizationInvitations',
      'createOrganization',
      'updateOrganization',
      'addUserToOrganization',
      'updateMemberRole',
      'removeMember',
      'createInvitation',
      'cancelInvitation',
      'getUser',
      'login',
      'logout',
      'getOrganizations',
      'getTasks',
      'getTask',
      'createTask',
      'updateTask',
      'deleteTask',
      'getProjects',
      'getProject',
      'getEvaluations',
      'generateResponses',
      'getModels',
      'getPrompts',
      'updateUserSuperadminStatus',
      'deleteUser',
      'getCurrentUser',
      'getAnnotationOverview',
      'getAnnotationProjectStatistics',
      'createAnnotation',
      'updateAnnotation',
      'getAnnotations',
      'exportBulkData',
      'importBulkData',
      // Prompt methods removed in Issue #759
      'getTaskData',
      'updateTaskData',
      'refresh',
      'updateQuestion',
      'addQuestionsToTask',
    ]

    const mockClient: any = {}

    // Set up default return values for each method
    const defaultReturns: Record<string, any> = {
      getAllUsers: [],
      getOrganizationMembers: [],
      listInvitations: [],
      getOrganizationInvitations: [],
      getOrganizations: [],
      getTasks: { tasks: [], total: 0 },
      getTask: null,
      getProjects: [],
      getProject: null,
      getEvaluations: [],
      getModels: [],
      getPrompts: [],
      getCurrentUser: null,
      getAnnotationOverview: { annotations: [] },
      getAnnotationProjectStatistics: {},
      getAnnotations: [],
      getTaskData: { data: [] },
    }

    // Apply mocks to all methods
    mockMethods.forEach((method) => {
      const returnValue =
        defaultReturns[method] !== undefined ? defaultReturns[method] : {}
      mockClient[method] = jest.fn().mockResolvedValue(returnValue)
    })

    // Add HTTP methods that are used directly
    mockClient.get = jest.fn().mockResolvedValue({})
    mockClient.post = jest.fn().mockResolvedValue({})
    mockClient.put = jest.fn().mockResolvedValue({})
    mockClient.patch = jest.fn().mockResolvedValue({})
    mockClient.delete = jest.fn().mockResolvedValue({})

    // Add configuration methods
    mockClient.setAuthFailureHandler = jest.fn()
    mockClient.setOrganizationContextProvider = jest.fn()
    mockClient.clearCache = jest.fn()
    mockClient.clearUserCache = jest.fn()

    return mockClient
  }

  const mockApiClient = createMockApiClient()

  // Create taskApi compatible object
  const mockTaskApi = {
    getTasks: jest.fn().mockResolvedValue({ tasks: [], total: 0 }),
    getTask: jest.fn().mockResolvedValue(null),
    createTask: jest.fn().mockResolvedValue({}),
    updateTask: jest.fn().mockResolvedValue({}),
    deleteTask: jest.fn().mockResolvedValue(undefined),
    getTaskData: jest.fn().mockResolvedValue({ data: [] }),
    updateTaskData: jest.fn().mockResolvedValue({}),
    exportTaskData: jest.fn().mockResolvedValue({}),
    importTaskData: jest.fn().mockResolvedValue({}),
    bulkUpdateTasks: jest.fn().mockResolvedValue({}),
    assignTasks: jest.fn().mockResolvedValue({}),
    duplicateTask: jest.fn().mockResolvedValue({}),
  }

  // Create a proper constructor function for ApiClient
  class MockApiClient {
    constructor() {
      // Copy all mock methods to this instance
      const instance = createMockApiClient()
      Object.assign(this, instance)
    }
  }

  return {
    ApiClient: MockApiClient,
    api: mockApiClient,
    default: mockApiClient,
    taskApi: mockTaskApi,
    // Export individual methods for * as taskApi imports
    getTasks: mockTaskApi.getTasks,
    getTask: mockTaskApi.getTask,
    createTask: mockTaskApi.createTask,
    updateTask: mockTaskApi.updateTask,
    deleteTask: mockTaskApi.deleteTask,
    getTaskData: mockTaskApi.getTaskData,
    updateTaskData: mockTaskApi.updateTaskData,
    exportTaskData: mockTaskApi.exportTaskData,
    importTaskData: mockTaskApi.importTaskData,
    bulkUpdateTasks: mockTaskApi.bulkUpdateTasks,
    assignTasks: mockTaskApi.assignTasks,
    duplicateTask: mockTaskApi.duplicateTask,
  }
})

// Mock window.matchMedia (only in jsdom environment)
if (typeof window !== 'undefined') {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: jest.fn().mockImplementation((query) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: jest.fn(),
      removeListener: jest.fn(),
      addEventListener: jest.fn(),
      removeEventListener: jest.fn(),
      dispatchEvent: jest.fn(),
    })),
  })
}

// Mock IntersectionObserver
global.IntersectionObserver = class IntersectionObserver {
  root: Element | null = null
  rootMargin: string = ''
  thresholds: ReadonlyArray<number> = []

  constructor() {}
  disconnect() {}
  observe() {}
  unobserve() {}
  takeRecords() {
    return []
  }
} as any

// Mock ResizeObserver
global.ResizeObserver = class ResizeObserver {
  constructor() {}
  disconnect() {}
  observe() {}
  unobserve() {}
}

// Mock window.location globally to avoid conflicts
// Create a mock location object with configurable properties for spying
let _mockPathname = '/'
const mockLocation = {} as any

// Export helper to set mock pathname for tests - attach to global for easy access
;(global as any).__setMockPathname = (pathname: string) => {
  _mockPathname = pathname
}
;(global as any).__getMockPathname = () => _mockPathname

// Define each property with Object.defineProperty to make them configurable
Object.defineProperty(mockLocation, 'href', {
  get: () => 'http://localhost:3000' + _mockPathname,
  set: () => {},
  configurable: true,
  enumerable: true,
})

Object.defineProperty(mockLocation, 'pathname', {
  get: () => _mockPathname,
  set: (value: string) => {
    _mockPathname = value
  },
  configurable: true,
  enumerable: true,
})

let _mockProtocol = 'http:'
let _mockHost = 'localhost:3000'

Object.defineProperty(mockLocation, 'protocol', {
  get: () => _mockProtocol,
  set: (value: string) => {
    _mockProtocol = value
  },
  configurable: true,
  enumerable: true,
})

Object.defineProperty(mockLocation, 'host', {
  get: () => _mockHost,
  set: (value: string) => {
    _mockHost = value
  },
  configurable: true,
  enumerable: true,
})

mockLocation.origin = 'http://localhost:3000'
mockLocation.hostname = 'localhost'
mockLocation.port = '3000'
mockLocation.search = ''
mockLocation.hash = ''
mockLocation.assign = jest.fn()
mockLocation.replace = jest.fn()
mockLocation.reload = jest.fn()
mockLocation.toString = () => 'http://localhost:3000'

// Always replace window.location in test environment to avoid jsdom navigation errors
if (typeof window !== 'undefined') {
  // JSDOM's window.location is non-configurable, so we use a different approach:
  // We spy on the window object's prototype to intercept location access
  // This is done by replacing the getter on Window.prototype

  // Store original getter
  const originalLocationDescriptor = Object.getOwnPropertyDescriptor(
    window,
    'location'
  )

  // Use a workaround: delete from window and define on Window.prototype instead
  // This works because JSDOM's location is defined on the window instance, not prototype
  try {
    // @ts-ignore - bypass readonly
    delete window.location
    // Define mock on window
    Object.defineProperty(window, 'location', {
      value: mockLocation,
      writable: true,
      configurable: true,
      enumerable: true,
    })
  } catch {
    // If the above fails, fall back to assigning properties to the existing location
    // This won't fully mock but will allow some tests to work
    if (window.location) {
      try {
        Object.defineProperty(window.location, 'pathname', {
          get: () => _mockPathname,
          set: (val) => {
            _mockPathname = val
          },
          configurable: true,
        })
      } catch {
        // Last resort: just use the global helper and have tests read _mockPathname directly
      }
    }
  }
}

// Mock File.prototype.text() globally for all tests
// Guard with typeof check since File may not be defined in all Jest projects (e.g. Node/server)
if (typeof File !== 'undefined' && !File.prototype.text) {
  File.prototype.text = function (this: File) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = () => {
        resolve(reader.result as string)
      }
      reader.onerror = () => {
        reject(reader.error)
      }
      reader.readAsText(this)
    })
  }
}

// Suppress console errors in tests unless explicitly needed
const originalError = console.error
beforeAll(() => {
  console.error = (...args: any[]) => {
    if (
      typeof args[0] === 'string' &&
      (args[0].includes('Warning: ReactDOM.render') ||
        args[0].includes('Warning: useLayoutEffect') ||
        args[0].includes('Warning: An update to') ||
        args[0].includes('act(...)') ||
        args[0].includes('Not implemented: HTMLFormElement.requestSubmit') ||
        args[0].includes('Not implemented: navigation'))
    ) {
      return
    }
    originalError.call(console, ...args)
  }
})

// Ensure location properties are reset between tests
afterEach(() => {
  mockLocation.href = 'http://localhost:3000'
  mockLocation.pathname = '/'
  mockLocation.search = ''
  mockLocation.hash = ''
  mockLocation.assign.mockClear()
  mockLocation.replace.mockClear()
  mockLocation.reload.mockClear()
  jest.clearAllMocks()
})

afterAll(() => {
  console.error = originalError
})

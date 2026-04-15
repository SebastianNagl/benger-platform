// Jest DOM matchers
import '@testing-library/jest-dom'

// Mock fetch globally for all tests
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
)

// Mock Next.js router
jest.mock('next/router', () => ({
  useRouter: () => ({
    route: '/',
    pathname: '/',
    query: {},
    asPath: '/',
    push: jest.fn(),
    replace: jest.fn(),
    reload: jest.fn(),
    back: jest.fn(),
    prefetch: jest.fn(),
    beforePopState: jest.fn(),
    events: {
      on: jest.fn(),
      off: jest.fn(),
      emit: jest.fn(),
    },
  }),
}))

// Mock Next.js navigation (App Router)
jest.mock('next/navigation', () => ({
  useRouter: () => ({
    push: jest.fn(),
    replace: jest.fn(),
    prefetch: jest.fn(),
    back: jest.fn(),
    forward: jest.fn(),
    refresh: jest.fn(),
  }),
  usePathname: () => '/',
  useSearchParams: () => new URLSearchParams(),
}))

// Mock environment variables
process.env.NEXT_PUBLIC_API_URL = 'http://localhost:8001'

// Mock Next.js server environment for API route tests
Object.defineProperty(global, 'Request', {
  value: class Request {
    constructor(input, init) {
      Object.defineProperty(this, 'url', {
        value: input,
        writable: false,
        enumerable: true,
        configurable: true,
      })
      this.method = init?.method || 'GET'
      this.headers = new Headers(init?.headers || {})
      this.body = init?.body
    }

    async text() {
      return this.body || ''
    }

    async json() {
      return JSON.parse(this.body || '{}')
    }
  },
  writable: true,
})

Object.defineProperty(global, 'Response', {
  value: class Response {
    constructor(body, init) {
      this.body = body
      this.status = init?.status || 200
      this.statusText = init?.statusText || 'OK'
      this.headers = new Headers(init?.headers || {})
      // Set ok property based on status code (200-299 range)
      this.ok = this.status >= 200 && this.status < 300

      // Set default content-type for JSON responses
      if (body && typeof body === 'string' && body.trim().startsWith('{')) {
        if (!this.headers.get('content-type')) {
          this.headers.set('content-type', 'application/json')
        }
      }
    }

    async text() {
      return this.body || ''
    }

    async json() {
      return JSON.parse(this.body || '{}')
    }

    clone() {
      return new Response(this.body, {
        status: this.status,
        statusText: this.statusText,
        headers: this.headers,
      })
    }

    static json(data, init) {
      return new Response(JSON.stringify(data), {
        ...init,
        headers: {
          'content-type': 'application/json',
          ...(init?.headers || {}),
        },
      })
    }
  },
  writable: true,
})

Object.defineProperty(global, 'Headers', {
  value: class Headers {
    constructor(init) {
      this._headers = new Map()
      if (init) {
        if (init instanceof Headers) {
          init.forEach((value, key) => this.set(key, value))
        } else if (Array.isArray(init)) {
          init.forEach(([key, value]) => this.set(key, value))
        } else if (typeof init === 'object') {
          Object.entries(init).forEach(([key, value]) => this.set(key, value))
        }
      }
    }

    set(key, value) {
      this._headers.set(key.toLowerCase(), value)
    }

    append(key, value) {
      const existing = this.get(key)
      if (existing) {
        // For Set-Cookie headers, we need to keep them separate
        // Store as array internally
        const keyLower = key.toLowerCase()
        const currentValue = this._headers.get(keyLower)
        if (Array.isArray(currentValue)) {
          currentValue.push(value)
        } else {
          this._headers.set(keyLower, [currentValue, value])
        }
      } else {
        this.set(key, value)
      }
    }

    get(key) {
      const value = this._headers.get(key.toLowerCase())
      if (Array.isArray(value)) {
        return value[0]
      }
      return value || null
    }

    getSetCookie() {
      const setCookieKey = 'set-cookie'
      const value = this._headers.get(setCookieKey)
      if (!value) return []
      if (Array.isArray(value)) return value
      return [value]
    }

    has(key) {
      return this._headers.has(key.toLowerCase())
    }

    delete(key) {
      this._headers.delete(key.toLowerCase())
    }

    forEach(callback) {
      this._headers.forEach((value, key) => {
        if (Array.isArray(value)) {
          value.forEach((v) => callback(v, key))
        } else {
          callback(value, key)
        }
      })
    }

    entries() {
      return this._headers.entries()
    }

    keys() {
      return this._headers.keys()
    }

    values() {
      return this._headers.values()
    }
  },
  writable: true,
})

// Global test utilities
global.ResizeObserver = class ResizeObserver {
  constructor(cb) {
    this.cb = cb
  }
  observe() {
    this.cb([{ borderBoxSize: { inlineSize: 0, blockSize: 0 } }], this)
  }
  unobserve() {}
  disconnect() {}
}

// Mock IntersectionObserver
global.IntersectionObserver = class IntersectionObserver {
  constructor() {}
  observe() {}
  disconnect() {}
  unobserve() {}
}

// Mock navigator.clipboard if not already defined (only in browser-like environments)
// This check is needed because api-routes tests run in node environment where navigator doesn't exist
if (typeof navigator !== 'undefined') {
  if (!navigator.clipboard) {
    Object.defineProperty(navigator, 'clipboard', {
      value: {
        writeText: jest.fn().mockResolvedValue(undefined),
        readText: jest.fn().mockResolvedValue(''),
      },
      writable: true,
      configurable: true,
    })
  } else if (
    !navigator.clipboard.writeText ||
    !jest.isMockFunction(navigator.clipboard.writeText)
  ) {
    // If clipboard exists but writeText is not a mock, replace it
    navigator.clipboard.writeText = jest.fn().mockResolvedValue(undefined)
    navigator.clipboard.readText = jest.fn().mockResolvedValue('')
  }
}

// Mock FeatureFlagContext
jest.mock('@/contexts/FeatureFlagContext', () => ({
  useFeatureFlags: () => ({
    flags: {},
    isLoading: false,
    error: null,
    isEnabled: jest.fn().mockReturnValue(true),
    refreshFlags: jest.fn(),
    checkFlag: jest.fn().mockResolvedValue(true),
    lastUpdate: Date.now(),
  }),
  useFeatureFlag: jest.fn().mockReturnValue(true),
  FeatureFlagProvider: ({ children }) => children,
}))

// Mock other common contexts
jest.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({
    user: {
      id: 'test-user-id',
      username: 'testuser',
      email: 'test@example.com',
      name: 'Test User',
      is_superadmin: false,
      is_active: true,
    },
    login: jest.fn(),
    signup: jest.fn(),
    logout: jest.fn(),
    updateUser: jest.fn(),
    isLoading: false,
    refreshAuth: jest.fn(),
    organizations: [],
    currentOrganization: null,
    setCurrentOrganization: jest.fn(),
    refreshOrganizations: jest.fn(),
  }),
  AuthProvider: ({ children }) => children,
}))

jest.mock('@/contexts/I18nContext', () => {
  const translations = {
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
    'annotation.viewTaskData': 'View complete task data',
  }

  return {
    useI18n: () => ({
      t: (key) => translations[key] || key,
      changeLanguage: jest.fn(),
      currentLanguage: 'en',
      languages: ['en', 'de'],
    }),
    I18nProvider: ({ children }) => children,
  }
})

// Mock axios now that it's installed
jest.mock('axios', () => ({
  __esModule: true,
  default: {
    post: jest.fn().mockResolvedValue({ data: {} }),
    get: jest.fn().mockResolvedValue({ data: {} }),
    put: jest.fn().mockResolvedValue({ data: {} }),
    delete: jest.fn().mockResolvedValue({ data: {} }),
    create: jest.fn(() => ({
      post: jest.fn().mockResolvedValue({ data: {} }),
      get: jest.fn().mockResolvedValue({ data: {} }),
      put: jest.fn().mockResolvedValue({ data: {} }),
      delete: jest.fn().mockResolvedValue({ data: {} }),
    })),
  },
  AxiosError: class AxiosError extends Error {
    constructor(message, code) {
      super(message)
      this.name = 'AxiosError'
      this.code = code
    }
  },
}))

/**
 * Component mocks for testing
 * Provides mock implementations of commonly used components
 */

// Mock shared components
export const mockHeroPattern = () => {
  jest.mock('@/components/shared/HeroPattern', () => ({
    HeroPattern: () => <div data-testid="hero-pattern">Hero Pattern</div>,
  }))
}

export const mockGridPattern = () => {
  jest.mock('@/components/shared/GridPattern', () => ({
    GridPattern: () => <div data-testid="grid-pattern">Grid Pattern</div>,
  }))
}

export const mockButton = () => {
  jest.mock('@/components/shared/Button', () => ({
    Button: ({ children, href, ...props }: any) => (
      <button data-testid="button" data-href={href} {...props}>
        {children}
      </button>
    ),
  }))
}

export const mockResponsiveContainer = () => {
  jest.mock('@/components/shared/ResponsiveContainer', () => ({
    ResponsiveContainer: ({ children, ...props }: any) => (
      <div data-testid="responsive-container" {...props}>
        {children}
      </div>
    ),
    LegacyContainer: ({ children, ...props }: any) => (
      <div data-testid="legacy-container" {...props}>
        {children}
      </div>
    ),
  }))
}

export const mockLoadingSpinner = () => {
  jest.mock('@/components/shared/LoadingSpinner', () => ({
    LoadingSpinner: () => <div data-testid="loading-spinner">Loading...</div>,
    TaskDataSkeleton: () => (
      <div data-testid="task-data-skeleton">Loading...</div>
    ),
    PageLoading: () => <div data-testid="page-loading">Loading...</div>,
  }))
}

export const mockEmptyState = () => {
  jest.mock('@/components/shared/EmptyStates', () => ({
    EmptyState: ({ message }: any) => (
      <div data-testid="empty-state">{message}</div>
    ),
    NoAnalyticsDataEmptyState: () => (
      <div data-testid="no-analytics-empty">No analytics data</div>
    ),
    NoTaskSelectedEmptyState: () => (
      <div data-testid="no-task-empty">No task selected</div>
    ),
  }))
}

export const mockSpinner = () => {
  jest.mock('@/components/shared/Spinner', () => ({
    Spinner: () => <div data-testid="spinner">Loading...</div>,
  }))
}

export const mockAuthGuard = () => {
  jest.mock('@/components/auth/AuthGuard', () => ({
    AuthGuard: ({ children }: any) => <>{children}</>,
  }))
}

export const mockProtectedRoute = () => {
  jest.mock('@/components/auth/ProtectedRoute', () => ({
    __esModule: true,
    default: ({ children }: any) => <>{children}</>,
    ProtectedRoute: ({ children }: any) => <>{children}</>,
  }))
}

export const mockBreadcrumb = () => {
  jest.mock('@/components/shared/Breadcrumb', () => ({
    Breadcrumb: ({ items }: any) => (
      <nav data-testid="breadcrumb">
        {items?.map((item: any, i: number) => (
          <span key={i}>{item.label}</span>
        ))}
      </nav>
    ),
  }))
}

export const mockToast = () => {
  jest.mock('@/components/shared/Toast', () => ({
    ToastProvider: ({ children }: any) => <>{children}</>,
    useToast: () => ({
      addToast: jest.fn(),
      removeToast: jest.fn(),
      toasts: [],
    }),
  }))
}

export const mockAlertDialog = () => {
  jest.mock('@/components/shared/AlertDialog', () => ({
    AlertDialog: ({ isOpen, children }: any) =>
      isOpen ? <div data-testid="alert-dialog">{children}</div> : null,
  }))
}

export const mockConfirmationDialog = () => {
  jest.mock('@/components/shared/ConfirmationDialog', () => ({
    ConfirmationDialog: ({ isOpen, onConfirm, onCancel, children }: any) =>
      isOpen ? (
        <div data-testid="confirmation-dialog">
          {children}
          <button onClick={onConfirm}>Confirm</button>
          <button onClick={onCancel}>Cancel</button>
        </div>
      ) : null,
  }))
}

// Mock all shared components at once
export const mockAllSharedComponents = () => {
  mockHeroPattern()
  mockGridPattern()
  mockButton()
  mockResponsiveContainer()
  mockLoadingSpinner()
  mockEmptyState()
  mockSpinner()
  mockAuthGuard()
  mockProtectedRoute()
  mockBreadcrumb()
  mockToast()
  mockAlertDialog()
  mockConfirmationDialog()
}

// Mock specific component exports that might cause issues
export const mockSharedIndex = () => {
  jest.mock('@/components/shared', () => ({
    HeroPattern: () => <div data-testid="hero-pattern">Hero Pattern</div>,
    GridPattern: () => <div data-testid="grid-pattern">Grid Pattern</div>,
    Button: ({ children, ...props }: any) => (
      <button {...props}>{children}</button>
    ),
    ResponsiveContainer: ({ children }: any) => <div>{children}</div>,
    LegacyContainer: ({ children }: any) => <div>{children}</div>,
    LoadingSpinner: () => <div>Loading...</div>,
    TaskDataSkeleton: () => <div>Loading...</div>,
    PageLoading: () => <div>Loading...</div>,
    EmptyState: ({ message }: any) => <div>{message}</div>,
    NoAnalyticsDataEmptyState: () => <div>No analytics data</div>,
    NoTaskSelectedEmptyState: () => <div>No task selected</div>,
    Spinner: () => <div>Loading...</div>,
    ToastProvider: ({ children }: any) => <>{children}</>,
    useToast: () => ({
      addToast: jest.fn(),
      removeToast: jest.fn(),
      toasts: [],
    }),
    SimpleToastProvider: ({ children }: any) => <>{children}</>,
    useSimpleToast: () => ({ addToast: jest.fn() }),
    Tag: ({ children }: any) => <span>{children}</span>,
    FeatureFlag: ({ children }: any) => <>{children}</>,
    AsyncFeatureFlag: ({ children }: any) => <>{children}</>,
    FeatureFlagBoundary: ({ children }: any) => <>{children}</>,
    FeatureFlagDebug: () => null,
    useFeatureFlagWithFallback: () => false,
    withFeatureFlag: (Component: any) => Component,
    GlobalErrorBoundary: ({ children }: any) => <>{children}</>,
    Prose: ({ children }: any) => <div>{children}</div>,
    NoSSR: ({ children }: any) => <>{children}</>,
    RotatingText: ({ texts }: any) => <span>{texts?.[0]}</span>,
    Search: () => <input data-testid="search" />,
    MobileSearch: () => <input data-testid="mobile-search" />,
    Feedback: () => <div>Feedback</div>,
    AlertDialog: ({ isOpen, children }: any) =>
      isOpen ? <div>{children}</div> : null,
    ConfirmationDialog: ({ isOpen, children }: any) =>
      isOpen ? <div>{children}</div> : null,
    Code: ({ children }: any) => <code>{children}</code>,
    CodeGroup: ({ children }: any) => <div>{children}</div>,
    Pre: ({ children }: any) => <pre>{children}</pre>,
    Guides: () => <div>Guides</div>,
    Heading: ({ children }: any) => <h1>{children}</h1>,
    Libraries: () => <div>Libraries</div>,
    Resources: () => <div>Resources</div>,
    SimpleFeatureFlagProvider: ({ children }: any) => <>{children}</>,
    useFeatureFlag: () => false,
    useFeatureFlags: () => ({}),
    UserApiKeys: () => <div>User API Keys</div>,
    MDXButton: ({ children }: any) => <button>{children}</button>,
    MDXCodeGroup: ({ children }: any) => <div>{children}</div>,
    Col: ({ children }: any) => <div>{children}</div>,
    Note: ({ children }: any) => <div>{children}</div>,
    Properties: ({ children }: any) => <div>{children}</div>,
    Property: ({ children }: any) => <div>{children}</div>,
    Row: ({ children }: any) => <div>{children}</div>,
    a: ({ children }: any) => <a>{children}</a>,
    code: ({ children }: any) => <code>{children}</code>,
    h2: ({ children }: any) => <h2>{children}</h2>,
    pre: ({ children }: any) => <pre>{children}</pre>,
    wrapper: ({ children }: any) => <div>{children}</div>,
  }))
}

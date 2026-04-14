/**
 * @jest-environment jsdom
 */
/* eslint-disable react-hooks/globals -- Valid test pattern: capturing hook values via external variables for assertions */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import {
  SimpleFeatureFlagProvider,
  useFeatureFlag,
  useFeatureFlags,
} from '../SimpleFeatureFlags'

// Mock SimpleAuth
const mockUseAuth = jest.fn()

jest.mock('@/components/auth/SimpleAuth', () => ({
  useAuth: () => mockUseAuth(),
}))

// Test component to access feature flag context
function TestComponent() {
  const { flags, isLoading, isEnabled, toggleFlag } = useFeatureFlags()

  return (
    <div>
      <div data-testid="loading-status">
        {isLoading ? 'Loading' : 'Not Loading'}
      </div>
      <div data-testid="flags-count">Flags: {Object.keys(flags).length}</div>

      <div data-testid="new-ui-flag">
        new_ui: {isEnabled('new_ui') ? 'enabled' : 'disabled'}
      </div>
      <div data-testid="beta-features-flag">
        beta_features: {isEnabled('beta_features') ? 'enabled' : 'disabled'}
      </div>
      <div data-testid="advanced-analytics-flag">
        advanced_analytics:{' '}
        {isEnabled('advanced_analytics') ? 'enabled' : 'disabled'}
      </div>
      <div data-testid="experimental-features-flag">
        experimental_features:{' '}
        {isEnabled('experimental_features') ? 'enabled' : 'disabled'}
      </div>
      <div data-testid="unknown-flag">
        unknown_flag: {isEnabled('unknown_flag') ? 'enabled' : 'disabled'}
      </div>

      <button
        onClick={() => toggleFlag('new_ui')}
        data-testid="toggle-new-ui-btn"
      >
        Toggle New UI
      </button>
      <button
        onClick={() => toggleFlag('beta_features')}
        data-testid="toggle-beta-btn"
      >
        Toggle Beta
      </button>
      <button
        onClick={() => toggleFlag('experimental_features')}
        data-testid="toggle-experimental-btn"
      >
        Toggle Experimental
      </button>
    </div>
  )
}

// Test component using useFeatureFlag hook
function FeatureFlagHookComponent({ flagName }: { flagName: string }) {
  const isEnabled = useFeatureFlag(flagName)

  return (
    <div data-testid="hook-result">
      {isEnabled ? `${flagName} enabled` : `${flagName} disabled`}
    </div>
  )
}

describe('SimpleFeatureFlags', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockUseAuth.mockReturnValue({ user: null })
  })

  describe('Basic Rendering', () => {
    it('renders children correctly', () => {
      mockUseAuth.mockReturnValue({ user: null })

      render(
        <SimpleFeatureFlagProvider>
          <div data-testid="child">Child Component</div>
        </SimpleFeatureFlagProvider>
      )

      expect(screen.getByTestId('child')).toBeInTheDocument()
    })

    it('renders provider without crashing', () => {
      mockUseAuth.mockReturnValue({ user: null })

      const { container } = render(
        <SimpleFeatureFlagProvider>
          <TestComponent />
        </SimpleFeatureFlagProvider>
      )

      expect(container).toBeInTheDocument()
    })

    it('renders with multiple children', () => {
      mockUseAuth.mockReturnValue({ user: null })

      render(
        <SimpleFeatureFlagProvider>
          <div data-testid="first-child">First</div>
          <div data-testid="second-child">Second</div>
        </SimpleFeatureFlagProvider>
      )

      expect(screen.getByTestId('first-child')).toBeInTheDocument()
      expect(screen.getByTestId('second-child')).toBeInTheDocument()
    })

    it('renders with nested component structure', () => {
      mockUseAuth.mockReturnValue({ user: null })

      render(
        <SimpleFeatureFlagProvider>
          <div>
            <h1>Title</h1>
            <TestComponent />
            <p>Footer</p>
          </div>
        </SimpleFeatureFlagProvider>
      )

      expect(screen.getByText('Title')).toBeInTheDocument()
      expect(screen.getByTestId('flags-count')).toBeInTheDocument()
      expect(screen.getByText('Footer')).toBeInTheDocument()
    })
  })

  describe('Feature Flag Checking', () => {
    it('initializes with default flags', () => {
      mockUseAuth.mockReturnValue({ user: null })

      render(
        <SimpleFeatureFlagProvider>
          <TestComponent />
        </SimpleFeatureFlagProvider>
      )

      expect(screen.getByTestId('flags-count')).toHaveTextContent('Flags: 4')
    })

    it('enables new_ui flag by default', () => {
      mockUseAuth.mockReturnValue({ user: null })

      render(
        <SimpleFeatureFlagProvider>
          <TestComponent />
        </SimpleFeatureFlagProvider>
      )

      expect(screen.getByTestId('new-ui-flag')).toHaveTextContent(
        'new_ui: enabled'
      )
    })

    it('disables beta_features flag by default', () => {
      mockUseAuth.mockReturnValue({ user: null })

      render(
        <SimpleFeatureFlagProvider>
          <TestComponent />
        </SimpleFeatureFlagProvider>
      )

      expect(screen.getByTestId('beta-features-flag')).toHaveTextContent(
        'beta_features: disabled'
      )
    })

    it('disables experimental_features flag by default', () => {
      mockUseAuth.mockReturnValue({ user: null })

      render(
        <SimpleFeatureFlagProvider>
          <TestComponent />
        </SimpleFeatureFlagProvider>
      )

      expect(
        screen.getByTestId('experimental-features-flag')
      ).toHaveTextContent('experimental_features: disabled')
    })

    it('returns false for unknown flags', () => {
      mockUseAuth.mockReturnValue({ user: null })

      render(
        <SimpleFeatureFlagProvider>
          <TestComponent />
        </SimpleFeatureFlagProvider>
      )

      expect(screen.getByTestId('unknown-flag')).toHaveTextContent(
        'unknown_flag: disabled'
      )
    })

    it('checks flag status correctly with isEnabled', () => {
      mockUseAuth.mockReturnValue({ user: null })

      let contextValue: any

      function ContextConsumer() {
        contextValue = useFeatureFlags()
        return null
      }

      render(
        <SimpleFeatureFlagProvider>
          <ContextConsumer />
        </SimpleFeatureFlagProvider>
      )

      expect(contextValue.isEnabled('new_ui')).toBe(true)
      expect(contextValue.isEnabled('beta_features')).toBe(false)
      expect(contextValue.isEnabled('unknown')).toBe(false)
    })
  })

  describe('Children Rendering', () => {
    it('renders all children when flags are enabled', () => {
      mockUseAuth.mockReturnValue({ user: { role: 'admin' } })

      function ConditionalContent() {
        const newUiEnabled = useFeatureFlag('new_ui')
        const advancedAnalyticsEnabled = useFeatureFlag('advanced_analytics')

        return (
          <div>
            {newUiEnabled && (
              <div data-testid="new-ui-content">New UI Content</div>
            )}
            {advancedAnalyticsEnabled && (
              <div data-testid="analytics-content">Analytics Content</div>
            )}
          </div>
        )
      }

      render(
        <SimpleFeatureFlagProvider>
          <ConditionalContent />
        </SimpleFeatureFlagProvider>
      )

      expect(screen.getByTestId('new-ui-content')).toBeInTheDocument()
      expect(screen.getByTestId('analytics-content')).toBeInTheDocument()
    })

    it('does not render children when flags are disabled', () => {
      mockUseAuth.mockReturnValue({ user: null })

      function ConditionalContent() {
        const betaEnabled = useFeatureFlag('beta_features')
        const experimentalEnabled = useFeatureFlag('experimental_features')

        return (
          <div>
            {betaEnabled && <div data-testid="beta-content">Beta Content</div>}
            {experimentalEnabled && (
              <div data-testid="experimental-content">Experimental Content</div>
            )}
            <div data-testid="always-visible">Always Visible</div>
          </div>
        )
      }

      render(
        <SimpleFeatureFlagProvider>
          <ConditionalContent />
        </SimpleFeatureFlagProvider>
      )

      expect(screen.queryByTestId('beta-content')).not.toBeInTheDocument()
      expect(
        screen.queryByTestId('experimental-content')
      ).not.toBeInTheDocument()
      expect(screen.getByTestId('always-visible')).toBeInTheDocument()
    })

    it('renders component children based on flags', () => {
      mockUseAuth.mockReturnValue({ user: null })

      function FeatureComponent() {
        const newUiEnabled = useFeatureFlag('new_ui')
        return newUiEnabled ? (
          <div data-testid="feature-component">Feature Active</div>
        ) : (
          <div data-testid="feature-disabled">Feature Disabled</div>
        )
      }

      render(
        <SimpleFeatureFlagProvider>
          <FeatureComponent />
        </SimpleFeatureFlagProvider>
      )

      expect(screen.getByTestId('feature-component')).toBeInTheDocument()
      expect(screen.queryByTestId('feature-disabled')).not.toBeInTheDocument()
    })

    it('preserves component props based on flags', () => {
      mockUseAuth.mockReturnValue({ user: null })

      function StyledFeature() {
        const newUiEnabled = useFeatureFlag('new_ui')
        return (
          <button
            data-testid="styled-button"
            className={newUiEnabled ? 'new-style' : 'old-style'}
          >
            Click Me
          </button>
        )
      }

      render(
        <SimpleFeatureFlagProvider>
          <StyledFeature />
        </SimpleFeatureFlagProvider>
      )

      const button = screen.getByTestId('styled-button')
      expect(button).toHaveClass('new-style')
      expect(button).not.toHaveClass('old-style')
    })
  })

  describe('Fallback Content', () => {
    it('renders fallback when flag is disabled', () => {
      mockUseAuth.mockReturnValue({ user: null })

      function FallbackExample() {
        const betaEnabled = useFeatureFlag('beta_features')
        return betaEnabled ? (
          <div data-testid="main-content">Main Content</div>
        ) : (
          <div data-testid="fallback-content">Fallback Content</div>
        )
      }

      render(
        <SimpleFeatureFlagProvider>
          <FallbackExample />
        </SimpleFeatureFlagProvider>
      )

      expect(screen.getByTestId('fallback-content')).toBeInTheDocument()
      expect(screen.queryByTestId('main-content')).not.toBeInTheDocument()
    })

    it('renders main content when flag is enabled', () => {
      mockUseAuth.mockReturnValue({ user: null })

      function FallbackExample() {
        const newUiEnabled = useFeatureFlag('new_ui')
        return newUiEnabled ? (
          <div data-testid="main-content">Main Content</div>
        ) : (
          <div data-testid="fallback-content">Fallback Content</div>
        )
      }

      render(
        <SimpleFeatureFlagProvider>
          <FallbackExample />
        </SimpleFeatureFlagProvider>
      )

      expect(screen.getByTestId('main-content')).toBeInTheDocument()
      expect(screen.queryByTestId('fallback-content')).not.toBeInTheDocument()
    })

    it('renders complex fallback content', () => {
      mockUseAuth.mockReturnValue({ user: null })

      function ComplexFallback() {
        const betaEnabled = useFeatureFlag('beta_features')
        return betaEnabled ? (
          <div data-testid="feature">Feature</div>
        ) : (
          <div>
            <h2 data-testid="fallback-title">Feature Unavailable</h2>
            <p data-testid="fallback-message">Coming Soon</p>
          </div>
        )
      }

      render(
        <SimpleFeatureFlagProvider>
          <ComplexFallback />
        </SimpleFeatureFlagProvider>
      )

      expect(screen.getByTestId('fallback-title')).toHaveTextContent(
        'Feature Unavailable'
      )
      expect(screen.getByTestId('fallback-message')).toHaveTextContent(
        'Coming Soon'
      )
    })

    it('renders null as fallback', () => {
      mockUseAuth.mockReturnValue({ user: null })

      function NullFallback() {
        const betaEnabled = useFeatureFlag('beta_features')
        return betaEnabled ? <div data-testid="content">Content</div> : null
      }

      const { container } = render(
        <SimpleFeatureFlagProvider>
          <NullFallback />
        </SimpleFeatureFlagProvider>
      )

      expect(screen.queryByTestId('content')).not.toBeInTheDocument()
      expect(container.textContent).toBe('')
    })
  })

  describe('Props/Attributes', () => {
    it('provides flags object with all flags', () => {
      mockUseAuth.mockReturnValue({ user: null })

      let flagsObject: any

      function FlagsConsumer() {
        const { flags } = useFeatureFlags()
        flagsObject = flags
        return null
      }

      render(
        <SimpleFeatureFlagProvider>
          <FlagsConsumer />
        </SimpleFeatureFlagProvider>
      )

      expect(flagsObject).toHaveProperty('new_ui', true)
      expect(flagsObject).toHaveProperty('beta_features', false)
      expect(flagsObject).toHaveProperty('advanced_analytics', false)
      expect(flagsObject).toHaveProperty('experimental_features', false)
    })

    it('provides isLoading attribute', () => {
      mockUseAuth.mockReturnValue({ user: null })

      render(
        <SimpleFeatureFlagProvider>
          <TestComponent />
        </SimpleFeatureFlagProvider>
      )

      expect(screen.getByTestId('loading-status')).toHaveTextContent(
        'Not Loading'
      )
    })

    it('provides isEnabled function', () => {
      mockUseAuth.mockReturnValue({ user: null })

      let isEnabledFn: any

      function FunctionConsumer() {
        const { isEnabled } = useFeatureFlags()
        isEnabledFn = isEnabled
        return null
      }

      render(
        <SimpleFeatureFlagProvider>
          <FunctionConsumer />
        </SimpleFeatureFlagProvider>
      )

      expect(typeof isEnabledFn).toBe('function')
      expect(isEnabledFn('new_ui')).toBe(true)
      expect(isEnabledFn('beta_features')).toBe(false)
    })

    it('provides toggleFlag function', () => {
      mockUseAuth.mockReturnValue({ user: null })

      let toggleFlagFn: any

      function FunctionConsumer() {
        const { toggleFlag } = useFeatureFlags()
        toggleFlagFn = toggleFlag
        return null
      }

      render(
        <SimpleFeatureFlagProvider>
          <FunctionConsumer />
        </SimpleFeatureFlagProvider>
      )

      expect(typeof toggleFlagFn).toBe('function')
    })
  })

  describe('Context Integration', () => {
    it('updates advanced_analytics based on user role', () => {
      mockUseAuth.mockReturnValue({ user: { role: 'admin' } })

      render(
        <SimpleFeatureFlagProvider>
          <TestComponent />
        </SimpleFeatureFlagProvider>
      )

      expect(screen.getByTestId('advanced-analytics-flag')).toHaveTextContent(
        'advanced_analytics: enabled'
      )
    })

    it('disables advanced_analytics for non-admin users', () => {
      mockUseAuth.mockReturnValue({ user: { role: 'user' } })

      render(
        <SimpleFeatureFlagProvider>
          <TestComponent />
        </SimpleFeatureFlagProvider>
      )

      expect(screen.getByTestId('advanced-analytics-flag')).toHaveTextContent(
        'advanced_analytics: disabled'
      )
    })

    it('disables advanced_analytics when no user', () => {
      mockUseAuth.mockReturnValue({ user: null })

      render(
        <SimpleFeatureFlagProvider>
          <TestComponent />
        </SimpleFeatureFlagProvider>
      )

      expect(screen.getByTestId('advanced-analytics-flag')).toHaveTextContent(
        'advanced_analytics: disabled'
      )
    })

    it('updates flags when user role changes', () => {
      mockUseAuth.mockReturnValue({ user: { role: 'user' } })

      const { rerender } = render(
        <SimpleFeatureFlagProvider>
          <TestComponent />
        </SimpleFeatureFlagProvider>
      )

      expect(screen.getByTestId('advanced-analytics-flag')).toHaveTextContent(
        'advanced_analytics: disabled'
      )

      mockUseAuth.mockReturnValue({ user: { role: 'admin' } })

      rerender(
        <SimpleFeatureFlagProvider>
          <TestComponent />
        </SimpleFeatureFlagProvider>
      )

      waitFor(() => {
        expect(screen.getByTestId('advanced-analytics-flag')).toHaveTextContent(
          'advanced_analytics: enabled'
        )
      })
    })

    it('handles multiple role transitions', () => {
      mockUseAuth.mockReturnValue({ user: null })

      const { rerender } = render(
        <SimpleFeatureFlagProvider>
          <TestComponent />
        </SimpleFeatureFlagProvider>
      )

      expect(screen.getByTestId('advanced-analytics-flag')).toHaveTextContent(
        'advanced_analytics: disabled'
      )

      mockUseAuth.mockReturnValue({ user: { role: 'admin' } })

      rerender(
        <SimpleFeatureFlagProvider>
          <TestComponent />
        </SimpleFeatureFlagProvider>
      )

      mockUseAuth.mockReturnValue({ user: { role: 'user' } })

      rerender(
        <SimpleFeatureFlagProvider>
          <TestComponent />
        </SimpleFeatureFlagProvider>
      )

      mockUseAuth.mockReturnValue({ user: { role: 'admin' } })

      rerender(
        <SimpleFeatureFlagProvider>
          <TestComponent />
        </SimpleFeatureFlagProvider>
      )
    })
  })

  describe('Accessibility', () => {
    it('maintains accessible structure with feature flags', () => {
      mockUseAuth.mockReturnValue({ user: { role: 'admin' } })

      function AccessibleComponent() {
        const newUiEnabled = useFeatureFlag('new_ui')
        return (
          <div>
            <h1>Dashboard</h1>
            {newUiEnabled && (
              <button aria-label="New Feature">New Feature</button>
            )}
          </div>
        )
      }

      render(
        <SimpleFeatureFlagProvider>
          <AccessibleComponent />
        </SimpleFeatureFlagProvider>
      )

      expect(
        screen.getByRole('heading', { name: 'Dashboard' })
      ).toBeInTheDocument()
      expect(
        screen.getByRole('button', { name: 'New Feature' })
      ).toBeInTheDocument()
    })

    it('preserves ARIA attributes with flags', () => {
      mockUseAuth.mockReturnValue({ user: null })

      function AriaComponent() {
        const newUiEnabled = useFeatureFlag('new_ui')
        return (
          <div
            role="region"
            aria-label="Feature Section"
            data-testid="feature-region"
          >
            {newUiEnabled ? 'New Version' : 'Old Version'}
          </div>
        )
      }

      render(
        <SimpleFeatureFlagProvider>
          <AriaComponent />
        </SimpleFeatureFlagProvider>
      )

      const region = screen.getByTestId('feature-region')
      expect(region).toHaveAttribute('role', 'region')
      expect(region).toHaveAttribute('aria-label', 'Feature Section')
    })

    it('maintains focus management across flag changes', async () => {
      mockUseAuth.mockReturnValue({ user: null })
      const user = userEvent.setup()

      function FocusComponent() {
        const betaEnabled = useFeatureFlag('beta_features')
        return (
          <div>
            <button data-testid="primary-button">Primary</button>
            {betaEnabled && <button data-testid="beta-button">Beta</button>}
          </div>
        )
      }

      render(
        <SimpleFeatureFlagProvider>
          <FocusComponent />
        </SimpleFeatureFlagProvider>
      )

      const primaryButton = screen.getByTestId('primary-button')
      await user.click(primaryButton)
      expect(primaryButton).toHaveFocus()
    })

    it('provides semantic HTML structure regardless of flags', () => {
      mockUseAuth.mockReturnValue({ user: null })

      function SemanticComponent() {
        const newUiEnabled = useFeatureFlag('new_ui')
        return (
          <main>
            <header>
              <h1>Title</h1>
            </header>
            <section>
              {newUiEnabled ? (
                <article>New Content</article>
              ) : (
                <article>Old Content</article>
              )}
            </section>
          </main>
        )
      }

      render(
        <SimpleFeatureFlagProvider>
          <SemanticComponent />
        </SimpleFeatureFlagProvider>
      )

      expect(screen.getByRole('main')).toBeInTheDocument()
      expect(screen.getByRole('banner')).toBeInTheDocument()
      expect(screen.getByRole('heading')).toBeInTheDocument()
    })
  })

  describe('Edge Cases', () => {
    it('handles empty flag name', () => {
      mockUseAuth.mockReturnValue({ user: null })

      render(
        <SimpleFeatureFlagProvider>
          <FeatureFlagHookComponent flagName="" />
        </SimpleFeatureFlagProvider>
      )

      expect(screen.getByTestId('hook-result')).toHaveTextContent('disabled')
    })

    it('handles special characters in flag name', () => {
      mockUseAuth.mockReturnValue({ user: null })

      render(
        <SimpleFeatureFlagProvider>
          <FeatureFlagHookComponent flagName="feature-with-dashes_and_underscores" />
        </SimpleFeatureFlagProvider>
      )

      expect(screen.getByTestId('hook-result')).toHaveTextContent('disabled')
    })

    it('handles toggle of non-existent flag', async () => {
      mockUseAuth.mockReturnValue({ user: null })
      const user = userEvent.setup()

      function ToggleUnknownComponent() {
        const { isEnabled, toggleFlag } = useFeatureFlags()

        return (
          <div>
            <div data-testid="unknown-status">
              {isEnabled('unknown') ? 'enabled' : 'disabled'}
            </div>
            <button
              onClick={() => toggleFlag('unknown')}
              data-testid="toggle-unknown-btn"
            >
              Toggle Unknown
            </button>
          </div>
        )
      }

      render(
        <SimpleFeatureFlagProvider>
          <ToggleUnknownComponent />
        </SimpleFeatureFlagProvider>
      )

      expect(screen.getByTestId('unknown-status')).toHaveTextContent('disabled')

      const toggleBtn = screen.getByTestId('toggle-unknown-btn')
      await user.click(toggleBtn)

      await waitFor(() => {
        expect(screen.getByTestId('unknown-status')).toHaveTextContent(
          'enabled'
        )
      })
    })

    it('handles rapid flag toggles', async () => {
      mockUseAuth.mockReturnValue({ user: null })
      const user = userEvent.setup()

      render(
        <SimpleFeatureFlagProvider>
          <TestComponent />
        </SimpleFeatureFlagProvider>
      )

      const toggleBtn = screen.getByTestId('toggle-new-ui-btn')

      expect(screen.getByTestId('new-ui-flag')).toHaveTextContent(
        'new_ui: enabled'
      )

      await user.click(toggleBtn)
      await waitFor(() => {
        expect(screen.getByTestId('new-ui-flag')).toHaveTextContent(
          'new_ui: disabled'
        )
      })

      await user.click(toggleBtn)
      await waitFor(() => {
        expect(screen.getByTestId('new-ui-flag')).toHaveTextContent(
          'new_ui: enabled'
        )
      })

      await user.click(toggleBtn)
      await waitFor(() => {
        expect(screen.getByTestId('new-ui-flag')).toHaveTextContent(
          'new_ui: disabled'
        )
      })
    })

    it('handles null children', () => {
      mockUseAuth.mockReturnValue({ user: null })

      const { container } = render(
        <SimpleFeatureFlagProvider>{null}</SimpleFeatureFlagProvider>
      )

      expect(container.textContent).toBe('')
    })

    it('handles undefined user', () => {
      mockUseAuth.mockReturnValue({ user: undefined })

      render(
        <SimpleFeatureFlagProvider>
          <TestComponent />
        </SimpleFeatureFlagProvider>
      )

      expect(screen.getByTestId('advanced-analytics-flag')).toHaveTextContent(
        'advanced_analytics: disabled'
      )
    })

    it('handles user without role property', () => {
      mockUseAuth.mockReturnValue({ user: {} })

      render(
        <SimpleFeatureFlagProvider>
          <TestComponent />
        </SimpleFeatureFlagProvider>
      )

      expect(screen.getByTestId('advanced-analytics-flag')).toHaveTextContent(
        'advanced_analytics: disabled'
      )
    })

    it('maintains flag state across multiple toggles', async () => {
      mockUseAuth.mockReturnValue({ user: null })
      const user = userEvent.setup()

      render(
        <SimpleFeatureFlagProvider>
          <TestComponent />
        </SimpleFeatureFlagProvider>
      )

      const toggleBetaBtn = screen.getByTestId('toggle-beta-btn')
      const toggleExperimentalBtn = screen.getByTestId(
        'toggle-experimental-btn'
      )

      expect(screen.getByTestId('beta-features-flag')).toHaveTextContent(
        'beta_features: disabled'
      )
      expect(
        screen.getByTestId('experimental-features-flag')
      ).toHaveTextContent('experimental_features: disabled')

      await user.click(toggleBetaBtn)
      await waitFor(() => {
        expect(screen.getByTestId('beta-features-flag')).toHaveTextContent(
          'beta_features: enabled'
        )
      })

      await user.click(toggleExperimentalBtn)
      await waitFor(() => {
        expect(
          screen.getByTestId('experimental-features-flag')
        ).toHaveTextContent('experimental_features: enabled')
      })

      expect(screen.getByTestId('beta-features-flag')).toHaveTextContent(
        'beta_features: enabled'
      )
    })
  })

  describe('useFeatureFlag Hook', () => {
    it('returns correct value for enabled flag', () => {
      mockUseAuth.mockReturnValue({ user: null })

      render(
        <SimpleFeatureFlagProvider>
          <FeatureFlagHookComponent flagName="new_ui" />
        </SimpleFeatureFlagProvider>
      )

      expect(screen.getByTestId('hook-result')).toHaveTextContent(
        'new_ui enabled'
      )
    })

    it('returns correct value for disabled flag', () => {
      mockUseAuth.mockReturnValue({ user: null })

      render(
        <SimpleFeatureFlagProvider>
          <FeatureFlagHookComponent flagName="beta_features" />
        </SimpleFeatureFlagProvider>
      )

      expect(screen.getByTestId('hook-result')).toHaveTextContent(
        'beta_features disabled'
      )
    })

    it('returns false for unknown flag', () => {
      mockUseAuth.mockReturnValue({ user: null })

      render(
        <SimpleFeatureFlagProvider>
          <FeatureFlagHookComponent flagName="unknown_flag" />
        </SimpleFeatureFlagProvider>
      )

      expect(screen.getByTestId('hook-result')).toHaveTextContent(
        'unknown_flag disabled'
      )
    })

    it('returns false when used outside provider', () => {
      function ComponentWithoutProvider() {
        const isEnabled = useFeatureFlag('new_ui')
        return <div data-testid="result">{isEnabled ? 'yes' : 'no'}</div>
      }

      render(<ComponentWithoutProvider />)

      expect(screen.getByTestId('result')).toHaveTextContent('no')
    })

    it('responds to flag changes', async () => {
      mockUseAuth.mockReturnValue({ user: null })
      const user = userEvent.setup()

      function TogglableComponent() {
        const isEnabled = useFeatureFlag('beta_features')
        const { toggleFlag } = useFeatureFlags()

        return (
          <div>
            <div data-testid="flag-status">
              {isEnabled ? 'enabled' : 'disabled'}
            </div>
            <button
              onClick={() => toggleFlag('beta_features')}
              data-testid="toggle-btn"
            >
              Toggle
            </button>
          </div>
        )
      }

      render(
        <SimpleFeatureFlagProvider>
          <TogglableComponent />
        </SimpleFeatureFlagProvider>
      )

      expect(screen.getByTestId('flag-status')).toHaveTextContent('disabled')

      await user.click(screen.getByTestId('toggle-btn'))

      await waitFor(() => {
        expect(screen.getByTestId('flag-status')).toHaveTextContent('enabled')
      })
    })
  })

  describe('useFeatureFlags Hook', () => {
    it('throws error when used outside provider', () => {
      const consoleError = jest
        .spyOn(console, 'error')
        .mockImplementation(() => {})

      function ComponentWithoutProvider() {
        useFeatureFlags()
        return <div>Test</div>
      }

      expect(() => render(<ComponentWithoutProvider />)).toThrow(
        'useFeatureFlags must be used within a FeatureFlagProvider'
      )

      consoleError.mockRestore()
    })

    it('provides all required context values', () => {
      mockUseAuth.mockReturnValue({ user: null })

      let contextValue: any

      function ContextConsumer() {
        contextValue = useFeatureFlags()
        return null
      }

      render(
        <SimpleFeatureFlagProvider>
          <ContextConsumer />
        </SimpleFeatureFlagProvider>
      )

      expect(contextValue).toHaveProperty('flags')
      expect(contextValue).toHaveProperty('isLoading')
      expect(contextValue).toHaveProperty('isEnabled')
      expect(contextValue).toHaveProperty('toggleFlag')
    })

    it('provides working isEnabled function', () => {
      mockUseAuth.mockReturnValue({ user: null })

      let contextValue: any

      function ContextConsumer() {
        contextValue = useFeatureFlags()
        return null
      }

      render(
        <SimpleFeatureFlagProvider>
          <ContextConsumer />
        </SimpleFeatureFlagProvider>
      )

      expect(contextValue.isEnabled('new_ui')).toBe(true)
      expect(contextValue.isEnabled('beta_features')).toBe(false)
      expect(contextValue.isEnabled('nonexistent')).toBe(false)
    })

    it('provides working toggleFlag function', async () => {
      mockUseAuth.mockReturnValue({ user: null })

      let contextValue: any

      function ContextConsumer() {
        contextValue = useFeatureFlags()
        return (
          <div data-testid="beta-status">
            {contextValue.isEnabled('beta_features') ? 'on' : 'off'}
          </div>
        )
      }

      render(
        <SimpleFeatureFlagProvider>
          <ContextConsumer />
        </SimpleFeatureFlagProvider>
      )

      expect(screen.getByTestId('beta-status')).toHaveTextContent('off')

      await waitFor(() => {
        contextValue.toggleFlag('beta_features')
      })

      await waitFor(() => {
        expect(screen.getByTestId('beta-status')).toHaveTextContent('on')
      })
    })
  })

  describe('Toggle Functionality', () => {
    it('toggles flag from enabled to disabled', async () => {
      mockUseAuth.mockReturnValue({ user: null })
      const user = userEvent.setup()

      render(
        <SimpleFeatureFlagProvider>
          <TestComponent />
        </SimpleFeatureFlagProvider>
      )

      expect(screen.getByTestId('new-ui-flag')).toHaveTextContent(
        'new_ui: enabled'
      )

      await user.click(screen.getByTestId('toggle-new-ui-btn'))

      await waitFor(() => {
        expect(screen.getByTestId('new-ui-flag')).toHaveTextContent(
          'new_ui: disabled'
        )
      })
    })

    it('toggles flag from disabled to enabled', async () => {
      mockUseAuth.mockReturnValue({ user: null })
      const user = userEvent.setup()

      render(
        <SimpleFeatureFlagProvider>
          <TestComponent />
        </SimpleFeatureFlagProvider>
      )

      expect(screen.getByTestId('beta-features-flag')).toHaveTextContent(
        'beta_features: disabled'
      )

      await user.click(screen.getByTestId('toggle-beta-btn'))

      await waitFor(() => {
        expect(screen.getByTestId('beta-features-flag')).toHaveTextContent(
          'beta_features: enabled'
        )
      })
    })

    it('toggles multiple flags independently', async () => {
      mockUseAuth.mockReturnValue({ user: null })
      const user = userEvent.setup()

      render(
        <SimpleFeatureFlagProvider>
          <TestComponent />
        </SimpleFeatureFlagProvider>
      )

      await user.click(screen.getByTestId('toggle-new-ui-btn'))
      await user.click(screen.getByTestId('toggle-beta-btn'))

      await waitFor(() => {
        expect(screen.getByTestId('new-ui-flag')).toHaveTextContent(
          'new_ui: disabled'
        )
        expect(screen.getByTestId('beta-features-flag')).toHaveTextContent(
          'beta_features: enabled'
        )
      })
    })

    it('maintains toggle state across renders', async () => {
      mockUseAuth.mockReturnValue({ user: null })
      const user = userEvent.setup()

      const { rerender } = render(
        <SimpleFeatureFlagProvider>
          <TestComponent />
        </SimpleFeatureFlagProvider>
      )

      await user.click(screen.getByTestId('toggle-beta-btn'))

      await waitFor(() => {
        expect(screen.getByTestId('beta-features-flag')).toHaveTextContent(
          'beta_features: enabled'
        )
      })

      rerender(
        <SimpleFeatureFlagProvider>
          <TestComponent />
        </SimpleFeatureFlagProvider>
      )

      await waitFor(() => {
        expect(screen.getByTestId('beta-features-flag')).toHaveTextContent(
          'beta_features: enabled'
        )
      })
    })
  })

  describe('Integration Tests', () => {
    it('combines multiple feature flags in conditional rendering', () => {
      mockUseAuth.mockReturnValue({ user: { role: 'admin' } })

      function ComplexComponent() {
        const newUi = useFeatureFlag('new_ui')
        const analytics = useFeatureFlag('advanced_analytics')

        return (
          <div>
            {newUi && analytics && (
              <div data-testid="combined-feature">Advanced Dashboard</div>
            )}
            {newUi && !analytics && (
              <div data-testid="partial-feature">Basic Dashboard</div>
            )}
          </div>
        )
      }

      render(
        <SimpleFeatureFlagProvider>
          <ComplexComponent />
        </SimpleFeatureFlagProvider>
      )

      expect(screen.getByTestId('combined-feature')).toBeInTheDocument()
      expect(screen.queryByTestId('partial-feature')).not.toBeInTheDocument()
    })

    it('handles real-world dashboard scenario', () => {
      mockUseAuth.mockReturnValue({ user: { role: 'admin' } })

      function Dashboard() {
        const newUi = useFeatureFlag('new_ui')
        const analytics = useFeatureFlag('advanced_analytics')
        const beta = useFeatureFlag('beta_features')

        return (
          <div>
            <h1 data-testid="dashboard-title">Dashboard</h1>
            {newUi && <div data-testid="new-nav">New Navigation</div>}
            {analytics && (
              <div data-testid="analytics-panel">Analytics Panel</div>
            )}
            {beta && <div data-testid="beta-badge">Beta Features</div>}
          </div>
        )
      }

      render(
        <SimpleFeatureFlagProvider>
          <Dashboard />
        </SimpleFeatureFlagProvider>
      )

      expect(screen.getByTestId('dashboard-title')).toBeInTheDocument()
      expect(screen.getByTestId('new-nav')).toBeInTheDocument()
      expect(screen.getByTestId('analytics-panel')).toBeInTheDocument()
      expect(screen.queryByTestId('beta-badge')).not.toBeInTheDocument()
    })

    it('gracefully handles missing auth context', () => {
      mockUseAuth.mockReturnValue({})

      render(
        <SimpleFeatureFlagProvider>
          <TestComponent />
        </SimpleFeatureFlagProvider>
      )

      expect(screen.getByTestId('flags-count')).toHaveTextContent('Flags: 4')
    })

    it('works with nested providers', () => {
      mockUseAuth.mockReturnValue({ user: null })

      function InnerComponent() {
        const newUi = useFeatureFlag('new_ui')
        return <div data-testid="inner">{newUi ? 'yes' : 'no'}</div>
      }

      function OuterComponent() {
        return (
          <div>
            <div data-testid="outer">outer</div>
            <InnerComponent />
          </div>
        )
      }

      render(
        <SimpleFeatureFlagProvider>
          <OuterComponent />
        </SimpleFeatureFlagProvider>
      )

      expect(screen.getByTestId('outer')).toHaveTextContent('outer')
      expect(screen.getByTestId('inner')).toHaveTextContent('yes')
    })
  })
})

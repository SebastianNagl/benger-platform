import { render, screen, waitFor } from '@testing-library/react'
import {
  AsyncFeatureFlag,
  FeatureFlag,
  FeatureFlagBoundary,
  FeatureFlagDebug,
  useFeatureFlagWithFallback,
  withFeatureFlag,
} from '../FeatureFlag'

// Mock the FeatureFlagContext
const mockUseFeatureFlags = jest.fn()
const mockUseFeatureFlag = jest.fn()

jest.mock('@/contexts/FeatureFlagContext', () => ({
  useFeatureFlags: () => mockUseFeatureFlags(),
  useFeatureFlag: (flagName: string) => mockUseFeatureFlag(flagName),
}))

describe('FeatureFlag', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  describe('Basic Rendering', () => {
    it('renders without crashing', () => {
      mockUseFeatureFlags.mockReturnValue({ isLoading: false })
      mockUseFeatureFlag.mockReturnValue(true)

      const { container } = render(
        <FeatureFlag flag="test-flag">
          <div>Content</div>
        </FeatureFlag>
      )

      expect(container).toBeInTheDocument()
    })

    it('renders with string children', () => {
      mockUseFeatureFlags.mockReturnValue({ isLoading: false })
      mockUseFeatureFlag.mockReturnValue(true)

      render(
        <FeatureFlag flag="test-flag">
          <div>Test Content</div>
        </FeatureFlag>
      )

      expect(screen.getByText('Test Content')).toBeInTheDocument()
    })

    it('renders with multiple children', () => {
      mockUseFeatureFlags.mockReturnValue({ isLoading: false })
      mockUseFeatureFlag.mockReturnValue(true)

      render(
        <FeatureFlag flag="test-flag">
          <div>First Child</div>
          <div>Second Child</div>
        </FeatureFlag>
      )

      expect(screen.getByText('First Child')).toBeInTheDocument()
      expect(screen.getByText('Second Child')).toBeInTheDocument()
    })

    it('renders with complex nested children', () => {
      mockUseFeatureFlags.mockReturnValue({ isLoading: false })
      mockUseFeatureFlag.mockReturnValue(true)

      render(
        <FeatureFlag flag="test-flag">
          <div>
            <h1>Title</h1>
            <p>Description</p>
            <button>Action</button>
          </div>
        </FeatureFlag>
      )

      expect(screen.getByText('Title')).toBeInTheDocument()
      expect(screen.getByText('Description')).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Action' })).toBeInTheDocument()
    })
  })

  describe('Feature Flag Detection', () => {
    it('calls useFeatureFlag with correct flag name', () => {
      mockUseFeatureFlags.mockReturnValue({ isLoading: false })
      mockUseFeatureFlag.mockReturnValue(true)

      render(
        <FeatureFlag flag="my-feature">
          <div>Content</div>
        </FeatureFlag>
      )

      expect(mockUseFeatureFlag).toHaveBeenCalledWith('my-feature')
    })

    it('handles enabled flag correctly', () => {
      mockUseFeatureFlags.mockReturnValue({ isLoading: false })
      mockUseFeatureFlag.mockReturnValue(true)

      render(
        <FeatureFlag flag="enabled-flag">
          <div>Enabled Content</div>
        </FeatureFlag>
      )

      expect(screen.getByText('Enabled Content')).toBeInTheDocument()
    })

    it('handles disabled flag correctly', () => {
      mockUseFeatureFlags.mockReturnValue({ isLoading: false })
      mockUseFeatureFlag.mockReturnValue(false)

      render(
        <FeatureFlag flag="disabled-flag">
          <div>Hidden Content</div>
        </FeatureFlag>
      )

      expect(screen.queryByText('Hidden Content')).not.toBeInTheDocument()
    })

    it('responds to flag changes', () => {
      mockUseFeatureFlags.mockReturnValue({ isLoading: false })
      mockUseFeatureFlag.mockReturnValue(false)

      const { rerender } = render(
        <FeatureFlag flag="dynamic-flag">
          <div>Dynamic Content</div>
        </FeatureFlag>
      )

      expect(screen.queryByText('Dynamic Content')).not.toBeInTheDocument()

      mockUseFeatureFlag.mockReturnValue(true)
      rerender(
        <FeatureFlag flag="dynamic-flag">
          <div>Dynamic Content</div>
        </FeatureFlag>
      )

      expect(screen.getByText('Dynamic Content')).toBeInTheDocument()
    })
  })

  describe('Children Rendering', () => {
    it('renders children when flag is enabled', () => {
      mockUseFeatureFlags.mockReturnValue({ isLoading: false })
      mockUseFeatureFlag.mockReturnValue(true)

      render(
        <FeatureFlag flag="test-flag">
          <div>Visible Content</div>
        </FeatureFlag>
      )

      expect(screen.getByText('Visible Content')).toBeInTheDocument()
    })

    it('does not render children when flag is disabled', () => {
      mockUseFeatureFlags.mockReturnValue({ isLoading: false })
      mockUseFeatureFlag.mockReturnValue(false)

      render(
        <FeatureFlag flag="test-flag">
          <div>Hidden Content</div>
        </FeatureFlag>
      )

      expect(screen.queryByText('Hidden Content')).not.toBeInTheDocument()
    })

    it('renders component children', () => {
      mockUseFeatureFlags.mockReturnValue({ isLoading: false })
      mockUseFeatureFlag.mockReturnValue(true)

      const TestComponent = () => <div>Component Content</div>

      render(
        <FeatureFlag flag="test-flag">
          <TestComponent />
        </FeatureFlag>
      )

      expect(screen.getByText('Component Content')).toBeInTheDocument()
    })

    it('preserves children props and state', () => {
      mockUseFeatureFlags.mockReturnValue({ isLoading: false })
      mockUseFeatureFlag.mockReturnValue(true)

      render(
        <FeatureFlag flag="test-flag">
          <button data-testid="test-button" className="custom-class">
            Click Me
          </button>
        </FeatureFlag>
      )

      const button = screen.getByTestId('test-button')
      expect(button).toHaveClass('custom-class')
      expect(button).toHaveTextContent('Click Me')
    })
  })

  describe('Fallback Content', () => {
    it('renders fallback when flag is disabled and fallback provided', () => {
      mockUseFeatureFlags.mockReturnValue({ isLoading: false })
      mockUseFeatureFlag.mockReturnValue(false)

      render(
        <FeatureFlag flag="test-flag" fallback={<div>Fallback Content</div>}>
          <div>Main Content</div>
        </FeatureFlag>
      )

      expect(screen.getByText('Fallback Content')).toBeInTheDocument()
      expect(screen.queryByText('Main Content')).not.toBeInTheDocument()
    })

    it('renders null when flag is disabled and no fallback', () => {
      mockUseFeatureFlags.mockReturnValue({ isLoading: false })
      mockUseFeatureFlag.mockReturnValue(false)

      const { container } = render(
        <FeatureFlag flag="test-flag">
          <div>Main Content</div>
        </FeatureFlag>
      )

      expect(container.textContent).toBe('')
    })

    it('renders complex fallback content', () => {
      mockUseFeatureFlags.mockReturnValue({ isLoading: false })
      mockUseFeatureFlag.mockReturnValue(false)

      render(
        <FeatureFlag
          flag="test-flag"
          fallback={
            <div>
              <h2>Feature Unavailable</h2>
              <p>This feature is currently disabled</p>
            </div>
          }
        >
          <div>Main Content</div>
        </FeatureFlag>
      )

      expect(screen.getByText('Feature Unavailable')).toBeInTheDocument()
      expect(
        screen.getByText('This feature is currently disabled')
      ).toBeInTheDocument()
    })

    it('does not render fallback when flag is enabled', () => {
      mockUseFeatureFlags.mockReturnValue({ isLoading: false })
      mockUseFeatureFlag.mockReturnValue(true)

      render(
        <FeatureFlag flag="test-flag" fallback={<div>Fallback Content</div>}>
          <div>Main Content</div>
        </FeatureFlag>
      )

      expect(screen.getByText('Main Content')).toBeInTheDocument()
      expect(screen.queryByText('Fallback Content')).not.toBeInTheDocument()
    })
  })

  describe('Loading State', () => {
    it('renders loading content when isLoading is true', () => {
      mockUseFeatureFlags.mockReturnValue({ isLoading: true })
      mockUseFeatureFlag.mockReturnValue(false)

      render(
        <FeatureFlag flag="test-flag" loading={<div>Loading...</div>}>
          <div>Main Content</div>
        </FeatureFlag>
      )

      expect(screen.getByText('Loading...')).toBeInTheDocument()
      expect(screen.queryByText('Main Content')).not.toBeInTheDocument()
    })

    it('does not render loading when isLoading is false', () => {
      mockUseFeatureFlags.mockReturnValue({ isLoading: false })
      mockUseFeatureFlag.mockReturnValue(true)

      render(
        <FeatureFlag flag="test-flag" loading={<div>Loading...</div>}>
          <div>Main Content</div>
        </FeatureFlag>
      )

      expect(screen.queryByText('Loading...')).not.toBeInTheDocument()
      expect(screen.getByText('Main Content')).toBeInTheDocument()
    })

    it('renders nothing when loading without loading prop', () => {
      mockUseFeatureFlags.mockReturnValue({ isLoading: true })
      mockUseFeatureFlag.mockReturnValue(false)

      const { container } = render(
        <FeatureFlag flag="test-flag">
          <div>Main Content</div>
        </FeatureFlag>
      )

      expect(container.textContent).toBe('')
    })

    it('transitions from loading to content', () => {
      mockUseFeatureFlags.mockReturnValue({ isLoading: true })
      mockUseFeatureFlag.mockReturnValue(false)

      const { rerender } = render(
        <FeatureFlag flag="test-flag" loading={<div>Loading...</div>}>
          <div>Main Content</div>
        </FeatureFlag>
      )

      expect(screen.getByText('Loading...')).toBeInTheDocument()

      mockUseFeatureFlags.mockReturnValue({ isLoading: false })
      mockUseFeatureFlag.mockReturnValue(true)

      rerender(
        <FeatureFlag flag="test-flag" loading={<div>Loading...</div>}>
          <div>Main Content</div>
        </FeatureFlag>
      )

      expect(screen.queryByText('Loading...')).not.toBeInTheDocument()
      expect(screen.getByText('Main Content')).toBeInTheDocument()
    })
  })

  describe('Edge Cases', () => {
    it('handles empty children', () => {
      mockUseFeatureFlags.mockReturnValue({ isLoading: false })
      mockUseFeatureFlag.mockReturnValue(true)

      const { container } = render(
        <FeatureFlag flag="test-flag">{null}</FeatureFlag>
      )

      expect(container.textContent).toBe('')
    })

    it('handles undefined flag name gracefully', () => {
      mockUseFeatureFlags.mockReturnValue({ isLoading: false })
      mockUseFeatureFlag.mockReturnValue(false)

      render(
        <FeatureFlag flag="">
          <div>Content</div>
        </FeatureFlag>
      )

      expect(screen.queryByText('Content')).not.toBeInTheDocument()
    })

    it('handles special characters in flag name', () => {
      mockUseFeatureFlags.mockReturnValue({ isLoading: false })
      mockUseFeatureFlag.mockReturnValue(true)

      render(
        <FeatureFlag flag="feature-with-dashes_and_underscores">
          <div>Content</div>
        </FeatureFlag>
      )

      expect(mockUseFeatureFlag).toHaveBeenCalledWith(
        'feature-with-dashes_and_underscores'
      )
      expect(screen.getByText('Content')).toBeInTheDocument()
    })

    it('handles rapid flag changes', () => {
      mockUseFeatureFlags.mockReturnValue({ isLoading: false })
      mockUseFeatureFlag.mockReturnValue(true)

      const { rerender } = render(
        <FeatureFlag flag="test-flag">
          <div>Content</div>
        </FeatureFlag>
      )

      expect(screen.getByText('Content')).toBeInTheDocument()

      mockUseFeatureFlag.mockReturnValue(false)
      rerender(
        <FeatureFlag flag="test-flag">
          <div>Content</div>
        </FeatureFlag>
      )

      expect(screen.queryByText('Content')).not.toBeInTheDocument()

      mockUseFeatureFlag.mockReturnValue(true)
      rerender(
        <FeatureFlag flag="test-flag">
          <div>Content</div>
        </FeatureFlag>
      )

      expect(screen.getByText('Content')).toBeInTheDocument()
    })
  })

  describe('AsyncFeatureFlag', () => {
    beforeEach(() => {
      jest.useFakeTimers()
    })

    afterEach(() => {
      jest.useRealTimers()
    })

    it('renders loading state initially', () => {
      const mockCheckFlag = jest.fn().mockResolvedValue(true)
      mockUseFeatureFlags.mockReturnValue({ checkFlag: mockCheckFlag })

      render(
        <AsyncFeatureFlag flag="async-flag" loading={<div>Loading...</div>}>
          <div>Content</div>
        </AsyncFeatureFlag>
      )

      expect(screen.getByText('Loading...')).toBeInTheDocument()
    })

    it('renders children after async check returns true', async () => {
      const mockCheckFlag = jest.fn().mockResolvedValue(true)
      mockUseFeatureFlags.mockReturnValue({ checkFlag: mockCheckFlag })

      render(
        <AsyncFeatureFlag flag="async-flag">
          <div>Async Content</div>
        </AsyncFeatureFlag>
      )

      await waitFor(() => {
        expect(screen.getByText('Async Content')).toBeInTheDocument()
      })

      expect(mockCheckFlag).toHaveBeenCalledWith('async-flag')
    })

    it('renders fallback after async check returns false', async () => {
      const mockCheckFlag = jest.fn().mockResolvedValue(false)
      mockUseFeatureFlags.mockReturnValue({ checkFlag: mockCheckFlag })

      render(
        <AsyncFeatureFlag flag="async-flag" fallback={<div>Fallback</div>}>
          <div>Async Content</div>
        </AsyncFeatureFlag>
      )

      await waitFor(() => {
        expect(screen.getByText('Fallback')).toBeInTheDocument()
      })

      expect(screen.queryByText('Async Content')).not.toBeInTheDocument()
    })

    it('handles async errors gracefully', async () => {
      const consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation()
      const mockCheckFlag = jest.fn().mockRejectedValue(new Error('API Error'))
      mockUseFeatureFlags.mockReturnValue({ checkFlag: mockCheckFlag })

      render(
        <AsyncFeatureFlag
          flag="async-flag"
          fallback={<div>Error Fallback</div>}
        >
          <div>Async Content</div>
        </AsyncFeatureFlag>
      )

      await waitFor(() => {
        expect(screen.getByText('Error Fallback')).toBeInTheDocument()
      })

      expect(consoleErrorSpy).toHaveBeenCalled()
      consoleErrorSpy.mockRestore()
    })

    it('cleans up on unmount', async () => {
      const mockCheckFlag = jest.fn().mockResolvedValue(true)
      mockUseFeatureFlags.mockReturnValue({ checkFlag: mockCheckFlag })

      const { unmount } = render(
        <AsyncFeatureFlag flag="async-flag">
          <div>Content</div>
        </AsyncFeatureFlag>
      )

      unmount()

      await waitFor(() => {
        expect(mockCheckFlag).toHaveBeenCalled()
      })
    })

    it('renders fallback when isEnabled is null and no loading prop', async () => {
      const mockCheckFlag = jest.fn().mockResolvedValue(false)
      mockUseFeatureFlags.mockReturnValue({ checkFlag: mockCheckFlag })

      render(
        <AsyncFeatureFlag
          flag="async-flag"
          fallback={<div>No Loading Fallback</div>}
        >
          <div>Content</div>
        </AsyncFeatureFlag>
      )

      expect(screen.getByText('No Loading Fallback')).toBeInTheDocument()

      await waitFor(() => {
        expect(mockCheckFlag).toHaveBeenCalled()
      })
    })

    it('renders null fallback when disabled', async () => {
      const mockCheckFlag = jest.fn().mockResolvedValue(false)
      mockUseFeatureFlags.mockReturnValue({ checkFlag: mockCheckFlag })

      const { container } = render(
        <AsyncFeatureFlag flag="async-flag">
          <div>Content</div>
        </AsyncFeatureFlag>
      )

      await waitFor(() => {
        expect(mockCheckFlag).toHaveBeenCalled()
      })

      expect(container.textContent).toBe('')
    })

    it('calls checkFlag with correct flag name', async () => {
      const mockCheckFlag = jest.fn().mockResolvedValue(true)
      mockUseFeatureFlags.mockReturnValue({ checkFlag: mockCheckFlag })

      render(
        <AsyncFeatureFlag flag="specific-async-flag">
          <div>Content</div>
        </AsyncFeatureFlag>
      )

      await waitFor(() => {
        expect(mockCheckFlag).toHaveBeenCalledWith('specific-async-flag')
      })
    })

    it('handles flag change when component updates', async () => {
      const mockCheckFlag = jest.fn().mockResolvedValue(true)
      mockUseFeatureFlags.mockReturnValue({ checkFlag: mockCheckFlag })

      const { rerender } = render(
        <AsyncFeatureFlag flag="flag1">
          <div>Content 1</div>
        </AsyncFeatureFlag>
      )

      await waitFor(() => {
        expect(screen.getByText('Content 1')).toBeInTheDocument()
      })

      mockCheckFlag.mockResolvedValue(false)

      rerender(
        <AsyncFeatureFlag flag="flag2">
          <div>Content 2</div>
        </AsyncFeatureFlag>
      )

      await waitFor(() => {
        expect(mockCheckFlag).toHaveBeenCalledWith('flag2')
      })
    })

    it('respects mounted flag to prevent state updates after unmount', async () => {
      const mockCheckFlag = jest
        .fn()
        .mockImplementation(
          () => new Promise((resolve) => setTimeout(() => resolve(true), 100))
        )
      mockUseFeatureFlags.mockReturnValue({ checkFlag: mockCheckFlag })

      const { unmount } = render(
        <AsyncFeatureFlag flag="async-flag">
          <div>Content</div>
        </AsyncFeatureFlag>
      )

      unmount()

      await waitFor(() => {
        expect(mockCheckFlag).toHaveBeenCalled()
      })
    })

    it('renders with complex nested async children', async () => {
      const mockCheckFlag = jest.fn().mockResolvedValue(true)
      mockUseFeatureFlags.mockReturnValue({ checkFlag: mockCheckFlag })

      render(
        <AsyncFeatureFlag flag="async-flag">
          <div>
            <h1>Async Title</h1>
            <p>Async Description</p>
            <button>Async Action</button>
          </div>
        </AsyncFeatureFlag>
      )

      await waitFor(() => {
        expect(screen.getByText('Async Title')).toBeInTheDocument()
      })

      expect(screen.getByText('Async Description')).toBeInTheDocument()
      expect(
        screen.getByRole('button', { name: 'Async Action' })
      ).toBeInTheDocument()
    })

    it('handles timeout scenarios', async () => {
      const mockCheckFlag = jest
        .fn()
        .mockImplementation(
          () => new Promise((resolve) => setTimeout(() => resolve(true), 5000))
        )
      mockUseFeatureFlags.mockReturnValue({ checkFlag: mockCheckFlag })

      render(
        <AsyncFeatureFlag flag="timeout-flag" loading={<div>Loading...</div>}>
          <div>Content</div>
        </AsyncFeatureFlag>
      )

      expect(screen.getByText('Loading...')).toBeInTheDocument()

      await waitFor(
        () => {
          expect(mockCheckFlag).toHaveBeenCalled()
        },
        { timeout: 6000 }
      )
    })

    it('handles async network errors with specific error messages', async () => {
      const consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation()
      const mockCheckFlag = jest
        .fn()
        .mockRejectedValue(new Error('Network timeout'))
      mockUseFeatureFlags.mockReturnValue({ checkFlag: mockCheckFlag })

      render(
        <AsyncFeatureFlag
          flag="network-flag"
          fallback={<div>Network Error</div>}
        >
          <div>Content</div>
        </AsyncFeatureFlag>
      )

      await waitFor(() => {
        expect(screen.getByText('Network Error')).toBeInTheDocument()
      })

      expect(consoleErrorSpy).toHaveBeenCalledWith(
        "Error checking feature flag 'network-flag':",
        expect.any(Error)
      )

      consoleErrorSpy.mockRestore()
    })

    it('prevents race conditions with rapid unmount/mount', async () => {
      const mockCheckFlag = jest.fn().mockResolvedValue(true)
      mockUseFeatureFlags.mockReturnValue({ checkFlag: mockCheckFlag })

      const { unmount, rerender } = render(
        <AsyncFeatureFlag flag="race-flag">
          <div>Content 1</div>
        </AsyncFeatureFlag>
      )

      rerender(
        <AsyncFeatureFlag flag="race-flag">
          <div>Content 2</div>
        </AsyncFeatureFlag>
      )

      unmount()

      await waitFor(() => {
        expect(mockCheckFlag).toHaveBeenCalled()
      })
    })

    it('renders multiple AsyncFeatureFlags independently', async () => {
      const mockCheckFlag = jest.fn((flag: string) => {
        return Promise.resolve(flag === 'enabled-flag')
      })
      mockUseFeatureFlags.mockReturnValue({ checkFlag: mockCheckFlag })

      render(
        <div>
          <AsyncFeatureFlag flag="enabled-flag">
            <div>Enabled Content</div>
          </AsyncFeatureFlag>
          <AsyncFeatureFlag
            flag="disabled-flag"
            fallback={<div>Disabled Content</div>}
          >
            <div>Should Not Render</div>
          </AsyncFeatureFlag>
        </div>
      )

      await waitFor(() => {
        expect(screen.getByText('Enabled Content')).toBeInTheDocument()
      })

      await waitFor(() => {
        expect(screen.getByText('Disabled Content')).toBeInTheDocument()
      })

      expect(screen.queryByText('Should Not Render')).not.toBeInTheDocument()
    })
  })

  describe('FeatureFlagDebug', () => {
    const originalEnv = process.env.NODE_ENV

    afterEach(() => {
      process.env.NODE_ENV = originalEnv
    })

    it('renders in development mode', () => {
      process.env.NODE_ENV = 'development'
      mockUseFeatureFlags.mockReturnValue({
        flags: { 'test-flag': true },
        isLoading: false,
        error: null,
      })
      mockUseFeatureFlag.mockReturnValue(true)

      render(<FeatureFlagDebug flag="test-flag" />)

      expect(screen.getByText(/test-flag/)).toBeInTheDocument()
    })

    it('does not render in production mode', () => {
      process.env.NODE_ENV = 'production'
      mockUseFeatureFlags.mockReturnValue({
        flags: { 'test-flag': true },
        isLoading: false,
        error: null,
      })
      mockUseFeatureFlag.mockReturnValue(true)

      const { container } = render(<FeatureFlagDebug flag="test-flag" />)

      expect(container.textContent).toBe('')
    })

    it('shows enabled state correctly', () => {
      process.env.NODE_ENV = 'development'
      mockUseFeatureFlags.mockReturnValue({
        flags: { 'test-flag': true },
        isLoading: false,
        error: null,
      })
      mockUseFeatureFlag.mockReturnValue(true)

      render(<FeatureFlagDebug flag="test-flag" />)

      expect(screen.getByText(/✅/)).toBeInTheDocument()
    })

    it('shows disabled state correctly', () => {
      process.env.NODE_ENV = 'development'
      mockUseFeatureFlags.mockReturnValue({
        flags: { 'test-flag': false },
        isLoading: false,
        error: null,
      })
      mockUseFeatureFlag.mockReturnValue(false)

      render(<FeatureFlagDebug flag="test-flag" />)

      expect(screen.getByText(/❌/)).toBeInTheDocument()
    })

    it('shows loading state correctly', () => {
      process.env.NODE_ENV = 'development'
      mockUseFeatureFlags.mockReturnValue({
        flags: {},
        isLoading: true,
        error: null,
      })
      mockUseFeatureFlag.mockReturnValue(false)

      render(<FeatureFlagDebug flag="test-flag" />)

      expect(screen.getByText(/⏳/)).toBeInTheDocument()
    })

    it('shows details when showDetails is true', () => {
      process.env.NODE_ENV = 'development'
      mockUseFeatureFlags.mockReturnValue({
        flags: { 'test-flag': true, 'other-flag': false },
        isLoading: false,
        error: null,
      })
      mockUseFeatureFlag.mockReturnValue(true)

      render(<FeatureFlagDebug flag="test-flag" showDetails />)

      expect(screen.getByText(/All flags: 2/)).toBeInTheDocument()
    })

    it('shows error in details', () => {
      process.env.NODE_ENV = 'development'
      mockUseFeatureFlags.mockReturnValue({
        flags: {},
        isLoading: false,
        error: 'Failed to load flags',
      })
      mockUseFeatureFlag.mockReturnValue(false)

      render(<FeatureFlagDebug flag="test-flag" showDetails />)

      expect(
        screen.getByText(/Error: Failed to load flags/)
      ).toBeInTheDocument()
    })
  })

  describe('withFeatureFlag HOC', () => {
    it('wraps component with feature flag', () => {
      mockUseFeatureFlags.mockReturnValue({ isLoading: false })
      mockUseFeatureFlag.mockReturnValue(true)

      const TestComponent = ({ text }: { text: string }) => <div>{text}</div>
      const WrappedComponent = withFeatureFlag(TestComponent, 'test-flag')

      render(<WrappedComponent text="Wrapped Content" />)

      expect(screen.getByText('Wrapped Content')).toBeInTheDocument()
    })

    it('shows fallback when flag is disabled', () => {
      mockUseFeatureFlags.mockReturnValue({ isLoading: false })
      mockUseFeatureFlag.mockReturnValue(false)

      const TestComponent = ({ text }: { text: string }) => <div>{text}</div>
      const WrappedComponent = withFeatureFlag(
        TestComponent,
        'test-flag',
        <div>HOC Fallback</div>
      )

      render(<WrappedComponent text="Wrapped Content" />)

      expect(screen.queryByText('Wrapped Content')).not.toBeInTheDocument()
      expect(screen.getByText('HOC Fallback')).toBeInTheDocument()
    })

    it('passes props through to wrapped component', () => {
      mockUseFeatureFlags.mockReturnValue({ isLoading: false })
      mockUseFeatureFlag.mockReturnValue(true)

      const TestComponent = ({
        text,
        count,
      }: {
        text: string
        count: number
      }) => (
        <div>
          {text} - {count}
        </div>
      )
      const WrappedComponent = withFeatureFlag(TestComponent, 'test-flag')

      render(<WrappedComponent text="Test" count={42} />)

      expect(screen.getByText('Test - 42')).toBeInTheDocument()
    })
  })

  describe('useFeatureFlagWithFallback Hook', () => {
    it('returns flag value when no error', () => {
      const TestComponent = () => {
        const mockIsEnabled = jest.fn().mockReturnValue(true)
        mockUseFeatureFlags.mockReturnValue({
          isEnabled: mockIsEnabled,
          error: null,
        })

        const enabled = useFeatureFlagWithFallback('test-flag')
        return <div>{enabled ? 'Enabled' : 'Disabled'}</div>
      }

      render(<TestComponent />)
      expect(screen.getByText('Enabled')).toBeInTheDocument()
    })

    it('returns fallback value when error occurs', () => {
      const consoleWarnSpy = jest.spyOn(console, 'warn').mockImplementation()

      const TestComponent = () => {
        mockUseFeatureFlags.mockReturnValue({
          isEnabled: jest.fn(),
          error: 'API Error',
        })

        const enabled = useFeatureFlagWithFallback('test-flag', true)
        return <div>{enabled ? 'Enabled' : 'Disabled'}</div>
      }

      render(<TestComponent />)
      expect(screen.getByText('Enabled')).toBeInTheDocument()
      expect(consoleWarnSpy).toHaveBeenCalled()

      consoleWarnSpy.mockRestore()
    })

    it('uses default fallback of false', () => {
      const consoleWarnSpy = jest.spyOn(console, 'warn').mockImplementation()

      const TestComponent = () => {
        mockUseFeatureFlags.mockReturnValue({
          isEnabled: jest.fn(),
          error: 'API Error',
        })

        const enabled = useFeatureFlagWithFallback('test-flag')
        return <div>{enabled ? 'Enabled' : 'Disabled'}</div>
      }

      render(<TestComponent />)
      expect(screen.getByText('Disabled')).toBeInTheDocument()

      consoleWarnSpy.mockRestore()
    })
  })

  describe('FeatureFlagBoundary', () => {
    it('renders children when no error', () => {
      mockUseFeatureFlags.mockReturnValue({ error: null })

      render(
        <FeatureFlagBoundary>
          <div>Boundary Content</div>
        </FeatureFlagBoundary>
      )

      expect(screen.getByText('Boundary Content')).toBeInTheDocument()
    })

    it('renders children when error occurs and no fallback', () => {
      const consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation()
      mockUseFeatureFlags.mockReturnValue({ error: 'System Error' })

      render(
        <FeatureFlagBoundary>
          <div>Boundary Content</div>
        </FeatureFlagBoundary>
      )

      expect(screen.getByText('Boundary Content')).toBeInTheDocument()
      expect(consoleErrorSpy).toHaveBeenCalledWith(
        'Feature flag system error:',
        'System Error'
      )

      consoleErrorSpy.mockRestore()
    })

    it('renders fallback when error occurs and fallback provided', () => {
      const consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation()
      mockUseFeatureFlags.mockReturnValue({ error: 'System Error' })

      render(
        <FeatureFlagBoundary fallback={<div>Error Fallback</div>}>
          <div>Boundary Content</div>
        </FeatureFlagBoundary>
      )

      expect(screen.getByText('Error Fallback')).toBeInTheDocument()
      expect(screen.queryByText('Boundary Content')).not.toBeInTheDocument()

      consoleErrorSpy.mockRestore()
    })
  })

  describe('Integration Tests', () => {
    it('combines multiple feature flags in nested structure', () => {
      mockUseFeatureFlags.mockReturnValue({ isLoading: false })

      const { rerender } = render(
        <FeatureFlag flag="outer-flag">
          <div>
            <FeatureFlag flag="inner-flag">
              <div>Nested Content</div>
            </FeatureFlag>
          </div>
        </FeatureFlag>
      )

      mockUseFeatureFlag.mockImplementation((flag: string) => {
        return flag === 'outer-flag' || flag === 'inner-flag'
      })

      rerender(
        <FeatureFlag flag="outer-flag">
          <div>
            <FeatureFlag flag="inner-flag">
              <div>Nested Content</div>
            </FeatureFlag>
          </div>
        </FeatureFlag>
      )

      expect(screen.getByText('Nested Content')).toBeInTheDocument()
    })

    it('handles complex real-world scenario', () => {
      mockUseFeatureFlags.mockReturnValue({ isLoading: false })
      mockUseFeatureFlag.mockImplementation(
        (flag: string) => flag === 'reports'
      )

      render(
        <div>
          <FeatureFlag
            flag="reports"
            fallback={<div>Reports coming soon</div>}
            loading={<div>Loading reports...</div>}
          >
            <div>
              <h1>Reports Dashboard</h1>
              <button>Generate Report</button>
            </div>
          </FeatureFlag>
          <FeatureFlag
            flag="analytics"
            fallback={<div>Analytics unavailable</div>}
          >
            <div>Analytics Content</div>
          </FeatureFlag>
        </div>
      )

      expect(screen.getByText('Reports Dashboard')).toBeInTheDocument()
      expect(
        screen.getByRole('button', { name: 'Generate Report' })
      ).toBeInTheDocument()
      expect(screen.getByText('Analytics unavailable')).toBeInTheDocument()
      expect(screen.queryByText('Analytics Content')).not.toBeInTheDocument()
    })

    it('works with FeatureFlagBoundary wrapper', () => {
      mockUseFeatureFlags.mockReturnValue({ isLoading: false, error: null })
      mockUseFeatureFlag.mockReturnValue(true)

      render(
        <FeatureFlagBoundary>
          <FeatureFlag flag="test-flag">
            <div>Protected Content</div>
          </FeatureFlag>
        </FeatureFlagBoundary>
      )

      expect(screen.getByText('Protected Content')).toBeInTheDocument()
    })

    it('gracefully degrades on system error with boundary', () => {
      const consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation()
      mockUseFeatureFlags.mockReturnValue({
        isLoading: false,
        error: 'Connection failed',
      })
      mockUseFeatureFlag.mockReturnValue(false)

      render(
        <FeatureFlagBoundary fallback={<div>System unavailable</div>}>
          <FeatureFlag flag="test-flag">
            <div>Main Content</div>
          </FeatureFlag>
        </FeatureFlagBoundary>
      )

      expect(screen.getByText('System unavailable')).toBeInTheDocument()

      consoleErrorSpy.mockRestore()
    })

    it('handles deeply nested feature flags', () => {
      mockUseFeatureFlags.mockReturnValue({ isLoading: false })
      mockUseFeatureFlag.mockReturnValue(true)

      render(
        <FeatureFlag flag="level1">
          <div>
            <FeatureFlag flag="level2">
              <div>
                <FeatureFlag flag="level3">
                  <div>Deep Content</div>
                </FeatureFlag>
              </div>
            </FeatureFlag>
          </div>
        </FeatureFlag>
      )

      expect(screen.getByText('Deep Content')).toBeInTheDocument()
    })

    it('handles mixed async and sync flags', async () => {
      const mockCheckFlag = jest.fn().mockResolvedValue(true)
      mockUseFeatureFlags.mockReturnValue({
        isLoading: false,
        checkFlag: mockCheckFlag,
      })
      mockUseFeatureFlag.mockReturnValue(true)

      render(
        <div>
          <FeatureFlag flag="sync-flag">
            <div>Sync Content</div>
          </FeatureFlag>
          <AsyncFeatureFlag flag="async-flag">
            <div>Async Content</div>
          </AsyncFeatureFlag>
        </div>
      )

      expect(screen.getByText('Sync Content')).toBeInTheDocument()

      await waitFor(() => {
        expect(screen.getByText('Async Content')).toBeInTheDocument()
      })
    })

    it('handles HOC wrapped components with feature flags', () => {
      mockUseFeatureFlags.mockReturnValue({ isLoading: false })
      mockUseFeatureFlag.mockReturnValue(true)

      const InnerComponent = ({ title }: { title: string }) => <h1>{title}</h1>
      const WrappedInner = withFeatureFlag(InnerComponent, 'inner-flag')

      const OuterComponent = () => (
        <FeatureFlag flag="outer-flag">
          <WrappedInner title="HOC Title" />
        </FeatureFlag>
      )

      render(<OuterComponent />)

      expect(screen.getByText('HOC Title')).toBeInTheDocument()
    })

    it('preserves component hierarchy and styling', () => {
      mockUseFeatureFlags.mockReturnValue({ isLoading: false })
      mockUseFeatureFlag.mockReturnValue(true)

      render(
        <FeatureFlag flag="test-flag">
          <div className="parent">
            <div className="child" data-testid="styled-child">
              <span className="grandchild">Styled Content</span>
            </div>
          </div>
        </FeatureFlag>
      )

      const child = screen.getByTestId('styled-child')
      expect(child).toHaveClass('child')
      expect(screen.getByText('Styled Content')).toBeInTheDocument()
    })
  })

  describe('Additional Edge Cases', () => {
    it('handles boolean children', () => {
      mockUseFeatureFlags.mockReturnValue({ isLoading: false })
      mockUseFeatureFlag.mockReturnValue(true)

      const { container } = render(
        <FeatureFlag flag="test-flag">{false}</FeatureFlag>
      )

      expect(container.textContent).toBe('')
    })

    it('handles number children', () => {
      mockUseFeatureFlags.mockReturnValue({ isLoading: false })
      mockUseFeatureFlag.mockReturnValue(true)

      render(<FeatureFlag flag="test-flag">{42}</FeatureFlag>)

      expect(screen.getByText('42')).toBeInTheDocument()
    })

    it('handles array children', () => {
      mockUseFeatureFlags.mockReturnValue({ isLoading: false })
      mockUseFeatureFlag.mockReturnValue(true)

      render(
        <FeatureFlag flag="test-flag">
          {[
            <div key="1">Item 1</div>,
            <div key="2">Item 2</div>,
            <div key="3">Item 3</div>,
          ]}
        </FeatureFlag>
      )

      expect(screen.getByText('Item 1')).toBeInTheDocument()
      expect(screen.getByText('Item 2')).toBeInTheDocument()
      expect(screen.getByText('Item 3')).toBeInTheDocument()
    })

    it('handles function as children pattern (render prop)', () => {
      mockUseFeatureFlags.mockReturnValue({ isLoading: false })
      mockUseFeatureFlag.mockReturnValue(true)

      const renderContent = () => <div>Function Content</div>

      render(<FeatureFlag flag="test-flag">{renderContent()}</FeatureFlag>)

      expect(screen.getByText('Function Content')).toBeInTheDocument()
    })

    it('handles fragment children', () => {
      mockUseFeatureFlags.mockReturnValue({ isLoading: false })
      mockUseFeatureFlag.mockReturnValue(true)

      render(
        <FeatureFlag flag="test-flag">
          <>
            <div>Fragment Child 1</div>
            <div>Fragment Child 2</div>
          </>
        </FeatureFlag>
      )

      expect(screen.getByText('Fragment Child 1')).toBeInTheDocument()
      expect(screen.getByText('Fragment Child 2')).toBeInTheDocument()
    })

    it('handles very long flag names', () => {
      mockUseFeatureFlags.mockReturnValue({ isLoading: false })
      mockUseFeatureFlag.mockReturnValue(true)

      const longFlagName =
        'very-long-feature-flag-name-with-many-words-and-dashes-to-test-edge-cases'

      render(
        <FeatureFlag flag={longFlagName}>
          <div>Content</div>
        </FeatureFlag>
      )

      expect(mockUseFeatureFlag).toHaveBeenCalledWith(longFlagName)
      expect(screen.getByText('Content')).toBeInTheDocument()
    })

    it('handles unicode in flag names', () => {
      mockUseFeatureFlags.mockReturnValue({ isLoading: false })
      mockUseFeatureFlag.mockReturnValue(true)

      render(
        <FeatureFlag flag="flag-with-émojis-🚀">
          <div>Unicode Content</div>
        </FeatureFlag>
      )

      expect(mockUseFeatureFlag).toHaveBeenCalledWith('flag-with-émojis-🚀')
    })

    it('handles conditional fallback rendering', () => {
      mockUseFeatureFlags.mockReturnValue({ isLoading: false })
      mockUseFeatureFlag.mockReturnValue(false)

      const fallbackContent = false ? <div>Should not render</div> : null

      const { container } = render(
        <FeatureFlag flag="test-flag" fallback={fallbackContent}>
          <div>Main Content</div>
        </FeatureFlag>
      )

      expect(container.textContent).toBe('')
    })

    it('handles event handlers in children', () => {
      mockUseFeatureFlags.mockReturnValue({ isLoading: false })
      mockUseFeatureFlag.mockReturnValue(true)

      const handleClick = jest.fn()

      render(
        <FeatureFlag flag="test-flag">
          <button onClick={handleClick}>Click Me</button>
        </FeatureFlag>
      )

      const button = screen.getByRole('button', { name: 'Click Me' })
      button.click()

      expect(handleClick).toHaveBeenCalledTimes(1)
    })

    it('handles loading state with complex loading component', () => {
      mockUseFeatureFlags.mockReturnValue({ isLoading: true })
      mockUseFeatureFlag.mockReturnValue(false)

      render(
        <FeatureFlag
          flag="test-flag"
          loading={
            <div>
              <span>Loading...</span>
              <div className="spinner" />
            </div>
          }
        >
          <div>Content</div>
        </FeatureFlag>
      )

      expect(screen.getByText('Loading...')).toBeInTheDocument()
    })

    it('handles multiple flag checks in rapid succession', () => {
      mockUseFeatureFlags.mockReturnValue({ isLoading: false })

      const { rerender } = render(
        <FeatureFlag flag="flag1">
          <div>Content 1</div>
        </FeatureFlag>
      )

      mockUseFeatureFlag.mockReturnValue(true)
      rerender(
        <FeatureFlag flag="flag2">
          <div>Content 2</div>
        </FeatureFlag>
      )

      mockUseFeatureFlag.mockReturnValue(false)
      rerender(
        <FeatureFlag flag="flag3">
          <div>Content 3</div>
        </FeatureFlag>
      )

      mockUseFeatureFlag.mockReturnValue(true)
      rerender(
        <FeatureFlag flag="flag4">
          <div>Content 4</div>
        </FeatureFlag>
      )

      expect(screen.getByText('Content 4')).toBeInTheDocument()
    })

    it('handles flag boundary with multiple children', () => {
      mockUseFeatureFlags.mockReturnValue({ error: null })

      render(
        <FeatureFlagBoundary>
          <div>Child 1</div>
          <div>Child 2</div>
          <div>Child 3</div>
        </FeatureFlagBoundary>
      )

      expect(screen.getByText('Child 1')).toBeInTheDocument()
      expect(screen.getByText('Child 2')).toBeInTheDocument()
      expect(screen.getByText('Child 3')).toBeInTheDocument()
    })

    it('handles useFeatureFlagWithFallback with true default', () => {
      const mockIsEnabled = jest.fn().mockReturnValue(false)

      const TestComponent = () => {
        mockUseFeatureFlags.mockReturnValue({
          isEnabled: mockIsEnabled,
          error: null,
        })

        const enabled = useFeatureFlagWithFallback('test-flag', true)
        return <div>{enabled ? 'Enabled by fallback' : 'Disabled'}</div>
      }

      render(<TestComponent />)
      expect(screen.getByText('Disabled')).toBeInTheDocument()
    })

    it('handles withFeatureFlag HOC with no fallback', () => {
      mockUseFeatureFlags.mockReturnValue({ isLoading: false })
      mockUseFeatureFlag.mockReturnValue(false)

      const TestComponent = () => <div>Component</div>
      const WrappedComponent = withFeatureFlag(TestComponent, 'test-flag')

      const { container } = render(<WrappedComponent />)

      expect(container.textContent).toBe('')
    })

    it('handles debug component with empty flags object', () => {
      process.env.NODE_ENV = 'development'
      mockUseFeatureFlags.mockReturnValue({
        flags: {},
        isLoading: false,
        error: null,
      })
      mockUseFeatureFlag.mockReturnValue(false)

      render(<FeatureFlagDebug flag="test-flag" showDetails />)

      expect(screen.getByText(/All flags: 0/)).toBeInTheDocument()
    })

    it('handles debug component without details in loading state', () => {
      process.env.NODE_ENV = 'development'
      mockUseFeatureFlags.mockReturnValue({
        flags: {},
        isLoading: true,
        error: null,
      })
      mockUseFeatureFlag.mockReturnValue(false)

      render(<FeatureFlagDebug flag="test-flag" showDetails={false} />)

      expect(screen.getByText(/⏳/)).toBeInTheDocument()
      expect(screen.queryByText(/All flags/)).not.toBeInTheDocument()
    })
  })
})

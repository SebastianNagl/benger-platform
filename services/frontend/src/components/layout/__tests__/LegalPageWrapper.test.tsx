/**
 * @jest-environment jsdom
 */

import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { render, screen } from '@testing-library/react'
import { LegalPageWrapper } from '../LegalPageWrapper'

jest.mock('@/contexts/AuthContext')
jest.mock('@/contexts/I18nContext')

jest.mock('@/components/shared/Breadcrumb', () => ({
  Breadcrumb: ({ items }: any) => (
    <nav data-testid="breadcrumb">
      {items.map((item: any, idx: number) => (
        <span key={idx} data-testid={`breadcrumb-item-${idx}`}>
          {item.label}
        </span>
      ))}
    </nav>
  ),
}))

jest.mock('@/components/shared/ResponsiveContainer', () => ({
  ResponsiveContainer: ({
    children,
    size,
    className,
  }: {
    children: React.ReactNode
    size?: string
    className?: string
  }) => (
    <div
      data-testid="responsive-container"
      data-size={size}
      className={className}
    >
      {children}
    </div>
  ),
}))

jest.mock('@/stores', () => ({
  useUIStore: jest.fn(() => ({
    isSidebarHidden: false,
  })),
}))

const mockUseAuth = useAuth as jest.MockedFunction<typeof useAuth>
const mockUseI18n = useI18n as jest.MockedFunction<typeof useI18n>

describe('LegalPageWrapper Component', () => {
  const defaultProps = {
    titleKey: 'legal.imprint.title',
    breadcrumbLabel: 'Imprint',
    href: '/about/imprint',
    children: <div>Legal content</div>,
  }

  beforeEach(() => {
    jest.clearAllMocks()
    mockUseI18n.mockReturnValue({
      t: (key: string) => {
        const translations: Record<string, string> = {
          'navigation.dashboard': 'Home',
          'legal.imprint.title': 'Imprint',
          'legal.dataProtection.title': 'Data Protection',
        }
        return translations[key] || key
      },
      locale: 'en',
      setLocale: jest.fn(),
    } as any)
  })

  describe('Basic Rendering', () => {
    it('renders wrapper component', () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: false,
        login: jest.fn(),
        logout: jest.fn(),
        isInitialized: true,
      } as any)

      const { container } = render(<LegalPageWrapper {...defaultProps} />)
      expect(container).toBeInTheDocument()
    })

    it('renders children content', () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: false,
        login: jest.fn(),
        logout: jest.fn(),
        isInitialized: true,
      } as any)

      render(<LegalPageWrapper {...defaultProps} />)
      expect(screen.getByText('Legal content')).toBeInTheDocument()
    })

    it('renders without errors', () => {
      mockUseAuth.mockReturnValue({
        user: { id: '1', email: 'test@example.com' },
        isLoading: false,
        login: jest.fn(),
        logout: jest.fn(),
        isInitialized: true,
      } as any)

      expect(() => render(<LegalPageWrapper {...defaultProps} />)).not.toThrow()
    })
  })

  describe('Authenticated User Layout', () => {
    beforeEach(() => {
      mockUseAuth.mockReturnValue({
        user: { id: '1', email: 'test@example.com', name: 'Test User' },
        isLoading: false,
        login: jest.fn(),
        logout: jest.fn(),
        isInitialized: true,
      } as any)
    })

    it('renders ResponsiveContainer for authenticated users', () => {
      render(<LegalPageWrapper {...defaultProps} />)
      expect(screen.getByTestId('responsive-container')).toBeInTheDocument()
    })

    it('renders Breadcrumb for authenticated users', () => {
      render(<LegalPageWrapper {...defaultProps} />)
      expect(screen.getByTestId('breadcrumb')).toBeInTheDocument()
    })

    it('renders breadcrumb with correct items', () => {
      render(<LegalPageWrapper {...defaultProps} />)

      expect(screen.getByText('Home')).toBeInTheDocument()
      expect(screen.getByText('Imprint')).toBeInTheDocument()
    })

    it('renders two breadcrumb items', () => {
      render(<LegalPageWrapper {...defaultProps} />)

      expect(screen.getByTestId('breadcrumb-item-0')).toBeInTheDocument()
      expect(screen.getByTestId('breadcrumb-item-1')).toBeInTheDocument()
    })

    it('renders children in prose wrapper', () => {
      const { container } = render(<LegalPageWrapper {...defaultProps} />)

      const proseWrapper = container.querySelector('.prose')
      expect(proseWrapper).toBeInTheDocument()
      expect(proseWrapper).toHaveTextContent('Legal content')
    })

    it('applies correct size to ResponsiveContainer', () => {
      render(<LegalPageWrapper {...defaultProps} />)

      const container = screen.getByTestId('responsive-container')
      expect(container).toHaveAttribute('data-size', 'xl')
    })
  })

  describe('Unauthenticated User Layout', () => {
    beforeEach(() => {
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: false,
        login: jest.fn(),
        logout: jest.fn(),
        isInitialized: true,
      } as any)
    })

    it('does not render ResponsiveContainer for unauthenticated users', () => {
      render(<LegalPageWrapper {...defaultProps} />)
      expect(
        screen.queryByTestId('responsive-container')
      ).not.toBeInTheDocument()
    })

    it('does not render Breadcrumb for unauthenticated users', () => {
      render(<LegalPageWrapper {...defaultProps} />)
      expect(screen.queryByTestId('breadcrumb')).not.toBeInTheDocument()
    })

    it('renders children directly without wrapper', () => {
      render(<LegalPageWrapper {...defaultProps} />)

      expect(screen.getByText('Legal content')).toBeInTheDocument()
      expect(
        screen.queryByTestId('responsive-container')
      ).not.toBeInTheDocument()
    })

    it('renders only a fragment wrapper', () => {
      const { container } = render(<LegalPageWrapper {...defaultProps} />)

      // Should not have prose classes
      const proseWrapper = container.querySelector('.prose')
      expect(proseWrapper).not.toBeInTheDocument()
    })
  })

  describe('Props/Attributes', () => {
    beforeEach(() => {
      mockUseAuth.mockReturnValue({
        user: { id: '1', email: 'test@example.com' },
        isLoading: false,
        login: jest.fn(),
        logout: jest.fn(),
        isInitialized: true,
      } as any)
    })

    it('passes titleKey prop correctly', () => {
      const customProps = {
        ...defaultProps,
        titleKey: 'legal.dataProtection.title',
      }

      render(<LegalPageWrapper {...customProps} />)
      // titleKey is used by parent component, but not directly rendered
      expect(screen.getByTestId('breadcrumb')).toBeInTheDocument()
    })

    it('passes breadcrumbLabel to breadcrumb', () => {
      const customProps = {
        ...defaultProps,
        breadcrumbLabel: 'Custom Label',
      }

      render(<LegalPageWrapper {...customProps} />)
      expect(screen.getByText('Custom Label')).toBeInTheDocument()
    })

    it('passes href to breadcrumb', () => {
      const customProps = {
        ...defaultProps,
        href: '/about/custom-page',
      }

      render(<LegalPageWrapper {...customProps} />)
      expect(screen.getByTestId('breadcrumb')).toBeInTheDocument()
    })

    it('handles different breadcrumbLabel values', () => {
      const { rerender } = render(<LegalPageWrapper {...defaultProps} />)
      expect(screen.getByText('Imprint')).toBeInTheDocument()

      rerender(
        <LegalPageWrapper {...defaultProps} breadcrumbLabel="Data Protection" />
      )
      expect(screen.getByText('Data Protection')).toBeInTheDocument()
    })

    it('handles different href values', () => {
      const { rerender } = render(<LegalPageWrapper {...defaultProps} />)
      expect(screen.getByTestId('breadcrumb')).toBeInTheDocument()

      rerender(
        <LegalPageWrapper {...defaultProps} href="/about/data-protection" />
      )
      expect(screen.getByTestId('breadcrumb')).toBeInTheDocument()
    })
  })

  describe('Children Rendering', () => {
    beforeEach(() => {
      mockUseAuth.mockReturnValue({
        user: { id: '1', email: 'test@example.com' },
        isLoading: false,
        login: jest.fn(),
        logout: jest.fn(),
        isInitialized: true,
      } as any)
    })

    it('renders simple text children', () => {
      render(
        <LegalPageWrapper {...defaultProps}>
          <p>Simple text content</p>
        </LegalPageWrapper>
      )

      expect(screen.getByText('Simple text content')).toBeInTheDocument()
    })

    it('renders complex JSX children', () => {
      render(
        <LegalPageWrapper {...defaultProps}>
          <div>
            <h1>Title</h1>
            <p>Paragraph 1</p>
            <p>Paragraph 2</p>
          </div>
        </LegalPageWrapper>
      )

      expect(screen.getByText('Title')).toBeInTheDocument()
      expect(screen.getByText('Paragraph 1')).toBeInTheDocument()
      expect(screen.getByText('Paragraph 2')).toBeInTheDocument()
    })

    it('renders multiple child elements', () => {
      render(
        <LegalPageWrapper {...defaultProps}>
          <h1>Heading</h1>
          <p>First paragraph</p>
          <ul>
            <li>Item 1</li>
            <li>Item 2</li>
          </ul>
        </LegalPageWrapper>
      )

      expect(screen.getByText('Heading')).toBeInTheDocument()
      expect(screen.getByText('First paragraph')).toBeInTheDocument()
      expect(screen.getByText('Item 1')).toBeInTheDocument()
      expect(screen.getByText('Item 2')).toBeInTheDocument()
    })

    it('renders children with nested components', () => {
      const NestedComponent = () => <span>Nested content</span>

      render(
        <LegalPageWrapper {...defaultProps}>
          <div>
            <NestedComponent />
          </div>
        </LegalPageWrapper>
      )

      expect(screen.getByText('Nested content')).toBeInTheDocument()
    })
  })

  describe('Styling', () => {
    beforeEach(() => {
      mockUseAuth.mockReturnValue({
        user: { id: '1', email: 'test@example.com' },
        isLoading: false,
        login: jest.fn(),
        logout: jest.fn(),
        isInitialized: true,
      } as any)
    })

    it('applies ResponsiveContainer with correct className', () => {
      render(<LegalPageWrapper {...defaultProps} />)

      const container = screen.getByTestId('responsive-container')
      expect(container).toHaveClass('pb-10', 'pt-8')
    })

    it('applies prose classes to content wrapper', () => {
      const { container } = render(<LegalPageWrapper {...defaultProps} />)

      const proseWrapper = container.querySelector('.prose')
      expect(proseWrapper).toBeInTheDocument()
      expect(proseWrapper).toHaveClass('prose', 'prose-zinc', 'max-w-none')
    })

    it('applies dark mode prose class', () => {
      const { container } = render(<LegalPageWrapper {...defaultProps} />)

      const proseWrapper = container.querySelector('.prose')
      expect(proseWrapper).toHaveClass('dark:prose-invert')
    })

    it('applies margin to breadcrumb wrapper', () => {
      const { container } = render(<LegalPageWrapper {...defaultProps} />)

      const breadcrumbWrapper = container.querySelector('.mb-4')
      expect(breadcrumbWrapper).toBeInTheDocument()
    })

    it('has correct layout structure', () => {
      const { container } = render(<LegalPageWrapper {...defaultProps} />)

      const responsiveContainer = screen.getByTestId('responsive-container')
      const breadcrumbWrapper = container.querySelector('.mb-4')
      const proseWrapper = container.querySelector('.prose')

      expect(responsiveContainer).toContainElement(breadcrumbWrapper)
      expect(responsiveContainer).toContainElement(proseWrapper as Element)
    })
  })

  describe('Accessibility', () => {
    it('renders semantic HTML for authenticated users', () => {
      mockUseAuth.mockReturnValue({
        user: { id: '1', email: 'test@example.com' },
        isLoading: false,
        login: jest.fn(),
        logout: jest.fn(),
        isInitialized: true,
      } as any)

      render(<LegalPageWrapper {...defaultProps} />)

      expect(screen.getByTestId('breadcrumb')).toBeInTheDocument()
    })

    it('maintains proper content hierarchy', () => {
      mockUseAuth.mockReturnValue({
        user: { id: '1', email: 'test@example.com' },
        isLoading: false,
        login: jest.fn(),
        logout: jest.fn(),
        isInitialized: true,
      } as any)

      const { container } = render(
        <LegalPageWrapper {...defaultProps}>
          <h1>Main Title</h1>
          <h2>Subtitle</h2>
        </LegalPageWrapper>
      )

      const h1 = container.querySelector('h1')
      const h2 = container.querySelector('h2')

      expect(h1).toBeInTheDocument()
      expect(h2).toBeInTheDocument()
    })

    it('prose wrapper allows accessible content formatting', () => {
      mockUseAuth.mockReturnValue({
        user: { id: '1', email: 'test@example.com' },
        isLoading: false,
        login: jest.fn(),
        logout: jest.fn(),
        isInitialized: true,
      } as any)

      const { container } = render(
        <LegalPageWrapper {...defaultProps}>
          <article>
            <h1>Article Title</h1>
            <p>Article content</p>
          </article>
        </LegalPageWrapper>
      )

      const article = container.querySelector('article')
      expect(article).toBeInTheDocument()
    })

    it('does not interfere with child accessibility attributes', () => {
      mockUseAuth.mockReturnValue({
        user: { id: '1', email: 'test@example.com' },
        isLoading: false,
        login: jest.fn(),
        logout: jest.fn(),
        isInitialized: true,
      } as any)

      render(
        <LegalPageWrapper {...defaultProps}>
          <button aria-label="Close dialog">Close</button>
        </LegalPageWrapper>
      )

      const button = screen.getByLabelText('Close dialog')
      expect(button).toBeInTheDocument()
    })
  })

  describe('Edge Cases', () => {
    it('handles null user', () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: false,
        login: jest.fn(),
        logout: jest.fn(),
        isInitialized: true,
      } as any)

      render(<LegalPageWrapper {...defaultProps} />)
      expect(screen.getByText('Legal content')).toBeInTheDocument()
    })

    it('handles undefined user', () => {
      mockUseAuth.mockReturnValue({
        user: undefined,
        isLoading: false,
        login: jest.fn(),
        logout: jest.fn(),
        isInitialized: true,
      } as any)

      render(<LegalPageWrapper {...defaultProps} />)
      expect(screen.queryByTestId('breadcrumb')).not.toBeInTheDocument()
    })

    it('handles empty string children', () => {
      mockUseAuth.mockReturnValue({
        user: { id: '1', email: 'test@example.com' },
        isLoading: false,
        login: jest.fn(),
        logout: jest.fn(),
        isInitialized: true,
      } as any)

      render(<LegalPageWrapper {...defaultProps}>{''}</LegalPageWrapper>)
      expect(screen.getByTestId('responsive-container')).toBeInTheDocument()
    })

    it('handles very long breadcrumb labels', () => {
      mockUseAuth.mockReturnValue({
        user: { id: '1', email: 'test@example.com' },
        isLoading: false,
        login: jest.fn(),
        logout: jest.fn(),
        isInitialized: true,
      } as any)

      const longLabel = 'A'.repeat(200)
      render(<LegalPageWrapper {...defaultProps} breadcrumbLabel={longLabel} />)

      expect(screen.getByText(longLabel)).toBeInTheDocument()
    })

    it('handles special characters in breadcrumb label', () => {
      mockUseAuth.mockReturnValue({
        user: { id: '1', email: 'test@example.com' },
        isLoading: false,
        login: jest.fn(),
        logout: jest.fn(),
        isInitialized: true,
      } as any)

      const specialLabel = '< > & " \' @ # § ü ö ä'
      render(
        <LegalPageWrapper {...defaultProps} breadcrumbLabel={specialLabel} />
      )

      expect(screen.getByText(specialLabel)).toBeInTheDocument()
    })

    it('handles unicode characters in breadcrumb label', () => {
      mockUseAuth.mockReturnValue({
        user: { id: '1', email: 'test@example.com' },
        isLoading: false,
        login: jest.fn(),
        logout: jest.fn(),
        isInitialized: true,
      } as any)

      const unicodeLabel = '你好 世界 🌍 Datenschutzerklärung'
      render(
        <LegalPageWrapper {...defaultProps} breadcrumbLabel={unicodeLabel} />
      )

      expect(screen.getByText(unicodeLabel)).toBeInTheDocument()
    })

    it('handles href with query parameters', () => {
      mockUseAuth.mockReturnValue({
        user: { id: '1', email: 'test@example.com' },
        isLoading: false,
        login: jest.fn(),
        logout: jest.fn(),
        isInitialized: true,
      } as any)

      render(
        <LegalPageWrapper {...defaultProps} href="/about/imprint?lang=de" />
      )

      expect(screen.getByTestId('breadcrumb')).toBeInTheDocument()
    })

    it('handles href with hash fragment', () => {
      mockUseAuth.mockReturnValue({
        user: { id: '1', email: 'test@example.com' },
        isLoading: false,
        login: jest.fn(),
        logout: jest.fn(),
        isInitialized: true,
      } as any)

      render(
        <LegalPageWrapper {...defaultProps} href="/about/imprint#section" />
      )

      expect(screen.getByTestId('breadcrumb')).toBeInTheDocument()
    })

    it('handles loading state with null user', () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: true,
        login: jest.fn(),
        logout: jest.fn(),
        isInitialized: false,
      } as any)

      render(<LegalPageWrapper {...defaultProps} />)
      expect(screen.queryByTestId('breadcrumb')).not.toBeInTheDocument()
    })

    it('handles loading state with existing user', () => {
      mockUseAuth.mockReturnValue({
        user: { id: '1', email: 'test@example.com' },
        isLoading: true,
        login: jest.fn(),
        logout: jest.fn(),
        isInitialized: false,
      } as any)

      render(<LegalPageWrapper {...defaultProps} />)
      expect(screen.getByTestId('breadcrumb')).toBeInTheDocument()
    })

    it('handles rapid auth state changes', () => {
      const { rerender } = render(<LegalPageWrapper {...defaultProps} />)

      mockUseAuth.mockReturnValue({
        user: null,
        isLoading: false,
        login: jest.fn(),
        logout: jest.fn(),
        isInitialized: true,
      } as any)
      rerender(<LegalPageWrapper {...defaultProps} />)
      expect(screen.queryByTestId('breadcrumb')).not.toBeInTheDocument()

      mockUseAuth.mockReturnValue({
        user: { id: '1', email: 'test@example.com' },
        isLoading: false,
        login: jest.fn(),
        logout: jest.fn(),
        isInitialized: true,
      } as any)
      rerender(<LegalPageWrapper {...defaultProps} />)
      expect(screen.getByTestId('breadcrumb')).toBeInTheDocument()
    })

    it('renders with deeply nested children', () => {
      mockUseAuth.mockReturnValue({
        user: { id: '1', email: 'test@example.com' },
        isLoading: false,
        login: jest.fn(),
        logout: jest.fn(),
        isInitialized: true,
      } as any)

      render(
        <LegalPageWrapper {...defaultProps}>
          <div>
            <div>
              <div>
                <div>
                  <p>Deeply nested content</p>
                </div>
              </div>
            </div>
          </div>
        </LegalPageWrapper>
      )

      expect(screen.getByText('Deeply nested content')).toBeInTheDocument()
    })

    it('handles missing translation keys gracefully', () => {
      mockUseAuth.mockReturnValue({
        user: { id: '1', email: 'test@example.com' },
        isLoading: false,
        login: jest.fn(),
        logout: jest.fn(),
        isInitialized: true,
      } as any)

      mockUseI18n.mockReturnValue({
        t: (key: string) => key, // Returns key if not found
        locale: 'en',
        setLocale: jest.fn(),
      } as any)

      render(<LegalPageWrapper {...defaultProps} />)
      expect(screen.getByTestId('breadcrumb')).toBeInTheDocument()
    })

    it('handles different user roles', () => {
      mockUseAuth.mockReturnValue({
        user: {
          id: '1',
          email: 'admin@example.com',
          role: 'superadmin',
        },
        isLoading: false,
        login: jest.fn(),
        logout: jest.fn(),
        isInitialized: true,
      } as any)

      render(<LegalPageWrapper {...defaultProps} />)
      expect(screen.getByTestId('breadcrumb')).toBeInTheDocument()
    })

    it('handles numeric values in children', () => {
      mockUseAuth.mockReturnValue({
        user: { id: '1', email: 'test@example.com' },
        isLoading: false,
        login: jest.fn(),
        logout: jest.fn(),
        isInitialized: true,
      } as any)

      render(
        <LegalPageWrapper {...defaultProps}>
          <p>Version: {123}</p>
        </LegalPageWrapper>
      )

      expect(screen.getByText(/Version: 123/)).toBeInTheDocument()
    })

    it('handles boolean children gracefully', () => {
      mockUseAuth.mockReturnValue({
        user: { id: '1', email: 'test@example.com' },
        isLoading: false,
        login: jest.fn(),
        logout: jest.fn(),
        isInitialized: true,
      } as any)

      render(
        <LegalPageWrapper {...defaultProps}>
          {true && <p>Conditional content</p>}
        </LegalPageWrapper>
      )

      expect(screen.getByText('Conditional content')).toBeInTheDocument()
    })
  })

  describe('Translation Integration', () => {
    beforeEach(() => {
      mockUseAuth.mockReturnValue({
        user: { id: '1', email: 'test@example.com' },
        isLoading: false,
        login: jest.fn(),
        logout: jest.fn(),
        isInitialized: true,
      } as any)
    })

    it('calls translation function with correct key', () => {
      const mockT = jest.fn((key: string) => key)
      mockUseI18n.mockReturnValue({
        t: mockT,
        locale: 'en',
        setLocale: jest.fn(),
      } as any)

      render(<LegalPageWrapper {...defaultProps} />)

      expect(mockT).toHaveBeenCalledWith('navigation.dashboard')
    })

    it('displays translated breadcrumb home label', () => {
      mockUseI18n.mockReturnValue({
        t: (key: string) => (key === 'navigation.dashboard' ? 'Startseite' : key),
        locale: 'de',
        setLocale: jest.fn(),
      } as any)

      render(<LegalPageWrapper {...defaultProps} />)

      expect(screen.getByText('Startseite')).toBeInTheDocument()
    })

    it('handles missing translations', () => {
      mockUseI18n.mockReturnValue({
        t: (key: string) => `[Missing: ${key}]`,
        locale: 'en',
        setLocale: jest.fn(),
      } as any)

      render(<LegalPageWrapper {...defaultProps} />)

      expect(screen.getByText('[Missing: navigation.dashboard]')).toBeInTheDocument()
    })
  })
})

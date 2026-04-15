/**
 * @jest-environment jsdom
 */

import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ComingSoon } from '../ComingSoon'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string) => {
      const translations: Record<string, string> = {
        'common.comingSoon': 'Coming Soon',
        'common.comingSoonMessage': 'This feature is currently under development and will be available soon.',
        'common.goBack': 'Go Back',
      }
      return translations[key] || key
    },
    locale: 'en',
  }),
}))

// Mock Next.js navigation
const mockBack = jest.fn()
jest.mock('next/navigation', () => ({
  useRouter: () => ({
    back: mockBack,
  }),
}))

// Mock ResponsiveContainer
jest.mock('@/components/shared/ResponsiveContainer', () => ({
  ResponsiveContainer: (props: any) => <div {...props}>{props.children}</div>,
}))

// Mock Button
jest.mock('@/components/shared/Button', () => ({
  Button: (props: any) => <button {...props}>{props.children}</button>,
}))

describe('ComingSoon Component', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  describe('Basic Rendering', () => {
    it('renders correctly with default props', () => {
      render(<ComingSoon />)

      expect(screen.getByText('Coming Soon')).toBeInTheDocument()
      expect(
        screen.getByText(
          'This feature is currently under development and will be available soon.'
        )
      ).toBeInTheDocument()
      expect(screen.getByText('Go Back')).toBeInTheDocument()
    })

    it('renders the clock icon', () => {
      const { container } = render(<ComingSoon />)

      const svg = container.querySelector('svg')
      expect(svg).toBeInTheDocument()
      expect(svg).toHaveAttribute('viewBox', '0 0 24 24')
    })

    it('renders all required sections', () => {
      const { container } = render(<ComingSoon />)

      // Icon section
      const iconContainer = container.querySelector('.mb-8')
      expect(iconContainer).toBeInTheDocument()

      // Title
      expect(screen.getByRole('heading', { level: 1 })).toBeInTheDocument()

      // Description
      const description = screen.getByText(
        'This feature is currently under development and will be available soon.'
      )
      expect(description).toBeInTheDocument()
    })
  })

  describe('Content Display', () => {
    it('displays custom title when provided', () => {
      render(<ComingSoon title="Custom Feature Coming" />)

      expect(screen.getByText('Custom Feature Coming')).toBeInTheDocument()
      expect(screen.queryByText('Coming Soon')).not.toBeInTheDocument()
    })

    it('displays custom description when provided', () => {
      const customDesc = 'This amazing feature will be ready next month.'
      render(<ComingSoon description={customDesc} />)

      expect(screen.getByText(customDesc)).toBeInTheDocument()
      expect(
        screen.queryByText(
          'This feature is currently under development and will be available soon.'
        )
      ).not.toBeInTheDocument()
    })

    it('displays both custom title and description', () => {
      render(
        <ComingSoon
          title="New Analytics Dashboard"
          description="Advanced analytics and reporting tools are being developed."
        />
      )

      expect(screen.getByText('New Analytics Dashboard')).toBeInTheDocument()
      expect(
        screen.getByText(
          'Advanced analytics and reporting tools are being developed.'
        )
      ).toBeInTheDocument()
    })
  })

  describe('Props/Attributes', () => {
    it('accepts and renders custom title prop', () => {
      const customTitle = 'Under Construction'
      render(<ComingSoon title={customTitle} />)

      const heading = screen.getByRole('heading', { level: 1 })
      expect(heading).toHaveTextContent(customTitle)
    })

    it('accepts and renders custom description prop', () => {
      const customDescription = 'We are working hard on this feature.'
      render(<ComingSoon description={customDescription} />)

      expect(screen.getByText(customDescription)).toBeInTheDocument()
    })

    it('accepts showBackButton prop', () => {
      render(<ComingSoon showBackButton={false} />)

      expect(screen.queryByText('Go Back')).not.toBeInTheDocument()
    })

    it('uses default values for all optional props', () => {
      render(<ComingSoon />)

      expect(screen.getByText('Coming Soon')).toBeInTheDocument()
      expect(
        screen.getByText(
          'This feature is currently under development and will be available soon.'
        )
      ).toBeInTheDocument()
      expect(screen.getByText('Go Back')).toBeInTheDocument()
    })
  })

  describe('Styling', () => {
    it('applies correct container classes', () => {
      const { container } = render(<ComingSoon />)

      const mainContainer = container.querySelector(
        '.flex.min-h-\\[60vh\\].flex-col.items-center.justify-center.text-center'
      )
      expect(mainContainer).toBeInTheDocument()
    })

    it('applies correct icon styling classes', () => {
      const { container } = render(<ComingSoon />)

      const svg = container.querySelector('svg')
      expect(svg).toHaveClass(
        'h-24',
        'w-24',
        'text-zinc-300',
        'dark:text-zinc-600'
      )
    })

    it('applies correct title styling classes', () => {
      render(<ComingSoon />)

      const heading = screen.getByRole('heading', { level: 1 })
      expect(heading).toHaveClass(
        'mb-4',
        'text-3xl',
        'font-bold',
        'text-zinc-900',
        'dark:text-zinc-100'
      )
    })

    it('applies correct description styling classes', () => {
      const { container } = render(<ComingSoon />)

      const description = screen.getByText(
        'This feature is currently under development and will be available soon.'
      )
      expect(description.tagName).toBe('P')
      expect(description).toHaveClass(
        'mb-8',
        'max-w-md',
        'text-lg',
        'text-zinc-600',
        'dark:text-zinc-400'
      )
    })

    it('applies correct SVG stroke properties', () => {
      const { container } = render(<ComingSoon />)

      const svg = container.querySelector('svg')
      expect(svg).toHaveAttribute('fill', 'none')
      expect(svg).toHaveAttribute('stroke', 'currentColor')

      const path = svg?.querySelector('path')
      expect(path).toHaveAttribute('stroke-linecap', 'round')
      expect(path).toHaveAttribute('stroke-linejoin', 'round')
      expect(path).toHaveAttribute('stroke-width', '1.5')
    })

    it('renders clock icon with correct path data', () => {
      const { container } = render(<ComingSoon />)

      const path = container.querySelector('path')
      expect(path).toHaveAttribute(
        'd',
        'M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z'
      )
    })
  })

  describe('Optional Elements', () => {
    it('shows back button when showBackButton is true', () => {
      render(<ComingSoon showBackButton={true} />)

      expect(screen.getByText('Go Back')).toBeInTheDocument()
    })

    it('hides back button when showBackButton is false', () => {
      render(<ComingSoon showBackButton={false} />)

      expect(screen.queryByText('Go Back')).not.toBeInTheDocument()
    })

    it('shows back button by default', () => {
      render(<ComingSoon />)

      expect(screen.getByText('Go Back')).toBeInTheDocument()
    })

    it('renders back button with correct classes when shown', () => {
      render(<ComingSoon showBackButton={true} />)

      const button = screen.getByText('Go Back')
      expect(button).toHaveClass(
        'bg-emerald-600',
        'text-white',
        'hover:bg-emerald-700'
      )
    })
  })

  describe('Accessibility', () => {
    it('uses semantic HTML with heading tag', () => {
      render(<ComingSoon />)

      const heading = screen.getByRole('heading', { level: 1 })
      expect(heading).toBeInTheDocument()
      expect(heading).toHaveTextContent('Coming Soon')
    })

    it('provides descriptive text for screen readers', () => {
      render(<ComingSoon />)

      const heading = screen.getByRole('heading', { level: 1 })
      const description = screen.getByText(
        'This feature is currently under development and will be available soon.'
      )

      expect(heading).toBeInTheDocument()
      expect(description).toBeInTheDocument()
    })

    it('button is keyboard accessible', async () => {
      const user = userEvent.setup()
      render(<ComingSoon />)

      const button = screen.getByText('Go Back')
      button.focus()

      expect(button).toHaveFocus()

      await user.keyboard('{Enter}')
      expect(mockBack).toHaveBeenCalledTimes(1)
    })

    it('maintains proper semantic structure', () => {
      const { container } = render(<ComingSoon />)

      const heading = screen.getByRole('heading', { level: 1 })
      const paragraph = container.querySelector('p')

      expect(heading).toBeInTheDocument()
      expect(paragraph).toBeInTheDocument()
    })

    it('icon is decorative only', () => {
      const { container } = render(<ComingSoon />)

      const svg = container.querySelector('svg')
      expect(svg).not.toHaveAttribute('role')
      expect(svg).not.toHaveAttribute('aria-label')
    })
  })

  describe('Edge Cases', () => {
    it('handles empty string title', () => {
      render(<ComingSoon title="" />)

      const heading = screen.getByRole('heading', { level: 1 })
      expect(heading).toHaveTextContent('')
      expect(heading).toBeInTheDocument()
    })

    it('handles empty string description', () => {
      const { container } = render(<ComingSoon description="" />)

      const paragraph = container.querySelector('p')
      expect(paragraph).toHaveTextContent('')
      expect(paragraph).toBeInTheDocument()
    })

    const specialChar = '& < > " \' / \\'
    it('handles special characters in title', () => {
      const titleWithSpecialChars = `Coming Soon ${specialChar}`
      render(<ComingSoon title={titleWithSpecialChars} />)

      expect(screen.getByText(titleWithSpecialChars)).toBeInTheDocument()
    })

    it('handles special characters in description', () => {
      const descWithSpecialChars = `Feature ${specialChar} under development.`
      render(<ComingSoon description={descWithSpecialChars} />)

      expect(screen.getByText(descWithSpecialChars)).toBeInTheDocument()
    })

    it('handles very long title text', () => {
      const longTitle =
        'This is a very long title that might wrap to multiple lines and should still render correctly without breaking the layout'
      render(<ComingSoon title={longTitle} />)

      expect(screen.getByText(longTitle)).toBeInTheDocument()
    })

    it('handles very long description text', () => {
      const longDescription =
        'This is a very long description that contains multiple sentences and should properly wrap within the max-width constraint. It should maintain readability and proper spacing even with lots of content that extends beyond a single line of text.'
      render(<ComingSoon description={longDescription} />)

      expect(screen.getByText(longDescription)).toBeInTheDocument()
    })

    it('handles multiple re-renders with different props', () => {
      const { rerender } = render(<ComingSoon title="First Title" />)
      expect(screen.getByText('First Title')).toBeInTheDocument()

      rerender(<ComingSoon title="Second Title" />)
      expect(screen.getByText('Second Title')).toBeInTheDocument()
      expect(screen.queryByText('First Title')).not.toBeInTheDocument()

      rerender(<ComingSoon showBackButton={false} />)
      expect(screen.queryByText('Go Back')).not.toBeInTheDocument()
    })

    it('maintains structure with all props as undefined', () => {
      render(
        <ComingSoon
          title={undefined}
          description={undefined}
          showBackButton={undefined}
        />
      )

      // Should use default values
      expect(screen.getByText('Coming Soon')).toBeInTheDocument()
      expect(screen.getByText('Go Back')).toBeInTheDocument()
    })
  })

  describe('Dark Mode Support', () => {
    it('includes dark mode classes for icon', () => {
      const { container } = render(<ComingSoon />)

      const svg = container.querySelector('svg')
      expect(svg).toHaveClass('dark:text-zinc-600')
    })

    it('includes dark mode classes for title', () => {
      render(<ComingSoon />)

      const heading = screen.getByRole('heading', { level: 1 })
      expect(heading).toHaveClass('dark:text-zinc-100')
    })

    it('includes dark mode classes for description', () => {
      const { container } = render(<ComingSoon />)

      const paragraph = container.querySelector('p')
      expect(paragraph).toHaveClass('dark:text-zinc-400')
    })

    it('applies dark mode classes correctly', () => {
      const { container } = render(<ComingSoon />)

      const darkModeElements = container.querySelectorAll('[class*="dark:"]')
      expect(darkModeElements.length).toBeGreaterThan(0)
    })
  })

  describe('Button Interaction', () => {
    it('calls router.back() when button is clicked', async () => {
      const user = userEvent.setup()
      render(<ComingSoon />)

      const button = screen.getByText('Go Back')
      await user.click(button)

      expect(mockBack).toHaveBeenCalledTimes(1)
    })

    it('calls router.back() when button is clicked with fireEvent', () => {
      render(<ComingSoon />)

      const button = screen.getByText('Go Back')
      fireEvent.click(button)

      expect(mockBack).toHaveBeenCalledTimes(1)
    })

    it('does not call router.back() when showBackButton is false', async () => {
      const user = userEvent.setup()
      render(<ComingSoon showBackButton={false} />)

      expect(screen.queryByText('Go Back')).not.toBeInTheDocument()
      expect(mockBack).not.toHaveBeenCalled()
    })

    it('handles multiple button clicks', async () => {
      const user = userEvent.setup()
      render(<ComingSoon />)

      const button = screen.getByText('Go Back')
      await user.click(button)
      await user.click(button)
      await user.click(button)

      expect(mockBack).toHaveBeenCalledTimes(3)
    })
  })

  describe('Component Integration', () => {
    it('renders within ResponsiveContainer wrapper', () => {
      render(<ComingSoon />)

      // ResponsiveContainer should receive size and className props
      const container = screen
        .getByText('Coming Soon')
        .closest('div')
        ?.closest('div')
      expect(container).toBeInTheDocument()
    })

    it('passes props to Button component', () => {
      render(<ComingSoon />)

      const button = screen.getByText('Go Back')
      expect(button).toHaveClass(
        'bg-emerald-600',
        'text-white',
        'hover:bg-emerald-700'
      )
    })

    it('maintains proper component hierarchy', () => {
      const { container } = render(<ComingSoon />)

      // ResponsiveContainer > div > (icon, title, description, button)
      const mainDiv = container.querySelector('.flex.min-h-\\[60vh\\].flex-col')
      expect(mainDiv).toBeInTheDocument()

      const icon = mainDiv?.querySelector('svg')
      const heading = mainDiv?.querySelector('h1')
      const paragraph = mainDiv?.querySelector('p')
      const button = mainDiv?.querySelector('button')

      expect(icon).toBeInTheDocument()
      expect(heading).toBeInTheDocument()
      expect(paragraph).toBeInTheDocument()
      expect(button).toBeInTheDocument()
    })
  })

  describe('Layout and Spacing', () => {
    it('applies correct margin classes to icon container', () => {
      const { container } = render(<ComingSoon />)

      const iconContainer = container.querySelector('.mb-8')
      expect(iconContainer).toBeInTheDocument()
      expect(iconContainer?.querySelector('svg')).toBeInTheDocument()
    })

    it('applies correct margin classes to heading', () => {
      render(<ComingSoon />)

      const heading = screen.getByRole('heading', { level: 1 })
      expect(heading).toHaveClass('mb-4')
    })

    it('applies correct margin classes to description', () => {
      const { container } = render(<ComingSoon />)

      const description = container.querySelector('p')
      expect(description).toHaveClass('mb-8')
    })

    it('applies min-height to main container', () => {
      const { container } = render(<ComingSoon />)

      const mainContainer = container.querySelector('.min-h-\\[60vh\\]')
      expect(mainContainer).toBeInTheDocument()
    })

    it('centers content vertically and horizontally', () => {
      const { container } = render(<ComingSoon />)

      const mainContainer = container.querySelector('.flex')
      expect(mainContainer).toHaveClass(
        'items-center',
        'justify-center',
        'text-center'
      )
    })
  })
})

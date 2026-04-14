/**
 * @jest-environment jsdom
 */

import { render, screen } from '@testing-library/react'
import NotFound from '../not-found'

// Mock I18nContext
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string) => {
      const translations: Record<string, string> = {
        'errors.404.code': '404',
        'errors.404.title': 'Page not found',
        'errors.404.description':
          "Sorry, we couldn't find the page you're looking for.",
        'errors.404.backButton': 'Go back home',
      }
      return translations[key] || key
    },
  }),
}))

// Mock the shared components
jest.mock('@/components/shared', () => ({
  HeroPattern: () => <div data-testid="hero-pattern" />,
}))

jest.mock('@/components/shared/Button', () => ({
  Button: ({ children, href, arrow, className }: any) => (
    <a
      href={href}
      className={className}
      data-arrow={arrow}
      data-testid="button-link"
    >
      {children}
    </a>
  ),
}))

describe('NotFound', () => {
  describe('Basic Rendering', () => {
    it('renders 404 status code', () => {
      render(<NotFound />)

      expect(screen.getByText('404')).toBeInTheDocument()
    })

    it('renders page not found heading', () => {
      render(<NotFound />)

      expect(screen.getByText('Page not found')).toBeInTheDocument()
    })

    it('renders descriptive error message', () => {
      render(<NotFound />)

      expect(screen.getByText(/Sorry.*find.*page/)).toBeInTheDocument()
    })

    it('renders back to docs button', () => {
      render(<NotFound />)

      expect(screen.getByText('Go back home')).toBeInTheDocument()
    })

    it('renders HeroPattern component', () => {
      render(<NotFound />)

      expect(screen.getByTestId('hero-pattern')).toBeInTheDocument()
    })
  })

  describe('Button Component', () => {
    it('renders Button component with correct href', () => {
      render(<NotFound />)

      const button = screen.getByTestId('button-link')
      expect(button).toHaveAttribute('href', '/')
    })

    it('renders Button with arrow prop', () => {
      render(<NotFound />)

      const button = screen.getByTestId('button-link')
      expect(button).toHaveAttribute('data-arrow', 'right')
    })

    it('renders Button with correct text', () => {
      render(<NotFound />)

      const button = screen.getByTestId('button-link')
      expect(button).toHaveTextContent('Go back home')
    })

    it('renders Button with correct className', () => {
      render(<NotFound />)

      const button = screen.getByTestId('button-link')
      expect(button).toHaveClass('mt-8')
    })
  })

  describe('Layout and Structure', () => {
    it('renders content in centered container', () => {
      const { container } = render(<NotFound />)

      const centerContainer = container.querySelector(
        '.mx-auto.flex.h-full.max-w-xl'
      )
      expect(centerContainer).toBeInTheDocument()
    })

    it('applies flex and column layout classes', () => {
      const { container } = render(<NotFound />)

      const centerContainer = container.querySelector('.flex.flex-col')
      expect(centerContainer).toBeInTheDocument()
    })

    it('applies centered items and text alignment', () => {
      const { container } = render(<NotFound />)

      const centerContainer = container.querySelector(
        '.items-center.justify-center'
      )
      expect(centerContainer).toBeInTheDocument()
      expect(centerContainer).toHaveClass('text-center')
    })

    it('applies correct padding', () => {
      const { container } = render(<NotFound />)

      const centerContainer = container.querySelector('.py-16')
      expect(centerContainer).toBeInTheDocument()
    })

    it('uses React Fragment wrapper', () => {
      const { container } = render(<NotFound />)

      // Component uses Fragment (<>), so container should have multiple direct children
      expect(container.firstChild).toBeTruthy()
    })
  })

  describe('Typography and Styling', () => {
    it('applies correct 404 status code styling', () => {
      render(<NotFound />)

      const statusCode = screen.getByText('404')
      expect(statusCode).toHaveClass(
        'text-sm',
        'font-semibold',
        'text-zinc-900',
        'dark:text-white'
      )
    })

    it('applies correct heading styling', () => {
      render(<NotFound />)

      const heading = screen.getByText('Page not found')
      expect(heading).toHaveClass(
        'mt-2',
        'text-2xl',
        'font-bold',
        'text-zinc-900',
        'dark:text-white'
      )
    })

    it('applies correct description styling', () => {
      render(<NotFound />)

      const description = screen.getByText(/Sorry.*find.*page/)
      expect(description).toHaveClass(
        'mt-2',
        'text-base',
        'text-zinc-600',
        'dark:text-zinc-400'
      )
    })

    it('uses proper heading level', () => {
      render(<NotFound />)

      const heading = screen.getByRole('heading', { level: 1 })
      expect(heading).toHaveTextContent('Page not found')
    })
  })

  describe('Dark Mode Support', () => {
    it('includes dark mode classes for 404 status', () => {
      render(<NotFound />)

      const statusCode = screen.getByText('404')
      expect(statusCode).toHaveClass('dark:text-white')
    })

    it('includes dark mode classes for heading', () => {
      render(<NotFound />)

      const heading = screen.getByText('Page not found')
      expect(heading).toHaveClass('dark:text-white')
    })

    it('includes dark mode classes for description', () => {
      render(<NotFound />)

      const description = screen.getByText(/Sorry.*find.*page/)
      expect(description).toHaveClass('dark:text-zinc-400')
    })
  })

  describe('Spacing and Layout', () => {
    it('applies correct spacing to container', () => {
      const { container } = render(<NotFound />)

      const centerContainer = container.querySelector('.mx-auto')
      expect(centerContainer).toHaveClass('mx-auto', 'max-w-xl', 'py-16')
    })

    it('applies correct margin to heading', () => {
      render(<NotFound />)

      const heading = screen.getByText('Page not found')
      expect(heading).toHaveClass('mt-2')
    })

    it('applies correct margin to description', () => {
      render(<NotFound />)

      const description = screen.getByText(/Sorry.*find.*page/)
      expect(description).toHaveClass('mt-2')
    })

    it('applies correct margin to button', () => {
      render(<NotFound />)

      const button = screen.getByTestId('button-link')
      expect(button).toHaveClass('mt-8')
    })

    it('uses proper vertical spacing progression', () => {
      render(<NotFound />)

      const heading = screen.getByText('Page not found')
      const description = screen.getByText(/Sorry.*find.*page/)
      const button = screen.getByTestId('button-link')

      expect(heading).toHaveClass('mt-2')
      expect(description).toHaveClass('mt-2')
      expect(button).toHaveClass('mt-8')
    })
  })

  describe('Accessibility', () => {
    it('uses semantic heading element', () => {
      render(<NotFound />)

      const heading = screen.getByRole('heading', { level: 1 })
      expect(heading).toBeInTheDocument()
    })

    it('provides descriptive error message', () => {
      render(<NotFound />)

      const description = screen.getByText(/Sorry.*find.*page/)
      expect(description).toBeInTheDocument()
    })

    it('includes navigable link to home', () => {
      render(<NotFound />)

      const button = screen.getByTestId('button-link')
      expect(button).toHaveAttribute('href', '/')
    })

    it('maintains proper text hierarchy', () => {
      render(<NotFound />)

      const status = screen.getByText('404')
      const heading = screen.getByText('Page not found')
      const description = screen.getByText(/Sorry/)

      expect(status).toBeInTheDocument()
      expect(heading).toBeInTheDocument()
      expect(description).toBeInTheDocument()
    })

    it('uses high contrast colors', () => {
      render(<NotFound />)

      const heading = screen.getByText('Page not found')
      expect(heading).toHaveClass('text-zinc-900')

      const description = screen.getByText(/Sorry.*find.*page/)
      expect(description).toHaveClass('text-zinc-600')
    })
  })

  describe('Responsive Design', () => {
    it('applies max-width constraint', () => {
      const { container } = render(<NotFound />)

      const centerContainer = container.querySelector('.max-w-xl')
      expect(centerContainer).toBeInTheDocument()
    })

    it('uses relative units for font sizes', () => {
      render(<NotFound />)

      const statusCode = screen.getByText('404')
      expect(statusCode).toHaveClass('text-sm')

      const heading = screen.getByText('Page not found')
      expect(heading).toHaveClass('text-2xl')

      const description = screen.getByText(/Sorry.*find.*page/)
      expect(description).toHaveClass('text-base')
    })

    it('uses responsive padding', () => {
      const { container } = render(<NotFound />)

      const centerContainer = container.querySelector('.py-16')
      expect(centerContainer).toBeInTheDocument()
    })

    it('centers content horizontally and vertically', () => {
      const { container } = render(<NotFound />)

      const centerContainer = container.querySelector(
        '.items-center.justify-center'
      )
      expect(centerContainer).toBeInTheDocument()
    })
  })

  describe('Content Hierarchy', () => {
    it('renders elements in correct order', () => {
      const { container } = render(<NotFound />)

      const allText = container.textContent
      const statusIndex = allText?.indexOf('404')
      const headingIndex = allText?.indexOf('Page not found')
      const descriptionIndex = allText?.indexOf('Sorry')
      const buttonIndex = allText?.indexOf('Go back home')

      expect(statusIndex).toBeLessThan(headingIndex!)
      expect(headingIndex).toBeLessThan(descriptionIndex!)
      expect(descriptionIndex).toBeLessThan(buttonIndex!)
    })

    it('maintains visual hierarchy with font weights', () => {
      render(<NotFound />)

      const statusCode = screen.getByText('404')
      expect(statusCode).toHaveClass('font-semibold')

      const heading = screen.getByText('Page not found')
      expect(heading).toHaveClass('font-bold')
    })

    it('uses different font sizes for hierarchy', () => {
      render(<NotFound />)

      const statusCode = screen.getByText('404')
      expect(statusCode).toHaveClass('text-sm')

      const heading = screen.getByText('Page not found')
      expect(heading).toHaveClass('text-2xl')

      const description = screen.getByText(/Sorry.*find.*page/)
      expect(description).toHaveClass('text-base')
    })
  })

  describe('Background Pattern', () => {
    it('renders HeroPattern before content', () => {
      const { container } = render(<NotFound />)

      const heroPattern = screen.getByTestId('hero-pattern')
      const centerContainer = container.querySelector('.mx-auto.max-w-xl')

      expect(heroPattern).toBeInTheDocument()
      expect(centerContainer).toBeInTheDocument()
    })

    it('includes HeroPattern component', () => {
      render(<NotFound />)

      expect(screen.getByTestId('hero-pattern')).toBeInTheDocument()
    })
  })

  describe('User Experience', () => {
    it('provides clear error status', () => {
      render(<NotFound />)

      expect(screen.getByText('404')).toBeInTheDocument()
      expect(screen.getByText('Page not found')).toBeInTheDocument()
    })

    it('provides helpful error message', () => {
      render(<NotFound />)

      const message = screen.getByText(/Sorry.*find.*page/)
      expect(message).toBeInTheDocument()
    })

    it('provides clear call to action', () => {
      render(<NotFound />)

      const button = screen.getByTestId('button-link')
      expect(button).toHaveTextContent('Go back home')
      expect(button).toHaveAttribute('href', '/')
    })

    it('centers content for better visibility', () => {
      const { container } = render(<NotFound />)

      const centerContainer = container.querySelector('.text-center')
      expect(centerContainer).toBeInTheDocument()
    })
  })

  describe('Component Integration', () => {
    it('integrates Button component correctly', () => {
      render(<NotFound />)

      const button = screen.getByTestId('button-link')
      expect(button).toBeInTheDocument()
      expect(button.tagName).toBe('A')
    })

    it('integrates HeroPattern component correctly', () => {
      render(<NotFound />)

      const pattern = screen.getByTestId('hero-pattern')
      expect(pattern).toBeInTheDocument()
    })

    it('passes correct props to Button', () => {
      render(<NotFound />)

      const button = screen.getByTestId('button-link')
      expect(button).toHaveAttribute('href', '/')
      expect(button).toHaveAttribute('data-arrow', 'right')
      expect(button).toHaveClass('mt-8')
    })
  })

  describe('Edge Cases', () => {
    it('renders consistently on multiple renders', () => {
      const { rerender } = render(<NotFound />)

      expect(screen.getByText('404')).toBeInTheDocument()
      expect(screen.getByText('Page not found')).toBeInTheDocument()

      rerender(<NotFound />)

      expect(screen.getByText('404')).toBeInTheDocument()
      expect(screen.getByText('Page not found')).toBeInTheDocument()
    })

    it('maintains structure without props', () => {
      const { container } = render(<NotFound />)

      expect(container.firstChild).toBeTruthy()
      expect(screen.getByTestId('hero-pattern')).toBeInTheDocument()
      expect(screen.getByText('404')).toBeInTheDocument()
    })

    it('renders all text content correctly', () => {
      render(<NotFound />)

      expect(screen.getByText('404')).toBeInTheDocument()
      expect(screen.getByText('Page not found')).toBeInTheDocument()
      expect(screen.getByText(/Sorry.*find.*page/)).toBeInTheDocument()
      expect(screen.getByText('Go back home')).toBeInTheDocument()
    })
  })

  describe('Visual Design', () => {
    it('uses consistent color scheme', () => {
      render(<NotFound />)

      const statusCode = screen.getByText('404')
      const heading = screen.getByText('Page not found')

      expect(statusCode).toHaveClass('text-zinc-900', 'dark:text-white')
      expect(heading).toHaveClass('text-zinc-900', 'dark:text-white')
    })

    it('applies proper text alignment', () => {
      const { container } = render(<NotFound />)

      const textContainer = container.querySelector('.text-center')
      expect(textContainer).toBeInTheDocument()
    })

    it('maintains proper spacing ratios', () => {
      render(<NotFound />)

      const heading = screen.getByText('Page not found')
      const description = screen.getByText(/Sorry.*find.*page/)
      const button = screen.getByTestId('button-link')

      expect(heading).toHaveClass('mt-2')
      expect(description).toHaveClass('mt-2')
      expect(button).toHaveClass('mt-8')
    })
  })
})

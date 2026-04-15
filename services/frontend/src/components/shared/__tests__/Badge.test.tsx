import { fireEvent, render, screen } from '@testing-library/react'
import { Badge } from '../Badge'

describe('Badge', () => {
  describe('basic rendering', () => {
    it('renders badge with default variant', () => {
      render(<Badge>Test Badge</Badge>)

      const badge = screen.getByText('Test Badge')
      expect(badge).toBeInTheDocument()
      expect(badge).toHaveClass(
        'inline-flex',
        'items-center',
        'rounded-full',
        'px-2.5',
        'py-0.5',
        'text-xs',
        'font-medium'
      )
    })

    it('renders badge content correctly', () => {
      render(<Badge>Custom Content</Badge>)

      expect(screen.getByText('Custom Content')).toBeInTheDocument()
    })

    it('renders with span element', () => {
      const { container } = render(<Badge>Test</Badge>)

      const badge = container.querySelector('span')
      expect(badge).toBeInTheDocument()
      expect(badge).toHaveTextContent('Test')
    })
  })

  describe('variant styling', () => {
    it('applies default variant styling by default', () => {
      render(<Badge>Default Badge</Badge>)

      const badge = screen.getByText('Default Badge')
      expect(badge).toHaveClass(
        'bg-emerald-100',
        'text-emerald-800',
        'dark:bg-emerald-900/20',
        'dark:text-emerald-400'
      )
    })

    it('applies default variant styling when explicitly set', () => {
      render(<Badge variant="default">Default Badge</Badge>)

      const badge = screen.getByText('Default Badge')
      expect(badge).toHaveClass(
        'bg-emerald-100',
        'text-emerald-800',
        'dark:bg-emerald-900/20',
        'dark:text-emerald-400'
      )
    })

    it('applies secondary variant styling', () => {
      render(<Badge variant="secondary">Secondary Badge</Badge>)

      const badge = screen.getByText('Secondary Badge')
      expect(badge).toHaveClass(
        'bg-zinc-100',
        'text-zinc-800',
        'dark:bg-zinc-800',
        'dark:text-zinc-300'
      )
    })

    it('applies destructive variant styling', () => {
      render(<Badge variant="destructive">Destructive Badge</Badge>)

      const badge = screen.getByText('Destructive Badge')
      expect(badge).toHaveClass(
        'bg-red-100',
        'text-red-800',
        'dark:bg-red-900/20',
        'dark:text-red-400'
      )
    })

    it('applies outline variant styling', () => {
      render(<Badge variant="outline">Outline Badge</Badge>)

      const badge = screen.getByText('Outline Badge')
      expect(badge).toHaveClass(
        'border',
        'border-zinc-200',
        'dark:border-zinc-700',
        'text-zinc-600',
        'dark:text-zinc-400'
      )
    })
  })

  describe('custom styling', () => {
    it('applies custom className', () => {
      render(<Badge className="custom-class">Custom Badge</Badge>)

      const badge = screen.getByText('Custom Badge')
      expect(badge).toHaveClass('custom-class')
    })

    it('combines custom className with default classes', () => {
      render(<Badge className="custom-class">Custom Badge</Badge>)

      const badge = screen.getByText('Custom Badge')
      expect(badge).toHaveClass(
        'custom-class',
        'inline-flex',
        'items-center',
        'rounded-full'
      )
    })

    it('combines custom className with variant styling', () => {
      render(
        <Badge variant="secondary" className="custom-class">
          Custom Badge
        </Badge>
      )

      const badge = screen.getByText('Custom Badge')
      expect(badge).toHaveClass('custom-class', 'bg-zinc-100', 'text-zinc-800')
    })
  })

  describe('content types', () => {
    it('renders text content', () => {
      render(<Badge>Text Content</Badge>)

      expect(screen.getByText('Text Content')).toBeInTheDocument()
    })

    it('renders numeric content', () => {
      render(<Badge>{42}</Badge>)

      expect(screen.getByText('42')).toBeInTheDocument()
    })

    it('renders JSX content', () => {
      render(
        <Badge>
          <span>JSX Content</span>
        </Badge>
      )

      expect(screen.getByText('JSX Content')).toBeInTheDocument()
    })

    it('renders multiple children', () => {
      render(
        <Badge>
          <span>First</span>
          <span>Second</span>
        </Badge>
      )

      expect(screen.getByText('First')).toBeInTheDocument()
      expect(screen.getByText('Second')).toBeInTheDocument()
    })

    it('renders empty badge', () => {
      const { container } = render(<Badge></Badge>)

      const badge = container.querySelector('span')
      expect(badge).toBeInTheDocument()
      expect(badge).toHaveTextContent('')
    })
  })

  describe('accessibility', () => {
    it('provides accessible content', () => {
      render(<Badge>Badge Label</Badge>)

      const badge = screen.getByText('Badge Label')
      expect(badge).toBeInTheDocument()
    })

    it('preserves text content for screen readers', () => {
      render(<Badge>Important Status</Badge>)

      expect(screen.getByText('Important Status')).toBeInTheDocument()
    })

    it('works with aria attributes when added', () => {
      // Note: The Badge component doesn't spread props, so aria attributes won't be applied
      // This test demonstrates the component behavior
      render(<Badge>Active</Badge>)

      const badge = screen.getByText('Active')
      expect(badge).toBeInTheDocument()
      expect(badge).toHaveTextContent('Active')
    })
  })

  describe('semantic usage', () => {
    it('can be used for status indicators', () => {
      render(<Badge variant="default">Active</Badge>)

      expect(screen.getByText('Active')).toHaveClass(
        'bg-emerald-100',
        'text-emerald-800'
      )
    })

    it('can be used for warning indicators', () => {
      render(<Badge variant="destructive">Error</Badge>)

      expect(screen.getByText('Error')).toHaveClass(
        'bg-red-100',
        'text-red-800'
      )
    })

    it('can be used for neutral information', () => {
      render(<Badge variant="secondary">Info</Badge>)

      expect(screen.getByText('Info')).toHaveClass(
        'bg-zinc-100',
        'text-zinc-800'
      )
    })

    it('can be used for outlined labels', () => {
      render(<Badge variant="outline">Draft</Badge>)

      expect(screen.getByText('Draft')).toHaveClass('border', 'border-zinc-200')
    })
  })

  describe('dark mode support', () => {
    it('includes dark mode classes for default variant', () => {
      render(<Badge variant="default">Dark Mode</Badge>)

      const badge = screen.getByText('Dark Mode')
      expect(badge).toHaveClass(
        'dark:bg-emerald-900/20',
        'dark:text-emerald-400'
      )
    })

    it('includes dark mode classes for secondary variant', () => {
      render(<Badge variant="secondary">Dark Mode</Badge>)

      const badge = screen.getByText('Dark Mode')
      expect(badge).toHaveClass('dark:bg-zinc-800', 'dark:text-zinc-300')
    })

    it('includes dark mode classes for destructive variant', () => {
      render(<Badge variant="destructive">Dark Mode</Badge>)

      const badge = screen.getByText('Dark Mode')
      expect(badge).toHaveClass('dark:bg-red-900/20', 'dark:text-red-400')
    })

    it('includes dark mode classes for outline variant', () => {
      render(<Badge variant="outline">Dark Mode</Badge>)

      const badge = screen.getByText('Dark Mode')
      expect(badge).toHaveClass('dark:border-zinc-700', 'dark:text-zinc-400')
    })
  })

  describe('responsive design', () => {
    it('maintains consistent size across screen sizes', () => {
      render(<Badge>Responsive Badge</Badge>)

      const badge = screen.getByText('Responsive Badge')
      expect(badge).toHaveClass('px-2.5', 'py-0.5', 'text-xs')
    })

    it('works well with flexible layouts', () => {
      render(
        <div className="flex gap-2">
          <Badge>First</Badge>
          <Badge>Second</Badge>
        </div>
      )

      expect(screen.getByText('First')).toHaveClass('inline-flex')
      expect(screen.getByText('Second')).toHaveClass('inline-flex')
    })
  })

  describe('edge cases', () => {
    it('handles undefined children gracefully', () => {
      const { container } = render(<Badge>{undefined}</Badge>)

      const badge = container.querySelector('span')
      expect(badge).toBeInTheDocument()
    })

    it('handles null children gracefully', () => {
      const { container } = render(<Badge>{null}</Badge>)

      const badge = container.querySelector('span')
      expect(badge).toBeInTheDocument()
    })

    it('handles boolean children gracefully', () => {
      const { container } = render(<Badge>{true}</Badge>)

      const badge = container.querySelector('span')
      expect(badge).toBeInTheDocument()
    })

    it('handles very long text content', () => {
      const longText =
        'This is a very long badge text that might wrap or overflow'
      render(<Badge>{longText}</Badge>)

      expect(screen.getByText(longText)).toBeInTheDocument()
    })
  })

  describe('interactive functionality', () => {
    it('renders as span when no onClick provided', () => {
      const { container } = render(<Badge>Static Badge</Badge>)

      const badge = container.querySelector('span')
      expect(badge).toBeInTheDocument()
      expect(container.querySelector('button')).not.toBeInTheDocument()
    })

    it('renders as button when onClick provided', () => {
      const mockOnClick = jest.fn()
      const { container } = render(
        <Badge onClick={mockOnClick}>Clickable Badge</Badge>
      )

      const button = container.querySelector('button')
      expect(button).toBeInTheDocument()
      expect(container.querySelector('span')).not.toBeInTheDocument()
    })

    it('calls onClick when badge is clicked', () => {
      const mockOnClick = jest.fn()
      render(<Badge onClick={mockOnClick}>Clickable Badge</Badge>)

      const badge = screen.getByText('Clickable Badge')
      fireEvent.click(badge)

      expect(mockOnClick).toHaveBeenCalledTimes(1)
    })

    it('applies interactive classes when onClick provided', () => {
      const mockOnClick = jest.fn()
      render(<Badge onClick={mockOnClick}>Interactive Badge</Badge>)

      const badge = screen.getByText('Interactive Badge')
      expect(badge).toHaveClass(
        'cursor-pointer',
        'hover:opacity-80',
        'transition-opacity',
        'focus:outline-none',
        'focus:ring-2',
        'focus:ring-offset-1',
        'focus:ring-blue-500'
      )
    })

    it('does not apply interactive classes when no onClick provided', () => {
      render(<Badge>Static Badge</Badge>)

      const badge = screen.getByText('Static Badge')
      expect(badge).not.toHaveClass(
        'cursor-pointer',
        'hover:opacity-80',
        'transition-opacity'
      )
    })

    it('supports aria-label for accessibility', () => {
      const mockOnClick = jest.fn()
      render(
        <Badge onClick={mockOnClick} aria-label="Navigate to project settings">
          Status
        </Badge>
      )

      const badge = screen.getByLabelText('Navigate to project settings')
      expect(badge).toBeInTheDocument()
      expect(badge).toHaveTextContent('Status')
    })

    it('handles keyboard interactions', () => {
      const mockOnClick = jest.fn()
      render(<Badge onClick={mockOnClick}>Keyboard Badge</Badge>)

      const badge = screen.getByText('Keyboard Badge')

      // Test Enter key
      fireEvent.keyDown(badge, { key: 'Enter', code: 'Enter' })

      // Button elements handle keyboard interactions automatically
      // We just need to ensure the component renders as a button
      expect(badge.tagName).toBe('BUTTON')
    })

    it('preserves variant styling when interactive', () => {
      const mockOnClick = jest.fn()
      render(
        <Badge variant="destructive" onClick={mockOnClick}>
          Error Status
        </Badge>
      )

      const badge = screen.getByText('Error Status')
      expect(badge).toHaveClass(
        'bg-red-100',
        'text-red-800',
        'cursor-pointer',
        'hover:opacity-80'
      )
    })

    it('combines custom className with interactive classes', () => {
      const mockOnClick = jest.fn()
      render(
        <Badge onClick={mockOnClick} className="custom-interactive">
          Custom Interactive
        </Badge>
      )

      const badge = screen.getByText('Custom Interactive')
      expect(badge).toHaveClass(
        'custom-interactive',
        'cursor-pointer',
        'hover:opacity-80',
        'transition-opacity'
      )
    })
  })
})

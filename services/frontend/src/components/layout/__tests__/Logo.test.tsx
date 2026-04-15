import { render, screen } from '@testing-library/react'
import { Logo } from '../Logo'

describe('Logo', () => {
  describe('rendering', () => {
    it('renders the BenGER logo text', () => {
      render(<Logo />)

      expect(screen.getByText('BenGER')).toBeInTheDocument()
    })

    it('renders the rock emoji icon', () => {
      render(<Logo />)

      expect(screen.getByText('🤘')).toBeInTheDocument()
    })

    it('renders with default styling classes', () => {
      const { container } = render(<Logo />)

      const logoContainer = container.firstChild as HTMLElement
      expect(logoContainer).toHaveClass(
        'flex',
        'items-center',
        'gap-2',
        'text-lg',
        'font-bold',
        'text-zinc-900',
        'dark:text-white'
      )
    })
  })

  describe('styling customization', () => {
    it('applies custom className while preserving default classes', () => {
      const { container } = render(<Logo className="custom-logo-class" />)

      const logoContainer = container.firstChild as HTMLElement
      expect(logoContainer).toHaveClass('custom-logo-class')
      expect(logoContainer).toHaveClass('flex', 'items-center', 'gap-2')
    })

    it('handles undefined className gracefully', () => {
      const { container } = render(<Logo className={undefined} />)

      const logoContainer = container.firstChild as HTMLElement
      expect(logoContainer).toHaveClass('flex', 'items-center', 'gap-2')
    })

    it('handles empty className', () => {
      const { container } = render(<Logo className="" />)

      const logoContainer = container.firstChild as HTMLElement
      expect(logoContainer).toHaveClass('flex', 'items-center', 'gap-2')
    })

    it('combines multiple custom classes', () => {
      const { container } = render(<Logo className="custom-1 custom-2" />)

      const logoContainer = container.firstChild as HTMLElement
      expect(logoContainer).toHaveClass('custom-1', 'custom-2')
      expect(logoContainer).toHaveClass('flex', 'items-center', 'gap-2')
    })
  })

  describe('emoji styling', () => {
    it('applies correct text size to emoji', () => {
      render(<Logo />)

      const emoji = screen.getByText('🤘')
      expect(emoji).toHaveClass('text-xl')
    })

    it('emoji is contained within a span element', () => {
      render(<Logo />)

      const emoji = screen.getByText('🤘')
      expect(emoji.tagName).toBe('SPAN')
    })
  })

  describe('text styling', () => {
    it('renders BenGER text in a span element', () => {
      render(<Logo />)

      const text = screen.getByText('BenGER')
      expect(text.tagName).toBe('SPAN')
    })

    it('applies correct typography classes', () => {
      const { container } = render(<Logo />)

      const logoContainer = container.firstChild as HTMLElement
      expect(logoContainer).toHaveClass('text-lg', 'font-bold')
    })
  })

  describe('dark mode support', () => {
    it('includes dark mode text color classes', () => {
      const { container } = render(<Logo />)

      const logoContainer = container.firstChild as HTMLElement
      expect(logoContainer).toHaveClass('text-zinc-900', 'dark:text-white')
    })
  })

  describe('component props', () => {
    it('forwards HTML div props correctly', () => {
      const { container } = render(
        <Logo
          id="logo-test"
          data-testid="custom-logo"
          role="banner"
          onClick={() => {}}
        />
      )

      const logoContainer = container.firstChild as HTMLElement
      expect(logoContainer).toHaveAttribute('id', 'logo-test')
      expect(logoContainer).toHaveAttribute('data-testid', 'custom-logo')
      expect(logoContainer).toHaveAttribute('role', 'banner')
    })

    it('supports custom event handlers', () => {
      const mockClick = jest.fn()
      render(<Logo onClick={mockClick} />)

      const logo = screen.getByText('BenGER').parentElement!
      logo.click()

      expect(mockClick).toHaveBeenCalledTimes(1)
    })

    it('supports custom styles', () => {
      const customStyles = { backgroundColor: 'red', padding: '10px' }
      const { container } = render(<Logo style={customStyles} />)

      const logoContainer = container.firstChild as HTMLElement
      expect(logoContainer).toHaveAttribute('style')
    })

    it('supports aria attributes', () => {
      const { container } = render(
        <Logo aria-label="BenGER Logo" aria-describedby="logo-description" />
      )

      const logoContainer = container.firstChild as HTMLElement
      expect(logoContainer).toHaveAttribute('aria-label', 'BenGER Logo')
      expect(logoContainer).toHaveAttribute(
        'aria-describedby',
        'logo-description'
      )
    })
  })

  describe('layout behavior', () => {
    it('uses flexbox layout for proper alignment', () => {
      const { container } = render(<Logo />)

      const logoContainer = container.firstChild as HTMLElement
      expect(logoContainer).toHaveClass('flex', 'items-center')
    })

    it('has proper spacing between emoji and text', () => {
      const { container } = render(<Logo />)

      const logoContainer = container.firstChild as HTMLElement
      expect(logoContainer).toHaveClass('gap-2')
    })

    it('maintains proper element order (emoji first, then text)', () => {
      render(<Logo />)

      const emoji = screen.getByText('🤘')
      const text = screen.getByText(/BenGER/)
      // Both should be inside the same container
      expect(emoji.parentElement).toBe(text.parentElement)
    })
  })

  describe('accessibility', () => {
    it('provides meaningful text content', () => {
      render(<Logo />)

      // Both emoji and text should be accessible
      expect(screen.getByText('🤘')).toBeInTheDocument()
      expect(screen.getByText('BenGER')).toBeInTheDocument()
    })

    it('can be used as clickable element when needed', () => {
      const mockClick = jest.fn()
      render(<Logo onClick={mockClick} tabIndex={0} />)

      const logo = screen.getByText('BenGER').parentElement!
      logo.focus()
      logo.click()

      expect(mockClick).toHaveBeenCalled()
    })

    it('supports keyboard navigation when interactive', () => {
      const { container } = render(<Logo tabIndex={0} />)

      const logoContainer = container.firstChild as HTMLElement
      expect(logoContainer).toHaveAttribute('tabIndex', '0')
    })
  })

  describe('branding consistency', () => {
    it('uses consistent brand colors', () => {
      const { container } = render(<Logo />)

      const logoContainer = container.firstChild as HTMLElement
      expect(logoContainer).toHaveClass('text-zinc-900', 'dark:text-white')
    })

    it('uses consistent typography scale', () => {
      const { container } = render(<Logo />)

      const logoContainer = container.firstChild as HTMLElement
      expect(logoContainer).toHaveClass('text-lg', 'font-bold')

      const emoji = screen.getByText('🤘')
      expect(emoji).toHaveClass('text-xl')
    })

    it('maintains brand recognition elements', () => {
      render(<Logo />)

      // Core brand elements should always be present
      expect(screen.getByText('🤘')).toBeInTheDocument() // Brand emoji
      expect(screen.getByText('BenGER')).toBeInTheDocument() // Brand name
    })
  })

  describe('subtitle', () => {
    it('renders subtitle when provided', () => {
      render(<Logo subtitle="Benchmark for German Law" />)
      expect(screen.getByText(/Benchmark for German Law/)).toBeInTheDocument()
    })

    it('does not render subtitle when not provided', () => {
      const { container } = render(<Logo />)
      expect(container.textContent).not.toContain(' - ')
    })

    it('renders subtitle inline with BenGER text', () => {
      render(<Logo subtitle="Benchmark for German Law" />)
      const textSpan = screen.getByText(/BenGER/)
      expect(textSpan.textContent).toContain('BenGER')
      expect(textSpan.textContent).toContain('Benchmark for German Law')
    })
  })
})

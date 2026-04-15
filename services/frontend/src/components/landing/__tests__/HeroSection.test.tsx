import { render, screen } from '@testing-library/react'
import { HeroSection } from '../HeroSection'

// Mock the dependencies
jest.mock('@/components/shared/Button', () => ({
  Button: ({ children, href, className }: any) => (
    <a href={href} className={className}>
      {children}
    </a>
  ),
}))

jest.mock('@/components/shared', () => ({
  HeroPattern: () => <div data-testid="hero-pattern" />,
}))

jest.mock('@/components/shared/RotatingText', () => ({
  RotatingText: ({ words, className }: any) => (
    <span className={className} data-testid="rotating-text">
      {words[0]}
    </span>
  ),
}))

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, varsOrDefault?: any) => {
      const translations: Record<string, any> = require('../../../locales/en/common.json')
      const parts = key.split('.')
      let value: any = translations
      for (const part of parts) {
        if (value && typeof value === 'object' && part in value) {
          value = value[part]
        } else {
          return key
        }
      }
      if (Array.isArray(value)) return value
      if (typeof value !== 'string') return key
      if (varsOrDefault && typeof varsOrDefault === 'object') {
        for (const [k, v] of Object.entries(varsOrDefault)) {
          value = value.replace(new RegExp(`\\{${k}\\}`, 'g'), String(v))
        }
      }
      return value
    },
    locale: 'en',
  }),
}))


describe('HeroSection', () => {
  beforeEach(() => {
  })

  afterEach(() => {
    jest.clearAllMocks()
  })

  describe('rendering', () => {
    it('renders hero pattern background', () => {
      render(<HeroSection />)
      expect(screen.getByTestId('hero-pattern')).toBeInTheDocument()
    })

    it('renders main headline with rotating text', () => {
      render(<HeroSection />)

      expect(screen.getByText(/Do you trust AI with your/)).toBeInTheDocument()
      expect(
        screen.getByText('?')
      ).toBeInTheDocument()
      expect(screen.getByTestId('rotating-text')).toBeInTheDocument()
      expect(screen.getByTestId('rotating-text')).toHaveTextContent(
        'legal briefs'
      )
    })

    it('renders subtitle', () => {
      render(<HeroSection />)

      expect(
        screen.getByText(/Together, we use BenGER/)
      ).toBeInTheDocument()
    })

    it('renders primary CTA button', () => {
      render(<HeroSection />)

      const ctaButton = screen.getByText('Get Started')
      expect(ctaButton).toBeInTheDocument()
      expect(ctaButton.closest('a')).toHaveAttribute('href', '/login')
    })

    it('renders register prompt and link', () => {
      render(<HeroSection />)

      expect(screen.getByText("Don't have an account?")).toBeInTheDocument()

      const registerLink = screen.getByText('Create account')
      expect(registerLink).toBeInTheDocument()
      expect(registerLink.closest('a')).toHaveAttribute('href', '/register')
    })
  })

  describe('styling and layout', () => {
    it('applies responsive padding classes', () => {
      const { container } = render(<HeroSection />)

      const mainContainer = container.firstChild as HTMLElement
      expect(mainContainer).toHaveClass('px-4', 'sm:px-6', 'lg:px-8')
      expect(mainContainer).toHaveClass('pt-8', 'sm:pt-14')
    })

    it('applies correct text sizing classes for headline', () => {
      render(<HeroSection />)

      const headline = screen.getByRole('heading', { level: 1 })
      expect(headline).toHaveClass(
        'text-4xl',
        'sm:text-5xl',
        'md:text-6xl',
        'lg:text-7xl'
      )
      expect(headline).toHaveClass('font-bold', 'tracking-tight')
    })

    it('applies emerald color to rotating text', () => {
      render(<HeroSection />)

      const rotatingText = screen.getByTestId('rotating-text')
      expect(rotatingText).toHaveClass(
        'text-emerald-600',
        'dark:text-emerald-400'
      )
    })

    it('applies correct spacing for subtitle', () => {
      render(<HeroSection />)

      const subtitle = screen.getByText(/Together, we use BenGER/)
      expect(subtitle).toHaveClass('mt-8', 'sm:mt-12')
      expect(subtitle).toHaveClass('text-lg', 'sm:text-xl', 'lg:text-2xl')
    })

    it('applies correct button styling', () => {
      render(<HeroSection />)

      const ctaButton = screen.getByText('Get Started')
      expect(ctaButton).toHaveClass('bg-emerald-600')
      expect(ctaButton).toHaveClass('px-12', 'py-4', 'sm:px-16', 'sm:py-5')
      expect(ctaButton).toHaveClass('text-xl', 'sm:text-2xl')
    })

    it('applies proper spacing for register section', () => {
      render(<HeroSection />)

      const registerSection = screen
        .getByText("Don't have an account?")
        .closest('div')
      expect(registerSection).toHaveClass('mt-8', 'sm:mt-12')
    })
  })

  describe('accessibility', () => {
    it('uses proper heading hierarchy', () => {
      render(<HeroSection />)

      const mainHeading = screen.getByRole('heading', { level: 1 })
      expect(mainHeading).toBeInTheDocument()
    })

    it('provides proper link navigation', () => {
      render(<HeroSection />)

      const loginButton = screen.getByText('Get Started').closest('a')
      const registerLink = screen.getByText('Create account').closest('a')

      expect(loginButton).toHaveAttribute('href', '/login')
      expect(registerLink).toHaveAttribute('href', '/register')
    })

    it('maintains proper color contrast classes', () => {
      render(<HeroSection />)

      const headline = screen.getByRole('heading', { level: 1 })
      expect(headline).toHaveClass('text-zinc-900', 'dark:text-white')

      const subtitle = screen.getByText(/Together, we use BenGER/)
      expect(subtitle).toHaveClass('text-zinc-600', 'dark:text-zinc-400')
    })
  })

  describe('responsive behavior', () => {
    it('adapts container padding for different screen sizes', () => {
      const { container } = render(<HeroSection />)

      const outerContainer = container.firstChild as HTMLElement
      expect(outerContainer).toHaveClass('px-4', 'sm:px-6', 'lg:px-8')
    })

    it('adapts vertical padding for different screen sizes', () => {
      const { container } = render(<HeroSection />)

      const innerContainer = container.querySelector('.mx-auto.max-w-5xl')
      expect(innerContainer).toHaveClass(
        'py-12',
        'sm:py-16',
        'md:py-24',
        'lg:py-32'
      )
    })

    it('scales text appropriately across breakpoints', () => {
      render(<HeroSection />)

      const headline = screen.getByRole('heading', { level: 1 })
      expect(headline).toHaveClass(
        'text-4xl',
        'sm:text-5xl',
        'md:text-6xl',
        'lg:text-7xl'
      )

      const subtitle = screen.getByText(/Together, we use BenGER/)
      expect(subtitle).toHaveClass('text-lg', 'sm:text-xl', 'lg:text-2xl')
    })

    it('adapts button sizing for different screens', () => {
      render(<HeroSection />)

      const ctaButton = screen.getByText('Get Started')
      expect(ctaButton).toHaveClass('px-12', 'py-4', 'sm:px-16', 'sm:py-5')
      expect(ctaButton).toHaveClass('text-xl', 'sm:text-2xl')
    })
  })

  describe('internationalization', () => {
    it('renders all translated text content', () => {
      render(<HeroSection />)

      expect(screen.getByText(/Do you trust AI with your/)).toBeInTheDocument()
      expect(screen.getByText(/Together, we use BenGER/)).toBeInTheDocument()
      expect(screen.getByText('Get Started')).toBeInTheDocument()
      expect(screen.getByText("Don't have an account?")).toBeInTheDocument()
      expect(screen.getByText('Create account')).toBeInTheDocument()
    })

    it('passes rotating words array to RotatingText component', () => {
      render(<HeroSection />)

      const rotatingText = screen.getByTestId('rotating-text')
      expect(rotatingText).toBeInTheDocument()
      // The mock shows the first word from the array
      expect(rotatingText).toHaveTextContent('legal briefs')
    })
  })

  describe('component structure', () => {
    it('maintains proper DOM hierarchy', () => {
      const { container } = render(<HeroSection />)

      const outerDiv = container.firstChild as HTMLElement
      expect(outerDiv).toHaveClass('relative', 'isolate')

      const innerContainer = outerDiv.querySelector('.mx-auto.max-w-5xl')
      expect(innerContainer).toBeInTheDocument()

      const centeringDiv = innerContainer?.querySelector('.text-center')
      expect(centeringDiv).toBeInTheDocument()
    })

    it('positions hero pattern correctly', () => {
      render(<HeroSection />)

      const heroPattern = screen.getByTestId('hero-pattern')
      expect(heroPattern).toBeInTheDocument()
    })

    it('maintains proper spacing between sections', () => {
      render(<HeroSection />)

      const ctaSection = screen.getByText('Get Started').closest('div')
      expect(ctaSection).toHaveClass('mt-12', 'sm:mt-16')

      const registerSection = screen
        .getByText("Don't have an account?")
        .closest('div')
      expect(registerSection).toHaveClass('mt-8', 'sm:mt-12')
    })
  })
})

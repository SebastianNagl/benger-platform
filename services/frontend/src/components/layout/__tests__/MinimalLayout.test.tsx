/**
 * @jest-environment jsdom
 */
import { render, screen } from '@testing-library/react'
import { MinimalLayout } from '../MinimalLayout'

jest.mock('@/components/layout/SectionProvider', () => ({
  SectionProvider: ({ children, sections }: any) => (
    <div
      data-testid="section-provider"
      data-sections={JSON.stringify(sections)}
    >
      {children}
    </div>
  ),
}))

jest.mock('@/components/layout/Logo', () => ({
  Logo: ({ className }: any) => <div data-testid="logo" className={className} />,
}))

jest.mock('@/components/layout/ThemeToggle', () => ({
  ThemeToggle: () => <div data-testid="theme-toggle">Theme Toggle</div>,
}))

jest.mock('@/components/layout/LanguageSwitcher', () => ({
  LanguageSwitcher: () => (
    <div data-testid="language-switcher">Language Switcher</div>
  ),
}))

jest.mock('next/navigation', () => ({
  usePathname: () => '/about/imprint',
}))

jest.mock('next/link', () => ({
  __esModule: true,
  default: ({ children, href, onClick, ...props }: any) => (
    <a href={href} onClick={onClick} {...props}>
      {children}
    </a>
  ),
}))

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string) => {
      const translations: Record<string, string> = {
        'landing.nav.information': 'Information',
        'landing.nav.news': 'News',
        'landing.nav.people': 'People',
        'landing.nav.license': 'License',
        'landing.nav.login': 'Login',
        'footer.imprint': 'Imprint',
        'footer.dataProtection': 'Data Protection',
        'footer.github': 'GitHub',
        'footer.copyright': 'Copyright',
        'footer.allRightsReserved': 'All rights reserved.',
      }
      return translations[key] || key
    },
    locale: 'en',
  }),
}))

describe('MinimalLayout', () => {
  it('renders header, main, footer landmarks with children inside main', () => {
    const { container } = render(
      <MinimalLayout>
        <div>Body content</div>
      </MinimalLayout>
    )

    expect(container.querySelector('header')).toBeInTheDocument()
    const main = container.querySelector('main')
    expect(main).toBeInTheDocument()
    expect(main).toHaveTextContent('Body content')
    expect(container.querySelector('footer')).toBeInTheDocument()
  })

  it('wraps content in a SectionProvider', () => {
    render(
      <MinimalLayout sections={[]}>
        <div>Content</div>
      </MinimalLayout>
    )

    expect(screen.getByTestId('section-provider')).toBeInTheDocument()
  })

  it('passes sections through to SectionProvider', () => {
    const sections = [
      { id: 's1', title: 'Section 1' },
      { id: 's2', title: 'Section 2' },
    ]
    render(
      <MinimalLayout sections={sections}>
        <div>Content</div>
      </MinimalLayout>
    )

    expect(screen.getByTestId('section-provider')).toHaveAttribute(
      'data-sections',
      JSON.stringify(sections)
    )
  })

  it('shares the SiteHeader chrome with the landing page', () => {
    render(
      <MinimalLayout>
        <div>Content</div>
      </MinimalLayout>
    )

    expect(screen.getByTestId('logo')).toBeInTheDocument()
    expect(screen.getByTestId('language-switcher')).toBeInTheDocument()
    expect(screen.getByTestId('theme-toggle')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Login' })).toHaveAttribute(
      'href',
      '/login'
    )
  })

  it('shares the SiteFooter with the landing page (corrected GitHub URL, no Notion)', () => {
    render(
      <MinimalLayout>
        <div>Content</div>
      </MinimalLayout>
    )

    expect(screen.getByRole('link', { name: 'Imprint' })).toHaveAttribute(
      'href',
      '/about/imprint'
    )
    expect(
      screen.getByRole('link', { name: 'Data Protection' })
    ).toHaveAttribute('href', '/about/data-protection')
    expect(screen.getByRole('link', { name: 'GitHub' })).toHaveAttribute(
      'href',
      'https://github.com/SebastianNagl/benger-platform'
    )
    expect(
      screen.queryByRole('link', { name: /Notion/ })
    ).not.toBeInTheDocument()
  })

  it('renders the prose-styled content wrapper at the centred max-w-4xl width', () => {
    const { container } = render(
      <MinimalLayout>
        <div>Content</div>
      </MinimalLayout>
    )

    const main = container.querySelector('main')
    expect(main).toHaveClass('mx-auto', 'max-w-4xl')

    const proseWrapper = container.querySelector('.prose')
    expect(proseWrapper).toHaveClass(
      'prose',
      'prose-zinc',
      'max-w-none',
      'dark:prose-invert'
    )
  })

  it('applies w-full on the root so flex body parents centre correctly', () => {
    const { container } = render(
      <MinimalLayout>
        <div>Content</div>
      </MinimalLayout>
    )

    const root = container.querySelector('[data-testid="section-provider"] > div')
    expect(root).toHaveClass('min-h-screen', 'w-full', 'bg-white')
  })
})

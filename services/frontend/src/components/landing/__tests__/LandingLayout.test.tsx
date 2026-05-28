import { render, screen } from '@testing-library/react'
import { LandingLayout } from '../LandingLayout'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string) => {
      const translations: Record<string, string> = {
        'landing.nav.information': 'Information',
        'landing.nav.news': 'News & Publications',
        'landing.nav.people': 'People & Network',
        'landing.nav.license': 'License & Citation',
        'landing.nav.login': 'Login',
        'layout.footer.imprint': 'Impressum',
        'layout.footer.dataProtection': 'Datenschutz',
        'layout.footer.followGithub': 'Follow us on GitHub',
        'layout.footer.allRightsReserved': 'All rights reserved.',
      }
      return translations[key] || key
    },
    locale: 'en',
  }),
}))

jest.mock('next/navigation', () => ({
  usePathname: () => '/',
}))

jest.mock('next/link', () => {
  function Link({ href, className, children, onClick, ...rest }: any) {
    return (
      <a href={href} className={className} onClick={onClick} {...rest}>
        {children}
      </a>
    )
  }
  return Link
})

jest.mock('@/components/layout/Logo', () => ({
  Logo: ({ className }: any) => <div data-testid="logo" className={className} />,
}))

jest.mock('@/components/layout/ThemeToggle', () => ({
  ThemeToggle: () => <button data-testid="theme-toggle">Theme</button>,
}))

jest.mock('@/components/layout/LanguageSwitcher', () => ({
  LanguageSwitcher: () => (
    <select data-testid="language-switcher">
      <option>en</option>
    </select>
  ),
}))

describe('LandingLayout', () => {
  const TestContent = () => <div data-testid="test-content">Test Content</div>

  it('renders header, main, and footer landmarks with children inside main', () => {
    render(
      <LandingLayout>
        <TestContent />
      </LandingLayout>
    )

    expect(screen.getByRole('banner')).toBeInTheDocument()
    const main = screen.getByRole('main')
    expect(main).toContainElement(screen.getByTestId('test-content'))
    expect(screen.getByRole('contentinfo')).toBeInTheDocument()
  })

  it('renders the SiteHeader chrome (logo, section tabs, login)', () => {
    render(
      <LandingLayout>
        <TestContent />
      </LandingLayout>
    )

    expect(screen.getByTestId('logo')).toBeInTheDocument()
    expect(screen.getByText('Information')).toBeInTheDocument()
    expect(screen.getByText('News & Publications')).toBeInTheDocument()
    expect(screen.getByText('People & Network')).toBeInTheDocument()
    expect(screen.getByText('License & Citation')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Login' })).toHaveAttribute(
      'href',
      '/login'
    )
    expect(screen.getByTestId('theme-toggle')).toBeInTheDocument()
    expect(screen.getByTestId('language-switcher')).toBeInTheDocument()
  })

  it('renders the shared Footer with legal links and the corrected GitHub URL', () => {
    render(
      <LandingLayout>
        <TestContent />
      </LandingLayout>
    )

    expect(screen.getByRole('link', { name: 'Impressum' })).toHaveAttribute(
      'href',
      '/about/imprint'
    )
    expect(screen.getByRole('link', { name: 'Datenschutz' })).toHaveAttribute(
      'href',
      '/about/data-protection'
    )
    expect(
      screen.getByRole('link', { name: /Follow us on GitHub/ })
    ).toHaveAttribute(
      'href',
      'https://github.com/SebastianNagl/benger-platform'
    )
  })

  it('no longer renders the Notion follow link', () => {
    render(
      <LandingLayout>
        <TestContent />
      </LandingLayout>
    )

    expect(
      screen.queryByRole('link', { name: /Notion/ })
    ).not.toBeInTheDocument()
    expect(screen.queryByText(/legaltechcolab/)).not.toBeInTheDocument()
  })
})

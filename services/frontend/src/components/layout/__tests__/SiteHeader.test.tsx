/**
 * @jest-environment jsdom
 *
 * Behavioral coverage for SiteHeader — the public landing-page header.
 * Covers: nav rendering, the isHome IntersectionObserver effect (active-section
 * highlight), the non-home short-circuit, and handleSectionClick smooth-scroll +
 * history.replaceState behavior (home vs non-home branches).
 *
 * Child widgets (Logo / LanguageSwitcher / ThemeToggle) are mocked so the test
 * stays focused on SiteHeader's own logic and doesn't pull in next-themes /
 * HydrationContext.
 */

import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { usePathname } from 'next/navigation'
import { SiteHeader } from '../SiteHeader'

// next/navigation: usePathname is the lever for the isHome branch.
jest.mock('next/navigation', () => ({
  usePathname: jest.fn(),
}))
const mockUsePathname = usePathname as jest.Mock

// next/link → plain anchor so onClick + href are observable.
jest.mock('next/link', () => {
  return function Link({
    children,
    href,
    onClick,
    className,
    ...props
  }: {
    children: React.ReactNode
    href: string
    onClick?: (e: any) => void
    className?: string
    [key: string]: any
  }) {
    return (
      <a href={href} onClick={onClick} className={className} {...props}>
        {children}
      </a>
    )
  }
})

// i18n: echo the key so we can assert on nav keys directly.
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({ t: (key: string) => key }),
}))

// Stub the child widgets.
jest.mock('../Logo', () => ({
  Logo: (props: any) => <div data-testid="logo" className={props.className} />,
}))
jest.mock('../LanguageSwitcher', () => ({
  LanguageSwitcher: () => <div data-testid="language-switcher" />,
}))
jest.mock('../ThemeToggle', () => ({
  ThemeToggle: () => <div data-testid="theme-toggle" />,
}))

// Capture the IntersectionObserver callback so tests can drive entries.
type IOEntry = { target: { id: string }; isIntersecting: boolean }
let ioCallback: ((entries: IOEntry[]) => void) | null = null
let ioObserved: string[] = []
let ioDisconnected = false

class MockIntersectionObserver {
  constructor(cb: (entries: IOEntry[]) => void) {
    ioCallback = cb
  }
  observe(el: Element) {
    ioObserved.push((el as HTMLElement).id)
  }
  unobserve() {}
  disconnect() {
    ioDisconnected = true
  }
}

describe('SiteHeader', () => {
  const NAV_IDS = ['information', 'news', 'people', 'license']

  beforeEach(() => {
    jest.clearAllMocks()
    ioCallback = null
    ioObserved = []
    ioDisconnected = false
    ;(global as any).IntersectionObserver = MockIntersectionObserver
    mockUsePathname.mockReturnValue('/')
    // Provide the section anchor elements the effect observes.
    document.body.innerHTML = ''
    NAV_IDS.forEach((id) => {
      const el = document.createElement('section')
      el.id = id
      document.body.appendChild(el)
    })
  })

  it('renders all nav sections, the logo, and the login link', () => {
    render(<SiteHeader />)

    NAV_IDS.forEach((id) => {
      expect(screen.getByText(`landing.nav.${id}`)).toBeInTheDocument()
    })
    expect(screen.getByTestId('logo')).toBeInTheDocument()
    expect(screen.getByTestId('language-switcher')).toBeInTheDocument()
    expect(screen.getByTestId('theme-toggle')).toBeInTheDocument()
    expect(screen.getByText('landing.nav.login')).toBeInTheDocument()
  })

  it('observes every section anchor when on the home page', () => {
    render(<SiteHeader />)
    expect(ioObserved.sort()).toEqual([...NAV_IDS].sort())
  })

  it('highlights the active section when its anchor intersects', () => {
    render(<SiteHeader />)
    expect(ioCallback).not.toBeNull()

    // Drive the observer: "news" becomes visible. Wrap in act() so the
    // setActiveSection state update flushes before we assert.
    act(() => {
      ioCallback!([{ target: { id: 'news' }, isIntersecting: true }])
    })

    const newsLink = screen.getByText('landing.nav.news')
    expect(newsLink.className).toContain('bg-emerald-50')

    // A non-active section keeps the muted styling.
    const peopleLink = screen.getByText('landing.nav.people')
    expect(peopleLink.className).not.toContain('bg-emerald-50')
  })

  it('clears the highlight when the active section scrolls out of view', () => {
    render(<SiteHeader />)
    act(() => {
      ioCallback!([{ target: { id: 'news' }, isIntersecting: true }])
    })
    expect(screen.getByText('landing.nav.news').className).toContain(
      'bg-emerald-50'
    )

    act(() => {
      ioCallback!([{ target: { id: 'news' }, isIntersecting: false }])
    })
    expect(screen.getByText('landing.nav.news').className).not.toContain(
      'bg-emerald-50'
    )
  })

  it('disconnects the observer on unmount', () => {
    const { unmount } = render(<SiteHeader />)
    unmount()
    expect(ioDisconnected).toBe(true)
  })

  it('does not set up an observer when off the home page', () => {
    mockUsePathname.mockReturnValue('/dashboard')
    render(<SiteHeader />)
    // The non-home branch returns early without observing.
    expect(ioObserved).toHaveLength(0)
  })

  it('handleSectionClick scrolls + rewrites history on the home page', async () => {
    const user = userEvent.setup()
    const scrollSpy = jest.fn()
    document
      .getElementById('people')!
      .scrollIntoView = scrollSpy as any
    const replaceStateSpy = jest.spyOn(window.history, 'replaceState')

    render(<SiteHeader />)

    await user.click(screen.getByText('landing.nav.people'))

    expect(scrollSpy).toHaveBeenCalledWith({ behavior: 'smooth' })
    expect(replaceStateSpy).toHaveBeenCalledWith(null, '', '/#people')
    replaceStateSpy.mockRestore()
  })

  it('handleSectionClick is a no-op (default navigation) when off the home page', async () => {
    mockUsePathname.mockReturnValue('/dashboard')
    const user = userEvent.setup()
    const replaceStateSpy = jest.spyOn(window.history, 'replaceState')

    render(<SiteHeader />)

    await user.click(screen.getByText('landing.nav.information'))

    // Off-home click returns early: no smooth-scroll history rewrite.
    expect(replaceStateSpy).not.toHaveBeenCalled()
    replaceStateSpy.mockRestore()
  })
})

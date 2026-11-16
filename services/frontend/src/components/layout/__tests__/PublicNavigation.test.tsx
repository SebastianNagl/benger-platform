/**
 * @jest-environment jsdom
 */
import { fireEvent, render, screen, within } from '@testing-library/react'
import { usePublicNavigation } from '../PublicNavigation'

let mockLocale: 'de' | 'en' | 'fr' = 'en'
jest.mock('@/contexts/I18nContext', () =>
  require('@/test-utils/i18nMock').i18nMock(() => mockLocale),
)

jest.mock('next/link', () => {
  const React = require('react')
  return React.forwardRef(function Link({ href, ...props }: any, ref: any) {
    return <a ref={ref} href={href} {...props} />
  })
})

jest.mock('next/navigation', () => ({
  usePathname: jest.fn(),
}))

let mockVisibleSections: string[] = []
jest.mock('@/components/layout/SectionProvider', () => ({
  useSectionStore: (selector: (state: unknown) => unknown) =>
    selector({ sections: [], visibleSections: mockVisibleSections }),
}))

const mockUsePathname = require('next/navigation').usePathname

function Bar() {
  const { inline, menu } = usePublicNavigation()
  return (
    <div>
      {inline}
      {menu}
    </div>
  )
}

/** Lay the bar out with the given free width and natural list width. */
function mockWidths(free: number, needed: number, displayed = true) {
  jest
    .spyOn(HTMLElement.prototype, 'getClientRects')
    .mockImplementation(() => (displayed ? [{}] : []) as unknown as DOMRectList)
  jest
    .spyOn(HTMLElement.prototype, 'clientWidth', 'get')
    .mockImplementation(() => free)
  jest
    .spyOn(HTMLElement.prototype, 'scrollWidth', 'get')
    .mockImplementation(() => needed)
}

const inlineLinks = () =>
  within(screen.getByTestId('public-nav-inline')).getAllByRole('link', {
    hidden: true,
  })

describe('PublicNavigation', () => {
  beforeEach(() => {
    mockLocale = 'en'
    mockVisibleSections = []
    mockUsePathname.mockReturnValue('/')
  })

  afterEach(() => {
    jest.restoreAllMocks()
  })

  it('lists the landing sections and the public pages', () => {
    mockWidths(1000, 600)
    render(<Bar />)
    expect(
      inlineLinks().map((link) => [
        link.textContent,
        link.getAttribute('href'),
      ]),
    ).toEqual([
      ['Information', '/#information'],
      ['News & Publications', '/#news'],
      ['Group & Network', '/#people'],
      ['License & Citation', '/#license'],
      ['Reports', '/reports'],
      ['Changelog', '/changelog'],
    ])
  })

  it.each([
    ['de', ['Information', 'News & Publikationen', 'Berichte', 'Changelog']],
    [
      'fr',
      [
        'Informations',
        'Actualités et publications',
        'Rapports',
        'Journal des modifications',
      ],
    ],
  ] as const)('translates the items (%s)', (locale, labels) => {
    mockLocale = locale
    mockWidths(2000, 600)
    render(<Bar />)
    const texts = inlineLinks().map((link) => link.textContent)
    for (const label of labels) expect(texts).toContain(label)
  })

  it('highlights the landing section in view, not the hero', () => {
    mockWidths(1000, 600)
    mockVisibleSections = ['_top', 'news', 'people']
    render(<Bar />)
    const current = inlineLinks().filter((link) =>
      link.hasAttribute('aria-current'),
    )
    expect(current.map((link) => link.getAttribute('href'))).toEqual(['/#news'])
    expect(current[0]).toHaveAttribute('aria-current', 'location')
  })

  it.each([
    ['/reports', '/reports'],
    ['/reports/42', '/reports'],
    ['/changelog', '/changelog'],
  ])('marks %s as the current page', (path, href) => {
    mockUsePathname.mockReturnValue(path)
    // Off the landing page no section counts as in view.
    mockVisibleSections = ['news']
    mockWidths(1000, 600)
    render(<Bar />)
    const current = inlineLinks().filter((link) =>
      link.hasAttribute('aria-current'),
    )
    expect(current.map((link) => link.getAttribute('href'))).toEqual([href])
    expect(current[0]).toHaveAttribute('aria-current', 'page')
  })

  it('keeps the items in the bar while they fit', () => {
    mockWidths(1000, 600)
    render(<Bar />)
    expect(screen.getByTestId('public-nav-inline')).toHaveAttribute(
      'data-fits',
      'true',
    )
    expect(inlineLinks()[0]).not.toHaveAttribute('tabindex')
    expect(screen.getByTestId('public-nav-menu-root')).toHaveClass('hidden')
  })

  it('collapses the items into the menu when they do not fit', () => {
    mockWidths(400, 600)
    render(<Bar />)
    expect(screen.getByTestId('public-nav-inline')).toHaveAttribute(
      'data-fits',
      'false',
    )
    // Out of sight and out of the tab order; the menu takes over.
    for (const link of inlineLinks())
      expect(link).toHaveAttribute('tabindex', '-1')
    expect(screen.getByTestId('public-nav-menu-root')).not.toHaveClass('hidden')
  })

  it('uses the menu on phones, where the bar shows no items', () => {
    mockWidths(0, 0, false)
    render(<Bar />)
    expect(screen.getByTestId('public-nav-inline')).toHaveAttribute(
      'data-fits',
      'false',
    )
    expect(screen.getByTestId('public-nav-menu-root')).not.toHaveClass('hidden')
  })

  it('opens a compact menu with the items and the way in', () => {
    mockWidths(400, 600)
    render(<Bar />)
    fireEvent.click(screen.getByTestId('public-nav-menu-button'))
    const menu = screen.getByTestId('public-nav-menu')
    const hrefs = within(menu)
      .getAllByRole('link')
      .map((link) => link.getAttribute('href'))
    expect(hrefs).toEqual([
      '/#information',
      '/#news',
      '/#people',
      '/#license',
      '/reports',
      '/changelog',
      '/login',
      '/register',
    ])
  })

  it('scrolls smoothly to a section on the landing page', () => {
    mockWidths(1000, 600)
    const section = document.createElement('section')
    section.id = 'people'
    section.scrollIntoView = jest.fn()
    document.body.appendChild(section)
    try {
      render(<Bar />)
      const link = inlineLinks().find(
        (l) => l.getAttribute('href') === '/#people',
      )!
      const notPrevented = fireEvent.click(link)
      expect(notPrevented).toBe(false)
      expect(section.scrollIntoView).toHaveBeenCalledWith({
        behavior: 'smooth',
      })
      expect(window.location.hash).toBe('#people')
    } finally {
      section.remove()
    }
  })

  it('leaves section links to the router on other pages', () => {
    mockUsePathname.mockReturnValue('/reports')
    mockWidths(1000, 600)
    render(<Bar />)
    const section = document.createElement('section')
    section.id = 'news'
    section.scrollIntoView = jest.fn()
    document.body.appendChild(section)
    try {
      const link = inlineLinks().find(
        (l) => l.getAttribute('href') === '/#news',
      )!
      // The link navigates to /#news; the click is not taken over.
      expect(fireEvent.click(link)).toBe(true)
      expect(section.scrollIntoView).not.toHaveBeenCalled()
    } finally {
      section.remove()
    }
  })
})

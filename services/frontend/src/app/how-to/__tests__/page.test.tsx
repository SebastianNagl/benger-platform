/**
 * @jest-environment jsdom
 *
 * /how-to — the guide catalog. Guides come from the registry, so the test
 * registers its own small set and asserts grouping, chips, TOC and the
 * deep-link scroll. (Searching is the nav-bar search's job.)
 */
import '@testing-library/jest-dom'
import { fireEvent, render, screen } from '@testing-library/react'

import { registerHowToGuides, type HowToGuide } from '@/lib/howto'

import HowToPage from '../page'

let mockLocale = 'de'
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    locale: mockLocale,
    t: (key: string, fallback?: any, vars?: Record<string, unknown>) => {
      let text = typeof fallback === 'string' ? fallback : key
      const v = vars ?? (typeof fallback === 'object' ? fallback : undefined)
      if (v) Object.entries(v).forEach(([k, val]) => { text = text.replace(`{${k}}`, String(val)) })
      return text
    },
  }),
}))
jest.mock('@/components/shared/ResponsiveContainer', () => ({
  ResponsiveContainer: ({ children }: any) => <div>{children}</div>,
}))
jest.mock('@/components/shared/Breadcrumb', () => ({
  Breadcrumb: () => <nav data-testid="breadcrumb" />,
}))
jest.mock('next/link', () => ({
  __esModule: true,
  default: ({ href, children, ...rest }: any) => <a href={href} {...rest}>{children}</a>,
}))

const GUIDES: HowToGuide[] = [
  {
    id: 'what-is-benger',
    category: 'start',
    title: { de: 'Was ist BenGER?', en: 'What is BenGER?' },
    summary: { de: 'Die Expertenplattform.', en: 'The expert platform.' },
  },
  {
    id: 'api-keys',
    category: 'generation',
    title: { de: 'Wie hinterlege ich einen API-Schlüssel?', en: 'How do I add an API key?' },
    summary: { de: 'Unter **Einstellungen** → `Modelle` (*optional*).', en: 'Under **Settings** → `Models` (*optional*).' },
    steps: { de: ['Öffnen Sie [Modelle](/settings/models).', 'Schlüssel einfügen.'], en: ['Open [Models](/settings/models).', 'Paste the key.'] },
    tips: { de: ['Der Schlüssel wird verschlüsselt gespeichert.'], en: ['The key is stored encrypted.'] },
    pitfalls: { de: ['Ohne Guthaben schlägt die Generierung fehl.'], en: ['Without credit the generation fails.'] },
    links: [{ label: { de: 'Modellkatalog', en: 'Model catalog' }, href: '/models' }],
    keywords: { de: ['OpenAI'], en: ['provider'] },
  },
  {
    id: 'invite-group',
    category: 'organizations',
    title: { de: 'Wie lade ich jemanden in eine Gruppe ein?', en: 'How do I invite someone to a group?' },
    summary: { de: 'Über den Gruppen-Einladungslink.', en: 'Via the group invitation link.' },
  },
]

beforeEach(() => {
  mockLocale = 'de'
  registerHowToGuides('platform', GUIDES)
  registerHowToGuides('extended', [])
  window.location.hash = ''
})

describe('HowToPage', () => {
  it('renders the title, the search box and every guide grouped by category', () => {
    render(<HowToPage />)
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Anleitungen')
    expect(screen.queryByTestId('howto-search')).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 2, name: 'Erste Schritte' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 2, name: 'KI-Modelle & Generierung' })).toBeInTheDocument()
    expect(screen.getByTestId('howto-guide-what-is-benger')).toBeInTheDocument()
    expect(screen.getByTestId('howto-guide-api-keys')).toBeInTheDocument()
    expect(screen.getByTestId('howto-guide-invite-group')).toBeInTheDocument()
  })

  it('renders steps, tips, pitfalls, related links and inline formatting', () => {
    render(<HowToPage />)
    const card = screen.getByTestId('howto-guide-api-keys')
    expect(card).toHaveTextContent('Schlüssel einfügen.')
    expect(card).toHaveTextContent('Gut zu wissen')
    expect(card).toHaveTextContent('Typische Stolpersteine')
    expect(card.querySelector('strong')).toHaveTextContent('Einstellungen')
    expect(card.querySelector('code')).toHaveTextContent('Modelle')
    expect(card.querySelector('em')).toHaveTextContent('optional')
    expect(screen.getByRole('link', { name: 'Modelle' })).toHaveAttribute('href', '/settings/models')
    expect(screen.getByRole('link', { name: /Modellkatalog/ })).toHaveAttribute('href', '/models')
  })

  it('narrows to one category via the chips and toggles back', () => {
    render(<HowToPage />)
    fireEvent.click(screen.getByRole('button', { name: /Organisationen, Gruppen & Einladungen/ }))
    expect(screen.getByTestId('howto-guide-invite-group')).toBeInTheDocument()
    expect(screen.queryByTestId('howto-guide-api-keys')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Organisationen, Gruppen & Einladungen/ }))
    expect(screen.getByTestId('howto-guide-api-keys')).toBeInTheDocument()
  })

  it('lists every visible guide in the table of contents', () => {
    render(<HowToPage />)
    const toc = screen.getByTestId('howto-toc')
    expect(toc).toHaveTextContent('Was ist BenGER?')
    expect(toc.querySelector('a[href="#api-keys"]')).toBeInTheDocument()
  })

  it('renders English copy when the locale is en', () => {
    mockLocale = 'en'
    render(<HowToPage />)
    expect(screen.getByRole('heading', { level: 2, name: 'Getting started' })).toBeInTheDocument()
    expect(screen.getByTestId('howto-guide-api-keys')).toHaveTextContent('How do I add an API key?')
  })

  it('scrolls to the guide named in the URL hash', () => {
    window.location.hash = '#invite-group'
    const spy = jest.fn()
    Element.prototype.scrollIntoView = spy
    render(<HowToPage />)
    expect(spy).toHaveBeenCalled()
  })
})

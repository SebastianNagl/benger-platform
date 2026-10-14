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
import { registerTranslations } from '@/lib/i18n/catalog'

import HowToPage from '../page'

let mockLocale = 'de'
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    locale: mockLocale,
    // The real catalog, so labels render as users see them.
    t: (key: string, vars?: Record<string, unknown>) =>
      jest
        .requireActual('@/lib/i18n/catalog')
        .translateKey(mockLocale, key, vars),
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
  default: ({ href, children, ...rest }: any) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}))

const GUIDES: HowToGuide[] = [
  { id: 't-what-is-benger', category: 'start' },
  { id: 't-api-keys', category: 'generation', links: ['/models'] },
  { id: 't-invite-group', category: 'organizations' },
]

// Guide copy lives in the catalog; the test guides bring their own.
registerTranslations('howto-page-test', {
  de: {
    howToGuides: {
      't-what-is-benger': {
        title: 'Was ist BenGER?',
        summary: 'Die Expertenplattform.',
      },
      't-api-keys': {
        title: 'Wie hinterlege ich einen API-Schlüssel?',
        summary: 'Unter **Einstellungen** → `Modelle` (*optional*).',
        steps: [
          'Öffnen Sie [Modelle](/settings/models).',
          'Schlüssel einfügen.',
        ],
        tips: ['Der Schlüssel wird verschlüsselt gespeichert.'],
        pitfalls: ['Ohne Guthaben schlägt die Generierung fehl.'],
        links: ['Modellkatalog'],
        keywords: ['OpenAI'],
      },
      't-invite-group': {
        title: 'Wie lade ich jemanden in eine Gruppe ein?',
        summary: 'Über den Gruppen-Einladungslink.',
      },
    },
  },
  en: {
    howToGuides: {
      't-what-is-benger': {
        title: 'What is BenGER?',
        summary: 'The expert platform.',
      },
      't-api-keys': {
        title: 'How do I add an API key?',
        summary: 'Under **Settings** → `Models` (*optional*).',
        steps: ['Open [Models](/settings/models).', 'Paste the key.'],
        tips: ['The key is stored encrypted.'],
        pitfalls: ['Without credit the generation fails.'],
        links: ['Model catalog'],
        keywords: ['provider'],
      },
      't-invite-group': {
        title: 'How do I invite someone to a group?',
        summary: 'Via the group invitation link.',
      },
    },
  },
  fr: {},
})

beforeEach(() => {
  mockLocale = 'de'
  registerHowToGuides('platform', GUIDES)
  registerHowToGuides('extended', [])
  window.location.hash = ''
})

describe('HowToPage', () => {
  it('renders the title, the search box and every guide grouped by category', () => {
    render(<HowToPage />)
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(
      'Anleitungen',
    )
    expect(screen.queryByTestId('howto-search')).not.toBeInTheDocument()
    expect(
      screen.getByRole('heading', { level: 2, name: 'Erste Schritte' }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('heading', {
        level: 2,
        name: 'KI-Modelle & Generierung',
      }),
    ).toBeInTheDocument()
    expect(
      screen.getByTestId('howto-guide-t-what-is-benger'),
    ).toBeInTheDocument()
    expect(screen.getByTestId('howto-guide-t-api-keys')).toBeInTheDocument()
    expect(screen.getByTestId('howto-guide-t-invite-group')).toBeInTheDocument()
  })

  it('renders steps, tips, pitfalls, related links and inline formatting', () => {
    render(<HowToPage />)
    const card = screen.getByTestId('howto-guide-t-api-keys')
    expect(card).toHaveTextContent('Schlüssel einfügen.')
    expect(card).toHaveTextContent('Gut zu wissen')
    expect(card).toHaveTextContent('Typische Stolpersteine')
    expect(card.querySelector('strong')).toHaveTextContent('Einstellungen')
    expect(card.querySelector('code')).toHaveTextContent('Modelle')
    expect(card.querySelector('em')).toHaveTextContent('optional')
    expect(screen.getByRole('link', { name: 'Modelle' })).toHaveAttribute(
      'href',
      '/settings/models',
    )
    expect(screen.getByRole('link', { name: /Modellkatalog/ })).toHaveAttribute(
      'href',
      '/models',
    )
  })

  it('narrows to one category via the chips and toggles back', () => {
    render(<HowToPage />)
    fireEvent.click(
      screen.getByRole('button', {
        name: /Organisationen, Gruppen & Einladungen/,
      }),
    )
    expect(screen.getByTestId('howto-guide-t-invite-group')).toBeInTheDocument()
    expect(
      screen.queryByTestId('howto-guide-t-api-keys'),
    ).not.toBeInTheDocument()
    fireEvent.click(
      screen.getByRole('button', {
        name: /Organisationen, Gruppen & Einladungen/,
      }),
    )
    expect(screen.getByTestId('howto-guide-t-api-keys')).toBeInTheDocument()
  })

  it('lists every visible guide in the table of contents', () => {
    render(<HowToPage />)
    const toc = screen.getByTestId('howto-toc')
    expect(toc).toHaveTextContent('Was ist BenGER?')
    expect(toc.querySelector('a[href="#t-api-keys"]')).toBeInTheDocument()
  })

  it('renders English copy when the locale is en', () => {
    mockLocale = 'en'
    render(<HowToPage />)
    expect(
      screen.getByRole('heading', { level: 2, name: 'Getting started' }),
    ).toBeInTheDocument()
    expect(screen.getByTestId('howto-guide-t-api-keys')).toHaveTextContent(
      'How do I add an API key?',
    )
  })

  it('scrolls to the guide named in the URL hash', () => {
    window.location.hash = '#t-invite-group'
    const spy = jest.fn()
    Element.prototype.scrollIntoView = spy
    render(<HowToPage />)
    expect(spy).toHaveBeenCalled()
  })
})

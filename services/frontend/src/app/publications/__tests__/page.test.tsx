/**
 * @jest-environment jsdom
 *
 * /publications renders our publications from the landing page's news list
 * (one source, so the two cannot drift apart), the related publications,
 * similar projects and research groups from data/publicationsNetwork.ts,
 * each linking to its canonical page, in every locale.
 */
import '@testing-library/jest-dom'
import { render, screen, within } from '@testing-library/react'

import {
  ALL_NETWORK_ENTRY_IDS,
  OUR_GROUP,
  OUR_PAPER_LINKS,
  RELATED_GROUPS,
  RELATED_PUBLICATIONS,
  SIMILAR_PROJECTS,
} from '@/data/publicationsNetwork'
import { getMessages, lookup } from '@/lib/i18n/catalog'

import PublicationsPage from '../page'

let mockLocale = 'de'
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    locale: mockLocale,
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

const LOCALES = ['de', 'en', 'fr'] as const

type NewsItem = { title: string; type: string; url?: string }
const newsItems = (locale: string) =>
  lookup(locale as any, 'landing.news.items') as unknown as NewsItem[]

beforeEach(() => {
  mockLocale = 'de'
})

describe('PublicationsPage', () => {
  it.each(LOCALES)(
    'lists exactly the landing page publications in %s, with their paper links',
    (locale) => {
      mockLocale = locale
      render(<PublicationsPage />)
      const ours = screen.getByTestId('publications-ours')
      const expected = newsItems(locale).filter((i) => i.type === 'publication')
      expect(expected.length).toBeGreaterThan(0)
      const titles = within(ours)
        .getAllByRole('heading', { level: 3 })
        .map((h) => h.textContent)
      expect(titles).toEqual(expected.map((i) => i.title))
      for (const item of expected) {
        expect(ours.querySelector(`a[href="${item.url}"]`)).not.toBeNull()
        const paper = OUR_PAPER_LINKS[item.url ?? '']
        if (paper) {
          expect(ours.querySelector(`a[href="${paper}"]`)).not.toBeNull()
        }
      }
    },
  )

  it('leaves news entries out of our publications', () => {
    render(<PublicationsPage />)
    const ours = screen.getByTestId('publications-ours')
    for (const item of newsItems('de').filter((i) => i.type === 'news')) {
      expect(ours).not.toHaveTextContent(item.title)
    }
  })

  it('renders every external entry as an external link with its note', () => {
    mockLocale = 'en'
    render(<PublicationsPage />)
    for (const pub of RELATED_PUBLICATIONS) {
      const card = screen.getByTestId(`publication-${pub.id}`)
      const link = within(card).getByRole('link', { name: pub.title })
      expect(link).toHaveAttribute('href', pub.url)
      expect(link).toHaveAttribute('target', '_blank')
      expect(link).toHaveAttribute('rel', 'noopener noreferrer')
      expect(card).toHaveTextContent(
        String(lookup('en', `publicationsNetwork.entries.${pub.id}`)),
      )
      expect(card).toHaveTextContent(
        String(
          lookup('en', `publicationsNetwork.jurisdictions.${pub.jurisdiction}`),
        ),
      )
    }
    for (const entry of [...SIMILAR_PROJECTS, OUR_GROUP, ...RELATED_GROUPS]) {
      const card = screen.getByTestId(`network-${entry.id}`)
      expect(
        within(card).getByRole('link', { name: entry.name }),
      ).toHaveAttribute('href', entry.url)
    }
  })

  it('shows our group before the related groups', () => {
    render(<PublicationsPage />)
    const groups = screen.getByTestId('publications-groups')
    const ids = Array.from(groups.querySelectorAll('[data-testid]')).map((el) =>
      el.getAttribute('data-testid'),
    )
    expect(ids[0]).toBe(`network-${OUR_GROUP.id}`)
    expect(ids.slice(1)).toEqual(RELATED_GROUPS.map((g) => `network-${g.id}`))
  })

  it('links every section from the table of contents', () => {
    render(<PublicationsPage />)
    const toc = screen.getByTestId('publications-toc')
    for (const id of ['ours', 'related', 'projects', 'groups']) {
      expect(toc.querySelector(`a[href="#${id}"]`)).toBeInTheDocument()
      expect(screen.getByTestId(`publications-${id}`)).toHaveAttribute('id', id)
    }
  })
})

describe('publicationsNetwork content rules', () => {
  it('has unique ids and a note for every entry, and no orphan notes, in every locale', () => {
    expect(new Set(ALL_NETWORK_ENTRY_IDS).size).toBe(
      ALL_NETWORK_ENTRY_IDS.length,
    )
    for (const locale of LOCALES) {
      const entries = (getMessages(locale).publicationsNetwork as any).entries
      expect(Object.keys(entries).sort()).toEqual(
        [...ALL_NETWORK_ENTRY_IDS].sort(),
      )
      for (const id of ALL_NETWORK_ENTRY_IDS) {
        expect(String(entries[id]).length).toBeGreaterThan(20)
      }
    }
  })

  it('labels every jurisdiction in every locale', () => {
    for (const locale of LOCALES) {
      for (const pub of RELATED_PUBLICATIONS) {
        const key = `publicationsNetwork.jurisdictions.${pub.jurisdiction}`
        expect(lookup(locale, key)).toEqual(expect.any(String))
      }
    }
  })

  it('links only to canonical https pages', () => {
    const urls = [
      ...RELATED_PUBLICATIONS.map((p) => p.url),
      ...SIMILAR_PROJECTS.map((p) => p.url),
      OUR_GROUP.url,
      ...RELATED_GROUPS.map((g) => g.url),
      ...Object.values(OUR_PAPER_LINKS),
    ]
    for (const url of urls) expect(url).toMatch(/^https:\/\//)
    for (const pub of RELATED_PUBLICATIONS) {
      expect(pub.url).toMatch(
        /^https:\/\/(doi\.org\/10\.\d+\/|arxiv\.org\/abs\/\d{4}\.\d{4,5}$)/,
      )
    }
    for (const paper of Object.values(OUR_PAPER_LINKS)) {
      expect(paper).toMatch(/^https:\/\/arxiv\.org\/abs\/\d{4}\.\d{4,5}$/)
    }
  })

  it('maps paper links only to existing landing publications', () => {
    const publicationUrls = newsItems('de')
      .filter((i) => i.type === 'publication')
      .map((i) => i.url)
    for (const articleUrl of Object.keys(OUR_PAPER_LINKS)) {
      expect(publicationUrls).toContain(articleUrl)
    }
  })

  it('uses the same article urls for the landing entries in every locale', () => {
    const urls = (locale: string) => newsItems(locale).map((i) => i.url)
    expect(urls('en')).toEqual(urls('de'))
    expect(urls('fr')).toEqual(urls('de'))
  })
})

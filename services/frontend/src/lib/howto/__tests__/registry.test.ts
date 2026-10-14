import { registerTranslations } from '@/lib/i18n/catalog'

import {
  categoryText,
  getHowToGuides,
  guideSearchText,
  guideText,
  HOWTO_CATEGORIES,
  normalizeForSearch,
  registerHowToGuides,
  stripInlineMarkup,
  type HowToGuide,
} from '../registry'

const g = (
  id: string,
  category: HowToGuide['category'],
  extra: Partial<HowToGuide> = {},
): HowToGuide => ({
  id,
  category,
  ...extra,
})

describe('how-to registry', () => {
  beforeEach(() => {
    registerHowToGuides('a', [])
    registerHowToGuides('b', [])
  })

  it('re-registering a source replaces its guides instead of duplicating them', () => {
    registerHowToGuides('a', [g('one', 'projects')])
    registerHowToGuides('a', [g('one', 'projects'), g('two', 'data')])
    expect(getHowToGuides().filter((x) => x.id === 'one')).toHaveLength(1)
    expect(getHowToGuides().map((x) => x.id)).toEqual(
      expect.arrayContaining(['one', 'two']),
    )
  })

  it('orders guides by category order, regardless of registration order', () => {
    registerHowToGuides('a', [g('late', 'troubleshooting')])
    registerHowToGuides('b', [g('early', 'start'), g('mid', 'evaluation')])
    const ids = getHowToGuides().map((x) => x.id)
    expect(ids.indexOf('early')).toBeLessThan(ids.indexOf('mid'))
    expect(ids.indexOf('mid')).toBeLessThan(ids.indexOf('late'))
  })

  it('every category id is unique and has catalog copy in both languages', () => {
    const ids = HOWTO_CATEGORIES.map((c) => c.id)
    expect(new Set(ids).size).toBe(ids.length)
    HOWTO_CATEGORIES.forEach((c) => {
      for (const locale of ['de', 'en']) {
        const { title, blurb } = categoryText(c.id, locale)
        expect(title).not.toContain('howToCategories.')
        expect(blurb).not.toContain('howToCategories.')
      }
    })
  })
})

describe('search helpers', () => {
  it('stripInlineMarkup turns guide copy into plain text', () => {
    expect(
      stripInlineMarkup(
        'Unter **Profil** → `Modelle` (*optional*), siehe [Profil](/profile).',
      ),
    ).toBe('Unter Profil → Modelle (optional), siehe Profil.')
  })

  it('normalizes umlauts and sharp s so "schlussel" finds "Schlüssel"', () => {
    expect(normalizeForSearch('API-Schlüssel Straße')).toBe(
      'api-schlussel strasse',
    )
  })

  beforeAll(() => {
    registerTranslations('registry-test', {
      de: {
        howToGuides: {
          k: {
            title: 'Titel k',
            summary: 'Zusammenfassung k',
            steps: ['Schritt eins'],
            tips: ['Tipp'],
            pitfalls: ['Falle'],
            keywords: ['Schlüssel'],
            links: ['Profil'],
          },
        },
      },
      en: {
        howToGuides: {
          k: {
            title: 'Title k',
            summary: 'Summary k',
            steps: ['Step one'],
            tips: ['Tip'],
            pitfalls: ['Trap'],
            keywords: ['key'],
            links: ['Profile'],
          },
        },
      },
      fr: { howToGuides: { k: { keywords: ['clé'] } } },
    })
  })

  it('guideText reads the copy from the catalog and pairs link labels with hrefs', () => {
    const guide = g('k', 'generation', { links: ['/profile'] })
    expect(guideText(guide, 'en')).toEqual({
      title: 'Title k',
      summary: 'Summary k',
      steps: ['Step one'],
      tips: ['Tip'],
      pitfalls: ['Trap'],
      keywords: ['key'],
      links: [{ label: 'Profile', href: '/profile' }],
    })
    expect(guideText(guide, 'de').links).toEqual([
      { label: 'Profil', href: '/profile' },
    ])
    // fr falls back to English copy where the French catalog has none.
    expect(guideText(guide, 'fr').title).toBe('Title k')
    expect(guideText(guide, 'fr').keywords).toEqual(['clé'])
  })

  it('guideText degrades to the key and empty lists for a guide without copy', () => {
    const text = guideText(g('nope', 'data'), 'de')
    expect(text.title).toBe('howToGuides.nope.title')
    expect(text.steps).toEqual([])
  })

  it('guideSearchText includes steps, tips, pitfalls, the keywords of every language and searchTerms', () => {
    const guide = g('k', 'generation', { searchTerms: ['not_linked'] })
    const de = guideSearchText(guide, 'de')
    expect(de).toContain('schritt eins')
    expect(de).toContain('tipp')
    expect(de).toContain('falle')
    expect(de).toContain('schlussel')
    expect(de).toContain('key')
    expect(de).toContain('cle')
    expect(de).toContain('not_linked')
    expect(de).not.toContain('step one')
  })
})

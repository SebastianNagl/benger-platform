import {
  getHowToGuides,
  guideSearchText,
  HOWTO_CATEGORIES,
  normalizeForSearch,
  registerHowToGuides,
  stripInlineMarkup,
  type HowToGuide,
} from '../registry'

const g = (id: string, category: HowToGuide['category'], extra: Partial<HowToGuide> = {}): HowToGuide => ({
  id,
  category,
  title: { de: `Titel ${id}`, en: `Title ${id}` },
  summary: { de: `Zusammenfassung ${id}`, en: `Summary ${id}` },
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
    expect(getHowToGuides().map((x) => x.id)).toEqual(expect.arrayContaining(['one', 'two']))
  })

  it('orders guides by category order, regardless of registration order', () => {
    registerHowToGuides('a', [g('late', 'troubleshooting')])
    registerHowToGuides('b', [g('early', 'start'), g('mid', 'evaluation')])
    const ids = getHowToGuides().map((x) => x.id)
    expect(ids.indexOf('early')).toBeLessThan(ids.indexOf('mid'))
    expect(ids.indexOf('mid')).toBeLessThan(ids.indexOf('late'))
  })

  it('every category id is unique and has both languages', () => {
    const ids = HOWTO_CATEGORIES.map((c) => c.id)
    expect(new Set(ids).size).toBe(ids.length)
    HOWTO_CATEGORIES.forEach((c) => {
      expect(c.title.de).toBeTruthy()
      expect(c.title.en).toBeTruthy()
    })
  })
})

describe('search helpers', () => {
  it('stripInlineMarkup turns guide copy into plain text', () => {
    expect(stripInlineMarkup('Unter **Profil** → `Modelle` (*optional*), siehe [Profil](/profile).')).toBe(
      'Unter Profil → Modelle (optional), siehe Profil.',
    )
  })

  it('normalizes umlauts and sharp s so "schlussel" finds "Schlüssel"', () => {
    expect(normalizeForSearch('API-Schlüssel Straße')).toBe('api-schlussel strasse')
  })

  it('guideSearchText includes steps, tips, pitfalls and both languages of keywords', () => {
    const guide = g('k', 'generation', {
      steps: { de: ['Schritt eins'], en: ['Step one'] },
      tips: { de: ['Tipp'], en: ['Tip'] },
      pitfalls: { de: ['Falle'], en: ['Trap'] },
      keywords: { de: ['Schlüssel'], en: ['key'] },
    })
    const de = guideSearchText(guide, 'de')
    expect(de).toContain('schritt eins')
    expect(de).toContain('tipp')
    expect(de).toContain('falle')
    expect(de).toContain('schlussel')
    expect(de).toContain('key')
    expect(de).not.toContain('step one')
  })
})

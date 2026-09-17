/**
 * The learning platform (LTI) guides: lti-setup, lti-manage, lti-teacher,
 * lti-grades, lti-privacy and ts-lti-errors.
 *
 * These guides describe a feature whose UI ships with the extended edition,
 * so the tests pin what can drift silently: both languages stay parallel,
 * the copy stays brand-neutral and plain (no em dashes, formal German), every
 * launch error code is explained, the guides link to each other, and the UI
 * labels they quote match the labels the app renders.
 */

import deCommon from '@/locales/de/common.json'
import enCommon from '@/locales/en/common.json'

import { PLATFORM_CHANGELOG } from '@/data/changelog'
import {
  guideSearchText,
  normalizeForSearch,
  type HowToGuide,
} from '@/lib/howto/registry'
import { LTI_LAUNCH_ERROR_CODES } from '@/lib/lti/launchErrors'

import { PLATFORM_HOWTO_GUIDES } from '../guides'
import { GENERATION_GUIDES } from '../guides/generation'
import { INTEGRATION_GUIDES } from '../guides/integrations'
import { ORGANIZATION_GUIDES } from '../guides/organizations'

const LOCALES = ['de', 'en'] as const
type Locale = (typeof LOCALES)[number]

const LTI_GUIDE_IDS = [
  'lti-setup',
  'lti-manage',
  'lti-teacher',
  'lti-grades',
  'lti-privacy',
  'ts-lti-errors',
] as const

const EM_DASH = /\u2014/
const EN_DASH_AS_DASH = / \u2013 /
const COMMONS: Record<Locale, unknown> = { de: deCommon, en: enCommon }

function guide(id: string): HowToGuide {
  const found = PLATFORM_HOWTO_GUIDES.find((g) => g.id === id)
  if (!found) throw new Error(`guide ${id} missing`)
  return found
}

function texts(g: HowToGuide, locale: Locale): string[] {
  return [
    g.title[locale],
    g.summary[locale],
    ...(g.steps?.[locale] ?? []),
    ...(g.tips?.[locale] ?? []),
    ...(g.pitfalls?.[locale] ?? []),
    ...(g.links ?? []).map((l) => l.label[locale]),
    ...(g.keywords?.[locale] ?? []),
  ]
}

function body(id: string, locale: Locale): string {
  return texts(guide(id), locale).join('\n')
}

function label(locale: Locale, key: string): string {
  let node: unknown = COMMONS[locale]
  for (const part of key.split('.')) {
    node = (node as Record<string, unknown> | undefined)?.[part]
  }
  if (typeof node !== 'string') throw new Error(`${locale}: ${key} missing`)
  return node
}

describe('LTI guides: structure', () => {
  it('registers all six guides with the platform', () => {
    const ids = PLATFORM_HOWTO_GUIDES.map((g) => g.id)
    for (const id of LTI_GUIDE_IDS) expect(ids).toContain(id)
    expect(new Set(ids).size).toBe(ids.length)
  })

  it('keeps the setup, manage, teacher, grades and privacy guides together', () => {
    expect(INTEGRATION_GUIDES.map((g) => g.id)).toEqual([
      'lti-setup',
      'lti-manage',
      'lti-teacher',
      'lti-grades',
      'lti-privacy',
    ])
    for (const g of INTEGRATION_GUIDES) {
      expect(g.category).toBe('integrations')
    }
    expect(guide('ts-lti-errors').category).toBe('troubleshooting')
  })

  it.each(LTI_GUIDE_IDS)('%s has parallel German and English lists', (id) => {
    const g = guide(id)
    for (const field of ['steps', 'tips', 'pitfalls'] as const) {
      const list = g[field]
      if (!list) continue
      expect(list.de.length).toBe(list.en.length)
      expect(list.de.length).toBeGreaterThan(0)
    }
    expect(g.steps).toBeDefined()
    expect(g.keywords?.de.length).toBeGreaterThan(0)
    expect(g.keywords?.en.length).toBeGreaterThan(0)
    for (const locale of LOCALES) {
      expect(g.title[locale].trim().length).toBeGreaterThan(10)
      expect(g.summary[locale].trim().length).toBeGreaterThan(40)
    }
  })

  it.each(LTI_GUIDE_IDS)('%s links only to guides that exist', (id) => {
    const known = new Set(PLATFORM_HOWTO_GUIDES.map((g) => g.id))
    const hrefs = [
      ...(guide(id).links ?? []).map((l) => l.href),
      ...LOCALES.flatMap((locale) =>
        [...body(id, locale).matchAll(/\]\((\/how-to#[^)]+)\)/g)].map(
          (m) => m[1],
        ),
      ),
    ]
    for (const href of hrefs.filter((h) => h.startsWith('/how-to#'))) {
      expect(known.has(href.slice('/how-to#'.length))).toBe(true)
    }
  })

  it('links the guides to each other', () => {
    const links = (id: string) => (guide(id).links ?? []).map((l) => l.href)
    expect(links('lti-setup')).toEqual(
      expect.arrayContaining([
        '/how-to#lti-manage',
        '/how-to#lti-teacher',
        '/how-to#lti-privacy',
        '/how-to#ts-lti-errors',
      ]),
    )
    expect(links('lti-manage')).toEqual(
      expect.arrayContaining(['/how-to#lti-setup', '/how-to#lti-grades']),
    )
    expect(links('lti-teacher')).toContain('/how-to#lti-grades')
    expect(links('lti-grades')).toEqual(
      expect.arrayContaining(['/how-to#lti-teacher', '/how-to#lti-manage']),
    )
    expect(links('lti-privacy')).toEqual(
      expect.arrayContaining(['/how-to#lti-setup', '/how-to#lti-manage']),
    )
  })
})

describe('LTI guides: wording', () => {
  it.each(LTI_GUIDE_IDS)('%s is brand-neutral and plain', (id) => {
    for (const locale of LOCALES) {
      for (const text of texts(guide(id), locale)) {
        expect(text).not.toMatch(/vertretbar/i)
        expect(text).not.toMatch(EM_DASH)
        expect(text).not.toMatch(EN_DASH_AS_DASH)
        expect(text).not.toMatch(/superadmin/i)
      }
    }
  })

  it.each(LTI_GUIDE_IDS)('%s addresses readers formally in German', (id) => {
    for (const text of texts(guide(id), 'de')) {
      expect(text).not.toMatch(/\b(du|dich|dir|dein|deine|deinen|deiner)\b/i)
    }
  })
})

describe('ts-lti-errors covers every launch error code', () => {
  it.each(LOCALES)('names each code in the %s text', (locale) => {
    const text = body('ts-lti-errors', locale)
    for (const code of LTI_LAUNCH_ERROR_CODES) {
      expect(text).toContain(`\`${code}\``)
    }
  })

  it.each(LOCALES)('is found by each code (%s search text)', (locale) => {
    const text = guideSearchText(guide('ts-lti-errors'), locale)
    for (const code of LTI_LAUNCH_ERROR_CODES) {
      expect(text).toContain(normalizeForSearch(code))
    }
  })
})

describe('LTI guides: statements users rely on', () => {
  it('sends org admins to the panel and the API keys first', () => {
    for (const locale of LOCALES) {
      const text = body('lti-setup', locale)
      expect(text).toContain(label(locale, 'admin.organizations.more'))
      expect(text).toContain(
        label(locale, 'admin.organizations.lmsIntegration'),
      )
      expect(text).toContain(
        label(locale, 'organization.apiKeys.orgProvidesToggle'),
      )
      expect(text).toContain(
        label(locale, 'extended.lti.orgPanel.connectTitle'),
      )
      expect(text).toContain(
        label(locale, 'extended.lti.orgPanel.inviteCreate'),
      )
      expect(text).toContain(label(locale, 'extended.lti.admin.toolHost'))
      expect(text).toContain(label(locale, 'extended.lti.admin.toolHostMain'))
      expect(text).toContain(
        label(locale, 'extended.lti.admin.toolHostStudent'),
      )
      expect(text).toContain(label(locale, 'extended.lti.orgPanel.new'))
      expect(text).toContain(label(locale, 'extended.lti.admin.toolConfig'))
      expect(text).toContain(
        label(locale, 'extended.lti.orgPanel.invitePending'),
      )
    }
    expect(body('lti-setup', 'de')).toMatch(/sofort aktiv/)
    expect(body('lti-setup', 'en')).toMatch(/active at once/)
    // No fallback key, and no superadmin step any more.
    expect(body('lti-setup', 'de')).toMatch(/keinen Rückfall/)
    expect(body('lti-setup', 'en')).toMatch(/no fallback/)
    expect(body('lti-setup', 'de')).not.toMatch(/Plattform-Administration/)
  })

  it('names the panel sections and actions of a connection', () => {
    const keys = [
      'extended.lti.orgPanel.disable',
      'extended.lti.orgPanel.enable',
      'extended.lti.admin.deploymentsTitle',
      'extended.lti.admin.deploymentDisable',
      'extended.lti.admin.instructorRole',
      'extended.lti.admin.studentRole',
      'extended.lti.admin.linkByEmail',
      'extended.lti.admin.activities.title',
      'extended.lti.admin.activities.openOverview',
      'extended.lti.admin.accounts.title',
      'extended.lti.admin.accounts.unlink',
      'extended.lti.admin.anonymize.open',
      'extended.lti.admin.transfers.title',
      'extended.lti.admin.retry',
      'extended.lti.admin.events.title',
      'extended.lti.orgPanel.keys.title',
      'extended.lti.admin.delete.open',
    ]
    for (const locale of LOCALES) {
      const text = body('lti-manage', locale)
      for (const key of keys) expect(text).toContain(label(locale, key))
    }
    // The group admin cap and the org_admin downgrade on group connections.
    expect(body('lti-manage', 'de')).toMatch(/höchstens Mitwirkender/)
    expect(body('lti-manage', 'en')).toMatch(/at most contributor/)
    expect(body('lti-manage', 'de')).toMatch(/Mitwirkender plus Gruppen-Admin/)
    // Deleting needs the connection switched off first.
    expect(body('lti-manage', 'de')).toMatch(
      /Deaktivieren Sie die Anbindung zuerst/,
    )
    expect(body('lti-manage', 'en')).toMatch(/disable the connection first/)
  })

  it('tells teachers what they can link and where they land', () => {
    const keys = [
      'extended.lti.picker.title',
      'extended.lti.picker.ownBadge',
      'extended.lti.picker.createExam',
      'extended.lti.picker.link',
      'extended.lti.identity.separateAccount',
    ]
    for (const locale of LOCALES) {
      const text = body('lti-teacher', locale)
      for (const key of keys) expect(text).toContain(label(locale, key))
    }
    const de = body('lti-teacher', 'de')
    expect(de).toMatch(/Bewertungsbogen/)
    expect(de).toMatch(/mehreren Aufgaben/)
    expect(de).toMatch(/private Klausuren/)
    expect(de).toMatch(/Forschungsnutzung/)
    expect(de).toMatch(/Aktivitätsübersicht/)
    const en = body('lti-teacher', 'en')
    expect(en).toMatch(/several tasks/)
    expect(en).toMatch(/Private exams/)
  })

  it('explains the activity overview and both grade columns', () => {
    const keys = [
      'extended.lti.activity.tableTitle',
      'extended.lti.activity.colAi',
      'extended.lti.activity.colHuman',
      'extended.lti.activity.openKorrektur',
      'extended.lti.activity.retry',
      'extended.lti.activity.columnsTitle',
      'extended.lti.activity.aiRecreate',
      'extended.lti.activity.aiBlockedKey',
      'extended.lti.activity.syncSynced',
      'extended.lti.activity.syncFailed',
      'extended.lti.activity.linkedOpen',
      'extended.lti.admin.activities.openOverview',
    ]
    for (const locale of LOCALES) {
      const text = body('lti-grades', locale)
      for (const key of keys) expect(text).toContain(label(locale, key))
      expect(text).toContain('KI-Bewertung')
    }
    const de = body('lti-grades', 'de')
    expect(de).toMatch(/Notensynchronisation und Spaltenverwaltung/)
    expect(de).toMatch(/ILIAS erhält je Person einen Wert/)
    expect(de).toMatch(/Eine Korrektur löscht nichts/)
    expect(de).toMatch(/Notenschlüssel/)
    const en = body('lti-grades', 'en')
    expect(en).toMatch(/Moodle gets two columns/)
    expect(en).toMatch(/Grading deletes nothing/)
  })

  it('states consent, research use and names plainly', () => {
    const de = body('lti-privacy', 'de')
    expect(de).toMatch(/Forschungsnutzung ist Pflicht/)
    expect(de).toMatch(/Art\. 7 Abs\. 4 DSGVO/)
    expect(de).toMatch(/Pseudonym/)
    expect(de).toMatch(/Vertrag vor dem Einladungslink/)
    expect(de).toMatch(/Deutschland/)
    const en = body('lti-privacy', 'en')
    expect(en).toMatch(/Research use is required/)
    expect(en).toMatch(/Art\. 7\(4\) GDPR/)
    expect(en).toMatch(/Contract before the invitation link/)
    // The old claims are gone.
    expect(de).not.toMatch(/weder Name noch E-Mail/)
    expect(de).not.toMatch(/Wir legen jede Registrierung deaktiviert an/)
    expect(en).not.toMatch(/neither name nor email/)
  })
})

describe('related guides and pages', () => {
  it('api-keys says linked exams bill the connection organization', () => {
    const apiKeys = GENERATION_GUIDES.find((g) => g.id === 'api-keys')
    expect(apiKeys).toBeDefined()
    const de = apiKeys!.tips!.de.join('\n')
    const en = apiKeys!.tips!.en.join('\n')
    expect(de).toMatch(/Organisation dieser Anbindung/)
    expect(de).toMatch(/keinen Rückfall/)
    expect(en).toMatch(/organization of that connection/)
    expect(en).toMatch(/no fallback/)
    for (const text of [...apiKeys!.tips!.de, ...apiKeys!.tips!.en]) {
      expect(text).not.toMatch(/vertretbar/i)
      expect(text).not.toMatch(EM_DASH)
    }
  })

  it('org-roles names the learning platform connections', () => {
    const roles = ORGANIZATION_GUIDES.find((g) => g.id === 'org-roles')
    expect(roles?.steps?.de.join('\n')).toContain('(/how-to#lti-manage)')
    expect(roles?.steps?.en.join('\n')).toContain('(/how-to#lti-manage)')
    expect(roles?.steps?.de.join('\n')).toMatch(/Pseudonym/)
  })

  it.each(LOCALES)(
    'the %s privacy policy describes the learning platform processing',
    (locale) => {
      const heading = label(locale, 'legal.dataProtection.lmsData')
      const text = label(locale, 'legal.dataProtection.lmsDataText')
      expect(heading).toMatch(/Moodle, ILIAS/)
      for (const part of [heading, text]) {
        expect(part).not.toMatch(EM_DASH)
        expect(part).not.toMatch(/vertretbar/i)
      }
      const expected =
        locale === 'de'
          ? [
              /Forschungszwecke/,
              /Pseudonym/,
              /30 Minuten/,
              /24 Stunden/,
              /Administration dieser Plattform/,
              /anonymisieren/,
            ]
          : [
              /research/,
              /pseudonym/,
              /30 minutes/,
              /24 hours/,
              /administration of this platform/,
              /anonymize/,
            ]
      for (const pattern of expected) expect(text).toMatch(pattern)
    },
  )

  it('the 2026-09-17 changelog entries are neutral and plain', () => {
    const entries = PLATFORM_CHANGELOG.filter((e) => e.date === '2026-09-17')
    expect(entries.length).toBeGreaterThanOrEqual(3)
    for (const entry of entries) {
      for (const text of [entry.text.de, entry.text.en]) {
        expect(text).not.toMatch(/vertretbar/i)
        expect(text).not.toMatch(EM_DASH)
      }
    }
  })
})

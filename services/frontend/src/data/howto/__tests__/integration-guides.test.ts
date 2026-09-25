/**
 * The learning platform (LTI) guides: lti-setup, lti-manage, lti-teacher,
 * lti-grades, lti-privacy, ts-lti-errors and ts-lti-grades.
 *
 * These guides describe a feature whose UI ships with the extended edition,
 * so the tests pin what can drift silently: both languages stay parallel,
 * the copy stays brand-neutral and plain (no em dashes, formal German), every
 * launch error code is explained, the guides link to each other, and the UI
 * labels they quote match the labels the app renders.
 */

import { readFileSync } from 'fs'
import { resolve } from 'path'

import deCommon from '@/locales/de/common.json'
import enCommon from '@/locales/en/common.json'

import { PLATFORM_CHANGELOG } from '@/data/changelog'
import {
  guideSearchText,
  normalizeForSearch,
  type HowToGuide,
} from '@/lib/howto/registry'
import { LTI_LAUNCH_ERROR_CODES } from '@/lib/lti/launchErrors'
import { buildGuideIndex, rankSearchResults } from '@/lib/search'

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
  'ts-lti-grades',
] as const

// Moodle 4.5.12 labels, checked against the German language pack
// (ltiservice_gradebookservices, grades) and the English strings.
const MOODLE = {
  agsField: {
    de: 'IMS LTI Aufgaben und Bewertung',
    en: 'IMS LTI Assignment and Grade Services',
  },
  agsColumns: {
    de: 'Service für die Synchronisation von Bewertungen und die Verwaltung der Spalten nutzen',
    en: 'Use this service for grade sync and column management',
  },
  gradebookSetup: { de: 'Setup für Bewertungen', en: 'Gradebook setup' },
  weights: { de: 'Gewichtungen', en: 'Weights' },
  saveChanges: { de: 'Änderungen speichern', en: 'Save changes' },
  courseTotal: { de: 'Kurs gesamt', en: 'Course total' },
} as const

// ILIAS 10.9 labels of the global provider form and the learning progress
// settings, checked against lang/ilias_de.lang and lang/ilias_en.lang of the
// release_10 branch (modules lti, trac, common, administration).
const ILIAS = {
  identification: {
    de: 'Identifikation der Person',
    en: 'User identification',
  },
  userId: { de: 'ID des ILIAS-Kontos', en: 'ILIAS user id' },
  // Works technically, but the user id mode is the one supported setting
  // (owner decision 2026-09-17), so the guides no longer offer it.
  hash: 'Hash@ILIAS-Plattform-ID.ilias',
  emailMode: { de: 'E-Mail-Adresse', en: 'E-Mail Address' },
  fullName: { de: 'Vollständiger Name', en: 'Entire name' },
  grading: {
    de: 'Erweiterte Benotungsdienste',
    en: 'Advanced Grading Services',
  },
  outcome: {
    de: 'Provider unterstützt Outcome Service',
    en: 'Provider supports Outcome Service',
  },
  masteryDefault: {
    de: 'Voreinstellung Mastery Score',
    en: 'Default Mastery Score',
  },
} as const

// Earlier advice that breaks the ILIAS grade transfer (identification by
// the email address) or quotes labels ILIAS 10.9 does not show.
const OLD_ILIAS_ADVICE = [
  /Privacy-Modus/,
  /privacy mode/i,
  /Identifizierung per E-Mail-Adresse/,
  /identification by email address/i,
  /identify users by email address/i,
  /sends name and email/i,
  /Name und E-Mail-Adresse übertragen werden/,
]

// Labels Moodle does not use. They were quoted in earlier versions.
const OLD_AGS_LABELS = [
  /Notensynchronisation und Spaltenverwaltung/,
  /grade synchronization and column management/,
]

const PUBLIC_DOC = resolve(
  __dirname,
  '../../../../../../docs/lms-integration.md',
)

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

function stepWith(id: string, locale: Locale, needle: string): string {
  const found = (guide(id).steps?.[locale] ?? []).find((s) =>
    s.includes(needle),
  )
  if (!found) throw new Error(`${id} ${locale}: no step contains ${needle}`)
  return found
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
    expect(guide('ts-lti-grades').category).toBe('troubleshooting')
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
    expect(links('lti-grades')).toContain('/how-to#ts-lti-grades')
    expect(links('ts-lti-errors')).toContain('/how-to#ts-lti-grades')
    expect(links('ts-lti-grades')).toEqual(
      expect.arrayContaining(['/how-to#lti-grades', '/how-to#lti-manage']),
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

  it.each(LTI_GUIDE_IDS)('%s quotes Moodle labels that exist', (id) => {
    for (const locale of LOCALES) {
      for (const pattern of OLD_AGS_LABELS) {
        expect(body(id, locale)).not.toMatch(pattern)
      }
    }
  })

  it.each(LOCALES)(
    'the %s app texts about the AI column quote the real Moodle labels',
    (locale) => {
      for (const key of [
        'extended.lti.admin.activities.aiScopeMissing',
        'extended.lti.activity.aiUnavailableScope',
      ]) {
        const text = label(locale, key)
        const [open, close] = locale === 'de' ? ['„', '“'] : ['“', '”']
        for (const pattern of OLD_AGS_LABELS) expect(text).not.toMatch(pattern)
        expect(text).toContain(`${open}${MOODLE.agsField[locale]}${close}`)
        expect(text).toContain(`${open}${MOODLE.agsColumns[locale]}${close}`)
      }
    },
  )

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
      expect(text).toContain(label(locale, 'extended.lti.orgPanel.connect'))
      expect(text).toContain(
        label(locale, 'extended.lti.orgPanel.inviteCreate'),
      )
      expect(text).toContain(label(locale, 'extended.lti.admin.toolHost'))
      expect(text).toContain(label(locale, 'extended.lti.admin.toolHostMain'))
      expect(text).toContain(
        label(locale, 'extended.lti.admin.toolHostStudent'),
      )
      expect(text).toContain(label(locale, 'extended.lti.connect.other'))
      expect(text).toContain(label(locale, 'extended.lti.connect.connect'))
      expect(text).toContain(label(locale, 'extended.lti.admin.toolConfig'))
      expect(text).toContain(
        label(locale, 'extended.lti.orgPanel.invitePendingTitle'),
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
      'extended.lti.orgPanel.switchOn',
      'extended.lti.orgPanel.switchOff',
      'extended.lti.orgPanel.switchedOffBadge',
      'extended.lti.admin.deploymentsTitle',
      'extended.lti.admin.deploymentSwitchOn',
      'extended.lti.admin.deploymentSwitchOff',
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
    // The switches show their state. The action names are only screen
    // reader labels, so no guide quotes them as visible buttons.
    for (const id of LTI_GUIDE_IDS) {
      for (const locale of LOCALES) {
        for (const key of [
          'extended.lti.orgPanel.disable',
          'extended.lti.orgPanel.enable',
          'extended.lti.admin.deploymentDisable',
          'extended.lti.admin.deploymentEnable',
        ]) {
          expect(body(id, locale)).not.toContain(`**${label(locale, key)}**`)
        }
      }
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
      'extended.lti.picker.ownBadge',
      'extended.lti.picker.createExam',
      'extended.lti.picker.createExamSecondary',
      'extended.lti.picker.link',
      'extended.lti.identity.separateAccount',
    ]
    for (const locale of LOCALES) {
      const text = body('lti-teacher', locale)
      for (const key of keys) expect(text).toContain(label(locale, key))
      // The picker is headed with the activity title. The fallback label is
      // only a search keyword, never the named heading of a step.
      const pickerStep = stepWith(
        'lti-teacher',
        locale,
        label(locale, 'extended.lti.picker.ownBadge'),
      )
      expect(pickerStep).not.toContain(
        `**${label(locale, 'extended.lti.picker.title')}**`,
      )
      // "Or create a new exam" when exams are listed, "Create new exam" when
      // the list is empty.
      expect(pickerStep).toContain(
        `**${label(locale, 'extended.lti.picker.createExamSecondary')}**`,
      )
    }
    const de = body('lti-teacher', 'de')
    expect(de).toMatch(/Bewertungsbogen/)
    expect(de).toMatch(/mehreren Aufgaben/)
    expect(de).toMatch(/private Klausuren/)
    expect(de).toMatch(/Forschungsnutzung/)
    expect(de).toMatch(/Aktivitätsübersicht/)
    expect(de).toMatch(/Die Auswahl trägt den Titel Ihrer Aktivität/)
    const en = body('lti-teacher', 'en')
    expect(en).toMatch(/several tasks/)
    expect(en).toMatch(/Private exams/)
    expect(en).toMatch(/The picker carries your activity’s title/)
  })

  it('says the grading view opens in the expert interface on both addresses', () => {
    for (const locale of LOCALES) {
      const korrektur = label(locale, 'extended.lti.activity.openKorrektur')
      const student = label(locale, 'extended.lti.admin.toolHostStudent')
      for (const id of ['lti-teacher', 'lti-grades']) {
        const step = stepWith(id, locale, `**${korrektur}**`)
        expect(step).toContain(student)
        expect(step).toMatch(
          locale === 'de' ? /Expertenoberfläche/ : /expert interface/,
        )
      }
    }
    expect(body('lti-setup', 'de')).toMatch(
      /Nur die Korrektur öffnet sich in der Expertenoberfläche/,
    )
    expect(body('lti-setup', 'en')).toMatch(
      /Only the grading view opens in the expert interface/,
    )
  })

  it('tells teachers to take the AI column out of the Moodle course total', () => {
    for (const locale of LOCALES) {
      for (const id of ['lti-teacher', 'lti-grades']) {
        const text = body(id, locale)
        expect(text).toContain(MOODLE.courseTotal[locale])
        expect(text).toContain(MOODLE.gradebookSetup[locale])
        expect(text).toContain(MOODLE.weights[locale])
        expect(text).toContain(MOODLE.saveChanges[locale])
        expect(text).toMatch(
          locale === 'de' ? /0 eintragen|tragen Sie 0 ein/ : /enter 0/,
        )
      }
    }
    // The setup guide points admins to it as well.
    expect(body('lti-setup', 'de')).toMatch(/Kursgesamtbewertung/)
    expect(body('lti-setup', 'en')).toMatch(/course total/)
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
    for (const locale of LOCALES) {
      const text = body('lti-grades', locale)
      expect(text).toContain(MOODLE.agsField[locale])
      expect(text).toContain(MOODLE.agsColumns[locale])
      // "Send again" is offered for failed transfers only.
      const retry = stepWith(
        'lti-grades',
        locale,
        `**${label(locale, 'extended.lti.activity.retry')}**`,
      )
      expect(retry).toMatch(
        locale === 'de'
          ? /Hat eine Übertragung einen Fehler/
          : /If a transfer has an error/,
      )
    }
    const de = body('lti-grades', 'de')
    expect(de).toMatch(/ILIAS erhält je Person einen Wert/)
    expect(de).toMatch(/Eine Korrektur löscht nichts/)
    expect(de).toMatch(/Notenschlüssel/)
    expect(de).not.toMatch(/Erneut senden\*\* schickt eine Note/)
    const en = body('lti-grades', 'en')
    expect(en).toMatch(/Moodle gets two columns/)
    expect(en).toMatch(/Grading deletes nothing/)
  })

  it('says consistently when waiting grades and changes arrive', () => {
    const de = body('lti-grades', 'de')
    const en = body('lti-grades', 'en')
    // Unfunded org: graded at the next hourly check once the key is there.
    expect(de).toMatch(
      /bei der nächsten stündlichen Prüfung korrigiert, also spätestens nach etwa einer Stunde/,
    )
    expect(en).toMatch(
      /graded at the next hourly check, so within about an hour/,
    )
    // Grade changes after the fact.
    expect(de).toMatch(/geht der neue Wert spätestens nach etwa einer Stunde/)
    expect(en).toMatch(/reaches the learning platform within about an hour/)
    expect(de).not.toMatch(/innerhalb einer Stunde/)
  })

  it('lti-grades names the block reasons students see and the quick retries', () => {
    const de = body('lti-grades', 'de')
    const en = body('lti-grades', 'en')
    expect(de).toMatch(
      /Studierende sehen den Grund: Ihre Organisation bezahlt die KI-Korrektur noch nicht, oder ihr fehlt ein API-Schlüssel für das Bewertungsmodell/,
    )
    expect(en).toMatch(
      /Students see the reason: their organization does not pay for AI grading yet, or it has no API key for the grading model/,
    )
    expect(de).not.toMatch(/sehen dann, dass ihre Organisation noch keinen/)
    expect(en).not.toMatch(/has not added an API key yet, and/)
    // The retry schedule matches the push worker (10/30/90 s, then backoff).
    expect(de).toMatch(/nach 10, 30 und 90 Sekunden erneut/)
    expect(en).toMatch(/again after 10, 30 and 90 seconds/)
    expect(de).not.toMatch(/zuerst nach einer Minute/)
    expect(en).not.toMatch(/first after one minute/)
    // A permanent refusal fails at once.
    expect(de).toMatch(
      /Lehnt die Lernplattform die Note dagegen endgültig ab \(etwa mit 400, 401, 403 oder 404\), ist die Übertragung sofort fehlgeschlagen/,
    )
    expect(en).toMatch(
      /refuses the grade for good \(for example with 400, 401, 403 or 404\), the transfer fails at once/,
    )
    for (const locale of LOCALES) {
      expect(body('lti-manage', locale)).toMatch(
        locale === 'de' ? /sofort fehlgeschlagen/ : /fails at once/,
      )
    }
  })

  it('names the AI column with the activity title', () => {
    expect(body('lti-grades', 'de')).toMatch(
      /Sie heißt \*KI-Bewertung: Titel der Aktivität\*/,
    )
    expect(body('lti-grades', 'en')).toMatch(
      /It is named \*KI-Bewertung: activity title\*/,
    )
  })

  it('names the Moodle grade service by its real labels in the setup guides', () => {
    for (const locale of LOCALES) {
      for (const id of ['lti-setup', 'lti-manage']) {
        const text = body(id, locale)
        expect(text).toContain(MOODLE.agsField[locale])
        expect(text).toContain(MOODLE.agsColumns[locale])
      }
    }
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

describe('LTI guides: the ILIAS identification rule', () => {
  it.each(LTI_GUIDE_IDS)(
    '%s never recommends identifying people by email in ILIAS',
    (id) => {
      for (const locale of LOCALES) {
        for (const pattern of OLD_ILIAS_ADVICE) {
          expect(body(id, locale)).not.toMatch(pattern)
        }
      }
      // The German texts use the German ILIAS label of the grade service.
      expect(body(id, 'de')).not.toContain(ILIAS.grading.en)
    },
  )

  it.each(['lti-setup', 'lti-privacy'])(
    '%s recommends the ILIAS user id mode and the full name',
    (id) => {
      for (const locale of LOCALES) {
        const text = body(id, locale)
        expect(text).toContain(ILIAS.identification[locale])
        expect(text).toContain(`**${ILIAS.userId[locale]} …**`)
        expect(text).not.toContain(ILIAS.hash)
        expect(text).toContain(`**${ILIAS.fullName[locale]}**`)
        expect(text).toContain(`*${ILIAS.emailMode[locale]}*`)
        // Every mention of the email mode warns against it.
        const emailSentences = text
          .split(/(?<=\.)\s/)
          .filter((sentence) =>
            sentence.includes(`*${ILIAS.emailMode[locale]}*`),
          )
        expect(emailSentences.length).toBeGreaterThan(0)
        for (const sentence of emailSentences) {
          expect(sentence).toMatch(
            locale === 'de' ? /nicht|ungeeignet|scheitert/ : /not|fails/,
          )
        }
      }
      // ILIAS sends the name but no email address, so the page asks once
      // for one after consent.
      const de = body(id, 'de')
      const en = body(id, 'en')
      expect(de).toMatch(/keine E-Mail-Adresse/)
      expect(de).toMatch(/keine automatische Aktivierungsmail/)
      expect(de).toMatch(/keine Verknüpfung mit bestehenden Konten/)
      expect(de).toMatch(/fragt die Seite [^.]*einmal nach [^.]*E-Mail-Adresse/)
      expect(de).not.toMatch(/keine Aktivierungsmail/)
      expect(en).toMatch(/no email address/)
      expect(en).toMatch(/no automatic activation mail/)
      expect(en).toMatch(/no linking to existing accounts/)
      expect(en).toMatch(/asks [^.]*once for [^.]*email address/)
      expect(en).not.toMatch(/(?<!automatic )activation mail and no/)
    },
  )

  it.each(['lti-setup', 'lti-privacy'])(
    '%s says the address step can be skipped and its link activates',
    (id) => {
      expect(body(id, 'de')).toMatch(/Der Schritt lässt sich überspringen/)
      expect(body(id, 'en')).toMatch(/The step can be skipped/)
    },
  )

  it('lti-privacy explains the address step in full', () => {
    const de = guide('lti-privacy').tips!.de.join('\n')
    const en = guide('lti-privacy').tips!.en.join('\n')
    expect(de).toMatch(/etwa alle Konten aus ILIAS/)
    expect(de).toMatch(/erst, wenn die Person den Bestätigungslink öffnet/)
    expect(de).toMatch(/schon zu einem anderen Konto gehört, wird abgelehnt/)
    expect(de).toMatch(/hinterlegt die Adresse später in der App/)
    expect(en).toMatch(/such as every account from ILIAS/)
    expect(en).toMatch(/only once the person opens the confirmation link/)
    expect(en).toMatch(/already belongs to another account is refused/)
    expect(en).toMatch(/adds an address in the app later/)
    expect(de).not.toMatch(/erhalten diese E-Mail nicht/)
    expect(en).not.toMatch(/do not get this email/)
  })

  it('asks for the provider settings ILIAS needs for grades', () => {
    for (const locale of LOCALES) {
      const text = body('lti-setup', locale)
      expect(text).toContain(ILIAS.grading[locale === 'de' ? 'de' : 'en'])
      expect(text).toContain(ILIAS.outcome[locale])
      expect(text).toContain(ILIAS.masteryDefault[locale])
      expect(text).toContain('**22**')
    }
    expect(body('lti-setup', 'de')).toContain(
      '*Verfügbarkeit* **in neuen und bestehenden Objekten**',
    )
    expect(body('lti-setup', 'en')).toContain(
      '*Availability* to **For Creating Objects**',
    )
  })

  it('says that ILIAS accounts carry the name only', () => {
    expect(guide('lti-privacy').summary.de).toMatch(/aus ILIAS nur den Namen/)
    expect(guide('lti-privacy').summary.en).toMatch(/from ILIAS only the name/)
    expect(body('lti-teacher', 'de')).toMatch(
      /ILIAS übermittelt keine E-Mail-Adresse/,
    )
    expect(body('lti-teacher', 'en')).toMatch(/ILIAS sends no email address/)
    // Teachers are asked for their address too, with "Sie".
    expect(body('lti-teacher', 'de')).toMatch(
      /Die Seite fragt Sie dann einmal nach Ihrer E-Mail-Adresse/,
    )
    expect(body('lti-teacher', 'en')).toMatch(
      /The page then asks you once for your email address/,
    )
  })

  it('ts-lti-grades explains the ILIAS refusal and the fix first', () => {
    const g = guide('ts-lti-grades')
    for (const locale of LOCALES) {
      const first = g.steps![locale][0]
      expect(first).toContain('User not available')
      expect(first).toContain('ILIAS kennt die Person nicht')
      expect(first).toContain(ILIAS.identification[locale])
      expect(first).toContain(`**${ILIAS.userId[locale]} …**`)
      expect(first).not.toContain(ILIAS.hash)
      expect(first).toContain(
        `**${label(locale, 'extended.lti.admin.events.iliasEmailModeTitle')}**`,
      )
      const text = body('ts-lti-grades', locale)
      expect(text).toContain(ILIAS.grading[locale])
      expect(text).toContain(ILIAS.outcome[locale])
      expect(text).toContain(label(locale, 'extended.lti.activity.retry'))
      expect(text).toContain(label(locale, 'extended.lti.admin.retry'))
      expect(text).toContain(label(locale, 'extended.lti.activity.syncFailed'))
      expect(text).toContain(label(locale, 'extended.lti.orgPanel.switchOff'))
      expect(text).toMatch(/400, 401, 403 (oder|or) 404/)
    }
  })

  it.each(LOCALES)(
    'ts-lti-grades is the first hit for "User not available" (%s)',
    (locale) => {
      const entries = buildGuideIndex({
        t: (_key: string, fallback?: string) => fallback ?? _key,
        locale,
        flags: {},
        user: {},
        organizations: [],
        guides: PLATFORM_HOWTO_GUIDES,
      } as Parameters<typeof buildGuideIndex>[0])
      const urls = rankSearchResults(entries, 'User not available').map(
        (r) => r.url,
      )
      expect(urls[0]).toBe('/how-to#ts-lti-grades')
    },
  )
})

describe('public LMS integration doc', () => {
  const doc = readFileSync(PUBLIC_DOC, 'utf8')
  // Line breaks and blockquote markers joined, so wrapped text matches.
  const flat = (text: string) => text.replace(/\n>?[ \t]*/g, ' ')
  const flatDoc = flat(doc)

  function section(heading: string): string {
    const start = doc.indexOf(heading)
    if (start < 0) throw new Error(`section ${heading} missing`)
    const next = doc.indexOf('\n#', start + heading.length)
    return flat(doc.slice(start, next < 0 ? undefined : next))
  }

  it('uses the real Moodle 4.5 labels for the grade service', () => {
    for (const pattern of OLD_AGS_LABELS) expect(flatDoc).not.toMatch(pattern)
    for (const locale of LOCALES) {
      expect(flatDoc).toContain(MOODLE.agsColumns[locale])
      expect(flatDoc).toContain(MOODLE.agsField[locale])
    }
    const requirements = section('## 9. Requirements on your LMS')
    expect(requirements).toContain(MOODLE.agsColumns.en)
    expect(requirements).toContain(MOODLE.agsColumns.de)
    expect(requirements).toContain('Service nur für Bewertungen nutzen')
    const appendixB = section('## Appendix B')
    expect(appendixB).toContain(`„${MOODLE.agsField.de}“`)
    expect(appendixB).toContain(MOODLE.agsColumns.de)
    expect(appendixB).toContain('„Service nur für Bewertungen nutzen“')
    expect(appendixB).toContain('Anwendername an Tool übergeben')
    expect(appendixB).toContain('E-Mail des Anwenders an Tool übergeben')
  })

  it('explains the AI column in the course total (§7, §8.7, Appendix B)', () => {
    const courseSetup = section('## 7. Course setup (teacher)')
    expect(courseSetup).toContain(
      '**Moodle: keep the AI grade out of the course total.**',
    )
    expect(courseSetup).toMatch(/as a normal manual grade item/)
    expect(courseSetup).toContain(
      `**${MOODLE.gradebookSetup.en}** (German Moodle: *Bewertungen → ${MOODLE.gradebookSetup.de}*)`,
    )
    expect(courseSetup).toContain(
      `**${MOODLE.weights.en}** column (*${MOODLE.weights.de}*), enter 0`,
    )
    expect(courseSetup).toContain(
      `**${MOODLE.saveChanges.en}** (*${MOODLE.saveChanges.de}*)`,
    )
    const automated = section('### 8.7 Automated assessment')
    expect(automated).toMatch(
      /It counts in the course total until the teacher sets its weight to 0/,
    )
    const checklist = section('### Validation checklist')
    expect(checklist).toMatch(
      /After the teacher set the weight of "KI-Bewertung" to 0, the Moodle course total counts the activity column only/,
    )
    const troubleshooting = section('### Troubleshooting')
    expect(troubleshooting).toMatch(
      /The Moodle course total also counts the AI grade/,
    )
    const appendixB = section('## Appendix B')
    expect(appendixB).toMatch(/\*\*Kursgesamtbewertung:\*\*/)
    expect(appendixB).toContain(`„${MOODLE.courseTotal.de}“`)
    expect(appendixB).toContain(`„${MOODLE.gradebookSetup.de}“`)
    expect(appendixB).toContain(
      `„${MOODLE.weights.de}“ anhaken, **0** eintragen`,
    )
    expect(appendixB).toContain(`„${MOODLE.saveChanges.de}“`)
  })

  it('names the picker, the retry and the grading view correctly', () => {
    const courseSetup = section('## 7. Course setup (teacher)')
    expect(courseSetup).not.toMatch(/picker \(\*\*Link activity\*\*\)/)
    expect(courseSetup).toMatch(
      /The picker carries the activity's title as its heading/,
    )
    expect(courseSetup).toContain(
      '**Or create a new exam** below the list, or **Create new exam** when the list is empty',
    )
    expect(courseSetup).toMatch(
      /A transfer with an error \(failed, or waiting after a failed attempt\) can be sent again with \*\*Send again\*\*/,
    )
    expect(courseSetup).toMatch(
      /\*\*Open grading\*\* always opens the Korrektur in the expert interface, also on the student host/,
    )
    expect(flatDoc).toMatch(/Only the Korrektur opens in the expert interface/)
    expect(flatDoc).toMatch(
      /\*\*Send again\*\* in the activity overview \(for transfers with an error\)/,
    )
    expect(flatDoc).not.toMatch(/sends a grade again/)
  })

  it('describes the transfer retries and the one-push-per-student rule', () => {
    const outbox = flatDoc.slice(
      flatDoc.indexOf('**Grade transfer is an outbox.**'),
      flatDoc.indexOf('**Switching off.**'),
    )
    expect(outbox).toMatch(
      /Transfers for one student in one course run one at a time/,
    )
    expect(outbox).toMatch(/This does not count as an attempt/)
    expect(outbox).toMatch(/is sent again after 10, 30 and 90 seconds/)
    expect(outbox).toMatch(
      /The wait is 60 seconds after the first attempt and doubles with each attempt, up to 6 hours/,
    )
    expect(outbox).toMatch(/An HTML error page from the LMS is cut off/)
    expect(outbox).not.toMatch(/becomes due again after 60 seconds, then/)
    // Students see the actual block reason.
    expect(section('### 8.5 Where the data lives')).toMatch(
      /Students see the reason: their organization does not pay for AI grading yet, or it has no API key for the grading model/,
    )
  })

  it('says graded within about an hour once the key is there', () => {
    expect(section('### 8.5 Where the data lives')).toMatch(
      /Once the key is in place, it is graded at the next hourly check, so within about an hour/,
    )
    expect(section('### Troubleshooting')).toMatch(
      /Waiting submissions are graded at the next hourly check, so within about an hour/,
    )
    expect(section('### Validation checklist')).toMatch(
      /A Notenschlüssel recompute reaches the LMS within about an hour/,
    )
    expect(flatDoc).not.toMatch(/within the hour/)
  })

  it('names the shared student organization neutrally in the data section', () => {
    const accounts = section('### 8.1 Accounts and names')
    expect(accounts).toMatch(/for students and teachers alike/)
    expect(accounts).toMatch(/operator's shared student organization/)
    expect(accounts).toMatch(/This has a technical reason/)
    expect(accounts).toMatch(/Existing accounts linked by proof do not join/)
    const persisted = section('### 8.3 What is persisted')
    expect(persisted).toMatch(/`organization_memberships`/)
    expect(persisted).toMatch(/operator's shared student organization/)
  })

  it('stays brand-neutral and plain', () => {
    expect(doc).not.toMatch(/vertretbar/i)
    expect(doc).not.toMatch(/what-a-benger/i)
    expect(doc).not.toMatch(EM_DASH)
    // No internal issue numbers (anchors like #81-accounts are fine).
    expect(doc).not.toMatch(/(?:^|[\s(])#\d+\b(?!-)/m)
  })

  it('recommends a non-email ILIAS identification everywhere', () => {
    for (const pattern of OLD_ILIAS_ADVICE) expect(flatDoc).not.toMatch(pattern)
    const limits = section('### ILIAS limitations to plan around')
    for (const locale of LOCALES) {
      expect(limits).toContain(ILIAS.identification[locale])
      expect(limits).toContain(ILIAS.fullName[locale])
      expect(limits).toContain(ILIAS.outcome[locale])
      expect(limits).toContain(ILIAS.masteryDefault[locale])
    }
    expect(limits).toContain(`*${ILIAS.userId.de}`)
    expect(flatDoc).not.toContain(ILIAS.hash)
    expect(limits).toMatch(/Do not choose \*E-Mail-Adresse\*/)
    expect(limits).toMatch(/404 User not available/)
    expect(limits).toMatch(/This is an ILIAS issue/)
    expect(limits).toMatch(
      /Accounts from ILIAS therefore start with the full name but no email address/,
    )
    expect(limits).toMatch(
      /no automatic activation mail and no linking to an existing account/,
    )
    expect(limits).toMatch(
      /students and teachers are asked once for an email address\. The step can be skipped/,
    )
    expect(flatDoc).not.toMatch(/There is no activation mail/)
    const registering = section('### Connection settings')
    expect(registering).toMatch(/\*\*ILIAS privacy settings\.\*\*/)
    expect(registering).toMatch(
      /Do not change the identification after go-live/,
    )
    const dynamic = section('### 6a. One-link registration')
    expect(dynamic).toContain(ILIAS.grading.de)
    expect(dynamic).toContain(ILIAS.outcome.de)
    expect(dynamic).toContain(
      '*Eigene Tool-Einstellungen mit dynamischer Registrierung anlegen (LTI 1.3)*',
    )
    const accounts = section('### 8.1 Accounts and names')
    expect(accounts).toMatch(/An account from ILIAS gets the full name only/)
    expect(accounts).toMatch(/\*\*Asked once for an address\.\*\*/)
    expect(accounts).toMatch(/That link is the activation mail/)
    expect(accounts).toMatch(/The person can skip the step/)
    expect(accounts).toMatch(/already uses is refused with a clear message/)
    expect(accounts).toMatch(
      /comes once per connection, and again only\s+when the consent version changes/,
    )
    const requirements = section('## 9. Requirements on your LMS')
    expect(requirements).toMatch(/never by \*E-Mail-Adresse\*/)
    expect(requirements).toContain(ILIAS.grading.de)
    const brief = flat(doc.slice(0, doc.indexOf('## 1. Edition boundary')))
    expect(brief).toMatch(/From ILIAS they carry the name only/)
    const troubleshooting = section('### Troubleshooting')
    expect(troubleshooting).toMatch(
      /ILIAS refuses every grade with `404 User not available`/,
    )
    // No quoted English ILIAS labels without the German one.
    expect(flatDoc).not.toMatch(/"Advanced Grading Services"/)
  })

  it('gives the ILIAS setup sheet with the real ILIAS 10.9 labels', () => {
    const sheet = section('## Appendix A')
    for (const text of [
      'Administration → ILIAS erweitern → LTI',
      '„ILIAS als LTI-Konsument“',
      '„Globalen Provider für alle Benutzer hinzufügen“',
      '„Verfügbarkeit“: **„in neuen und bestehenden Objekten“**',
      '„LTI Version“: **„Version 1.3“**',
      '„Login URL“: `https://<tool-host>/api/lti/launch`',
      '„Initiate Login URL“: `https://<tool-host>/api/lti/login`',
      '„Redirection URI“: `https://<tool-host>/api/lti/launch`',
      '„Typ des öffentlichen Schlüssels“: **„URL (Json Web Token)“**',
      '„Unterstützung für Deep Linking“: **aus**',
      `„${ILIAS.grading.de}“: **aktivieren**`,
      `„${ILIAS.identification.de}“: **„ID des ILIAS-Kontos kombiniert mit einer eindeutigen ILIAS-Plattform-ID, die als E-Mail-Adresse formatiert ist“**`,
      'Bitte **nicht** „E-Mail-Adresse“ wählen',
      `„Anmeldename“: **„${ILIAS.fullName.de}“**`,
      `„${ILIAS.outcome.de}“ **anhaken**`,
      `„${ILIAS.masteryDefault.de}“ auf **22**`,
      '„Hinweise“',
      'Administration → Lernerfolge → Zugriffsstatistiken und Lernfortschritt',
      '„Tracking aktivieren“ „Lernfortschritt“ anhaken',
      '„Optionen für den Start“: **„Neues Fenster“**',
      '„Optionen für den Lernfortschritt“',
      'keine echte E-Mail-Adresse',
      'einmal nach ihrer E-Mail-Adresse gefragt',
      'Der Schritt lässt sich überspringen',
      'zugleich die Aktivierungsmail',
    ]) {
      expect(sheet).toContain(text)
    }
    for (const stale of [
      ILIAS.hash,
      'keine Aktivierungsmail',
      'Add Global Provider',
      'Erweiterung von ILIAS',
      'Advanced Grading Services',
      'Identifizierung per',
      'JWK-Keyset-URL',
    ]) {
      expect(sheet).not.toContain(stale)
    }
  })

  it('uses the visible switch labels of the panel', () => {
    const settings = section('### Connection settings')
    for (const locale of LOCALES) {
      const pairs: Array<[string, string]> = [
        ['extended.lti.orgPanel.switchOn', 'extended.lti.orgPanel.switchOn'],
        ['extended.lti.orgPanel.switchOff', 'extended.lti.orgPanel.switchOff'],
        [
          'extended.lti.orgPanel.switchedOffBadge',
          'extended.lti.orgPanel.switchedOffBadge',
        ],
        [
          'extended.lti.admin.deploymentSwitchOn',
          'extended.lti.admin.deploymentSwitchOn',
        ],
        [
          'extended.lti.admin.deploymentSwitchOff',
          'extended.lti.admin.deploymentSwitchOff',
        ],
      ]
      for (const [key] of pairs) {
        const text = label(locale, key)
        expect(settings).toContain(
          locale === 'en' ? `**${text}**` : `*${text}*`,
        )
      }
    }
  })

  it('states the smaller corrections precisely', () => {
    expect(section('### 8.1 Accounts and names')).toMatch(
      /reserved top-level domains such as `\.invalid` or `\.local`/,
    )
    const errors = section('### Launch error codes')
    expect(errors).not.toMatch(/deactivated or anonymized/)
    expect(errors).toMatch(
      /An anonymized account never comes back: anonymizing removes its LMS link, so a later launch creates a new account/,
    )
    expect(errors).toContain(
      'The page *Separate account* offers only **Continue**, which creates a separate account',
    )
    expect(flatDoc).toMatch(
      /A score that the LMS refuses for good \(400, 401, 403, 404 or another 4xx status that is not listed above\) makes the row `failed` at once/,
    )
    expect(flatDoc).toMatch(/"KI-Bewertung: <activity title>"/)
    expect(section('## Appendix B')).toContain(
      '„KI-Bewertung: <Titel der Aktivität>“',
    )
    expect(section('### 8.9 Retention')).toMatch(
      /all stored sign-in sessions \(open and ended ones\)/,
    )
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

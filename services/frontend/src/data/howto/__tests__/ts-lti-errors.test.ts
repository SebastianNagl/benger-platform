/**
 * The "launch from Moodle or ILIAS fails" how-to (ts-lti-errors).
 *
 * The guide is the long form of the LTI error page: one step per page code
 * of lib/lti/launchErrors.ts, in the same order, in German and English, each
 * with cause, fix and who can help. These tests keep it in step with the
 * code list and pin the statements users rely on.
 */

import {
  guideSearchText,
  normalizeForSearch,
  type HowToGuide,
} from '@/lib/howto/registry'
import { LTI_LAUNCH_ERROR_CODES } from '@/lib/lti/launchErrors'
import { buildGuideIndex, rankSearchResults } from '@/lib/search'
import deCommon from '@/locales/de/common.json'
import enCommon from '@/locales/en/common.json'

import { PLATFORM_HOWTO_GUIDES } from '../guides'
import { TROUBLESHOOTING_GUIDES } from '../guides/troubleshooting'

const LOCALES = ['de', 'en'] as const

function getGuide(): HowToGuide {
  const guide = TROUBLESHOOTING_GUIDES.find((g) => g.id === 'ts-lti-errors')
  if (!guide) throw new Error('ts-lti-errors guide missing')
  return guide
}

function stepFor(code: string, locale: 'de' | 'en'): string {
  const step = getGuide().steps?.[locale].find((s) =>
    s.startsWith(`\`${code}\`:`),
  )
  if (!step) throw new Error(`no ${locale} step for ${code}`)
  return step
}

function allText(guide: HowToGuide, locale: 'de' | 'en'): string[] {
  return [
    guide.title[locale],
    guide.summary[locale],
    ...(guide.steps?.[locale] ?? []),
    ...(guide.tips?.[locale] ?? []),
    ...(guide.pitfalls?.[locale] ?? []),
    ...(guide.links ?? []).map((l) => l.label[locale]),
  ]
}

describe('ts-lti-errors guide', () => {
  it('is a troubleshooting guide of the platform', () => {
    const guide = getGuide()
    expect(guide.category).toBe('troubleshooting')
    expect(PLATFORM_HOWTO_GUIDES).toContain(guide)
  })

  it.each(LOCALES)(
    'has one %s step per launch error code, in registry order',
    (locale) => {
      const leads = (getGuide().steps?.[locale] ?? []).map(
        (step) => /^`([a-z_]+)`: /.exec(step)?.[1],
      )
      expect(leads).toEqual([...LTI_LAUNCH_ERROR_CODES])
    },
  )

  it('keeps German and English lists the same length', () => {
    const guide = getGuide()
    for (const field of ['steps', 'tips', 'pitfalls', 'keywords'] as const) {
      const list = guide[field]
      expect(list).toBeDefined()
      expect(list?.de.length).toBe(list?.en.length)
      expect(list?.de.length).toBeGreaterThan(0)
    }
  })

  it.each(LOCALES)('gives cause and fix in every %s step', (locale) => {
    for (const code of LTI_LAUNCH_ERROR_CODES) {
      const body = stepFor(code, locale).slice(code.length + 4)
      // At least two sentences: what happened, and what to do or who acts.
      expect(body.split(/\.\s/).length).toBeGreaterThanOrEqual(2)
    }
  })

  it.each(LOCALES)('uses plain wording in %s', (locale) => {
    for (const text of allText(getGuide(), locale)) {
      expect(text).not.toMatch(/\u2014/) // no em dash
      expect(text).not.toMatch(/ \u2013 /) // no en dash as a dash
      expect(text).not.toMatch(/vertretbar/i)
      expect(text).not.toMatch(/superadmin/i)
    }
  })

  it('addresses readers formally in German', () => {
    for (const text of allText(getGuide(), 'de')) {
      expect(text).not.toMatch(/\b(du|dich|dein|deine|deinen|deiner)\b/i)
    }
  })

  it('explains how to read the error page', () => {
    const guide = getGuide()
    expect(guide.summary.de).toMatch(/Fehlercode/)
    expect(guide.summary.de).toMatch(/Referenz/)
    expect(guide.summary.en).toMatch(/error code/)
    expect(guide.summary.en).toMatch(/reference/)
  })

  it('says a switched-off connection shows registration_disabled', () => {
    expect(stepFor('registration_disabled', 'de')).toMatch(
      /abgeschaltete Anbindung zeigt bei jedem Start diesen Code/,
    )
    expect(stepFor('registration_disabled', 'en')).toMatch(
      /switched-off connection shows this code on every launch/,
    )
  })

  it('says invalid_state is an old or reused sign-in, not a cookie problem', () => {
    expect(stepFor('invalid_state', 'de')).toMatch(
      /älter als 5 Minuten oder wurde schon verwendet/,
    )
    expect(stepFor('invalid_state', 'en')).toMatch(
      /older than 5 minutes or was already used/,
    )
    for (const locale of LOCALES) {
      expect(stepFor('invalid_state', locale)).not.toMatch(/cookie/i)
    }
  })

  it('calls state_unavailable a temporary server problem', () => {
    expect(stepFor('state_unavailable', 'de')).toMatch(
      /vorübergehendes Serverproblem/,
    )
    expect(stepFor('state_unavailable', 'en')).toMatch(
      /temporary server problem/,
    )
    for (const locale of LOCALES) {
      expect(stepFor('state_unavailable', locale)).not.toMatch(/cookie/i)
    }
  })

  it('names the ILIAS provider ID for unknown_deployment', () => {
    expect(stepFor('unknown_deployment', 'de')).toMatch(/Provider-ID/)
    expect(stepFor('unknown_deployment', 'en')).toMatch(/provider ID/)
  })

  it('says membership_removed means an admin removed the person', () => {
    expect(stepFor('membership_removed', 'de')).toMatch(
      /Admin hat die Person aus der Organisation/,
    )
    expect(stepFor('membership_removed', 'en')).toMatch(
      /admin removed the person from the organization/,
    )
  })

  it('says how an org admin restores a removed membership', () => {
    const labels = {
      de: [
        deCommon.admin.organizations.inviteMember,
        deCommon.login.forgotPassword,
      ],
      en: [
        enCommon.admin.organizations.inviteMember,
        enCommon.login.forgotPassword,
      ],
    }
    for (const locale of LOCALES) {
      for (const label of labels[locale]) {
        expect(stepFor('membership_removed', locale)).toContain(`**${label}**`)
      }
    }
    expect(stepFor('membership_removed', 'de')).toMatch(
      /Einladung angemeldet an, ist die Mitgliedschaft wieder aktiv/,
    )
    // Accounts with a placeholder address get neither mail: the operator
    // adds them back, and group memberships are restored in the group.
    expect(stepFor('membership_removed', 'de')).toContain(
      `**${deCommon.admin.organizations.addExistingUser}**`,
    )
    expect(stepFor('membership_removed', 'en')).toContain(
      `**${enCommon.admin.organizations.addExistingUser}**`,
    )
    expect(stepFor('membership_removed', 'de')).toMatch(/der Gruppe hinzufügen/)
    expect(stepFor('membership_removed', 'en')).toMatch(
      /adding the person to the group/,
    )
    expect(stepFor('membership_removed', 'en')).toMatch(
      /accepts it while signed in, the membership is active again/,
    )
  })

  it('names the headings the pages show instead of a code', () => {
    const cases: Array<[string, string[]]> = [
      ['launch_expired', ['extended', 'lti', 'consent', 'expiredTitle']],
      ['launch_mismatch', ['extended', 'lti', 'consent', 'mismatchTitle']],
      [
        'link_proof_failed',
        ['extended', 'lti', 'identity', 'confirm', 'errorTitle'],
      ],
    ]
    const commons = { de: deCommon, en: enCommon } as const
    for (const [code, path] of cases) {
      for (const locale of LOCALES) {
        let node: unknown = commons[locale]
        for (const part of path) {
          node = (node as Record<string, unknown>)[part]
        }
        expect(typeof node).toBe('string')
        expect(stepFor(code, locale)).toContain(`**${node as string}**`)
        const keywords = (getGuide().keywords?.[locale] ?? []).map((k) =>
          k.toLowerCase(),
        )
        expect(keywords).toContain((node as string).toLowerCase())
      }
    }
  })

  it('ties launch_expired to a consent page left open too long', () => {
    expect(stepFor('launch_expired', 'de')).toMatch(
      /Zustimmungsseite .* länger als 30 Minuten/,
    )
    expect(stepFor('launch_expired', 'en')).toMatch(
      /consent page .* more than 30 minutes/,
    )
  })

  it('offers a separate account for account_not_linkable', () => {
    expect(stepFor('account_not_linkable', 'de')).toMatch(
      /Mit separatem Konto fortfahren/,
    )
    expect(stepFor('account_not_linkable', 'en')).toMatch(
      /Continue with a separate account/,
    )
  })

  it('tells who acts for each kind of problem', () => {
    const orgAdmin = {
      de: /Admins Ihrer Organisation/,
      en: /admins of your organization/,
    }
    const lmsAdmin = {
      de: /Administration der Lernplattform/,
      en: /learning platform administration/,
    }
    const reopen = {
      de: /Öffnen Sie die Aktivität erneut/,
      en: /Open the activity again/,
    }
    const operator = {
      de: /Betreiber der Plattform/,
      en: /operator of the platform/,
    }
    const expectations: Array<[string, Record<'de' | 'en', RegExp>[]]> = [
      ['registration_not_found', [orgAdmin, lmsAdmin]],
      ['registration_disabled', [orgAdmin]],
      ['unknown_deployment', [lmsAdmin, orgAdmin]],
      ['deployment_disabled', [orgAdmin]],
      ['membership_removed', [orgAdmin]],
      ['unsupported_message', [lmsAdmin]],
      ['invalid_state', [reopen]],
      ['launch_expired', [reopen]],
      ['launch_mismatch', [reopen]],
      ['link_proof_failed', [reopen]],
      ['org_inactive', [operator]],
      ['tool_not_configured', [operator]],
      ['internal', [operator]],
    ]
    for (const [code, patterns] of expectations) {
      for (const locale of LOCALES) {
        for (const pattern of patterns) {
          expect(stepFor(code, locale)).toMatch(pattern[locale])
        }
      }
    }
  })

  it('warns that an iframe launch lands on the login page', () => {
    const guide = getGuide()
    expect(
      guide.pitfalls?.de.some(
        (p) => /iframe/.test(p) && /Anmeldeseite/.test(p),
      ),
    ).toBe(true)
    expect(
      guide.pitfalls?.en.some((p) => /iframe/.test(p) && /login page/.test(p)),
    ).toBe(true)
  })

  it('links only to guides that exist', () => {
    const ids = new Set(PLATFORM_HOWTO_GUIDES.map((g) => g.id))
    const links = getGuide().links ?? []
    expect(links.map((l) => l.href)).toEqual(
      expect.arrayContaining(['/how-to#lti-setup', '/how-to#lti-manage']),
    )
    for (const link of links) {
      const anchor = /^\/how-to#(.+)$/.exec(link.href)?.[1]
      expect(anchor).toBeDefined()
      expect(ids.has(anchor as string)).toBe(true)
    }
  })

  it.each(LOCALES)('is found by every error code (%s search)', (locale) => {
    const text = guideSearchText(getGuide(), locale)
    for (const code of LTI_LAUNCH_ERROR_CODES) {
      expect(text).toContain(normalizeForSearch(code))
    }
    const entries = buildGuideIndex({
      t: (_key: string, fallback?: string) => fallback ?? _key,
      locale,
      flags: {},
      user: {},
      organizations: [],
      guides: PLATFORM_HOWTO_GUIDES,
    } as Parameters<typeof buildGuideIndex>[0])
    for (const code of [
      'registration_disabled',
      'unknown_deployment',
      'launch_expired',
      'membership_removed',
    ]) {
      const urls = rankSearchResults(entries, code).map((r) => r.url)
      expect(urls[0]).toBe('/how-to#ts-lti-errors')
    }
  })
})

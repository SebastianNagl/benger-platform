/**
 * The Korrektur page shows one tab per enabled human grading metric and
 * labels it with `korrekturWorkflow.metricTabs.<metric>`. A missing key
 * renders the raw key path as the tab label, which is what an exam with a
 * grading sheet (korrektur_custom) showed.
 */

import deCommon from '@/locales/de/common.json'
import enCommon from '@/locales/en/common.json'

// Every human grading metric the Korrektur page can list as a tab.
const KORREKTUR_METRICS = [
  'korrektur_classic',
  'korrektur_falloesung',
  'korrektur_custom',
] as const

const TABS = {
  de: deCommon.korrekturWorkflow.metricTabs as Record<string, string>,
  en: enCommon.korrekturWorkflow.metricTabs as Record<string, string>,
}

describe('Korrektur metric tab labels', () => {
  it.each(['de', 'en'] as const)('labels every metric in %s', (locale) => {
    for (const metric of KORREKTUR_METRICS) {
      const text = TABS[locale][metric]
      expect(typeof text).toBe('string')
      expect(text.trim().length).toBeGreaterThan(0)
      expect(text).not.toContain('korrekturWorkflow')
    }
    expect(Object.keys(TABS[locale]).sort()).toEqual(
      [...KORREKTUR_METRICS].sort(),
    )
  })

  it('names the grading sheet tab like the other grading tabs', () => {
    expect(TABS.de.korrektur_custom).toBe('Bewertungen (Bewertungsbogen)')
    expect(TABS.en.korrektur_custom).toBe('Grades (grading sheet)')
    expect(TABS.de.korrektur_falloesung).toMatch(/^Bewertungen \(/)
    expect(TABS.en.korrektur_falloesung).toMatch(/^Grades \(/)
  })
})

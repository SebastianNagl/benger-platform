import {
  formatAxisValue,
  formatCount,
  formatDate,
  formatDateTime,
  formatGradePoints,
  formatMetricValue,
  formatNumber,
  formatRate,
  humanizeMetricId,
  localeTag,
  metricLabel,
  metricScale,
  scaleLabel,
  scaleMax,
} from '../format'
import { REPORT_SNAPSHOT_FIXTURE } from '../fixture'

describe('format helpers', () => {
  it('maps app locales to BCP-47 tags', () => {
    expect(localeTag('de')).toBe('de-DE')
    expect(localeTag('en')).toBe('en-US')
    expect(localeTag('fr-FR')).toBe('fr-FR')
  })

  it('formats numbers per locale', () => {
    expect(formatNumber(84.66, 'de', 1)).toBe('84,7')
    expect(formatNumber(84.66, 'en', 1)).toBe('84.7')
    expect(formatCount(3626, 'de')).toBe('3.626')
    expect(formatCount(3626, 'en')).toBe('3,626')
  })

  describe('formatMetricValue', () => {
    it('renders each scale family', () => {
      expect(formatMetricValue(0.847, '0-1', 'de')).toBe('84,7 %')
      expect(formatMetricValue(84.7, '0-100', 'de')).toBe('84,7 / 100')
      expect(formatMetricValue(13.9, '0-18', 'de')).toBe('13,9 NP')
      expect(formatMetricValue(0.2134, 'raw', 'de')).toBe('0,21')
      expect(formatMetricValue(0.2134, undefined, 'en')).toBe('0.21')
    })

    it('returns a dash for missing values', () => {
      expect(formatMetricValue(null, '0-1', 'de')).toBe('–')
      expect(formatMetricValue(undefined, '0-100', 'de')).toBe('–')
      expect(formatMetricValue(Number.NaN, '0-18', 'de')).toBe('–')
    })
  })

  it('formats grade points with the denominator', () => {
    expect(formatGradePoints(13.9, 'de')).toBe('13,9 / 18 NP')
    expect(formatGradePoints(13.9, 'en')).toBe('13.9 / 18 NP')
    expect(formatGradePoints(null, 'de')).toBe('–')
    expect(formatGradePoints(Number.NaN, 'de')).toBe('–')
  })

  it('formats pass rates as whole percentages', () => {
    expect(formatRate(0.93, 'de')).toBe('93 %')
    expect(formatRate(1, 'de')).toBe('100 %')
    expect(formatRate(null, 'de')).toBe('–')
    expect(formatRate(undefined, 'de')).toBe('–')
  })

  it('humanizes metric ids', () => {
    expect(humanizeMetricId('llm_judge_falloesung_grade_points')).toBe('Llm Judge Falloesung Grade Points')
    expect(humanizeMetricId('bleu')).toBe('Bleu')
    expect(humanizeMetricId('__x')).toBe('X')
  })

  describe('metricLabel / metricScale', () => {
    const methods = REPORT_SNAPSHOT_FIXTURE.methods

    it('prefers the registry, then the snapshot, then a humanized id', () => {
      const registry = { llm_judge_falloesung: { display_name: 'Falllösung LLM Judge (Registry)' } }
      expect(metricLabel('llm_judge_falloesung', methods, registry)).toBe('Falllösung LLM Judge (Registry)')
      expect(metricLabel('llm_judge_falloesung', methods)).toBe('Falllösung LLM Judge')
      expect(metricLabel('rouge_l', methods, registry)).toBe('Rouge L')
      expect(metricLabel('rouge_l', undefined)).toBe('Rouge L')
    })

    it('resolves scales from the snapshot first, then the registry, then raw', () => {
      expect(metricScale('llm_judge_falloesung_grade_points', methods)).toBe('0-18')
      expect(metricScale('rouge_l', methods, { rouge_l: { display_scale: '0-1' } })).toBe('0-1')
      expect(metricScale('unknown', methods)).toBe('raw')
      expect(metricScale('unknown', undefined, {})).toBe('raw')
    })
  })

  it('describes scales and their upper bounds', () => {
    expect(scaleLabel('0-1')).toBe('0–1 (Anteil)')
    expect(scaleLabel('0-100')).toBe('0–100 Punkte')
    expect(scaleLabel('0-18')).toBe('0–18 Notenpunkte')
    expect(scaleLabel('raw')).toBe('Rohwert')
    expect(scaleLabel(undefined)).toBe('Rohwert')
    expect(scaleMax('0-1')).toBe(1)
    expect(scaleMax('0-100')).toBe(100)
    expect(scaleMax('0-18')).toBe(18)
    expect(scaleMax('raw')).toBeNull()
  })

  it('formats axis ticks per scale', () => {
    expect(formatAxisValue(0.5, '0-1', 'de')).toBe('50 %')
    expect(formatAxisValue(50, '0-100', 'de')).toBe('50')
    expect(formatAxisValue(12.5, '0-18', 'de')).toBe('13')
    expect(formatAxisValue(0.256, 'raw', 'en')).toBe('0.26')
  })

  it('formats dates and tolerates bad input', () => {
    expect(formatDate('2026-09-02T12:00:00Z', 'de')).toMatch(/2026/)
    expect(formatDate('2026-09-02T12:00:00Z', 'en')).toMatch(/September/)
    expect(formatDate(null, 'de')).toBe('')
    expect(formatDate('nope', 'de')).toBe('')
    expect(formatDateTime('2026-09-02T12:00:00Z', 'de')).toMatch(/2026/)
    expect(formatDateTime(undefined, 'de')).toBe('')
    expect(formatDateTime('nope', 'de')).toBe('')
  })
})

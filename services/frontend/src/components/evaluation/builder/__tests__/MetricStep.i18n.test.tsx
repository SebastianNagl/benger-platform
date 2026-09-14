/**
 * @jest-environment jsdom
 *
 * MetricStep (step 1 of the evaluation builder) renders the metric catalogue
 * in the UI language, with the English literal as the fallback for overlay
 * groups registered without keys.
 */
import '@testing-library/jest-dom'
import { fireEvent, render, screen } from '@testing-library/react'
import * as fs from 'fs'
import * as path from 'path'

import { registerMetricGroup } from '@/lib/api/evaluation-types'
import { MetricStep } from '../MetricStep'

const mockLocales: Record<string, any> = Object.fromEntries(
  ['de', 'en'].map((lang) => [
    lang,
    JSON.parse(
      fs.readFileSync(
        path.resolve(__dirname, `../../../../locales/${lang}/common.json`),
        'utf8',
      ),
    ),
  ]),
)
let mockLang = 'de'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, def?: any) => {
      const value = key
        .split('.')
        .reduce(
          (node: any, part) => (node == null ? node : node[part]),
          mockLocales[mockLang],
        )
      if (typeof value === 'string') return value
      return typeof def === 'string' ? def : key
    },
    locale: mockLang,
  }),
}))

registerMetricGroup({
  name: 'Overlay Group',
  description: 'Overlay literal',
  // Unregistered metric ids render no button; the group header still shows.
  metrics: ['overlay_unregistered'],
  nameKey: 'overlay.group.missing',
})

afterEach(() => {
  mockLang = 'de'
})

describe('MetricStep: translated metric catalogue', () => {
  it('renders groups and metrics in German', () => {
    render(<MetricStep selectedMetric="" onSelectMetric={jest.fn()} />)
    expect(screen.getByText('Lexikalische Metriken')).toBeInTheDocument()
    expect(
      screen.getByText('Zeichenketten- und Oberflächenabgleich'),
    ).toBeInTheDocument()
    const button = screen.getByTestId('metric-button-exact_match')
    expect(button).toHaveTextContent('Exakte Übereinstimmung')
    expect(
      button.querySelector('[title="Exakter Zeichenkettenabgleich"]'),
    ).not.toBeNull()
    expect(screen.queryByText('Lexical Metrics')).not.toBeInTheDocument()
    expect(screen.queryByText('Exact Match')).not.toBeInTheDocument()
  })

  it('renders groups and metrics in English', () => {
    mockLang = 'en'
    render(<MetricStep selectedMetric="" onSelectMetric={jest.fn()} />)
    expect(screen.getByText('Lexical Metrics')).toBeInTheDocument()
    expect(screen.getByTestId('metric-button-exact_match')).toHaveTextContent(
      'Exact Match',
    )
  })

  it('keeps the literal of an overlay group whose key does not resolve', () => {
    render(<MetricStep selectedMetric="" onSelectMetric={jest.fn()} />)
    expect(screen.getByText('Overlay Group')).toBeInTheDocument()
    expect(screen.getByText('Overlay literal')).toBeInTheDocument()
  })

  it('still selects a metric by its id', () => {
    const onSelectMetric = jest.fn()
    render(<MetricStep selectedMetric="" onSelectMetric={onSelectMetric} />)
    fireEvent.click(screen.getByTestId('metric-button-bleu'))
    expect(onSelectMetric).toHaveBeenCalledWith('bleu')
  })
})

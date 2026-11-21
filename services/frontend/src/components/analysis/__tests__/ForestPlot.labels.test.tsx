/**
 * Long row labels of the forest plot (e.g. system keys as scopes): every
 * label lies inside the SVG at desktop and phone width, in full where it
 * fits and shortened in the middle with a tooltip where it does not.
 *
 * The labels are measured with a canvas stub whose characters are 10 px
 * wide, wider than the real 12 px font, so the layout has to rely on the
 * measurement and not on a per-character guess.
 */

import '@testing-library/jest-dom'
import { render, screen, within } from '@testing-library/react'

import {
  fitLabel,
  ForestPlot,
  type ForestPlotRow,
} from '@/components/analysis/ForestPlot'

jest.mock('@/contexts/I18nContext', () =>
  require('@/test-utils/i18nMock').i18nMock('en'),
)

const CHAR = 10
const textWidth = (text: string) => text.length * CHAR

class FakeOffscreenCanvas {
  getContext() {
    return { font: '', measureText: (t: string) => ({ width: textWidth(t) }) }
  }
}

const SYSTEMS = [
  'Qwen/Qwen3.8-27B-Instruct@2026-10-01-a1b2c3d4e5f6',
  'meta-llama/Llama-5-70B-Instruct-Turbo@2026-09-15-ffeeddccbbaa',
]

const rows = (labels: string[]): ForestPlotRow[] =>
  labels.map((label, i) => ({
    id: String(i),
    label,
    estimate: 0.1 * (i + 1),
    lower: 0.1 * i - 0.05,
    upper: 0.1 * i + 0.25,
    emphasis: i === 0,
  }))

let width = 0
beforeAll(() => {
  ;(globalThis as { OffscreenCanvas?: unknown }).OffscreenCanvas =
    FakeOffscreenCanvas
  jest
    .spyOn(HTMLElement.prototype, 'clientWidth', 'get')
    .mockImplementation(() => width)
})
afterAll(() => {
  delete (globalThis as { OffscreenCanvas?: unknown }).OffscreenCanvas
  jest.restoreAllMocks()
})

/** Each label's shown text, tooltip and horizontal extent. */
function labels() {
  const svg = screen.getByRole('img')
  return within(svg)
    .getAllByTestId('forest-plot-label')
    .map((node) => {
      const shown = [...node.childNodes]
        .filter((c) => c.nodeType === Node.TEXT_NODE)
        .map((c) => c.textContent)
        .join('')
      const x = Number(node.getAttribute('x'))
      const endAnchored = node.getAttribute('text-anchor') === 'end'
      const left = endAnchored ? x - textWidth(shown) : x
      return {
        shown,
        tooltip: node.querySelector('title')?.textContent ?? null,
        left,
        right: left + textWidth(shown),
        svgWidth: Number(svg.getAttribute('width')),
      }
    })
}

describe.each([
  ['desktop', 1100],
  ['phone', 343],
])('long labels at %s width', (_name, containerWidth) => {
  it('keeps every label inside the plot and readable', () => {
    width = containerWidth
    const labelTexts = ['Pooled', ...SYSTEMS.map((s) => `stem = ${s}`)]
    render(<ForestPlot rows={rows(labelTexts)} ariaLabel="plot" />)
    const shown = labels()
    expect(shown).toHaveLength(labelTexts.length)
    shown.forEach((label, i) => {
      expect(label.svgWidth).toBe(containerWidth)
      expect(label.left).toBeGreaterThanOrEqual(0)
      expect(label.right).toBeLessThanOrEqual(containerWidth)
      if (label.shown === labelTexts[i]) {
        expect(label.tooltip).toBeNull()
      } else {
        // Shortened in the middle: start and end of the key stay visible.
        expect(label.tooltip).toBe(labelTexts[i])
        const [head, tail] = label.shown.split('…')
        expect(labelTexts[i].startsWith(head)).toBe(true)
        expect(labelTexts[i].endsWith(tail)).toBe(true)
        expect(tail.length).toBeGreaterThan(0)
      }
    })
    // The axis tick labels at the plot's ends stay inside too.
    const ticks = [
      ...screen.getByRole('img').querySelectorAll('text[text-anchor="middle"]'),
    ]
    expect(ticks.length).toBeGreaterThan(1)
    for (const tick of ticks) {
      const half = textWidth(tick.textContent ?? '') / 2
      expect(Number(tick.getAttribute('x')) - half).toBeGreaterThanOrEqual(0)
      expect(Number(tick.getAttribute('x')) + half).toBeLessThanOrEqual(
        containerWidth,
      )
    }
    if (containerWidth >= 1000) {
      // Wide enough: every label is shown in full.
      expect(shown.map((l) => l.shown)).toEqual(labelTexts)
    }
  })
})

it('reserves a side column as wide as the longest short label', () => {
  width = 900
  render(
    <ForestPlot
      rows={rows(['Pooled', 'system = sys_a', 'system = sys_bb'])}
      ariaLabel="plot"
    />,
  )
  const shown = labels()
  // Right-aligned in one column whose left edge is the longest label's.
  expect(new Set(shown.map((l) => l.right)).size).toBe(1)
  expect(Math.min(...shown.map((l) => l.left))).toBeGreaterThanOrEqual(0)
  expect(Math.min(...shown.map((l) => l.left))).toBeLessThanOrEqual(8)
  expect(shown.every((l) => l.tooltip === null)).toBe(true)
  // The plot starts after the column.
  const point = screen.getAllByTestId('forest-plot-point')[0]
  expect(Number(point.getAttribute('x'))).toBeGreaterThan(shown[0].right)
})

it('keeps the band and vertical lines off the stacked labels', () => {
  width = 343
  const labelTexts = ['Pooled', ...SYSTEMS.map((s) => `stem = ${s}`)]
  render(
    <ForestPlot
      rows={rows(labelTexts)}
      band={{ lower: -0.2, upper: 0.2, label: 'Equivalence bounds' }}
      nullValue={0}
      ariaLabel="plot"
    />,
  )
  const svg = screen.getByRole('img')
  const labelNodes = within(svg).getAllByTestId('forest-plot-label')
  // Stacked: every label starts at the left edge on its own line.
  expect(new Set(labelNodes.map((n) => n.getAttribute('x'))).size).toBe(1)
  // A label's glyphs reach about one font size (12 px) above its baseline
  // and a few pixels below it.
  const labelLines = labelNodes.map((n) => {
    const baseline = Number(n.getAttribute('y'))
    return [baseline - 13, baseline + 4] as const
  })
  const bandSegments = [...svg.querySelectorAll('rect')].filter(
    (r) => r.querySelector('title')?.textContent === 'Equivalence bounds',
  )
  const verticalLines = [...svg.querySelectorAll('line')].filter(
    (l) => l.getAttribute('x1') === l.getAttribute('x2'),
  )
  expect(bandSegments.length).toBeGreaterThan(0)
  expect(verticalLines.length).toBeGreaterThan(0)
  const spans = [
    ...bandSegments.map((r) => {
      const y = Number(r.getAttribute('y'))
      return [y, y + Number(r.getAttribute('height'))] as const
    }),
    ...verticalLines.map((l) => {
      const ys = [Number(l.getAttribute('y1')), Number(l.getAttribute('y2'))]
      return [Math.min(...ys), Math.max(...ys)] as const
    }),
  ]
  for (const [top, bottom] of spans) {
    for (const [labelTop, labelBottom] of labelLines) {
      expect(bottom <= labelTop || top >= labelBottom).toBe(true)
    }
  }
})

describe('fitLabel', () => {
  const measure = (t: string) => textWidth(t)

  it('keeps a label that fits', () => {
    expect(fitLabel('short', 50, measure)).toBe('short')
  })

  it('keeps the most characters that fit around a middle ellipsis', () => {
    const fitted = fitLabel('abcdefghijklmnopqrstuvwxyz', 100, measure)
    expect(fitted).toBe('abcde…wxyz')
    expect(measure(fitted)).toBeLessThanOrEqual(100)
  })
})

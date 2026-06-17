/**
 * @jest-environment jsdom
 *
 * Behavioral tests for JudgeAgreementHeatmap — previously 0% covered.
 *
 * Exercises the uncovered logic paths:
 *   - judge-id cleaning (null/'null'/'None'/empty/duplicate stripping)
 *   - the `< 2 cleaned judges` → render null short-circuit
 *   - buildMatrix: diagonal = 1, pairwise mirroring across the diagonal,
 *     `${a}__${b}` vs `${b}__${a}` key lookup, missing/NaN cells left null
 *   - pearson vs kappa colorscale/zmin/colorbar branches
 *   - fleissKappa present vs null/undefined header branch
 *   - custom vs default height
 *
 * Mirrors the Plotly mocking idiom in
 * `charts/__tests__/SignificanceHeatmap.test.tsx`: mock `next/dynamic` to
 * return a component that captures the props handed to <Plot>, then assert on
 * the captured data/layout.
 */
import '@testing-library/jest-dom'
import { render, screen } from '@testing-library/react'

jest.mock('@/contexts/I18nContext', () => ({
  // Component calls t(key, fallback) — return the fallback so assertions can
  // match the human-readable German labels the component ships with.
  useI18n: () => ({
    t: (_key: string, fallback?: any) =>
      typeof fallback === 'string' ? fallback : _key,
    locale: 'en',
  }),
}))

// Capture every props object handed to the dynamically-imported <Plot>.
const mockPlotProps: any[] = []
jest.mock('next/dynamic', () => {
  return () => {
    const MockPlot = (props: any) => {
      mockPlotProps.push(props)
      return <div data-testid="plotly-chart" />
    }
    MockPlot.displayName = 'MockPlot'
    return MockPlot
  }
})

import { JudgeAgreementHeatmap } from '../JudgeAgreementHeatmap'

const lastProps = () => mockPlotProps[mockPlotProps.length - 1]

beforeEach(() => {
  mockPlotProps.length = 0
})

describe('JudgeAgreementHeatmap', () => {
  describe('render gating (< 2 cleaned judges)', () => {
    it('renders nothing when fewer than two judges are supplied', () => {
      const { container } = render(
        <JudgeAgreementHeatmap
          judgeModelIds={['only-judge']}
          metric="llm_judge_falloesung"
          pairwise={{}}
          scoreType="pearson"
        />,
      )
      expect(container).toBeEmptyDOMElement()
      expect(screen.queryByTestId('plotly-chart')).not.toBeInTheDocument()
    })

    it('renders nothing when an empty judge list is supplied', () => {
      const { container } = render(
        <JudgeAgreementHeatmap
          judgeModelIds={[]}
          metric="m"
          pairwise={{}}
          scoreType="kappa"
        />,
      )
      expect(container).toBeEmptyDOMElement()
    })

    it('renders nothing when cleaning drops the set below two distinct judges', () => {
      // Two raw ids but one is a null-ish sentinel + one dup → only one survives.
      const { container } = render(
        <JudgeAgreementHeatmap
          judgeModelIds={['gpt-4o', 'gpt-4o', 'null', 'None', '', '  ']}
          metric="m"
          pairwise={{}}
          scoreType="pearson"
        />,
      )
      expect(container).toBeEmptyDOMElement()
    })
  })

  describe('judge-id cleaning', () => {
    it('strips null-sentinels, blanks and duplicates while preserving order', () => {
      render(
        <JudgeAgreementHeatmap
          judgeModelIds={[
            'gpt-4o',
            'null',
            'None',
            '',
            '   ',
            'gpt-4o', // dup of first
            'claude',
            'claude', // dup
            'mistral',
          ]}
          metric="m"
          pairwise={{}}
          scoreType="pearson"
        />,
      )
      // Axes reflect the cleaned, de-duplicated, order-preserved set.
      expect(lastProps().data[0].x).toEqual(['gpt-4o', 'claude', 'mistral'])
      expect(lastProps().data[0].y).toEqual(['gpt-4o', 'claude', 'mistral'])
    })

    it('coerces non-string ids and trims whitespace', () => {
      render(
        <JudgeAgreementHeatmap
          // Intentionally exercise the `(id ?? '').toString().trim()` path with
          // a value that has surrounding whitespace.
          judgeModelIds={['  judge-a  ', 'judge-b']}
          metric="m"
          pairwise={{}}
          scoreType="kappa"
        />,
      )
      expect(lastProps().data[0].x).toEqual(['judge-a', 'judge-b'])
    })
  })

  describe('buildMatrix', () => {
    const judges = ['a', 'b', 'c']

    it('sets the diagonal to 1.0 and mirrors a single-triangle pairwise map', () => {
      render(
        <JudgeAgreementHeatmap
          judgeModelIds={judges}
          metric="m"
          // Only the a→b / a→c / b→c triangle is provided; component mirrors it.
          pairwise={{ a__b: 0.5, a__c: 0.25, b__c: -0.1 }}
          scoreType="pearson"
        />,
      )
      const z = lastProps().data[0].z
      // Diagonal
      expect(z[0][0]).toBe(1)
      expect(z[1][1]).toBe(1)
      expect(z[2][2]).toBe(1)
      // Direct key
      expect(z[0][1]).toBe(0.5)
      // Mirrored from a__b (the b→a cell uses the reversed key fallback)
      expect(z[1][0]).toBe(0.5)
      expect(z[2][0]).toBe(0.25)
      expect(z[0][2]).toBe(0.25)
      expect(z[1][2]).toBe(-0.1)
      expect(z[2][1]).toBe(-0.1)
    })

    it('formats off-diagonal cell text to three decimals and diagonal to 1.00', () => {
      render(
        <JudgeAgreementHeatmap
          judgeModelIds={['a', 'b']}
          metric="m"
          pairwise={{ a__b: 0.5 }}
          scoreType="pearson"
        />,
      )
      const text = lastProps().data[0].text
      expect(text[0][0]).toBe('1.00')
      expect(text[0][1]).toBe('0.500')
      expect(text[1][0]).toBe('0.500')
    })

    it('leaves missing pairwise entries as null cells with empty text', () => {
      render(
        <JudgeAgreementHeatmap
          judgeModelIds={['a', 'b', 'c']}
          metric="m"
          // b__c deliberately absent.
          pairwise={{ a__b: 0.3 }}
          scoreType="pearson"
        />,
      )
      const z = lastProps().data[0].z
      const text = lastProps().data[0].text
      expect(z[1][2]).toBeNull()
      expect(z[2][1]).toBeNull()
      expect(text[1][2]).toBe('')
    })

    it('treats NaN pairwise values as missing (null) rather than rendering NaN', () => {
      render(
        <JudgeAgreementHeatmap
          judgeModelIds={['a', 'b']}
          metric="m"
          pairwise={{ a__b: Number.NaN }}
          scoreType="pearson"
        />,
      )
      const z = lastProps().data[0].z
      expect(z[0][1]).toBeNull()
      expect(z[1][0]).toBeNull()
    })
  })

  describe('scoreType branches', () => {
    it('uses the RdBu diverging palette with zmin=-1 for pearson', () => {
      render(
        <JudgeAgreementHeatmap
          judgeModelIds={['a', 'b']}
          metric="m"
          pairwise={{ a__b: 0.5 }}
          scoreType="pearson"
        />,
      )
      const trace = lastProps().data[0]
      expect(trace.colorscale).toBe('RdBu')
      expect(trace.zmin).toBe(-1)
      expect(trace.zmax).toBe(1)
      expect(trace.colorbar.title.text).toBe('r')
      // Pearson title branch.
      expect(screen.getByText(/Pearson/)).toBeInTheDocument()
    })

    it('uses the Blues sequential palette with zmin=0 for kappa', () => {
      render(
        <JudgeAgreementHeatmap
          judgeModelIds={['a', 'b']}
          metric="m"
          pairwise={{ a__b: 0.5 }}
          scoreType="kappa"
        />,
      )
      const trace = lastProps().data[0]
      expect(trace.colorscale).toBe('Blues')
      expect(trace.zmin).toBe(0)
      expect(trace.zmax).toBe(1)
      expect(trace.colorbar.title.text).toBe('κ')
      // Kappa title branch (contains the κ glyph).
      expect(screen.getByText(/κ/)).toBeInTheDocument()
    })
  })

  describe('header + fleissKappa branch', () => {
    it('renders the metric name in the header', () => {
      render(
        <JudgeAgreementHeatmap
          judgeModelIds={['a', 'b']}
          metric="llm_judge_falloesung"
          pairwise={{ a__b: 0.5 }}
          scoreType="pearson"
        />,
      )
      expect(screen.getByText('llm_judge_falloesung')).toBeInTheDocument()
    })

    it('renders the Fleiss κ headline when a number is supplied', () => {
      render(
        <JudgeAgreementHeatmap
          judgeModelIds={['a', 'b']}
          metric="m"
          pairwise={{ a__b: 0.5 }}
          scoreType="kappa"
          fleissKappa={0.42}
        />,
      )
      expect(screen.getByText(/Fleiss/)).toBeInTheDocument()
      expect(screen.getByText('0.420')).toBeInTheDocument()
    })

    it('renders the Fleiss headline for a 0 value (not just truthy ones)', () => {
      // 0 is falsy but must still show — guards against an `if (fleissKappa)` bug.
      render(
        <JudgeAgreementHeatmap
          judgeModelIds={['a', 'b']}
          metric="m"
          pairwise={{ a__b: 0.5 }}
          scoreType="kappa"
          fleissKappa={0}
        />,
      )
      expect(screen.getByText(/Fleiss/)).toBeInTheDocument()
      expect(screen.getByText('0.000')).toBeInTheDocument()
    })

    it('omits the Fleiss headline when fleissKappa is null', () => {
      render(
        <JudgeAgreementHeatmap
          judgeModelIds={['a', 'b']}
          metric="m"
          pairwise={{ a__b: 0.5 }}
          scoreType="pearson"
          fleissKappa={null}
        />,
      )
      expect(screen.queryByText(/Fleiss/)).not.toBeInTheDocument()
    })

    it('omits the Fleiss headline when fleissKappa is undefined (default)', () => {
      render(
        <JudgeAgreementHeatmap
          judgeModelIds={['a', 'b']}
          metric="m"
          pairwise={{ a__b: 0.5 }}
          scoreType="pearson"
        />,
      )
      expect(screen.queryByText(/Fleiss/)).not.toBeInTheDocument()
    })
  })

  describe('layout / height', () => {
    it('defaults the plot height to 360', () => {
      render(
        <JudgeAgreementHeatmap
          judgeModelIds={['a', 'b']}
          metric="m"
          pairwise={{ a__b: 0.5 }}
          scoreType="pearson"
        />,
      )
      expect(lastProps().layout.height).toBe(360)
    })

    it('forwards a custom height to the layout', () => {
      render(
        <JudgeAgreementHeatmap
          judgeModelIds={['a', 'b']}
          metric="m"
          pairwise={{ a__b: 0.5 }}
          scoreType="pearson"
          height={520}
        />,
      )
      expect(lastProps().layout.height).toBe(520)
    })
  })
})

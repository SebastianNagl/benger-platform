/**
 * The value distribution chart: exact values and bins, the reference line,
 * the mean marker, the summary and the tooltips.
 */

import '@testing-library/jest-dom'
import { fireEvent, render, screen } from '@testing-library/react'

import { barsOf, ValueDistributionChart } from '../ValueDistributionChart'

jest.mock('@/contexts/I18nContext', () =>
  require('@/test-utils/i18nMock').i18nMock('en'),
)

describe('ValueDistributionChart', () => {
  it('draws exact values with the reference, mean and summary', () => {
    const { container } = render(
      <ValueDistributionChart
        data={{
          histogram: {
            kind: 'exact',
            values: [
              [-5, 2],
              [0, 6],
              [5, 4],
              [10, 1],
            ],
          },
          n: 13,
          groups: 7,
          mean: 1.92,
          median: 0,
          atReference: 6,
          above: 5,
          below: 2,
        }}
        valueLabel="Difference of share"
      />,
    )
    expect(screen.getAllByTestId('distribution-bar')).toHaveLength(4)
    expect(screen.getByTestId('distribution-reference')).toBeInTheDocument()
    expect(screen.getByTestId('distribution-mean')).toBeInTheDocument()
    expect(
      screen.getByRole('img', { name: 'Distribution of 13 values, mean 1.92' }),
    ).toBeInTheDocument()
    expect(screen.getByText('Difference of share')).toBeInTheDocument()
    expect(screen.getByText('13 from 7 units')).toBeInTheDocument()
    expect(screen.getByText('1.92 · 0')).toBeInTheDocument()
    expect(screen.getByText('At 0')).toBeInTheDocument()
    expect(screen.getByText('5 · 2')).toBeInTheDocument()

    const hit = container.querySelectorAll('rect')[1] as SVGRectElement
    fireEvent.mouseMove(hit, { clientX: 5, clientY: 5 })
    expect(screen.getByRole('tooltip')).toHaveTextContent('0: 6')
    fireEvent.mouseLeave(container.querySelector('svg') as SVGSVGElement)
    expect(screen.queryByRole('tooltip')).toBeNull()
  })

  it('draws bins and leaves out what the data does not carry', () => {
    const { container } = render(
      <ValueDistributionChart
        data={{
          histogram: {
            kind: 'bins',
            bins: [
              [0, 0.5, 3],
              [0.5, 1, 1],
            ],
          },
          n: 4,
        }}
        valueLabel="Rate"
        referenceValue={0.5}
      />,
    )
    expect(screen.getAllByTestId('distribution-bar')).toHaveLength(2)
    expect(screen.queryByTestId('distribution-mean')).toBeNull()
    expect(screen.getByText('4')).toBeInTheDocument()
    expect(screen.queryByText(/Mean/)).toBeNull()
    fireEvent.mouseMove(container.querySelectorAll('rect')[0], {
      clientX: 1,
      clientY: 1,
    })
    expect(screen.getByRole('tooltip')).toHaveTextContent('0 to 0.5: 3')
  })

  it('makes bars of exact values from the closest gap', () => {
    expect(
      barsOf({ kind: 'exact', values: [[1, 2]] }).map((b) => [b.lo, b.hi]),
    ).toEqual([[0.5, 1.5]])
    expect(
      barsOf({
        kind: 'exact',
        values: [
          [0, 1],
          [10, 1],
        ],
      })[0],
    ).toMatchObject({ lo: -4, hi: 4, exact: true })
  })
})

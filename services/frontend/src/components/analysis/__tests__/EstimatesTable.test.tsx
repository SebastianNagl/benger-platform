/**
 * The estimates table: one row per estimate with family and adjusted p, the
 * equivalence column, filters and the expandable details.
 */

import '@testing-library/jest-dom'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { EstimatesTable } from '@/components/analysis/EstimatesTable'
import { makeEstimates } from '@/test-utils/analysisFixtures'

jest.mock('@/contexts/I18nContext', () =>
  require('@/test-utils/i18nMock').i18nMock('en'),
)

const rowAt = (position: number) =>
  screen
    .getAllByTestId('estimate-row')
    .find((r) => r.getAttribute('data-position') === String(position))!

describe('EstimatesTable', () => {
  it('shows every estimate with its family, adjusted p and equivalence', () => {
    render(<EstimatesTable estimates={makeEstimates()} />)
    expect(screen.getAllByTestId('estimate-row')).toHaveLength(4)

    const pooled = within(rowAt(0))
    expect(pooled.getByText('Pooled')).toBeInTheDocument()
    expect(pooled.getByText('-2.5')).toBeInTheDocument()
    expect(pooled.getByText('[-3.48, -1.52]')).toBeInTheDocument()
    expect(pooled.getByText('0.010')).toBeInTheDocument()
    expect(pooled.getByText('primary')).toBeInTheDocument()
    expect(pooled.getByText('Holm')).toBeInTheDocument()
    expect(pooled.getByText('0.020')).toBeInTheDocument()
    expect(pooled.getByText('Not established')).toBeInTheDocument()
    expect(pooled.getByText(/\[-3, 3\] \(\+1 more\)/)).toBeInTheDocument()

    const sysA = within(rowAt(1))
    expect(sysA.getByText('system = sys_a')).toBeInTheDocument()
    expect(sysA.getByText('1E-4')).toBeInTheDocument()
    expect(sysA.getByText('2E-4')).toBeInTheDocument()

    expect(within(rowAt(2)).getByText('Equivalent')).toBeInTheDocument()

    const failed = within(rowAt(3))
    expect(failed.getByText('Error')).toBeInTheDocument()
    expect(failed.getByText('did sys_a')).toBeInTheDocument()
  })

  it('keeps the exact p-value in the cell title', () => {
    render(<EstimatesTable estimates={makeEstimates()} />)
    expect(within(rowAt(1)).getByText('1E-4')).toHaveAttribute(
      'title',
      '0.0001',
    )
  })

  it('expands a row to its tests, families and conventions', async () => {
    const user = userEvent.setup()
    render(<EstimatesTable estimates={makeEstimates()} />)
    expect(screen.queryByTestId('estimate-details')).toBeNull()
    await user.click(within(rowAt(0)).getByRole('button', { name: 'Details' }))
    const details = within(screen.getByTestId('estimate-details'))
    expect(details.getByText('Equivalence tests (TOST)')).toBeInTheDocument()
    expect(details.getByText('[-2, 2]')).toBeInTheDocument()
    expect(details.getByText('Families')).toBeInTheDocument()
    // family MDE of the Holm family
    expect(details.getByText('1.6')).toBeInTheDocument()
    expect(details.getByText(/"ssc": "statsmodels"/)).toBeInTheDocument()

    await user.click(within(rowAt(0)).getByRole('button', { name: 'Details' }))
    expect(screen.queryByTestId('estimate-details')).toBeNull()
  })

  it('shows the engine message of a failed estimate in its details', async () => {
    const user = userEvent.setup()
    render(<EstimatesTable estimates={makeEstimates()} />)
    await user.click(rowAt(3))
    expect(
      within(screen.getByTestId('estimate-details')).getByText(
        "unknown parameter 'x_p:system[sys_a]'",
      ),
    ).toBeInTheDocument()
  })

  it('filters by family membership and by estimand', async () => {
    const user = userEvent.setup()
    render(<EstimatesTable estimates={makeEstimates()} />)
    const family = screen.getByTestId('estimates-family-filter')
    expect(
      Array.from((family as HTMLSelectElement).options).map((o) => o.value),
    ).toEqual(['__all__', 'per_system', 'primary'])
    await user.selectOptions(family, 'per_system')
    expect(screen.getAllByTestId('estimate-row')).toHaveLength(2)
    expect(screen.getByText('2 of 4')).toBeInTheDocument()

    await user.selectOptions(
      screen.getByTestId('estimates-estimand-filter'),
      'by_system',
    )
    expect(
      screen.getByText('No estimates match the filter.'),
    ).toBeInTheDocument()

    await user.selectOptions(family, '__all__')
    expect(screen.getAllByTestId('estimate-row')).toHaveLength(1)
  })
})

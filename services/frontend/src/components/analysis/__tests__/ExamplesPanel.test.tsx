/**
 * The examples of a contrast: the units of the run's design, paged, one
 * opened in the unit viewer with the factor the contrast compares, the
 * system and design pickers, and the refusal for viewers without full
 * content rights.
 */

import '@testing-library/jest-dom'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { variantViewsAPI } from '@/lib/api/variantViews'
import { makeEstimate, makeRun } from '@/test-utils/analysisFixtures'
import {
  makeDesignRow,
  makeUnitView,
  SYSTEM_A,
  SYSTEM_B,
} from '@/test-utils/variantViewFixtures'
import { EXAMPLE_UNITS_PAGE, ExamplesPanel } from '../ExamplesPanel'

jest.mock('@/contexts/I18nContext', () =>
  require('@/test-utils/i18nMock').i18nMock('en'),
)

jest.mock('@/lib/api/variantViews', () => ({
  variantViewsAPI: {
    listDesigns: jest.fn(),
    listUnits: jest.fn(),
    getUnit: jest.fn(),
    getTrialRequest: jest.fn(),
  },
}))

const api = variantViewsAPI as jest.Mocked<typeof variantViewsAPI>

const run = makeRun({
  normalized_spec: {
    inputs: { designs: ['swap', 'second'] },
    measures: {
      x_second: { kind: 'expression', expr: "1 * (party == 'second')" },
    },
    estimands: [
      {
        id: 'party',
        estimator: 'fe_ols',
        terms: ['x_second', 'order_late'],
        contrasts: [
          { id: 'party', kind: 'linear', weights: { x_second: 1 } },
          { id: 'order', kind: 'linear', weights: { order_late: 1 } },
        ],
      },
    ],
  },
})

const estimates = [
  makeEstimate({ position: 0, estimand_id: 'party', contrast_id: 'party' }),
  makeEstimate({
    position: 1,
    estimand_id: 'party',
    contrast_id: 'party',
    scope: 'by system',
    scope_values: { system: SYSTEM_A },
  }),
  makeEstimate({
    position: 2,
    estimand_id: 'party',
    contrast_id: 'party',
    scope: 'by system',
    scope_values: { system: SYSTEM_B },
  }),
  makeEstimate({ position: 3, estimand_id: 'party', contrast_id: 'order' }),
  makeEstimate({ position: 4, estimand_id: 'joint', kind: 'wald' }),
]

const units = (from: number, count: number, total: number) => ({
  items: Array.from({ length: count }, (_, i) => ({
    unit: `u${from + i + 1}`,
    task_count: 4,
  })),
  total,
  limit: EXAMPLE_UNITS_PAGE,
  offset: from,
})

beforeEach(() => {
  jest.clearAllMocks()
  api.listDesigns.mockResolvedValue([
    makeDesignRow({
      spec: {
        ...makeDesignRow().spec,
        factors: [
          { name: 'party', type: 'nominal', levels: ['first', 'second'] },
          { name: 'order', type: 'nominal', levels: ['early', 'late'] },
        ],
      },
    }),
  ])
  api.getUnit.mockResolvedValue(makeUnitView())
})

describe('ExamplesPanel', () => {
  it('opens the first unit with the factor the contrast compares', async () => {
    api.listUnits.mockResolvedValue(units(0, 3, 3))
    render(<ExamplesPanel projectId="p1" run={run} estimates={estimates} />)
    expect(await screen.findByText('Units 1 to 3 of 3')).toBeInTheDocument()
    expect(api.listUnits).toHaveBeenCalledWith(
      'p1',
      'swap',
      EXAMPLE_UNITS_PAGE,
      0,
    )
    const viewer = await screen.findByTestId('variant-unit-viewer')
    expect(api.getUnit).toHaveBeenCalledWith('p1', 'swap', 'u1', null)
    // x_second compares party = second against first.
    expect(within(viewer).getByTestId('unit-treated')).toHaveTextContent(
      'party = second',
    )
    expect(within(viewer).getAllByTestId('unit-span')[0]).toHaveTextContent(
      'Ida Brook',
    )
    expect(screen.getByRole('button', { name: 'u1' })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
    // Joint tests are no contrast to show examples of.
    expect(
      within(screen.getByTestId('examples-contrast')).getAllByRole('option'),
    ).toHaveLength(2)
  })

  it('picks units, systems and designs', async () => {
    const user = userEvent.setup()
    api.listUnits.mockResolvedValue(units(0, 3, 3))
    render(<ExamplesPanel projectId="p1" run={run} estimates={estimates} />)
    await screen.findByTestId('variant-unit-viewer')
    await user.click(screen.getByRole('button', { name: 'u2' }))
    await waitFor(() =>
      expect(api.getUnit).toHaveBeenLastCalledWith('p1', 'swap', 'u2', null),
    )
    await user.selectOptions(screen.getByTestId('examples-system'), SYSTEM_B)
    await waitFor(() =>
      expect(api.getUnit).toHaveBeenLastCalledWith(
        'p1',
        'swap',
        'u2',
        SYSTEM_B,
      ),
    )
    // The order contrast has no system scope: the system filter goes away.
    await user.selectOptions(
      screen.getByTestId('examples-contrast'),
      within(screen.getByTestId('examples-contrast')).getAllByRole('option')[1],
    )
    await waitFor(() =>
      expect(screen.queryByTestId('examples-system')).toBeNull(),
    )
    await user.selectOptions(screen.getByTestId('examples-design'), 'second')
    await waitFor(() =>
      expect(api.listUnits).toHaveBeenLastCalledWith(
        'p1',
        'second',
        EXAMPLE_UNITS_PAGE,
        0,
      ),
    )
  })

  it('pages through the units', async () => {
    const user = userEvent.setup()
    api.listUnits
      .mockResolvedValueOnce(units(0, EXAMPLE_UNITS_PAGE, 14))
      .mockResolvedValueOnce(units(EXAMPLE_UNITS_PAGE, 2, 14))
      .mockResolvedValueOnce(units(0, EXAMPLE_UNITS_PAGE, 14))
    render(<ExamplesPanel projectId="p1" run={run} estimates={estimates} />)
    expect(await screen.findByText('Units 1 to 12 of 14')).toBeInTheDocument()
    expect(screen.getByText('Previous')).toBeDisabled()
    await user.click(screen.getByText('Next'))
    expect(await screen.findByText('Units 13 to 14 of 14')).toBeInTheDocument()
    expect(screen.getByText('Next')).toBeDisabled()
    // The opened unit is not on this page: the page's first one opens.
    await waitFor(() =>
      expect(api.getUnit).toHaveBeenLastCalledWith('p1', 'swap', 'u13', null),
    )
    await user.click(screen.getByText('Previous'))
    expect(await screen.findByText('Units 1 to 12 of 14')).toBeInTheDocument()
  })

  it('says when the design has no units', async () => {
    api.listUnits.mockResolvedValue(units(0, 0, 0))
    render(<ExamplesPanel projectId="p1" run={run} estimates={estimates} />)
    expect(
      await screen.findByText('This design has no units yet.'),
    ).toBeInTheDocument()
    expect(screen.getByText('Units 0 to 0 of 0')).toBeInTheDocument()
    expect(api.getUnit).not.toHaveBeenCalled()
  })

  it('refuses viewers without full content rights', async () => {
    api.listUnits.mockRejectedValue({ response: { status: 403 } })
    api.listDesigns.mockRejectedValue({ response: { status: 403 } })
    render(<ExamplesPanel projectId="p1" run={run} estimates={estimates} />)
    expect(
      await screen.findByText(
        /Examples need the org admin or contributor role on the project/,
      ),
    ).toBeInTheDocument()
    expect(api.getUnit).not.toHaveBeenCalled()
  })

  it('reports other errors and renders nothing without designs or contrasts', async () => {
    api.listUnits.mockRejectedValue(new Error('boom'))
    const { rerender, container } = render(
      <ExamplesPanel projectId="p1" run={run} estimates={estimates} />,
    )
    expect(
      await screen.findByText('The units could not be loaded.'),
    ).toBeInTheDocument()
    rerender(<ExamplesPanel projectId="p1" run={run} estimates={[]} />)
    expect(container).toBeEmptyDOMElement()
    rerender(
      <ExamplesPanel
        projectId="p1"
        run={makeRun({ normalized_spec: {} })}
        estimates={estimates}
      />,
    )
    expect(container).toBeEmptyDOMElement()
  })
})

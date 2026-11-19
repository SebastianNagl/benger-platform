/**
 * The variant design panel: the factor tree, the hashes and their
 * comparison with a recorded hash, the checks on request, and the loader of
 * a project's designs.
 */

import '@testing-library/jest-dom'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { variantViewsAPI } from '@/lib/api/variantViews'
import { makeDesignRow } from '@/test-utils/variantViewFixtures'
import { VariantDesignPanel, VariantDesignsLoader } from '../VariantDesignPanel'

jest.mock('@/contexts/I18nContext', () =>
  require('@/test-utils/i18nMock').i18nMock('en'),
)

jest.mock('@/lib/api/variantViews', () => ({
  variantViewsAPI: { listDesigns: jest.fn(), checkDesign: jest.fn() },
}))

const api = variantViewsAPI as jest.Mocked<typeof variantViewsAPI>

const report = (ok: boolean) => ({
  content_hash: 'c'.repeat(64),
  report: {
    ok,
    task_count: 48,
    unit_count: 24,
    assignments: { ok: true, problem_count: 0, problems: [] },
    balance: { ok, problem_count: ok ? 0 : 2, problems: [] },
    invariance: { ok: true, problem_count: 0, problems: [], checked_pairs: 24 },
  },
})

beforeEach(() => jest.clearAllMocks())

describe('VariantDesignPanel', () => {
  it('shows the factor tree, status, hashes and bindings', () => {
    const design = makeDesignRow({
      spec: {
        ...makeDesignRow().spec,
        factors: [
          ...(makeDesignRow().spec.factors ?? []),
          {
            name: 'name_id',
            type: 'nominal',
            role: 'nuisance',
            source: 'structure',
            levels: Array.from({ length: 10 }, (_, i) => `n${i}`),
          },
          { name: 'free', type: 'text' },
        ],
        slots: {
          count: 6,
          factors: [{ name: 'pos', type: 'numeric', minimum: 1, maximum: 6 }],
        },
        outcomes: [{ name: 'risk' }],
      },
    })
    render(<VariantDesignPanel design={design} />)
    const tree = screen.getByTestId('design-factor-tree')
    expect(within(tree).getByText('Unit: case')).toBeInTheDocument()
    expect(within(tree).getByText('first, second')).toBeInTheDocument()
    expect(within(tree).getByText('0 … 100')).toBeInTheDocument()
    // party, free and the slot factor pos keep the defaults.
    expect(
      within(tree).getAllByText('manipulated · within units'),
    ).toHaveLength(3)
    expect(
      within(tree).getByText(
        'nuisance · within units · from the prompt structure',
      ),
    ).toBeInTheDocument()
    expect(within(tree).getByText(/n7 … \(10\)/)).toBeInTheDocument()
    expect(within(tree).getByText('Per slot (6 slots)')).toBeInTheDocument()
    expect(within(tree).getByText('1 … 6')).toBeInTheDocument()
    expect(within(tree).getByText('risk')).toBeInTheDocument()
    expect(within(tree).getByText('facts')).toBeInTheDocument()
    expect(screen.getByText('frozen')).toBeInTheDocument()
    expect(screen.getByText('48 tasks')).toBeInTheDocument()
    expect(screen.getByText('Name swap')).toBeInTheDocument()
    expect(screen.queryByTestId('design-hash-match')).toBeNull()
    expect(screen.queryByTestId('design-run-check')).toBeNull()
  })

  it('compares the content hash with a recorded one', () => {
    const { rerender } = render(
      <VariantDesignPanel
        design={makeDesignRow()}
        recordedHash={'c'.repeat(64)}
      />,
    )
    expect(screen.getByTestId('design-hash-match')).toBeInTheDocument()
    rerender(
      <VariantDesignPanel
        design={makeDesignRow()}
        recordedHash={'d'.repeat(64)}
      />,
    )
    expect(screen.getByTestId('design-hash-mismatch')).toBeInTheDocument()
  })

  it('runs the checks on request and shows a failure', async () => {
    const user = userEvent.setup()
    const onCheck = jest
      .fn()
      .mockResolvedValueOnce(report(false))
      .mockRejectedValueOnce(new Error('Server busy'))
      .mockRejectedValueOnce({})
    render(
      <VariantDesignPanel
        design={makeDesignRow({ status: 'odd', task_count: undefined })}
        onCheck={onCheck}
      />,
    )
    expect(screen.getByText('odd')).toBeInTheDocument()
    await user.click(screen.getByTestId('design-run-check'))
    const check = await screen.findByTestId('design-check')
    expect(check).toHaveTextContent('Assignments: passed')
    expect(check).toHaveTextContent('Balance: 2 problems')
    expect(check).toHaveTextContent(
      '48 tasks in 24 units, 24 twin pairs compared',
    )
    await user.click(screen.getByTestId('design-run-check'))
    expect(await screen.findByText('Server busy')).toBeInTheDocument()
    await user.click(screen.getByTestId('design-run-check'))
    expect(
      await screen.findByText('The checks could not be run.'),
    ).toBeInTheDocument()
  })
})

describe('VariantDesignsLoader', () => {
  it('loads the named designs and checks one', async () => {
    const user = userEvent.setup()
    api.listDesigns.mockResolvedValue([
      makeDesignRow(),
      makeDesignRow({ key: 'other', id: 'd2' }),
    ])
    api.checkDesign.mockResolvedValue(report(true))
    render(<VariantDesignsLoader projectId="p1" keys={['swap']} />)
    expect(screen.getByRole('status')).toHaveTextContent('Loading the designs…')
    const panels = await screen.findAllByTestId('variant-design-panel')
    expect(panels).toHaveLength(1)
    await user.click(screen.getByTestId('design-run-check'))
    expect(await screen.findByTestId('design-check')).toBeInTheDocument()
    expect(api.checkDesign).toHaveBeenCalledWith('p1', 'swap')
  })

  it('lists every design without keys and says when none is left', async () => {
    api.listDesigns.mockResolvedValueOnce([
      makeDesignRow(),
      makeDesignRow({ key: 'b' }),
    ])
    const { rerender } = render(<VariantDesignsLoader projectId="p1" />)
    expect(await screen.findAllByTestId('variant-design-panel')).toHaveLength(2)
    api.listDesigns.mockResolvedValueOnce([])
    rerender(<VariantDesignsLoader projectId="p2" keys={['gone']} />)
    expect(
      await screen.findByText(
        'The project has none of these designs any more.',
      ),
    ).toBeInTheDocument()
  })

  it('hides itself for viewers who may not read designs and reports errors', async () => {
    api.listDesigns.mockRejectedValueOnce({ response: { status: 403 } })
    const { container, rerender } = render(
      <VariantDesignsLoader projectId="p1" />,
    )
    await screen.findByText(() => false).catch(() => null)
    expect(container).toBeEmptyDOMElement()
    api.listDesigns.mockRejectedValueOnce(new Error('boom'))
    rerender(<VariantDesignsLoader projectId="p3" />)
    expect(
      await screen.findByText('The designs could not be loaded.'),
    ).toBeInTheDocument()
  })
})

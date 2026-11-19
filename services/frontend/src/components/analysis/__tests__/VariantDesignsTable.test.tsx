/**
 * The variant design table: rows with status, version, tasks and the frozen
 * content hash; Check and Freeze show exactly what the routes answered
 * (report, units, cells, the hash, a refusal with its report); the list is
 * read back after a freeze; import posts the chosen export document.
 */

import '@testing-library/jest-dom'
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react'

import { VariantDesignsTable } from '@/components/analysis/VariantDesignsTable'
import { makeDesign, makeDesignReport } from '@/test-utils/analysisFixtures'

jest.mock('@/contexts/I18nContext', () =>
  require('@/test-utils/i18nMock').i18nMock('en'),
)

const mockList = jest.fn()
const mockCheck = jest.fn()
const mockFreeze = jest.fn()
const mockImport = jest.fn()
jest.mock('@/lib/api/variantDesigns', () => ({
  ...jest.requireActual('@/lib/api/variantDesigns'),
  variantDesignsAPI: {
    list: (...a: unknown[]) => mockList(...a),
    check: (...a: unknown[]) => mockCheck(...a),
    freeze: (...a: unknown[]) => mockFreeze(...a),
    importDocument: (...a: unknown[]) => mockImport(...a),
  },
}))

const HASH = 'c0ffee' + '1'.repeat(58)
const DRAFT = makeDesign()
const FROZEN = makeDesign({
  id: 'design-2',
  key: 'docket',
  status: 'frozen',
  version: 2,
  content_hash: HASH,
  spec: { schema_version: 1 },
  task_count: 30,
})

const refusal = (status: number, detail: Record<string, unknown>) =>
  Object.assign(new Error(String(detail.message ?? status)), {
    response: { status, data: { detail } },
  })

const onDesignsChange = jest.fn()
const renderTable = () =>
  render(
    <VariantDesignsTable
      projectId="project-1"
      onDesignsChange={onDesignsChange}
    />,
  )

beforeEach(() => {
  jest.clearAllMocks()
  mockList.mockResolvedValue([DRAFT, FROZEN])
})

describe('VariantDesignsTable', () => {
  it('lists the designs with status, version, tasks and hash', async () => {
    renderTable()
    const draft = await screen.findByTestId('variant-design-role_swap')
    expect(draft).toHaveTextContent('role_swap')
    expect(draft).toHaveTextContent('Role swap')
    expect(draft).toHaveTextContent('Draft')
    expect(draft).toHaveTextContent('48')
    expect(
      within(draft).getByRole('button', { name: 'Freeze design role_swap' }),
    ).toBeVisible()

    const frozen = screen.getByTestId('variant-design-docket')
    expect(frozen).toHaveTextContent('Frozen')
    expect(within(frozen).getByTitle(HASH)).toHaveTextContent('c0ffee111111')
    // A frozen design cannot be frozen again.
    expect(
      within(frozen).queryByRole('button', { name: 'Freeze design docket' }),
    ).toBeNull()
    expect(onDesignsChange).toHaveBeenCalledWith([DRAFT, FROZEN])
    expect(mockList).toHaveBeenCalledWith('project-1')
  })

  it('says when there are no designs and when they cannot be read', async () => {
    mockList.mockResolvedValueOnce([])
    const { unmount } = renderTable()
    expect(
      await screen.findByText('No variant designs yet.'),
    ).toBeInTheDocument()
    unmount()

    mockList.mockRejectedValueOnce(new Error('403'))
    renderTable()
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'The variant designs could not be loaded.',
    )
  })

  it('shows the check report and the hash a freeze would record', async () => {
    mockCheck.mockResolvedValue({
      report: makeDesignReport(),
      content_hash: HASH,
    })
    renderTable()
    fireEvent.click(
      await screen.findByRole('button', { name: 'Check design role_swap' }),
    )
    const outcome = await screen.findByTestId(
      'variant-design-outcome-role_swap',
    )
    expect(mockCheck).toHaveBeenCalledWith('project-1', 'role_swap')
    expect(outcome).toHaveTextContent('Every check passed.')
    expect(outcome).toHaveTextContent('Units12')
    expect(outcome).toHaveTextContent('Cells per unit4')
    expect(outcome).toHaveTextContent('Pairs checked36')
    expect(outcome).toHaveTextContent('A freeze would record')
    expect(within(outcome).getByTitle(HASH)).toBeVisible()
    // A check changes nothing: the design stays a draft.
    expect(screen.getByTestId('variant-design-role_swap')).toHaveTextContent(
      'Draft',
    )
    expect(mockList).toHaveBeenCalledTimes(1)
  })

  it('lists the problems of a failed check', async () => {
    mockCheck.mockResolvedValue({
      report: makeDesignReport({
        ok: false,
        balance: {
          ok: false,
          problem_count: 2,
          problems: [
            { kind: 'missing_cell', message: 'unit u3 lacks cell (P, first)' },
            { kind: 'missing_cell', message: 'unit u7 lacks cell (D, last)' },
          ],
          expected_cells_per_unit: 4,
        },
      }),
      content_hash: HASH,
    })
    renderTable()
    fireEvent.click(
      await screen.findByRole('button', { name: 'Check design role_swap' }),
    )
    const outcome = await screen.findByTestId(
      'variant-design-outcome-role_swap',
    )
    expect(outcome).toHaveTextContent('Some checks failed.')
    expect(outcome).toHaveTextContent('Balance: 2 problems')
    expect(outcome).toHaveTextContent('Assignments: ok')
    expect(outcome).toHaveTextContent('unit u3 lacks cell (P, first)')
    expect(outcome).toHaveTextContent('unit u7 lacks cell (D, last)')
  })

  it('shows a refused check with the route message and problems', async () => {
    mockCheck.mockRejectedValue(
      refusal(422, {
        code: 'variant_design_invalid',
        message: "The variant design 'role_swap' is invalid.",
        problems: [{ path: '/factors/0/levels', message: 'must not be empty' }],
      }),
    )
    renderTable()
    fireEvent.click(
      await screen.findByRole('button', { name: 'Check design role_swap' }),
    )
    const outcome = await screen.findByTestId(
      'variant-design-outcome-role_swap',
    )
    expect(outcome).toHaveTextContent('The design is invalid.')
    expect(outcome).toHaveTextContent('/factors/0/levels: must not be empty')
  })

  it('shows the route message of a refusal it has no words of its own for', async () => {
    mockCheck.mockRejectedValue(
      refusal(409, {
        code: 'variant_design_hash_mismatch',
        message: 'The tasks do not hash to the recorded content hash.',
      }),
    )
    renderTable()
    fireEvent.click(
      await screen.findByRole('button', { name: 'Check design role_swap' }),
    )
    expect(
      await screen.findByTestId('variant-design-outcome-role_swap'),
    ).toHaveTextContent('The tasks do not hash to the recorded content hash.')
  })

  it('freezes after confirmation and reads the stored state back', async () => {
    const report = makeDesignReport()
    mockFreeze.mockResolvedValue({
      design: { ...DRAFT, status: 'frozen', content_hash: HASH, version: 1 },
      report,
    })
    renderTable()
    fireEvent.click(
      await screen.findByRole('button', { name: 'Freeze design role_swap' }),
    )
    expect(await screen.findByText('Freeze design role_swap?')).toBeVisible()
    mockList.mockResolvedValue([
      { ...DRAFT, status: 'frozen', content_hash: HASH },
      FROZEN,
    ])
    fireEvent.click(screen.getByRole('button', { name: 'Freeze' }))

    const outcome = await screen.findByTestId(
      'variant-design-outcome-role_swap',
    )
    expect(mockFreeze).toHaveBeenCalledWith('project-1', 'role_swap')
    expect(outcome).toHaveTextContent('The design is frozen.')
    expect(within(outcome).getByTitle(HASH)).toBeVisible()
    await waitFor(() =>
      expect(screen.getByTestId('variant-design-role_swap')).toHaveTextContent(
        'Frozen',
      ),
    )
    expect(mockList).toHaveBeenCalledTimes(2)
    expect(
      screen.queryByRole('button', { name: 'Freeze design role_swap' }),
    ).toBeNull()
  })

  it('keeps a design whose checks fail a draft and shows the report', async () => {
    mockFreeze.mockRejectedValue(
      refusal(409, {
        code: 'variant_design_checks_failed',
        message:
          "The variant design 'role_swap' fails its checks and stays a draft.",
        report: makeDesignReport({
          ok: false,
          invariance: {
            ok: false,
            problem_count: 1,
            problems: [
              {
                kind: 'span_changed',
                message: 'text outside the span differs',
              },
            ],
            checked_pairs: 36,
          },
        }),
      }),
    )
    renderTable()
    fireEvent.click(
      await screen.findByRole('button', { name: 'Freeze design role_swap' }),
    )
    fireEvent.click(await screen.findByRole('button', { name: 'Freeze' }))
    const outcome = await screen.findByTestId(
      'variant-design-outcome-role_swap',
    )
    expect(outcome).toHaveTextContent(
      'The design fails its checks and stays a draft.',
    )
    expect(outcome).toHaveTextContent('Invariance: 1 problem')
    expect(outcome).toHaveTextContent('text outside the span differs')
    expect(screen.getByTestId('variant-design-role_swap')).toHaveTextContent(
      'Draft',
    )
    expect(mockList).toHaveBeenCalledTimes(1)
  })

  it('reports a failed freeze without a refusal body', async () => {
    mockFreeze.mockRejectedValue(new Error(''))
    renderTable()
    fireEvent.click(
      await screen.findByRole('button', { name: 'Freeze design role_swap' }),
    )
    fireEvent.click(await screen.findByRole('button', { name: 'Freeze' }))
    expect(
      await screen.findByText('The design could not be frozen.'),
    ).toBeVisible()
  })

  const choose = (content: string) => {
    const input = screen.getByTestId('variant-design-import-input')
    const file = new File([content], 'design.json', {
      type: 'application/json',
    })
    Object.defineProperty(file, 'text', {
      value: () => Promise.resolve(content),
    })
    fireEvent.change(input, { target: { files: [file] } })
  }

  it('imports an export document as a draft and lists it', async () => {
    renderTable()
    await screen.findByTestId('variant-design-role_swap')
    const doc = {
      format: 'benger.variant_design.v1',
      key: 'new_design',
      spec: { schema_version: 1 },
    }
    mockImport.mockResolvedValue(makeDesign({ key: 'new_design' }))
    mockList.mockResolvedValue([
      DRAFT,
      FROZEN,
      makeDesign({ key: 'new_design' }),
    ])
    choose(JSON.stringify(doc))

    expect(
      await screen.findByText('Design new_design imported as a draft.'),
    ).toBeVisible()
    expect(mockImport).toHaveBeenCalledWith('project-1', doc)
    expect(await screen.findByTestId('variant-design-new_design')).toBeVisible()
  })

  it('refuses a file that is not JSON and shows an import refusal', async () => {
    renderTable()
    await screen.findByTestId('variant-design-role_swap')
    choose('{not json')
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'The file is not valid JSON',
    )
    expect(mockImport).not.toHaveBeenCalled()

    mockImport.mockRejectedValue(
      refusal(409, {
        code: 'variant_design_exists',
        message: "The project already has a variant design 'role_swap'.",
      }),
    )
    choose(JSON.stringify({ format: 'x', key: 'role_swap', spec: {} }))
    expect(
      await screen.findByText(
        'The project already has a design with this key.',
      ),
    ).toBeVisible()
  })

  it('lists the problems of a refused import and opens the file picker', async () => {
    renderTable()
    await screen.findByTestId('variant-design-role_swap')
    const input = screen.getByTestId(
      'variant-design-import-input',
    ) as HTMLInputElement
    const click = jest.spyOn(input, 'click').mockImplementation(() => {})
    fireEvent.click(screen.getByTestId('variant-design-import'))
    expect(click).toHaveBeenCalled()

    mockImport.mockRejectedValue(
      refusal(422, {
        code: 'variant_design_invalid',
        message: 'The variant design is invalid.',
        problems: [{ path: '/spec/unit', message: 'is required' }],
      }),
    )
    choose(JSON.stringify({ format: 'x', key: 'bad', spec: {} }))
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('The design is invalid.')
    expect(alert).toHaveTextContent('/spec/unit: is required')
  })
})

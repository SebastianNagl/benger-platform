/**
 * The start dialog: a blank form, the prefill from an earlier run of the
 * same project, the refusal of a run of another project or one that cannot
 * be read, and the plan picker (a saved plan's spec, name and hash; a run
 * started from it sends the plan's spec unchanged).
 */

import '@testing-library/jest-dom'
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react'

import { StartAnalysisDialog } from '@/components/analysis/StartAnalysisDialog'
import { makePlan, makeRun } from '@/test-utils/analysisFixtures'

jest.mock('@/contexts/I18nContext', () =>
  require('@/test-utils/i18nMock').i18nMock('en'),
)

const mockGetRun = jest.fn()
const mockDesigns = jest.fn()
const mockPlans = jest.fn()
const mockStartRun = jest.fn()
const mockValidate = jest.fn()
jest.mock('@/lib/api/analysis', () => ({
  ...jest.requireActual('@/lib/api/analysis'),
  analysisAPI: {
    getRun: (...a: unknown[]) => mockGetRun(...a),
    listDesignKeys: (...a: unknown[]) => mockDesigns(...a),
    listPlans: (...a: unknown[]) => mockPlans(...a),
    startRun: (...a: unknown[]) => mockStartRun(...a),
    validateSpec: (...a: unknown[]) => mockValidate(...a),
  },
}))

const onStarted = jest.fn()
const open = (fromRunId: string | null = null, planId: string | null = null) =>
  render(
    <StartAnalysisDialog
      isOpen
      onClose={jest.fn()}
      projectId="project-1"
      fromRunId={fromRunId}
      planId={planId}
      onStarted={onStarted}
    />,
  )

const PLAN = makePlan()
const OTHER_PLAN = makePlan({
  id: 'plan-2',
  name: 'Robustness check',
  spec: { spec_version: 1, name: 'Robustness', inputs: { designs: ['d'] } },
  spec_hash: 'f'.repeat(64),
  saved_at: null,
})

const specText = () =>
  (screen.getByLabelText('Analysis spec (JSON)') as HTMLTextAreaElement).value

beforeEach(() => {
  jest.clearAllMocks()
  mockDesigns.mockResolvedValue(['role_swap'])
  mockGetRun.mockResolvedValue(makeRun())
  mockPlans.mockResolvedValue([])
  mockStartRun.mockResolvedValue(makeRun({ id: 'run-new' }))
})

describe('StartAnalysisDialog', () => {
  it('opens a blank form and reads the design keys', async () => {
    open()
    const dialog = await screen.findByTestId('start-analysis-dialog')
    expect(within(dialog).getByTestId('new-analysis-run-form')).toBeVisible()
    await waitFor(() => expect(mockDesigns).toHaveBeenCalledWith('project-1'))
    expect(mockGetRun).not.toHaveBeenCalled()
  })

  it('prefills the spec and name of a run of the project', async () => {
    open('run-1')
    const name = (await screen.findByLabelText(
      'Name (optional)',
    )) as HTMLInputElement
    await waitFor(() => expect(name.value).toBe('Role swap'))
    expect(
      (screen.getByLabelText('Analysis spec (JSON)') as HTMLTextAreaElement)
        .value,
    ).toContain('"designs"')
  })

  it('refuses a run of another project and a run that cannot be read', async () => {
    mockGetRun.mockResolvedValue(makeRun({ project_id: 'other' }))
    const { unmount } = open('run-1')
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'The spec of that run could not be loaded.',
    )
    unmount()

    mockGetRun.mockRejectedValue(new Error('404'))
    open('run-1')
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'The spec of that run could not be loaded.',
    )
    // The form stays usable without the prefill.
    expect(screen.getByTestId('new-analysis-run-form')).toBeInTheDocument()
  })

  it('offers no picker without plans or an earlier run', async () => {
    open()
    await waitFor(() => expect(mockPlans).toHaveBeenCalledWith('project-1'))
    expect(screen.queryByLabelText('Source')).not.toBeInTheDocument()
  })

  it('prefills a preselected plan with its spec, name and hash', async () => {
    mockPlans.mockResolvedValue([PLAN, OTHER_PLAN])
    open(null, 'plan-1')
    const name = (await screen.findByLabelText(
      'Name (optional)',
    )) as HTMLInputElement
    expect(name.value).toBe('Primary analysis')
    expect(JSON.parse(specText())).toEqual(PLAN.spec)
    expect((screen.getByLabelText('Source') as HTMLSelectElement).value).toBe(
      'plan:plan-1',
    )
    expect(screen.getByTestId('start-analysis-plan-hash')).toHaveTextContent(
      'Plan spec hash a1b2c3d4e5f6, saved',
    )
  })

  it('starts the run with the plan spec unchanged', async () => {
    mockPlans.mockResolvedValue([PLAN])
    open(null, 'plan-1')
    fireEvent.click(await screen.findByTestId('new-analysis-run-start'))
    await waitFor(() =>
      expect(mockStartRun).toHaveBeenCalledWith(
        'project-1',
        PLAN.spec,
        'Primary analysis',
      ),
    )
    expect(onStarted).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'run-new' }),
    )
  })

  it('says whether a validated spec still matches the plan', async () => {
    mockPlans.mockResolvedValue([PLAN])
    mockValidate.mockResolvedValue({ spec_hash: PLAN.spec_hash })
    open(null, 'plan-1')
    fireEvent.click(await screen.findByRole('button', { name: 'Validate' }))
    expect(await screen.findByRole('status')).toHaveTextContent(
      'It matches the saved plan.',
    )

    mockValidate.mockResolvedValue({ spec_hash: '0'.repeat(64) })
    fireEvent.change(screen.getByLabelText('Analysis spec (JSON)'), {
      target: { value: '{"spec_version": 1}' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Validate' }))
    expect(await screen.findByRole('status')).toHaveTextContent(
      'It differs from the saved plan.',
    )
  })

  it('switches between plans, the earlier run and a blank spec', async () => {
    mockPlans.mockResolvedValue([PLAN, OTHER_PLAN])
    open('run-1')
    const picker = (await screen.findByLabelText('Source')) as HTMLSelectElement
    // The earlier run wins when the dialog opens with one.
    await waitFor(() => expect(picker.value).toBe('run'))
    await waitFor(() =>
      expect(
        (screen.getByLabelText('Name (optional)') as HTMLInputElement).value,
      ).toBe('Role swap'),
    )
    expect(
      within(picker)
        .getAllByRole('option')
        .map((o) => o.textContent),
    ).toEqual([
      'Plan: Primary analysis',
      'Plan: Robustness check',
      "The earlier run's spec",
      'A pasted spec',
    ])

    fireEvent.change(picker, { target: { value: 'plan:plan-2' } })
    expect(JSON.parse(specText())).toEqual(OTHER_PLAN.spec)
    expect(screen.getByTestId('start-analysis-plan-hash')).toHaveTextContent(
      'Plan spec hash ffffffffffff',
    )

    fireEvent.change(picker, { target: { value: 'blank' } })
    expect(specText()).toBe('')
    expect(
      screen.queryByTestId('start-analysis-plan-hash'),
    ).not.toBeInTheDocument()
  })

  it('names a preselected plan that no longer exists', async () => {
    mockPlans.mockResolvedValue([OTHER_PLAN])
    open(null, 'plan-1')
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'This plan no longer exists.',
    )
    expect(
      screen.queryByTestId('new-analysis-run-form'),
    ).not.toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Source'), {
      target: { value: 'blank' },
    })
    expect(screen.getByTestId('new-analysis-run-form')).toBeInTheDocument()
  })

  it('keeps the blank form when the plans cannot be read', async () => {
    mockPlans.mockRejectedValue(new Error('403'))
    open()
    expect(
      await screen.findByTestId('new-analysis-run-form'),
    ).toBeInTheDocument()
    expect(screen.queryByLabelText('Source')).not.toBeInTheDocument()
  })
})

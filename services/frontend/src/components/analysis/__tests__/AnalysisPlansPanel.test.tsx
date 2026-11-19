/**
 * The analysis plans panel: the stored plans with hash and save time, a new
 * plan and an edit saved on top of the plans as stored right before the
 * save (ids kept, nothing another editor saved is lost), the engine's
 * messages when the API refuses a plan, deletion and the start callback.
 */

import '@testing-library/jest-dom'
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react'

import { AnalysisPlansPanel } from '@/components/analysis/AnalysisPlansPanel'
import { makePlan } from '@/test-utils/analysisFixtures'

jest.mock('@/contexts/I18nContext', () =>
  require('@/test-utils/i18nMock').i18nMock('en'),
)

const mockListPlans = jest.fn()
const mockSavePlans = jest.fn()
jest.mock('@/lib/api/analysis', () => ({
  ...jest.requireActual('@/lib/api/analysis'),
  analysisAPI: {
    listPlans: (...a: unknown[]) => mockListPlans(...a),
    savePlans: (...a: unknown[]) => mockSavePlans(...a),
    validateSpec: jest.fn(),
  },
}))

const PLAN = makePlan()
const SPEC = { spec_version: 1, name: 'New', inputs: { designs: ['d'] } }

const onStartPlan = jest.fn()
const onPlansChange = jest.fn()
const renderPanel = () =>
  render(
    <AnalysisPlansPanel
      projectId="project-1"
      designKeys={['role_swap']}
      onStartPlan={onStartPlan}
      onPlansChange={onPlansChange}
    />,
  )

const fillEditor = (name: string, spec: unknown) => {
  const editor = screen.getByTestId('analysis-plan-editor')
  fireEvent.change(within(editor).getByLabelText('Plan name'), {
    target: { value: name },
  })
  fireEvent.change(within(editor).getByLabelText('Analysis spec (JSON)'), {
    target: { value: JSON.stringify(spec) },
  })
  return editor
}

beforeEach(() => {
  jest.clearAllMocks()
  mockListPlans.mockResolvedValue([PLAN])
})

describe('AnalysisPlansPanel', () => {
  it('lists the stored plans with hash and save time', async () => {
    renderPanel()
    const row = await screen.findByTestId('analysis-plan-plan-1')
    expect(row).toHaveTextContent('Primary analysis')
    expect(row).toHaveTextContent('Spec hash')
    expect(within(row).getByTitle(PLAN.spec_hash)).toHaveTextContent(
      'a1b2c3d4e5f6',
    )
    expect(row).toHaveTextContent('saved')
    expect(mockListPlans).toHaveBeenCalledWith('project-1')
    expect(onPlansChange).toHaveBeenCalledWith([PLAN])
  })

  it('says when there are no plans and when they cannot be read', async () => {
    mockListPlans.mockResolvedValueOnce([])
    const { unmount } = renderPanel()
    expect(
      await screen.findByText('No analysis plans yet.'),
    ).toBeInTheDocument()
    unmount()

    mockListPlans.mockRejectedValueOnce(new Error('403'))
    renderPanel()
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'The analysis plans could not be loaded.',
    )
  })

  it('saves a new plan after the plans stored right before the save', async () => {
    const concurrent = makePlan({ id: 'plan-9', name: 'Saved meanwhile' })
    renderPanel()
    await screen.findByTestId('analysis-plan-plan-1')
    mockListPlans.mockResolvedValueOnce([PLAN, concurrent])
    const created = makePlan({ id: 'plan-new', name: 'Second', spec: SPEC })
    mockSavePlans.mockResolvedValue([PLAN, concurrent, created])

    fireEvent.click(screen.getByTestId('analysis-plan-new'))
    const editor = fillEditor('  Second ', SPEC)
    fireEvent.click(within(editor).getByTestId('analysis-plan-save'))

    await waitFor(() =>
      expect(mockSavePlans).toHaveBeenCalledWith('project-1', [
        { id: 'plan-1', name: PLAN.name, spec: PLAN.spec },
        { id: 'plan-9', name: 'Saved meanwhile', spec: concurrent.spec },
        { name: 'Second', spec: SPEC },
      ]),
    )
    expect(await screen.findByTestId('analysis-plan-plan-new')).toBeVisible()
    expect(screen.getByTestId('analysis-plan-plan-9')).toBeVisible()
    await waitFor(() =>
      expect(
        screen.queryByTestId('analysis-plan-editor'),
      ).not.toBeInTheDocument(),
    )
  })

  it('needs a name before a plan can be saved', async () => {
    renderPanel()
    await screen.findByTestId('analysis-plan-plan-1')
    fireEvent.click(screen.getByTestId('analysis-plan-new'))
    const editor = fillEditor('   ', SPEC)
    expect(within(editor).getByTestId('analysis-plan-save')).toBeDisabled()
  })

  it('edits a plan in place and keeps its id', async () => {
    renderPanel()
    await screen.findByTestId('analysis-plan-plan-1')
    mockSavePlans.mockResolvedValue([makePlan({ name: 'Renamed' })])

    fireEvent.click(
      screen.getByRole('button', { name: 'Edit plan Primary analysis' }),
    )
    const editor = screen.getByTestId('analysis-plan-editor')
    expect(
      (within(editor).getByLabelText('Plan name') as HTMLInputElement).value,
    ).toBe('Primary analysis')
    expect(
      JSON.parse(
        (
          within(editor).getByLabelText(
            'Analysis spec (JSON)',
          ) as HTMLTextAreaElement
        ).value,
      ),
    ).toEqual(PLAN.spec)
    fireEvent.change(within(editor).getByLabelText('Plan name'), {
      target: { value: 'Renamed' },
    })
    fireEvent.click(within(editor).getByTestId('analysis-plan-save'))

    await waitFor(() =>
      expect(mockSavePlans).toHaveBeenCalledWith('project-1', [
        { id: 'plan-1', name: 'Renamed', spec: PLAN.spec },
      ]),
    )
    expect(await screen.findByText('Renamed')).toBeVisible()
  })

  it('saves an edited plan that was deleted meanwhile as a plan again', async () => {
    renderPanel()
    await screen.findByTestId('analysis-plan-plan-1')
    mockListPlans.mockResolvedValueOnce([])
    mockSavePlans.mockResolvedValue([PLAN])
    fireEvent.click(
      screen.getByRole('button', { name: 'Edit plan Primary analysis' }),
    )
    fireEvent.click(screen.getByTestId('analysis-plan-save'))
    await waitFor(() =>
      expect(mockSavePlans).toHaveBeenCalledWith('project-1', [
        { id: 'plan-1', name: PLAN.name, spec: PLAN.spec },
      ]),
    )
  })

  it('shows the engine messages of a refused plan and keeps the editor open', async () => {
    renderPanel()
    await screen.findByTestId('analysis-plan-plan-1')
    const refusal = Object.assign(new Error('422'), {
      response: {
        status: 422,
        data: {
          detail: {
            code: 'invalid_analysis_plan',
            message: 'An analysis plan is invalid',
            errors: [
              "/analysis_plans/1/spec/measures/x/expr: unknown function 'open'",
            ],
          },
        },
      },
    })
    mockSavePlans.mockRejectedValue(refusal)

    fireEvent.click(screen.getByTestId('analysis-plan-new'))
    const editor = fillEditor('Broken', SPEC)
    fireEvent.click(within(editor).getByTestId('analysis-plan-save'))

    const errors = await within(editor).findByTestId('new-analysis-run-errors')
    expect(errors).toHaveTextContent(
      "/analysis_plans/1/spec/measures/x/expr: unknown function 'open'",
    )
    expect(screen.getByTestId('analysis-plan-editor')).toBeVisible()
    expect(screen.queryByTestId('analysis-plan-plan-new')).toBeNull()
  })

  it('deletes a plan after confirmation', async () => {
    renderPanel()
    await screen.findByTestId('analysis-plan-plan-1')
    mockSavePlans.mockResolvedValue([])

    fireEvent.click(
      screen.getByRole('button', { name: 'Delete plan Primary analysis' }),
    )
    expect(
      await screen.findByText('Delete plan Primary analysis?'),
    ).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }))

    await waitFor(() =>
      expect(mockSavePlans).toHaveBeenCalledWith('project-1', []),
    )
    expect(
      await screen.findByText('No analysis plans yet.'),
    ).toBeInTheDocument()
    expect(onPlansChange).toHaveBeenLastCalledWith([])
  })

  it('reports a failed delete', async () => {
    renderPanel()
    await screen.findByTestId('analysis-plan-plan-1')
    mockSavePlans.mockRejectedValue(new Error('Network down'))
    fireEvent.click(
      screen.getByRole('button', { name: 'Delete plan Primary analysis' }),
    )
    fireEvent.click(await screen.findByRole('button', { name: 'Delete' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Network down')
    expect(screen.getByTestId('analysis-plan-plan-1')).toBeVisible()
  })

  it('starts a run from a plan through the host', async () => {
    renderPanel()
    fireEvent.click(
      await screen.findByRole('button', {
        name: 'Start a run from plan Primary analysis',
      }),
    )
    expect(onStartPlan).toHaveBeenCalledWith('plan-1')
  })
})

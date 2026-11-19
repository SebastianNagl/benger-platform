/**
 * The Analyses part of the Evaluation card: designs and plans side by side,
 * a run started from a saved plan (the dialog opens with that plan and
 * sends its spec), the evaluations page's Analyses view opened on the new
 * run, and the counts the host shows in its badge.
 */

import '@testing-library/jest-dom'
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react'

import { ProjectAnalysesSection } from '@/components/analysis/ProjectAnalysesSection'
import { makeDesign, makePlan, makeRun } from '@/test-utils/analysisFixtures'

jest.mock('@/contexts/I18nContext', () =>
  require('@/test-utils/i18nMock').i18nMock('en'),
)

const mockPush = jest.fn()
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
}))

const mockListPlans = jest.fn()
const mockStartRun = jest.fn()
jest.mock('@/lib/api/analysis', () => ({
  ...jest.requireActual('@/lib/api/analysis'),
  analysisAPI: {
    listPlans: (...a: unknown[]) => mockListPlans(...a),
    listDesignKeys: () => Promise.resolve(['role_swap']),
    startRun: (...a: unknown[]) => mockStartRun(...a),
    getRun: jest.fn(),
    savePlans: jest.fn(),
    validateSpec: jest.fn(),
  },
}))

const mockListDesigns = jest.fn()
jest.mock('@/lib/api/variantDesigns', () => ({
  ...jest.requireActual('@/lib/api/variantDesigns'),
  variantDesignsAPI: {
    list: (...a: unknown[]) => mockListDesigns(...a),
    check: jest.fn(),
    freeze: jest.fn(),
    importDocument: jest.fn(),
  },
}))

const PLAN = makePlan()
const onSummaryChange = jest.fn()

beforeEach(() => {
  jest.clearAllMocks()
  mockListPlans.mockResolvedValue([PLAN])
  mockListDesigns.mockResolvedValue([makeDesign()])
  mockStartRun.mockResolvedValue(makeRun({ id: 'run-from-plan' }))
})

describe('ProjectAnalysesSection', () => {
  it('starts a run from a saved plan and opens it on the evaluations page', async () => {
    render(
      <ProjectAnalysesSection
        projectId="project-1"
        onSummaryChange={onSummaryChange}
      />,
    )
    expect(await screen.findByTestId('variant-design-role_swap')).toBeVisible()
    fireEvent.click(
      await screen.findByRole('button', {
        name: 'Start a run from plan Primary analysis',
      }),
    )
    const dialog = await screen.findByTestId('start-analysis-dialog')
    await waitFor(() =>
      expect(
        (within(dialog).getByLabelText('Source') as HTMLSelectElement).value,
      ).toBe('plan:plan-1'),
    )
    fireEvent.click(within(dialog).getByTestId('new-analysis-run-start'))

    await waitFor(() =>
      expect(mockStartRun).toHaveBeenCalledWith(
        'project-1',
        PLAN.spec,
        PLAN.name,
      ),
    )
    expect(mockPush).toHaveBeenCalledWith(
      '/evaluations?projectId=project-1&type=analysis&run=run-from-plan',
    )
    expect(onSummaryChange).toHaveBeenLastCalledWith({ designs: 1, plans: 1 })
    expect(
      screen.getByText('Start a run from a saved plan or a pasted spec.'),
    ).toBeVisible()
  })

  it('opens a blank start dialog and says a design is needed first', async () => {
    mockListDesigns.mockResolvedValue([])
    mockListPlans.mockResolvedValue([])
    render(
      <ProjectAnalysesSection
        projectId="project-1"
        onSummaryChange={onSummaryChange}
      />,
    )
    expect(
      await screen.findByText(
        'An analysis reads the tasks of a variant design. Import one first.',
      ),
    ).toBeVisible()
    await waitFor(() =>
      expect(onSummaryChange).toHaveBeenLastCalledWith({
        designs: 0,
        plans: 0,
      }),
    )
    fireEvent.click(screen.getByTestId('project-analyses-start'))
    const dialog = await screen.findByTestId('start-analysis-dialog')
    expect(within(dialog).queryByLabelText('Source')).toBeNull()
    expect(
      (
        within(dialog).getByLabelText(
          'Analysis spec (JSON)',
        ) as HTMLTextAreaElement
      ).value,
    ).toBe('')
  })
})

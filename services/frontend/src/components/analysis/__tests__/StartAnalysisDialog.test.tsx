/**
 * The start dialog: a blank form, the prefill from an earlier run of the
 * same project, and the refusal of a run of another project or one that
 * cannot be read.
 */

import '@testing-library/jest-dom'
import { render, screen, waitFor, within } from '@testing-library/react'

import { StartAnalysisDialog } from '@/components/analysis/StartAnalysisDialog'
import { makeRun } from '@/test-utils/analysisFixtures'

jest.mock('@/contexts/I18nContext', () =>
  require('@/test-utils/i18nMock').i18nMock('en'),
)

const mockGetRun = jest.fn()
const mockDesigns = jest.fn()
jest.mock('@/lib/api/analysis', () => ({
  ...jest.requireActual('@/lib/api/analysis'),
  analysisAPI: {
    getRun: (...a: unknown[]) => mockGetRun(...a),
    listDesignKeys: (...a: unknown[]) => mockDesigns(...a),
  },
}))

const open = (fromRunId: string | null = null) =>
  render(
    <StartAnalysisDialog
      isOpen
      onClose={jest.fn()}
      projectId="project-1"
      fromRunId={fromRunId}
      onStarted={jest.fn()}
    />,
  )

beforeEach(() => {
  jest.clearAllMocks()
  mockDesigns.mockResolvedValue(['role_swap'])
  mockGetRun.mockResolvedValue(makeRun())
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
})

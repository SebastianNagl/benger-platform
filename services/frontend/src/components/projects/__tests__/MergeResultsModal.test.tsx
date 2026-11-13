/**
 * @jest-environment jsdom
 */

import { MergeResultsModal } from '@/components/projects/MergeResultsModal'
import { useToast } from '@/components/shared/Toast'
import { projectsAPI } from '@/lib/api/projects'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

jest.mock('@/components/shared/Toast', () => ({
  useToast: jest.fn(),
}))

jest.mock('@/lib/api/projects', () => ({
  projectsAPI: {
    runMergeImportJob: jest.fn(),
  },
}))

jest.mock('@/contexts/I18nContext', () =>
  require('@/test-utils/i18nMock').i18nMock('en'),
)

const file = new File(['{}'], 'copy.ndjson', { type: 'application/x-ndjson' })

function renderModal(onMergeComplete = jest.fn()) {
  render(
    <MergeResultsModal
      isOpen
      onClose={jest.fn()}
      projectId="proj-1"
      onMergeComplete={onMergeComplete}
    />,
  )
  return onMergeComplete
}

function chooseFile() {
  fireEvent.change(screen.getByTestId('merge-results-file'), {
    target: { files: [file] },
  })
}

describe('MergeResultsModal', () => {
  const addToast = jest.fn()

  beforeEach(() => {
    jest.clearAllMocks()
    ;(useToast as jest.Mock).mockReturnValue({ addToast })
  })

  it('needs a file before it can merge', () => {
    renderModal()
    expect(screen.getByTestId('merge-results-submit')).toBeDisabled()
    chooseFile()
    expect(screen.getByTestId('merge-results-submit')).toBeEnabled()
  })

  it('sends the model id map and shows what was added and skipped', async () => {
    ;(projectsAPI.runMergeImportJob as jest.Mock).mockResolvedValue({
      status: 'completed',
      result: {
        statistics: {
          matched_tasks: 2,
          added_counts: { generations: 2, evaluations: 1, task_evaluations: 2 },
          skipped_present_counts: { generations: 4, evaluations: 1 },
          models_added_to_project: ['custom-prod'],
        },
      },
    })
    const onMergeComplete = renderModal()
    chooseFile()
    fireEvent.click(screen.getByTestId('merge-add-model'))
    fireEvent.change(screen.getByTestId('merge-model-source-0'), {
      target: { value: ' custom-local ' },
    })
    fireEvent.change(screen.getByTestId('merge-model-target-0'), {
      target: { value: 'custom-prod' },
    })
    fireEvent.click(screen.getByTestId('merge-results-submit'))

    await waitFor(() =>
      expect(screen.getByTestId('merge-results-summary')).toBeInTheDocument(),
    )
    expect(projectsAPI.runMergeImportJob).toHaveBeenCalledWith(
      'proj-1',
      file,
      undefined,
      { modelIdMap: { 'custom-local': 'custom-prod' } },
    )
    const summary = screen.getByTestId('merge-results-summary').textContent
    expect(summary).toContain('Matched 2 tasks')
    expect(summary).toContain('Skipped 4 generations')
    expect(summary).toContain('custom-prod')
    expect(onMergeComplete).toHaveBeenCalled()
    expect(addToast).toHaveBeenCalledWith('Results merged', 'success')
  })

  it('blocks a half-filled model row', () => {
    renderModal()
    chooseFile()
    fireEvent.click(screen.getByTestId('merge-add-model'))
    fireEvent.change(screen.getByTestId('merge-model-source-0'), {
      target: { value: 'custom-local' },
    })
    expect(screen.getByTestId('merge-results-submit')).toBeDisabled()
  })

  it('explains a refused merge of foreign tasks', async () => {
    ;(projectsAPI.runMergeImportJob as jest.Mock).mockRejectedValue(
      new Error('409: merge_task_mismatch: Of the 3 tasks in the export, ...'),
    )
    const onMergeComplete = renderModal()
    chooseFile()
    fireEvent.click(screen.getByTestId('merge-results-submit'))

    await waitFor(() =>
      expect(screen.getByTestId('merge-results-error')).toHaveTextContent(
        "this project's tasks, so nothing was imported",
      ),
    )
    expect(onMergeComplete).not.toHaveBeenCalled()
  })
})

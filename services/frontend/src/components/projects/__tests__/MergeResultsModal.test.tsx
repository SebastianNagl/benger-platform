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
    uploadImportFile: jest.fn(),
    previewMergeImport: jest.fn(),
    runMergeImportJob: jest.fn(),
  },
}))

jest.mock('@/contexts/I18nContext', () =>
  require('@/test-utils/i18nMock').i18nMock('en'),
)

const file = new File(['{}'], 'copy.ndjson', { type: 'application/x-ndjson' })

const preview = {
  matched_tasks: 2,
  added_counts: { generations: 2, evaluations: 1, task_evaluations: 2 },
  skipped_present_counts: { generations: 4, evaluations: 1 },
  models_added_to_project: [],
  models: [
    {
      source_model_id: 'custom-local',
      model_id: 'custom-local',
      mapped: false,
      known: false,
      name: null,
      rows_added: 3,
      rows_present: 0,
    },
    {
      source_model_id: 'gpt-4o',
      model_id: 'gpt-4o',
      mapped: false,
      known: true,
      name: 'GPT-4o',
      rows_added: 0,
      rows_present: 4,
    },
  ],
  unknown_models: ['custom-local'],
  available_models: [
    { id: 'gpt-4o', name: 'GPT-4o', is_custom: false },
    { id: 'custom-prod', name: 'Qwen3 (prod)', is_custom: true },
  ],
}

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

async function checkFile() {
  chooseFile()
  fireEvent.click(screen.getByTestId('merge-results-check'))
  await waitFor(() =>
    expect(screen.getByTestId('merge-preview')).toBeInTheDocument(),
  )
}

describe('MergeResultsModal', () => {
  const addToast = jest.fn()

  beforeEach(() => {
    jest.clearAllMocks()
    ;(useToast as jest.Mock).mockReturnValue({ addToast })
    ;(projectsAPI.uploadImportFile as jest.Mock).mockResolvedValue(
      'imports/2026/11/proj-1/copy.ndjson',
    )
    ;(projectsAPI.previewMergeImport as jest.Mock).mockResolvedValue(preview)
  })

  it('needs a file before it can check it', () => {
    renderModal()
    expect(screen.getByTestId('merge-results-check')).toBeDisabled()
    chooseFile()
    expect(screen.getByTestId('merge-results-check')).toBeEnabled()
  })

  it('lists the models of the file and blocks the merge until unknown ones are mapped', async () => {
    renderModal()
    await checkFile()
    expect(projectsAPI.previewMergeImport).toHaveBeenCalledWith(
      'proj-1',
      'imports/2026/11/proj-1/copy.ndjson',
    )
    const previewText = screen.getByTestId('merge-preview').textContent
    expect(previewText).toContain('custom-local')
    expect(previewText).toContain('Keep: GPT-4o')
    expect(previewText).toContain('does not exist here')
    expect(screen.getByTestId('merge-results-submit')).toBeDisabled()

    fireEvent.change(screen.getByTestId('merge-model-target-0'), {
      target: { value: 'custom-prod' },
    })
    expect(screen.getByTestId('merge-results-submit')).toBeEnabled()
  })

  it('merges the uploaded file with the chosen map and names the added models', async () => {
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
    await checkFile()
    fireEvent.change(screen.getByTestId('merge-model-target-0'), {
      target: { value: 'custom-prod' },
    })
    fireEvent.click(screen.getByTestId('merge-results-submit'))

    await waitFor(() =>
      expect(screen.getByTestId('merge-results-summary')).toBeInTheDocument(),
    )
    // The file was uploaded once, for the check, and is merged from there.
    expect(projectsAPI.uploadImportFile).toHaveBeenCalledTimes(1)
    expect(projectsAPI.runMergeImportJob).toHaveBeenCalledWith(
      'proj-1',
      file,
      undefined,
      {
        modelIdMap: { 'custom-local': 'custom-prod' },
        objectKey: 'imports/2026/11/proj-1/copy.ndjson',
      },
    )
    const summary = screen.getByTestId('merge-results-summary').textContent
    expect(summary).toContain('Matched 2 tasks')
    expect(summary).toContain('Skipped 4 generations')
    // The name, not the raw custom id.
    expect(summary).toContain('Qwen3 (prod)')
    expect(summary).not.toContain('custom-prod')
    expect(onMergeComplete).toHaveBeenCalled()
    expect(addToast).toHaveBeenCalledWith('Results merged', 'success')
  })

  it('explains a file of foreign tasks at the check', async () => {
    const error: any = new Error('Of the 3 tasks in the export, ...')
    error.response = {
      status: 409,
      data: { detail: { code: 'merge_task_mismatch', message: '...' } },
    }
    ;(projectsAPI.previewMergeImport as jest.Mock).mockRejectedValue(error)
    const onMergeComplete = renderModal()
    chooseFile()
    fireEvent.click(screen.getByTestId('merge-results-check'))

    await waitFor(() =>
      expect(screen.getByTestId('merge-results-error')).toHaveTextContent(
        "this project's tasks, so nothing was imported",
      ),
    )
    expect(screen.queryByTestId('merge-results-submit')).not.toBeInTheDocument()
    expect(onMergeComplete).not.toHaveBeenCalled()
  })

  it('explains a merge refused for unknown models', async () => {
    const error: any = new Error('1 model id(s) of the export do not exist')
    error.code = 'merge_unknown_models'
    ;(projectsAPI.runMergeImportJob as jest.Mock).mockRejectedValue(error)
    renderModal()
    await checkFile()
    fireEvent.change(screen.getByTestId('merge-model-target-0'), {
      target: { value: 'custom-prod' },
    })
    fireEvent.click(screen.getByTestId('merge-results-submit'))

    await waitFor(() =>
      expect(screen.getByTestId('merge-results-error')).toHaveTextContent(
        'Some model ids of the file do not exist here',
      ),
    )
  })
})

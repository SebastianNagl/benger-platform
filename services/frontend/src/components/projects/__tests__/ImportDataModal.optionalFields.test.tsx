/**
 * @jest-environment jsdom
 *
 * Optional data bindings in the project-page import dialog.
 *
 * The exam template binds `$bearbeitervermerk` and `$zusatzmaterial` as side
 * props of the Angabe tag; both parts are optional, and the "Klausur
 * erfassen" form leaves them out of the task when they are empty. The
 * dialog used to treat every `$name` in the labeling config as required,
 * so such an exam stopped at a validation error, and "Trotzdem importieren"
 * re-ran the same check and never imported anything.
 */

import { ImportDataModal } from '@/components/projects/ImportDataModal'
import { useToast } from '@/components/shared/Toast'
import { useProgress } from '@/contexts/ProgressContext'
import { projectsAPI } from '@/lib/api/projects'
import { useProjectStore } from '@/stores/projectStore'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

jest.mock('@/contexts/ProgressContext', () => ({
  useProgress: jest.fn(),
}))

jest.mock('@/components/shared/Toast', () => ({
  useToast: jest.fn(),
}))

jest.mock('@/lib/api/projects', () => ({
  projectsAPI: {
    runNestedImportJob: jest.fn(),
  },
}))

jest.mock('@/stores/projectStore', () => ({
  useProjectStore: jest.fn(),
}))

jest.mock('@/components/projects/import/CloudImportPanel', () => ({
  CloudImportPanel: () => <div data-testid="cloud-import-panel-stub" />,
}))

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, params?: Record<string, unknown>) =>
      params ? `${key} ${JSON.stringify(params)}` : key,
    locale: 'de',
  }),
}))

jest.mock('@/components/tasks/ImportPreviewWithMapping', () => ({
  ImportPreviewWithMapping: ({ file, templateFields }: any) => (
    <div data-testid="import-preview">
      <span data-testid="import-preview-file">{file ? file.name : ''}</span>
      <span data-testid="import-preview-fields">
        {(templateFields ?? []).join(',')}
      </span>
    </div>
  ),
}))

const EXAM_CONFIG = `<View>
  <Header value="Angabe"/>
  <Angabe name="angabe" value="$sachverhalt" toName="sachverhalt"
          bearbeitervermerk="$bearbeitervermerk"
          zusatzmaterial="$zusatzmaterial"
          linkedTo="gliederung">
    <Label value="Wichtig" background="#fef08a"/>
  </Angabe>
  <Header value="Lösung"/>
  <Loesung name="loesung" toName="sachverhalt" linkedTo="gliederung"
           required="true"/>
</View>`

const TEXT_CONFIG = `<View>
  <Text name="text" value="$text"/>
  <TextArea name="answer" toName="text"/>
</View>`

async function uploadedImportEnvelope(callIndex = 0): Promise<any> {
  const call = (projectsAPI.runNestedImportJob as jest.Mock).mock.calls[
    callIndex
  ]
  return JSON.parse(await (call[1] as File).text())
}

describe('ImportDataModal - optional data bindings', () => {
  const mockFetchProject = jest.fn()
  const mockAddToast = jest.fn()

  const props = {
    isOpen: true,
    onClose: jest.fn(),
    projectId: 'p1',
    onImportComplete: jest.fn(),
  }

  beforeEach(() => {
    jest.clearAllMocks()
    ;(useToast as jest.Mock).mockReturnValue({ addToast: mockAddToast })
    ;(useProgress as jest.Mock).mockReturnValue({
      startProgress: jest.fn(),
      updateProgress: jest.fn(),
      completeProgress: jest.fn(),
    })
    ;(useProjectStore as jest.Mock).mockReturnValue({
      fetchProject: mockFetchProject,
    })
    ;(projectsAPI.runNestedImportJob as jest.Mock).mockResolvedValue({
      job_id: 'job-1',
      status: 'completed',
      result: { created_tasks: 1 },
    })
  })

  async function pasteAndImport(data: unknown) {
    const user = userEvent.setup()
    render(<ImportDataModal {...props} />)
    await waitFor(() => expect(mockFetchProject).toHaveBeenCalled())
    await user.click(screen.getByText('dataImport.tabs.paste'))
    fireEvent.change(
      screen.getByPlaceholderText(
        'projects.creation.wizard.step2.paste.placeholder',
      ),
      { target: { value: JSON.stringify(data) } },
    )
    await user.click(
      screen.getByRole('button', { name: 'projects.data.import' }),
    )
    return user
  }

  it('imports an exam without the optional Bearbeitervermerk and Zusatzmaterial', async () => {
    mockFetchProject.mockResolvedValue({ id: 'p1', label_config: EXAM_CONFIG })

    await pasteAndImport([{ sachverhalt: 'SV', musterloesung: 'ML' }])

    await waitFor(() =>
      expect(projectsAPI.runNestedImportJob).toHaveBeenCalledTimes(1),
    )
    expect((await uploadedImportEnvelope()).data).toEqual([
      { data: { sachverhalt: 'SV', musterloesung: 'ML' } },
    ])
    expect(
      screen.queryByText('tasks.importModal.validationError'),
    ).not.toBeInTheDocument()
  })

  it('lists the expected field as required and the side bindings as optional', async () => {
    mockFetchProject.mockResolvedValue({ id: 'p1', label_config: EXAM_CONFIG })

    render(<ImportDataModal {...props} />)

    const required = await screen.findByTestId('import-required-fields')
    expect(required).toHaveTextContent('$sachverhalt')
    expect(required).not.toHaveTextContent('bearbeitervermerk')
    expect(screen.getByTestId('import-optional-fields')).toHaveTextContent(
      'tasks.importModal.optionalFields {"fields":"$bearbeitervermerk, $zusatzmaterial"}',
    )
  })

  it('still stops at the validation error when the main value binding is missing', async () => {
    mockFetchProject.mockResolvedValue({ id: 'p1', label_config: TEXT_CONFIG })

    await pasteAndImport([{ content: 'x' }])

    expect(
      await screen.findByText(
        'Validation error - These fields are not present in the data: text',
      ),
    ).toBeInTheDocument()
    expect(projectsAPI.runNestedImportJob).not.toHaveBeenCalled()
  })

  it('"Trotzdem importieren" imports the data as it is', async () => {
    mockFetchProject.mockResolvedValue({ id: 'p1', label_config: TEXT_CONFIG })

    const user = await pasteAndImport([{ content: 'x' }])
    await user.click(
      await screen.findByRole('button', {
        name: 'tasks.importModal.importAnyway',
      }),
    )

    await waitFor(() =>
      expect(projectsAPI.runNestedImportJob).toHaveBeenCalledTimes(1),
    )
    expect((await uploadedImportEnvelope()).data).toEqual([
      { data: { content: 'x' } },
    ])
    expect(props.onImportComplete).toBeDefined()
    await waitFor(() => expect(props.onClose).toHaveBeenCalled())
  })

  it('gives the field mapping the pasted data as a file', async () => {
    mockFetchProject.mockResolvedValue({ id: 'p1', label_config: TEXT_CONFIG })

    await pasteAndImport([{ content: 'x' }])

    expect(await screen.findByTestId('import-preview-file')).toHaveTextContent(
      /\.json$/,
    )
    expect(screen.getByTestId('import-preview-fields')).toHaveTextContent(
      'text',
    )
  })
})

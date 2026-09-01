/**
 * Tests for the shared ImportSourceTabs component and its kind-aware
 * tab-order helper getImportTabConfig.
 */

/**
 * @jest-environment jsdom
 */

import '@testing-library/jest-dom'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ImportSourceTabs, getImportTabConfig } from '../ImportSourceTabs'

const mockAddToast = jest.fn()

jest.mock('@/components/shared/Toast', () => ({
  useToast: () => ({ addToast: mockAddToast }),
}))

jest.mock('@/components/projects/ExtractTextButton', () => ({
  ExtractTextButton: ({ onText }: { onText: (t: string) => void }) => (
    <button
      data-testid="extract-text-stub"
      onClick={() => onText('extracted text')}
    >
      Extract
    </button>
  ),
}))

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, fallbackOrParams?: any, maybeParams?: any) => {
      const translations: Record<string, string> = {
        'dataImport.tabs.upload': 'Upload file',
        'dataImport.tabs.paste': 'Paste table/JSON',
        'dataImport.tabs.cloud': 'Cloud storage',
        'projects.creation.wizard.step2.upload.dropzone': 'Drop files here',
        'projects.creation.wizard.step2.upload.supportedFormats':
          'JSON, CSV, TSV',
        'projects.creation.wizard.step2.upload.chooseFiles': 'Choose Files',
        'projects.creation.wizard.step2.upload.removeFile': 'Remove File',
        'projects.creation.wizard.step2.upload.selectedFile':
          'Selected: {filename}',
        'projects.creation.wizard.step2.paste.label': 'Paste data',
        'projects.creation.wizard.step2.paste.placeholder': 'Paste here',
        'projects.creation.wizard.step2.paste.noData': 'No data',
        'projects.creation.wizard.step2.paste.lines': '{count} lines',
        'projects.creation.wizard.step2.paste.clear': 'Clear',
        'projects.creation.wizard.step2.paste.validate': 'Validate',
        'projects.creation.wizard.step2.paste.formatDetected':
          '{format} detected',
        'projects.creation.wizard.step2.paste.invalidFormat': 'Invalid format',
      }
      const params =
        typeof fallbackOrParams === 'object' ? fallbackOrParams : maybeParams
      let result = translations[key] || key
      if (params && typeof params === 'object') {
        Object.entries(params).forEach(([k, v]) => {
          result = result.replace(`{${k}}`, String(v))
        })
      }
      return result
    },
  }),
}))

function setup(
  props: Partial<React.ComponentProps<typeof ImportSourceTabs>> = {}
) {
  const onPastedDataChange = jest.fn()
  const onFileChange = jest.fn()
  const onColumnsDetected = jest.fn()
  const utils = render(
    <ImportSourceTabs
      selectedFile={props.selectedFile ?? null}
      pastedData={props.pastedData ?? ''}
      onFileChange={props.onFileChange ?? onFileChange}
      onPastedDataChange={props.onPastedDataChange ?? onPastedDataChange}
      onColumnsDetected={
        'onColumnsDetected' in props
          ? props.onColumnsDetected
          : onColumnsDetected
      }
      projectKind={props.projectKind}
      structuredTab={props.structuredTab}
      cloudPanel={props.cloudPanel}
      testIdPrefix={props.testIdPrefix ?? 'test-import'}
    />
  )
  return { ...utils, onPastedDataChange, onFileChange, onColumnsDetected }
}

beforeEach(() => {
  jest.clearAllMocks()
})

describe('getImportTabConfig', () => {
  it('leads with the structured tab for exam projects', () => {
    expect(getImportTabConfig('exam', true)).toEqual({
      order: ['structured', 'upload', 'paste', 'cloud'],
      defaultTab: 'structured',
    })
  })

  it('is upload-first for exam projects without a structured tab', () => {
    expect(getImportTabConfig('exam', false)).toEqual({
      order: ['upload', 'paste', 'cloud'],
      defaultTab: 'upload',
    })
  })

  it('appends the structured tab last for non-exam kinds', () => {
    expect(getImportTabConfig(undefined, true)).toEqual({
      order: ['upload', 'paste', 'cloud', 'structured'],
      defaultTab: 'upload',
    })
    expect(getImportTabConfig('generic', true)).toEqual({
      order: ['upload', 'paste', 'cloud', 'structured'],
      defaultTab: 'upload',
    })
  })

  it('is upload-first with three tabs when no structured tab exists', () => {
    expect(getImportTabConfig(undefined, false)).toEqual({
      order: ['upload', 'paste', 'cloud'],
      defaultTab: 'upload',
    })
  })
})

describe('ImportSourceTabs — rendering', () => {
  it('renders three prefixed tabs and defaults to upload', () => {
    setup()
    expect(screen.getByTestId('test-import-data-tabs')).toBeInTheDocument()
    expect(screen.getByTestId('test-import-upload-tab')).toBeInTheDocument()
    expect(screen.getByTestId('test-import-paste-tab')).toBeInTheDocument()
    expect(screen.getByTestId('test-import-cloud-tab')).toBeInTheDocument()
    expect(
      screen.queryByTestId('test-import-structured-tab')
    ).not.toBeInTheDocument()
    // Upload panel is the default content.
    expect(screen.getByText('Drop files here')).toBeInTheDocument()
  })

  it('renders the structured tab and its content for exam kind as default', () => {
    setup({
      projectKind: 'exam',
      structuredTab: {
        label: 'Enter exam',
        content: <div data-testid="structured-content">structured</div>,
      },
    })
    const structuredTrigger = screen.getByTestId('test-import-structured-tab')
    expect(structuredTrigger).toHaveTextContent('Enter exam')
    // Exam kind: structured is the default tab, ordered first.
    expect(screen.getByTestId('structured-content')).toBeInTheDocument()
    const triggers = screen.getAllByRole('button', {
      name: /Enter exam|Upload file|Paste table\/JSON|Cloud storage/,
    })
    expect(triggers[0]).toHaveTextContent('Enter exam')
  })

  it('orders the structured tab last for non-exam kinds', () => {
    setup({
      projectKind: 'generic',
      structuredTab: {
        label: 'Enter exam',
        content: <div data-testid="structured-content">structured</div>,
      },
    })
    // Upload stays default; structured content not mounted.
    expect(screen.getByText('Drop files here')).toBeInTheDocument()
    expect(screen.queryByTestId('structured-content')).not.toBeInTheDocument()
    const list = screen.getByTestId('test-import-structured-tab')
    expect(list).toBeInTheDocument()
  })

  it('renders an empty cloud tab when no cloud panel is provided', async () => {
    const user = userEvent.setup()
    setup()
    await user.click(screen.getByTestId('test-import-cloud-tab'))
    // No built-in placeholder anymore — the surfaces inject the real panel.
    expect(screen.queryByText('Coming soon')).not.toBeInTheDocument()
    expect(screen.queryByTestId('custom-cloud')).not.toBeInTheDocument()
  })

  it('renders the injected cloud panel when provided', async () => {
    const user = userEvent.setup()
    setup({ cloudPanel: <div data-testid="custom-cloud">cloudy</div> })
    await user.click(screen.getByTestId('test-import-cloud-tab'))
    expect(await screen.findByTestId('custom-cloud')).toBeInTheDocument()
  })
})

describe('ImportSourceTabs — paste tab', () => {
  async function openPasteTab(user: ReturnType<typeof userEvent.setup>) {
    await user.click(screen.getByTestId('test-import-paste-tab'))
    return screen.findByTestId('test-import-paste-data-textarea')
  }

  it('reports pasted data and detected columns', async () => {
    const user = userEvent.setup()
    const { onPastedDataChange, onColumnsDetected } = setup()
    const textarea = await openPasteTab(user)
    const json = JSON.stringify([{ question: 'q', answer: 'a' }])
    fireEvent.change(textarea, { target: { value: json } })

    expect(onPastedDataChange).toHaveBeenCalledWith(json)
    expect(onColumnsDetected).toHaveBeenCalledWith(['question', 'answer'])
  })

  it('clears pasted data and columns via the Clear button', async () => {
    const user = userEvent.setup()
    const { onPastedDataChange, onColumnsDetected } = setup({
      pastedData: 'a\nb',
    })
    await openPasteTab(user)
    await user.click(screen.getByTestId('test-import-clear-data-button'))

    expect(onPastedDataChange).toHaveBeenCalledWith('')
    expect(onColumnsDetected).toHaveBeenCalledWith([])
  })

  it('shows the line count for pasted data', async () => {
    const user = userEvent.setup()
    setup({ pastedData: 'a\nb\nc' })
    await openPasteTab(user)
    expect(
      screen.getByTestId('test-import-paste-line-count')
    ).toHaveAttribute('data-line-count', '3')
  })

  it('toasts the detected format on validate', async () => {
    const user = userEvent.setup()
    setup({ pastedData: 'a\tb\n1\t2' })
    await openPasteTab(user)
    await user.click(screen.getByTestId('test-import-validate-data-button'))
    expect(mockAddToast).toHaveBeenCalledWith('TSV detected', 'success')
  })

  it('feeds extracted document text into the paste flow', async () => {
    const user = userEvent.setup()
    const { onPastedDataChange } = setup()
    await openPasteTab(user)
    await user.click(screen.getByTestId('extract-text-stub'))
    expect(onPastedDataChange).toHaveBeenCalledWith(
      JSON.stringify([{ text: 'extracted text' }], null, 2)
    )
  })
})

describe('ImportSourceTabs — upload tab', () => {
  it('reports the selected file and its detected columns', async () => {
    const user = userEvent.setup()
    const { onFileChange, onColumnsDetected } = setup()

    const input = screen.getByTestId(
      'test-import-file-input'
    ) as HTMLInputElement
    const file = new File(['h1\th2\nv1\tv2'], 'data.tsv', {
      type: 'text/tab-separated-values',
    })
    await user.upload(input, file)

    expect(onFileChange).toHaveBeenCalledWith(file)
    await waitFor(() =>
      expect(onColumnsDetected).toHaveBeenCalledWith(['h1', 'h2'])
    )
  })

  it('does not require onColumnsDetected', async () => {
    const user = userEvent.setup()
    const onFileChange = jest.fn()
    setup({ onFileChange, onColumnsDetected: undefined })

    const input = screen.getByTestId(
      'test-import-file-input'
    ) as HTMLInputElement
    const file = new File(['x'], 'plain.txt', { type: 'text/plain' })
    await user.upload(input, file)

    expect(onFileChange).toHaveBeenCalledWith(file)
  })

  it('clears file and columns via the remove button', async () => {
    const user = userEvent.setup()
    const file = new File(['x'], 'mydata.json', { type: 'application/json' })
    const { onFileChange, onColumnsDetected } = setup({ selectedFile: file })

    expect(screen.getByText('Selected: mydata.json')).toBeInTheDocument()
    await user.click(screen.getByTestId('test-import-remove-file-button'))

    expect(onFileChange).toHaveBeenCalledWith(null)
    expect(onColumnsDetected).toHaveBeenCalledWith([])
  })

  it('accepts a dropped file', async () => {
    const { onFileChange } = setup()
    const dropzone = screen.getByRole('button', { name: 'Drop files here' })
    const file = new File(['a,b\n1,2'], 'dropped.csv', { type: 'text/csv' })

    fireEvent.drop(dropzone, { dataTransfer: { files: [file] } })

    expect(onFileChange).toHaveBeenCalledWith(file)
  })
})

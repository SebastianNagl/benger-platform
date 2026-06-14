/**
 * Tests for StepDataImport (project-creation wizard step 2).
 * Covers the paste/upload flows, column extraction across JSON / CSV / TSV,
 * format detection on validate, and the detected-columns rendering branch.
 */

/**
 * @jest-environment jsdom
 */

import '@testing-library/jest-dom'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type * as React from 'react'
import { StepDataImport } from '../StepDataImport'

const mockAddToast = jest.fn()

jest.mock('@/components/shared/Toast', () => ({
  useToast: () => ({ addToast: mockAddToast }),
}))

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, params?: any) => {
      const translations: Record<string, string> = {
        'projects.creation.wizard.step2.title': 'Import Data',
        'projects.creation.wizard.step2.subtitle': 'Add your dataset',
        'projects.creation.wizard.step2.tabs.upload': 'Upload',
        'projects.creation.wizard.step2.tabs.paste': 'Paste',
        'projects.creation.wizard.step2.tabs.cloud': 'Cloud',
        'projects.creation.wizard.step2.upload.dropzone': 'Drop files here',
        'projects.creation.wizard.step2.upload.supportedFormats': 'JSON, CSV, TSV',
        'projects.creation.wizard.step2.upload.chooseFiles': 'Choose Files',
        'projects.creation.wizard.step2.upload.removeFile': 'Remove File',
        'projects.creation.wizard.step2.upload.selectedFile': 'Selected: {filename}',
        'projects.creation.wizard.step2.paste.label': 'Paste data',
        'projects.creation.wizard.step2.paste.placeholder': 'Paste here',
        'projects.creation.wizard.step2.paste.noData': 'No data',
        'projects.creation.wizard.step2.paste.lines': '{count} lines',
        'projects.creation.wizard.step2.paste.clear': 'Clear',
        'projects.creation.wizard.step2.paste.validate': 'Validate',
        'projects.creation.wizard.step2.paste.formatDetected': '{format} detected',
        'projects.creation.wizard.step2.paste.invalidFormat': 'Invalid format',
        'projects.creation.wizard.step2.cloud.comingSoon': 'Coming soon',
        'projects.creation.wizard.step2.detectedColumns': 'Detected columns',
        'projects.creation.wizard.step2.note': 'Note text',
        'projects.wizard.note': 'Note',
      }
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
  props: Partial<React.ComponentProps<typeof StepDataImport>> = {}
) {
  const onPastedDataChange = jest.fn()
  const onFileChange = jest.fn()
  const onDataColumnsChange = jest.fn()
  const utils = render(
    <StepDataImport
      pastedData={props.pastedData ?? ''}
      selectedFile={props.selectedFile ?? null}
      dataColumns={props.dataColumns ?? []}
      onPastedDataChange={props.onPastedDataChange ?? onPastedDataChange}
      onFileChange={props.onFileChange ?? onFileChange}
      onDataColumnsChange={props.onDataColumnsChange ?? onDataColumnsChange}
    />
  )
  return { ...utils, onPastedDataChange, onFileChange, onDataColumnsChange }
}

beforeEach(() => {
  jest.clearAllMocks()
})

describe('StepDataImport — rendering', () => {
  it('renders the title, subtitle and three import tabs', () => {
    setup()
    expect(screen.getByText('Import Data')).toBeInTheDocument()
    expect(screen.getByTestId('project-create-upload-tab')).toBeInTheDocument()
    expect(screen.getByTestId('project-create-paste-tab')).toBeInTheDocument()
    expect(screen.getByTestId('project-create-cloud-tab')).toBeInTheDocument()
  })

  it('renders detected columns when dataColumns is non-empty', () => {
    setup({ dataColumns: ['question', 'answer'] })
    expect(screen.getByText('Detected columns')).toBeInTheDocument()
    expect(screen.getByText('question')).toBeInTheDocument()
    expect(screen.getByText('answer')).toBeInTheDocument()
  })

  it('does not render the detected-columns block when empty', () => {
    setup({ dataColumns: [] })
    expect(screen.queryByText('Detected columns')).not.toBeInTheDocument()
  })
})

describe('StepDataImport — paste tab', () => {
  // The paste TabsContent only mounts once the paste trigger is active.
  async function openPasteTab(user: ReturnType<typeof userEvent.setup>) {
    await user.click(screen.getByTestId('project-create-paste-tab'))
    return screen.findByTestId('project-create-paste-data-textarea')
  }

  it('reports zero lines and disables clear/validate when empty', async () => {
    const user = userEvent.setup()
    setup({ pastedData: '' })
    await openPasteTab(user)
    const count = screen.getByTestId('project-create-paste-line-count')
    expect(count).toHaveAttribute('data-line-count', '0')
    expect(screen.getByTestId('project-create-clear-data-button')).toBeDisabled()
    expect(
      screen.getByTestId('project-create-validate-data-button')
    ).toBeDisabled()
  })

  it('counts lines for multi-line pasted data', async () => {
    const user = userEvent.setup()
    setup({ pastedData: 'a\nb\nc' })
    await openPasteTab(user)
    const count = screen.getByTestId('project-create-paste-line-count')
    expect(count).toHaveAttribute('data-line-count', '3')
  })

  it('extracts JSON object keys when pasting a JSON array', async () => {
    const user = userEvent.setup()
    const { onPastedDataChange, onDataColumnsChange } = setup()
    const textarea = await openPasteTab(user)
    const json = JSON.stringify([{ question: 'q', answer: 'a' }])
    fireEvent.change(textarea, { target: { value: json } })

    expect(onPastedDataChange).toHaveBeenCalledWith(json)
    expect(onDataColumnsChange).toHaveBeenCalledWith(['question', 'answer'])
  })

  it('extracts columns from a nested qa_samples JSON wrapper', async () => {
    const user = userEvent.setup()
    const { onDataColumnsChange } = setup()
    const textarea = await openPasteTab(user)
    const json = JSON.stringify({ qa_samples: [{ q: '1', a: '2' }] })
    fireEvent.change(textarea, { target: { value: json } })

    expect(onDataColumnsChange).toHaveBeenCalledWith(['q', 'a'])
  })

  it('extracts TSV headers', async () => {
    const user = userEvent.setup()
    const { onDataColumnsChange } = setup()
    const textarea = await openPasteTab(user)
    fireEvent.change(textarea, { target: { value: 'col1\tcol2\nv1\tv2' } })

    expect(onDataColumnsChange).toHaveBeenCalledWith(['col1', 'col2'])
  })

  it('extracts CSV headers and strips surrounding quotes', async () => {
    const user = userEvent.setup()
    const { onDataColumnsChange } = setup()
    const textarea = await openPasteTab(user)
    fireEvent.change(textarea, { target: { value: '"name","age"\nx,1' } })

    expect(onDataColumnsChange).toHaveBeenCalledWith(['name', 'age'])
  })

  it('returns no columns for plain text without delimiters', async () => {
    const user = userEvent.setup()
    const { onDataColumnsChange } = setup()
    const textarea = await openPasteTab(user)
    fireEvent.change(textarea, { target: { value: 'just some prose' } })

    expect(onDataColumnsChange).toHaveBeenCalledWith([])
  })

  it('clears pasted data via the Clear button', async () => {
    const user = userEvent.setup()
    const { onPastedDataChange, onDataColumnsChange } = setup({
      pastedData: 'a\nb',
    })
    await openPasteTab(user)
    await user.click(screen.getByTestId('project-create-clear-data-button'))

    expect(onPastedDataChange).toHaveBeenCalledWith('')
    expect(onDataColumnsChange).toHaveBeenCalledWith([])
  })

  it('detects JSON format on validate and toasts success', async () => {
    const user = userEvent.setup()
    setup({ pastedData: '[{"a":1}]' })
    await openPasteTab(user)
    await user.click(screen.getByTestId('project-create-validate-data-button'))

    expect(mockAddToast).toHaveBeenCalledWith('JSON detected', 'success')
  })

  it('detects TSV format on validate', async () => {
    const user = userEvent.setup()
    setup({ pastedData: 'a\tb\n1\t2' })
    await openPasteTab(user)
    await user.click(screen.getByTestId('project-create-validate-data-button'))

    expect(mockAddToast).toHaveBeenCalledWith('TSV detected', 'success')
  })

  it('detects CSV format on validate', async () => {
    const user = userEvent.setup()
    setup({ pastedData: 'a,b\n1,2' })
    await openPasteTab(user)
    await user.click(screen.getByTestId('project-create-validate-data-button'))

    expect(mockAddToast).toHaveBeenCalledWith('CSV detected', 'success')
  })

  it('falls back to TXT format for plain text on validate', async () => {
    const user = userEvent.setup()
    setup({ pastedData: 'plain prose without delimiters' })
    await openPasteTab(user)
    await user.click(screen.getByTestId('project-create-validate-data-button'))

    expect(mockAddToast).toHaveBeenCalledWith('TXT detected', 'success')
  })
})

describe('StepDataImport — upload tab', () => {
  it('extracts columns from an uploaded file via FileReader', async () => {
    const user = userEvent.setup()
    const { onFileChange, onDataColumnsChange } = setup()

    // Switch to the upload tab is the default; the hidden input is present.
    const input = screen.getByTestId(
      'project-create-file-input'
    ) as HTMLInputElement
    const file = new File(['header1\theader2\nv1\tv2'], 'data.tsv', {
      type: 'text/tab-separated-values',
    })

    await user.upload(input, file)

    expect(onFileChange).toHaveBeenCalledWith(file)
    await waitFor(() =>
      expect(onDataColumnsChange).toHaveBeenCalledWith(['header1', 'header2'])
    )
  })

  it('shows the selected-file UI and a remove button when a file is set', () => {
    const file = new File(['x'], 'mydata.json', { type: 'application/json' })
    setup({ selectedFile: file })

    expect(screen.getByText('Selected: mydata.json')).toBeInTheDocument()
    expect(
      screen.getByTestId('project-create-remove-file-button')
    ).toBeInTheDocument()
  })

  it('clears file and columns when Remove File is clicked', async () => {
    const user = userEvent.setup()
    const file = new File(['x'], 'mydata.json', { type: 'application/json' })
    const { onFileChange, onDataColumnsChange } = setup({ selectedFile: file })

    await user.click(screen.getByTestId('project-create-remove-file-button'))

    expect(onFileChange).toHaveBeenCalledWith(null)
    expect(onDataColumnsChange).toHaveBeenCalledWith([])
  })

  it('handles a file dropped onto the dropzone', async () => {
    const { onFileChange, onDataColumnsChange } = setup()
    const dropzone = screen.getByRole('button', { name: 'Drop files here' })
    const file = new File(['a,b\n1,2'], 'dropped.csv', { type: 'text/csv' })

    fireEvent.drop(dropzone, {
      dataTransfer: { files: [file] },
    })

    expect(onFileChange).toHaveBeenCalledWith(file)
    await waitFor(() =>
      expect(onDataColumnsChange).toHaveBeenCalledWith(['a', 'b'])
    )
  })

  it('prevents default on dragover without crashing', () => {
    setup()
    const dropzone = screen.getByRole('button', { name: 'Drop files here' })
    // Should not throw.
    fireEvent.dragOver(dropzone)
    expect(dropzone).toBeInTheDocument()
  })
})

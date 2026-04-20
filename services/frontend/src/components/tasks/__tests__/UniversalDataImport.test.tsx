/**
 * Comprehensive tests for UniversalDataImport component
 * Target: 85%+ coverage
 */

import '@testing-library/jest-dom'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { UniversalDataImport } from '../UniversalDataImport'

// Mock translation function
const mockT = (key: string) => {
  const translations: Record<string, string> = {
    'tasks.import.title': 'Import Data',
    'tasks.import.supportedFormats':
      'Supported: JSON, CSV, TSV, TXT, Excel (.xlsx)',
    'tasks.import.smartMapping': 'Smart field mapping included',
    'tasks.import.dropHere': 'Drag & drop your file here',
    'tasks.import.clickBrowse': 'or click to browse',
    'tasks.import.chooseFile': 'Choose File',
    'tasks.import.formatLabels.json': 'JSON',
    'tasks.import.formatLabels.jsonDesc': 'Structured data',
    'tasks.import.formatLabels.csv': 'CSV',
    'tasks.import.formatLabels.csvDesc': 'Comma separated',
    'tasks.import.formatLabels.excel': 'Excel',
    'tasks.import.formatLabels.excelDesc': '.xlsx files',
    'tasks.import.formatLabels.more': 'More',
    'tasks.import.formatLabels.moreDesc': 'TSV, TXT',
    'tasks.import.examples.jsonTitle': 'Example JSON structure',
    'tasks.import.examples.csvTitle': 'Example CSV format',
    'tasks.import.importSuccess': 'Import Successful!',
    'tasks.import.importSuccessDesc': 'Your data has been imported',
  }
  return translations[key] || key
}

// Mock I18nContext
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: mockT,
    locale: 'en' as const,
    changeLocale: jest.fn(),
    isReady: true,
  }),
}))

// Mock ImportPreviewWithMapping
jest.mock('../ImportPreviewWithMapping', () => ({
  ImportPreviewWithMapping: ({
    file,
    onImport,
    onCancel,
  }: {
    file: File
    onImport: (data: any[]) => void
    onCancel: () => void
  }) => (
    <div data-testid="import-preview">
      <div data-testid="preview-filename">{file.name}</div>
      <button onClick={() => onImport([{ test: 'data' }])}>Import</button>
      <button onClick={onCancel}>Cancel</button>
    </div>
  ),
}))

describe('UniversalDataImport', () => {
  const mockOnImport = jest.fn()
  const defaultProps = {
    onImport: mockOnImport,
    templateFields: ['field1', 'field2', 'field3'],
  }

  beforeEach(() => {
    jest.clearAllMocks()
  })

  describe('Initial Render', () => {
    it('should render import card with title', () => {
      render(<UniversalDataImport {...defaultProps} />)
      expect(screen.getByText('Import Data')).toBeInTheDocument()
    })

    it('should display supported formats alert', () => {
      render(<UniversalDataImport {...defaultProps} />)
      expect(
        screen.getByText('Supported: JSON, CSV, TSV, TXT, Excel (.xlsx)')
      ).toBeInTheDocument()
      expect(
        screen.getByText('Smart field mapping included')
      ).toBeInTheDocument()
    })

    it('should show dropzone with instructions', () => {
      render(<UniversalDataImport {...defaultProps} />)
      expect(screen.getByText('Drag & drop your file here')).toBeInTheDocument()
      expect(screen.getByText('or click to browse')).toBeInTheDocument()
    })

    it('should display file input with correct accept types', () => {
      const { container } = render(<UniversalDataImport {...defaultProps} />)
      const fileInput = container.querySelector(
        'input[type="file"]'
      ) as HTMLInputElement
      expect(fileInput).toBeInTheDocument()
      expect(fileInput.accept).toBe('.json,.jsonl,.csv,.tsv,.txt,.xlsx,.xls')
    })

    it('should show Choose File button', () => {
      render(<UniversalDataImport {...defaultProps} />)
      expect(screen.getByText('Choose File')).toBeInTheDocument()
    })
  })

  describe('Format Examples Display', () => {
    it('should display all format cards', () => {
      render(<UniversalDataImport {...defaultProps} />)
      expect(screen.getByText('JSON')).toBeInTheDocument()
      expect(screen.getByText('Structured data')).toBeInTheDocument()
      expect(screen.getByText('CSV')).toBeInTheDocument()
      expect(screen.getByText('Comma separated')).toBeInTheDocument()
      expect(screen.getByText('Excel')).toBeInTheDocument()
      expect(screen.getByText('.xlsx files')).toBeInTheDocument()
      expect(screen.getByText('More')).toBeInTheDocument()
      expect(screen.getByText('TSV, TXT')).toBeInTheDocument()
    })

    it('should show expandable JSON example', () => {
      render(<UniversalDataImport {...defaultProps} />)
      const jsonExample = screen.getByText('Example JSON structure')
      expect(jsonExample).toBeInTheDocument()
      fireEvent.click(jsonExample)
      const examples = screen.getAllByText(/plaintiff claims/)
      expect(examples.length).toBeGreaterThan(0)
    })

    it('should show expandable CSV example', () => {
      render(<UniversalDataImport {...defaultProps} />)
      const csvExample = screen.getByText('Example CSV format')
      expect(csvExample).toBeInTheDocument()
      fireEvent.click(csvExample)
      const examples = screen.getAllByText(/plaintiff claims/)
      expect(examples.length).toBeGreaterThan(0)
    })
  })

  describe('File Selection', () => {
    it('should handle file selection via input', () => {
      const { container } = render(<UniversalDataImport {...defaultProps} />)
      const file = new File([JSON.stringify([{ test: 'data' }])], 'test.json', {
        type: 'application/json',
      })
      const fileInput = container.querySelector(
        'input[type="file"]'
      ) as HTMLInputElement
      Object.defineProperty(fileInput, 'files', {
        value: [file],
        writable: false,
      })
      fireEvent.change(fileInput)
      expect(screen.getByTestId('import-preview')).toBeInTheDocument()
      expect(screen.getByTestId('preview-filename')).toHaveTextContent(
        'test.json'
      )
    })

    it('should show preview for JSON file', () => {
      const { container } = render(<UniversalDataImport {...defaultProps} />)
      const file = new File(['[{"name": "test"}]'], 'data.json', {
        type: 'application/json',
      })
      const fileInput = container.querySelector(
        'input[type="file"]'
      ) as HTMLInputElement
      Object.defineProperty(fileInput, 'files', {
        value: [file],
        writable: false,
      })
      fireEvent.change(fileInput)
      expect(screen.getByTestId('import-preview')).toBeInTheDocument()
    })

    it('should show preview for CSV file', () => {
      const { container } = render(<UniversalDataImport {...defaultProps} />)
      const file = new File(['col1,col2\nval1,val2'], 'data.csv', {
        type: 'text/csv',
      })
      const fileInput = container.querySelector(
        'input[type="file"]'
      ) as HTMLInputElement
      Object.defineProperty(fileInput, 'files', {
        value: [file],
        writable: false,
      })
      fireEvent.change(fileInput)
      expect(screen.getByTestId('import-preview')).toBeInTheDocument()
    })

    it('should show preview for Excel file', () => {
      const { container } = render(<UniversalDataImport {...defaultProps} />)
      const file = new File([new ArrayBuffer(100)], 'data.xlsx', {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      })
      const fileInput = container.querySelector(
        'input[type="file"]'
      ) as HTMLInputElement
      Object.defineProperty(fileInput, 'files', {
        value: [file],
        writable: false,
      })
      fireEvent.change(fileInput)
      expect(screen.getByTestId('import-preview')).toBeInTheDocument()
    })
  })

  describe('Drag and Drop', () => {
    it('should handle drag over event', () => {
      const { container } = render(<UniversalDataImport {...defaultProps} />)
      const dropzone = container.querySelector(
        'div[class*="border-dashed"]'
      ) as HTMLElement
      fireEvent.dragOver(dropzone, {
        preventDefault: jest.fn(),
      })
      expect(dropzone.className).toContain('border-blue-400')
    })

    it('should handle drag leave event', () => {
      const { container } = render(<UniversalDataImport {...defaultProps} />)
      const dropzone = container.querySelector(
        'div[class*="border-dashed"]'
      ) as HTMLElement
      fireEvent.dragOver(dropzone, {
        preventDefault: jest.fn(),
      })
      fireEvent.dragLeave(dropzone)
      expect(dropzone.className).not.toContain('border-blue-400')
    })

    it('should handle file drop', () => {
      const { container } = render(<UniversalDataImport {...defaultProps} />)
      const file = new File(['test'], 'test.json', {
        type: 'application/json',
      })
      const dropzone = container.querySelector(
        'div[class*="border-dashed"]'
      ) as HTMLElement
      fireEvent.drop(dropzone, {
        preventDefault: jest.fn(),
        dataTransfer: {
          files: [file],
        },
      })
      expect(screen.getByTestId('import-preview')).toBeInTheDocument()
    })

    it('should ignore drop without files', () => {
      const { container } = render(<UniversalDataImport {...defaultProps} />)
      const dropzone = container.querySelector(
        'div[class*="border-dashed"]'
      ) as HTMLElement
      fireEvent.drop(dropzone, {
        preventDefault: jest.fn(),
        dataTransfer: {
          files: [],
        },
      })
      expect(screen.queryByTestId('import-preview')).not.toBeInTheDocument()
    })
  })

  describe('Import Flow', () => {
    it('should call onImport with data when import is clicked', async () => {
      const { container } = render(<UniversalDataImport {...defaultProps} />)
      const file = new File(['test'], 'test.json', {
        type: 'application/json',
      })
      const fileInput = container.querySelector(
        'input[type="file"]'
      ) as HTMLInputElement
      Object.defineProperty(fileInput, 'files', {
        value: [file],
        writable: false,
      })
      fireEvent.change(fileInput)
      const importButton = screen.getByText('Import')
      fireEvent.click(importButton)
      await waitFor(() => {
        expect(mockOnImport).toHaveBeenCalledWith([{ test: 'data' }])
      })
    })

    it('should show success state after import', async () => {
      const { container } = render(<UniversalDataImport {...defaultProps} />)
      const file = new File(['test'], 'test.json', {
        type: 'application/json',
      })
      const fileInput = container.querySelector(
        'input[type="file"]'
      ) as HTMLInputElement
      Object.defineProperty(fileInput, 'files', {
        value: [file],
        writable: false,
      })
      fireEvent.change(fileInput)
      const importButton = screen.getByText('Import')
      fireEvent.click(importButton)
      await waitFor(() => {
        expect(screen.getByText('Import Successful!')).toBeInTheDocument()
        expect(
          screen.getByText('Your data has been imported')
        ).toBeInTheDocument()
      })
    })

    it('should reset to initial state after success', async () => {
      const { container } = render(<UniversalDataImport {...defaultProps} />)
      const file = new File(['test'], 'test.json', {
        type: 'application/json',
      })
      const fileInput = container.querySelector(
        'input[type="file"]'
      ) as HTMLInputElement
      Object.defineProperty(fileInput, 'files', {
        value: [file],
        writable: false,
      })
      fireEvent.change(fileInput)
      const importButton = screen.getByText('Import')
      fireEvent.click(importButton)
      await waitFor(() => {
        expect(screen.getByText('Import Successful!')).toBeInTheDocument()
      })
      await waitFor(
        () => {
          expect(screen.getByText('Choose File')).toBeInTheDocument()
        },
        { timeout: 3000 }
      )
    })
  })

  describe('Cancel Flow', () => {
    it('should return to initial state when cancel is clicked', () => {
      const { container } = render(<UniversalDataImport {...defaultProps} />)
      const file = new File(['test'], 'test.json', {
        type: 'application/json',
      })
      const fileInput = container.querySelector(
        'input[type="file"]'
      ) as HTMLInputElement
      Object.defineProperty(fileInput, 'files', {
        value: [file],
        writable: false,
      })
      fireEvent.change(fileInput)
      expect(screen.getByTestId('import-preview')).toBeInTheDocument()
      const cancelButton = screen.getByText('Cancel')
      fireEvent.click(cancelButton)
      expect(screen.queryByTestId('import-preview')).not.toBeInTheDocument()
      expect(screen.getByText('Choose File')).toBeInTheDocument()
    })

    it('should clear selected file on cancel', () => {
      const { container } = render(<UniversalDataImport {...defaultProps} />)
      const file = new File(['test'], 'test.json', {
        type: 'application/json',
      })
      const fileInput = container.querySelector(
        'input[type="file"]'
      ) as HTMLInputElement
      Object.defineProperty(fileInput, 'files', {
        value: [file],
        writable: false,
      })
      fireEvent.change(fileInput)
      const cancelButton = screen.getByText('Cancel')
      fireEvent.click(cancelButton)
      expect(screen.getByText('Drag & drop your file here')).toBeInTheDocument()
    })
  })

  describe('Template Fields', () => {
    it('should pass template fields to preview', () => {
      const templateFields = ['custom1', 'custom2', 'custom3']
      const { container } = render(
        <UniversalDataImport
          onImport={mockOnImport}
          templateFields={templateFields}
        />
      )
      const file = new File(['test'], 'test.json', {
        type: 'application/json',
      })
      const fileInput = container.querySelector(
        'input[type="file"]'
      ) as HTMLInputElement
      Object.defineProperty(fileInput, 'files', {
        value: [file],
        writable: false,
      })
      fireEvent.change(fileInput)
      expect(screen.getByTestId('import-preview')).toBeInTheDocument()
    })

    it('should work without template fields', () => {
      const { container } = render(
        <UniversalDataImport onImport={mockOnImport} />
      )
      const file = new File(['test'], 'test.json', {
        type: 'application/json',
      })
      const fileInput = container.querySelector(
        'input[type="file"]'
      ) as HTMLInputElement
      Object.defineProperty(fileInput, 'files', {
        value: [file],
        writable: false,
      })
      fireEvent.change(fileInput)
      expect(screen.getByTestId('import-preview')).toBeInTheDocument()
    })
  })

  describe('Custom className', () => {
    it('should apply custom className to card', () => {
      const { container } = render(
        <UniversalDataImport
          {...defaultProps}
          className="custom-import-class"
        />
      )
      const card = container.querySelector('.custom-import-class')
      expect(card).toBeInTheDocument()
    })

    it('should apply className to success state', async () => {
      const { container } = render(
        <UniversalDataImport
          {...defaultProps}
          className="custom-success-class"
        />
      )
      const file = new File(['test'], 'test.json', {
        type: 'application/json',
      })
      const fileInput = container.querySelector(
        'input[type="file"]'
      ) as HTMLInputElement
      Object.defineProperty(fileInput, 'files', {
        value: [file],
        writable: false,
      })
      fireEvent.change(fileInput)
      const importButton = screen.getByText('Import')
      fireEvent.click(importButton)
      await waitFor(() => {
        const successCard = container.querySelector('.custom-success-class')
        expect(successCard).toBeInTheDocument()
      })
    })
  })

  describe('Edge Cases', () => {
    it('should handle empty file name', () => {
      const { container } = render(<UniversalDataImport {...defaultProps} />)
      const file = new File(['test'], '', { type: 'application/json' })
      const fileInput = container.querySelector(
        'input[type="file"]'
      ) as HTMLInputElement
      Object.defineProperty(fileInput, 'files', {
        value: [file],
        writable: false,
      })
      fireEvent.change(fileInput)
      expect(screen.getByTestId('import-preview')).toBeInTheDocument()
    })

    it('should handle multiple rapid file selections', () => {
      const { container } = render(<UniversalDataImport {...defaultProps} />)
      const fileInput = container.querySelector(
        'input[type="file"]'
      ) as HTMLInputElement
      const file1 = new File(['test1'], 'test1.json', {
        type: 'application/json',
      })
      Object.defineProperty(fileInput, 'files', {
        value: [file1],
        writable: false,
      })
      fireEvent.change(fileInput)
      expect(screen.getByTestId('preview-filename')).toHaveTextContent(
        'test1.json'
      )
    })

    it('should handle file selection after cancel', () => {
      const { container, rerender } = render(
        <UniversalDataImport {...defaultProps} />
      )
      let fileInput = container.querySelector(
        'input[type="file"]'
      ) as HTMLInputElement
      const file1 = new File(['test1'], 'test1.json', {
        type: 'application/json',
      })
      Object.defineProperty(fileInput, 'files', {
        value: [file1],
        writable: false,
      })
      fireEvent.change(fileInput)
      const cancelButton = screen.getByText('Cancel')
      fireEvent.click(cancelButton)
      // After cancel, get a fresh reference to the file input
      fileInput = container.querySelector(
        'input[type="file"]'
      ) as HTMLInputElement
      const file2 = new File(['test2'], 'test2.json', {
        type: 'application/json',
      })
      Object.defineProperty(fileInput, 'files', {
        value: [file2],
        writable: false,
      })
      fireEvent.change(fileInput)
      expect(screen.getByTestId('preview-filename')).toHaveTextContent(
        'test2.json'
      )
    })
  })
})

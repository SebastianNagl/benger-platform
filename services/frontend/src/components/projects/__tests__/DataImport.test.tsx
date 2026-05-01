/**
 * Comprehensive tests for DataImport component
 * Target: 90%+ coverage of all functionality
 */

import { renderWithProviders } from '@/test-utils'
import '@testing-library/jest-dom'
import { fireEvent, screen, waitFor } from '@testing-library/react'

// Toast mocking is handled by setupTests.ts: useToast().addToast(msg, type)
// dispatches to mockToast.success/error/etc, exported from setupTests.
import { mockToast } from '@/test-utils/setupTests'
const mockToastSuccess = mockToast.success
const mockToastError = mockToast.error

const mockImportData = jest.fn()
const mockOnComplete = jest.fn()
let mockLoading = false

// Store onDrop callback for direct invocation
let capturedOnDrop: ((files: File[]) => void) | null = null

// Mock react-dropzone first - before component import
jest.mock('react-dropzone', () => ({
  useDropzone: (params: any) => {
    const { onDrop, accept, maxFiles, disabled } = params
    // Capture the onDrop callback for manual invocation
    capturedOnDrop = onDrop

    return {
      getRootProps: () => ({
        onClick: jest.fn(),
        'data-testid': 'dropzone',
      }),
      getInputProps: () => ({
        type: 'file',
        accept: Object.values(accept || {})
          .flat()
          .join(','),
        'data-testid': 'file-input',
      }),
      isDragActive: false,
      acceptedFiles: [],
    }
  },
}))

jest.mock('@/stores/projectStore', () => ({
  useProjectStore: jest.fn(() => ({
    importData: mockImportData,
    loading: mockLoading,
  })),
}))

// Configure I18n mock from test-utils with DataImport translations
import { useI18n } from '@/contexts/I18nContext'
const mockUseI18n = useI18n as jest.MockedFunction<typeof useI18n>
const dataImportI18nValue = {
  t: (key: string, arg2?: any, arg3?: any) => {
    const vars = typeof arg2 === 'object' ? arg2 : arg3
    const translations: Record<string, string> = {
      'projects.dataImport.title': 'Import Data',
      'projects.dataImport.subtitle': 'Add tasks to your project by uploading files or pasting data',
      'projects.dataImport.uploadFile': 'Upload File',
      'projects.dataImport.pasteData': 'Paste Data',
      'projects.dataImport.dropFile': 'Drop the file here...',
      'projects.dataImport.dragAndDrop': 'Drag & drop a file here, or click to browse',
      'projects.dataImport.supportedFormats': 'Supports JSON, CSV, TSV, and TXT files',
      'projects.dataImport.exampleFormats': 'Example formats:',
      'projects.dataImport.pastePlaceholder': 'Paste your data here...',
      'projects.dataImport.importing': 'Importing...',
      'projects.dataImport.importData': 'Import Data',
      'projects.dataImport.importSuccess': 'Successfully imported {count} tasks',
      'projects.dataImport.importFailed': 'Failed to import data',
      'projects.dataImport.importFileFailed': 'Failed to import file',
      'projects.dataImport.pasteEmpty': 'Please paste some data first',
      'projects.dataImport.unsupportedFormat': 'Unsupported file format',
      'projects.dataImport.importStats': 'Successfully imported {successful} of {total} tasks',
      'projects.dataImport.importStatsFailed': '{count} failed',
      'common.loading': 'Loading...',
    }
    let result = translations[key] || key
    if (typeof _default === 'object') vars = _default as any
    if (vars) {
      Object.entries(vars).forEach(([k, v]) => {
        result = result.replace(`{${k}}`, String(v))
      })
    }
    return result
  },
  locale: 'en',
} as any

// Import component after mocks are set up
import { DataImport } from '../DataImport'

// Helper to trigger file processing
const triggerFileUpload = async (container: HTMLElement, file: File) => {
  const input = container.querySelector(
    'input[data-testid="file-input"]'
  ) as HTMLInputElement

  Object.defineProperty(input, 'files', {
    value: [file],
    configurable: true,
  })

  // Manually invoke the onDrop callback that was captured during component render
  if (capturedOnDrop) {
    await capturedOnDrop([file], [], {} as any)
  }
}

describe('DataImport', () => {
  const defaultProps = {
    projectId: 'test-project-123',
    onComplete: mockOnComplete,
  }

  beforeEach(() => {
    jest.clearAllMocks()
    mockUseI18n.mockReturnValue(dataImportI18nValue)
    mockImportData.mockResolvedValue(undefined)
    mockLoading = false

    // Mock File.prototype.text() to read file contents
    File.prototype.text = jest.fn(function (this: File) {
      // Read the actual content from the File object created with new File([content], ...)
      return new Promise((resolve) => {
        const reader = new FileReader()
        reader.onload = () => {
          resolve(reader.result as string)
        }
        reader.readAsText(this)
      })
    })
  })

  describe('Component Rendering', () => {
    it('should render with title and description', () => {
      renderWithProviders(<DataImport {...defaultProps} />)

      expect(screen.getByText('Import Data')).toBeInTheDocument()
      expect(screen.getByText(/Add tasks to your project/i)).toBeInTheDocument()
    })

    it('should render upload and paste tabs', () => {
      renderWithProviders(<DataImport {...defaultProps} />)

      expect(screen.getByText(/Upload File/i)).toBeInTheDocument()
      expect(screen.getByText(/Paste Data/i)).toBeInTheDocument()
    })

    it('should display format badges', () => {
      renderWithProviders(<DataImport {...defaultProps} />)

      expect(screen.getByText('JSON')).toBeInTheDocument()
      expect(screen.getByText('CSV')).toBeInTheDocument()
      expect(screen.getByText('TSV')).toBeInTheDocument()
      expect(screen.getByText('TXT')).toBeInTheDocument()
    })

    it('should show format examples', () => {
      renderWithProviders(<DataImport {...defaultProps} />)

      expect(screen.getByText(/Example formats:/i)).toBeInTheDocument()
      expect(screen.getByText(/JSON:/i)).toBeInTheDocument()
      expect(screen.getByText(/CSV:/i)).toBeInTheDocument()
    })
  })

  describe('JSON File Processing', () => {
    it('should import JSON array file', async () => {
      const { container } = renderWithProviders(
        <DataImport {...defaultProps} />
      )

      const jsonData = [{ text: 'Item 1' }, { text: 'Item 2' }]
      const file = new File([JSON.stringify(jsonData)], 'test.json', {
        type: 'application/json',
      })

      await triggerFileUpload(container, file)

      await waitFor(
        () => {
          expect(mockImportData).toHaveBeenCalledWith(
            'test-project-123',
            jsonData
          )
        },
        { timeout: 3000 }
      )

      expect(mockToastSuccess).toHaveBeenCalledWith(
        'Successfully imported 2 tasks'
      )
      expect(mockOnComplete).toHaveBeenCalled()
    })

    it('should handle JSON with data property', async () => {
      const { container } = renderWithProviders(
        <DataImport {...defaultProps} />
      )

      const wrappedData = {
        data: [{ text: 'Item 1' }, { text: 'Item 2' }],
        meta: 'extra',
      }
      const file = new File([JSON.stringify(wrappedData)], 'test.json', {
        type: 'application/json',
      })

      await triggerFileUpload(container, file)

      await waitFor(
        () => {
          expect(mockImportData).toHaveBeenCalledWith('test-project-123', [
            { text: 'Item 1' },
            { text: 'Item 2' },
          ])
        },
        { timeout: 3000 }
      )
    })

    it('should convert single JSON object to array', async () => {
      const { container } = renderWithProviders(
        <DataImport {...defaultProps} />
      )

      const singleObject = { text: 'Single item', category: 'test' }
      const file = new File([JSON.stringify(singleObject)], 'test.json', {
        type: 'application/json',
      })

      await triggerFileUpload(container, file)

      await waitFor(
        () => {
          expect(mockImportData).toHaveBeenCalledWith('test-project-123', [
            singleObject,
          ])
        },
        { timeout: 3000 }
      )
    })

    it('should handle invalid JSON', async () => {
      const { container } = renderWithProviders(
        <DataImport {...defaultProps} />
      )

      const file = new File(['not valid json {'], 'test.json', {
        type: 'application/json',
      })

      await triggerFileUpload(container, file)

      await waitFor(
        () => {
          expect(mockToastError).toHaveBeenCalled()
          expect(mockImportData).not.toHaveBeenCalled()
        },
        { timeout: 3000 }
      )
    })
  })

  describe('CSV File Processing', () => {
    it('should process CSV file correctly', async () => {
      const { container } = renderWithProviders(
        <DataImport {...defaultProps} />
      )

      const csvContent = 'text,category\nItem 1,Cat 1\nItem 2,Cat 2'
      const file = new File([csvContent], 'test.csv', { type: 'text/csv' })

      await triggerFileUpload(container, file)

      await waitFor(
        () => {
          expect(mockImportData).toHaveBeenCalledWith('test-project-123', [
            { text: 'Item 1', category: 'Cat 1' },
            { text: 'Item 2', category: 'Cat 2' },
          ])
        },
        { timeout: 3000 }
      )
    })

    it('should handle CSV with empty values', async () => {
      const { container } = renderWithProviders(
        <DataImport {...defaultProps} />
      )

      const csvContent = 'text,category\nItem 1,\n,Category'
      const file = new File([csvContent], 'test.csv', { type: 'text/csv' })

      await triggerFileUpload(container, file)

      await waitFor(
        () => {
          expect(mockImportData).toHaveBeenCalledWith('test-project-123', [
            { text: 'Item 1', category: '' },
            { text: '', category: 'Category' },
          ])
        },
        { timeout: 3000 }
      )
    })

    it('should handle CSV with multiple columns', async () => {
      const { container } = renderWithProviders(
        <DataImport {...defaultProps} />
      )

      const csvContent =
        'text,category,priority\nTask 1,Legal,High\nTask 2,Tax,Low'
      const file = new File([csvContent], 'test.csv', { type: 'text/csv' })

      await triggerFileUpload(container, file)

      await waitFor(
        () => {
          expect(mockImportData).toHaveBeenCalledWith('test-project-123', [
            { text: 'Task 1', category: 'Legal', priority: 'High' },
            { text: 'Task 2', category: 'Tax', priority: 'Low' },
          ])
        },
        { timeout: 3000 }
      )
    })

    it('should handle CSV with quoted values', async () => {
      const { container } = renderWithProviders(
        <DataImport {...defaultProps} />
      )

      const csvContent = 'text,category\n"Item 1","Cat 1"\n"Item 2","Cat 2"'
      const file = new File([csvContent], 'test.csv', { type: 'text/csv' })

      await triggerFileUpload(container, file)

      await waitFor(
        () => {
          expect(mockImportData).toHaveBeenCalled()
        },
        { timeout: 3000 }
      )
    })
  })

  describe('TSV File Processing', () => {
    it('should process TSV file correctly', async () => {
      const { container } = renderWithProviders(
        <DataImport {...defaultProps} />
      )

      const tsvContent = 'text\tcategory\nItem 1\tCat 1\nItem 2\tCat 2'
      const file = new File([tsvContent], 'test.tsv', {
        type: 'text/tab-separated-values',
      })

      await triggerFileUpload(container, file)

      await waitFor(
        () => {
          expect(mockImportData).toHaveBeenCalledWith('test-project-123', [
            { text: 'Item 1', category: 'Cat 1' },
            { text: 'Item 2', category: 'Cat 2' },
          ])
        },
        { timeout: 3000 }
      )
    })

    it('should trim whitespace in TSV', async () => {
      const { container } = renderWithProviders(
        <DataImport {...defaultProps} />
      )

      const tsvContent = 'text\tcategory\n  Item 1  \t  Cat 1  '
      const file = new File([tsvContent], 'test.tsv', {
        type: 'text/tab-separated-values',
      })

      await triggerFileUpload(container, file)

      await waitFor(
        () => {
          expect(mockImportData).toHaveBeenCalled()
        },
        { timeout: 3000 }
      )
    })
  })

  describe('TXT File Processing', () => {
    it('should process TXT file line by line', async () => {
      const { container } = renderWithProviders(
        <DataImport {...defaultProps} />
      )

      const txtContent = 'Line 1\nLine 2\nLine 3'
      const file = new File([txtContent], 'test.txt', { type: 'text/plain' })

      await triggerFileUpload(container, file)

      await waitFor(
        () => {
          expect(mockImportData).toHaveBeenCalledWith('test-project-123', [
            { text: 'Line 1' },
            { text: 'Line 2' },
            { text: 'Line 3' },
          ])
        },
        { timeout: 3000 }
      )
    })

    it('should trim whitespace from TXT lines', async () => {
      const { container } = renderWithProviders(
        <DataImport {...defaultProps} />
      )

      const txtContent = '  Line 1  \n  Line 2  '
      const file = new File([txtContent], 'test.txt', { type: 'text/plain' })

      await triggerFileUpload(container, file)

      await waitFor(
        () => {
          expect(mockImportData).toHaveBeenCalledWith('test-project-123', [
            { text: 'Line 1' },
            { text: 'Line 2' },
          ])
        },
        { timeout: 3000 }
      )
    })

    it('should handle empty lines in TXT', async () => {
      const { container } = renderWithProviders(
        <DataImport {...defaultProps} />
      )

      const txtContent = 'Line 1\n\nLine 2\n\nLine 3'
      const file = new File([txtContent], 'test.txt', { type: 'text/plain' })

      await triggerFileUpload(container, file)

      await waitFor(
        () => {
          expect(mockImportData).toHaveBeenCalled()
        },
        { timeout: 3000 }
      )
    })
  })

  describe('Unsupported File Format', () => {
    it('should show error for unsupported file format', async () => {
      const { container } = renderWithProviders(
        <DataImport {...defaultProps} />
      )

      const file = new File(['content'], 'test.pdf', {
        type: 'application/pdf',
      })

      await triggerFileUpload(container, file)

      await waitFor(
        () => {
          expect(mockToastError).toHaveBeenCalledWith('Unsupported file format')
          expect(mockImportData).not.toHaveBeenCalled()
        },
        { timeout: 3000 }
      )
    })

    it('should show error for unsupported extension', async () => {
      const { container } = renderWithProviders(
        <DataImport {...defaultProps} />
      )

      const file = new File(['content'], 'test.docx', {
        type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      })

      await triggerFileUpload(container, file)

      await waitFor(
        () => {
          expect(mockToastError).toHaveBeenCalled()
          expect(mockImportData).not.toHaveBeenCalled()
        },
        { timeout: 3000 }
      )
    })
  })

  describe('Paste Import - JSON', () => {
    it('should import pasted JSON array', async () => {
      renderWithProviders(<DataImport {...defaultProps} />)

      const pasteTab = screen.getByText(/Paste Data/i)
      fireEvent.click(pasteTab)

      const textarea = screen.getByPlaceholderText(/Paste your data here/i)
      const jsonData = [{ text: 'Pasted 1' }, { text: 'Pasted 2' }]

      fireEvent.change(textarea, {
        target: { value: JSON.stringify(jsonData) },
      })

      const importButton = screen.getByRole('button', { name: /Import Data/i })
      fireEvent.click(importButton)

      await waitFor(() => {
        expect(mockImportData).toHaveBeenCalledWith(
          'test-project-123',
          jsonData
        )
      })

      expect(mockToastSuccess).toHaveBeenCalledWith(
        'Successfully imported 2 tasks'
      )
      expect(mockOnComplete).toHaveBeenCalled()
    })

    it('should import pasted single JSON object', async () => {
      renderWithProviders(<DataImport {...defaultProps} />)

      const pasteTab = screen.getByText(/Paste Data/i)
      fireEvent.click(pasteTab)

      const textarea = screen.getByPlaceholderText(/Paste your data here/i)
      const jsonData = { text: 'Single item' }

      fireEvent.change(textarea, {
        target: { value: JSON.stringify(jsonData) },
      })

      const importButton = screen.getByRole('button', { name: /Import Data/i })
      fireEvent.click(importButton)

      await waitFor(() => {
        expect(mockImportData).toHaveBeenCalledWith('test-project-123', [
          jsonData,
        ])
      })
    })
  })

  describe('Paste Import - Plain Text', () => {
    it('should import plain text as line items', async () => {
      renderWithProviders(<DataImport {...defaultProps} />)

      const pasteTab = screen.getByText(/Paste Data/i)
      fireEvent.click(pasteTab)

      const textarea = screen.getByPlaceholderText(/Paste your data here/i)
      fireEvent.change(textarea, {
        target: { value: 'Line 1\nLine 2\nLine 3' },
      })

      const importButton = screen.getByRole('button', { name: /Import Data/i })
      fireEvent.click(importButton)

      await waitFor(() => {
        expect(mockImportData).toHaveBeenCalledWith('test-project-123', [
          { text: 'Line 1' },
          { text: 'Line 2' },
          { text: 'Line 3' },
        ])
      })
    })

    it('should trim whitespace from pasted lines', async () => {
      renderWithProviders(<DataImport {...defaultProps} />)

      const pasteTab = screen.getByText(/Paste Data/i)
      fireEvent.click(pasteTab)

      const textarea = screen.getByPlaceholderText(/Paste your data here/i)
      fireEvent.change(textarea, {
        target: { value: '  Line 1  \n  Line 2  ' },
      })

      const importButton = screen.getByRole('button', { name: /Import Data/i })
      fireEvent.click(importButton)

      await waitFor(() => {
        expect(mockImportData).toHaveBeenCalledWith('test-project-123', [
          { text: 'Line 1' },
          { text: 'Line 2' },
        ])
      })
    })
  })

  describe('Paste Import - Error Handling', () => {
    it('should disable button when pasting empty content', () => {
      renderWithProviders(<DataImport {...defaultProps} />)

      const pasteTab = screen.getByText(/Paste Data/i)
      fireEvent.click(pasteTab)

      const importButton = screen.getByRole('button', { name: /Import Data/i })

      // Button should be disabled for empty content
      expect(importButton).toBeDisabled()
      expect(mockImportData).not.toHaveBeenCalled()
    })

    it('should disable button for whitespace-only content', () => {
      renderWithProviders(<DataImport {...defaultProps} />)

      const pasteTab = screen.getByText(/Paste Data/i)
      fireEvent.click(pasteTab)

      const textarea = screen.getByPlaceholderText(/Paste your data here/i)
      fireEvent.change(textarea, {
        target: { value: '   \n   \n   ' },
      })

      const importButton = screen.getByRole('button', { name: /Import Data/i })

      // Button should be disabled for whitespace-only content
      expect(importButton).toBeDisabled()
    })

    it('should handle paste import API errors', async () => {
      mockImportData.mockRejectedValueOnce(new Error('Import failed'))

      renderWithProviders(<DataImport {...defaultProps} />)

      const pasteTab = screen.getByText(/Paste Data/i)
      fireEvent.click(pasteTab)

      const textarea = screen.getByPlaceholderText(/Paste your data here/i)
      fireEvent.change(textarea, {
        target: { value: 'test data' },
      })

      const importButton = screen.getByRole('button', { name: /Import Data/i })
      fireEvent.click(importButton)

      await waitFor(() => {
        expect(mockToastError).toHaveBeenCalledWith('Failed to import data')
        expect(mockOnComplete).not.toHaveBeenCalled()
      })
    })

    it('should clear textarea after successful import', async () => {
      renderWithProviders(<DataImport {...defaultProps} />)

      const pasteTab = screen.getByText(/Paste Data/i)
      fireEvent.click(pasteTab)

      const textarea = screen.getByPlaceholderText(
        /Paste your data here/i
      ) as HTMLTextAreaElement

      fireEvent.change(textarea, {
        target: { value: '{"text": "test"}' },
      })

      const importButton = screen.getByRole('button', { name: /Import Data/i })
      fireEvent.click(importButton)

      await waitFor(() => {
        expect(textarea.value).toBe('')
      })
    })
  })

  describe('File Import Error Handling', () => {
    it('should handle import errors from store', async () => {
      mockImportData.mockRejectedValueOnce(new Error('Import failed'))

      const { container } = renderWithProviders(
        <DataImport {...defaultProps} />
      )

      const file = new File([JSON.stringify([{ text: 'test' }])], 'test.json', {
        type: 'application/json',
      })

      await triggerFileUpload(container, file)

      await waitFor(
        () => {
          expect(mockImportData).toHaveBeenCalled()
          expect(mockToastError).toHaveBeenCalledWith('Import failed')
          expect(mockOnComplete).not.toHaveBeenCalled()
        },
        { timeout: 3000 }
      )
    })

    it('should handle generic errors', async () => {
      mockImportData.mockRejectedValueOnce('String error')

      const { container } = renderWithProviders(
        <DataImport {...defaultProps} />
      )

      const file = new File([JSON.stringify([{ text: 'test' }])], 'test.json', {
        type: 'application/json',
      })

      await triggerFileUpload(container, file)

      await waitFor(
        () => {
          expect(mockToastError).toHaveBeenCalledWith('Failed to import file')
        },
        { timeout: 3000 }
      )
    })
  })

  describe('Import Statistics Display', () => {
    it('should display import statistics after file upload', async () => {
      const { container } = renderWithProviders(
        <DataImport {...defaultProps} />
      )

      const file = new File(
        [
          JSON.stringify([
            { text: 'Item 1' },
            { text: 'Item 2' },
            { text: 'Item 3' },
          ]),
        ],
        'test.json',
        { type: 'application/json' }
      )

      await triggerFileUpload(container, file)

      await waitFor(
        () => {
          expect(
            screen.getByText(/Successfully imported 3 of 3 tasks/i)
          ).toBeInTheDocument()
        },
        { timeout: 3000 }
      )
    })

    it('should display import statistics after paste import', async () => {
      renderWithProviders(<DataImport {...defaultProps} />)

      const pasteTab = screen.getByText(/Paste Data/i)
      fireEvent.click(pasteTab)

      const textarea = screen.getByPlaceholderText(/Paste your data here/i)
      fireEvent.change(textarea, {
        target: { value: 'Line 1\nLine 2\nLine 3\nLine 4\nLine 5' },
      })

      const importButton = screen.getByRole('button', { name: /Import Data/i })
      fireEvent.click(importButton)

      await waitFor(() => {
        expect(
          screen.getByText(/Successfully imported 5 of 5 tasks/i)
        ).toBeInTheDocument()
      })
    })
  })

  describe('Loading States', () => {
    it('should disable controls when loading', () => {
      mockLoading = true

      renderWithProviders(<DataImport {...defaultProps} />)

      const pasteTab = screen.getByText(/Paste Data/i)
      fireEvent.click(pasteTab)

      const textarea = screen.getByPlaceholderText(/Paste your data here/i)
      expect(textarea).toBeDisabled()

      const importButton = screen.getByRole('button', { name: /Importing.../i })
      expect(importButton).toBeDisabled()

      mockLoading = false
    })

    it('should disable paste button when textarea is empty', () => {
      renderWithProviders(<DataImport {...defaultProps} />)

      const pasteTab = screen.getByText(/Paste Data/i)
      fireEvent.click(pasteTab)

      const importButton = screen.getByRole('button', { name: /Import Data/i })
      expect(importButton).toBeDisabled()
    })

    it('should enable paste button when textarea has content', () => {
      renderWithProviders(<DataImport {...defaultProps} />)

      const pasteTab = screen.getByText(/Paste Data/i)
      fireEvent.click(pasteTab)

      const textarea = screen.getByPlaceholderText(/Paste your data here/i)
      fireEvent.change(textarea, {
        target: { value: 'some content' },
      })

      const importButton = screen.getByRole('button', { name: /Import Data/i })
      expect(importButton).not.toBeDisabled()
    })
  })

  describe('Tab Navigation', () => {
    it('should switch between file and paste tabs', () => {
      renderWithProviders(<DataImport {...defaultProps} />)

      expect(screen.getByText(/Drag & drop a file here/i)).toBeInTheDocument()

      const pasteTab = screen.getByText(/Paste Data/i)
      fireEvent.click(pasteTab)

      expect(
        screen.getByPlaceholderText(/Paste your data here/i)
      ).toBeInTheDocument()

      const fileTab = screen.getByText(/Upload File/i)
      fireEvent.click(fileTab)

      expect(screen.getByText(/Drag & drop a file here/i)).toBeInTheDocument()
    })
  })

  describe('Edge Cases', () => {
    it('should handle large JSON arrays', async () => {
      const { container } = renderWithProviders(
        <DataImport {...defaultProps} />
      )

      const largeArray = Array.from({ length: 100 }, (_, i) => ({
        text: `Item ${i + 1}`,
      }))
      const file = new File([JSON.stringify(largeArray)], 'large.json', {
        type: 'application/json',
      })

      await triggerFileUpload(container, file)

      await waitFor(
        () => {
          expect(mockImportData).toHaveBeenCalledWith(
            'test-project-123',
            largeArray
          )
        },
        { timeout: 3000 }
      )
    })

    it('should handle empty CSV file', async () => {
      const { container } = renderWithProviders(
        <DataImport {...defaultProps} />
      )

      const csvContent = 'text,category\n'
      const file = new File([csvContent], 'empty.csv', { type: 'text/csv' })

      await triggerFileUpload(container, file)

      await waitFor(
        () => {
          expect(mockImportData).toHaveBeenCalled()
        },
        { timeout: 3000 }
      )
    })

    it('should handle single line TXT file', async () => {
      const { container } = renderWithProviders(
        <DataImport {...defaultProps} />
      )

      const txtContent = 'Single line only'
      const file = new File([txtContent], 'single.txt', { type: 'text/plain' })

      await triggerFileUpload(container, file)

      await waitFor(
        () => {
          expect(mockImportData).toHaveBeenCalledWith('test-project-123', [
            { text: 'Single line only' },
          ])
        },
        { timeout: 3000 }
      )
    })
  })

  describe('Callback Invocation', () => {
    it('should call onComplete after successful file import', async () => {
      const onComplete = jest.fn()
      const { container } = renderWithProviders(
        <DataImport projectId="test-project-123" onComplete={onComplete} />
      )

      const file = new File(
        [JSON.stringify([{ text: 'Item 1' }])],
        'test.json',
        {
          type: 'application/json',
        }
      )

      await triggerFileUpload(container, file)

      await waitFor(
        () => {
          expect(onComplete).toHaveBeenCalled()
        },
        { timeout: 3000 }
      )
    })

    it('should call onComplete after successful paste import', async () => {
      const onComplete = jest.fn()
      renderWithProviders(
        <DataImport projectId="test-project-123" onComplete={onComplete} />
      )

      const pasteTab = screen.getByText(/Paste Data/i)
      fireEvent.click(pasteTab)

      const textarea = screen.getByPlaceholderText(/Paste your data here/i)
      fireEvent.change(textarea, {
        target: { value: 'test data' },
      })

      const importButton = screen.getByRole('button', { name: /Import Data/i })
      fireEvent.click(importButton)

      await waitFor(() => {
        expect(onComplete).toHaveBeenCalled()
      })
    })

    it('should work without onComplete callback', async () => {
      const { container } = renderWithProviders(
        <DataImport projectId="test-project-123" />
      )

      const file = new File(
        [JSON.stringify([{ text: 'Item 1' }])],
        'test.json',
        {
          type: 'application/json',
        }
      )

      await triggerFileUpload(container, file)

      await waitFor(
        () => {
          expect(mockImportData).toHaveBeenCalled()
        },
        { timeout: 3000 }
      )
    })
  })
})

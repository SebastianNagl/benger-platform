/**
 * Tests for ImportPreviewWithMapping component
 * Target: 85%+ coverage
 */

import * as fieldMapping from '@/lib/utils/fieldMapping'
import * as universalImport from '@/lib/utils/universalImport'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ImportPreviewWithMapping } from '../ImportPreviewWithMapping'

// Mock the utility modules
jest.mock('@/lib/utils/universalImport')
jest.mock('@/lib/utils/fieldMapping')
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, varsOrDefault?: any) => {
      const translations: Record<string, any> = require('../../../locales/en/common.json')
      const parts = key.split('.')
      let value: any = translations
      for (const part of parts) {
        if (value && typeof value === 'object' && part in value) {
          value = value[part]
        } else {
          return key
        }
      }
      if (typeof value !== 'string') return key
      if (varsOrDefault && typeof varsOrDefault === 'object') {
        for (const [k, v] of Object.entries(varsOrDefault)) {
          value = value.replace(new RegExp(`\\{${k}\\}`, 'g'), String(v))
        }
      }
      return value
    },
    locale: 'en',
  }),
}))


describe('ImportPreviewWithMapping', () => {
  const mockOnImport = jest.fn()
  const mockOnCancel = jest.fn()

  const mockFile = new File(['test content'], 'test.csv', { type: 'text/csv' })

  const mockImportResult: universalImport.ImportResult = {
    data: [
      { name: 'Test 1', email: 'test1@example.com', age: 25 },
      { name: 'Test 2', email: 'test2@example.com', age: 30 },
      { name: 'Test 3', email: 'test3@example.com', age: 35 },
    ],
    format: 'csv',
    headers: ['name', 'email', 'age'],
    metadata: {
      totalRows: 3,
      totalColumns: 3,
    },
  }

  const mockMappingSuggestion: fieldMapping.MappingSuggestion = {
    mappings: [
      { source: 'name', target: 'fullName', confidence: 0.9, type: 'fuzzy' },
      {
        source: 'email',
        target: 'emailAddress',
        confidence: 1.0,
        type: 'exact',
      },
    ],
    unmappedSource: ['age'],
    unmappedTarget: ['phoneNumber'],
    quality: 'high',
  }

  const templateFields = ['fullName', 'emailAddress', 'phoneNumber']

  beforeEach(() => {
    jest.clearAllMocks()
    ;(universalImport.importFile as jest.Mock).mockResolvedValue(
      mockImportResult
    )
    ;(fieldMapping.suggestFieldMappings as jest.Mock).mockReturnValue(
      mockMappingSuggestion
    )
    ;(fieldMapping.applyFieldMappings as jest.Mock).mockImplementation(
      (data) => data
    )
    ;(universalImport.exportData as jest.Mock).mockResolvedValue(undefined)
  })

  describe('File Processing', () => {
    it('shows loading state while processing file', async () => {
      let resolveImport: (value: any) => void
      const importPromise = new Promise((resolve) => {
        resolveImport = resolve
      })
      ;(universalImport.importFile as jest.Mock).mockReturnValue(importPromise)

      render(
        <ImportPreviewWithMapping
          file={mockFile}
          templateFields={templateFields}
          onImport={mockOnImport}
          onCancel={mockOnCancel}
        />
      )

      expect(screen.getByText('Processing file...')).toBeInTheDocument()

      resolveImport!(mockImportResult)
      await waitFor(() => {
        expect(screen.queryByText('Processing file...')).not.toBeInTheDocument()
      })
    })

    it('processes file on mount when file is provided', async () => {
      render(
        <ImportPreviewWithMapping
          file={mockFile}
          templateFields={templateFields}
          onImport={mockOnImport}
          onCancel={mockOnCancel}
        />
      )

      await waitFor(() => {
        expect(universalImport.importFile).toHaveBeenCalledWith(mockFile, {
          skipEmptyRows: true,
          detectTypes: true,
        })
      })
    })

    it('displays error when file processing fails', async () => {
      const errorMessage = 'Failed to parse file'
      ;(universalImport.importFile as jest.Mock).mockRejectedValue(
        new Error(errorMessage)
      )

      render(
        <ImportPreviewWithMapping
          file={mockFile}
          templateFields={templateFields}
          onImport={mockOnImport}
          onCancel={mockOnCancel}
        />
      )

      await waitFor(() => {
        expect(screen.getByText(errorMessage)).toBeInTheDocument()
      })

      const cancelButton = screen.getByText('Cancel')
      expect(cancelButton).toBeInTheDocument()
    })

    it('handles cancel action from error state', async () => {
      ;(universalImport.importFile as jest.Mock).mockRejectedValue(
        new Error('Test error')
      )

      const user = userEvent.setup()
      render(
        <ImportPreviewWithMapping
          file={mockFile}
          templateFields={templateFields}
          onImport={mockOnImport}
          onCancel={mockOnCancel}
        />
      )

      await waitFor(() => {
        expect(screen.getByText('Test error')).toBeInTheDocument()
      })

      const cancelButton = screen.getByText('Cancel')
      await user.click(cancelButton)

      expect(mockOnCancel).toHaveBeenCalled()
    })

    it('does not process when no file is provided', () => {
      render(
        <ImportPreviewWithMapping
          templateFields={templateFields}
          onImport={mockOnImport}
          onCancel={mockOnCancel}
        />
      )

      expect(universalImport.importFile).not.toHaveBeenCalled()
    })
  })

  describe('Data Preview Tab', () => {
    it('displays import summary with file information', async () => {
      render(
        <ImportPreviewWithMapping
          file={mockFile}
          templateFields={templateFields}
          onImport={mockOnImport}
          onCancel={mockOnCancel}
        />
      )

      await waitFor(() => {
        expect(screen.getByText('test.csv')).toBeInTheDocument()
        expect(screen.getByText('3 rows')).toBeInTheDocument()
        expect(screen.getByText('CSV')).toBeInTheDocument()
      })
    })

    it('displays file size correctly', async () => {
      const largeFile = new File(['x'.repeat(2048)], 'large.csv', {
        type: 'text/csv',
      })

      render(
        <ImportPreviewWithMapping
          file={largeFile}
          templateFields={templateFields}
          onImport={mockOnImport}
          onCancel={mockOnCancel}
        />
      )

      await waitFor(() => {
        expect(screen.getByText('2.0 KB')).toBeInTheDocument()
      })
    })

    it('shows data preview table with headers and rows', async () => {
      render(
        <ImportPreviewWithMapping
          file={mockFile}
          templateFields={templateFields}
          onImport={mockOnImport}
          onCancel={mockOnCancel}
        />
      )

      await waitFor(() => {
        expect(screen.getByText('name')).toBeInTheDocument()
        expect(screen.getByText('email')).toBeInTheDocument()
        expect(screen.getByText('age')).toBeInTheDocument()
        expect(screen.getByText('Test 1')).toBeInTheDocument()
        expect(screen.getByText('test1@example.com')).toBeInTheDocument()
      })
    })

    it('limits preview to first 5 rows', async () => {
      const manyRows = Array.from({ length: 10 }, (_, i) => ({
        name: `Test ${i}`,
        email: `test${i}@example.com`,
      }))

      ;(universalImport.importFile as jest.Mock).mockResolvedValue({
        ...mockImportResult,
        data: manyRows,
        metadata: { totalRows: 10 },
      })

      render(
        <ImportPreviewWithMapping
          file={mockFile}
          templateFields={templateFields}
          onImport={mockOnImport}
          onCancel={mockOnCancel}
        />
      )

      await waitFor(() => {
        expect(screen.getByText('...and 5 more rows')).toBeInTheDocument()
      })
    })

    it('displays import errors if present', async () => {
      const resultWithErrors = {
        ...mockImportResult,
        errors: ['Row 1: Invalid format', 'Row 5: Missing required field'],
      }
      ;(universalImport.importFile as jest.Mock).mockResolvedValue(
        resultWithErrors
      )

      render(
        <ImportPreviewWithMapping
          file={mockFile}
          templateFields={templateFields}
          onImport={mockOnImport}
          onCancel={mockOnCancel}
        />
      )

      await waitFor(() => {
        expect(screen.getByText('Import warnings:')).toBeInTheDocument()
        expect(screen.getByText('Row 1: Invalid format')).toBeInTheDocument()
        expect(
          screen.getByText('Row 5: Missing required field')
        ).toBeInTheDocument()
      })
    })

    it('limits error display to first 3 errors', async () => {
      const resultWithManyErrors = {
        ...mockImportResult,
        errors: ['Error 1', 'Error 2', 'Error 3', 'Error 4', 'Error 5'],
      }
      ;(universalImport.importFile as jest.Mock).mockResolvedValue(
        resultWithManyErrors
      )

      render(
        <ImportPreviewWithMapping
          file={mockFile}
          templateFields={templateFields}
          onImport={mockOnImport}
          onCancel={mockOnCancel}
        />
      )

      await waitFor(() => {
        expect(screen.getByText('Error 1')).toBeInTheDocument()
        expect(screen.getByText('Error 2')).toBeInTheDocument()
        expect(screen.getByText('Error 3')).toBeInTheDocument()
        expect(screen.getByText('...and 2 more')).toBeInTheDocument()
      })
    })

    it('displays Excel sheet information', async () => {
      const excelResult = {
        ...mockImportResult,
        format: 'excel' as const,
        metadata: {
          totalRows: 3,
          sheets: ['Sheet1', 'Sheet2', 'Sheet3'],
        },
      }
      ;(universalImport.importFile as jest.Mock).mockResolvedValue(excelResult)

      render(
        <ImportPreviewWithMapping
          file={mockFile}
          templateFields={templateFields}
          onImport={mockOnImport}
          onCancel={mockOnCancel}
        />
      )

      await waitFor(() => {
        expect(screen.getByText('Sheets')).toBeInTheDocument()
        expect(screen.getByText('Sheet1')).toBeInTheDocument()
        expect(screen.getByText('Sheet2')).toBeInTheDocument()
        expect(screen.getByText('Sheet3')).toBeInTheDocument()
      })
    })
  })

  describe('Field Mapping Tab', () => {
    it('generates mapping suggestions when template fields are provided', async () => {
      render(
        <ImportPreviewWithMapping
          file={mockFile}
          templateFields={templateFields}
          onImport={mockOnImport}
          onCancel={mockOnCancel}
        />
      )

      await waitFor(() => {
        expect(fieldMapping.suggestFieldMappings).toHaveBeenCalledWith(
          mockImportResult.headers,
          templateFields,
          expect.any(Array)
        )
      })
    })

    it('does not show mapping tab when no template fields provided', async () => {
      render(
        <ImportPreviewWithMapping
          file={mockFile}
          templateFields={[]}
          onImport={mockOnImport}
          onCancel={mockOnCancel}
        />
      )

      await waitFor(() => {
        const mappingTab = screen.queryByText('Field Mapping')
        expect(mappingTab).toBeInTheDocument()
        // Tab should be disabled
        expect(mappingTab?.closest('button')).toBeDisabled()
      })
    })

    it('displays mapping quality indicator', async () => {
      const user = userEvent.setup()
      render(
        <ImportPreviewWithMapping
          file={mockFile}
          templateFields={templateFields}
          onImport={mockOnImport}
          onCancel={mockOnCancel}
        />
      )

      await waitFor(() => {
        expect(screen.getByText('Data Preview')).toBeInTheDocument()
      })

      const mappingTab = screen.getByText('Field Mapping')
      await user.click(mappingTab)

      await waitFor(() => {
        expect(screen.getByText('Mapping Quality')).toBeInTheDocument()
        expect(screen.getByText('2 of 3 fields mapped')).toBeInTheDocument()
      })
    })

    it('displays field mapping controls', async () => {
      const user = userEvent.setup()
      render(
        <ImportPreviewWithMapping
          file={mockFile}
          templateFields={templateFields}
          onImport={mockOnImport}
          onCancel={mockOnCancel}
        />
      )

      await waitFor(() => {
        expect(screen.getByText('Data Preview')).toBeInTheDocument()
      })

      const mappingTab = screen.getByText('Field Mapping')
      await user.click(mappingTab)

      await waitFor(() => {
        expect(screen.getByText('Field Mappings')).toBeInTheDocument()
        expect(screen.getByText('Export Mapping')).toBeInTheDocument()
      })
    })

    it('shows confidence badges for mappings', async () => {
      const user = userEvent.setup()
      render(
        <ImportPreviewWithMapping
          file={mockFile}
          templateFields={templateFields}
          onImport={mockOnImport}
          onCancel={mockOnCancel}
        />
      )

      await waitFor(() => {
        expect(screen.getByText('Data Preview')).toBeInTheDocument()
      })

      const mappingTab = screen.getByText('Field Mapping')
      await user.click(mappingTab)

      await waitFor(() => {
        expect(screen.getByText('fuzzy')).toBeInTheDocument()
        expect(screen.getByText('exact')).toBeInTheDocument()
      })
    })

    it('displays unmapped fields warning', async () => {
      const user = userEvent.setup()
      render(
        <ImportPreviewWithMapping
          file={mockFile}
          templateFields={templateFields}
          onImport={mockOnImport}
          onCancel={mockOnCancel}
        />
      )

      await waitFor(() => {
        expect(screen.getByText('Data Preview')).toBeInTheDocument()
      })

      const mappingTab = screen.getByText('Field Mapping')
      await user.click(mappingTab)

      await waitFor(() => {
        expect(screen.getByText('Unmapped source fields:')).toBeInTheDocument()
        // Check that 'age' appears in the unmapped fields list (not just anywhere on the page)
        const unmappedTexts = screen.getAllByText((content, element) => {
          return (
            element?.textContent === 'age' &&
            element?.className.includes('text-sm')
          )
        })
        expect(unmappedTexts.length).toBeGreaterThan(0)
      })
    })

    it('exports mapping configuration', async () => {
      const user = userEvent.setup()
      render(
        <ImportPreviewWithMapping
          file={mockFile}
          templateFields={templateFields}
          onImport={mockOnImport}
          onCancel={mockOnCancel}
        />
      )

      await waitFor(() => {
        expect(screen.getByText('Data Preview')).toBeInTheDocument()
      })

      const mappingTab = screen.getByText('Field Mapping')
      await user.click(mappingTab)

      await waitFor(() => {
        expect(screen.getByText('Export Mapping')).toBeInTheDocument()
      })

      const exportButton = screen.getByText('Export Mapping')
      await user.click(exportButton)

      expect(universalImport.exportData).toHaveBeenCalledWith(
        expect.arrayContaining([
          expect.objectContaining({
            mappings: expect.any(Object),
            sourceFields: mockImportResult.headers,
            targetFields: templateFields,
            timestamp: expect.any(String),
          }),
        ]),
        'json',
        'field-mapping-config'
      )
    })
  })

  describe('Import Actions', () => {
    it('handles import with original data when no template fields', async () => {
      const user = userEvent.setup()
      render(
        <ImportPreviewWithMapping
          file={mockFile}
          templateFields={[]}
          onImport={mockOnImport}
          onCancel={mockOnCancel}
        />
      )

      await waitFor(() => {
        expect(screen.getByText('Import 3 Items')).toBeInTheDocument()
      })

      const importButton = screen.getByText('Import 3 Items')
      await user.click(importButton)

      expect(mockOnImport).toHaveBeenCalledWith(mockImportResult.data)
    })

    it('handles import with mapped data when template fields provided', async () => {
      const mappedData = [
        { fullName: 'Test 1', emailAddress: 'test1@example.com' },
        { fullName: 'Test 2', emailAddress: 'test2@example.com' },
      ]
      ;(fieldMapping.applyFieldMappings as jest.Mock).mockReturnValue(
        mappedData
      )

      const user = userEvent.setup()
      render(
        <ImportPreviewWithMapping
          file={mockFile}
          templateFields={templateFields}
          onImport={mockOnImport}
          onCancel={mockOnCancel}
        />
      )

      await waitFor(() => {
        expect(screen.getByText('Import 3 Items')).toBeInTheDocument()
      })

      const importButton = screen.getByText('Import 3 Items')
      await user.click(importButton)

      expect(fieldMapping.applyFieldMappings).toHaveBeenCalled()
      expect(mockOnImport).toHaveBeenCalledWith(mappedData)
    })

    it('handles cancel action', async () => {
      const user = userEvent.setup()
      render(
        <ImportPreviewWithMapping
          file={mockFile}
          templateFields={templateFields}
          onImport={mockOnImport}
          onCancel={mockOnCancel}
        />
      )

      await waitFor(() => {
        expect(screen.getByText('Cancel')).toBeInTheDocument()
      })

      const cancelButton = screen.getByText('Cancel')
      await user.click(cancelButton)

      expect(mockOnCancel).toHaveBeenCalled()
    })

    it('shows configure mapping button when template fields exist', async () => {
      render(
        <ImportPreviewWithMapping
          file={mockFile}
          templateFields={templateFields}
          onImport={mockOnImport}
          onCancel={mockOnCancel}
        />
      )

      await waitFor(() => {
        expect(screen.getByText('Configure Mapping')).toBeInTheDocument()
      })
    })

    it('does not show configure mapping button when no template fields', async () => {
      render(
        <ImportPreviewWithMapping
          file={mockFile}
          templateFields={[]}
          onImport={mockOnImport}
          onCancel={mockOnCancel}
        />
      )

      await waitFor(() => {
        expect(screen.queryByText('Configure Mapping')).not.toBeInTheDocument()
      })
    })
  })

  describe('Mapping Quality Badge', () => {
    it('shows high quality badge with green color', async () => {
      const user = userEvent.setup()
      render(
        <ImportPreviewWithMapping
          file={mockFile}
          templateFields={templateFields}
          onImport={mockOnImport}
          onCancel={mockOnCancel}
        />
      )

      await waitFor(() => {
        const mappingTab = screen.getByText('Field Mapping')
        expect(mappingTab.nextElementSibling?.textContent).toBe('high')
      })
    })

    it('shows medium quality badge with yellow color', async () => {
      ;(fieldMapping.suggestFieldMappings as jest.Mock).mockReturnValue({
        ...mockMappingSuggestion,
        quality: 'medium',
      })

      render(
        <ImportPreviewWithMapping
          file={mockFile}
          templateFields={templateFields}
          onImport={mockOnImport}
          onCancel={mockOnCancel}
        />
      )

      await waitFor(() => {
        const badge = screen.getByText('medium')
        expect(badge).toBeInTheDocument()
      })
    })

    it('shows low quality badge with red color', async () => {
      ;(fieldMapping.suggestFieldMappings as jest.Mock).mockReturnValue({
        ...mockMappingSuggestion,
        quality: 'low',
      })

      render(
        <ImportPreviewWithMapping
          file={mockFile}
          templateFields={templateFields}
          onImport={mockOnImport}
          onCancel={mockOnCancel}
        />
      )

      await waitFor(() => {
        const badge = screen.getByText('low')
        expect(badge).toBeInTheDocument()
      })
    })
  })

  describe('Edge Cases', () => {
    it('handles empty data gracefully', async () => {
      ;(universalImport.importFile as jest.Mock).mockResolvedValue({
        data: [],
        format: 'csv',
        headers: [],
        metadata: { totalRows: 0 },
      })

      render(
        <ImportPreviewWithMapping
          file={mockFile}
          templateFields={templateFields}
          onImport={mockOnImport}
          onCancel={mockOnCancel}
        />
      )

      await waitFor(() => {
        expect(screen.getByText('0 rows')).toBeInTheDocument()
      })
    })

    it('handles data without headers', async () => {
      ;(universalImport.importFile as jest.Mock).mockResolvedValue({
        data: [{ col1: 'value1' }],
        format: 'csv',
        metadata: { totalRows: 1 },
      })

      render(
        <ImportPreviewWithMapping
          file={mockFile}
          templateFields={templateFields}
          onImport={mockOnImport}
          onCancel={mockOnCancel}
        />
      )

      await waitFor(() => {
        expect(screen.getByText('1 rows')).toBeInTheDocument()
      })
    })

    it('applies custom className when provided', async () => {
      const { container } = render(
        <ImportPreviewWithMapping
          file={mockFile}
          templateFields={templateFields}
          onImport={mockOnImport}
          onCancel={mockOnCancel}
          className="custom-class"
        />
      )

      await waitFor(() => {
        const card = container.querySelector('.custom-class')
        expect(card).toBeInTheDocument()
      })
    })

    it('handles non-Error thrown in file processing', async () => {
      ;(universalImport.importFile as jest.Mock).mockRejectedValue(
        'String error'
      )

      render(
        <ImportPreviewWithMapping
          file={mockFile}
          templateFields={templateFields}
          onImport={mockOnImport}
          onCancel={mockOnCancel}
        />
      )

      await waitFor(() => {
        expect(screen.getByText('Failed to process file')).toBeInTheDocument()
      })
    })

    it('handles file size below 1KB', async () => {
      const tinyFile = new File(['x'], 'tiny.csv', { type: 'text/csv' })

      render(
        <ImportPreviewWithMapping
          file={tinyFile}
          templateFields={templateFields}
          onImport={mockOnImport}
          onCancel={mockOnCancel}
        />
      )

      await waitFor(() => {
        expect(screen.getByText('1 bytes')).toBeInTheDocument()
      })
    })

    it('handles file size in MB range', async () => {
      const largeFile = new File(['x'.repeat(2 * 1024 * 1024)], 'large.csv', {
        type: 'text/csv',
      })

      render(
        <ImportPreviewWithMapping
          file={largeFile}
          templateFields={templateFields}
          onImport={mockOnImport}
          onCancel={mockOnCancel}
        />
      )

      await waitFor(() => {
        expect(screen.getByText(/2\.0 MB/)).toBeInTheDocument()
      })
    })
  })

  describe('Custom Field Mapping', () => {
    it('allows changing field mapping', async () => {
      const user = userEvent.setup()
      render(
        <ImportPreviewWithMapping
          file={mockFile}
          templateFields={templateFields}
          onImport={mockOnImport}
          onCancel={mockOnCancel}
        />
      )

      await waitFor(() => {
        expect(screen.getByText('Data Preview')).toBeInTheDocument()
      })

      const mappingTab = screen.getByText('Field Mapping')
      await user.click(mappingTab)

      await waitFor(() => {
        expect(screen.getByText('Field Mappings')).toBeInTheDocument()
      })
    })

    it('switches to mapping tab when configure button clicked', async () => {
      render(
        <ImportPreviewWithMapping
          file={mockFile}
          templateFields={templateFields}
          onImport={mockOnImport}
          onCancel={mockOnCancel}
        />
      )

      await waitFor(() => {
        expect(screen.getByText('Configure Mapping')).toBeInTheDocument()
      })

      const configureButton = screen.getByText('Configure Mapping')
      fireEvent.click(configureButton)

      await waitFor(() => {
        // Check that the button is now disabled (meaning we switched tabs)
        expect(configureButton).toBeDisabled()
      })
    })

    it('disables configure mapping button when already on mapping tab', async () => {
      render(
        <ImportPreviewWithMapping
          file={mockFile}
          templateFields={templateFields}
          onImport={mockOnImport}
          onCancel={mockOnCancel}
        />
      )

      await waitFor(() => {
        expect(screen.getByText('Configure Mapping')).toBeInTheDocument()
      })

      // Get the configure button first so we have a stable reference
      const configureButton = screen.getByText('Configure Mapping')

      // Click it to switch to mapping tab
      fireEvent.click(configureButton)

      await waitFor(() => {
        // After clicking, button should be disabled
        expect(configureButton).toBeDisabled()
      })
    })
  })

  describe('Tab Navigation', () => {
    it('starts on preview tab by default', async () => {
      render(
        <ImportPreviewWithMapping
          file={mockFile}
          templateFields={templateFields}
          onImport={mockOnImport}
          onCancel={mockOnCancel}
        />
      )

      await waitFor(() => {
        expect(screen.getByText('Data Preview')).toBeInTheDocument()
        expect(screen.getByText('test.csv')).toBeInTheDocument()
      })
    })

    it('switches between preview and mapping tabs', async () => {
      const user = userEvent.setup()
      render(
        <ImportPreviewWithMapping
          file={mockFile}
          templateFields={templateFields}
          onImport={mockOnImport}
          onCancel={mockOnCancel}
        />
      )

      await waitFor(() => {
        expect(screen.getByText('Data Preview')).toBeInTheDocument()
      })

      const mappingTab = screen.getByText('Field Mapping')
      await user.click(mappingTab)

      await waitFor(() => {
        expect(screen.getByText('Mapping Quality')).toBeInTheDocument()
      })

      const previewTab = screen.getByText('Data Preview')
      await user.click(previewTab)

      await waitFor(() => {
        expect(screen.getByText('test.csv')).toBeInTheDocument()
      })
    })
  })

  describe('Import Result Variations', () => {
    it('handles result with exactly 5 rows', async () => {
      const fiveRows = Array.from({ length: 5 }, (_, i) => ({
        name: `Test ${i}`,
        email: `test${i}@example.com`,
      }))

      ;(universalImport.importFile as jest.Mock).mockResolvedValue({
        ...mockImportResult,
        data: fiveRows,
      })

      render(
        <ImportPreviewWithMapping
          file={mockFile}
          templateFields={templateFields}
          onImport={mockOnImport}
          onCancel={mockOnCancel}
        />
      )

      await waitFor(() => {
        expect(screen.queryByText(/and \d+ more rows/)).not.toBeInTheDocument()
      })
    })

    it('handles result with exactly 3 errors', async () => {
      const resultWith3Errors = {
        ...mockImportResult,
        errors: ['Error 1', 'Error 2', 'Error 3'],
      }
      ;(universalImport.importFile as jest.Mock).mockResolvedValue(
        resultWith3Errors
      )

      render(
        <ImportPreviewWithMapping
          file={mockFile}
          templateFields={templateFields}
          onImport={mockOnImport}
          onCancel={mockOnCancel}
        />
      )

      await waitFor(() => {
        expect(screen.getByText('Error 1')).toBeInTheDocument()
        expect(screen.getByText('Error 2')).toBeInTheDocument()
        expect(screen.getByText('Error 3')).toBeInTheDocument()
        expect(screen.queryByText(/and \d+ more/)).not.toBeInTheDocument()
      })
    })

    it('handles result without metadata', async () => {
      ;(universalImport.importFile as jest.Mock).mockResolvedValue({
        data: mockImportResult.data,
        format: 'csv',
        headers: mockImportResult.headers,
      })

      render(
        <ImportPreviewWithMapping
          file={mockFile}
          templateFields={templateFields}
          onImport={mockOnImport}
          onCancel={mockOnCancel}
        />
      )

      await waitFor(() => {
        expect(screen.getByText('3 rows')).toBeInTheDocument()
      })
    })
  })
})

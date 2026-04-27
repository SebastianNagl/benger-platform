/**
 * @jest-environment jsdom
 */

import { ImportDataModal } from '@/components/projects/ImportDataModal'
import { useToast } from '@/components/shared/Toast'
import { useProgress } from '@/contexts/ProgressContext'
import { projectsAPI } from '@/lib/api/projects'
import { useProjectStore } from '@/stores/projectStore'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

// Mock dependencies
jest.mock('@/contexts/ProgressContext', () => ({
  useProgress: jest.fn(),
}))

jest.mock('@/components/shared/Toast', () => ({
  useToast: jest.fn(),
}))

jest.mock('@/lib/api/projects', () => ({
  projectsAPI: {
    importData: jest.fn(),
  },
}))

jest.mock('@/stores/projectStore', () => ({
  useProjectStore: jest.fn(),
}))

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, params?: any) => {
      const translations: Record<string, string> = {
        'projects.data.import': 'Import Data',
        'projects.data.importSuccess': 'Data imported successfully',
        'projects.data.importFailed': 'Failed to import data',
        'tasks.importModal.description': 'Import data to create tasks in your project',
        'tasks.importModal.fieldRequirements': 'Data Field Requirements',
        'tasks.importModal.fieldRequirementsDescription': 'Your template requires these data fields',
        'tasks.importModal.missingFieldsWarning': 'Missing required fields will cause validation errors',
        'tasks.importModal.uploadFiles': 'Upload Files',
        'tasks.importModal.pasteData': 'Paste Data',
        'tasks.importModal.cloudStorage': 'Cloud Storage',
        'tasks.importModal.dropFilesHere': 'Drop files here or click to upload',
        'tasks.importModal.supportedFormats': 'Supports JSON, CSV, TSV, and plain text files',
        'tasks.importModal.chooseFiles': 'Choose Files',
        'tasks.importModal.pasteYourData': 'Paste your data',
        'tasks.importModal.pastePlaceholder': 'Paste JSON, CSV, or plain text data...',
        'tasks.importModal.csvTip': 'Tip: For CSV data, include a header row with column names',
        'tasks.importModal.cloudComingSoon': 'Cloud storage integration coming soon',
        'tasks.importModal.validationError': 'Import Validation Error',
        'tasks.importModal.validationErrorDescription': 'The imported data fields do not match the template requirements',
        'tasks.importModal.importAnyway': 'Import Anyway',
        'tasks.importModal.orUseFieldMapping': 'Or use field mapping below',
        'common.remove': 'Remove',
        'common.cancel': 'Cancel',
        'common.notes': 'Notes',
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

jest.mock('@/components/tasks/ImportPreviewWithMapping', () => ({
  ImportPreviewWithMapping: ({
    onImport,
    onCancel,
  }: {
    onImport: (data: any[]) => void
    onCancel: () => void
  }) => (
    <div data-testid="import-preview-with-mapping">
      <button onClick={() => onImport([{ data: { text: 'mapped data' } }])}>
        Import Mapped
      </button>
      <button onClick={onCancel}>Cancel Mapping</button>
    </div>
  ),
}))

describe('ImportDataModal', () => {
  const mockOnClose = jest.fn()
  const mockOnImportComplete = jest.fn()
  const mockAddToast = jest.fn()
  const mockStartProgress = jest.fn()
  const mockUpdateProgress = jest.fn()
  const mockCompleteProgress = jest.fn()
  const mockFetchProject = jest.fn()

  const defaultProps = {
    isOpen: true,
    onClose: mockOnClose,
    projectId: 'test-project-123',
    onImportComplete: mockOnImportComplete,
  }

  const mockProject = {
    id: 'test-project-123',
    title: 'Test Project',
    label_config: '<View><Text name="text" value="$text"/></View>',
    description: 'Test description',
    created_at: '2025-01-01T00:00:00Z',
    updated_at: '2025-01-01T00:00:00Z',
  }

  beforeEach(() => {
    jest.clearAllMocks()
    ;(useToast as jest.Mock).mockReturnValue({
      addToast: mockAddToast,
    })
    ;(useProgress as jest.Mock).mockReturnValue({
      startProgress: mockStartProgress,
      updateProgress: mockUpdateProgress,
      completeProgress: mockCompleteProgress,
    })
    ;(useProjectStore as jest.Mock).mockReturnValue({
      fetchProject: mockFetchProject,
    })
    ;(projectsAPI.importData as jest.Mock).mockResolvedValue({
      created: 5,
    })

    mockFetchProject.mockResolvedValue(mockProject)
  })

  describe('Modal Rendering', () => {
    it('renders modal when isOpen is true', () => {
      render(<ImportDataModal {...defaultProps} />)

      expect(
        screen.getByRole('heading', { name: 'Import Data' })
      ).toBeInTheDocument()
      expect(
        screen.getByText(/Import data to create tasks in your project/i)
      ).toBeInTheDocument()
    })

    it('does not render modal when isOpen is false', () => {
      render(<ImportDataModal {...defaultProps} isOpen={false} />)

      expect(screen.queryByText('Import Data')).not.toBeInTheDocument()
    })

    it('fetches project template fields when modal opens', async () => {
      render(<ImportDataModal {...defaultProps} />)

      await waitFor(() => {
        expect(mockFetchProject).toHaveBeenCalledWith('test-project-123')
      })
    })

    it('displays template field requirements', async () => {
      render(<ImportDataModal {...defaultProps} />)

      await waitFor(() => {
        expect(screen.getByText('Data Field Requirements')).toBeInTheDocument()
      })

      expect(screen.getByText('$text')).toBeInTheDocument()
    })
  })

  describe('Tab Navigation', () => {
    it('renders all three tabs', () => {
      render(<ImportDataModal {...defaultProps} />)

      expect(screen.getByText('Upload Files')).toBeInTheDocument()
      expect(screen.getByText('Paste Data')).toBeInTheDocument()
      expect(screen.getByText('Cloud Storage')).toBeInTheDocument()
    })

    it('shows upload tab content by default', () => {
      render(<ImportDataModal {...defaultProps} />)

      expect(
        screen.getByText('Drop files here or click to upload')
      ).toBeInTheDocument()
    })

    it('switches to paste tab when clicked', async () => {
      const user = userEvent.setup()
      render(<ImportDataModal {...defaultProps} />)

      await user.click(screen.getByText('Paste Data'))

      expect(
        screen.getByPlaceholderText('Paste JSON, CSV, or plain text data...')
      ).toBeInTheDocument()
    })

    it('shows cloud storage coming soon message', async () => {
      const user = userEvent.setup()
      render(<ImportDataModal {...defaultProps} />)

      await user.click(screen.getByText('Cloud Storage'))

      expect(
        screen.getByText('Cloud storage integration coming soon')
      ).toBeInTheDocument()
    })
  })

  describe('File Upload', () => {
    it('handles file selection via input', async () => {
      render(<ImportDataModal {...defaultProps} />)

      const file = new File(['{"data": {"text": "test"}}'], 'test.json', {
        type: 'application/json',
      })

      const input = document.querySelector(
        'input[type="file"]'
      ) as HTMLInputElement

      await userEvent.upload(input, file)

      await waitFor(() => {
        expect(screen.getByText('test.json')).toBeInTheDocument()
      })
    })

    it('displays selected file information', async () => {
      render(<ImportDataModal {...defaultProps} />)

      const file = new File(['test content'], 'test.txt', {
        type: 'text/plain',
      })
      const input = document.querySelector(
        'input[type="file"]'
      ) as HTMLInputElement

      await userEvent.upload(input, file)

      await waitFor(() => {
        expect(screen.getByText('test.txt')).toBeInTheDocument()
        expect(screen.getByText(/KB/)).toBeInTheDocument()
      })
    })

    it('allows removing selected file', async () => {
      const user = userEvent.setup()
      render(<ImportDataModal {...defaultProps} />)

      const file = new File(['test'], 'test.txt', { type: 'text/plain' })
      const input = document.querySelector(
        'input[type="file"]'
      ) as HTMLInputElement

      await userEvent.upload(input, file)
      await waitFor(() => screen.getByText('test.txt'))

      const removeButton = screen.getByRole('button', { name: /Remove/i })
      await user.click(removeButton)

      expect(screen.queryByText('test.txt')).not.toBeInTheDocument()
      expect(
        screen.getByText('Drop files here or click to upload')
      ).toBeInTheDocument()
    })

    it('handles file drag and drop', async () => {
      render(<ImportDataModal {...defaultProps} />)

      const file = new File(['{"data": {"text": "test"}}'], 'dropped.json', {
        type: 'application/json',
      })

      const dropZone = screen.getByText(
        'Drop files here or click to upload'
      ).parentElement!

      fireEvent.dragOver(dropZone)
      fireEvent.drop(dropZone, {
        dataTransfer: { files: [file] },
      })

      await waitFor(() => {
        expect(screen.getByText('dropped.json')).toBeInTheDocument()
      })
    })

    it('clears pasted data when file is selected', async () => {
      render(<ImportDataModal {...defaultProps} />)

      const user = userEvent.setup()
      await user.click(screen.getByText('Paste Data'))

      const textarea = screen.getByPlaceholderText(
        'Paste JSON, CSV, or plain text data...'
      )
      await user.type(textarea, 'some pasted data')

      await user.click(screen.getByText('Upload Files'))

      const file = new File(['test'], 'test.txt', { type: 'text/plain' })
      const input = document.querySelector(
        'input[type="file"]'
      ) as HTMLInputElement
      await userEvent.upload(input, file)

      await waitFor(() => {
        expect(screen.getByText('test.txt')).toBeInTheDocument()
      })
    })
  })

  describe('Paste Data', () => {
    it('accepts pasted data in textarea', async () => {
      const user = userEvent.setup()
      render(<ImportDataModal {...defaultProps} />)

      await user.click(screen.getByText('Paste Data'))

      const textarea = screen.getByPlaceholderText(
        'Paste JSON, CSV, or plain text data...'
      )
      fireEvent.change(textarea, {
        target: { value: '{"data": {"text": "pasted"}}' },
      })

      expect(textarea).toHaveValue('{"data": {"text": "pasted"}}')
    })

    it('clears file selection when data is pasted', async () => {
      const user = userEvent.setup()
      render(<ImportDataModal {...defaultProps} />)

      // First select a file
      const file = new File(['test'], 'test.txt', { type: 'text/plain' })
      const input = document.querySelector(
        'input[type="file"]'
      ) as HTMLInputElement
      await userEvent.upload(input, file)

      await waitFor(() => screen.getByText('test.txt'))

      // Then paste data
      await user.click(screen.getByText('Paste Data'))
      const textarea = screen.getByPlaceholderText(
        'Paste JSON, CSV, or plain text data...'
      )
      await user.type(textarea, 'some text')

      // File should be cleared
      await user.click(screen.getByText('Upload Files'))
      expect(screen.queryByText('test.txt')).not.toBeInTheDocument()
    })
  })

  describe('Import Button State', () => {
    it('disables import button when no data is provided', () => {
      render(<ImportDataModal {...defaultProps} />)

      const importButton = screen.getByRole('button', { name: /Import Data/i })
      expect(importButton).toBeDisabled()
    })

    it('enables import button when file is selected', async () => {
      render(<ImportDataModal {...defaultProps} />)

      const file = new File(['test'], 'test.txt', { type: 'text/plain' })
      const input = document.querySelector(
        'input[type="file"]'
      ) as HTMLInputElement

      await userEvent.upload(input, file)

      await waitFor(() => {
        const importButton = screen.getByRole('button', {
          name: /Import Data/i,
        })
        expect(importButton).toBeEnabled()
      })
    })

    it('enables import button when pasted data is provided', async () => {
      const user = userEvent.setup()
      render(<ImportDataModal {...defaultProps} />)

      await user.click(screen.getByText('Paste Data'))
      const textarea = screen.getByPlaceholderText(
        'Paste JSON, CSV, or plain text data...'
      )
      await user.type(textarea, 'test data')

      const importButton = screen.getByRole('button', { name: /Import Data/i })
      expect(importButton).toBeEnabled()
    })

    it('disables buttons during import', async () => {
      const user = userEvent.setup()
      render(<ImportDataModal {...defaultProps} />)

      const file = new File(['{"data": {"text": "test"}}'], 'test.json', {
        type: 'application/json',
      })
      const input = document.querySelector(
        'input[type="file"]'
      ) as HTMLInputElement

      await userEvent.upload(input, file)
      await waitFor(() => screen.getByText('test.json'))

      const importButton = screen.getByRole('button', { name: /Import Data/i })
      await user.click(importButton)

      expect(importButton).toBeDisabled()
    })
  })

  describe('Import Process', () => {
    it('imports JSON file successfully', async () => {
      const user = userEvent.setup()
      render(<ImportDataModal {...defaultProps} />)

      const jsonContent = JSON.stringify([{ data: { text: 'test' } }])
      const file = new File([jsonContent], 'test.json', {
        type: 'application/json',
      })

      const input = document.querySelector(
        'input[type="file"]'
      ) as HTMLInputElement
      await userEvent.upload(input, file)

      await waitFor(() => screen.getByText('test.json'))

      const importButton = screen.getByRole('button', { name: /Import Data/i })
      await user.click(importButton)

      await waitFor(() => {
        expect(projectsAPI.importData).toHaveBeenCalledWith(
          'test-project-123',
          {
            data: [{ data: { text: 'test' } }],
          }
        )
      })
    })

    it('imports CSV file successfully', async () => {
      const user = userEvent.setup()
      render(<ImportDataModal {...defaultProps} />)

      const csvContent = 'text\nhello\nworld'
      const file = new File([csvContent], 'test.csv', { type: 'text/csv' })

      const input = document.querySelector(
        'input[type="file"]'
      ) as HTMLInputElement
      await userEvent.upload(input, file)

      await waitFor(() => screen.getByText('test.csv'))

      const importButton = screen.getByRole('button', { name: /Import Data/i })
      await user.click(importButton)

      await waitFor(() => {
        expect(projectsAPI.importData).toHaveBeenCalledWith(
          'test-project-123',
          expect.objectContaining({
            data: expect.arrayContaining([
              expect.objectContaining({ data: expect.any(Object) }),
            ]),
          })
        )
      })
    })

    it('imports plain text successfully', async () => {
      const user = userEvent.setup()
      render(<ImportDataModal {...defaultProps} />)

      const textContent = 'Line 1\nLine 2\nLine 3'
      const file = new File([textContent], 'test.txt', { type: 'text/plain' })

      const input = document.querySelector(
        'input[type="file"]'
      ) as HTMLInputElement
      await userEvent.upload(input, file)

      await waitFor(() => screen.getByText('test.txt'))

      const importButton = screen.getByRole('button', { name: /Import Data/i })
      await user.click(importButton)

      await waitFor(() => {
        expect(projectsAPI.importData).toHaveBeenCalled()
      })
    })

    it('imports pasted JSON successfully', async () => {
      const user = userEvent.setup()
      render(<ImportDataModal {...defaultProps} />)

      await user.click(screen.getByText('Paste Data'))
      const textarea = screen.getByPlaceholderText(
        'Paste JSON, CSV, or plain text data...'
      )
      fireEvent.change(textarea, {
        target: { value: JSON.stringify([{ data: { text: 'pasted' } }]) },
      })

      const importButton = screen.getByRole('button', { name: /Import Data/i })
      await user.click(importButton)

      await waitFor(() => {
        expect(projectsAPI.importData).toHaveBeenCalledWith(
          'test-project-123',
          expect.objectContaining({
            data: expect.arrayContaining([
              expect.objectContaining({ data: { text: 'pasted' } }),
            ]),
          })
        )
      })
    })

    it('shows progress indicators during import', async () => {
      const user = userEvent.setup()
      render(<ImportDataModal {...defaultProps} />)

      const file = new File(['{"data": {"text": "test"}}'], 'test.json', {
        type: 'application/json',
      })
      const input = document.querySelector(
        'input[type="file"]'
      ) as HTMLInputElement

      await userEvent.upload(input, file)
      await waitFor(() => screen.getByText('test.json'))

      const importButton = screen.getByRole('button', { name: /Import Data/i })
      await user.click(importButton)

      await waitFor(() => {
        expect(mockStartProgress).toHaveBeenCalledWith(
          expect.any(String),
          'Importing data...',
          expect.any(Object)
        )
        expect(mockUpdateProgress).toHaveBeenCalled()
        expect(mockCompleteProgress).toHaveBeenCalledWith(
          expect.any(String),
          'success'
        )
      })
    })

    it('displays success toast on successful import', async () => {
      const user = userEvent.setup()
      render(<ImportDataModal {...defaultProps} />)

      const file = new File(['{"data": {"text": "test"}}'], 'test.json', {
        type: 'application/json',
      })
      const input = document.querySelector(
        'input[type="file"]'
      ) as HTMLInputElement

      await userEvent.upload(input, file)
      await waitFor(() => screen.getByText('test.json'))

      const importButton = screen.getByRole('button', { name: /Import Data/i })
      await user.click(importButton)

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(
          'Data imported successfully',
          'success'
        )
      })
    })

    it('calls onImportComplete after successful import', async () => {
      const user = userEvent.setup()
      render(<ImportDataModal {...defaultProps} />)

      const file = new File(['{"data": {"text": "test"}}'], 'test.json', {
        type: 'application/json',
      })
      const input = document.querySelector(
        'input[type="file"]'
      ) as HTMLInputElement

      await userEvent.upload(input, file)
      await waitFor(() => screen.getByText('test.json'))

      const importButton = screen.getByRole('button', { name: /Import Data/i })
      await user.click(importButton)

      await waitFor(
        () => {
          expect(mockOnImportComplete).toHaveBeenCalled()
        },
        { timeout: 3000 }
      )
    })

    it('closes modal after successful import', async () => {
      const user = userEvent.setup()
      render(<ImportDataModal {...defaultProps} />)

      const file = new File(['{"data": {"text": "test"}}'], 'test.json', {
        type: 'application/json',
      })
      const input = document.querySelector(
        'input[type="file"]'
      ) as HTMLInputElement

      await userEvent.upload(input, file)
      await waitFor(() => screen.getByText('test.json'))

      const importButton = screen.getByRole('button', { name: /Import Data/i })
      await user.click(importButton)

      await waitFor(
        () => {
          expect(mockOnClose).toHaveBeenCalled()
        },
        { timeout: 3000 }
      )
    })
  })

  describe('Error Handling', () => {
    it('handles invalid JSON format', async () => {
      const user = userEvent.setup()
      render(<ImportDataModal {...defaultProps} />)

      await user.click(screen.getByText('Paste Data'))
      const textarea = screen.getByPlaceholderText(
        'Paste JSON, CSV, or plain text data...'
      )
      fireEvent.change(textarea, { target: { value: '{invalid json}' } })

      const importButton = screen.getByRole('button', { name: /Import Data/i })
      await user.click(importButton)

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(
          'Failed to import data',
          'error'
        )
      })
    })

    it('handles API import failure', async () => {
      ;(projectsAPI.importData as jest.Mock).mockRejectedValue(
        new Error('Import failed')
      )

      const user = userEvent.setup()
      render(<ImportDataModal {...defaultProps} />)

      const file = new File(['{"data": {"text": "test"}}'], 'test.json', {
        type: 'application/json',
      })
      const input = document.querySelector(
        'input[type="file"]'
      ) as HTMLInputElement

      await userEvent.upload(input, file)
      await waitFor(() => screen.getByText('test.json'))

      const importButton = screen.getByRole('button', { name: /Import Data/i })
      await user.click(importButton)

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(expect.any(String), 'error')
        expect(mockCompleteProgress).toHaveBeenCalledWith(
          expect.any(String),
          'error'
        )
      })
    })

    it('handles authentication errors', async () => {
      ;(projectsAPI.importData as jest.Mock).mockRejectedValue({
        response: { status: 401 },
      })

      const user = userEvent.setup()
      render(<ImportDataModal {...defaultProps} />)

      const file = new File(['{"data": {"text": "test"}}'], 'test.json', {
        type: 'application/json',
      })
      const input = document.querySelector(
        'input[type="file"]'
      ) as HTMLInputElement

      await userEvent.upload(input, file)
      await waitFor(() => screen.getByText('test.json'))

      const importButton = screen.getByRole('button', { name: /Import Data/i })
      await user.click(importButton)

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(
          'Failed to import data',
          'error'
        )
      })
    })

    it('handles permission errors', async () => {
      ;(projectsAPI.importData as jest.Mock).mockRejectedValue({
        response: { status: 403 },
      })

      const user = userEvent.setup()
      render(<ImportDataModal {...defaultProps} />)

      const file = new File(['{"data": {"text": "test"}}'], 'test.json', {
        type: 'application/json',
      })
      const input = document.querySelector(
        'input[type="file"]'
      ) as HTMLInputElement

      await userEvent.upload(input, file)
      await waitFor(() => screen.getByText('test.json'))

      const importButton = screen.getByRole('button', { name: /Import Data/i })
      await user.click(importButton)

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(
          'Failed to import data',
          'error'
        )
      })
    })
  })

  describe('Field Mapping', () => {
    it('shows field mapping when validation fails', async () => {
      const user = userEvent.setup()
      render(<ImportDataModal {...defaultProps} />)

      // Import data that doesn't match template fields
      const file = new File(
        ['{"data": {"wrong_field": "test"}}'],
        'test.json',
        { type: 'application/json' }
      )
      const input = document.querySelector(
        'input[type="file"]'
      ) as HTMLInputElement

      await userEvent.upload(input, file)
      await waitFor(() => screen.getByText('test.json'))

      const importButton = screen.getByRole('button', { name: /Import Data/i })
      await user.click(importButton)

      await waitFor(() => {
        expect(screen.getByText('Import Validation Error')).toBeInTheDocument()
      })
    })

    it('displays validation errors in mapping view', async () => {
      const user = userEvent.setup()
      render(<ImportDataModal {...defaultProps} />)

      const file = new File(
        ['{"data": {"wrong_field": "test"}}'],
        'test.json',
        { type: 'application/json' }
      )
      const input = document.querySelector(
        'input[type="file"]'
      ) as HTMLInputElement

      await userEvent.upload(input, file)
      await waitFor(() => screen.getByText('test.json'))

      const importButton = screen.getByRole('button', { name: /Import Data/i })
      await user.click(importButton)

      await waitFor(() => {
        expect(screen.getByText('Import Validation Error')).toBeInTheDocument()
      })
    })

    it('shows import anyway option when validation fails', async () => {
      const user = userEvent.setup()
      render(<ImportDataModal {...defaultProps} />)

      // Wait for template fields to load
      await waitFor(() => screen.getByText('$text'))

      const file = new File(
        [JSON.stringify([{ data: { wrong_field: 'test' } }])],
        'test.json',
        { type: 'application/json' }
      )
      const input = document.querySelector(
        'input[type="file"]'
      ) as HTMLInputElement

      await userEvent.upload(input, file)
      await waitFor(() => screen.getByText('test.json'))

      const importButton = screen.getByRole('button', { name: /Import Data/i })
      await user.click(importButton)

      // Verify validation error and "Import Anyway" button appear
      await waitFor(
        () => {
          expect(screen.getByText('Import Anyway')).toBeInTheDocument()
          expect(
            screen.getByText(/Import Validation Error/i)
          ).toBeInTheDocument()
          expect(mockAddToast).toHaveBeenCalledWith(
            expect.stringContaining("don't match"),
            'error'
          )
        },
        { timeout: 3000 }
      )
    })

    it('closes field mapping view when cancelled', async () => {
      const user = userEvent.setup()
      render(<ImportDataModal {...defaultProps} />)

      const file = new File(
        ['{"data": {"wrong_field": "test"}}'],
        'test.json',
        { type: 'application/json' }
      )
      const input = document.querySelector(
        'input[type="file"]'
      ) as HTMLInputElement

      await userEvent.upload(input, file)
      await waitFor(() => screen.getByText('test.json'))

      const importButton = screen.getByRole('button', { name: /Import Data/i })
      await user.click(importButton)

      await waitFor(() => screen.getByText('Import Validation Error'))

      const cancelButton = screen.getByRole('button', {
        name: /Cancel Mapping/i,
      })
      await user.click(cancelButton)

      expect(
        screen.queryByText('Import Validation Error')
      ).not.toBeInTheDocument()
    })
  })

  describe('Modal Close', () => {
    it('closes modal when cancel button is clicked', async () => {
      const user = userEvent.setup()
      render(<ImportDataModal {...defaultProps} />)

      const cancelButton = screen.getByRole('button', { name: /Cancel/i })
      await user.click(cancelButton)

      expect(mockOnClose).toHaveBeenCalled()
    })

    it('prevents closing during import', async () => {
      // Mock a slow import
      ;(projectsAPI.importData as jest.Mock).mockImplementation(
        () =>
          new Promise((resolve) => {
            setTimeout(() => resolve({ created: 1 }), 100)
          })
      )

      render(<ImportDataModal {...defaultProps} />)

      const file = new File(
        [JSON.stringify([{ data: { text: 'test' } }])],
        'test.json',
        {
          type: 'application/json',
        }
      )
      const input = document.querySelector(
        'input[type="file"]'
      ) as HTMLInputElement

      await userEvent.upload(input, file)
      await waitFor(() => screen.getByText('test.json'))

      const importButton = screen.getByRole('button', { name: /Import Data/i })
      await userEvent.click(importButton)

      // Check that cancel button is disabled during import
      await waitFor(() => {
        const cancelButton = screen.getByRole('button', { name: /Cancel/i })
        expect(cancelButton).toBeDisabled()
      })
    })
  })

  describe('Format Detection', () => {
    it('detects JSON format from pasted content', async () => {
      const user = userEvent.setup()
      render(<ImportDataModal {...defaultProps} />)

      await user.click(screen.getByText('Paste Data'))
      const textarea = screen.getByPlaceholderText(
        'Paste JSON, CSV, or plain text data...'
      )
      fireEvent.change(textarea, {
        target: { value: '{"data": {"text": "test"}}' },
      })

      const importButton = screen.getByRole('button', { name: /Import Data/i })
      await user.click(importButton)

      await waitFor(() => {
        expect(projectsAPI.importData).toHaveBeenCalled()
      })
    })

    it('detects CSV format from pasted content', async () => {
      const user = userEvent.setup()
      render(<ImportDataModal {...defaultProps} />)

      await user.click(screen.getByText('Paste Data'))
      const textarea = screen.getByPlaceholderText(
        'Paste JSON, CSV, or plain text data...'
      )
      await user.type(textarea, 'text\nhello\nworld')

      const importButton = screen.getByRole('button', { name: /Import Data/i })
      await user.click(importButton)

      await waitFor(() => {
        expect(projectsAPI.importData).toHaveBeenCalled()
      })
    })

    it('detects TSV format from pasted content', async () => {
      const user = userEvent.setup()
      render(<ImportDataModal {...defaultProps} />)

      await user.click(screen.getByText('Paste Data'))
      const textarea = screen.getByPlaceholderText(
        'Paste JSON, CSV, or plain text data...'
      )
      fireEvent.change(textarea, {
        target: { value: 'text\thello\nworld\ttest' },
      })

      const importButton = screen.getByRole('button', { name: /Import Data/i })
      await user.click(importButton)

      await waitFor(() => {
        expect(projectsAPI.importData).toHaveBeenCalled()
      })
    })
  })
})

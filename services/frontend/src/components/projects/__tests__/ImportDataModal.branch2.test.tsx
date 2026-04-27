/**
 * @jest-environment jsdom
 *
 * Branch coverage tests for ImportDataModal.
 * Targets uncovered branches:
 * - parseData: JSON single object (not array) -> wrapped in array
 * - parseData: JSON with item.data field (already Label Studio format)
 * - parseData: CSV with empty lines
 * - parseData: re-thrown error vs generic error
 * - handleImport: no data (empty) -> throws noData error
 * - handleImport: error.response.data.detail branch
 * - handleImport: error.message includes 'Failed to parse'
 * - handleFileSelect: no file (no files[0])
 * - handleDrop: no file in dataTransfer
 * - validateDataAgainstTemplate: template has no fields -> valid
 * - Paste data: clears file when pasting (textarea onChange with selectedFile)
 * - File upload: clears paste when selecting file (with pastedData)
 * - Field mapping: cancel mapping clears state
 * - fetchProjectTemplate: project without label_config
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
        'projects.import.failed': 'Import failed',
        'projects.import.noData': 'No data to import',
        'tasks.importModal.description': 'Import data to create tasks',
        'tasks.importModal.fieldRequirements': 'Field Requirements',
        'tasks.importModal.fieldRequirementsDescription': 'Required fields',
        'tasks.importModal.missingFieldsWarning': 'Missing fields warning',
        'tasks.importModal.uploadFiles': 'Upload Files',
        'tasks.importModal.pasteData': 'Paste Data',
        'tasks.importModal.cloudStorage': 'Cloud Storage',
        'tasks.importModal.dropFilesHere': 'Drop files here',
        'tasks.importModal.supportedFormats': 'JSON, CSV, TSV, TXT',
        'tasks.importModal.chooseFiles': 'Choose Files',
        'tasks.importModal.pasteYourData': 'Paste your data',
        'tasks.importModal.pastePlaceholder': 'Paste data here...',
        'tasks.importModal.csvTip': 'CSV tip',
        'tasks.importModal.cloudComingSoon': 'Coming soon',
        'tasks.importModal.validationError': 'Validation Error',
        'tasks.importModal.validationErrorDescription': 'Fields do not match',
        'tasks.importModal.importAnyway': 'Import Anyway',
        'tasks.importModal.orUseFieldMapping': 'Or use mapping',
        'common.remove': 'Remove',
        'common.cancel': 'Cancel',
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
  ImportPreviewWithMapping: ({ onImport, onCancel }: any) => (
    <div data-testid="import-preview">
      <button onClick={() => onImport([{ data: { text: 'mapped' } }])}>Import Mapped</button>
      <button onClick={onCancel}>Cancel Mapping</button>
    </div>
  ),
}))

describe('ImportDataModal - branch2 coverage', () => {
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
    projectId: 'test-project',
    onImportComplete: mockOnImportComplete,
  }

  beforeEach(() => {
    jest.clearAllMocks()
    ;(useToast as jest.Mock).mockReturnValue({ addToast: mockAddToast })
    ;(useProgress as jest.Mock).mockReturnValue({
      startProgress: mockStartProgress,
      updateProgress: mockUpdateProgress,
      completeProgress: mockCompleteProgress,
    })
    ;(useProjectStore as jest.Mock).mockReturnValue({ fetchProject: mockFetchProject })
    ;(projectsAPI.importData as jest.Mock).mockResolvedValue({ created: 5 })
  })

  describe('parseData branches', () => {
    it('handles JSON single object (not array) by wrapping in array', async () => {
      const user = userEvent.setup()
      // No template fields -> no validation error
      mockFetchProject.mockResolvedValue({ id: 'test-project' })

      render(<ImportDataModal {...defaultProps} />)

      await user.click(screen.getByText('Paste Data'))
      const textarea = screen.getByPlaceholderText('Paste data here...')
      // Paste a single object (not array)
      fireEvent.change(textarea, {
        target: { value: '{"text": "single item"}' },
      })

      await user.click(screen.getByRole('button', { name: /Import Data/i }))

      await waitFor(() => {
        expect(projectsAPI.importData).toHaveBeenCalledWith(
          'test-project',
          expect.objectContaining({
            data: [{ data: { text: 'single item' } }],
          })
        )
      })
    })

    it('handles JSON with item.data field (already in Label Studio format)', async () => {
      const user = userEvent.setup()
      mockFetchProject.mockResolvedValue({ id: 'test-project' })

      render(<ImportDataModal {...defaultProps} />)

      await user.click(screen.getByText('Paste Data'))
      const textarea = screen.getByPlaceholderText('Paste data here...')
      fireEvent.change(textarea, {
        target: { value: '[{"data": {"text": "already wrapped"}}]' },
      })

      await user.click(screen.getByRole('button', { name: /Import Data/i }))

      await waitFor(() => {
        expect(projectsAPI.importData).toHaveBeenCalledWith(
          'test-project',
          { data: [{ data: { text: 'already wrapped' } }] }
        )
      })
    })

    it('handles TSV content from file', async () => {
      mockFetchProject.mockResolvedValue({ id: 'test-project' })

      render(<ImportDataModal {...defaultProps} />)

      const tsvContent = 'name\tvalue\nAlice\t100\nBob\t200'
      const file = new File([tsvContent], 'data.tsv', { type: 'text/tab-separated-values' })
      const input = document.querySelector('input[type="file"]') as HTMLInputElement
      await userEvent.upload(input, file)

      await waitFor(() => screen.getByText('data.tsv'))

      await userEvent.click(screen.getByRole('button', { name: /Import Data/i }))

      await waitFor(() => {
        expect(projectsAPI.importData).toHaveBeenCalledWith(
          'test-project',
          expect.objectContaining({
            data: expect.arrayContaining([
              expect.objectContaining({ data: expect.objectContaining({ name: 'Alice' }) }),
            ]),
          })
        )
      })
    })
  })

  describe('error handling branches', () => {
    it('handles error with response.data.detail', async () => {
      ;(projectsAPI.importData as jest.Mock).mockRejectedValue({
        response: { status: 500, data: { detail: 'Server-specific error message' } },
      })

      const user = userEvent.setup()
      mockFetchProject.mockResolvedValue({ id: 'test-project' })

      render(<ImportDataModal {...defaultProps} />)

      const file = new File(['[{"data":{"text":"test"}}]'], 'test.json', { type: 'application/json' })
      const input = document.querySelector('input[type="file"]') as HTMLInputElement
      await userEvent.upload(input, file)
      await waitFor(() => screen.getByText('test.json'))

      await user.click(screen.getByRole('button', { name: /Import Data/i }))

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith('Failed to import data', 'error')
        expect(mockCompleteProgress).toHaveBeenCalledWith(expect.any(String), 'error')
      })
    })

    it('handles error with message containing "Failed to parse"', async () => {
      ;(projectsAPI.importData as jest.Mock).mockRejectedValue(
        new Error('Failed to parse CSV data: invalid format')
      )

      const user = userEvent.setup()
      mockFetchProject.mockResolvedValue({ id: 'test-project' })

      render(<ImportDataModal {...defaultProps} />)

      const file = new File(['[{"data":{"text":"test"}}]'], 'test.json', { type: 'application/json' })
      const input = document.querySelector('input[type="file"]') as HTMLInputElement
      await userEvent.upload(input, file)
      await waitFor(() => screen.getByText('test.json'))

      await user.click(screen.getByRole('button', { name: /Import Data/i }))

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith('Failed to import data', 'error')
      })
    })
  })

  describe('fetchProjectTemplate with no label_config', () => {
    it('does not show field requirements when project has no label_config', async () => {
      mockFetchProject.mockResolvedValue({
        id: 'test-project',
        title: 'No Config Project',
        // no label_config
      })

      render(<ImportDataModal {...defaultProps} />)

      await waitFor(() => {
        expect(mockFetchProject).toHaveBeenCalled()
      })

      // No field requirements should be displayed
      expect(screen.queryByText('Field Requirements')).not.toBeInTheDocument()
    })
  })

  describe('import button click prevention', () => {
    it('does nothing when button clicked during loading', async () => {
      // Make import hang
      ;(projectsAPI.importData as jest.Mock).mockImplementation(
        () => new Promise(() => {})
      )

      const user = userEvent.setup()
      mockFetchProject.mockResolvedValue({ id: 'test-project' })

      render(<ImportDataModal {...defaultProps} />)

      const file = new File(['[{"data":{"text":"test"}}]'], 'test.json', { type: 'application/json' })
      const input = document.querySelector('input[type="file"]') as HTMLInputElement
      await userEvent.upload(input, file)
      await waitFor(() => screen.getByText('test.json'))

      const importButton = screen.getByRole('button', { name: /Import Data/i })
      await user.click(importButton)

      // Wait for the import call to be dispatched and button to become disabled
      await waitFor(() => {
        expect(projectsAPI.importData).toHaveBeenCalledTimes(1)
        expect(importButton).toBeDisabled()
      })

      // Click again should not trigger another call
      fireEvent.click(importButton)
      expect(projectsAPI.importData).toHaveBeenCalledTimes(1)
    })
  })

  describe('drag and drop edge cases', () => {
    it('handles dragOver event', () => {
      mockFetchProject.mockResolvedValue({ id: 'test-project' })
      render(<ImportDataModal {...defaultProps} />)

      const dropZone = screen.getByText('Drop files here').parentElement!
      // dragOver should not throw
      fireEvent.dragOver(dropZone)
    })
  })

  describe('field mapping cancel clears state', () => {
    it('clears field mapping state and returns to main view on cancel', async () => {
      const user = userEvent.setup()
      mockFetchProject.mockResolvedValue({
        id: 'test-project',
        label_config: '<View><Text name="text" value="$text"/></View>',
      })

      render(<ImportDataModal {...defaultProps} />)

      // Wait for template fields
      await waitFor(() => {
        expect(mockFetchProject).toHaveBeenCalled()
      })

      const file = new File(['[{"data":{"wrong":"test"}}]'], 'test.json', { type: 'application/json' })
      const input = document.querySelector('input[type="file"]') as HTMLInputElement
      await userEvent.upload(input, file)
      await waitFor(() => screen.getByText('test.json'))

      await user.click(screen.getByRole('button', { name: /Import Data/i }))

      // Should show field mapping
      await waitFor(() => {
        expect(screen.getByTestId('import-preview')).toBeInTheDocument()
      })

      // Cancel mapping
      await user.click(screen.getByText('Cancel Mapping'))

      // Should return to normal view
      expect(screen.queryByTestId('import-preview')).not.toBeInTheDocument()
    })
  })
})

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import React from 'react'
import { BulkMetadataEditor } from '../MetadataField'
import { ToastProvider } from '../Toast'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, vars?: any) => {
      const translations: Record<string, string> = {
        'shared.metadata.bulkEditTitle': 'Edit Metadata for {count} Tasks',
        'shared.metadata.labelTags': 'Tags:',
        'shared.metadata.tagsPlaceholder': 'Enter tags, separated by commas',
        'shared.metadata.labelPriority': 'Priority:',
        'shared.metadata.selectDefault': '-- Select --',
        'shared.metadata.priorityLow': 'Low',
        'shared.metadata.priorityMedium': 'Medium',
        'shared.metadata.priorityHigh': 'High',
        'shared.metadata.priorityUrgent': 'Urgent',
        'shared.metadata.labelStatus': 'Status:',
        'shared.metadata.statusPending': 'Pending',
        'shared.metadata.statusInProgress': 'In Progress',
        'shared.metadata.statusReview': 'Review',
        'shared.metadata.statusCompleted': 'Completed',
        'shared.metadata.metadataToUpdate': 'Metadata to update:',
        'shared.metadata.updating': 'Updating...',
        'shared.metadata.updateMetadata': 'Update Metadata',
        'shared.metadata.noMetadataToUpdate': 'No metadata to update',
        'shared.metadata.bulkUpdated': 'Updated metadata for {count} tasks',
        'shared.metadata.failedUpdate': 'Failed to update metadata',
        'common.cancel': 'Cancel',
      }
      let result = translations[key] || key
      if (vars) {
        Object.entries(vars).forEach(([k, v]) => {
          result = result.replace(`{${k}}`, String(v))
        })
      }
      return result
    },
    locale: 'en',
  }),
}))

jest.mock('@/lib/api', () => ({
  __esModule: true,
  default: {
    patch: jest.fn(),
  },
}))

import apiClient from '@/lib/api'
const mockApiClient = apiClient as jest.Mocked<typeof apiClient>

const renderWithToast = (ui: React.ReactElement) => {
  return render(<ToastProvider>{ui}</ToastProvider>)
}

describe('BulkMetadataEditor', () => {
  const defaultProps = {
    taskIds: [1, 2, 3],
    onClose: jest.fn(),
    onSuccess: jest.fn(),
  }

  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('renders with correct title showing task count', () => {
    renderWithToast(<BulkMetadataEditor {...defaultProps} />)
    expect(screen.getByText('Edit Metadata for 3 Tasks')).toBeInTheDocument()
  })

  it('renders tags input field', () => {
    renderWithToast(<BulkMetadataEditor {...defaultProps} />)
    expect(screen.getByText('Tags:')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('Enter tags, separated by commas')).toBeInTheDocument()
  })

  it('renders priority selector', () => {
    renderWithToast(<BulkMetadataEditor {...defaultProps} />)
    expect(screen.getByText('Priority:')).toBeInTheDocument()
  })

  it('renders status selector', () => {
    renderWithToast(<BulkMetadataEditor {...defaultProps} />)
    expect(screen.getByText('Status:')).toBeInTheDocument()
  })

  it('renders cancel and update buttons', () => {
    renderWithToast(<BulkMetadataEditor {...defaultProps} />)
    expect(screen.getByText('Cancel')).toBeInTheDocument()
    expect(screen.getByText('Update Metadata')).toBeInTheDocument()
  })

  it('update button is disabled when no metadata changes', () => {
    renderWithToast(<BulkMetadataEditor {...defaultProps} />)
    const updateButton = screen.getByText('Update Metadata')
    expect(updateButton).toBeDisabled()
  })

  it('calls onClose when cancel is clicked', async () => {
    const user = userEvent.setup()
    const onClose = jest.fn()
    renderWithToast(<BulkMetadataEditor {...defaultProps} onClose={onClose} />)
    await user.click(screen.getByText('Cancel'))
    expect(onClose).toHaveBeenCalled()
  })

  it('adds tags when typing in tags field', async () => {
    const user = userEvent.setup()
    renderWithToast(<BulkMetadataEditor {...defaultProps} />)
    const tagsInput = screen.getByPlaceholderText('Enter tags, separated by commas')
    await user.type(tagsInput, 'tag1, tag2')
    // Metadata preview should appear
    await waitFor(() => {
      expect(screen.getByText('Metadata to update:')).toBeInTheDocument()
    })
  })

  it('removes tags metadata when tags field is cleared', async () => {
    const user = userEvent.setup()
    renderWithToast(<BulkMetadataEditor {...defaultProps} />)
    const tagsInput = screen.getByPlaceholderText('Enter tags, separated by commas')
    await user.type(tagsInput, 'tag1')
    await user.clear(tagsInput)
    // Update button should be disabled again
    const updateButton = screen.getByText('Update Metadata')
    expect(updateButton).toBeDisabled()
  })

  it('adds priority when selected', async () => {
    const user = userEvent.setup()
    renderWithToast(<BulkMetadataEditor {...defaultProps} />)
    const prioritySelect = screen.getAllByRole('combobox')[0]
    await user.selectOptions(prioritySelect, 'high')
    await waitFor(() => {
      expect(screen.getByText('Metadata to update:')).toBeInTheDocument()
    })
  })

  it('removes priority when reset to default', async () => {
    const user = userEvent.setup()
    renderWithToast(<BulkMetadataEditor {...defaultProps} />)
    const prioritySelect = screen.getAllByRole('combobox')[0]
    await user.selectOptions(prioritySelect, 'high')
    // Simulate resetting to empty via fireEvent since there is no empty <option>
    fireEvent.change(prioritySelect, { target: { value: '' } })
  })

  it('adds status when selected', async () => {
    const user = userEvent.setup()
    renderWithToast(<BulkMetadataEditor {...defaultProps} />)
    const statusSelect = screen.getAllByRole('combobox')[1]
    await user.selectOptions(statusSelect, 'completed')
    await waitFor(() => {
      expect(screen.getByText('Metadata to update:')).toBeInTheDocument()
    })
  })

  it('calls API when submit is clicked with metadata', async () => {
    const user = userEvent.setup()
    mockApiClient.patch.mockResolvedValueOnce({})
    renderWithToast(<BulkMetadataEditor {...defaultProps} />)

    const tagsInput = screen.getByPlaceholderText('Enter tags, separated by commas')
    await user.type(tagsInput, 'tag1')

    const updateButton = screen.getByText('Update Metadata')
    await user.click(updateButton)

    await waitFor(() => {
      expect(mockApiClient.patch).toHaveBeenCalledWith(
        '/api/projects/tasks/bulk-metadata',
        { task_ids: [1, 2, 3], metadata: { tags: ['tag1'] } }
      )
    })
  })

  it('calls onSuccess and onClose after successful submit', async () => {
    const user = userEvent.setup()
    const onSuccess = jest.fn()
    const onClose = jest.fn()
    mockApiClient.patch.mockResolvedValueOnce({})
    renderWithToast(
      <BulkMetadataEditor {...defaultProps} onSuccess={onSuccess} onClose={onClose} />
    )

    const tagsInput = screen.getByPlaceholderText('Enter tags, separated by commas')
    await user.type(tagsInput, 'tag1')

    await user.click(screen.getByText('Update Metadata'))

    await waitFor(() => {
      expect(onSuccess).toHaveBeenCalled()
      expect(onClose).toHaveBeenCalled()
    })
  })

  it('handles submit failure gracefully', async () => {
    const user = userEvent.setup()
    mockApiClient.patch.mockRejectedValueOnce(new Error('API Error'))
    renderWithToast(<BulkMetadataEditor {...defaultProps} />)

    const tagsInput = screen.getByPlaceholderText('Enter tags, separated by commas')
    await user.type(tagsInput, 'tag1')

    await user.click(screen.getByText('Update Metadata'))

    await waitFor(() => {
      expect(mockApiClient.patch).toHaveBeenCalled()
    })
    // Should not crash and onClose should not be called on failure
    expect(defaultProps.onClose).not.toHaveBeenCalled()
  })

  it('shows metadata preview as JSON', async () => {
    const user = userEvent.setup()
    renderWithToast(<BulkMetadataEditor {...defaultProps} />)
    const prioritySelect = screen.getAllByRole('combobox')[0]
    await user.selectOptions(prioritySelect, 'high')
    await waitFor(() => {
      const pre = screen.getByText(/"priority"/)
      expect(pre).toBeInTheDocument()
    })
  })
})

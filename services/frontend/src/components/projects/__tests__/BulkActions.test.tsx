/**
 * @jest-environment jsdom
 */

import { BulkActions } from '@/components/projects/BulkActions'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

// Mock the MetadataField component (BulkMetadataEditor)
jest.mock('@/components/shared/MetadataField', () => ({
  BulkMetadataEditor: ({ taskIds, onClose, onSuccess }: any) => (
    <div data-testid="bulk-metadata-editor">
      <div data-testid="task-ids">{taskIds.join(',')}</div>
      <button onClick={onClose} data-testid="close-editor">
        Close
      </button>
      <button onClick={() => onSuccess()} data-testid="save-editor">
        Save
      </button>
    </div>
  ),
}))
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


describe('BulkActions', () => {
  const defaultProps = {
    selectedCount: 0,
    selectedTaskIds: [],
    projectId: 'project-123',
    onDelete: jest.fn(),
    onExport: jest.fn(),
    onArchive: jest.fn(),
    canAssign: false,
  }

  beforeEach(() => {
    jest.clearAllMocks()
  })

  describe('Dropdown Button', () => {
    it('renders dropdown button with Actions label', () => {
      render(<BulkActions {...defaultProps} />)

      expect(screen.getByText('Actions')).toBeInTheDocument()
    })

    it('disables button when no tasks are selected', () => {
      render(<BulkActions {...defaultProps} selectedCount={0} />)

      const button = screen.getByText('Actions').closest('button')
      expect(button).toBeDisabled()
    })

    it('enables button when tasks are selected', () => {
      render(<BulkActions {...defaultProps} selectedCount={3} />)

      const button = screen.getByText('Actions').closest('button')
      expect(button).not.toBeDisabled()
    })

    it('displays selection count badge', () => {
      render(<BulkActions {...defaultProps} selectedCount={5} />)

      expect(screen.getByText('5')).toBeInTheDocument()
    })

    it('updates count badge when selection changes', () => {
      const { rerender } = render(
        <BulkActions {...defaultProps} selectedCount={2} />
      )

      expect(screen.getByText('2')).toBeInTheDocument()

      rerender(<BulkActions {...defaultProps} selectedCount={7} />)

      expect(screen.getByText('7')).toBeInTheDocument()
      expect(screen.queryByText('2')).not.toBeInTheDocument()
    })

    it('shows dropdown when button is clicked', async () => {
      const user = userEvent.setup()

      render(<BulkActions {...defaultProps} selectedCount={2} />)

      const button = screen.getByText('Actions')
      await user.click(button)

      expect(screen.getByText('2 task(s) selected')).toBeInTheDocument()
    })
  })

  describe('Dropdown Menu Items', () => {
    it('shows all action options when tasks are selected', async () => {
      const user = userEvent.setup()

      render(
        <BulkActions
          {...defaultProps}
          selectedCount={3}
          canAssign={true}
          onAssign={jest.fn()}
        />
      )

      await user.click(screen.getByText('Actions'))

      await waitFor(() => {
        expect(screen.getByText('Assign to Annotators')).toBeInTheDocument()
        expect(screen.getByText('Export Selected')).toBeInTheDocument()
        expect(screen.getByText('Duplicate Selected')).toBeInTheDocument()
        expect(screen.getByText('Edit Metadata')).toBeInTheDocument()
        expect(screen.getByText('Archive Selected')).toBeInTheDocument()
        expect(screen.getByText('Delete Selected')).toBeInTheDocument()
      })
    })

    it('shows correct task count in dropdown header', async () => {
      const user = userEvent.setup()

      render(<BulkActions {...defaultProps} selectedCount={1} />)

      await user.click(screen.getByText('Actions'))

      expect(screen.getByText('1 task(s) selected')).toBeInTheDocument()
    })

    it('pluralizes task count correctly', async () => {
      const user = userEvent.setup()

      const { rerender } = render(
        <BulkActions {...defaultProps} selectedCount={1} />
      )

      await user.click(screen.getByText('Actions'))
      expect(screen.getByText('1 task(s) selected')).toBeInTheDocument()

      await user.click(screen.getByText('Actions'))

      rerender(<BulkActions {...defaultProps} selectedCount={5} />)
      await user.click(screen.getByText('Actions'))

      expect(screen.getByText('5 task(s) selected')).toBeInTheDocument()
    })

    it('hides assign option when canAssign is false', async () => {
      const user = userEvent.setup()

      render(
        <BulkActions {...defaultProps} selectedCount={2} canAssign={false} />
      )

      await user.click(screen.getByText('Actions'))

      expect(screen.queryByText('Assign to Annotators')).not.toBeInTheDocument()
    })

    it('shows assign option when canAssign is true and onAssign is provided', async () => {
      const user = userEvent.setup()

      render(
        <BulkActions
          {...defaultProps}
          selectedCount={2}
          canAssign={true}
          onAssign={jest.fn()}
        />
      )

      await user.click(screen.getByText('Actions'))

      expect(screen.getByText('Assign to Annotators')).toBeInTheDocument()
    })

    it('shows empty state message when no tasks selected', async () => {
      const user = userEvent.setup()

      render(<BulkActions {...defaultProps} selectedCount={0} />)

      const button = screen.getByText('Actions').closest('button')
      expect(button).toBeDisabled()
    })
  })

  describe('Action Handlers', () => {
    it('calls onDelete when Delete Selected is clicked', async () => {
      const user = userEvent.setup()
      const mockOnDelete = jest.fn()

      render(
        <BulkActions
          {...defaultProps}
          selectedCount={2}
          onDelete={mockOnDelete}
        />
      )

      await user.click(screen.getByText('Actions'))
      await user.click(screen.getByText('Delete Selected'))

      expect(mockOnDelete).toHaveBeenCalledTimes(1)
    })

    it('calls onExport when Export Selected is clicked', async () => {
      const user = userEvent.setup()
      const mockOnExport = jest.fn()

      render(
        <BulkActions
          {...defaultProps}
          selectedCount={3}
          onExport={mockOnExport}
        />
      )

      await user.click(screen.getByText('Actions'))
      await user.click(screen.getByText('Export Selected'))

      expect(mockOnExport).toHaveBeenCalledTimes(1)
    })

    it('calls onArchive when Archive Selected is clicked', async () => {
      const user = userEvent.setup()
      const mockOnArchive = jest.fn()

      render(
        <BulkActions
          {...defaultProps}
          selectedCount={1}
          onArchive={mockOnArchive}
        />
      )

      await user.click(screen.getByText('Actions'))
      await user.click(screen.getByText('Archive Selected'))

      expect(mockOnArchive).toHaveBeenCalledTimes(1)
    })

    it('calls onAssign when Assign to Annotators is clicked', async () => {
      const user = userEvent.setup()
      const mockOnAssign = jest.fn()

      render(
        <BulkActions
          {...defaultProps}
          selectedCount={5}
          canAssign={true}
          onAssign={mockOnAssign}
        />
      )

      await user.click(screen.getByText('Actions'))
      await user.click(screen.getByText('Assign to Annotators'))

      expect(mockOnAssign).toHaveBeenCalledTimes(1)
    })

    it('shows alert for Duplicate functionality', async () => {
      const user = userEvent.setup()
      const alertSpy = jest.spyOn(window, 'alert').mockImplementation(() => {})

      render(<BulkActions {...defaultProps} selectedCount={2} />)

      await user.click(screen.getByText('Actions'))
      await user.click(screen.getByText('Duplicate Selected'))

      expect(alertSpy).toHaveBeenCalledWith(
        'Duplicate functionality coming soon'
      )

      alertSpy.mockRestore()
    })
  })

  describe('Metadata Editor Modal', () => {
    it('opens metadata editor when Edit Metadata is clicked', async () => {
      const user = userEvent.setup()

      render(
        <BulkActions
          {...defaultProps}
          selectedCount={3}
          selectedTaskIds={['1', '2', '3']}
        />
      )

      await user.click(screen.getByText('Actions'))
      await user.click(screen.getByText('Edit Metadata'))

      expect(screen.getByTestId('bulk-metadata-editor')).toBeInTheDocument()
    })

    it('passes correct task IDs to metadata editor', async () => {
      const user = userEvent.setup()

      render(
        <BulkActions
          {...defaultProps}
          selectedCount={2}
          selectedTaskIds={['42', '99']}
        />
      )

      await user.click(screen.getByText('Actions'))
      await user.click(screen.getByText('Edit Metadata'))

      expect(screen.getByTestId('task-ids')).toHaveTextContent('42,99')
    })

    it('closes metadata editor when close is clicked', async () => {
      const user = userEvent.setup()

      render(
        <BulkActions
          {...defaultProps}
          selectedCount={2}
          selectedTaskIds={['1', '2']}
        />
      )

      await user.click(screen.getByText('Actions'))
      await user.click(screen.getByText('Edit Metadata'))

      expect(screen.getByTestId('bulk-metadata-editor')).toBeInTheDocument()

      await user.click(screen.getByTestId('close-editor'))

      expect(
        screen.queryByTestId('bulk-metadata-editor')
      ).not.toBeInTheDocument()
    })

    it('calls onTagsUpdated when metadata is saved successfully', async () => {
      const user = userEvent.setup()
      const mockOnTagsUpdated = jest.fn()

      render(
        <BulkActions
          {...defaultProps}
          selectedCount={2}
          selectedTaskIds={['1', '2']}
          onTagsUpdated={mockOnTagsUpdated}
        />
      )

      await user.click(screen.getByText('Actions'))
      await user.click(screen.getByText('Edit Metadata'))

      await user.click(screen.getByTestId('save-editor'))

      await waitFor(() => {
        expect(mockOnTagsUpdated).toHaveBeenCalledTimes(1)
      })
    })

    it('closes metadata editor after successful save', async () => {
      const user = userEvent.setup()

      render(
        <BulkActions
          {...defaultProps}
          selectedCount={2}
          selectedTaskIds={['1', '2']}
          onTagsUpdated={jest.fn()}
        />
      )

      await user.click(screen.getByText('Actions'))
      await user.click(screen.getByText('Edit Metadata'))

      expect(screen.getByTestId('bulk-metadata-editor')).toBeInTheDocument()

      await user.click(screen.getByTestId('save-editor'))

      await waitFor(() => {
        expect(
          screen.queryByTestId('bulk-metadata-editor')
        ).not.toBeInTheDocument()
      })
    })
  })

  describe('Dropdown Behavior', () => {
    it('closes dropdown when action is clicked', async () => {
      const user = userEvent.setup()

      render(<BulkActions {...defaultProps} selectedCount={2} />)

      await user.click(screen.getByText('Actions'))
      expect(screen.getByText('Export Selected')).toBeInTheDocument()

      await user.click(screen.getByText('Export Selected'))

      await waitFor(() => {
        expect(screen.queryByText('Export Selected')).not.toBeInTheDocument()
      })
    })

    it('closes dropdown when clicking outside', async () => {
      const user = userEvent.setup()

      render(
        <div>
          <div data-testid="outside">Outside element</div>
          <BulkActions {...defaultProps} selectedCount={2} />
        </div>
      )

      await user.click(screen.getByText('Actions'))
      expect(screen.getByText('Export Selected')).toBeInTheDocument()

      await user.click(screen.getByTestId('outside'))

      await waitFor(() => {
        expect(screen.queryByText('Export Selected')).not.toBeInTheDocument()
      })
    })

    it('toggles dropdown on button click', async () => {
      const user = userEvent.setup()

      render(<BulkActions {...defaultProps} selectedCount={2} />)

      const button = screen.getByText('Actions')

      // Open dropdown
      await user.click(button)
      expect(screen.getByText('Export Selected')).toBeInTheDocument()

      // Close dropdown
      await user.click(button)
      await waitFor(() => {
        expect(screen.queryByText('Export Selected')).not.toBeInTheDocument()
      })

      // Open dropdown again
      await user.click(button)
      expect(screen.getByText('Export Selected')).toBeInTheDocument()
    })
  })

  describe('Edge Cases', () => {
    it('handles missing onTagsUpdated callback gracefully', async () => {
      const user = userEvent.setup()

      render(
        <BulkActions
          {...defaultProps}
          selectedCount={2}
          selectedTaskIds={['1', '2']}
          // onTagsUpdated not provided
        />
      )

      await user.click(screen.getByText('Actions'))
      await user.click(screen.getByText('Edit Metadata'))
      await user.click(screen.getByTestId('save-editor'))

      // Should not throw error
      await waitFor(() => {
        expect(
          screen.queryByTestId('bulk-metadata-editor')
        ).not.toBeInTheDocument()
      })
    })

    it('converts string task IDs to numbers for metadata editor', async () => {
      const user = userEvent.setup()

      render(
        <BulkActions
          {...defaultProps}
          selectedCount={2}
          selectedTaskIds={['123', '456']}
        />
      )

      await user.click(screen.getByText('Actions'))
      await user.click(screen.getByText('Edit Metadata'))

      // Task IDs should be passed as numbers
      expect(screen.getByTestId('task-ids')).toHaveTextContent('123,456')
    })

    it('handles empty selectedTaskIds array', async () => {
      const user = userEvent.setup()

      render(
        <BulkActions {...defaultProps} selectedCount={0} selectedTaskIds={[]} />
      )

      const button = screen.getByText('Actions').closest('button')
      expect(button).toBeDisabled()
    })

    it('shows dropdown with default empty task IDs', async () => {
      const user = userEvent.setup()

      render(
        <BulkActions
          {...defaultProps}
          selectedCount={1}
          // selectedTaskIds not provided (defaults to [])
        />
      )

      await user.click(screen.getByText('Actions'))
      await user.click(screen.getByText('Edit Metadata'))

      expect(screen.getByTestId('bulk-metadata-editor')).toBeInTheDocument()
    })

    it('works without projectId', async () => {
      const user = userEvent.setup()

      render(
        <BulkActions
          {...defaultProps}
          projectId={undefined}
          selectedCount={2}
        />
      )

      await user.click(screen.getByText('Actions'))

      expect(screen.getByText('Export Selected')).toBeInTheDocument()
    })
  })

  describe('Accessibility', () => {
    it('has accessible button role', () => {
      render(<BulkActions {...defaultProps} selectedCount={2} />)

      const button = screen.getByRole('button', { name: /Actions/i })
      expect(button).toBeInTheDocument()
    })

    it('shows visual disabled state', () => {
      render(<BulkActions {...defaultProps} selectedCount={0} />)

      const button = screen.getByRole('button')
      expect(button).toBeDisabled()
      expect(button).toHaveClass('disabled:opacity-50')
    })

    it('shows count badge with proper styling', () => {
      render(<BulkActions {...defaultProps} selectedCount={3} />)

      const badge = screen.getByText('3')
      expect(badge).toHaveClass('bg-emerald-100')
    })
  })

  describe('Integration Scenarios', () => {
    it('handles complete workflow: open, select action, execute, close', async () => {
      const user = userEvent.setup()
      const mockOnExport = jest.fn()

      render(
        <BulkActions
          {...defaultProps}
          selectedCount={5}
          onExport={mockOnExport}
        />
      )

      // Open dropdown
      await user.click(screen.getByText('Actions'))
      expect(screen.getByText('5 task(s) selected')).toBeInTheDocument()

      // Execute action
      await user.click(screen.getByText('Export Selected'))
      expect(mockOnExport).toHaveBeenCalledTimes(1)

      // Dropdown should be closed
      await waitFor(() => {
        expect(screen.queryByText('Export Selected')).not.toBeInTheDocument()
      })
    })

    it('handles metadata editing workflow with tags update', async () => {
      const user = userEvent.setup()
      const mockOnTagsUpdated = jest.fn()

      render(
        <BulkActions
          {...defaultProps}
          selectedCount={3}
          selectedTaskIds={['10', '20', '30']}
          onTagsUpdated={mockOnTagsUpdated}
        />
      )

      // Open dropdown
      await user.click(screen.getByText('Actions'))

      // Open metadata editor
      await user.click(screen.getByText('Edit Metadata'))
      expect(screen.getByTestId('bulk-metadata-editor')).toBeInTheDocument()

      // Save changes
      await user.click(screen.getByTestId('save-editor'))

      // Should close and trigger callback
      await waitFor(() => {
        expect(
          screen.queryByTestId('bulk-metadata-editor')
        ).not.toBeInTheDocument()
        expect(mockOnTagsUpdated).toHaveBeenCalledTimes(1)
      })
    })

    it('handles all action types sequentially', async () => {
      const user = userEvent.setup()
      const mockOnAssign = jest.fn()
      const mockOnExport = jest.fn()
      const mockOnArchive = jest.fn()
      const mockOnDelete = jest.fn()

      render(
        <BulkActions
          {...defaultProps}
          selectedCount={4}
          canAssign={true}
          onAssign={mockOnAssign}
          onExport={mockOnExport}
          onArchive={mockOnArchive}
          onDelete={mockOnDelete}
        />
      )

      // Test assign
      await user.click(screen.getByText('Actions'))
      await user.click(screen.getByText('Assign to Annotators'))
      expect(mockOnAssign).toHaveBeenCalledTimes(1)

      // Test export
      await user.click(screen.getByText('Actions'))
      await user.click(screen.getByText('Export Selected'))
      expect(mockOnExport).toHaveBeenCalledTimes(1)

      // Test archive
      await user.click(screen.getByText('Actions'))
      await user.click(screen.getByText('Archive Selected'))
      expect(mockOnArchive).toHaveBeenCalledTimes(1)

      // Test delete
      await user.click(screen.getByText('Actions'))
      await user.click(screen.getByText('Delete Selected'))
      expect(mockOnDelete).toHaveBeenCalledTimes(1)
    })
  })
})

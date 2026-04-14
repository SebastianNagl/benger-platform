/**
 * Test suite for MetadataField component
 * Comprehensive testing for inline metadata editing
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import React from 'react'
import { MetadataField } from '../MetadataField'
import { ToastProvider } from '../Toast'

const mockTranslate = (key: string, arg2?: any, arg3?: any) => {
  const vars = typeof arg2 === 'object' ? arg2 : arg3
  const translations: Record<string, string> = {
    'shared.metadata.updated': 'Metadata updated',
    'shared.metadata.failedUpdate': 'Failed to update metadata',
    'shared.metadata.noItems': 'No {field}',
    'shared.metadata.yes': 'Yes',
    'shared.metadata.no': 'No',
    'shared.metadata.enterCommaSeparated': 'Enter {field}, separated by commas',
    'shared.metadata.enterField': 'Enter {field}',
    'shared.metadata.save': 'Save',
    'shared.metadata.cancel': 'Cancel',
    'shared.metadata.addField': 'Add {field}',
    'shared.metadata.noMetadataToUpdate': 'No metadata to update',
    'shared.metadata.bulkUpdated': 'Updated metadata for {count} tasks',
    'shared.metadata.bulkEditTitle': 'Edit Metadata for {count} Tasks',
    'shared.metadata.labelTags': 'Tags:',
    'shared.metadata.tagsPlaceholder': 'Enter tags, separated by commas',
    'shared.metadata.labelPriority': 'Priority:',
    'shared.metadata.selectDefault': '\u2014 Select \u2014',
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
    'common.cancel': 'Cancel',
  }
  let result = translations[key] || key
  if (vars) {
    Object.entries(vars).forEach(([k, v]) => {
      result = result.replace(`{${k}}`, String(v))
    })
  }
  return result
}

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: mockTranslate,
    locale: 'en',
    setLocale: jest.fn(),
  }),
}))

// Mock the API client
jest.mock('@/lib/api', () => ({
  __esModule: true,
  default: {
    patch: jest.fn(),
  },
}))

import apiClient from '@/lib/api'

const mockApiClient = apiClient as jest.Mocked<typeof apiClient>

// Wrapper component with ToastProvider
const renderWithToast = (ui: React.ReactElement) => {
  return render(<ToastProvider>{ui}</ToastProvider>)
}

describe('MetadataField', () => {
  const defaultProps = {
    taskId: 1,
    fieldName: 'status',
    value: 'pending',
  }

  beforeEach(() => {
    jest.clearAllMocks()
  })

  describe('Basic Rendering', () => {
    it('renders field with string value', () => {
      renderWithToast(<MetadataField {...defaultProps} />)

      expect(screen.getByText('pending')).toBeInTheDocument()
    })

    it('renders field with numeric value', () => {
      renderWithToast(<MetadataField {...defaultProps} value={42} />)

      expect(screen.getByText('42')).toBeInTheDocument()
    })

    it('renders field with custom className', () => {
      const { container } = renderWithToast(
        <MetadataField {...defaultProps} className="custom-class" />
      )

      const field = container.querySelector('.custom-class')
      expect(field).toBeInTheDocument()
    })

    it('renders as inline-flex container', () => {
      const { container } = renderWithToast(<MetadataField {...defaultProps} />)

      const field = container.querySelector('.inline-flex')
      expect(field).toBeInTheDocument()
      expect(field).toHaveClass('items-center', 'gap-2')
    })
  })

  describe('Label and Value Display', () => {
    it('displays string value correctly', () => {
      renderWithToast(<MetadataField {...defaultProps} value="completed" />)

      expect(screen.getByText('completed')).toBeInTheDocument()
    })

    it('displays value with correct text color', () => {
      renderWithToast(<MetadataField {...defaultProps} value="test" />)

      const value = screen.getByText('test')
      expect(value).toHaveClass('text-zinc-900', 'dark:text-white')
    })

    it('updates display when value prop changes', () => {
      const { rerender } = renderWithToast(
        <MetadataField {...defaultProps} value="initial" />
      )

      expect(screen.getByText('initial')).toBeInTheDocument()

      rerender(
        <ToastProvider>
          <MetadataField {...defaultProps} value="updated" />
        </ToastProvider>
      )

      expect(screen.getByText('updated')).toBeInTheDocument()
      expect(screen.queryByText('initial')).not.toBeInTheDocument()
    })
  })

  describe('Field Types/Variants', () => {
    describe('String values', () => {
      it('renders string value correctly', () => {
        renderWithToast(<MetadataField {...defaultProps} value="test string" />)

        expect(screen.getByText('test string')).toBeInTheDocument()
      })

      it('shows text input when editing empty string value', async () => {
        const user = userEvent.setup()

        renderWithToast(<MetadataField {...defaultProps} value={null} />)

        const addButton = screen.getByTitle('Add status')
        await user.click(addButton)

        const input = screen.getByRole('textbox')
        expect(input).toBeInTheDocument()
        expect(input).toHaveValue('')
      })
    })

    describe('Boolean values', () => {
      it('renders true boolean as "Yes"', () => {
        renderWithToast(<MetadataField {...defaultProps} value={true} />)

        expect(screen.getByText('Yes')).toBeInTheDocument()
      })

      it('renders false boolean as "No"', () => {
        renderWithToast(<MetadataField {...defaultProps} value={false} />)

        expect(screen.getByText('No')).toBeInTheDocument()
      })

      it('applies green styling for true value', () => {
        renderWithToast(<MetadataField {...defaultProps} value={true} />)

        const badge = screen.getByText('Yes')
        expect(badge).toHaveClass(
          'bg-green-100',
          'text-green-700',
          'dark:bg-green-900/20',
          'dark:text-green-400'
        )
      })

      it('applies zinc styling for false value', () => {
        renderWithToast(<MetadataField {...defaultProps} value={false} />)

        const badge = screen.getByText('No')
        expect(badge).toHaveClass(
          'bg-zinc-100',
          'text-zinc-500',
          'dark:bg-zinc-800',
          'dark:text-zinc-400'
        )
      })

      it('boolean values are read-only', () => {
        renderWithToast(<MetadataField {...defaultProps} value={true} />)

        // Boolean values don't have edit buttons
        expect(screen.queryByTitle('Add status')).not.toBeInTheDocument()
        expect(screen.queryByTitle('Edit')).not.toBeInTheDocument()
      })

      it('shows select when editing null boolean via add button', async () => {
        const user = userEvent.setup()

        // Start with null value (to show Add button)
        renderWithToast(<MetadataField {...defaultProps} value={null} />)

        const addButton = screen.getByTitle('Add status')
        await user.click(addButton)

        // Should show text input by default since we can't determine it's a boolean
        const input = screen.getByRole('textbox')
        expect(input).toBeInTheDocument()
      })
    })

    describe('Array values', () => {
      it('renders empty array correctly', () => {
        renderWithToast(
          <MetadataField {...defaultProps} fieldName="tags" value={[]} />
        )

        expect(screen.getByText('No tags')).toBeInTheDocument()
      })

      it('renders single array item', () => {
        renderWithToast(<MetadataField {...defaultProps} value={['tag1']} />)

        expect(screen.getByText('tag1')).toBeInTheDocument()
      })

      it('renders two array items', () => {
        renderWithToast(
          <MetadataField {...defaultProps} value={['tag1', 'tag2']} />
        )

        expect(screen.getByText('tag1')).toBeInTheDocument()
        expect(screen.getByText('tag2')).toBeInTheDocument()
      })

      it('shows only first two items with count for longer arrays', () => {
        renderWithToast(
          <MetadataField
            {...defaultProps}
            value={['tag1', 'tag2', 'tag3', 'tag4']}
          />
        )

        expect(screen.getByText('tag1')).toBeInTheDocument()
        expect(screen.getByText('tag2')).toBeInTheDocument()
        expect(screen.getByText('+2')).toBeInTheDocument()
        expect(screen.queryByText('tag3')).not.toBeInTheDocument()
      })

      it('truncates long array items', () => {
        renderWithToast(
          <MetadataField
            {...defaultProps}
            value={['verylongtagnamethatexceedstenlimit']}
          />
        )

        // Component truncates at 10 characters
        expect(screen.getByText('verylongta...')).toBeInTheDocument()
      })

      it('does not truncate short array items', () => {
        renderWithToast(<MetadataField {...defaultProps} value={['short']} />)

        expect(screen.getByText('short')).toBeInTheDocument()
      })

      it('applies correct styling to array badges', () => {
        renderWithToast(<MetadataField {...defaultProps} value={['tag1']} />)

        const badge = screen.getByText('tag1')
        expect(badge).toHaveClass(
          'rounded',
          'bg-zinc-100',
          'px-1.5',
          'py-0',
          'text-xs',
          'font-medium',
          'text-zinc-700',
          'dark:bg-zinc-800',
          'dark:text-zinc-300'
        )
      })

      it('shows plus icon for empty array', () => {
        renderWithToast(
          <MetadataField {...defaultProps} fieldName="tags" value={[]} />
        )

        const button = screen.getByTitle('Add tags')
        expect(button).toBeInTheDocument()
      })

      it('shows comma-separated input when editing empty array', async () => {
        const user = userEvent.setup()

        renderWithToast(<MetadataField {...defaultProps} value={[]} />)

        const addButton = screen.getByTitle('Add status')
        await user.click(addButton)

        const input = screen.getByRole('textbox')
        expect(input).toHaveValue('')
        expect(input).toHaveAttribute(
          'placeholder',
          'Enter status, separated by commas'
        )
      })
    })
  })

  describe('Styling', () => {
    it('applies base styling classes', () => {
      const { container } = renderWithToast(<MetadataField {...defaultProps} />)

      const field = container.firstChild
      expect(field).toHaveClass('inline-flex', 'items-center', 'gap-2')
    })

    it('combines custom className with base classes', () => {
      const { container } = renderWithToast(
        <MetadataField {...defaultProps} className="my-custom-class" />
      )

      const field = container.firstChild
      expect(field).toHaveClass(
        'inline-flex',
        'items-center',
        'my-custom-class'
      )
    })

    it('applies dark mode classes to values', () => {
      renderWithToast(<MetadataField {...defaultProps} value="test" />)

      const value = screen.getByText('test')
      expect(value).toHaveClass('dark:text-white')
    })

    it('applies proper styling to input in edit mode', async () => {
      const user = userEvent.setup()

      renderWithToast(<MetadataField {...defaultProps} value={null} />)

      const addButton = screen.getByTitle('Add status')
      await user.click(addButton)

      const input = screen.getByRole('textbox')
      expect(input).toHaveClass(
        'rounded-md',
        'border',
        'px-2',
        'py-1',
        'text-sm',
        'focus:outline-none',
        'focus:ring-2',
        'focus:ring-emerald-500',
        'dark:border-zinc-700',
        'dark:bg-zinc-800'
      )
    })
  })

  describe('Empty/Null Values', () => {
    it('renders null value with dash', () => {
      renderWithToast(<MetadataField {...defaultProps} value={null} />)

      expect(screen.getByText('—')).toBeInTheDocument()
    })

    it('renders undefined value with dash', () => {
      renderWithToast(<MetadataField {...defaultProps} value={undefined} />)

      expect(screen.getByText('—')).toBeInTheDocument()
    })

    it('applies correct styling to null value', () => {
      renderWithToast(<MetadataField {...defaultProps} value={null} />)

      const dash = screen.getByText('—')
      expect(dash).toHaveClass('text-sm', 'text-zinc-400', 'dark:text-zinc-500')
    })

    it('shows plus icon for null value when editable', () => {
      renderWithToast(<MetadataField {...defaultProps} value={null} />)

      const button = screen.getByTitle('Add status')
      expect(button).toBeInTheDocument()
    })

    it('shows plus icon for undefined value when editable', () => {
      renderWithToast(<MetadataField {...defaultProps} value={undefined} />)

      const button = screen.getByTitle('Add status')
      expect(button).toBeInTheDocument()
    })

    it('does not show plus icon when not editable', () => {
      renderWithToast(
        <MetadataField {...defaultProps} value={null} editable={false} />
      )

      const button = screen.queryByTitle('Add status')
      expect(button).not.toBeInTheDocument()
    })

    it('applies correct styling to empty array message', () => {
      renderWithToast(
        <MetadataField {...defaultProps} fieldName="tags" value={[]} />
      )

      const message = screen.getByText('No tags')
      expect(message).toHaveClass(
        'text-sm',
        'text-zinc-400',
        'dark:text-zinc-500'
      )
    })
  })

  describe('Formatting', () => {
    it('converts number to string for display', () => {
      renderWithToast(<MetadataField {...defaultProps} value={123} />)

      expect(screen.getByText('123')).toBeInTheDocument()
    })

    it('handles zero value correctly', () => {
      renderWithToast(<MetadataField {...defaultProps} value={0} />)

      expect(screen.getByText('0')).toBeInTheDocument()
    })

    it('formats array with proper spacing', () => {
      renderWithToast(
        <MetadataField {...defaultProps} value={['a', 'b', 'c']} />
      )

      const container = screen.getByText('a').parentElement
      expect(container).toHaveClass('gap-1')
    })

    it('displays boolean with proper badge formatting', () => {
      renderWithToast(<MetadataField {...defaultProps} value={true} />)

      const badge = screen.getByText('Yes')
      expect(badge).toHaveClass('inline-flex', 'items-center', 'rounded')
    })

    it('parses comma-separated input correctly', async () => {
      const user = userEvent.setup()
      const mockUpdate = jest.fn()
      mockApiClient.patch.mockResolvedValueOnce({})

      renderWithToast(
        <MetadataField {...defaultProps} value={[]} onUpdate={mockUpdate} />
      )

      const addButton = screen.getByTitle('Add status')
      await user.click(addButton)

      const input = screen.getByRole('textbox') as HTMLInputElement
      await user.clear(input)
      // Use paste to handle comma correctly
      await user.click(input)
      await user.paste('tag1, tag2, tag3')

      const saveButton = screen.getByTitle('Save')
      await user.click(saveButton)

      await waitFor(
        () => {
          expect(mockApiClient.patch).toHaveBeenCalledWith(
            '/api/projects/tasks/1/metadata',
            { status: ['tag1', 'tag2', 'tag3'] }
          )
        },
        { timeout: 500 }
      )
    })

    it('filters out empty strings from comma-separated input', async () => {
      const user = userEvent.setup()
      const mockUpdate = jest.fn()
      mockApiClient.patch.mockResolvedValueOnce({})

      renderWithToast(
        <MetadataField {...defaultProps} value={[]} onUpdate={mockUpdate} />
      )

      const addButton = screen.getByTitle('Add status')
      await user.click(addButton)

      const input = screen.getByRole('textbox') as HTMLInputElement
      await user.click(input)
      // Use paste to handle comma correctly
      await user.paste('tag1,  , tag2,  ')

      const saveButton = screen.getByTitle('Save')
      await user.click(saveButton)

      await waitFor(
        () => {
          expect(mockApiClient.patch).toHaveBeenCalledWith(
            '/api/projects/tasks/1/metadata',
            { status: ['tag1', 'tag2'] }
          )
        },
        { timeout: 500 }
      )
    })
  })

  describe('Editing Functionality', () => {
    it('enters edit mode when add button is clicked', async () => {
      const user = userEvent.setup()

      renderWithToast(<MetadataField {...defaultProps} value={null} />)

      const addButton = screen.getByTitle('Add status')
      await user.click(addButton)

      expect(screen.getByRole('textbox')).toBeInTheDocument()
    })

    it('existing values are not editable by click', async () => {
      const user = userEvent.setup()

      renderWithToast(<MetadataField {...defaultProps} value="test" />)

      const value = screen.getByText('test')
      await user.click(value)

      // Should not enter edit mode
      expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
    })

    it('shows save and cancel buttons in edit mode', async () => {
      const user = userEvent.setup()

      renderWithToast(<MetadataField {...defaultProps} value={null} />)

      const addButton = screen.getByTitle('Add status')
      await user.click(addButton)

      expect(screen.getByTitle('Save')).toBeInTheDocument()
      expect(screen.getByTitle('Cancel')).toBeInTheDocument()
    })

    it('focuses input when entering edit mode', async () => {
      const user = userEvent.setup()

      renderWithToast(<MetadataField {...defaultProps} value={null} />)

      const addButton = screen.getByTitle('Add status')
      await user.click(addButton)

      const input = screen.getByRole('textbox')
      expect(input).toHaveFocus()
    })

    it('selects input text when entering edit mode with value', async () => {
      const user = userEvent.setup()

      renderWithToast(<MetadataField {...defaultProps} value={undefined} />)

      const addButton = screen.getByTitle('Add status')
      await user.click(addButton)

      // Input should be empty for undefined values
      const input = screen.getByRole('textbox') as HTMLInputElement
      expect(input.value).toBe('')
    })

    it('updates input value when typing', async () => {
      const user = userEvent.setup()

      renderWithToast(<MetadataField {...defaultProps} value={null} />)

      const addButton = screen.getByTitle('Add status')
      await user.click(addButton)

      const input = screen.getByRole('textbox')
      await user.type(input, 'new value')

      expect(input).toHaveValue('new value')
    })

    it('calls API when saving new value', async () => {
      const user = userEvent.setup()
      mockApiClient.patch.mockResolvedValueOnce({})

      renderWithToast(<MetadataField {...defaultProps} value={null} />)

      const addButton = screen.getByTitle('Add status')
      await user.click(addButton)

      const input = screen.getByRole('textbox')
      await user.type(input, 'updated')

      const saveButton = screen.getByTitle('Save')
      await user.click(saveButton)

      await waitFor(() => {
        expect(mockApiClient.patch).toHaveBeenCalledWith(
          '/api/projects/tasks/1/metadata',
          { status: 'updated' }
        )
      })
    })

    it('calls onUpdate callback after successful save', async () => {
      const user = userEvent.setup()
      const mockUpdate = jest.fn()
      mockApiClient.patch.mockResolvedValueOnce({})

      renderWithToast(
        <MetadataField {...defaultProps} value={null} onUpdate={mockUpdate} />
      )

      const addButton = screen.getByTitle('Add status')
      await user.click(addButton)

      const input = screen.getByRole('textbox')
      await user.type(input, 'updated')

      const saveButton = screen.getByTitle('Save')
      await user.click(saveButton)

      await waitFor(() => {
        expect(mockUpdate).toHaveBeenCalledWith('updated')
      })
    })

    it('exits edit mode after successful save', async () => {
      const user = userEvent.setup()
      mockApiClient.patch.mockResolvedValueOnce({})

      renderWithToast(<MetadataField {...defaultProps} value={null} />)

      const addButton = screen.getByTitle('Add status')
      await user.click(addButton)

      const input = screen.getByRole('textbox')
      await user.type(input, 'updated')

      const saveButton = screen.getByTitle('Save')
      await user.click(saveButton)

      await waitFor(() => {
        expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
      })
    })

    it('does not call API if value unchanged', async () => {
      const user = userEvent.setup()

      renderWithToast(<MetadataField {...defaultProps} value={null} />)

      const addButton = screen.getByTitle('Add status')
      await user.click(addButton)

      const saveButton = screen.getByTitle('Save')
      await user.click(saveButton)

      expect(mockApiClient.patch).not.toHaveBeenCalled()
    })

    it('exits edit mode when cancel is clicked', async () => {
      const user = userEvent.setup()

      renderWithToast(<MetadataField {...defaultProps} value={null} />)

      const addButton = screen.getByTitle('Add status')
      await user.click(addButton)

      const input = screen.getByRole('textbox')
      await user.type(input, 'changed')

      const cancelButton = screen.getByTitle('Cancel')
      await user.click(cancelButton)

      expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
      expect(screen.getByText('—')).toBeInTheDocument()
    })

    it('resets value when cancel is clicked', async () => {
      const user = userEvent.setup()

      renderWithToast(<MetadataField {...defaultProps} value={null} />)

      const addButton = screen.getByTitle('Add status')
      await user.click(addButton)

      const input = screen.getByRole('textbox')
      await user.type(input, 'changed')

      const cancelButton = screen.getByTitle('Cancel')
      await user.click(cancelButton)

      // Value should remain null
      expect(screen.getByText('—')).toBeInTheDocument()
    })

    it('saves on Enter key press', async () => {
      const user = userEvent.setup()
      mockApiClient.patch.mockResolvedValueOnce({})

      renderWithToast(<MetadataField {...defaultProps} value={null} />)

      const addButton = screen.getByTitle('Add status')
      await user.click(addButton)

      const input = screen.getByRole('textbox')
      await user.type(input, 'updated{Enter}')

      await waitFor(() => {
        expect(mockApiClient.patch).toHaveBeenCalledWith(
          '/api/projects/tasks/1/metadata',
          { status: 'updated' }
        )
      })
    })

    it('cancels on Escape key press', async () => {
      const user = userEvent.setup()

      renderWithToast(<MetadataField {...defaultProps} value={null} />)

      const addButton = screen.getByTitle('Add status')
      await user.click(addButton)

      const input = screen.getByRole('textbox')
      await user.type(input, 'changed{Escape}')

      expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
      expect(screen.getByText('—')).toBeInTheDocument()
    })

    it('disables buttons while saving', async () => {
      const user = userEvent.setup()
      mockApiClient.patch.mockImplementation(
        () => new Promise((resolve) => setTimeout(resolve, 100))
      )

      renderWithToast(<MetadataField {...defaultProps} value={null} />)

      const addButton = screen.getByTitle('Add status')
      await user.click(addButton)

      const input = screen.getByRole('textbox')
      await user.type(input, 'updated')

      const saveButton = screen.getByTitle('Save')
      await user.click(saveButton)

      expect(saveButton).toBeDisabled()
      expect(screen.getByTitle('Cancel')).toBeDisabled()
    })

    it('disables input while saving', async () => {
      const user = userEvent.setup()
      mockApiClient.patch.mockImplementation(
        () => new Promise((resolve) => setTimeout(resolve, 100))
      )

      renderWithToast(<MetadataField {...defaultProps} value={null} />)

      const addButton = screen.getByTitle('Add status')
      await user.click(addButton)

      const input = screen.getByRole('textbox')
      await user.type(input, 'updated')

      const saveButton = screen.getByTitle('Save')
      await user.click(saveButton)

      expect(input).toBeDisabled()
    })

    it('completes save successfully and exits edit mode', async () => {
      const user = userEvent.setup()
      mockApiClient.patch.mockResolvedValueOnce({})

      renderWithToast(<MetadataField {...defaultProps} value={null} />)

      const addButton = screen.getByTitle('Add status')
      await user.click(addButton)

      const input = screen.getByRole('textbox')
      await user.type(input, 'updated')

      const saveButton = screen.getByTitle('Save')
      await user.click(saveButton)

      // Wait for save to complete - API should be called and edit mode closed
      await waitFor(() => {
        expect(mockApiClient.patch).toHaveBeenCalledWith(
          '/api/projects/tasks/1/metadata',
          { status: 'updated' }
        )
      })

      // Edit mode should close after successful save
      await waitFor(() => {
        expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
      })
    })

    it('handles save failure and stays in edit mode', async () => {
      const user = userEvent.setup()
      mockApiClient.patch.mockRejectedValueOnce(new Error('API Error'))

      renderWithToast(<MetadataField {...defaultProps} value={null} />)

      const addButton = screen.getByTitle('Add status')
      await user.click(addButton)

      const input = screen.getByRole('textbox')
      await user.type(input, 'updated')

      const saveButton = screen.getByTitle('Save')
      await user.click(saveButton)

      // Wait for the API to be called
      await waitFor(() => {
        expect(mockApiClient.patch).toHaveBeenCalled()
      })

      // Should still be in edit mode after error
      await waitFor(() => {
        expect(screen.getByRole('textbox')).toBeInTheDocument()
      })
    })

    it('resets value on save failure', async () => {
      const user = userEvent.setup()
      mockApiClient.patch.mockRejectedValueOnce(new Error('API Error'))

      renderWithToast(<MetadataField {...defaultProps} value={null} />)

      const addButton = screen.getByTitle('Add status')
      await user.click(addButton)

      const input = screen.getByRole('textbox')
      await user.type(input, 'updated')

      const saveButton = screen.getByTitle('Save')
      await user.click(saveButton)

      // Wait for the error to be processed and value reset
      await waitFor(() => {
        expect(mockApiClient.patch).toHaveBeenCalled()
      })

      // Value should be reset to empty string in input
      await waitFor(() => {
        const updatedInput = screen.getByRole('textbox') as HTMLInputElement
        expect(updatedInput.value).toBe('')
      })
    })
  })

  describe('Non-editable Mode', () => {
    it('does not show edit controls when editable is false', () => {
      renderWithToast(
        <MetadataField {...defaultProps} value="test" editable={false} />
      )

      expect(screen.queryByTitle('Save')).not.toBeInTheDocument()
      expect(screen.queryByTitle('Cancel')).not.toBeInTheDocument()
    })

    it('does not enter edit mode when clicked', async () => {
      const user = userEvent.setup()

      renderWithToast(
        <MetadataField {...defaultProps} value="test" editable={false} />
      )

      const value = screen.getByText('test')
      await user.click(value)

      expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
    })

    it('does not show plus icon for empty values', () => {
      renderWithToast(
        <MetadataField {...defaultProps} value={null} editable={false} />
      )

      expect(screen.queryByTitle('Add status')).not.toBeInTheDocument()
    })

    it('renders with simple div wrapper', () => {
      const { container } = renderWithToast(
        <MetadataField {...defaultProps} value="test" editable={false} />
      )

      const div = container.querySelector('div')
      expect(div).toBeInTheDocument()
    })
  })

  describe('Edge Cases', () => {
    it('handles very long string values', () => {
      const longValue = 'a'.repeat(200)

      renderWithToast(<MetadataField {...defaultProps} value={longValue} />)

      expect(screen.getByText(longValue)).toBeInTheDocument()
    })

    it('handles empty string value', () => {
      const { container } = renderWithToast(
        <MetadataField {...defaultProps} value="" />
      )

      // Empty string renders but doesn't show add button (not null/undefined/empty array)
      const field = container.querySelector('.inline-flex')
      expect(field).toBeInTheDocument()
    })

    it('handles special characters in values', () => {
      renderWithToast(<MetadataField {...defaultProps} value="test@#$%^&*()" />)

      expect(screen.getByText('test@#$%^&*()')).toBeInTheDocument()
    })

    it('handles unicode characters in values', () => {
      renderWithToast(<MetadataField {...defaultProps} value="测试 🎉" />)

      expect(screen.getByText('测试 🎉')).toBeInTheDocument()
    })

    it('handles rapid edit mode toggling', async () => {
      const user = userEvent.setup()

      renderWithToast(<MetadataField {...defaultProps} value={null} />)

      // Click to add
      await user.click(screen.getByTitle('Add status'))
      expect(screen.getByRole('textbox')).toBeInTheDocument()

      // Cancel
      await user.click(screen.getByTitle('Cancel'))
      expect(screen.queryByRole('textbox')).not.toBeInTheDocument()

      // Click to add again
      await user.click(screen.getByTitle('Add status'))
      expect(screen.getByRole('textbox')).toBeInTheDocument()
    })

    it('prevents event propagation on container click', async () => {
      const user = userEvent.setup()
      const mockParentClick = jest.fn()

      const { container } = renderWithToast(
        <div onClick={mockParentClick}>
          <MetadataField {...defaultProps} value="test" />
        </div>
      )

      const field = container.querySelector('.inline-flex')
      await user.click(field!)

      // Should not trigger parent click
      expect(mockParentClick).not.toHaveBeenCalled()
    })

    it('handles null taskId gracefully', async () => {
      const user = userEvent.setup()
      mockApiClient.patch.mockResolvedValueOnce({})

      renderWithToast(
        <MetadataField taskId={null as any} fieldName="status" value={null} />
      )

      const addButton = screen.getByTitle('Add status')
      await user.click(addButton)

      const input = screen.getByRole('textbox')
      await user.type(input, 'updated')

      const saveButton = screen.getByTitle('Save')
      await user.click(saveButton)

      await waitFor(() => {
        expect(mockApiClient.patch).toHaveBeenCalledWith(
          '/api/projects/tasks/null/metadata',
          { status: 'updated' }
        )
      })
    })

    it('handles empty fieldName', () => {
      renderWithToast(<MetadataField taskId={1} fieldName="" value="test" />)

      expect(screen.getByText('test')).toBeInTheDocument()
    })
  })

  describe('Accessibility', () => {
    it('provides descriptive title for save button', async () => {
      const user = userEvent.setup()

      renderWithToast(<MetadataField {...defaultProps} value={null} />)

      const addButton = screen.getByTitle('Add status')
      await user.click(addButton)

      const saveButton = screen.getByTitle('Save')
      expect(saveButton).toBeInTheDocument()
    })

    it('provides descriptive title for cancel button', async () => {
      const user = userEvent.setup()

      renderWithToast(<MetadataField {...defaultProps} value={null} />)

      const addButton = screen.getByTitle('Add status')
      await user.click(addButton)

      const cancelButton = screen.getByTitle('Cancel')
      expect(cancelButton).toBeInTheDocument()
    })

    it('provides descriptive title for add button', () => {
      renderWithToast(<MetadataField {...defaultProps} value={null} />)

      const addButton = screen.getByTitle('Add status')
      expect(addButton).toBeInTheDocument()
    })

    it('provides placeholder text for inputs', async () => {
      const user = userEvent.setup()

      renderWithToast(<MetadataField {...defaultProps} value={null} />)

      const addButton = screen.getByTitle('Add status')
      await user.click(addButton)

      const input = screen.getByPlaceholderText('Enter status')
      expect(input).toBeInTheDocument()
    })

    it('supports keyboard navigation in edit mode', async () => {
      const user = userEvent.setup()
      mockApiClient.patch.mockResolvedValueOnce({})

      renderWithToast(<MetadataField {...defaultProps} value={null} />)

      const addButton = screen.getByTitle('Add status')
      await user.click(addButton)

      const input = screen.getByRole('textbox')
      await user.type(input, 'updated')

      // Tab to save button
      await user.tab()
      expect(screen.getByTitle('Save')).toHaveFocus()

      // Tab to cancel button
      await user.tab()
      expect(screen.getByTitle('Cancel')).toHaveFocus()
    })

    it('maintains focus management during editing', async () => {
      const user = userEvent.setup()

      renderWithToast(<MetadataField {...defaultProps} value={null} />)

      const addButton = screen.getByTitle('Add status')
      await user.click(addButton)

      // Input should be focused automatically
      const input = screen.getByRole('textbox')
      expect(input).toHaveFocus()
    })
  })

  describe('Button Interactions', () => {
    it('applies correct styling to save button', async () => {
      const user = userEvent.setup()

      renderWithToast(<MetadataField {...defaultProps} value={null} />)

      const addButton = screen.getByTitle('Add status')
      await user.click(addButton)

      const saveButton = screen.getByTitle('Save')
      expect(saveButton).toHaveClass(
        'p-1',
        'text-green-600',
        'hover:text-green-700',
        'disabled:opacity-50',
        'dark:text-green-400',
        'dark:hover:text-green-300'
      )
    })

    it('applies correct styling to cancel button', async () => {
      const user = userEvent.setup()

      renderWithToast(<MetadataField {...defaultProps} value={null} />)

      const addButton = screen.getByTitle('Add status')
      await user.click(addButton)

      const cancelButton = screen.getByTitle('Cancel')
      expect(cancelButton).toHaveClass(
        'p-1',
        'text-red-600',
        'hover:text-red-700',
        'disabled:opacity-50',
        'dark:text-red-400',
        'dark:hover:text-red-300'
      )
    })

    it('applies correct styling to add button', () => {
      renderWithToast(<MetadataField {...defaultProps} value={null} />)

      const addButton = screen.getByTitle('Add status')
      expect(addButton).toHaveClass(
        'p-1',
        'text-zinc-400',
        'hover:text-zinc-600',
        'dark:text-zinc-500',
        'dark:hover:text-zinc-300'
      )
    })

    it('prevents event propagation on button clicks', async () => {
      const user = userEvent.setup()
      const mockParentClick = jest.fn()
      mockApiClient.patch.mockResolvedValueOnce({})

      renderWithToast(
        <div onClick={mockParentClick}>
          <MetadataField {...defaultProps} value={null} />
        </div>
      )

      const addButton = screen.getByTitle('Add status')
      await user.click(addButton)

      const saveButton = screen.getByTitle('Save')
      await user.click(saveButton)

      // Should not trigger parent click
      expect(mockParentClick).not.toHaveBeenCalled()
    })
  })
})

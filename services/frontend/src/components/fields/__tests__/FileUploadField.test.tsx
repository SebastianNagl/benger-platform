/**
 * @jest-environment jsdom
 */

import { DisplayContext, TaskTemplateField } from '@/types/taskTemplate'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { FileUploadField } from '../FileUploadField'

// Mock Heroicons
jest.mock('@heroicons/react/24/outline', () => ({
  CloudArrowUpIcon: ({ className }: { className?: string }) => (
    <svg className={className} data-testid="cloud-arrow-up-icon">
      <path />
    </svg>
  ),
  DocumentIcon: ({ className }: { className?: string }) => (
    <svg className={className} data-testid="document-icon">
      <path />
    </svg>
  ),
  XMarkIcon: ({ className }: { className?: string }) => (
    <svg className={className} data-testid="x-mark-icon">
      <path />
    </svg>
  ),
  ExclamationCircleIcon: ({ className }: { className?: string }) => (
    <svg className={className} data-testid="exclamation-icon">
      <path />
    </svg>
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


describe('FileUploadField Component', () => {
  const mockOnChange = jest.fn()

  const defaultField: TaskTemplateField = {
    name: 'file_field',
    type: 'file',
    source: 'task_data',
    display: {
      annotation: 'editable',
      table: 'column',
      creation: 'editable',
    },
    label: 'Upload Document',
    description: 'Upload a document file',
    required: false,
  }

  const defaultProps = {
    field: defaultField,
    value: null,
    onChange: mockOnChange,
    context: 'annotation' as DisplayContext,
    readonly: false,
    errors: [],
  }

  beforeEach(() => {
    jest.clearAllMocks()
  })

  describe('Basic Rendering - Empty State', () => {
    it('renders upload dropzone when no file selected', () => {
      render(<FileUploadField {...defaultProps} />)

      expect(screen.getByText('Upload a file')).toBeInTheDocument()
      expect(screen.getByText('or drag and drop')).toBeInTheDocument()
    })

    it('renders cloud upload icon', () => {
      render(<FileUploadField {...defaultProps} />)

      expect(screen.getByTestId('cloud-arrow-up-icon')).toBeInTheDocument()
    })

    it('renders field label', () => {
      render(<FileUploadField {...defaultProps} />)

      expect(screen.getByText('Upload Document (Optional)')).toBeInTheDocument()
    })

    it('renders field description', () => {
      render(<FileUploadField {...defaultProps} />)

      expect(screen.getByText('Upload a document file')).toBeInTheDocument()
    })

    it('shows default file type text', () => {
      render(<FileUploadField {...defaultProps} />)

      expect(screen.getByText('Any file type')).toBeInTheDocument()
    })
  })

  describe('File Type Restrictions', () => {
    it('shows custom accept types', () => {
      const fieldWithAccept = {
        ...defaultField,
        metadata: {
          accept: '.pdf,.doc,.docx',
        },
      }
      render(<FileUploadField {...defaultProps} field={fieldWithAccept} />)

      expect(screen.getByText('.pdf,.doc,.docx')).toBeInTheDocument()
    })

    it('applies accept attribute to input', () => {
      const fieldWithAccept = {
        ...defaultField,
        metadata: {
          accept: 'image/*',
        },
      }
      render(<FileUploadField {...defaultProps} field={fieldWithAccept} />)

      const input = screen.getByLabelText('Upload a file')
      expect(input).toHaveAttribute('accept', 'image/*')
    })

    it('accepts only image files', () => {
      const fieldWithAccept = {
        ...defaultField,
        metadata: {
          accept: 'image/png,image/jpeg',
        },
      }
      render(<FileUploadField {...defaultProps} field={fieldWithAccept} />)

      const input = screen.getByLabelText('Upload a file')
      expect(input).toHaveAttribute('accept', 'image/png,image/jpeg')
    })
  })

  describe('File Selection', () => {
    it('handles file selection', async () => {
      const user = userEvent.setup()
      render(<FileUploadField {...defaultProps} />)

      const file = new File(['test content'], 'test.pdf', {
        type: 'application/pdf',
      })

      const input = screen.getByLabelText('Upload a file')
      await user.upload(input, file)

      expect(mockOnChange).toHaveBeenCalledWith({
        name: 'test.pdf',
        size: 12, // 'test content' is 12 bytes
        type: 'application/pdf',
      })
    })

    it('handles multiple file types', async () => {
      const user = userEvent.setup()
      const { rerender } = render(<FileUploadField {...defaultProps} />)

      // Test PDF
      const pdfFile = new File(['pdf content'], 'document.pdf', {
        type: 'application/pdf',
      })
      const input = screen.getByLabelText('Upload a file')
      await user.upload(input, pdfFile)

      expect(mockOnChange).toHaveBeenLastCalledWith({
        name: 'document.pdf',
        size: 11,
        type: 'application/pdf',
      })

      // Reset and test image
      mockOnChange.mockClear()
      rerender(<FileUploadField {...defaultProps} />)

      const imageFile = new File(['image data'], 'photo.jpg', {
        type: 'image/jpeg',
      })
      const input2 = screen.getByLabelText('Upload a file')
      await user.upload(input2, imageFile)

      expect(mockOnChange).toHaveBeenCalledWith({
        name: 'photo.jpg',
        size: 10,
        type: 'image/jpeg',
      })
    })
  })

  describe('File Display', () => {
    const mockFileValue = {
      name: 'document.pdf',
      size: 1024 * 100, // 100 KB
      type: 'application/pdf',
    }

    it('displays file information when file is selected', () => {
      render(<FileUploadField {...defaultProps} value={mockFileValue} />)

      expect(screen.getByText('document.pdf')).toBeInTheDocument()
      expect(screen.getByTestId('document-icon')).toBeInTheDocument()
    })

    it('shows remove button when file is selected', () => {
      render(<FileUploadField {...defaultProps} value={mockFileValue} />)

      expect(screen.getByTestId('x-mark-icon')).toBeInTheDocument()
    })

    it('hides upload dropzone when file is selected', () => {
      render(<FileUploadField {...defaultProps} value={mockFileValue} />)

      expect(screen.queryByText('Upload a file')).not.toBeInTheDocument()
      expect(
        screen.queryByTestId('cloud-arrow-up-icon')
      ).not.toBeInTheDocument()
    })
  })

  describe('File Size Formatting', () => {
    it('formats bytes correctly', () => {
      const file = { name: 'small.txt', size: 500, type: 'text/plain' }
      render(<FileUploadField {...defaultProps} value={file} />)

      expect(screen.getByText('500 B')).toBeInTheDocument()
    })

    it('formats kilobytes correctly', () => {
      const file = {
        name: 'medium.pdf',
        size: 1024 * 50,
        type: 'application/pdf',
      }
      render(<FileUploadField {...defaultProps} value={file} />)

      expect(screen.getByText('50.0 KB')).toBeInTheDocument()
    })

    it('formats megabytes correctly', () => {
      const file = {
        name: 'large.zip',
        size: 1024 * 1024 * 5,
        type: 'application/zip',
      }
      render(<FileUploadField {...defaultProps} value={file} />)

      expect(screen.getByText('5.0 MB')).toBeInTheDocument()
    })

    it('formats decimal kilobytes correctly', () => {
      const file = {
        name: 'file.txt',
        size: 1024 * 1.5,
        type: 'text/plain',
      }
      render(<FileUploadField {...defaultProps} value={file} />)

      expect(screen.getByText('1.5 KB')).toBeInTheDocument()
    })

    it('formats decimal megabytes correctly', () => {
      const file = {
        name: 'video.mp4',
        size: 1024 * 1024 * 2.7,
        type: 'video/mp4',
      }
      render(<FileUploadField {...defaultProps} value={file} />)

      expect(screen.getByText('2.7 MB')).toBeInTheDocument()
    })
  })

  describe('File Removal', () => {
    const mockFileValue = {
      name: 'document.pdf',
      size: 1024,
      type: 'application/pdf',
    }

    it('calls onChange with null when remove is clicked', async () => {
      const user = userEvent.setup()
      render(<FileUploadField {...defaultProps} value={mockFileValue} />)

      const removeButton = screen.getByTestId('x-mark-icon').parentElement!
      await user.click(removeButton)

      expect(mockOnChange).toHaveBeenCalledWith(null)
    })

    it('clears input value when file is removed', async () => {
      const user = userEvent.setup()
      const { rerender } = render(<FileUploadField {...defaultProps} />)

      // Upload a file
      const file = new File(['content'], 'test.pdf', {
        type: 'application/pdf',
      })
      const input = screen.getByLabelText('Upload a file') as HTMLInputElement
      await user.upload(input, file)

      // Rerender with the file value
      rerender(
        <FileUploadField
          {...defaultProps}
          value={{ name: 'test.pdf', size: 7, type: 'application/pdf' }}
        />
      )

      // Remove the file
      const removeButton = screen.getByTestId('x-mark-icon').parentElement!
      await user.click(removeButton)

      // Rerender back to empty state
      rerender(<FileUploadField {...defaultProps} value={null} />)

      const newInput = screen.getByLabelText(
        'Upload a file'
      ) as HTMLInputElement
      expect(newInput.value).toBe('')
    })
  })

  describe('Readonly State', () => {
    it('disables file input when readonly', () => {
      render(<FileUploadField {...defaultProps} readonly={true} />)

      const input = screen.getByLabelText('Upload a file')
      expect(input).toBeDisabled()
    })

    it('applies opacity to upload label when readonly', () => {
      render(<FileUploadField {...defaultProps} readonly={true} />)

      const label = screen.getByText('Upload a file').closest('label')
      expect(label).toHaveClass('opacity-50')
    })

    it('hides remove button when readonly with file', () => {
      const mockFileValue = {
        name: 'document.pdf',
        size: 1024,
        type: 'application/pdf',
      }
      render(
        <FileUploadField
          {...defaultProps}
          value={mockFileValue}
          readonly={true}
        />
      )

      expect(screen.queryByTestId('x-mark-icon')).not.toBeInTheDocument()
    })

    it('still displays file info when readonly', () => {
      const mockFileValue = {
        name: 'document.pdf',
        size: 1024,
        type: 'application/pdf',
      }
      render(
        <FileUploadField
          {...defaultProps}
          value={mockFileValue}
          readonly={true}
        />
      )

      expect(screen.getByText('document.pdf')).toBeInTheDocument()
      expect(screen.getByText('1.0 KB')).toBeInTheDocument()
    })
  })

  describe('Required Field Handling', () => {
    it('shows required asterisk for required fields', () => {
      const requiredField = { ...defaultField, required: true }
      render(<FileUploadField {...defaultProps} field={requiredField} />)

      const asterisk = screen.getByText('*')
      expect(asterisk).toBeInTheDocument()
      expect(asterisk).toHaveClass('text-red-500')
    })

    it('shows optional label for non-required fields', () => {
      render(<FileUploadField {...defaultProps} />)

      expect(screen.getByText('Upload Document (Optional)')).toBeInTheDocument()
    })
  })

  describe('Error Handling', () => {
    it('displays error message', () => {
      const errors = ['File is required']
      render(<FileUploadField {...defaultProps} errors={errors} />)

      expect(screen.getByText('File is required')).toBeInTheDocument()
    })

    it('displays multiple errors', () => {
      const errors = ['Required field', 'Invalid file type']
      render(<FileUploadField {...defaultProps} errors={errors} />)

      expect(screen.getByText('Required field')).toBeInTheDocument()
      expect(screen.getByText('Invalid file type')).toBeInTheDocument()
    })
  })

  describe('Styling', () => {
    it('applies custom className to wrapper', () => {
      render(<FileUploadField {...defaultProps} className="custom-class" />)

      const wrapper = screen
        .getByText('Upload a file')
        .closest('.field-wrapper')
      expect(wrapper).toHaveClass('custom-class')
    })

    it('applies dashed border to dropzone', () => {
      const { container } = render(<FileUploadField {...defaultProps} />)

      const dropzone = container.querySelector('.border-dashed')
      expect(dropzone).toBeInTheDocument()
    })
  })

  describe('Accessibility', () => {
    it('has proper label for input', () => {
      render(<FileUploadField {...defaultProps} />)

      const input = screen.getByLabelText('Upload a file')
      expect(input).toBeInTheDocument()
      expect(input).toHaveAttribute('type', 'file')
    })

    it('input has correct id and name attributes', () => {
      render(<FileUploadField {...defaultProps} />)

      const input = screen.getByLabelText('Upload a file')
      expect(input).toHaveAttribute('id', 'file_field')
      expect(input).toHaveAttribute('name', 'file_field')
    })

    it('remove button is keyboard accessible', async () => {
      const user = userEvent.setup()
      const mockFileValue = {
        name: 'document.pdf',
        size: 1024,
        type: 'application/pdf',
      }
      render(<FileUploadField {...defaultProps} value={mockFileValue} />)

      const removeButton = screen.getByTestId('x-mark-icon').parentElement!
      removeButton.focus()
      expect(removeButton).toHaveFocus()

      await user.keyboard('{Enter}')
      expect(mockOnChange).toHaveBeenCalledWith(null)
    })
  })

  describe('Edge Cases', () => {
    it('handles missing metadata gracefully', () => {
      const fieldWithoutMetadata: TaskTemplateField = {
        ...defaultField,
        metadata: undefined,
      }
      render(<FileUploadField {...defaultProps} field={fieldWithoutMetadata} />)

      expect(screen.getByText('Any file type')).toBeInTheDocument()
    })

    it('handles very large file sizes', () => {
      const file = {
        name: 'huge.zip',
        size: 1024 * 1024 * 1024, // 1 GB
        type: 'application/zip',
      }
      render(<FileUploadField {...defaultProps} value={file} />)

      expect(screen.getByText('1024.0 MB')).toBeInTheDocument()
    })

    it('handles zero byte files', () => {
      const file = { name: 'empty.txt', size: 0, type: 'text/plain' }
      render(<FileUploadField {...defaultProps} value={file} />)

      expect(screen.getByText('0 B')).toBeInTheDocument()
    })

    it('handles files with special characters in name', () => {
      const file = {
        name: 'file (1) - copy [special].pdf',
        size: 1024,
        type: 'application/pdf',
      }
      render(<FileUploadField {...defaultProps} value={file} />)

      expect(
        screen.getByText('file (1) - copy [special].pdf')
      ).toBeInTheDocument()
    })

    it('handles files with very long names', () => {
      const file = {
        name: 'a'.repeat(200) + '.pdf',
        size: 1024,
        type: 'application/pdf',
      }
      render(<FileUploadField {...defaultProps} value={file} />)

      expect(screen.getByText('a'.repeat(200) + '.pdf')).toBeInTheDocument()
    })
  })
})

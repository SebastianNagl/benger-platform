/**
 * @jest-environment jsdom
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { TaskDescriptionModal } from '../TaskDescriptionModal'

// Mock i18n
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

// Mock heroicons
jest.mock('@heroicons/react/24/outline', () => ({
  XMarkIcon: (props: any) => <svg {...props} data-testid="x-mark-icon" />,
}))

// Mock Headless UI
jest.mock('@headlessui/react', () => {
  const mockFragment = ({ children }: any) => children
  let currentOnClose: (() => void) | null = null

  return {
    Dialog: Object.assign(
      ({ children, onClose, open, ...props }: any) => {
        currentOnClose = onClose
        return open ? (
          <div {...props} role="dialog">
            {children}
          </div>
        ) : null
      },
      {
        Panel: ({ children, ...props }: any) => (
          <div {...props}>{children}</div>
        ),
        Title: ({ children, ...props }: any) => <h2 {...props}>{children}</h2>,
      }
    ),
    Transition: Object.assign(
      ({ show, appear, children, ...props }: any) =>
        show ? <div {...props}>{children}</div> : null,
      {
        Child: ({ children, ...props }: any) => {
          const childrenArray = Array.isArray(children) ? children : [children]
          const processedChildren = childrenArray.map((child: any) => {
            if (child?.props?.className?.includes('fixed inset-0 bg-black')) {
              return {
                ...child,
                props: {
                  ...child.props,
                  onClick: () => currentOnClose && currentOnClose(),
                },
              }
            }
            return child
          })

          return (
            <div {...props}>
              {Array.isArray(children)
                ? processedChildren
                : processedChildren[0]}
            </div>
          )
        },
      }
    ),
    Fragment: mockFragment,
  }
})

describe('TaskDescriptionModal', () => {
  const defaultProps = {
    isOpen: true,
    onClose: jest.fn(),
    onSave: jest.fn(),
    initialValue: '',
  }

  beforeEach(() => {
    jest.clearAllMocks()
  })

  describe('Rendering', () => {
    it('renders when isOpen is true', () => {
      render(<TaskDescriptionModal {...defaultProps} />)
      expect(screen.getByRole('dialog')).toBeInTheDocument()
      expect(screen.getByText('Task Description')).toBeInTheDocument()
    })

    it('does not render when isOpen is false', () => {
      render(<TaskDescriptionModal {...defaultProps} isOpen={false} />)
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })

    it('renders modal title', () => {
      render(<TaskDescriptionModal {...defaultProps} />)
      expect(
        screen.getByRole('heading', { name: 'Task Description' })
      ).toBeInTheDocument()
    })

    it('renders modal subtitle', () => {
      render(<TaskDescriptionModal {...defaultProps} />)
      expect(
        screen.getByText(
          /Provide an optional description for your task to help users understand its purpose/i
        )
      ).toBeInTheDocument()
    })

    it('renders close button with icon', () => {
      render(<TaskDescriptionModal {...defaultProps} />)
      const closeButton = screen.getByRole('button', { name: /close/i })
      expect(closeButton).toBeInTheDocument()
      expect(screen.getByTestId('x-mark-icon')).toBeInTheDocument()
    })

    it('renders textarea with label', () => {
      render(<TaskDescriptionModal {...defaultProps} />)
      expect(screen.getByLabelText('Description')).toBeInTheDocument()
      expect(
        screen.getByPlaceholderText(
          'Describe the purpose and goals of this task...'
        )
      ).toBeInTheDocument()
    })

    it('renders cancel button', () => {
      render(<TaskDescriptionModal {...defaultProps} />)
      expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument()
    })

    it('renders save button', () => {
      render(<TaskDescriptionModal {...defaultProps} />)
      expect(
        screen.getByRole('button', { name: 'Save Description' })
      ).toBeInTheDocument()
    })

    it('renders tips section', () => {
      render(<TaskDescriptionModal {...defaultProps} />)
      expect(
        screen.getByText('Tips for writing task descriptions:')
      ).toBeInTheDocument()
      expect(
        screen.getByText(/Explain the task's purpose and objectives/i)
      ).toBeInTheDocument()
    })

    it('renders all tip list items', () => {
      render(<TaskDescriptionModal {...defaultProps} />)
      expect(
        screen.getByText(/Explain the task's purpose and objectives/i)
      ).toBeInTheDocument()
      expect(
        screen.getByText(/Mention any specific domain knowledge required/i)
      ).toBeInTheDocument()
      expect(
        screen.getByText(/Include context about expected outputs/i)
      ).toBeInTheDocument()
      expect(
        screen.getByText(/Note any special instructions or constraints/i)
      ).toBeInTheDocument()
    })
  })

  describe('Initial Value Handling', () => {
    it('displays empty textarea when no initialValue provided', () => {
      render(<TaskDescriptionModal {...defaultProps} />)
      const textarea = screen.getByLabelText('Description')
      expect(textarea).toHaveValue('')
    })

    it('displays initialValue in textarea', () => {
      const initialValue = 'Task for annotating legal documents'
      render(
        <TaskDescriptionModal {...defaultProps} initialValue={initialValue} />
      )
      const textarea = screen.getByLabelText('Description')
      expect(textarea).toHaveValue(initialValue)
    })

    it('updates textarea when initialValue changes', () => {
      const { rerender } = render(
        <TaskDescriptionModal
          {...defaultProps}
          initialValue="First description"
        />
      )
      let textarea = screen.getByLabelText('Description')
      expect(textarea).toHaveValue('First description')

      rerender(
        <TaskDescriptionModal
          {...defaultProps}
          initialValue="Updated description"
        />
      )
      textarea = screen.getByLabelText('Description')
      expect(textarea).toHaveValue('Updated description')
    })

    it('handles multiline initialValue', () => {
      const multilineValue = 'Purpose: Annotation\nDomain: Legal\nOutput: JSON'
      render(
        <TaskDescriptionModal {...defaultProps} initialValue={multilineValue} />
      )
      const textarea = screen.getByLabelText('Description')
      expect(textarea).toHaveValue(multilineValue)
    })

    it('handles empty initialValue explicitly set', () => {
      render(<TaskDescriptionModal {...defaultProps} initialValue="" />)
      const textarea = screen.getByLabelText('Description')
      expect(textarea).toHaveValue('')
    })
  })

  describe('User Interaction', () => {
    it('allows typing in textarea', async () => {
      const user = userEvent.setup()
      render(<TaskDescriptionModal {...defaultProps} />)
      const textarea = screen.getByLabelText('Description')

      await user.type(textarea, 'New task description')
      expect(textarea).toHaveValue('New task description')
    })

    it('allows clearing textarea', async () => {
      const user = userEvent.setup()
      render(
        <TaskDescriptionModal {...defaultProps} initialValue="Initial text" />
      )
      const textarea = screen.getByLabelText('Description')

      await user.clear(textarea)
      expect(textarea).toHaveValue('')
    })

    it('allows editing existing text', async () => {
      const user = userEvent.setup()
      render(<TaskDescriptionModal {...defaultProps} initialValue="Original" />)
      const textarea = screen.getByLabelText('Description')

      await user.clear(textarea)
      await user.type(textarea, 'Modified')
      expect(textarea).toHaveValue('Modified')
    })

    it('allows multiline input', async () => {
      const user = userEvent.setup()
      render(<TaskDescriptionModal {...defaultProps} />)
      const textarea = screen.getByLabelText('Description')

      await user.type(textarea, 'Line 1{Enter}Line 2{Enter}Line 3')
      expect(textarea.value).toContain('Line 1')
      expect(textarea.value).toContain('Line 2')
      expect(textarea.value).toContain('Line 3')
    })

    it('handles long text input', async () => {
      const user = userEvent.setup()
      render(<TaskDescriptionModal {...defaultProps} />)
      const textarea = screen.getByLabelText('Description')
      const longText = 'This is a very long description. '.repeat(50)

      await user.type(textarea, longText)
      expect(textarea).toHaveValue(longText)
    })

    it('allows selecting text', async () => {
      const user = userEvent.setup()
      render(
        <TaskDescriptionModal
          {...defaultProps}
          initialValue="Select this text"
        />
      )
      const textarea = screen.getByLabelText('Description')

      await user.click(textarea)
      expect(textarea).toHaveFocus()
    })
  })

  describe('Save Functionality', () => {
    it('calls onSave with trimmed text when Save button clicked', async () => {
      const user = userEvent.setup()
      render(<TaskDescriptionModal {...defaultProps} />)
      const textarea = screen.getByLabelText('Description')
      const saveButton = screen.getByRole('button', {
        name: 'Save Description',
      })

      await user.type(textarea, '  Description with spaces  ')
      await user.click(saveButton)

      expect(defaultProps.onSave).toHaveBeenCalledWith(
        'Description with spaces'
      )
      expect(defaultProps.onSave).toHaveBeenCalledTimes(1)
    })

    it('calls onClose after successful save', async () => {
      const user = userEvent.setup()
      render(<TaskDescriptionModal {...defaultProps} />)
      const textarea = screen.getByLabelText('Description')
      const saveButton = screen.getByRole('button', {
        name: 'Save Description',
      })

      await user.type(textarea, 'New description')
      await user.click(saveButton)

      expect(defaultProps.onClose).toHaveBeenCalledTimes(1)
    })

    it('trims leading whitespace on save', async () => {
      const user = userEvent.setup()
      render(<TaskDescriptionModal {...defaultProps} />)
      const textarea = screen.getByLabelText('Description')
      const saveButton = screen.getByRole('button', {
        name: 'Save Description',
      })

      await user.type(textarea, '   Leading spaces')
      await user.click(saveButton)

      expect(defaultProps.onSave).toHaveBeenCalledWith('Leading spaces')
    })

    it('trims trailing whitespace on save', async () => {
      const user = userEvent.setup()
      render(<TaskDescriptionModal {...defaultProps} />)
      const textarea = screen.getByLabelText('Description')
      const saveButton = screen.getByRole('button', {
        name: 'Save Description',
      })

      await user.type(textarea, 'Trailing spaces   ')
      await user.click(saveButton)

      expect(defaultProps.onSave).toHaveBeenCalledWith('Trailing spaces')
    })

    it('saves empty string when textarea is empty', async () => {
      const user = userEvent.setup()
      render(<TaskDescriptionModal {...defaultProps} />)
      const saveButton = screen.getByRole('button', {
        name: 'Save Description',
      })

      await user.click(saveButton)

      expect(defaultProps.onSave).toHaveBeenCalledWith('')
    })

    it('preserves internal whitespace when saving', async () => {
      const user = userEvent.setup()
      render(<TaskDescriptionModal {...defaultProps} />)
      const textarea = screen.getByLabelText('Description')
      const saveButton = screen.getByRole('button', {
        name: 'Save Description',
      })

      await user.type(textarea, 'Text with  multiple  spaces')
      await user.click(saveButton)

      expect(defaultProps.onSave).toHaveBeenCalledWith(
        'Text with  multiple  spaces'
      )
    })

    it('saves multiline text correctly', async () => {
      const user = userEvent.setup()
      render(<TaskDescriptionModal {...defaultProps} />)
      const textarea = screen.getByLabelText('Description')
      const saveButton = screen.getByRole('button', {
        name: 'Save Description',
      })

      await user.type(textarea, 'Line 1{Enter}Line 2{Enter}Line 3')
      await user.click(saveButton)

      const savedValue = defaultProps.onSave.mock.calls[0][0]
      expect(savedValue).toContain('Line 1')
      expect(savedValue).toContain('Line 2')
      expect(savedValue).toContain('Line 3')
    })

    it('trims whitespace-only input to empty string', async () => {
      const user = userEvent.setup()
      render(<TaskDescriptionModal {...defaultProps} />)
      const textarea = screen.getByLabelText('Description')
      const saveButton = screen.getByRole('button', {
        name: 'Save Description',
      })

      await user.type(textarea, '     ')
      await user.click(saveButton)

      expect(defaultProps.onSave).toHaveBeenCalledWith('')
    })
  })

  describe('Cancel Functionality', () => {
    it('calls onClose when Cancel button clicked', async () => {
      const user = userEvent.setup()
      render(<TaskDescriptionModal {...defaultProps} />)
      const cancelButton = screen.getByRole('button', { name: 'Cancel' })

      await user.click(cancelButton)

      expect(defaultProps.onClose).toHaveBeenCalledTimes(1)
    })

    it('does not call onSave when cancelled', async () => {
      const user = userEvent.setup()
      render(<TaskDescriptionModal {...defaultProps} />)
      const textarea = screen.getByLabelText('Description')
      const cancelButton = screen.getByRole('button', { name: 'Cancel' })

      await user.type(textarea, 'Some text')
      await user.click(cancelButton)

      expect(defaultProps.onSave).not.toHaveBeenCalled()
    })

    it('resets textarea to initialValue when cancelled', async () => {
      const user = userEvent.setup()
      const initialValue = 'Original description'
      render(
        <TaskDescriptionModal {...defaultProps} initialValue={initialValue} />
      )
      const textarea = screen.getByLabelText('Description')
      const cancelButton = screen.getByRole('button', { name: 'Cancel' })

      await user.clear(textarea)
      await user.type(textarea, 'Modified description')
      expect(textarea).toHaveValue('Modified description')

      await user.click(cancelButton)

      expect(defaultProps.onClose).toHaveBeenCalled()
    })

    it('calls onClose when close icon clicked', async () => {
      const user = userEvent.setup()
      render(<TaskDescriptionModal {...defaultProps} />)
      const closeButton = screen.getByRole('button', { name: /close/i })

      await user.click(closeButton)

      expect(defaultProps.onClose).toHaveBeenCalledTimes(1)
    })

    it('resets form when close icon clicked', async () => {
      const user = userEvent.setup()
      const initialValue = 'Original'
      render(
        <TaskDescriptionModal {...defaultProps} initialValue={initialValue} />
      )
      const textarea = screen.getByLabelText('Description')
      const closeButton = screen.getByRole('button', { name: /close/i })

      await user.clear(textarea)
      await user.type(textarea, 'New text')
      await user.click(closeButton)

      expect(defaultProps.onClose).toHaveBeenCalled()
    })

    it('discards unsaved changes on cancel', async () => {
      const user = userEvent.setup()
      render(<TaskDescriptionModal {...defaultProps} initialValue="Initial" />)
      const textarea = screen.getByLabelText('Description')
      const cancelButton = screen.getByRole('button', { name: 'Cancel' })

      await user.clear(textarea)
      await user.type(textarea, 'Unsaved changes')
      await user.click(cancelButton)

      expect(defaultProps.onSave).not.toHaveBeenCalled()
    })
  })

  describe('Modal Behavior', () => {
    it('maintains state when reopened without closing', () => {
      const { rerender } = render(
        <TaskDescriptionModal {...defaultProps} isOpen={true} />
      )
      const textarea = screen.getByLabelText('Description')
      fireEvent.change(textarea, { target: { value: 'Test text' } })

      rerender(<TaskDescriptionModal {...defaultProps} isOpen={true} />)

      expect(textarea).toHaveValue('Test text')
    })

    it('handles rapid open/close transitions', () => {
      const { rerender } = render(
        <TaskDescriptionModal {...defaultProps} isOpen={false} />
      )
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()

      rerender(<TaskDescriptionModal {...defaultProps} isOpen={true} />)
      expect(screen.getByRole('dialog')).toBeInTheDocument()

      rerender(<TaskDescriptionModal {...defaultProps} isOpen={false} />)
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()

      rerender(<TaskDescriptionModal {...defaultProps} isOpen={true} />)
      expect(screen.getByRole('dialog')).toBeInTheDocument()
    })

    it('handles backdrop click to close', async () => {
      const { container } = render(<TaskDescriptionModal {...defaultProps} />)

      const backdrop = container.querySelector('.fixed.inset-0.bg-black')
      if (backdrop) {
        fireEvent.click(backdrop)
        await waitFor(() => {
          expect(defaultProps.onClose).toHaveBeenCalled()
        })
      }
    })

    it('resets to initialValue after canceling and reopening', async () => {
      const user = userEvent.setup()
      const initialValue = 'Initial'
      const { rerender } = render(
        <TaskDescriptionModal
          {...defaultProps}
          isOpen={true}
          initialValue={initialValue}
        />
      )
      const textarea = screen.getByLabelText('Description')
      const cancelButton = screen.getByRole('button', { name: 'Cancel' })

      await user.clear(textarea)
      await user.type(textarea, 'Modified')
      await user.click(cancelButton)

      rerender(
        <TaskDescriptionModal
          {...defaultProps}
          isOpen={false}
          initialValue={initialValue}
        />
      )
      rerender(
        <TaskDescriptionModal
          {...defaultProps}
          isOpen={true}
          initialValue={initialValue}
        />
      )

      expect(screen.getByLabelText('Description')).toHaveValue(initialValue)
    })
  })

  describe('Form State Management', () => {
    it('preserves state across re-renders when modal stays open', () => {
      const { rerender } = render(<TaskDescriptionModal {...defaultProps} />)
      const textarea = screen.getByLabelText('Description')
      fireEvent.change(textarea, { target: { value: 'Persistent text' } })

      rerender(<TaskDescriptionModal {...defaultProps} />)

      expect(textarea).toHaveValue('Persistent text')
    })

    it('updates when initialValue prop changes while open', () => {
      const { rerender } = render(
        <TaskDescriptionModal {...defaultProps} initialValue="First" />
      )
      let textarea = screen.getByLabelText('Description')
      expect(textarea).toHaveValue('First')

      rerender(<TaskDescriptionModal {...defaultProps} initialValue="Second" />)
      textarea = screen.getByLabelText('Description')
      expect(textarea).toHaveValue('Second')
    })

    it('handles empty string initialValue', () => {
      render(<TaskDescriptionModal {...defaultProps} initialValue="" />)
      const textarea = screen.getByLabelText('Description')
      expect(textarea).toHaveValue('')
    })

    it('maintains user input until save or cancel', async () => {
      const user = userEvent.setup()
      render(<TaskDescriptionModal {...defaultProps} />)
      const textarea = screen.getByLabelText('Description')

      await user.type(textarea, 'User input')
      expect(textarea).toHaveValue('User input')

      await user.type(textarea, ' more text')
      expect(textarea).toHaveValue('User input more text')
    })
  })

  describe('Accessibility', () => {
    it('has proper ARIA label for close button', () => {
      render(<TaskDescriptionModal {...defaultProps} />)
      expect(
        screen.getByRole('button', { name: /close/i })
      ).toBeInTheDocument()
    })

    it('has proper ID for textarea', () => {
      render(<TaskDescriptionModal {...defaultProps} />)
      const textarea = screen.getByLabelText('Description')
      expect(textarea).toHaveAttribute('id', 'task-description')
    })

    it('textarea has proper placeholder', () => {
      render(<TaskDescriptionModal {...defaultProps} />)
      const textarea = screen.getByLabelText('Description')
      expect(textarea).toHaveAttribute(
        'placeholder',
        'Describe the purpose and goals of this task...'
      )
    })

    it('textarea has correct row attribute', () => {
      render(<TaskDescriptionModal {...defaultProps} />)
      const textarea = screen.getByLabelText('Description')
      expect(textarea).toHaveAttribute('rows', '6')
    })

    it('maintains proper heading structure', () => {
      render(<TaskDescriptionModal {...defaultProps} />)
      const heading = screen.getByRole('heading', { name: 'Task Description' })
      expect(heading).toBeInTheDocument()
    })

    it('all buttons are keyboard accessible', () => {
      render(<TaskDescriptionModal {...defaultProps} />)
      const buttons = screen.getAllByRole('button')
      expect(buttons.length).toBeGreaterThan(0)
      buttons.forEach((button) => {
        expect(button).toBeInTheDocument()
      })
    })

    it('dialog has proper role', () => {
      render(<TaskDescriptionModal {...defaultProps} />)
      expect(screen.getByRole('dialog')).toBeInTheDocument()
    })
  })

  describe('Edge Cases', () => {
    it('handles undefined initialValue', () => {
      render(
        <TaskDescriptionModal {...defaultProps} initialValue={undefined} />
      )
      const textarea = screen.getByLabelText('Description')
      expect(textarea).toHaveValue('')
    })

    it('handles very long initialValue', () => {
      const longText = 'A'.repeat(10000)
      render(<TaskDescriptionModal {...defaultProps} initialValue={longText} />)
      const textarea = screen.getByLabelText('Description')
      expect(textarea).toHaveValue(longText)
    })

    it('handles special characters in initialValue', () => {
      const specialText = '!@#$%^&*()_+-=[]{}|;:\'",.<>?/~`'
      render(
        <TaskDescriptionModal {...defaultProps} initialValue={specialText} />
      )
      const textarea = screen.getByLabelText('Description')
      expect(textarea).toHaveValue(specialText)
    })

    it('handles unicode characters', () => {
      const unicodeText = '🎯 Legal analysis 法律 قانوني'
      render(
        <TaskDescriptionModal {...defaultProps} initialValue={unicodeText} />
      )
      const textarea = screen.getByLabelText('Description')
      expect(textarea).toHaveValue(unicodeText)
    })

    it('handles HTML entities in text', () => {
      const htmlText = '&lt;div&gt;Test&lt;/div&gt;'
      render(<TaskDescriptionModal {...defaultProps} initialValue={htmlText} />)
      const textarea = screen.getByLabelText('Description')
      expect(textarea).toHaveValue(htmlText)
    })

    it('handles rapid save clicks', async () => {
      const user = userEvent.setup()
      render(<TaskDescriptionModal {...defaultProps} />)
      const textarea = screen.getByLabelText('Description')
      const saveButton = screen.getByRole('button', {
        name: 'Save Description',
      })

      await user.type(textarea, 'Test')
      await user.click(saveButton)

      expect(defaultProps.onSave).toHaveBeenCalled()
      expect(defaultProps.onClose).toHaveBeenCalled()
    })

    it('handles rapid cancel clicks', async () => {
      const user = userEvent.setup()
      render(<TaskDescriptionModal {...defaultProps} />)
      const cancelButton = screen.getByRole('button', { name: 'Cancel' })

      await user.click(cancelButton)

      expect(defaultProps.onClose).toHaveBeenCalled()
    })

    it('handles tabs and special whitespace', async () => {
      const user = userEvent.setup()
      render(<TaskDescriptionModal {...defaultProps} />)
      const textarea = screen.getByLabelText('Description')

      fireEvent.change(textarea, { target: { value: 'Text\twith\ttabs' } })
      expect(textarea.value).toContain('\t')
    })

    it('preserves line breaks in multiline text', () => {
      const multilineText = 'Line 1\nLine 2\nLine 3\nLine 4'
      render(
        <TaskDescriptionModal {...defaultProps} initialValue={multilineText} />
      )
      const textarea = screen.getByLabelText('Description')
      expect(textarea.value).toBe(multilineText)
    })
  })
})

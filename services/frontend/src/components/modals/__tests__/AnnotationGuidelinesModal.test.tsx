/**
 * @jest-environment jsdom
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AnnotationGuidelinesModal } from '../AnnotationGuidelinesModal'

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

describe('AnnotationGuidelinesModal', () => {
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
      render(<AnnotationGuidelinesModal {...defaultProps} />)
      expect(screen.getByRole('dialog')).toBeInTheDocument()
      expect(screen.getByText('Annotation Guidelines')).toBeInTheDocument()
    })

    it('does not render when isOpen is false', () => {
      render(<AnnotationGuidelinesModal {...defaultProps} isOpen={false} />)
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })

    it('renders modal title', () => {
      render(<AnnotationGuidelinesModal {...defaultProps} />)
      expect(
        screen.getByRole('heading', { name: 'Annotation Guidelines' })
      ).toBeInTheDocument()
    })

    it('renders modal subtitle', () => {
      render(<AnnotationGuidelinesModal {...defaultProps} />)
      expect(
        screen.getByText(
          /Provide instructions to guide annotators on how to complete this task effectively/i
        )
      ).toBeInTheDocument()
    })

    it('renders close button with icon', () => {
      render(<AnnotationGuidelinesModal {...defaultProps} />)
      const closeButton = screen.getByRole('button', { name: /close/i })
      expect(closeButton).toBeInTheDocument()
      expect(screen.getByTestId('x-mark-icon')).toBeInTheDocument()
    })

    it('renders textarea with label', () => {
      render(<AnnotationGuidelinesModal {...defaultProps} />)
      expect(
        screen.getByLabelText('Guidelines for Annotators')
      ).toBeInTheDocument()
      expect(
        screen.getByPlaceholderText(
          'Provide clear instructions for annotators...'
        )
      ).toBeInTheDocument()
    })

    it('renders cancel button', () => {
      render(<AnnotationGuidelinesModal {...defaultProps} />)
      expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument()
    })

    it('renders save button', () => {
      render(<AnnotationGuidelinesModal {...defaultProps} />)
      expect(
        screen.getByRole('button', { name: 'Save Guidelines' })
      ).toBeInTheDocument()
    })

    it('renders guidelines help section', () => {
      render(<AnnotationGuidelinesModal {...defaultProps} />)
      expect(
        screen.getByText('Guidelines help annotators understand:')
      ).toBeInTheDocument()
      expect(
        screen.getByText('What constitutes a good vs. poor annotation')
      ).toBeInTheDocument()
    })

    it('renders pro tip section', () => {
      render(<AnnotationGuidelinesModal {...defaultProps} />)
      expect(screen.getByText(/Pro tip:/i)).toBeInTheDocument()
      expect(
        screen.getByText(
          /Clear guidelines improve annotation quality and reduce the need for revisions/i
        )
      ).toBeInTheDocument()
    })
  })

  describe('Initial Value Handling', () => {
    it('displays empty textarea when no initialValue provided', () => {
      render(<AnnotationGuidelinesModal {...defaultProps} />)
      const textarea = screen.getByLabelText('Guidelines for Annotators')
      expect(textarea).toHaveValue('')
    })

    it('displays initialValue in textarea', () => {
      const initialValue = 'Please annotate carefully'
      render(
        <AnnotationGuidelinesModal
          {...defaultProps}
          initialValue={initialValue}
        />
      )
      const textarea = screen.getByLabelText('Guidelines for Annotators')
      expect(textarea).toHaveValue(initialValue)
    })

    it('updates textarea when initialValue changes', () => {
      const { rerender } = render(
        <AnnotationGuidelinesModal {...defaultProps} initialValue="Initial" />
      )
      let textarea = screen.getByLabelText('Guidelines for Annotators')
      expect(textarea).toHaveValue('Initial')

      rerender(
        <AnnotationGuidelinesModal {...defaultProps} initialValue="Updated" />
      )
      textarea = screen.getByLabelText('Guidelines for Annotators')
      expect(textarea).toHaveValue('Updated')
    })

    it('handles multiline initialValue', () => {
      const multilineValue = 'Line 1\nLine 2\nLine 3'
      render(
        <AnnotationGuidelinesModal
          {...defaultProps}
          initialValue={multilineValue}
        />
      )
      const textarea = screen.getByLabelText('Guidelines for Annotators')
      expect(textarea).toHaveValue(multilineValue)
    })
  })

  describe('User Interaction', () => {
    it('allows typing in textarea', async () => {
      const user = userEvent.setup()
      render(<AnnotationGuidelinesModal {...defaultProps} />)
      const textarea = screen.getByLabelText('Guidelines for Annotators')

      await user.type(textarea, 'New guidelines')
      expect(textarea).toHaveValue('New guidelines')
    })

    it('allows clearing textarea', async () => {
      const user = userEvent.setup()
      render(
        <AnnotationGuidelinesModal
          {...defaultProps}
          initialValue="Initial text"
        />
      )
      const textarea = screen.getByLabelText('Guidelines for Annotators')

      await user.clear(textarea)
      expect(textarea).toHaveValue('')
    })

    it('allows editing existing text', async () => {
      const user = userEvent.setup()
      render(
        <AnnotationGuidelinesModal {...defaultProps} initialValue="Initial" />
      )
      const textarea = screen.getByLabelText('Guidelines for Annotators')

      await user.clear(textarea)
      await user.type(textarea, 'Edited')
      expect(textarea).toHaveValue('Edited')
    })

    it('allows multiline input', async () => {
      const user = userEvent.setup()
      render(<AnnotationGuidelinesModal {...defaultProps} />)
      const textarea = screen.getByLabelText('Guidelines for Annotators')

      await user.type(textarea, 'Line 1{Enter}Line 2{Enter}Line 3')
      expect(textarea.value).toContain('Line 1')
      expect(textarea.value).toContain('Line 2')
      expect(textarea.value).toContain('Line 3')
    })

    it('handles long text input', async () => {
      const user = userEvent.setup()
      render(<AnnotationGuidelinesModal {...defaultProps} />)
      const textarea = screen.getByLabelText('Guidelines for Annotators')
      const longText = 'A'.repeat(1000)

      await user.type(textarea, longText)
      expect(textarea).toHaveValue(longText)
    })
  })

  describe('Save Functionality', () => {
    it('calls onSave with trimmed text when Save button clicked', async () => {
      const user = userEvent.setup()
      render(<AnnotationGuidelinesModal {...defaultProps} />)
      const textarea = screen.getByLabelText('Guidelines for Annotators')
      const saveButton = screen.getByRole('button', { name: 'Save Guidelines' })

      await user.type(textarea, '  Guidelines with spaces  ')
      await user.click(saveButton)

      expect(defaultProps.onSave).toHaveBeenCalledWith('Guidelines with spaces')
      expect(defaultProps.onSave).toHaveBeenCalledTimes(1)
    })

    it('calls onClose after successful save', async () => {
      const user = userEvent.setup()
      render(<AnnotationGuidelinesModal {...defaultProps} />)
      const textarea = screen.getByLabelText('Guidelines for Annotators')
      const saveButton = screen.getByRole('button', { name: 'Save Guidelines' })

      await user.type(textarea, 'New guidelines')
      await user.click(saveButton)

      expect(defaultProps.onClose).toHaveBeenCalledTimes(1)
    })

    it('trims leading whitespace on save', async () => {
      const user = userEvent.setup()
      render(<AnnotationGuidelinesModal {...defaultProps} />)
      const textarea = screen.getByLabelText('Guidelines for Annotators')
      const saveButton = screen.getByRole('button', { name: 'Save Guidelines' })

      await user.type(textarea, '   Leading spaces')
      await user.click(saveButton)

      expect(defaultProps.onSave).toHaveBeenCalledWith('Leading spaces')
    })

    it('trims trailing whitespace on save', async () => {
      const user = userEvent.setup()
      render(<AnnotationGuidelinesModal {...defaultProps} />)
      const textarea = screen.getByLabelText('Guidelines for Annotators')
      const saveButton = screen.getByRole('button', { name: 'Save Guidelines' })

      await user.type(textarea, 'Trailing spaces   ')
      await user.click(saveButton)

      expect(defaultProps.onSave).toHaveBeenCalledWith('Trailing spaces')
    })

    it('saves empty string when textarea is empty', async () => {
      const user = userEvent.setup()
      render(<AnnotationGuidelinesModal {...defaultProps} />)
      const saveButton = screen.getByRole('button', { name: 'Save Guidelines' })

      await user.click(saveButton)

      expect(defaultProps.onSave).toHaveBeenCalledWith('')
    })

    it('preserves internal whitespace when saving', async () => {
      const user = userEvent.setup()
      render(<AnnotationGuidelinesModal {...defaultProps} />)
      const textarea = screen.getByLabelText('Guidelines for Annotators')
      const saveButton = screen.getByRole('button', { name: 'Save Guidelines' })

      await user.type(textarea, 'Text with  multiple  spaces')
      await user.click(saveButton)

      expect(defaultProps.onSave).toHaveBeenCalledWith(
        'Text with  multiple  spaces'
      )
    })

    it('saves multiline text correctly', async () => {
      const user = userEvent.setup()
      render(<AnnotationGuidelinesModal {...defaultProps} />)
      const textarea = screen.getByLabelText('Guidelines for Annotators')
      const saveButton = screen.getByRole('button', { name: 'Save Guidelines' })

      await user.type(textarea, 'Line 1{Enter}Line 2{Enter}Line 3')
      await user.click(saveButton)

      const savedValue = defaultProps.onSave.mock.calls[0][0]
      expect(savedValue).toContain('Line 1')
      expect(savedValue).toContain('Line 2')
      expect(savedValue).toContain('Line 3')
    })
  })

  describe('Cancel Functionality', () => {
    it('calls onClose when Cancel button clicked', async () => {
      const user = userEvent.setup()
      render(<AnnotationGuidelinesModal {...defaultProps} />)
      const cancelButton = screen.getByRole('button', { name: 'Cancel' })

      await user.click(cancelButton)

      expect(defaultProps.onClose).toHaveBeenCalledTimes(1)
    })

    it('does not call onSave when cancelled', async () => {
      const user = userEvent.setup()
      render(<AnnotationGuidelinesModal {...defaultProps} />)
      const textarea = screen.getByLabelText('Guidelines for Annotators')
      const cancelButton = screen.getByRole('button', { name: 'Cancel' })

      await user.type(textarea, 'Some text')
      await user.click(cancelButton)

      expect(defaultProps.onSave).not.toHaveBeenCalled()
    })

    it('resets textarea to initialValue when cancelled', async () => {
      const user = userEvent.setup()
      const initialValue = 'Original text'
      render(
        <AnnotationGuidelinesModal
          {...defaultProps}
          initialValue={initialValue}
        />
      )
      const textarea = screen.getByLabelText('Guidelines for Annotators')
      const cancelButton = screen.getByRole('button', { name: 'Cancel' })

      await user.clear(textarea)
      await user.type(textarea, 'Modified text')
      expect(textarea).toHaveValue('Modified text')

      await user.click(cancelButton)

      expect(defaultProps.onClose).toHaveBeenCalled()
    })

    it('calls onClose when close icon clicked', async () => {
      const user = userEvent.setup()
      render(<AnnotationGuidelinesModal {...defaultProps} />)
      const closeButton = screen.getByRole('button', { name: /close/i })

      await user.click(closeButton)

      expect(defaultProps.onClose).toHaveBeenCalledTimes(1)
    })

    it('resets form when close icon clicked', async () => {
      const user = userEvent.setup()
      const initialValue = 'Original'
      render(
        <AnnotationGuidelinesModal
          {...defaultProps}
          initialValue={initialValue}
        />
      )
      const textarea = screen.getByLabelText('Guidelines for Annotators')
      const closeButton = screen.getByRole('button', { name: /close/i })

      await user.clear(textarea)
      await user.type(textarea, 'New text')
      await user.click(closeButton)

      expect(defaultProps.onClose).toHaveBeenCalled()
    })
  })

  describe('Modal Behavior', () => {
    it('maintains state when reopened without closing', () => {
      const { rerender } = render(
        <AnnotationGuidelinesModal {...defaultProps} isOpen={true} />
      )
      const textarea = screen.getByLabelText('Guidelines for Annotators')
      fireEvent.change(textarea, { target: { value: 'Test text' } })

      rerender(<AnnotationGuidelinesModal {...defaultProps} isOpen={true} />)

      expect(textarea).toHaveValue('Test text')
    })

    it('handles rapid open/close transitions', () => {
      const { rerender } = render(
        <AnnotationGuidelinesModal {...defaultProps} isOpen={false} />
      )
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()

      rerender(<AnnotationGuidelinesModal {...defaultProps} isOpen={true} />)
      expect(screen.getByRole('dialog')).toBeInTheDocument()

      rerender(<AnnotationGuidelinesModal {...defaultProps} isOpen={false} />)
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()

      rerender(<AnnotationGuidelinesModal {...defaultProps} isOpen={true} />)
      expect(screen.getByRole('dialog')).toBeInTheDocument()
    })

    it('handles backdrop click to close', async () => {
      const { container } = render(
        <AnnotationGuidelinesModal {...defaultProps} />
      )

      const backdrop = container.querySelector('.fixed.inset-0.bg-black')
      if (backdrop) {
        fireEvent.click(backdrop)
        await waitFor(() => {
          expect(defaultProps.onClose).toHaveBeenCalled()
        })
      }
    })
  })

  describe('Form State Management', () => {
    it('preserves state across re-renders when modal stays open', () => {
      const { rerender } = render(
        <AnnotationGuidelinesModal {...defaultProps} />
      )
      const textarea = screen.getByLabelText('Guidelines for Annotators')
      fireEvent.change(textarea, { target: { value: 'Persistent text' } })

      rerender(<AnnotationGuidelinesModal {...defaultProps} />)

      expect(textarea).toHaveValue('Persistent text')
    })

    it('updates when initialValue prop changes while open', () => {
      const { rerender } = render(
        <AnnotationGuidelinesModal {...defaultProps} initialValue="First" />
      )
      let textarea = screen.getByLabelText('Guidelines for Annotators')
      expect(textarea).toHaveValue('First')

      rerender(
        <AnnotationGuidelinesModal {...defaultProps} initialValue="Second" />
      )
      textarea = screen.getByLabelText('Guidelines for Annotators')
      expect(textarea).toHaveValue('Second')
    })

    it('handles empty string initialValue', () => {
      render(<AnnotationGuidelinesModal {...defaultProps} initialValue="" />)
      const textarea = screen.getByLabelText('Guidelines for Annotators')
      expect(textarea).toHaveValue('')
    })
  })

  describe('Accessibility', () => {
    it('has proper ARIA label for close button', () => {
      render(<AnnotationGuidelinesModal {...defaultProps} />)
      expect(
        screen.getByRole('button', { name: /close/i })
      ).toBeInTheDocument()
    })

    it('has proper ID for textarea', () => {
      render(<AnnotationGuidelinesModal {...defaultProps} />)
      const textarea = screen.getByLabelText('Guidelines for Annotators')
      expect(textarea).toHaveAttribute('id', 'annotation-guidelines')
    })

    it('textarea has proper placeholder', () => {
      render(<AnnotationGuidelinesModal {...defaultProps} />)
      const textarea = screen.getByLabelText('Guidelines for Annotators')
      expect(textarea).toHaveAttribute(
        'placeholder',
        'Provide clear instructions for annotators...'
      )
    })

    it('textarea has correct row attribute', () => {
      render(<AnnotationGuidelinesModal {...defaultProps} />)
      const textarea = screen.getByLabelText('Guidelines for Annotators')
      expect(textarea).toHaveAttribute('rows', '8')
    })

    it('maintains proper heading structure', () => {
      render(<AnnotationGuidelinesModal {...defaultProps} />)
      const heading = screen.getByRole('heading', {
        name: 'Annotation Guidelines',
      })
      expect(heading).toBeInTheDocument()
    })

    it('all buttons are keyboard accessible', () => {
      render(<AnnotationGuidelinesModal {...defaultProps} />)
      const buttons = screen.getAllByRole('button')
      expect(buttons.length).toBeGreaterThan(0)
      buttons.forEach((button) => {
        expect(button).toBeInTheDocument()
      })
    })
  })

  describe('Edge Cases', () => {
    it('handles undefined initialValue', () => {
      render(
        <AnnotationGuidelinesModal {...defaultProps} initialValue={undefined} />
      )
      const textarea = screen.getByLabelText('Guidelines for Annotators')
      expect(textarea).toHaveValue('')
    })

    it('handles very long initialValue', () => {
      const longText = 'A'.repeat(10000)
      render(
        <AnnotationGuidelinesModal {...defaultProps} initialValue={longText} />
      )
      const textarea = screen.getByLabelText('Guidelines for Annotators')
      expect(textarea).toHaveValue(longText)
    })

    it('handles special characters in initialValue', () => {
      const specialText = '!@#$%^&*()_+-=[]{}|;:\'",.<>?/~`'
      render(
        <AnnotationGuidelinesModal
          {...defaultProps}
          initialValue={specialText}
        />
      )
      const textarea = screen.getByLabelText('Guidelines for Annotators')
      expect(textarea).toHaveValue(specialText)
    })

    it('handles unicode characters', () => {
      const unicodeText = '🚀 ✨ 你好 مرحبا'
      render(
        <AnnotationGuidelinesModal
          {...defaultProps}
          initialValue={unicodeText}
        />
      )
      const textarea = screen.getByLabelText('Guidelines for Annotators')
      expect(textarea).toHaveValue(unicodeText)
    })

    it('saves text with only whitespace as empty string', async () => {
      const user = userEvent.setup()
      render(<AnnotationGuidelinesModal {...defaultProps} />)
      const textarea = screen.getByLabelText('Guidelines for Annotators')
      const saveButton = screen.getByRole('button', { name: 'Save Guidelines' })

      await user.type(textarea, '   ')
      await user.click(saveButton)

      expect(defaultProps.onSave).toHaveBeenCalledWith('')
    })

    it('handles rapid save clicks', async () => {
      const user = userEvent.setup()
      render(<AnnotationGuidelinesModal {...defaultProps} />)
      const textarea = screen.getByLabelText('Guidelines for Annotators')
      const saveButton = screen.getByRole('button', { name: 'Save Guidelines' })

      await user.type(textarea, 'Test')
      await user.click(saveButton)

      expect(defaultProps.onSave).toHaveBeenCalled()
      expect(defaultProps.onClose).toHaveBeenCalled()
    })

    it('handles rapid cancel clicks', async () => {
      const user = userEvent.setup()
      render(<AnnotationGuidelinesModal {...defaultProps} />)
      const cancelButton = screen.getByRole('button', { name: 'Cancel' })

      await user.click(cancelButton)

      expect(defaultProps.onClose).toHaveBeenCalled()
    })
  })
})

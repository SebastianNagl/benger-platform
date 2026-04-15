/**
 * @jest-environment jsdom
 */
import { describe, expect, it, jest } from '@jest/globals'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '../Dialog'

// Mock @headlessui/react components
jest.mock('@headlessui/react', () => {
  const React = jest.requireActual('react')

  function MockDialog({ children, onClose, className }: any) {
    React.useEffect(() => {
      if (onClose) {
        ;(global as any).__mockDialogClose = onClose
      }
    }, [onClose])

    return (
      <div data-testid="dialog-wrapper" className={className}>
        {children}
      </div>
    )
  }

  function MockDialogPanel({ children, className }: any) {
    return (
      <div role="dialog" data-testid="dialog-panel" className={className}>
        {children}
      </div>
    )
  }
  MockDialogPanel.displayName = 'MockDialog.Panel'
  MockDialog.Panel = MockDialogPanel

  function MockDialogTitle({ children, className, as: Component = 'h3' }: any) {
    return <Component className={className}>{children}</Component>
  }
  MockDialogTitle.displayName = 'MockDialog.Title'
  MockDialog.Title = MockDialogTitle

  function MockTransition({ children, show }: any) {
    return show ? <>{children}</> : null
  }

  function MockTransitionChild({ children }: any) {
    return <>{children}</>
  }
  MockTransitionChild.displayName = 'MockTransition.Child'
  MockTransition.Child = MockTransitionChild

  return {
    Dialog: MockDialog,
    Transition: MockTransition,
  }
})

// Mock @heroicons/react
jest.mock('@heroicons/react/24/outline', () => ({
  XMarkIcon: ({ className }: any) => (
    <svg data-testid="x-mark-icon" className={className}>
      <title>Close</title>
    </svg>
  ),
}))

describe('Dialog Component', () => {
  describe('Basic Rendering', () => {
    it('should render dialog when open prop is true', () => {
      render(
        <Dialog open={true} onOpenChange={jest.fn()}>
          <div>Dialog Content</div>
        </Dialog>
      )

      expect(screen.getByRole('dialog')).toBeInTheDocument()
      expect(screen.getByText('Dialog Content')).toBeInTheDocument()
    })

    it('should not render dialog when open prop is false', () => {
      render(
        <Dialog open={false} onOpenChange={jest.fn()}>
          <div>Dialog Content</div>
        </Dialog>
      )

      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
      expect(screen.queryByText('Dialog Content')).not.toBeInTheDocument()
    })

    it('should render dialog when isOpen prop is true', () => {
      render(
        <Dialog isOpen={true} onClose={jest.fn()}>
          <div>Dialog Content</div>
        </Dialog>
      )

      expect(screen.getByRole('dialog')).toBeInTheDocument()
      expect(screen.getByText('Dialog Content')).toBeInTheDocument()
    })

    it('should not render dialog when isOpen prop is false', () => {
      render(
        <Dialog isOpen={false} onClose={jest.fn()}>
          <div>Dialog Content</div>
        </Dialog>
      )

      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })

    it('should render dialog with children', () => {
      render(
        <Dialog open={true} onOpenChange={jest.fn()}>
          <div data-testid="child-1">Child 1</div>
          <div data-testid="child-2">Child 2</div>
        </Dialog>
      )

      expect(screen.getByTestId('child-1')).toBeInTheDocument()
      expect(screen.getByTestId('child-2')).toBeInTheDocument()
    })
  })

  describe('Open/Close State', () => {
    it('should support open/onOpenChange API style', () => {
      const handleOpenChange = jest.fn()
      render(
        <Dialog open={true} onOpenChange={handleOpenChange}>
          <div>Content</div>
        </Dialog>
      )

      expect(screen.getByRole('dialog')).toBeInTheDocument()
    })

    it('should support isOpen/onClose API style', () => {
      const handleClose = jest.fn()
      render(
        <Dialog isOpen={true} onClose={handleClose}>
          <div>Content</div>
        </Dialog>
      )

      expect(screen.getByRole('dialog')).toBeInTheDocument()
    })

    it('should default to closed when no open props provided', () => {
      render(
        <Dialog onClose={jest.fn()}>
          <div>Content</div>
        </Dialog>
      )

      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })

    it('should prioritize open prop over isOpen prop', () => {
      render(
        <Dialog open={true} isOpen={false} onClose={jest.fn()}>
          <div>Content</div>
        </Dialog>
      )

      expect(screen.getByRole('dialog')).toBeInTheDocument()
    })
  })

  describe('User Interaction', () => {
    it('should call onOpenChange with false when close button clicked', async () => {
      const user = userEvent.setup()
      const handleOpenChange = jest.fn()

      render(
        <Dialog open={true} onOpenChange={handleOpenChange} title="Test Dialog">
          <div>Content</div>
        </Dialog>
      )

      const closeButton = screen.getByRole('button')
      await user.click(closeButton)

      expect(handleOpenChange).toHaveBeenCalledWith(false)
    })

    it('should call onClose when close button clicked', async () => {
      const user = userEvent.setup()
      const handleClose = jest.fn()

      render(
        <Dialog isOpen={true} onClose={handleClose} title="Test Dialog">
          <div>Content</div>
        </Dialog>
      )

      const closeButton = screen.getByRole('button')
      await user.click(closeButton)

      expect(handleClose).toHaveBeenCalled()
    })

    it('should not error when close button clicked without handlers', async () => {
      const user = userEvent.setup()

      render(
        <Dialog open={true} title="Test Dialog">
          <div>Content</div>
        </Dialog>
      )

      const closeButton = screen.getByRole('button')
      await expect(user.click(closeButton)).resolves.not.toThrow()
    })
  })

  describe('Title and Description', () => {
    it('should render title when title prop is provided', () => {
      render(
        <Dialog open={true} onClose={jest.fn()} title="Test Dialog Title">
          <div>Content</div>
        </Dialog>
      )

      expect(screen.getByText('Test Dialog Title')).toBeInTheDocument()
      expect(screen.getByRole('heading', { level: 3 })).toHaveTextContent(
        'Test Dialog Title'
      )
    })

    it('should not render title section when title prop is not provided', () => {
      render(
        <Dialog open={true} onClose={jest.fn()}>
          <div>Content</div>
        </Dialog>
      )

      expect(screen.queryByRole('heading')).not.toBeInTheDocument()
    })

    it('should render close button only when title is provided', () => {
      const { rerender } = render(
        <Dialog open={true} onClose={jest.fn()} title="Test">
          <div>Content</div>
        </Dialog>
      )

      expect(screen.getByRole('button')).toBeInTheDocument()
      expect(screen.getByTestId('x-mark-icon')).toBeInTheDocument()

      rerender(
        <Dialog open={true} onClose={jest.fn()}>
          <div>Content</div>
        </Dialog>
      )

      expect(screen.queryByRole('button')).not.toBeInTheDocument()
    })

    it('should render title as h3 element', () => {
      render(
        <Dialog open={true} onClose={jest.fn()} title="My Dialog">
          <div>Content</div>
        </Dialog>
      )

      const heading = screen.getByRole('heading', { level: 3 })
      expect(heading).toHaveTextContent('My Dialog')
    })
  })

  describe('Buttons/Actions', () => {
    it('should render action buttons passed as children', () => {
      render(
        <Dialog open={true} onClose={jest.fn()} title="Test">
          <div>
            <button>Cancel</button>
            <button>Confirm</button>
          </div>
        </Dialog>
      )

      expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument()
      expect(
        screen.getByRole('button', { name: 'Confirm' })
      ).toBeInTheDocument()
    })

    it('should handle multiple button clicks independently', async () => {
      const user = userEvent.setup()
      const handleCancel = jest.fn()
      const handleConfirm = jest.fn()

      render(
        <Dialog open={true} onClose={jest.fn()} title="Test">
          <div>
            <button onClick={handleCancel}>Cancel</button>
            <button onClick={handleConfirm}>Confirm</button>
          </div>
        </Dialog>
      )

      await user.click(screen.getByRole('button', { name: 'Cancel' }))
      expect(handleCancel).toHaveBeenCalledTimes(1)
      expect(handleConfirm).not.toHaveBeenCalled()

      await user.click(screen.getByRole('button', { name: 'Confirm' }))
      expect(handleConfirm).toHaveBeenCalledTimes(1)
      expect(handleCancel).toHaveBeenCalledTimes(1)
    })
  })

  describe('Styling', () => {
    it('should apply default styling classes', () => {
      render(
        <Dialog open={true} onClose={jest.fn()}>
          <div>Content</div>
        </Dialog>
      )

      const dialog = screen.getByRole('dialog')
      expect(dialog.className).toContain('bg-white')
      expect(dialog.className).toContain('dark:bg-gray-800')
      expect(dialog.className).toContain('rounded-2xl')
    })

    it('should apply custom className prop', () => {
      render(
        <Dialog open={true} onClose={jest.fn()} className="custom-class">
          <div>Content</div>
        </Dialog>
      )

      const dialog = screen.getByRole('dialog')
      expect(dialog.className).toContain('custom-class')
    })

    it('should merge custom className with default classes', () => {
      render(
        <Dialog open={true} onClose={jest.fn()} className="custom-width">
          <div>Content</div>
        </Dialog>
      )

      const dialog = screen.getByRole('dialog')
      expect(dialog.className).toContain('custom-width')
      expect(dialog.className).toContain('bg-white')
    })

    it('should apply title styling when title is provided', () => {
      render(
        <Dialog open={true} onClose={jest.fn()} title="Styled Title">
          <div>Content</div>
        </Dialog>
      )

      const heading = screen.getByRole('heading', { level: 3 })
      expect(heading.className).toContain('text-lg')
      expect(heading.className).toContain('font-medium')
      expect(heading.className).toContain('text-gray-900')
      expect(heading.className).toContain('dark:text-white')
    })

    it('should apply close button styling', () => {
      render(
        <Dialog open={true} onClose={jest.fn()} title="Test">
          <div>Content</div>
        </Dialog>
      )

      const closeButton = screen.getByRole('button')
      expect(closeButton.className).toContain('text-gray-400')
      expect(closeButton.className).toContain('hover:text-gray-600')
      expect(closeButton.className).toContain('absolute')
    })
  })

  describe('Accessibility', () => {
    it('should have role="dialog" attribute', () => {
      render(
        <Dialog open={true} onClose={jest.fn()}>
          <div>Content</div>
        </Dialog>
      )

      expect(screen.getByRole('dialog')).toBeInTheDocument()
    })

    it('should have accessible title when provided', () => {
      render(
        <Dialog open={true} onClose={jest.fn()} title="Accessible Dialog">
          <div>Content</div>
        </Dialog>
      )

      expect(
        screen.getByRole('heading', { name: 'Accessible Dialog' })
      ).toBeInTheDocument()
    })

    it('should have accessible close button', () => {
      render(
        <Dialog open={true} onClose={jest.fn()} title="Test">
          <div>Content</div>
        </Dialog>
      )

      const closeButton = screen.getByRole('button')
      expect(closeButton).toBeInTheDocument()
    })

    it('should provide keyboard navigation support', async () => {
      const user = userEvent.setup()
      const handleClose = jest.fn()

      render(
        <Dialog open={true} onClose={handleClose} title="Test">
          <div>
            <button>Action 1</button>
            <button>Action 2</button>
          </div>
        </Dialog>
      )

      await user.tab()
      await user.tab()
      await user.tab()

      // Verify all buttons are accessible via keyboard
      expect(document.activeElement).toBeInstanceOf(HTMLButtonElement)
    })

    it('should maintain focus management', () => {
      render(
        <Dialog open={true} onClose={jest.fn()} title="Focus Test">
          <input type="text" placeholder="First input" />
          <input type="text" placeholder="Second input" />
        </Dialog>
      )

      const inputs = screen.getAllByRole('textbox')
      expect(inputs).toHaveLength(2)
    })
  })

  describe('Edge Cases', () => {
    it('should handle undefined handlers gracefully', () => {
      expect(() =>
        render(
          <Dialog open={true}>
            <div>Content</div>
          </Dialog>
        )
      ).not.toThrow()
    })

    it('should handle empty children', () => {
      render(
        <Dialog open={true} onClose={jest.fn()}>
          {null}
        </Dialog>
      )

      expect(screen.getByRole('dialog')).toBeInTheDocument()
    })

    it('should handle empty title string', () => {
      render(
        <Dialog open={true} onClose={jest.fn()} title="">
          <div>Content</div>
        </Dialog>
      )

      expect(screen.queryByRole('heading')).not.toBeInTheDocument()
    })

    it('should handle rapid open/close transitions', async () => {
      const { rerender } = render(
        <Dialog open={false} onClose={jest.fn()}>
          <div>Content</div>
        </Dialog>
      )

      rerender(
        <Dialog open={true} onClose={jest.fn()}>
          <div>Content</div>
        </Dialog>
      )

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument()
      })

      rerender(
        <Dialog open={false} onClose={jest.fn()}>
          <div>Content</div>
        </Dialog>
      )

      await waitFor(() => {
        expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
      })
    })

    it('should handle complex nested content', () => {
      render(
        <Dialog open={true} onClose={jest.fn()} title="Nested Content">
          <div>
            <div>
              <p>Paragraph 1</p>
              <div>
                <span>Nested span</span>
                <ul>
                  <li>Item 1</li>
                  <li>Item 2</li>
                </ul>
              </div>
            </div>
          </div>
        </Dialog>
      )

      expect(screen.getByText('Paragraph 1')).toBeInTheDocument()
      expect(screen.getByText('Nested span')).toBeInTheDocument()
      expect(screen.getByText('Item 1')).toBeInTheDocument()
      expect(screen.getByText('Item 2')).toBeInTheDocument()
    })

    it('should handle long content gracefully', () => {
      const longContent = 'A'.repeat(1000)

      render(
        <Dialog open={true} onClose={jest.fn()} title="Long Content">
          <div>{longContent}</div>
        </Dialog>
      )

      expect(screen.getByText(longContent)).toBeInTheDocument()
    })

    it('should handle special characters in title', () => {
      render(
        <Dialog
          open={true}
          onClose={jest.fn()}
          title="Special <>&quot;'` Characters"
        >
          <div>Content</div>
        </Dialog>
      )

      expect(screen.getByText(/Special.*Characters/)).toBeInTheDocument()
    })

    it('should handle changing handlers', async () => {
      const user = userEvent.setup()
      const handler1 = jest.fn()
      const handler2 = jest.fn()

      const { rerender } = render(
        <Dialog open={true} onClose={handler1} title="Test">
          <div>Content</div>
        </Dialog>
      )

      await user.click(screen.getByRole('button'))
      expect(handler1).toHaveBeenCalledTimes(1)
      expect(handler2).not.toHaveBeenCalled()

      rerender(
        <Dialog open={true} onClose={handler2} title="Test">
          <div>Content</div>
        </Dialog>
      )

      await user.click(screen.getByRole('button'))
      expect(handler1).toHaveBeenCalledTimes(1)
      expect(handler2).toHaveBeenCalledTimes(1)
    })
  })

  describe('DialogContent Component', () => {
    it('should render DialogContent with children', () => {
      render(
        <DialogContent>
          <div>Dialog Content</div>
        </DialogContent>
      )

      expect(screen.getByText('Dialog Content')).toBeInTheDocument()
    })

    it('should apply default DialogContent classes', () => {
      render(
        <DialogContent>
          <div>Content</div>
        </DialogContent>
      )

      const dialog = screen.getByRole('dialog')
      expect(dialog.className).toContain('bg-white')
      expect(dialog.className).toContain('dark:bg-gray-800')
    })

    it('should apply custom className to DialogContent', () => {
      render(
        <DialogContent className="custom-content-class">
          <div>Content</div>
        </DialogContent>
      )

      const dialog = screen.getByRole('dialog')
      expect(dialog.className).toContain('custom-content-class')
    })
  })

  describe('DialogHeader Component', () => {
    it('should render DialogHeader with children', () => {
      render(
        <DialogHeader>
          <div>Header Content</div>
        </DialogHeader>
      )

      expect(screen.getByText('Header Content')).toBeInTheDocument()
    })

    it('should apply default DialogHeader classes', () => {
      render(
        <DialogHeader>
          <div>Header</div>
        </DialogHeader>
      )

      const header = screen.getByText('Header').parentElement
      expect(header?.className).toContain('mb-4')
    })

    it('should apply custom className to DialogHeader', () => {
      render(
        <DialogHeader className="custom-header-class">
          <div>Header</div>
        </DialogHeader>
      )

      const header = screen.getByText('Header').parentElement
      expect(header?.className).toContain('custom-header-class')
      expect(header?.className).toContain('mb-4')
    })
  })

  describe('DialogTitle Component', () => {
    it('should render DialogTitle with children', () => {
      render(<DialogTitle>Title Text</DialogTitle>)

      expect(screen.getByText('Title Text')).toBeInTheDocument()
    })

    it('should render DialogTitle as h3 element', () => {
      render(<DialogTitle>My Title</DialogTitle>)

      const heading = screen.getByRole('heading', { level: 3 })
      expect(heading).toHaveTextContent('My Title')
    })

    it('should apply default DialogTitle classes', () => {
      render(<DialogTitle>Title</DialogTitle>)

      const heading = screen.getByRole('heading', { level: 3 })
      expect(heading.className).toContain('text-lg')
      expect(heading.className).toContain('font-medium')
      expect(heading.className).toContain('text-gray-900')
      expect(heading.className).toContain('dark:text-white')
    })

    it('should apply custom className to DialogTitle', () => {
      render(<DialogTitle className="custom-title-class">Title</DialogTitle>)

      const heading = screen.getByRole('heading', { level: 3 })
      expect(heading.className).toContain('custom-title-class')
    })
  })

  describe('DialogTrigger Component', () => {
    it('should render DialogTrigger with children', () => {
      render(
        <DialogTrigger>
          <button>Open Dialog</button>
        </DialogTrigger>
      )

      expect(
        screen.getByRole('button', { name: 'Open Dialog' })
      ).toBeInTheDocument()
    })

    it('should handle asChild prop', () => {
      render(
        <DialogTrigger asChild>
          <button>Trigger Button</button>
        </DialogTrigger>
      )

      expect(
        screen.getByRole('button', { name: 'Trigger Button' })
      ).toBeInTheDocument()
    })

    it('should pass through all children unchanged', () => {
      render(
        <DialogTrigger>
          <div data-testid="trigger-content">
            <span>Child 1</span>
            <span>Child 2</span>
          </div>
        </DialogTrigger>
      )

      expect(screen.getByTestId('trigger-content')).toBeInTheDocument()
      expect(screen.getByText('Child 1')).toBeInTheDocument()
      expect(screen.getByText('Child 2')).toBeInTheDocument()
    })
  })

  describe('Integration Tests', () => {
    it('should work with all components together', () => {
      render(
        <Dialog open={true} onClose={jest.fn()}>
          <DialogHeader>
            <DialogTitle>Complete Dialog</DialogTitle>
          </DialogHeader>
          <DialogContent>
            <p>This is the dialog content</p>
          </DialogContent>
        </Dialog>
      )

      expect(
        screen.getByRole('heading', { name: 'Complete Dialog' })
      ).toBeInTheDocument()
      expect(screen.getByText('This is the dialog content')).toBeInTheDocument()
    })

    it('should handle complete dialog workflow', async () => {
      const user = userEvent.setup()
      const handleClose = jest.fn()

      render(
        <div>
          <DialogTrigger>
            <button>Open</button>
          </DialogTrigger>
          <Dialog open={true} onClose={handleClose} title="Workflow Dialog">
            <div>
              <p>Dialog content</p>
              <button onClick={handleClose}>Close Dialog</button>
            </div>
          </Dialog>
        </div>
      )

      expect(screen.getByRole('dialog')).toBeInTheDocument()

      await user.click(screen.getByRole('button', { name: 'Close Dialog' }))
      expect(handleClose).toHaveBeenCalled()
    })
  })
})

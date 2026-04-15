/**
 * @jest-environment jsdom
 */

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Tooltip } from '../Tooltip'

describe('Tooltip Component', () => {
  describe('Basic Rendering', () => {
    it('renders children content', () => {
      render(
        <Tooltip content="Tooltip text">
          <button>Hover me</button>
        </Tooltip>
      )

      expect(screen.getByText('Hover me')).toBeInTheDocument()
    })

    it('renders wrapper div', () => {
      const { container } = render(
        <Tooltip content="Tooltip text">
          <span>Content</span>
        </Tooltip>
      )

      const wrapper = container.querySelector('div')
      expect(wrapper).toBeInTheDocument()
    })

    it('renders multiple children', () => {
      render(
        <Tooltip content="Tooltip text">
          <span>First</span>
          <span>Second</span>
        </Tooltip>
      )

      expect(screen.getByText('First')).toBeInTheDocument()
      expect(screen.getByText('Second')).toBeInTheDocument()
    })

    it('renders text children', () => {
      render(<Tooltip content="Tooltip text">Plain text child</Tooltip>)

      expect(screen.getByText('Plain text child')).toBeInTheDocument()
    })
  })

  describe('String Content (Title Attribute)', () => {
    it('adds title attribute for string content', () => {
      const { container } = render(
        <Tooltip content="Helpful tooltip">
          <button>Action</button>
        </Tooltip>
      )

      const wrapper = container.querySelector('div')
      expect(wrapper).toHaveAttribute('title', 'Helpful tooltip')
    })

    it('renders correct tooltip text', () => {
      const { container } = render(
        <Tooltip content="This is the tooltip">
          <span>Hover target</span>
        </Tooltip>
      )

      const wrapper = container.querySelector('div')
      expect(wrapper?.getAttribute('title')).toBe('This is the tooltip')
    })

    it('handles simple string tooltips', () => {
      const { container } = render(
        <Tooltip content="Save">
          <button>💾</button>
        </Tooltip>
      )

      const wrapper = container.querySelector('div')
      expect(wrapper).toHaveAttribute('title', 'Save')
    })

    it('handles multi-line tooltip text', () => {
      const multiLineText = 'Line 1\nLine 2\nLine 3'
      const { container } = render(
        <Tooltip content={multiLineText}>
          <span>Info</span>
        </Tooltip>
      )

      const wrapper = container.querySelector('div')
      expect(wrapper).toHaveAttribute('title', multiLineText)
    })

    it('handles empty string content', () => {
      const { container } = render(
        <Tooltip content="">
          <span>No tooltip</span>
        </Tooltip>
      )

      const wrapper = container.querySelector('div')
      expect(wrapper).toHaveAttribute('title', '')
    })
  })

  describe('Complex Content (ReactNode)', () => {
    it('does not add title attribute for ReactNode content', () => {
      const complexContent = <div>Complex tooltip</div>
      const { container } = render(
        <Tooltip content={complexContent}>
          <button>Action</button>
        </Tooltip>
      )

      const wrapper = container.querySelector('div')
      expect(wrapper).not.toHaveAttribute('title')
    })

    it('renders children even with complex content', () => {
      const complexContent = (
        <div>
          <strong>Bold</strong> tooltip
        </div>
      )
      render(
        <Tooltip content={complexContent}>
          <span>Hover target</span>
        </Tooltip>
      )

      expect(screen.getByText('Hover target')).toBeInTheDocument()
    })

    it('handles JSX content gracefully', () => {
      const jsxContent = (
        <>
          <span>Icon</span>
          <span>Text</span>
        </>
      )
      const { container } = render(
        <Tooltip content={jsxContent}>
          <button>Hover</button>
        </Tooltip>
      )

      const wrapper = container.querySelector('div')
      expect(wrapper).not.toHaveAttribute('title')
      expect(screen.getByText('Hover')).toBeInTheDocument()
    })
  })

  describe('Styling', () => {
    it('applies custom className to wrapper', () => {
      const { container } = render(
        <Tooltip content="Tooltip" className="custom-class">
          <span>Content</span>
        </Tooltip>
      )

      const wrapper = container.querySelector('div')
      expect(wrapper).toHaveClass('custom-class')
    })

    it('applies multiple classes', () => {
      const { container } = render(
        <Tooltip content="Tooltip" className="class-1 class-2 class-3">
          <span>Content</span>
        </Tooltip>
      )

      const wrapper = container.querySelector('div')
      expect(wrapper).toHaveClass('class-1', 'class-2', 'class-3')
    })

    it('works without className prop', () => {
      const { container } = render(
        <Tooltip content="Tooltip">
          <span>Content</span>
        </Tooltip>
      )

      const wrapper = container.querySelector('div')
      expect(wrapper).toBeInTheDocument()
      expect(wrapper?.className).toBe('')
    })

    it('renders with empty className', () => {
      const { container } = render(
        <Tooltip content="Tooltip" className="">
          <span>Content</span>
        </Tooltip>
      )

      const wrapper = container.querySelector('div')
      expect(wrapper?.className).toBe('')
    })
  })

  describe('Children Types', () => {
    it('renders button children', () => {
      render(
        <Tooltip content="Click action">
          <button type="button">Click me</button>
        </Tooltip>
      )

      expect(screen.getByRole('button')).toBeInTheDocument()
    })

    it('renders link children', () => {
      render(
        <Tooltip content="Navigate">
          <a href="/path">Go here</a>
        </Tooltip>
      )

      expect(screen.getByRole('link')).toBeInTheDocument()
    })

    it('renders icon children', () => {
      render(
        <Tooltip content="Settings">
          <svg data-testid="settings-icon">
            <path />
          </svg>
        </Tooltip>
      )

      expect(screen.getByTestId('settings-icon')).toBeInTheDocument()
    })

    it('renders nested component children', () => {
      const CustomComponent = () => <div>Custom Component</div>
      render(
        <Tooltip content="Info">
          <CustomComponent />
        </Tooltip>
      )

      expect(screen.getByText('Custom Component')).toBeInTheDocument()
    })

    it('renders fragment children', () => {
      render(
        <Tooltip content="Multiple items">
          <>
            <span>Item 1</span>
            <span>Item 2</span>
          </>
        </Tooltip>
      )

      expect(screen.getByText('Item 1')).toBeInTheDocument()
      expect(screen.getByText('Item 2')).toBeInTheDocument()
    })
  })

  describe('Interaction', () => {
    it('children remain interactive with tooltip', async () => {
      const handleClick = jest.fn()
      const user = userEvent.setup()

      render(
        <Tooltip content="Click me">
          <button onClick={handleClick}>Action</button>
        </Tooltip>
      )

      const button = screen.getByRole('button')
      await user.click(button)

      expect(handleClick).toHaveBeenCalledTimes(1)
    })

    it('does not interfere with child event handlers', async () => {
      const handleMouseEnter = jest.fn()
      const handleMouseLeave = jest.fn()
      const user = userEvent.setup()

      render(
        <Tooltip content="Hover tooltip">
          <div
            onMouseEnter={handleMouseEnter}
            onMouseLeave={handleMouseLeave}
            data-testid="hover-target"
          >
            Hover me
          </div>
        </Tooltip>
      )

      const target = screen.getByTestId('hover-target')
      await user.hover(target)

      expect(handleMouseEnter).toHaveBeenCalled()
    })

    it('maintains focus behavior on children', async () => {
      const user = userEvent.setup()

      render(
        <Tooltip content="Focus info">
          <input type="text" placeholder="Enter text" />
        </Tooltip>
      )

      const input = screen.getByPlaceholderText('Enter text')
      await user.click(input)

      expect(input).toHaveFocus()
    })
  })

  describe('Edge Cases', () => {
    it('handles very long tooltip text', () => {
      const longText = 'A'.repeat(500)
      const { container } = render(
        <Tooltip content={longText}>
          <span>Long tooltip</span>
        </Tooltip>
      )

      const wrapper = container.querySelector('div')
      expect(wrapper?.getAttribute('title')).toBe(longText)
    })

    it('handles special characters in tooltip', () => {
      const specialChars = '< > & " \' @ # $ % ^ *'
      const { container } = render(
        <Tooltip content={specialChars}>
          <span>Special</span>
        </Tooltip>
      )

      const wrapper = container.querySelector('div')
      expect(wrapper).toHaveAttribute('title', specialChars)
    })

    it('handles unicode characters in tooltip', () => {
      const unicodeText = '你好 世界 🌍 café résumé'
      const { container } = render(
        <Tooltip content={unicodeText}>
          <span>Unicode</span>
        </Tooltip>
      )

      const wrapper = container.querySelector('div')
      expect(wrapper).toHaveAttribute('title', unicodeText)
    })

    it('handles whitespace in tooltip text', () => {
      const whitespaceText = '  Multiple   spaces   here  '
      const { container } = render(
        <Tooltip content={whitespaceText}>
          <span>Whitespace</span>
        </Tooltip>
      )

      const wrapper = container.querySelector('div')
      expect(wrapper).toHaveAttribute('title', whitespaceText)
    })

    it('handles numeric content as string', () => {
      const { container } = render(
        <Tooltip content="123">
          <span>Number tooltip</span>
        </Tooltip>
      )

      const wrapper = container.querySelector('div')
      expect(wrapper).toHaveAttribute('title', '123')
    })

    it('handles null children gracefully', () => {
      const { container } = render(<Tooltip content="Tooltip">{null}</Tooltip>)

      const wrapper = container.querySelector('div')
      expect(wrapper).toBeInTheDocument()
    })

    it('handles undefined children gracefully', () => {
      const { container } = render(
        <Tooltip content="Tooltip">{undefined}</Tooltip>
      )

      const wrapper = container.querySelector('div')
      expect(wrapper).toBeInTheDocument()
    })

    it('handles false children gracefully', () => {
      const { container } = render(<Tooltip content="Tooltip">{false}</Tooltip>)

      const wrapper = container.querySelector('div')
      expect(wrapper).toBeInTheDocument()
    })

    it('handles conditional children', () => {
      const showChild = true
      render(
        <Tooltip content="Conditional">
          {showChild && <span>Visible</span>}
        </Tooltip>
      )

      expect(screen.getByText('Visible')).toBeInTheDocument()
    })
  })

  describe('Type Checking', () => {
    it('correctly identifies string content', () => {
      const { container } = render(
        <Tooltip content="String tooltip">
          <span>Target</span>
        </Tooltip>
      )

      const wrapper = container.querySelector('div')
      expect(wrapper).toHaveAttribute('title')
    })

    it('correctly identifies non-string content', () => {
      const numberContent = 123 as any // Testing edge case
      const { container } = render(
        <Tooltip content={numberContent}>
          <span>Target</span>
        </Tooltip>
      )

      const wrapper = container.querySelector('div')
      expect(wrapper).not.toHaveAttribute('title')
    })

    it('handles boolean content', () => {
      const boolContent = true as any // Testing edge case
      const { container } = render(
        <Tooltip content={boolContent}>
          <span>Target</span>
        </Tooltip>
      )

      const wrapper = container.querySelector('div')
      expect(wrapper).not.toHaveAttribute('title')
    })
  })

  describe('Future Enhancement Note', () => {
    it('documents limitation with complex content', () => {
      // This test documents that complex ReactNode content currently
      // does not display a tooltip, as noted in the component comments.
      // When enhanced with a proper tooltip library, this behavior will change.

      const complexContent = (
        <div>
          <strong>Enhanced</strong> tooltip
        </div>
      )
      const { container } = render(
        <Tooltip content={complexContent}>
          <button>Hover</button>
        </Tooltip>
      )

      const wrapper = container.querySelector('div')
      expect(wrapper).not.toHaveAttribute('title')

      // This is the current expected behavior.
      // Future enhancement should make complex tooltips visible.
    })
  })
})

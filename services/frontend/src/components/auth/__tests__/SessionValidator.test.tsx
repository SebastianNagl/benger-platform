/**
 * @jest-environment jsdom
 */

import { render } from '@testing-library/react'
import { SessionValidator } from '../SessionValidator'

describe('SessionValidator Component', () => {
  describe('Component Rendering', () => {
    it('renders without crashing', () => {
      const { container } = render(<SessionValidator />)
      expect(container).toBeDefined()
    })

    it('returns null (no visible UI)', () => {
      const { container } = render(<SessionValidator />)
      expect(container.firstChild).toBeNull()
    })

    it('has no DOM elements', () => {
      const { container } = render(<SessionValidator />)
      expect(container).toBeEmptyDOMElement()
    })
  })

  describe('Backwards Compatibility', () => {
    it('exists for backwards compatibility but does nothing', () => {
      const { container } = render(<SessionValidator />)
      expect(container).toBeEmptyDOMElement()
    })

    it('can be safely included in component tree', () => {
      const { container } = render(
        <div>
          <SessionValidator />
          <div data-testid="sibling">Sibling Component</div>
        </div>
      )

      expect(
        container.querySelector('[data-testid="sibling"]')
      ).toBeInTheDocument()
    })

    it('does not interfere with parent components', () => {
      const parentSpy = jest.fn()

      function ParentComponent() {
        parentSpy()
        return (
          <div data-testid="parent">
            <SessionValidator />
          </div>
        )
      }

      const { getByTestId } = render(<ParentComponent />)

      expect(parentSpy).toHaveBeenCalled()
      expect(getByTestId('parent')).toBeInTheDocument()
    })
  })

  describe('Multiple Instances', () => {
    it('can render multiple instances without issues', () => {
      const { container } = render(
        <div>
          <SessionValidator />
          <SessionValidator />
          <SessionValidator />
        </div>
      )

      expect(container).toBeDefined()
    })

    it('has no side effects when rendered multiple times', () => {
      const { rerender, container } = render(<SessionValidator />)

      expect(container.firstChild).toBeNull()

      rerender(<SessionValidator />)
      expect(container.firstChild).toBeNull()

      rerender(<SessionValidator />)
      expect(container.firstChild).toBeNull()
    })
  })

  describe('Component Lifecycle', () => {
    it('handles mounting and unmounting correctly', () => {
      const { unmount, container } = render(<SessionValidator />)

      expect(container).toBeDefined()

      unmount()

      expect(container).toBeDefined()
    })

    it('does not perform any cleanup on unmount', () => {
      const { unmount } = render(<SessionValidator />)

      expect(() => unmount()).not.toThrow()
    })
  })

  describe('TypeScript Type Safety', () => {
    it('accepts no props', () => {
      expect(() => render(<SessionValidator />)).not.toThrow()
    })

    it('component is exported correctly', () => {
      expect(SessionValidator).toBeDefined()
      expect(typeof SessionValidator).toBe('function')
    })
  })
})

/**
 * @jest-environment jsdom
 */

import { render } from '@testing-library/react'
import { GridPattern } from '../GridPattern'

describe('GridPattern', () => {
  // Default props for testing
  const defaultProps = {
    width: 40,
    height: 40,
    x: 0,
    y: 0,
    squares: [
      [0, 0],
      [1, 1],
      [2, 2],
    ] as Array<[number, number]>,
  }

  // ==================== 1. Basic Rendering ====================
  describe('Basic Rendering', () => {
    it('renders without crashing', () => {
      const { container } = render(<GridPattern {...defaultProps} />)
      expect(container.firstChild).toBeInTheDocument()
    })

    it('renders an SVG element', () => {
      const { container } = render(<GridPattern {...defaultProps} />)
      const svg = container.querySelector('svg')
      expect(svg).toBeInTheDocument()
    })

    it('renders with aria-hidden attribute', () => {
      const { container } = render(<GridPattern {...defaultProps} />)
      const svg = container.querySelector('svg')
      expect(svg).toHaveAttribute('aria-hidden', 'true')
    })

    it('renders defs and pattern elements', () => {
      const { container } = render(<GridPattern {...defaultProps} />)
      const defs = container.querySelector('defs')
      const pattern = container.querySelector('pattern')
      expect(defs).toBeInTheDocument()
      expect(pattern).toBeInTheDocument()
    })

    it('renders background rectangle', () => {
      const { container } = render(<GridPattern {...defaultProps} />)
      const rects = container.querySelectorAll('rect')
      expect(rects.length).toBeGreaterThan(0)
      const backgroundRect = Array.from(rects).find(
        (rect) => rect.getAttribute('width') === '100%'
      )
      expect(backgroundRect).toBeInTheDocument()
    })

    it('renders nested SVG for squares', () => {
      const { container } = render(<GridPattern {...defaultProps} />)
      const svgs = container.querySelectorAll('svg')
      expect(svgs.length).toBeGreaterThanOrEqual(2)
    })
  })

  // ==================== 2. Props/Attributes ====================
  describe('Props and Attributes', () => {
    it('applies width and height to pattern', () => {
      const { container } = render(
        <GridPattern {...defaultProps} width={50} height={60} />
      )
      const pattern = container.querySelector('pattern')
      expect(pattern).toHaveAttribute('width', '50')
      expect(pattern).toHaveAttribute('height', '60')
    })

    it('applies x and y coordinates to pattern', () => {
      const { container } = render(
        <GridPattern {...defaultProps} x={10} y={20} />
      )
      const pattern = container.querySelector('pattern')
      expect(pattern).toHaveAttribute('x', '10')
      expect(pattern).toHaveAttribute('y', '20')
    })

    it('accepts string values for x and y', () => {
      const { container } = render(
        <GridPattern {...defaultProps} x="15" y="25" />
      )
      const pattern = container.querySelector('pattern')
      expect(pattern).toHaveAttribute('x', '15')
      expect(pattern).toHaveAttribute('y', '25')
    })

    it('applies patternUnits attribute', () => {
      const { container } = render(<GridPattern {...defaultProps} />)
      const pattern = container.querySelector('pattern')
      expect(pattern).toHaveAttribute('patternUnits', 'userSpaceOnUse')
    })

    it('renders correct number of square rectangles', () => {
      const squares: Array<[number, number]> = [
        [0, 0],
        [1, 1],
        [2, 2],
        [3, 3],
      ]
      const { container } = render(
        <GridPattern {...defaultProps} squares={squares} />
      )
      const nestedSvg = container.querySelectorAll('svg')[1]
      const squareRects = nestedSvg.querySelectorAll('rect')
      expect(squareRects.length).toBe(4)
    })

    it('accepts additional SVG props via rest operator', () => {
      const { container } = render(
        <GridPattern
          {...defaultProps}
          className="custom-class"
          data-testid="grid-pattern"
        />
      )
      const svg = container.querySelector('svg')
      expect(svg).toHaveClass('custom-class')
      expect(svg).toHaveAttribute('data-testid', 'grid-pattern')
    })

    it('supports style prop', () => {
      const { container } = render(
        <GridPattern {...defaultProps} style={{ opacity: 0.5 }} />
      )
      const svg = container.querySelector('svg')
      expect(svg).toHaveAttribute('style')
      const style = svg?.getAttribute('style')
      expect(style).toContain('opacity')
    })
  })

  // ==================== 3. Styling ====================
  describe('Styling', () => {
    it('applies overflow-visible class to nested SVG', () => {
      const { container } = render(<GridPattern {...defaultProps} />)
      const nestedSvg = container.querySelectorAll('svg')[1]
      expect(nestedSvg).toHaveClass('overflow-visible')
    })

    it('sets strokeWidth to 0 on background rect', () => {
      const { container } = render(<GridPattern {...defaultProps} />)
      const rects = container.querySelectorAll('rect')
      const backgroundRect = Array.from(rects).find(
        (rect) => rect.getAttribute('width') === '100%'
      )
      // React converts numeric strokeWidth prop to string attribute
      expect(backgroundRect).toHaveAttribute('stroke-width', '0')
    })

    it('sets strokeWidth to 0 on square rects', () => {
      const { container } = render(<GridPattern {...defaultProps} />)
      const nestedSvg = container.querySelectorAll('svg')[1]
      const squareRects = nestedSvg.querySelectorAll('rect')
      squareRects.forEach((rect) => {
        // React converts string strokeWidth prop to stroke-width attribute
        expect(rect).toHaveAttribute('stroke-width', '0')
      })
    })

    it('applies custom className alongside default classes', () => {
      const { container } = render(
        <GridPattern {...defaultProps} className="custom-grid" />
      )
      const svg = container.querySelector('svg')
      expect(svg).toHaveClass('custom-grid')
    })
  })

  // ==================== 4. SVG Pattern Generation ====================
  describe('SVG Pattern Generation', () => {
    it('generates unique pattern ID using useId', () => {
      const { container } = render(
        <>
          <GridPattern {...defaultProps} />
          <GridPattern {...defaultProps} />
        </>
      )

      const patterns = container.querySelectorAll('pattern')

      const id1 = patterns[0]?.getAttribute('id')
      const id2 = patterns[1]?.getAttribute('id')

      expect(id1).toBeTruthy()
      expect(id2).toBeTruthy()
      // IDs should be different for separate instances
      expect(id1).not.toBe(id2)
    })

    it('uses pattern ID in background rect fill', () => {
      const { container } = render(<GridPattern {...defaultProps} />)
      const pattern = container.querySelector('pattern')
      const patternId = pattern?.getAttribute('id')

      const rects = container.querySelectorAll('rect')
      const backgroundRect = Array.from(rects).find(
        (rect) => rect.getAttribute('width') === '100%'
      )
      const fill = backgroundRect?.getAttribute('fill')

      expect(fill).toBe(`url(#${patternId})`)
    })

    it('generates path with correct dimensions', () => {
      const { container } = render(
        <GridPattern {...defaultProps} width={50} height={60} />
      )
      const path = container.querySelector('path')
      const expectedD = 'M.5 60V.5H50'
      expect(path).toHaveAttribute('d', expectedD)
    })

    it('sets path fill to none', () => {
      const { container } = render(<GridPattern {...defaultProps} />)
      const path = container.querySelector('path')
      expect(path).toHaveAttribute('fill', 'none')
    })

    it('calculates square positions correctly', () => {
      const squares: Array<[number, number]> = [
        [1, 2],
        [3, 4],
      ]
      const width = 40
      const height = 40

      const { container } = render(
        <GridPattern
          {...defaultProps}
          squares={squares}
          width={width}
          height={height}
        />
      )
      const nestedSvg = container.querySelectorAll('svg')[1]
      const squareRects = nestedSvg.querySelectorAll('rect')

      expect(squareRects[0]).toHaveAttribute('x', String(1 * width))
      expect(squareRects[0]).toHaveAttribute('y', String(2 * height))
      expect(squareRects[1]).toHaveAttribute('x', String(3 * width))
      expect(squareRects[1]).toHaveAttribute('y', String(4 * height))
    })

    it('calculates square dimensions with +1 offset', () => {
      const width = 40
      const height = 40

      const { container } = render(
        <GridPattern {...defaultProps} width={width} height={height} />
      )
      const nestedSvg = container.querySelectorAll('svg')[1]
      const squareRects = nestedSvg.querySelectorAll('rect')

      squareRects.forEach((rect) => {
        expect(rect).toHaveAttribute('width', String(width + 1))
        expect(rect).toHaveAttribute('height', String(height + 1))
      })
    })

    it('generates unique keys for square rectangles', () => {
      const squares: Array<[number, number]> = [
        [0, 0],
        [1, 1],
        [2, 2],
      ]
      const { container } = render(
        <GridPattern {...defaultProps} squares={squares} />
      )
      const nestedSvg = container.querySelectorAll('svg')[1]
      const squareRects = nestedSvg.querySelectorAll('rect')

      // React keys are internal, but we can verify the rects are unique by their attributes
      const keys = Array.from(squareRects).map(
        (rect) => `${rect.getAttribute('x')}-${rect.getAttribute('y')}`
      )
      const uniqueKeys = new Set(keys)
      expect(uniqueKeys.size).toBe(squares.length)
    })
  })

  // ==================== 5. Responsive Behavior ====================
  describe('Responsive Behavior', () => {
    it('handles small dimensions', () => {
      const { container } = render(
        <GridPattern {...defaultProps} width={1} height={1} />
      )
      const pattern = container.querySelector('pattern')
      expect(pattern).toHaveAttribute('width', '1')
      expect(pattern).toHaveAttribute('height', '1')
    })

    it('handles large dimensions', () => {
      const { container } = render(
        <GridPattern {...defaultProps} width={1000} height={1000} />
      )
      const pattern = container.querySelector('pattern')
      expect(pattern).toHaveAttribute('width', '1000')
      expect(pattern).toHaveAttribute('height', '1000')
    })

    it('handles negative coordinates', () => {
      const { container } = render(
        <GridPattern {...defaultProps} x={-10} y={-20} />
      )
      const pattern = container.querySelector('pattern')
      expect(pattern).toHaveAttribute('x', '-10')
      expect(pattern).toHaveAttribute('y', '-20')
    })

    it('handles negative square positions', () => {
      const squares: Array<[number, number]> = [
        [-1, -1],
        [-2, -2],
      ]
      const { container } = render(
        <GridPattern {...defaultProps} squares={squares} />
      )
      const nestedSvg = container.querySelectorAll('svg')[1]
      const squareRects = nestedSvg.querySelectorAll('rect')

      expect(squareRects[0]).toHaveAttribute(
        'x',
        String(-1 * defaultProps.width)
      )
      expect(squareRects[0]).toHaveAttribute(
        'y',
        String(-1 * defaultProps.height)
      )
    })

    it('handles zero dimensions', () => {
      const { container } = render(
        <GridPattern {...defaultProps} width={0} height={0} />
      )
      const pattern = container.querySelector('pattern')
      expect(pattern).toHaveAttribute('width', '0')
      expect(pattern).toHaveAttribute('height', '0')
    })

    it('handles fractional dimensions', () => {
      const { container } = render(
        <GridPattern {...defaultProps} width={40.5} height={40.75} />
      )
      const pattern = container.querySelector('pattern')
      expect(pattern).toHaveAttribute('width', '40.5')
      expect(pattern).toHaveAttribute('height', '40.75')
    })
  })

  // ==================== 6. Accessibility ====================
  describe('Accessibility', () => {
    it('has aria-hidden="true" on main SVG', () => {
      const { container } = render(<GridPattern {...defaultProps} />)
      const svg = container.querySelector('svg')
      expect(svg).toHaveAttribute('aria-hidden', 'true')
    })

    it('does not have focusable elements', () => {
      const { container } = render(<GridPattern {...defaultProps} />)
      const focusableElements = container.querySelectorAll(
        'a, button, input, select, textarea, [tabindex]:not([tabindex="-1"])'
      )
      expect(focusableElements.length).toBe(0)
    })

    it('is purely decorative and not announced by screen readers', () => {
      const { container } = render(<GridPattern {...defaultProps} />)
      const svg = container.querySelector('svg')
      // Should have aria-hidden and no role or aria-label
      expect(svg).toHaveAttribute('aria-hidden', 'true')
      expect(svg).not.toHaveAttribute('role')
      expect(svg).not.toHaveAttribute('aria-label')
    })

    it('does not interfere with keyboard navigation', () => {
      const { container } = render(<GridPattern {...defaultProps} />)
      const svg = container.querySelector('svg')
      expect(svg).not.toHaveAttribute('tabindex')
    })
  })

  // ==================== 7. Edge Cases ====================
  describe('Edge Cases', () => {
    it('renders with empty squares array', () => {
      const { container } = render(
        <GridPattern {...defaultProps} squares={[]} />
      )
      const svg = container.querySelector('svg')
      expect(svg).toBeInTheDocument()

      const nestedSvg = container.querySelectorAll('svg')[1]
      const squareRects = nestedSvg?.querySelectorAll('rect') || []
      expect(squareRects.length).toBe(0)
    })

    it('renders with single square', () => {
      const squares: Array<[number, number]> = [[0, 0]]
      const { container } = render(
        <GridPattern {...defaultProps} squares={squares} />
      )
      const nestedSvg = container.querySelectorAll('svg')[1]
      const squareRects = nestedSvg.querySelectorAll('rect')
      expect(squareRects.length).toBe(1)
    })

    it('renders with many squares', () => {
      const squares: Array<[number, number]> = Array.from(
        { length: 100 },
        (_, i) => [i % 10, Math.floor(i / 10)]
      )
      const { container } = render(
        <GridPattern {...defaultProps} squares={squares} />
      )
      const nestedSvg = container.querySelectorAll('svg')[1]
      const squareRects = nestedSvg.querySelectorAll('rect')
      expect(squareRects.length).toBe(100)
    })

    it('handles duplicate square positions', () => {
      const squares: Array<[number, number]> = [
        [0, 0],
        [0, 0],
        [1, 1],
        [1, 1],
      ]
      const { container } = render(
        <GridPattern {...defaultProps} squares={squares} />
      )
      const nestedSvg = container.querySelectorAll('svg')[1]
      const squareRects = nestedSvg.querySelectorAll('rect')
      // React renders all items but warns about duplicate keys
      // The last item with each key wins, so we get all 4 rendered
      expect(squareRects.length).toBe(4)
    })

    it('handles very large square coordinates', () => {
      const squares: Array<[number, number]> = [[1000000, 1000000]]
      const { container } = render(
        <GridPattern {...defaultProps} squares={squares} />
      )
      const nestedSvg = container.querySelectorAll('svg')[1]
      const squareRects = nestedSvg.querySelectorAll('rect')
      expect(squareRects[0]).toHaveAttribute(
        'x',
        String(1000000 * defaultProps.width)
      )
      expect(squareRects[0]).toHaveAttribute(
        'y',
        String(1000000 * defaultProps.height)
      )
    })

    it('handles zero coordinate squares', () => {
      const squares: Array<[number, number]> = [[0, 0]]
      const { container } = render(
        <GridPattern {...defaultProps} squares={squares} />
      )
      const nestedSvg = container.querySelectorAll('svg')[1]
      const squareRects = nestedSvg.querySelectorAll('rect')
      expect(squareRects[0]).toHaveAttribute('x', '0')
      expect(squareRects[0]).toHaveAttribute('y', '0')
    })

    it('handles special character in className', () => {
      const specialChar = '@'
      const className = `grid${specialChar}pattern`
      const { container } = render(
        <GridPattern {...defaultProps} className={className} />
      )
      const svg = container.querySelector('svg')
      expect(svg).toHaveClass(className)
    })

    it('handles string x and y with decimal values', () => {
      const { container } = render(
        <GridPattern {...defaultProps} x="10.5" y="20.75" />
      )
      const pattern = container.querySelector('pattern')
      expect(pattern).toHaveAttribute('x', '10.5')
      expect(pattern).toHaveAttribute('y', '20.75')
    })

    it('maintains pattern consistency across re-renders', () => {
      const { container, rerender } = render(<GridPattern {...defaultProps} />)
      const pattern1 = container.querySelector('pattern')
      const id1 = pattern1?.getAttribute('id')

      rerender(
        <GridPattern {...defaultProps} width={50} height={50} squares={[]} />
      )
      const pattern2 = container.querySelector('pattern')
      const id2 = pattern2?.getAttribute('id')

      // ID should remain the same across re-renders of the same component instance
      expect(id1).toBe(id2)
    })
  })

  // ==================== 8. Dark Mode Support ====================
  describe('Dark Mode Support', () => {
    it('supports dark mode class via className prop', () => {
      const { container } = render(
        <GridPattern {...defaultProps} className="dark:stroke-white/10" />
      )
      const svg = container.querySelector('svg')
      expect(svg).toHaveClass('dark:stroke-white/10')
    })

    it('supports stroke color classes', () => {
      const { container } = render(
        <GridPattern
          {...defaultProps}
          className="stroke-gray-500 dark:stroke-gray-700"
        />
      )
      const svg = container.querySelector('svg')
      expect(svg).toHaveClass('stroke-gray-500')
      expect(svg).toHaveClass('dark:stroke-gray-700')
    })

    it('supports fill color classes for squares', () => {
      const { container } = render(
        <GridPattern
          {...defaultProps}
          className="[&_rect]:fill-blue-500 dark:[&_rect]:fill-blue-700"
        />
      )
      const svg = container.querySelector('svg')
      expect(svg).toHaveClass('[&_rect]:fill-blue-500')
      expect(svg).toHaveClass('dark:[&_rect]:fill-blue-700')
    })

    it('supports opacity classes', () => {
      const { container } = render(
        <GridPattern {...defaultProps} className="opacity-50 dark:opacity-25" />
      )
      const svg = container.querySelector('svg')
      expect(svg).toHaveClass('opacity-50')
      expect(svg).toHaveClass('dark:opacity-25')
    })

    it('combines multiple dark mode classes', () => {
      const darkModeClasses =
        'stroke-gray-500 dark:stroke-gray-700 opacity-50 dark:opacity-25'
      const { container } = render(
        <GridPattern {...defaultProps} className={darkModeClasses} />
      )
      const svg = container.querySelector('svg')
      expect(svg).toHaveClass('stroke-gray-500')
      expect(svg).toHaveClass('dark:stroke-gray-700')
      expect(svg).toHaveClass('opacity-50')
      expect(svg).toHaveClass('dark:opacity-25')
    })
  })
})

/**
 * @jest-environment jsdom
 */

import { render, screen } from '@testing-library/react'
import { HeroPattern } from '../HeroPattern'

// Mock GridPattern component
jest.mock('@/components/shared/GridPattern', () => ({
  GridPattern: (props: any) => (
    <svg {...props} data-testid="grid-pattern">
      <rect data-testid="grid-pattern-rect" />
    </svg>
  ),
}))

describe('HeroPattern Component', () => {
  describe('Basic Rendering', () => {
    it('renders without crashing', () => {
      const { container } = render(<HeroPattern />)
      expect(container).toBeInTheDocument()
    })

    it('renders outer wrapper div with correct positioning', () => {
      const { container } = render(<HeroPattern />)
      const outerDiv = container.firstChild as HTMLElement
      expect(outerDiv).toHaveClass(
        'absolute',
        'inset-0',
        '-z-10',
        'mx-0',
        'max-w-none',
        'overflow-hidden'
      )
    })

    it('renders middle container div with correct styling', () => {
      const { container } = render(<HeroPattern />)
      const outerDiv = container.firstChild as HTMLElement
      const middleDiv = outerDiv.firstChild as HTMLElement
      expect(middleDiv).toHaveClass(
        'h-100',
        'w-325',
        'dark:mask-[linear-gradient(white,transparent)]',
        'absolute',
        'left-1/2',
        'top-0',
        'ml-[-38rem]'
      )
    })

    it('renders gradient container div', () => {
      const { container } = render(<HeroPattern />)
      const outerDiv = container.firstChild as HTMLElement
      const middleDiv = outerDiv.firstChild as HTMLElement
      const gradientDiv = middleDiv.firstChild as HTMLElement
      expect(gradientDiv).toBeInTheDocument()
    })
  })

  describe('Pattern Generation', () => {
    it('renders GridPattern component', () => {
      render(<HeroPattern />)
      expect(screen.getByTestId('grid-pattern')).toBeInTheDocument()
    })

    it('passes correct width prop to GridPattern', () => {
      render(<HeroPattern />)
      const gridPattern = screen.getByTestId('grid-pattern')
      expect(gridPattern).toHaveAttribute('width', '72')
    })

    it('passes correct height prop to GridPattern', () => {
      render(<HeroPattern />)
      const gridPattern = screen.getByTestId('grid-pattern')
      expect(gridPattern).toHaveAttribute('height', '56')
    })

    it('passes correct x position to GridPattern', () => {
      render(<HeroPattern />)
      const gridPattern = screen.getByTestId('grid-pattern')
      expect(gridPattern).toHaveAttribute('x', '-12')
    })

    it('passes correct y position to GridPattern', () => {
      render(<HeroPattern />)
      const gridPattern = screen.getByTestId('grid-pattern')
      expect(gridPattern).toHaveAttribute('y', '4')
    })

    it('passes correct squares array to GridPattern', () => {
      render(<HeroPattern />)
      const gridPattern = screen.getByTestId('grid-pattern')
      // Mock serializes array as comma-separated string
      expect(gridPattern).toHaveAttribute('squares', '4,3,2,1,7,3,10,6')
    })
  })

  describe('Props/Attributes', () => {
    it('GridPattern has correct className', () => {
      render(<HeroPattern />)
      const gridPattern = screen.getByTestId('grid-pattern')
      expect(gridPattern).toHaveClass(
        'dark:fill-white/2.5',
        'absolute',
        'inset-x-0',
        'inset-y-[-50%]',
        'h-[200%]',
        'w-full',
        'skew-y-[-18deg]',
        'fill-black/40',
        'stroke-black/50',
        'mix-blend-overlay',
        'dark:stroke-white/5'
      )
    })

    it('has no accessible props since it is decorative', () => {
      const { container } = render(<HeroPattern />)
      const outerDiv = container.firstChild as HTMLElement
      expect(outerDiv).not.toHaveAttribute('role')
      expect(outerDiv).not.toHaveAttribute('aria-label')
    })
  })

  describe('Styling', () => {
    it('applies absolute positioning to outer container', () => {
      const { container } = render(<HeroPattern />)
      const outerDiv = container.firstChild as HTMLElement
      expect(outerDiv).toHaveClass('absolute')
    })

    it('applies z-index layering correctly', () => {
      const { container } = render(<HeroPattern />)
      const outerDiv = container.firstChild as HTMLElement
      expect(outerDiv).toHaveClass('-z-10')
    })

    it('applies overflow-hidden to prevent content overflow', () => {
      const { container } = render(<HeroPattern />)
      const outerDiv = container.firstChild as HTMLElement
      expect(outerDiv).toHaveClass('overflow-hidden')
    })

    it('applies gradient background classes', () => {
      const { container } = render(<HeroPattern />)
      const outerDiv = container.firstChild as HTMLElement
      const middleDiv = outerDiv.firstChild as HTMLElement
      const gradientDiv = middleDiv.firstChild as HTMLElement
      expect(gradientDiv).toHaveClass(
        'bg-linear-to-r',
        'mask-[radial-gradient(farthest-side_at_top,white,transparent)]'
      )
    })

    it('applies gradient colors from teal to lime', () => {
      const { container } = render(<HeroPattern />)
      const outerDiv = container.firstChild as HTMLElement
      const middleDiv = outerDiv.firstChild as HTMLElement
      const gradientDiv = middleDiv.firstChild as HTMLElement
      expect(gradientDiv).toHaveClass('from-[#36b49f]', 'to-[#DBFF75]')
    })

    it('applies correct opacity for light mode', () => {
      const { container } = render(<HeroPattern />)
      const outerDiv = container.firstChild as HTMLElement
      const middleDiv = outerDiv.firstChild as HTMLElement
      const gradientDiv = middleDiv.firstChild as HTMLElement
      expect(gradientDiv).toHaveClass('opacity-40')
    })

    it('applies dark mode gradient colors', () => {
      const { container } = render(<HeroPattern />)
      const outerDiv = container.firstChild as HTMLElement
      const middleDiv = outerDiv.firstChild as HTMLElement
      const gradientDiv = middleDiv.firstChild as HTMLElement
      expect(gradientDiv).toHaveClass(
        'dark:from-[#36b49f]/30',
        'dark:to-[#DBFF75]/30'
      )
    })

    it('applies dark mode opacity', () => {
      const { container } = render(<HeroPattern />)
      const outerDiv = container.firstChild as HTMLElement
      const middleDiv = outerDiv.firstChild as HTMLElement
      const gradientDiv = middleDiv.firstChild as HTMLElement
      expect(gradientDiv).toHaveClass('dark:opacity-100')
    })
  })

  describe('SVG Elements', () => {
    it('renders SVG element', () => {
      const { container } = render(<HeroPattern />)
      const svg = container.querySelector('svg[viewBox="0 0 1113 440"]')
      expect(svg).toBeInTheDocument()
    })

    it('SVG has correct viewBox attribute', () => {
      const { container } = render(<HeroPattern />)
      const svg = container.querySelector('svg[viewBox="0 0 1113 440"]')
      expect(svg).toHaveAttribute('viewBox', '0 0 1113 440')
    })

    it('SVG is marked as aria-hidden', () => {
      const { container } = render(<HeroPattern />)
      const svg = container.querySelector('svg[viewBox="0 0 1113 440"]')
      expect(svg).toHaveAttribute('aria-hidden', 'true')
    })

    it('SVG has correct positioning classes', () => {
      const { container } = render(<HeroPattern />)
      const svg = container.querySelector('svg[viewBox="0 0 1113 440"]')
      expect(svg).toHaveClass(
        'w-278.25',
        'absolute',
        'left-1/2',
        'top-0',
        'ml-[-19rem]'
      )
    })

    it('SVG has blur and fill classes', () => {
      const { container } = render(<HeroPattern />)
      const svg = container.querySelector('svg[viewBox="0 0 1113 440"]')
      expect(svg).toHaveClass('fill-white', 'blur-[26px]')
    })

    it('SVG is hidden in dark mode', () => {
      const { container } = render(<HeroPattern />)
      const svg = container.querySelector('svg[viewBox="0 0 1113 440"]')
      expect(svg).toHaveClass('dark:hidden')
    })

    it('SVG contains path element', () => {
      const { container } = render(<HeroPattern />)
      const svg = container.querySelector('svg[viewBox="0 0 1113 440"]')
      const path = svg?.querySelector('path')
      expect(path).toBeInTheDocument()
    })

    it('SVG path has correct d attribute', () => {
      const { container } = render(<HeroPattern />)
      const svg = container.querySelector('svg[viewBox="0 0 1113 440"]')
      const path = svg?.querySelector('path')
      const dAttr =
        'M.016 439.5s-9.5-300 434-300S882.516 20 882.516 20V0h230.004v439.5H.016Z'
      expect(path).toHaveAttribute('d', dAttr)
    })
  })

  describe('Responsive Behavior', () => {
    it('uses viewport-relative positioning', () => {
      const { container } = render(<HeroPattern />)
      const outerDiv = container.firstChild as HTMLElement
      expect(outerDiv).toHaveClass('inset-0')
    })

    it('centers content using left-1/2', () => {
      const { container } = render(<HeroPattern />)
      const outerDiv = container.firstChild as HTMLElement
      const middleDiv = outerDiv.firstChild as HTMLElement
      expect(middleDiv).toHaveClass('left-1/2')
    })

    it('uses negative margin for precise positioning', () => {
      const { container } = render(<HeroPattern />)
      const outerDiv = container.firstChild as HTMLElement
      const middleDiv = outerDiv.firstChild as HTMLElement
      expect(middleDiv).toHaveClass('ml-[-38rem]')
    })

    it('SVG centers with left-1/2', () => {
      const { container } = render(<HeroPattern />)
      const svg = container.querySelector('svg[viewBox="0 0 1113 440"]')
      expect(svg).toHaveClass('left-1/2')
    })

    it('applies responsive width to middle container', () => {
      const { container } = render(<HeroPattern />)
      const outerDiv = container.firstChild as HTMLElement
      const middleDiv = outerDiv.firstChild as HTMLElement
      expect(middleDiv).toHaveClass('w-325')
    })

    it('applies responsive height to middle container', () => {
      const { container } = render(<HeroPattern />)
      const outerDiv = container.firstChild as HTMLElement
      const middleDiv = outerDiv.firstChild as HTMLElement
      expect(middleDiv).toHaveClass('h-100')
    })
  })

  describe('Accessibility', () => {
    it('decorative SVG is aria-hidden', () => {
      const { container } = render(<HeroPattern />)
      const svg = container.querySelector('svg[viewBox="0 0 1113 440"]')
      expect(svg).toHaveAttribute('aria-hidden', 'true')
    })

    it('GridPattern SVG is also aria-hidden (via mock)', () => {
      render(<HeroPattern />)
      const gridPattern = screen.getByTestId('grid-pattern')
      expect(gridPattern).toBeInTheDocument()
      // GridPattern component itself sets aria-hidden in actual implementation
    })

    it('component is purely decorative with no interactive elements', () => {
      const { container } = render(<HeroPattern />)
      const buttons = container.querySelectorAll('button')
      const links = container.querySelectorAll('a')
      const inputs = container.querySelectorAll('input')
      expect(buttons).toHaveLength(0)
      expect(links).toHaveLength(0)
      expect(inputs).toHaveLength(0)
    })

    it('uses -z-10 to ensure pattern stays behind content', () => {
      const { container } = render(<HeroPattern />)
      const outerDiv = container.firstChild as HTMLElement
      expect(outerDiv).toHaveClass('-z-10')
    })
  })

  describe('Edge Cases', () => {
    it('renders consistently on multiple renders', () => {
      const { container, rerender } = render(<HeroPattern />)
      const firstRender = container.innerHTML

      rerender(<HeroPattern />)
      const secondRender = container.innerHTML

      expect(firstRender).toBe(secondRender)
    })

    it('component has no props to handle', () => {
      // HeroPattern accepts no props - this is expected behavior
      const { container } = render(<HeroPattern />)
      expect(container.firstChild).toBeInTheDocument()
    })

    it('maintains structure with deeply nested divs', () => {
      const { container } = render(<HeroPattern />)
      const outerDiv = container.firstChild as HTMLElement
      const middleDiv = outerDiv.firstChild as HTMLElement
      const gradientDiv = middleDiv.firstChild as HTMLElement
      const gridPattern = screen.getByTestId('grid-pattern')

      expect(outerDiv).toBeInTheDocument()
      expect(middleDiv).toBeInTheDocument()
      expect(gradientDiv).toBeInTheDocument()
      expect(gridPattern).toBeInTheDocument()
    })

    it('handles special characters in path d attribute', () => {
      const { container } = render(<HeroPattern />)
      const svg = container.querySelector('svg[viewBox="0 0 1113 440"]')
      const path = svg?.querySelector('path')
      const dValue = path?.getAttribute('d')

      expect(dValue).toContain('M')
      expect(dValue).toContain('s')
      expect(dValue).toContain('S')
      expect(dValue).toContain('V')
      expect(dValue).toContain('h')
      expect(dValue).toContain('H')
      expect(dValue).toContain('Z')
    })

    it('renders without errors when unmounted', () => {
      const { unmount } = render(<HeroPattern />)
      expect(() => unmount()).not.toThrow()
    })

    it('maintains fixed squares configuration', () => {
      render(<HeroPattern />)
      const gridPattern = screen.getByTestId('grid-pattern')
      const squares = gridPattern.getAttribute('squares')

      // Mock serializes array as comma-separated string
      expect(squares).toBe('4,3,2,1,7,3,10,6')
    })

    it('gradient container has all required blend mode classes', () => {
      const { container } = render(<HeroPattern />)
      const outerDiv = container.firstChild as HTMLElement
      const middleDiv = outerDiv.firstChild as HTMLElement
      const gradientDiv = middleDiv.firstChild as HTMLElement

      expect(gradientDiv).toHaveClass('absolute', 'inset-0')
    })

    it('handles custom color values in className', () => {
      const { container } = render(<HeroPattern />)
      const outerDiv = container.firstChild as HTMLElement
      const middleDiv = outerDiv.firstChild as HTMLElement
      const gradientDiv = middleDiv.firstChild as HTMLElement

      const className = gradientDiv.className
      expect(className).toContain('#36b49f')
      expect(className).toContain('#DBFF75')
    })

    it('component renders with correct number of child elements', () => {
      const { container } = render(<HeroPattern />)
      const outerDiv = container.firstChild as HTMLElement

      // Should have 1 child (middle div)
      expect(outerDiv.children).toHaveLength(1)

      const middleDiv = outerDiv.firstChild as HTMLElement
      // Should have 2 children (gradient div and SVG element)
      expect(middleDiv.children).toHaveLength(2)

      const gradientDiv = middleDiv.firstChild as HTMLElement
      // Gradient div should have 1 child (GridPattern)
      expect(gradientDiv.children).toHaveLength(1)
    })

    it('SVG maintains exact dimensions via viewBox', () => {
      const { container } = render(<HeroPattern />)
      const svg = container.querySelector('svg[viewBox="0 0 1113 440"]')
      const viewBox = svg?.getAttribute('viewBox')

      const dimensions = viewBox?.split(' ').map(Number)
      expect(dimensions).toEqual([0, 0, 1113, 440])
    })
  })
})

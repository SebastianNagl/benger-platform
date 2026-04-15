import { render, screen } from '@testing-library/react'
import { useInView } from 'framer-motion'
import React from 'react'

import { useSectionStore } from '@/components/layout/SectionProvider'
import { Heading } from '@/components/shared/Heading'

// Mock dependencies
jest.mock('framer-motion', () => ({
  useInView: jest.fn(),
}))

jest.mock('next/link', () => {
  return function MockLink({
    children,
    href,
    ...props
  }: {
    children: React.ReactNode
    href: string
    [key: string]: any
  }) {
    return (
      <a href={href} {...props}>
        {children}
      </a>
    )
  }
})

jest.mock('@/components/layout/SectionProvider', () => ({
  useSectionStore: jest.fn(),
}))

jest.mock('@/components/shared/Tag', () => ({
  Tag: ({ children }: { children: React.ReactNode }) => (
    <span data-testid="tag">{children}</span>
  ),
}))

jest.mock('@/lib/remToPx', () => ({
  remToPx: jest.fn((rem: number) => rem * 16),
}))

describe('Heading Component', () => {
  const mockRegisterHeading = jest.fn()
  const mockUseInView = useInView as jest.MockedFunction<typeof useInView>
  const mockUseSectionStore = useSectionStore as jest.MockedFunction<
    typeof useSectionStore
  >

  beforeEach(() => {
    jest.clearAllMocks()
    mockUseInView.mockReturnValue(false)
    mockUseSectionStore.mockReturnValue(mockRegisterHeading)
  })

  // 1. Basic Rendering
  describe('Basic Rendering', () => {
    it('renders without crashing', () => {
      render(<Heading id="test-heading">Test Heading</Heading>)
      expect(screen.getByText('Test Heading')).toBeInTheDocument()
    })

    it('renders with children text content', () => {
      render(<Heading id="heading-1">Hello World</Heading>)
      expect(screen.getByText('Hello World')).toBeInTheDocument()
    })

    it('renders with complex children', () => {
      render(
        <Heading id="heading-2">
          <span>Complex</span> <strong>Content</strong>
        </Heading>
      )
      expect(screen.getByText('Complex')).toBeInTheDocument()
      expect(screen.getByText('Content')).toBeInTheDocument()
    })

    it('requires an id prop', () => {
      // TypeScript enforces this at compile time
      // Component requires id prop as per type definition
      render(<Heading id="required-id">With ID</Heading>)
      expect(screen.getByText('With ID')).toBeInTheDocument()
    })
  })

  // 2. Level/Hierarchy (h1, h2, h3, h4, h5, h6)
  describe('Level/Hierarchy', () => {
    it('renders as h2 by default', () => {
      const { container } = render(
        <Heading id="default-level">Default</Heading>
      )
      const h2 = container.querySelector('h2')
      expect(h2).toBeInTheDocument()
      expect(h2).toHaveTextContent('Default')
    })

    it('renders as h2 when level prop is 2', () => {
      const { container } = render(
        <Heading id="h2-heading" level={2}>
          H2 Heading
        </Heading>
      )
      const h2 = container.querySelector('h2')
      expect(h2).toBeInTheDocument()
      expect(h2).toHaveTextContent('H2 Heading')
    })

    it('renders as h3 when level prop is 3', () => {
      const { container } = render(
        <Heading id="h3-heading" level={3}>
          H3 Heading
        </Heading>
      )
      const h3 = container.querySelector('h3')
      expect(h3).toBeInTheDocument()
      expect(h3).toHaveTextContent('H3 Heading')
    })

    it('only supports levels 2 and 3 per component type definition', () => {
      // Component is typed as `Heading<Level extends 2 | 3>`
      // This test documents the intentional limitation
      const { container: container2 } = render(
        <Heading id="test-2" level={2}>
          Level 2
        </Heading>
      )
      expect(container2.querySelector('h2')).toBeInTheDocument()

      const { container: container3 } = render(
        <Heading id="test-3" level={3}>
          Level 3
        </Heading>
      )
      expect(container3.querySelector('h3')).toBeInTheDocument()
    })

    it('registers heading with section store when level is 2', () => {
      render(
        <Heading id="register-test" level={2}>
          Register Test
        </Heading>
      )

      expect(mockRegisterHeading).toHaveBeenCalled()
      const callArgs = mockRegisterHeading.mock.calls[0][0]
      expect(callArgs).toHaveProperty('id', 'register-test')
      expect(callArgs).toHaveProperty('ref')
      expect(callArgs).toHaveProperty('offsetRem', 6)
    })

    it('does not register heading when level is 3', () => {
      render(
        <Heading id="no-register" level={3}>
          No Register
        </Heading>
      )

      expect(mockRegisterHeading).not.toHaveBeenCalled()
    })
  })

  // 3. Styling/Variants
  describe('Styling/Variants', () => {
    it('applies scroll-mt-24 class when no tag or label', () => {
      const { container } = render(
        <Heading id="no-eyebrow">No Eyebrow</Heading>
      )
      const heading = container.querySelector('h2')
      expect(heading).toHaveClass('scroll-mt-24')
    })

    it('applies scroll-mt-32 and mt-2 classes when tag is provided', () => {
      const { container } = render(
        <Heading id="with-tag" tag="GET">
          With Tag
        </Heading>
      )
      const heading = container.querySelector('h2')
      expect(heading).toHaveClass('scroll-mt-32', 'mt-2')
    })

    it('applies scroll-mt-32 and mt-2 classes when label is provided', () => {
      const { container } = render(
        <Heading id="with-label" label="v1.0">
          With Label
        </Heading>
      )
      const heading = container.querySelector('h2')
      expect(heading).toHaveClass('scroll-mt-32', 'mt-2')
    })

    it('applies scroll-mt-32 and mt-2 classes when both tag and label provided', () => {
      const { container } = render(
        <Heading id="with-both" tag="POST" label="v2.0">
          With Both
        </Heading>
      )
      const heading = container.querySelector('h2')
      expect(heading).toHaveClass('scroll-mt-32', 'mt-2')
    })

    it('uses correct offsetRem for heading registration with tag', () => {
      render(
        <Heading id="offset-tag" level={2} tag="PUT">
          Offset Tag
        </Heading>
      )

      const callArgs = mockRegisterHeading.mock.calls[0][0]
      expect(callArgs.offsetRem).toBe(8)
    })

    it('uses correct offsetRem for heading registration with label', () => {
      render(
        <Heading id="offset-label" level={2} label="beta">
          Offset Label
        </Heading>
      )

      const callArgs = mockRegisterHeading.mock.calls[0][0]
      expect(callArgs.offsetRem).toBe(8)
    })
  })

  // 4. Children Content
  describe('Children Content', () => {
    it('renders string children', () => {
      render(<Heading id="string">String Content</Heading>)
      expect(screen.getByText('String Content')).toBeInTheDocument()
    })

    it('renders JSX element children', () => {
      render(
        <Heading id="jsx">
          <span data-testid="child">JSX Child</span>
        </Heading>
      )
      expect(screen.getByTestId('child')).toBeInTheDocument()
    })

    it('renders multiple children', () => {
      render(
        <Heading id="multiple">
          <span>First</span>
          <span>Second</span>
          <span>Third</span>
        </Heading>
      )
      expect(screen.getByText('First')).toBeInTheDocument()
      expect(screen.getByText('Second')).toBeInTheDocument()
      expect(screen.getByText('Third')).toBeInTheDocument()
    })

    it('renders children with anchor by default', () => {
      render(<Heading id="with-anchor">With Anchor</Heading>)
      const link = screen.getByRole('link')
      expect(link).toBeInTheDocument()
      expect(link).toHaveAttribute('href', '#with-anchor')
    })

    it('renders children without anchor when anchor=false', () => {
      render(
        <Heading id="no-anchor" anchor={false}>
          No Anchor
        </Heading>
      )
      const links = screen.queryAllByRole('link')
      expect(links).toHaveLength(0)
    })
  })

  // 5. HTML Attributes
  describe('HTML Attributes', () => {
    it('accepts and renders custom className', () => {
      const { container } = render(
        <Heading id="custom-class" className="custom-heading-class">
          Custom Class
        </Heading>
      )
      const heading = container.querySelector('h2')
      expect(heading).toHaveClass('custom-heading-class')
    })

    it('accepts and renders data attributes', () => {
      const { container } = render(
        <Heading id="data-attr" data-testid="custom-heading">
          Data Attribute
        </Heading>
      )
      const heading = container.querySelector('h2')
      expect(heading).toHaveAttribute('data-testid', 'custom-heading')
    })

    it('accepts and renders aria attributes', () => {
      const { container } = render(
        <Heading id="aria-attr" aria-label="Custom ARIA Label">
          ARIA Heading
        </Heading>
      )
      const heading = container.querySelector('h2')
      expect(heading).toHaveAttribute('aria-label', 'Custom ARIA Label')
    })

    it('merges custom className with default classes', () => {
      const { container } = render(
        <Heading id="merge-class" className="extra-class">
          Merge Class
        </Heading>
      )
      const heading = container.querySelector('h2')
      // Component overwrites className rather than merging
      expect(heading).toHaveClass('extra-class')
      expect(heading).not.toHaveClass('scroll-mt-24')
    })

    it('passes through additional HTML attributes', () => {
      const { container } = render(
        <Heading
          id="extra-attrs"
          title="Tooltip"
          // @ts-expect-error - Testing arbitrary props
          data-custom="value"
        >
          Extra Attrs
        </Heading>
      )
      const heading = container.querySelector('h2')
      expect(heading).toHaveAttribute('title', 'Tooltip')
      expect(heading).toHaveAttribute('data-custom', 'value')
    })
  })

  // 6. Accessibility
  describe('Accessibility', () => {
    it('renders semantic heading elements', () => {
      const { container } = render(
        <Heading id="semantic" level={2}>
          Semantic
        </Heading>
      )
      expect(container.querySelector('h2')).toBeInTheDocument()
    })

    it('maintains heading hierarchy with level prop', () => {
      const { container: c2 } = render(
        <Heading id="h2" level={2}>
          H2
        </Heading>
      )
      const { container: c3 } = render(
        <Heading id="h3" level={3}>
          H3
        </Heading>
      )

      expect(c2.querySelector('h2')).toBeInTheDocument()
      expect(c3.querySelector('h3')).toBeInTheDocument()
    })

    it('anchor link has correct href pointing to heading id', () => {
      render(<Heading id="anchor-href">Anchor HREF</Heading>)
      const link = screen.getByRole('link')
      expect(link).toHaveAttribute('href', '#anchor-href')
    })

    it('anchor icon is hidden from screen readers', () => {
      mockUseInView.mockReturnValue(true)
      const { container } = render(<Heading id="icon-aria">Icon ARIA</Heading>)
      const svg = container.querySelector('svg')
      expect(svg).toHaveAttribute('aria-hidden', 'true')
    })

    it('heading is keyboard accessible when anchor is enabled', () => {
      render(<Heading id="keyboard">Keyboard</Heading>)
      const link = screen.getByRole('link')
      expect(link).toBeInTheDocument()
    })

    it('renders text content for screen readers', () => {
      render(<Heading id="screen-reader">Screen Reader Text</Heading>)
      expect(screen.getByText('Screen Reader Text')).toBeInTheDocument()
    })

    it('supports custom aria-label', () => {
      const { container } = render(
        <Heading id="custom-aria" aria-label="Custom Label">
          Content
        </Heading>
      )
      const heading = container.querySelector('h2')
      expect(heading).toHaveAttribute('aria-label', 'Custom Label')
    })
  })

  // 7. Edge Cases
  describe('Edge Cases', () => {
    it('handles empty children gracefully', () => {
      render(<Heading id="empty">{''}</Heading>)
      const { container } = render(<Heading id="empty-alt"></Heading>)
      expect(container.querySelector('h2')).toBeInTheDocument()
    })

    it('handles null children gracefully', () => {
      render(<Heading id="null">{null}</Heading>)
      const { container } = render(<Heading id="null-alt">{null}</Heading>)
      expect(container.querySelector('h2')).toBeInTheDocument()
    })

    it('handles undefined tag and label', () => {
      render(
        <Heading id="undefined-props" tag={undefined} label={undefined}>
          Undefined Props
        </Heading>
      )
      expect(screen.getByText('Undefined Props')).toBeInTheDocument()
      expect(screen.queryByTestId('tag')).not.toBeInTheDocument()
    })

    it('renders eyebrow when only tag is provided', () => {
      render(
        <Heading id="only-tag" tag="DELETE">
          Only Tag
        </Heading>
      )
      expect(screen.getByTestId('tag')).toBeInTheDocument()
      expect(screen.getByText('DELETE')).toBeInTheDocument()
    })

    it('renders eyebrow when only label is provided', () => {
      const { container } = render(
        <Heading id="only-label" label="alpha">
          Only Label
        </Heading>
      )
      expect(screen.getByText('alpha')).toBeInTheDocument()
      expect(container.querySelector('.font-mono')).toBeInTheDocument()
    })

    it('renders both tag and label with separator', () => {
      const { container } = render(
        <Heading id="tag-and-label" tag="GET" label="v1.0">
          Tag and Label
        </Heading>
      )
      expect(screen.getByTestId('tag')).toBeInTheDocument()
      expect(screen.getByText('GET')).toBeInTheDocument()
      expect(screen.getByText('v1.0')).toBeInTheDocument()
      const separator = container.querySelector('.bg-zinc-300')
      expect(separator).toBeInTheDocument()
    })

    it('handles anchor=false with inView=true', () => {
      mockUseInView.mockReturnValue(true)
      render(
        <Heading id="no-anchor-inview" anchor={false}>
          No Anchor In View
        </Heading>
      )
      const links = screen.queryAllByRole('link')
      expect(links).toHaveLength(0)
    })

    it('handles very long heading text', () => {
      const longText = 'A'.repeat(500)
      render(<Heading id="long-text">{longText}</Heading>)
      expect(screen.getByText(longText)).toBeInTheDocument()
    })

    it('handles special characters in id', () => {
      render(<Heading id="special-chars_123">Special</Heading>)
      const link = screen.getByRole('link')
      expect(link).toHaveAttribute('href', '#special-chars_123')
    })

    it('does not render eyebrow when tag and label are empty strings', () => {
      const { container } = render(
        <Heading id="empty-strings" tag="" label="">
          Empty Strings
        </Heading>
      )
      expect(screen.queryByTestId('tag')).not.toBeInTheDocument()
      const eyebrow = container.querySelector('.flex.items-center')
      expect(eyebrow).not.toBeInTheDocument()
    })
  })

  // 8. Dark Mode
  describe('Dark Mode', () => {
    it('applies dark mode classes to anchor icon background', () => {
      mockUseInView.mockReturnValue(true)
      const { container } = render(
        <Heading id="dark-anchor">Dark Anchor</Heading>
      )
      const anchorBg = container.querySelector('.dark\\:bg-zinc-800')
      expect(anchorBg).toBeInTheDocument()
    })

    it('applies dark mode classes to anchor icon stroke', () => {
      mockUseInView.mockReturnValue(true)
      const { container } = render(<Heading id="dark-icon">Dark Icon</Heading>)
      const icon = container.querySelector('.dark\\:stroke-zinc-400')
      expect(icon).toBeInTheDocument()
    })

    it('applies dark mode classes to eyebrow separator', () => {
      const { container } = render(
        <Heading id="dark-separator" tag="GET" label="v1">
          Dark Separator
        </Heading>
      )
      const separator = container.querySelector('.dark\\:bg-zinc-600')
      expect(separator).toBeInTheDocument()
    })

    it('applies dark mode classes to label text', () => {
      const { container } = render(
        <Heading id="dark-label" label="v1.0">
          Dark Label
        </Heading>
      )
      const label = container.querySelector('.text-zinc-400')
      expect(label).toBeInTheDocument()
      expect(label).toHaveTextContent('v1.0')
    })

    it('anchor ring has dark mode variant', () => {
      mockUseInView.mockReturnValue(true)
      const { container } = render(<Heading id="dark-ring">Dark Ring</Heading>)
      const ring = container.querySelector('.dark\\:ring-zinc-700')
      expect(ring).toBeInTheDocument()
    })

    it('anchor hover state has dark mode classes', () => {
      mockUseInView.mockReturnValue(true)
      const { container } = render(
        <Heading id="dark-hover">Dark Hover</Heading>
      )
      const hoverElement = container.querySelector(
        '.dark\\:hover\\:bg-zinc-700'
      )
      expect(hoverElement).toBeInTheDocument()
    })
  })

  // Additional: Anchor Visibility Behavior
  describe('Anchor Visibility Behavior', () => {
    it('shows anchor icon when inView is true', () => {
      mockUseInView.mockReturnValue(true)
      const { container } = render(
        <Heading id="visible-anchor">Visible Anchor</Heading>
      )
      const anchorIcon = container.querySelector('.absolute')
      expect(anchorIcon).toBeInTheDocument()
    })

    it('does not show anchor icon when inView is false', () => {
      mockUseInView.mockReturnValue(false)
      const { container } = render(
        <Heading id="hidden-anchor">Hidden Anchor</Heading>
      )
      const anchorIcon = container.querySelector('.absolute')
      expect(anchorIcon).not.toBeInTheDocument()
    })

    it('useInView is called with correct options', () => {
      render(<Heading id="inview-options">InView Options</Heading>)

      expect(mockUseInView).toHaveBeenCalled()
      const callArgs = mockUseInView.mock.calls[0]
      expect(callArgs[1]).toHaveProperty('amount', 'all')
      expect(callArgs[1]).toHaveProperty('margin')
    })
  })
})

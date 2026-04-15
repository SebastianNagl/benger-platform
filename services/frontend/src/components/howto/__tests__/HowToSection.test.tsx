/**
 * Test suite for HowToSection component
 * Issue #582: Comprehensive How-To documentation section
 */

import { render, screen } from '@testing-library/react'
import { HowToSection } from '../HowToSection'

// Mock the SectionProvider store
const mockRegisterHeading = jest.fn()
const mockUnregisterHeading = jest.fn()
const mockGetHeadings = jest.fn(() => [])

jest.mock('@/components/layout/SectionProvider', () => ({
  useSectionStore: (selector: any) => {
    const store = {
      registerHeading: mockRegisterHeading,
      unregisterHeading: mockUnregisterHeading,
      getHeadings: mockGetHeadings,
    }
    return selector(store)
  },
}))

describe('HowToSection Component', () => {
  const defaultProps = {
    title: 'Test Section',
    children: <div data-testid="section-content">Test content</div>,
  }

  beforeEach(() => {
    mockRegisterHeading.mockClear()
    mockUnregisterHeading.mockClear()
    mockGetHeadings.mockClear()
  })

  it('renders correctly with default props', () => {
    render(<HowToSection {...defaultProps} />)

    const heading = screen.getByRole('heading', { name: /test section/i })
    expect(heading).toBeInTheDocument()
    expect(heading).toHaveTextContent('Test Section')
    expect(heading.tagName).toBe('H2')
  })

  it('renders with custom heading level', () => {
    render(<HowToSection {...defaultProps} level="h3" />)

    const heading = screen.getByRole('heading', { name: /test section/i })
    expect(heading).toBeInTheDocument()
    expect(heading.tagName).toBe('H3')
    expect(heading).toHaveTextContent('Test Section')
  })

  it('renders children content immediately', () => {
    render(<HowToSection {...defaultProps} />)

    const content = screen.getByTestId('section-content')
    expect(content).toBeInTheDocument()
    expect(content).toHaveTextContent('Test content')
  })

  it('applies correct id attribute', () => {
    render(<HowToSection {...defaultProps} id="test-section" />)

    const section = screen.getByRole('heading').closest('section')
    expect(section).toHaveAttribute('id', 'test-section')
  })

  it('applies scroll margin class for navigation', () => {
    render(<HowToSection {...defaultProps} id="test-section" />)

    const section = screen.getByRole('heading').closest('section')
    expect(section).toHaveClass('scroll-mt-24')
  })

  it('applies correct heading styles for h2', () => {
    render(<HowToSection {...defaultProps} />)

    const heading = screen.getByRole('heading')
    expect(heading).toHaveClass(
      'text-3xl',
      'font-bold',
      'tracking-tight',
      'text-zinc-900',
      'dark:text-white'
    )
  })

  it('applies correct heading styles for h3', () => {
    render(<HowToSection {...defaultProps} level="h3" />)

    const heading = screen.getByRole('heading')
    expect(heading).toHaveClass(
      'text-2xl',
      'font-semibold',
      'tracking-tight',
      'text-zinc-900',
      'dark:text-white'
    )
  })

  it('applies correct content wrapper styles', () => {
    render(<HowToSection {...defaultProps} id="test-section" />)

    const content = screen.getByTestId('section-content')
    const contentWrapper = content.parentElement
    expect(contentWrapper).toHaveClass(
      'mt-6',
      'text-base',
      'text-zinc-600',
      'dark:text-zinc-400'
    )
  })

  it('renders multiple sections without conflicts', () => {
    render(
      <div>
        <HowToSection title="Section 1" id="section-1">
          <div data-testid="content-1">Content 1</div>
        </HowToSection>
        <HowToSection title="Section 2" id="section-2">
          <div data-testid="content-2">Content 2</div>
        </HowToSection>
      </div>
    )

    expect(
      screen.getByRole('heading', { name: /section 1/i })
    ).toBeInTheDocument()
    expect(
      screen.getByRole('heading', { name: /section 2/i })
    ).toBeInTheDocument()

    // Both sections should render their content
    expect(screen.getByTestId('content-1')).toBeInTheDocument()
    expect(screen.getByTestId('content-2')).toBeInTheDocument()
  })
})

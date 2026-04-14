/**
 * Test suite for LoadingSpinner component
 * Issue #364: Comprehensive component testing for shared components
 */

import { render } from '@testing-library/react'
import { LoadingSpinner } from '../LoadingSpinner'

describe('LoadingSpinner Component', () => {
  it('renders correctly with default props', () => {
    const { container } = render(<LoadingSpinner />)

    const spinner = container.querySelector('.animate-spin')
    expect(spinner).toBeInTheDocument()
    expect(spinner).toHaveClass('h-8', 'w-8') // medium size by default
  })

  it('applies small size correctly', () => {
    const { container } = render(<LoadingSpinner size="small" />)

    const spinner = container.querySelector('.animate-spin')
    expect(spinner).toHaveClass('h-4', 'w-4')
  })

  it('applies medium size correctly', () => {
    const { container } = render(<LoadingSpinner size="medium" />)

    const spinner = container.querySelector('.animate-spin')
    expect(spinner).toHaveClass('h-8', 'w-8')
  })

  it('applies large size correctly', () => {
    const { container } = render(<LoadingSpinner size="large" />)

    const spinner = container.querySelector('.animate-spin')
    expect(spinner).toHaveClass('h-12', 'w-12')
  })

  it('applies custom className', () => {
    const { container } = render(<LoadingSpinner className="custom-spinner" />)

    const spinner = container.querySelector('.animate-spin')
    expect(spinner).toHaveClass('custom-spinner')
  })

  it('renders with animation by default', () => {
    const { container } = render(<LoadingSpinner />)

    const spinner = container.querySelector('.animate-spin')
    expect(spinner).toHaveClass('animate-spin')
  })

  it('renders with border styles', () => {
    const { container } = render(<LoadingSpinner />)

    const spinner = container.querySelector('.animate-spin')
    expect(spinner).toHaveClass(
      'border-2',
      'border-gray-300',
      'border-t-blue-600'
    )
  })

  it('renders as a div element', () => {
    const { container } = render(<LoadingSpinner />)

    const spinner = container.querySelector('.animate-spin')
    expect(spinner?.tagName).toBe('DIV')
  })

  it('combines multiple classNames correctly', () => {
    const { container } = render(
      <LoadingSpinner size="large" className="extra-class" />
    )

    const spinner = container.querySelector('.animate-spin')
    expect(spinner).toHaveClass('h-12', 'w-12', 'extra-class')
  })
})

// Import additional components from same file
import { TaskDataSkeleton, PageLoading } from '../LoadingSpinner'

describe('TaskDataSkeleton Component', () => {
  it('renders with default 5 rows', () => {
    const { container } = render(<TaskDataSkeleton />)
    // Header row + 5 data rows
    const rows = container.querySelectorAll('.grid.grid-cols-6')
    expect(rows).toHaveLength(6) // 1 header + 5 data rows
  })

  it('renders custom number of rows', () => {
    const { container } = render(<TaskDataSkeleton rows={3} />)
    const rows = container.querySelectorAll('.grid.grid-cols-6')
    expect(rows).toHaveLength(4) // 1 header + 3 data rows
  })

  it('renders with animate-pulse class', () => {
    const { container } = render(<TaskDataSkeleton />)
    const animatedElements = container.querySelectorAll('.animate-pulse')
    expect(animatedElements.length).toBeGreaterThan(0)
  })

  it('renders header skeleton with border-b', () => {
    const { container } = render(<TaskDataSkeleton />)
    const headerRow = container.querySelector('.grid.grid-cols-6.border-b')
    expect(headerRow).toBeInTheDocument()
  })

  it('renders with space-y-4 container', () => {
    const { container } = render(<TaskDataSkeleton />)
    const wrapper = container.querySelector('.space-y-4')
    expect(wrapper).toBeInTheDocument()
  })
})

describe('PageLoading Component', () => {
  it('renders with default "Loading..." message', () => {
    const { container } = render(<PageLoading />)
    expect(container.textContent).toContain('Loading...')
  })

  it('renders with custom message', () => {
    const { container } = render(<PageLoading message="Please wait..." />)
    expect(container.textContent).toContain('Please wait...')
  })

  it('renders a large LoadingSpinner', () => {
    const { container } = render(<PageLoading />)
    const spinner = container.querySelector('.h-12.w-12')
    expect(spinner).toBeInTheDocument()
  })

  it('renders with min-height constraint', () => {
    const { container } = render(<PageLoading />)
    const wrapper = container.querySelector('.min-h-\\[400px\\]')
    expect(wrapper).toBeInTheDocument()
  })

  it('centers content vertically and horizontally', () => {
    const { container } = render(<PageLoading />)
    const wrapper = container.firstChild as HTMLElement
    expect(wrapper).toHaveClass('flex', 'items-center', 'justify-center')
  })
})

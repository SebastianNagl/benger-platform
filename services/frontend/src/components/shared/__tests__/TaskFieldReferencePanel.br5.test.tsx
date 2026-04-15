/**
 * @jest-environment jsdom
 *
 * Branch coverage tests for TaskFieldReferencePanel - round 5.
 * Tests synchronous branches. Async state transitions (field loading) are
 * covered by TaskFieldReferencePanel.fn.test.tsx.
 */
import '@testing-library/jest-dom'
import { fireEvent, render, screen } from '@testing-library/react'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, fallback?: string) => fallback || key,
    locale: 'en',
  }),
}))

jest.mock('@/lib/api/projects', () => ({
  projectsAPI: {
    getTaskFields: jest.fn().mockReturnValue(new Promise(() => {})),
  },
}))

jest.mock('../LoadingSpinner', () => ({
  LoadingSpinner: ({ size }: any) => (
    <div data-testid="loading-spinner" data-size={size}>
      Loading...
    </div>
  ),
}))

import { TaskFieldReferencePanel } from '../TaskFieldReferencePanel'

describe('TaskFieldReferencePanel - br5 branch coverage', () => {
  const defaultProps = { projectId: 'proj-1' }

  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('renders collapsed by default with default title', () => {
    render(<TaskFieldReferencePanel {...defaultProps} />)
    expect(screen.getByText('Available Task Fields')).toBeInTheDocument()
    // Content should NOT be visible when collapsed
    expect(screen.queryByTestId('loading-spinner')).not.toBeInTheDocument()
  })

  it('expands on click and shows loading state', () => {
    render(<TaskFieldReferencePanel {...defaultProps} />)
    fireEvent.click(screen.getByRole('button'))
    // After expanding, shows loading (since mock never resolves)
    expect(screen.getByTestId('loading-spinner')).toBeInTheDocument()
  })

  it('renders with custom title', () => {
    render(
      <TaskFieldReferencePanel
        {...defaultProps}
        title="Custom Title"
      />
    )
    expect(screen.getByText('Custom Title')).toBeInTheDocument()
  })

  it('renders description when expanded', () => {
    render(
      <TaskFieldReferencePanel
        {...defaultProps}
        description="Custom description"
        defaultExpanded={true}
      />
    )
    expect(screen.getByText('Custom description')).toBeInTheDocument()
  })

  it('shows loading state when defaultExpanded=true', () => {
    render(<TaskFieldReferencePanel {...defaultProps} defaultExpanded={true} />)
    expect(screen.getByTestId('loading-spinner')).toBeInTheDocument()
    expect(screen.getByText('Loading fields...')).toBeInTheDocument()
  })

  it('does not fetch when projectId is empty', () => {
    const { projectsAPI } = require('@/lib/api/projects')
    render(<TaskFieldReferencePanel projectId="" defaultExpanded={true} />)
    expect(projectsAPI.getTaskFields).not.toHaveBeenCalled()
  })

  it('applies className prop', () => {
    const { container } = render(
      <TaskFieldReferencePanel {...defaultProps} className="my-custom-class" />
    )
    expect(container.querySelector('.my-custom-class')).toBeInTheDocument()
  })

  it('collapses when clicking header on expanded panel', () => {
    render(<TaskFieldReferencePanel {...defaultProps} defaultExpanded={true} />)
    // Loading should be visible initially
    expect(screen.getByTestId('loading-spinner')).toBeInTheDocument()

    // Click header to collapse
    const headerBtn = screen.getByText('Available Task Fields').closest('button')!
    fireEvent.click(headerBtn)

    // Loading spinner should be gone after collapse
    expect(screen.queryByTestId('loading-spinner')).not.toBeInTheDocument()
  })
})

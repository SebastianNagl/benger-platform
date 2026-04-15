import { render, screen } from '@testing-library/react'
import { TaskFieldReferencePanel } from '../TaskFieldReferencePanel'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, fallback?: string) => fallback || key,
    locale: 'en',
  }),
}))

jest.mock('@/lib/api/projects', () => ({
  projectsAPI: {
    getTaskFields: jest.fn().mockResolvedValue({ fields: [] }),
  },
}))

jest.mock('../LoadingSpinner', () => ({
  LoadingSpinner: ({ size }: any) => (
    <div data-testid="loading-spinner" data-size={size}>Spinner</div>
  ),
}))

describe('TaskFieldReferencePanel', () => {
  const defaultProps = { projectId: 'proj-1' }

  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('renders collapsed by default with title', () => {
    render(<TaskFieldReferencePanel {...defaultProps} />)
    expect(screen.getByText('Available Task Fields')).toBeInTheDocument()
  })

  it('renders custom title', () => {
    render(<TaskFieldReferencePanel {...defaultProps} title="Custom Title" />)
    expect(screen.getByText('Custom Title')).toBeInTheDocument()
  })

  it('does not fetch when projectId is empty', () => {
    const { projectsAPI } = require('@/lib/api/projects')
    render(<TaskFieldReferencePanel projectId="" />)
    expect(projectsAPI.getTaskFields).not.toHaveBeenCalled()
  })

  it('applies custom className', () => {
    const { container } = render(
      <TaskFieldReferencePanel {...defaultProps} className="my-class" />
    )
    expect(container.querySelector('.my-class')).toBeInTheDocument()
  })

  it('renders expand/collapse button', () => {
    const { container } = render(<TaskFieldReferencePanel {...defaultProps} />)
    const button = container.querySelector('button')
    expect(button).toBeInTheDocument()
  })

  it('shows chevron right when collapsed', () => {
    const { container } = render(<TaskFieldReferencePanel {...defaultProps} />)
    // When collapsed, should not have border-t content div
    const contentDiv = container.querySelector('.border-t.border-zinc-200')
    expect(contentDiv).not.toBeInTheDocument()
  })

  it('shows content when defaultExpanded', () => {
    render(<TaskFieldReferencePanel {...defaultProps} defaultExpanded />)
    // The expanded section with loading should be visible
    expect(screen.getByTestId('loading-spinner')).toBeInTheDocument()
  })

  it('renders information circle icon', () => {
    const { container } = render(<TaskFieldReferencePanel {...defaultProps} />)
    const svgIcon = container.querySelector('svg')
    expect(svgIcon).toBeInTheDocument()
  })

  it('calls getTaskFields with projectId', () => {
    const { projectsAPI } = require('@/lib/api/projects')
    render(<TaskFieldReferencePanel projectId="test-proj-123" />)
    expect(projectsAPI.getTaskFields).toHaveBeenCalledWith('test-proj-123')
  })

  it('renders with rounded-lg border styling', () => {
    const { container } = render(<TaskFieldReferencePanel {...defaultProps} />)
    const panel = container.firstChild as HTMLElement
    expect(panel).toHaveClass('rounded-lg', 'border')
  })
})

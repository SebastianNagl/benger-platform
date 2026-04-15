/**
 * @jest-environment jsdom
 */
import '@testing-library/jest-dom'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { PublicationToggle } from '../PublicationToggle'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string) => key,
    locale: 'en',
  }),
}))

jest.mock('@/components/shared/Button', () => ({
  Button: ({ children, onClick, disabled, variant, className, ...props }: any) => (
    <button
      onClick={onClick}
      disabled={disabled}
      data-variant={variant}
      className={className}
      {...props}
    >
      {children}
    </button>
  ),
}))

// Helper to mock fetch globally
const mockFetch = jest.fn()
beforeAll(() => {
  global.fetch = mockFetch
})
afterAll(() => {
  // @ts-ignore
  delete global.fetch
})

describe('PublicationToggle', () => {
  const defaultProps = {
    projectId: 'proj-1',
    isPublished: false,
    canPublish: true,
    canPublishReason: '',
  }

  beforeEach(() => {
    jest.clearAllMocks()
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ is_published: true }),
    })
  })

  it('renders the publication title', () => {
    render(<PublicationToggle {...defaultProps} />)

    expect(screen.getByText('project.report.publication.title')).toBeInTheDocument()
  })

  it('shows draft status badge when not published', () => {
    render(<PublicationToggle {...defaultProps} isPublished={false} />)

    expect(screen.getByText('project.report.publication.statusDraft')).toBeInTheDocument()
  })

  it('shows published status badge when published', () => {
    render(<PublicationToggle {...defaultProps} isPublished={true} />)

    expect(screen.getByText('project.report.publication.statusPublished')).toBeInTheDocument()
  })

  it('shows draft description when not published', () => {
    render(<PublicationToggle {...defaultProps} isPublished={false} />)

    expect(screen.getByText('project.report.publication.draft')).toBeInTheDocument()
  })

  it('shows published description when published', () => {
    render(<PublicationToggle {...defaultProps} isPublished={true} />)

    expect(screen.getByText('project.report.publication.published')).toBeInTheDocument()
  })

  it('shows publish button when not published', () => {
    render(<PublicationToggle {...defaultProps} isPublished={false} />)

    expect(screen.getByText('project.report.publication.publish')).toBeInTheDocument()
  })

  it('shows unpublish button when published', () => {
    render(<PublicationToggle {...defaultProps} isPublished={true} />)

    expect(screen.getByText('project.report.publication.unpublish')).toBeInTheDocument()
  })

  it('disables publish button when canPublish is false and not published', () => {
    render(
      <PublicationToggle
        {...defaultProps}
        canPublish={false}
        canPublishReason="Report not found"
      />
    )

    const buttons = screen.getAllByText('project.report.publication.publish')
    const mainButton = buttons[0].closest('button')
    expect(mainButton).toBeDisabled()
  })

  it('shows the translated reason when canPublish is false', () => {
    render(
      <PublicationToggle
        {...defaultProps}
        canPublish={false}
        canPublishReason="Report not found"
      />
    )

    expect(screen.getByText('project.report.reasons.reportNotFound')).toBeInTheDocument()
  })

  it('shows raw reason when no translation mapping exists', () => {
    render(
      <PublicationToggle
        {...defaultProps}
        canPublish={false}
        canPublishReason="Some unknown reason"
      />
    )

    expect(screen.getByText('Some unknown reason')).toBeInTheDocument()
  })

  it('does not show reason when canPublish is true', () => {
    render(<PublicationToggle {...defaultProps} canPublish={true} />)

    expect(screen.queryByText('project.report.reasons.reportNotFound')).not.toBeInTheDocument()
  })

  it('does not show reason when already published', () => {
    render(
      <PublicationToggle
        {...defaultProps}
        isPublished={true}
        canPublish={false}
        canPublishReason="Report not found"
      />
    )

    expect(screen.queryByText('project.report.reasons.reportNotFound')).not.toBeInTheDocument()
  })

  it('shows confirmation dialog when publish button is clicked', () => {
    render(<PublicationToggle {...defaultProps} />)

    // Click the main publish button
    const publishButtons = screen.getAllByText('project.report.publication.publish')
    fireEvent.click(publishButtons[0])

    // Confirmation dialog should appear
    expect(screen.getByText('project.report.publication.confirmPublishTitle')).toBeInTheDocument()
    expect(screen.getByText('project.report.publication.confirmPublishMessage')).toBeInTheDocument()
  })

  it('shows unpublish confirmation dialog when unpublish button is clicked', () => {
    render(<PublicationToggle {...defaultProps} isPublished={true} />)

    const unpublishButtons = screen.getAllByText('project.report.publication.unpublish')
    fireEvent.click(unpublishButtons[0])

    expect(screen.getByText('project.report.publication.confirmUnpublishTitle')).toBeInTheDocument()
    expect(screen.getByText('project.report.publication.confirmUnpublishMessage')).toBeInTheDocument()
  })

  it('hides confirmation dialog when cancel is clicked', () => {
    render(<PublicationToggle {...defaultProps} />)

    // Open dialog
    const publishButtons = screen.getAllByText('project.report.publication.publish')
    fireEvent.click(publishButtons[0])

    expect(screen.getByText('project.report.publication.confirmPublishTitle')).toBeInTheDocument()

    // Click cancel
    fireEvent.click(screen.getByText('project.report.publication.cancel'))

    expect(screen.queryByText('project.report.publication.confirmPublishTitle')).not.toBeInTheDocument()
  })

  it('calls fetch with correct endpoint when publishing', async () => {
    render(<PublicationToggle {...defaultProps} />)

    // Open dialog
    const publishButtons = screen.getAllByText('project.report.publication.publish')
    fireEvent.click(publishButtons[0])

    // Confirm
    const confirmButtons = screen.getAllByText('project.report.publication.publish')
    // The confirm button is the last publish button (in the dialog)
    fireEvent.click(confirmButtons[confirmButtons.length - 1])

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        '/api/projects/proj-1/report/publish',
        { method: 'PUT', credentials: 'include' }
      )
    })
  })

  it('calls fetch with unpublish endpoint when unpublishing', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ is_published: false }),
    })

    render(<PublicationToggle {...defaultProps} isPublished={true} />)

    // Open dialog
    const unpublishButtons = screen.getAllByText('project.report.publication.unpublish')
    fireEvent.click(unpublishButtons[0])

    // Confirm
    const confirmButtons = screen.getAllByText('project.report.publication.unpublish')
    fireEvent.click(confirmButtons[confirmButtons.length - 1])

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        '/api/projects/proj-1/report/unpublish',
        { method: 'PUT', credentials: 'include' }
      )
    })
  })

  it('calls onToggle callback with published state after successful toggle', async () => {
    const onToggle = jest.fn()
    render(<PublicationToggle {...defaultProps} onToggle={onToggle} />)

    // Open and confirm
    const publishButtons = screen.getAllByText('project.report.publication.publish')
    fireEvent.click(publishButtons[0])
    const confirmButtons = screen.getAllByText('project.report.publication.publish')
    fireEvent.click(confirmButtons[confirmButtons.length - 1])

    await waitFor(() => {
      expect(onToggle).toHaveBeenCalledWith(true)
    })
  })

  it('shows error message when fetch fails', async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      json: () => Promise.resolve({ detail: 'Unauthorized' }),
    })

    render(<PublicationToggle {...defaultProps} />)

    // Open and confirm
    const publishButtons = screen.getAllByText('project.report.publication.publish')
    fireEvent.click(publishButtons[0])
    const confirmButtons = screen.getAllByText('project.report.publication.publish')
    fireEvent.click(confirmButtons[confirmButtons.length - 1])

    await waitFor(() => {
      expect(screen.getByText('Unauthorized')).toBeInTheDocument()
    })
  })

  it('shows processing text on button while loading', async () => {
    // Make fetch hang
    mockFetch.mockReturnValue(new Promise(() => {}))

    render(<PublicationToggle {...defaultProps} />)

    // Open and confirm
    const publishButtons = screen.getAllByText('project.report.publication.publish')
    fireEvent.click(publishButtons[0])
    const confirmButtons = screen.getAllByText('project.report.publication.publish')
    fireEvent.click(confirmButtons[confirmButtons.length - 1])

    await waitFor(() => {
      expect(screen.getByText('project.report.publication.processing')).toBeInTheDocument()
    })
  })

  it('maps all known reason strings to translation keys', () => {
    const reasons = [
      'Report not found',
      'Project must have tasks',
      'Project must have LLM generations',
      'Project must have completed evaluations',
      'Report not created yet',
    ]

    for (const reason of reasons) {
      const { unmount } = render(
        <PublicationToggle
          {...defaultProps}
          canPublish={false}
          canPublishReason={reason}
        />
      )

      // Should show a translation key, not the raw reason
      expect(screen.queryByText(reason)).not.toBeInTheDocument()
      unmount()
    }
  })
})

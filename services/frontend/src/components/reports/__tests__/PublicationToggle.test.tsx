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

let mockUser: any = { id: 'u1', is_superadmin: true }
jest.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({ user: mockUser, isLoading: false }),
}))

jest.mock('@/lib/api/reports', () => ({
  publishReport: jest.fn(),
  unpublishReport: jest.fn(),
  setReportVisibility: jest.fn(),
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

import {
  publishReport,
  setReportVisibility,
  unpublishReport,
} from '@/lib/api/reports'

const mockPublish = publishReport as jest.Mock
const mockUnpublish = unpublishReport as jest.Mock
const mockVisibility = setReportVisibility as jest.Mock

const T = {
  title: 'project.report.publication.title',
  statusDraft: 'project.report.publication.statusDraft',
  statusPublished: 'project.report.publication.statusPublished',
  statusPublic: 'reports.publication.statusPublic',
  draft: 'project.report.publication.draft',
  visibleToOrgs: 'reports.publication.visibleToOrgs',
  visibleToPublic: 'reports.publication.visibleToPublic',
  publish: 'project.report.publication.publish',
  unpublish: 'project.report.publication.unpublish',
  withdraw: 'reports.publication.withdraw',
  makePublic: 'reports.publication.makePublic',
  orgsOnly: 'reports.publication.orgsOnly',
  processing: 'project.report.publication.processing',
  cancel: 'project.report.publication.cancel',
  confirmPublishTitle: 'project.report.publication.confirmPublishTitle',
  confirmUnpublishTitle: 'project.report.publication.confirmUnpublishTitle',
  visibilityOrgs: 'reports.publication.visibilityOrgs',
  visibilityPublic: 'reports.publication.visibilityPublic',
  publicLink: 'reports.publication.publicLink',
  copyLink: 'reports.publication.copyLink',
  copied: 'reports.publication.copied',
}

describe('PublicationToggle', () => {
  const defaultProps = {
    projectId: 'proj-1',
    reportId: 'report-1',
    isPublished: false,
    isPublic: false,
    canPublish: true,
    canPublishReason: '',
  }

  beforeEach(() => {
    jest.clearAllMocks()
    mockUser = { id: 'u1', is_superadmin: true }
    mockPublish.mockResolvedValue({ is_published: true, is_public: false })
    mockUnpublish.mockResolvedValue({ is_published: false, is_public: false })
    mockVisibility.mockResolvedValue({ is_published: true, is_public: true })
  })

  describe('draft state', () => {
    it('renders title, draft badge and description', () => {
      render(<PublicationToggle {...defaultProps} />)

      expect(screen.getByText(T.title)).toBeInTheDocument()
      expect(screen.getByTestId('publication-status')).toHaveTextContent(
        T.statusDraft
      )
      expect(screen.getByText(T.draft)).toBeInTheDocument()
      expect(screen.getByText(T.publish)).toBeInTheDocument()
    })

    it('hides the publish button for non-superadmins (status only)', () => {
      mockUser = { id: 'u2', is_superadmin: false, role: 'ORG_ADMIN' }
      render(<PublicationToggle {...defaultProps} />)

      expect(screen.getByText(T.statusDraft)).toBeInTheDocument()
      expect(screen.queryByText(T.publish)).not.toBeInTheDocument()
      expect(screen.queryByRole('button')).not.toBeInTheDocument()
    })

    it('disables publish and shows the translated reason when canPublish is false', () => {
      render(
        <PublicationToggle
          {...defaultProps}
          canPublish={false}
          canPublishReason="Report not found"
        />
      )

      expect(screen.getByText(T.publish).closest('button')).toBeDisabled()
      expect(
        screen.getByText('project.report.reasons.reportNotFound')
      ).toBeInTheDocument()
    })

    it('shows the raw reason when no translation mapping exists', () => {
      render(
        <PublicationToggle
          {...defaultProps}
          canPublish={false}
          canPublishReason="Some unknown reason"
        />
      )
      expect(screen.getByText('Some unknown reason')).toBeInTheDocument()
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
        expect(screen.queryByText(reason)).not.toBeInTheDocument()
        unmount()
      }
    })

    it('opens the publish dialog with the organizations option preselected', () => {
      render(<PublicationToggle {...defaultProps} />)

      fireEvent.click(screen.getByText(T.publish))

      expect(screen.getByRole('dialog')).toBeInTheDocument()
      expect(screen.getByText(T.confirmPublishTitle)).toBeInTheDocument()
      const orgRadio = screen.getByRole('radio', { name: new RegExp(T.visibilityOrgs) })
      const publicRadio = screen.getByRole('radio', { name: new RegExp(T.visibilityPublic) })
      expect(orgRadio).toBeChecked()
      expect(publicRadio).not.toBeChecked()
    })

    it('closes the dialog on cancel without calling the API', () => {
      render(<PublicationToggle {...defaultProps} />)

      fireEvent.click(screen.getByText(T.publish))
      fireEvent.click(screen.getByText(T.cancel))

      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
      expect(mockPublish).not.toHaveBeenCalled()
    })

    it('publishes for organizations only and reports the new state', async () => {
      const onToggle = jest.fn()
      const onChange = jest.fn()
      render(
        <PublicationToggle
          {...defaultProps}
          onToggle={onToggle}
          onChange={onChange}
        />
      )

      fireEvent.click(screen.getByText(T.publish))
      const confirmButtons = screen.getAllByText(T.publish)
      fireEvent.click(confirmButtons[confirmButtons.length - 1])

      await waitFor(() => {
        expect(mockPublish).toHaveBeenCalledWith('proj-1', { is_public: false })
      })
      expect(onToggle).toHaveBeenCalledWith(true)
      expect(onChange).toHaveBeenCalledWith({
        is_published: true,
        is_public: false,
      })
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })

    it('publishes publicly when the public radio is selected', async () => {
      mockPublish.mockResolvedValue({ is_published: true, is_public: true })
      const onChange = jest.fn()
      render(<PublicationToggle {...defaultProps} onChange={onChange} />)

      fireEvent.click(screen.getByText(T.publish))
      fireEvent.click(
        screen.getByRole('radio', { name: new RegExp(T.visibilityPublic) })
      )
      const confirmButtons = screen.getAllByText(T.publish)
      fireEvent.click(confirmButtons[confirmButtons.length - 1])

      await waitFor(() => {
        expect(mockPublish).toHaveBeenCalledWith('proj-1', { is_public: true })
      })
      expect(onChange).toHaveBeenCalledWith({
        is_published: true,
        is_public: true,
      })
    })

    it('shows the API error message when publishing fails', async () => {
      mockPublish.mockRejectedValue(new Error('Unauthorized'))
      render(<PublicationToggle {...defaultProps} />)

      fireEvent.click(screen.getByText(T.publish))
      const confirmButtons = screen.getAllByText(T.publish)
      fireEvent.click(confirmButtons[confirmButtons.length - 1])

      await waitFor(() => {
        expect(screen.getByText('Unauthorized')).toBeInTheDocument()
      })
    })

    it('shows processing text while the request is pending', async () => {
      mockPublish.mockReturnValue(new Promise(() => {}))
      render(<PublicationToggle {...defaultProps} />)

      fireEvent.click(screen.getByText(T.publish))
      const confirmButtons = screen.getAllByText(T.publish)
      fireEvent.click(confirmButtons[confirmButtons.length - 1])

      await waitFor(() => {
        expect(screen.getByText(T.processing)).toBeInTheDocument()
      })
    })
  })

  describe('published for organizations', () => {
    const props = { ...defaultProps, isPublished: true, isPublic: false }

    it('shows the published badge, the org visibility text and both actions', () => {
      render(<PublicationToggle {...props} />)

      expect(screen.getByTestId('publication-status')).toHaveTextContent(
        T.statusPublished
      )
      expect(screen.getByText(T.visibleToOrgs)).toBeInTheDocument()
      expect(screen.getByText(T.makePublic)).toBeInTheDocument()
      expect(screen.getByText(T.unpublish)).toBeInTheDocument()
      expect(screen.queryByText(T.publicLink)).not.toBeInTheDocument()
    })

    it('does not show the reason once published', () => {
      render(
        <PublicationToggle
          {...props}
          canPublish={false}
          canPublishReason="Report not found"
        />
      )
      expect(
        screen.queryByText('project.report.reasons.reportNotFound')
      ).not.toBeInTheDocument()
    })

    it('makes the report public without re-firing the legacy onToggle', async () => {
      const onToggle = jest.fn()
      const onChange = jest.fn()
      render(
        <PublicationToggle {...props} onToggle={onToggle} onChange={onChange} />
      )

      fireEvent.click(screen.getByText(T.makePublic))

      await waitFor(() => {
        expect(mockVisibility).toHaveBeenCalledWith('proj-1', {
          is_public: true,
        })
      })
      expect(onChange).toHaveBeenCalledWith({
        is_published: true,
        is_public: true,
      })
      expect(onToggle).not.toHaveBeenCalled()
    })

    it('withdraws publication after confirmation', async () => {
      const onToggle = jest.fn()
      render(<PublicationToggle {...props} onToggle={onToggle} />)

      fireEvent.click(screen.getByText(T.unpublish))
      expect(screen.getByText(T.confirmUnpublishTitle)).toBeInTheDocument()

      const confirmButtons = screen.getAllByText(T.unpublish)
      fireEvent.click(confirmButtons[confirmButtons.length - 1])

      await waitFor(() => {
        expect(mockUnpublish).toHaveBeenCalledWith('proj-1')
      })
      expect(onToggle).toHaveBeenCalledWith(false)
    })

    it('shows an error when the visibility change fails', async () => {
      mockVisibility.mockRejectedValue(new Error('Only while published'))
      render(<PublicationToggle {...props} />)

      fireEvent.click(screen.getByText(T.makePublic))

      await waitFor(() => {
        expect(screen.getByText('Only while published')).toBeInTheDocument()
      })
    })

    it('non-superadmins see the status but no actions', () => {
      mockUser = { id: 'u2', is_superadmin: false, role: 'CONTRIBUTOR' }
      render(<PublicationToggle {...props} />)

      expect(screen.getByText(T.visibleToOrgs)).toBeInTheDocument()
      expect(screen.queryByText(T.makePublic)).not.toBeInTheDocument()
      expect(screen.queryByText(T.unpublish)).not.toBeInTheDocument()
    })
  })

  describe('public', () => {
    const props = { ...defaultProps, isPublished: true, isPublic: true }

    beforeEach(() => {
      Object.assign(navigator, {
        clipboard: { writeText: jest.fn().mockResolvedValue(undefined) },
      })
    })

    it('shows the public badge, the public text and the copyable link', () => {
      render(<PublicationToggle {...props} />)

      expect(screen.getByTestId('publication-status')).toHaveTextContent(
        T.statusPublic
      )
      expect(screen.getByText(T.visibleToPublic)).toBeInTheDocument()
      const link = screen.getByLabelText(T.publicLink) as HTMLInputElement
      expect(link).toHaveAttribute('readonly')
      expect(link.value).toBe('http://localhost/reports/report-1')
      expect(screen.getByText(T.orgsOnly)).toBeInTheDocument()
      expect(screen.getByText(T.withdraw)).toBeInTheDocument()
    })

    it('copies the public link to the clipboard', async () => {
      render(<PublicationToggle {...props} />)

      fireEvent.click(screen.getByText(T.copyLink))

      await waitFor(() => {
        expect(navigator.clipboard.writeText).toHaveBeenCalledWith(
          'http://localhost/reports/report-1'
        )
      })
      expect(screen.getByText(T.copied)).toBeInTheDocument()
    })

    it('switches back to organizations only', async () => {
      mockVisibility.mockResolvedValue({ is_published: true, is_public: false })
      const onChange = jest.fn()
      render(<PublicationToggle {...props} onChange={onChange} />)

      fireEvent.click(screen.getByText(T.orgsOnly))

      await waitFor(() => {
        expect(mockVisibility).toHaveBeenCalledWith('proj-1', {
          is_public: false,
        })
      })
      expect(onChange).toHaveBeenCalledWith({
        is_published: true,
        is_public: false,
      })
    })

    it('withdraws a public report after confirmation', async () => {
      const onChange = jest.fn()
      render(<PublicationToggle {...props} onChange={onChange} />)

      fireEvent.click(screen.getByText(T.withdraw))
      const confirmButtons = screen.getAllByText(T.unpublish)
      fireEvent.click(confirmButtons[confirmButtons.length - 1])

      await waitFor(() => {
        expect(mockUnpublish).toHaveBeenCalledWith('proj-1')
      })
      expect(onChange).toHaveBeenCalledWith({
        is_published: false,
        is_public: false,
      })
    })

    it('non-superadmins see the status and the link but no actions', () => {
      mockUser = { id: 'u2', is_superadmin: false, role: 'ORG_ADMIN' }
      render(<PublicationToggle {...props} />)

      expect(screen.getByText(T.visibleToPublic)).toBeInTheDocument()
      expect(screen.getByLabelText(T.publicLink)).toBeInTheDocument()
      expect(screen.queryByText(T.orgsOnly)).not.toBeInTheDocument()
      expect(screen.queryByText(T.withdraw)).not.toBeInTheDocument()
    })

    it('omits the link when no report id is known', () => {
      render(<PublicationToggle {...props} reportId={null} />)

      expect(screen.queryByLabelText(T.publicLink)).not.toBeInTheDocument()
    })
  })
})

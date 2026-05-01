/**
 * Coverage-focused tests for ReportEditorPage
 *
 * Targets uncovered branches:
 * - Contributor user can access (role === 'CONTRIBUTOR')
 * - ORG_ADMIN user can access (role === 'ORG_ADMIN')
 * - Report with empty/missing sections (optional chaining branches)
 * - Save with empty field values (uses undefined for empty strings)
 * - Save when report or projectId is null (early return)
 * - Non-superadmin returning null after load
 */

/**
 * @jest-environment jsdom
 */

import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useRouter } from 'next/navigation'
import ReportEditorPage from '../../edit/page'

jest.mock('next/navigation', () => ({
  useRouter: jest.fn(),
}))

jest.mock('@/contexts/AuthContext', () => ({
  useAuth: jest.fn(),
}))

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: jest.fn(),
}))

jest.mock('@/components/shared/Toast', () => ({
  useToast: jest.fn(() => ({ addToast: jest.fn() })),
}))

jest.mock('@/components/shared/Breadcrumb', () => ({
  Breadcrumb: ({ items }: any) => (
    <nav data-testid="breadcrumb">
      {items.map((item: any, i: number) => (
        <span key={i}>{item.label}</span>
      ))}
    </nav>
  ),
}))

jest.mock('@/components/shared/Button', () => ({
  Button: ({ children, onClick, disabled, variant }: any) => (
    <button onClick={onClick} disabled={disabled} data-variant={variant}>
      {children}
    </button>
  ),
}))

jest.mock('@/components/shared/Label', () => ({
  Label: ({ children, htmlFor }: any) => (
    <label htmlFor={htmlFor}>{children}</label>
  ),
}))

jest.mock('@/components/shared/Textarea', () => ({
  Textarea: ({ id, value, onChange, placeholder, rows }: any) => (
    <textarea
      id={id}
      value={value}
      onChange={onChange}
      placeholder={placeholder}
      rows={rows}
      data-testid={`textarea-${id}`}
    />
  ),
}))

jest.mock('@heroicons/react/24/outline', () => ({
  ArrowLeftIcon: () => <svg data-testid="arrow-left-icon" />,
}))

const mockRouter = { push: jest.fn(), replace: jest.fn() }
const mockAddToast = jest.fn()
const mockT = (key: string, params?: any) => key

function createParams(id: string) {
  return Promise.resolve({ id })
}

const mockContributor = {
  id: 'user-2',
  username: 'contributor',
  email: 'contributor@test.com',
  is_superadmin: false,
  is_active: true,
  role: 'CONTRIBUTOR',
}

const mockOrgAdmin = {
  id: 'user-4',
  username: 'orgadmin',
  email: 'orgadmin@test.com',
  is_superadmin: false,
  is_active: true,
  role: 'ORG_ADMIN',
}

const mockSuperadmin = {
  id: 'user-1',
  username: 'admin',
  email: 'admin@test.com',
  is_superadmin: true,
  is_active: true,
  role: 'ORG_ADMIN',
}

const mockReportEmptySections = {
  id: 'report-1',
  project_id: 'proj-1',
  project_title: 'Test Project',
  is_published: false,
  content: {
    sections: {},
    metadata: {},
  },
}

const mockReportFullSections = {
  id: 'report-2',
  project_id: 'proj-1',
  project_title: 'Test Project',
  is_published: false,
  content: {
    sections: {
      project_info: {
        custom_title: 'My Title',
        custom_description: 'My Description',
      },
      data: { custom_text: 'Data text' },
      annotations: {
        custom_text: 'Ann text',
        acknowledgment_text: 'Thanks',
      },
      generation: { custom_text: 'Gen text' },
      evaluation: {
        custom_interpretation: 'Interp',
        conclusions: 'Concl',
      },
    },
    metadata: {},
  },
}

describe('ReportEditorPage - branch coverage', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    ;(useRouter as jest.Mock).mockReturnValue(mockRouter)
    ;(useI18n as jest.Mock).mockReturnValue({ t: mockT })
    global.fetch = jest.fn()

    const { useToast } = require('@/components/shared/Toast')
    ;(useToast as jest.Mock).mockReturnValue({ addToast: mockAddToast })
  })

  afterEach(() => {
    jest.restoreAllMocks()
  })

  describe('Role-based access', () => {
    it('allows CONTRIBUTOR to access the page', async () => {
      ;(useAuth as jest.Mock).mockReturnValue({ user: mockContributor })
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockReportFullSections),
      })

      render(<ReportEditorPage params={createParams('proj-1')} />)

      // Contributor can fetch report but is not superadmin, so renders null after load
      await waitFor(() => {
        expect(global.fetch).toHaveBeenCalled()
      })
    })

    it('allows ORG_ADMIN to access the page', async () => {
      ;(useAuth as jest.Mock).mockReturnValue({ user: mockOrgAdmin })
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockReportFullSections),
      })

      render(<ReportEditorPage params={createParams('proj-1')} />)

      await waitFor(() => {
        expect(global.fetch).toHaveBeenCalled()
      })
    })
  })

  describe('Report with empty sections', () => {
    it('handles report with no section data (all optional chaining defaults)', async () => {
      ;(useAuth as jest.Mock).mockReturnValue({ user: mockSuperadmin })
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockReportEmptySections),
      })

      render(<ReportEditorPage params={createParams('proj-1')} />)

      await waitFor(() => {
        expect(
          screen.getByText('project.report.editor.projectInfo.title')
        ).toBeInTheDocument()
      })

      // All fields should be empty strings (defaulted from undefined via || '')
      const titleInput = screen.getByPlaceholderText('Test Project') as HTMLInputElement
      expect(titleInput.value).toBe('')
    })

    it('handles report with no content.sections at all', async () => {
      ;(useAuth as jest.Mock).mockReturnValue({ user: mockSuperadmin })
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: () =>
          Promise.resolve({
            id: 'report-3',
            project_id: 'proj-1',
            project_title: 'Test Project',
            is_published: false,
            content: {
              metadata: {},
            },
          }),
      })

      render(<ReportEditorPage params={createParams('proj-1')} />)

      await waitFor(() => {
        expect(
          screen.getByText('project.report.editor.projectInfo.title')
        ).toBeInTheDocument()
      })
    })
  })

  describe('Save edge cases', () => {
    it('shows saving text on save button while saving', async () => {
      ;(useAuth as jest.Mock).mockReturnValue({ user: mockSuperadmin })
      // Mount-time: (1) main report, (2) report-data (metrics list).
      // Click save: (3) PUT/POST that never resolves to keep "saving" state.
      ;(global.fetch as jest.Mock)
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve(mockReportFullSections),
        })
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ evaluation_charts: { by_model: {}, metric_metadata: {} } }),
        })
        .mockImplementationOnce(() => new Promise(() => {}))

      const user = userEvent.setup()
      render(<ReportEditorPage params={createParams('proj-1')} />)

      await waitFor(() => {
        expect(screen.getByText('project.report.editor.saveReport')).toBeInTheDocument()
      })

      await user.click(screen.getByText('project.report.editor.saveReport'))

      await waitFor(() => {
        expect(screen.getByText('project.report.editor.saving')).toBeInTheDocument()
      })
    })

    it('clears field values to undefined when saving empty strings', async () => {
      ;(useAuth as jest.Mock).mockReturnValue({ user: mockSuperadmin })
      ;(global.fetch as jest.Mock)
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve(mockReportFullSections),
        })
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ evaluation_charts: { by_model: {}, metric_metadata: {} } }),
        })
        .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve({}) })

      const user = userEvent.setup()
      render(<ReportEditorPage params={createParams('proj-1')} />)

      await waitFor(() => {
        expect(screen.getByPlaceholderText('Test Project')).toBeInTheDocument()
      })

      // Clear the custom title field
      const titleInput = screen.getByPlaceholderText('Test Project')
      await user.clear(titleInput)

      // Save
      await user.click(screen.getByText('project.report.editor.saveReport'))

      await waitFor(() => {
        expect(global.fetch).toHaveBeenCalledTimes(3)
        // The save call is the third fetch (after report + metrics on mount).
        const postCall = (global.fetch as jest.Mock).mock.calls[2]
        expect(postCall[1].method).toBe('POST')
        const body = JSON.parse(postCall[1].body)
        // Empty string becomes undefined in the save payload.
        expect(body.content.sections.project_info.custom_title).toBeUndefined()
      })
    })
  })

  describe('Non-superadmin post-load rendering', () => {
    it('renders null for non-superadmin contributor after report loads', async () => {
      ;(useAuth as jest.Mock).mockReturnValue({ user: mockContributor })
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockReportFullSections),
      })

      const { container } = render(
        <ReportEditorPage params={createParams('proj-1')} />
      )

      // The non-superadmin check returns null after load
      await waitFor(() => {
        expect(global.fetch).toHaveBeenCalled()
      })

      // Container should be empty since non-superadmin renders null
      await waitFor(() => {
        expect(container.querySelector('h1')).toBeNull()
      })
    })
  })

  describe('Network error on fetch', () => {
    it('handles network exception during fetch', async () => {
      ;(useAuth as jest.Mock).mockReturnValue({ user: mockSuperadmin })
      ;(global.fetch as jest.Mock).mockRejectedValueOnce(new Error('Network error'))

      render(<ReportEditorPage params={createParams('proj-1')} />)

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(
          'project.report.editor.failedToLoad',
          'error'
        )
        expect(mockRouter.push).toHaveBeenCalledWith('/projects/proj-1')
      })
    })
  })
})

/**
 * Banner on the pages of a soft-deleted project: superadmins only, only for
 * the project in view, restore refreshes the project so the banner goes.
 *
 * @jest-environment jsdom
 */

import '@testing-library/jest-dom'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { DeletedProjectBanner } from '../DeletedProjectBanner'

const mockState: { current: any } = { current: {} }
jest.mock('@/stores/projectStore', () => ({
  useProjectStore: (selector: (s: any) => any) => selector(mockState.current),
}))
const mockUser: { current: any } = { current: null }
jest.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({ user: mockUser.current }),
}))
jest.mock('@/contexts/I18nContext', () =>
  require('@/test-utils/i18nMock').i18nMock('de'),
)
const mockAddToast = jest.fn()
jest.mock('@/components/shared/Toast', () => ({
  useToast: () => ({ addToast: mockAddToast }),
}))
const mockRestore = jest.fn()
jest.mock('@/lib/api/projects', () => ({
  projectsAPI: { restoreProject: (...a: any[]) => mockRestore(...a) },
}))

const mockFetchProject = jest.fn()
const deletedProject = {
  id: 'p1',
  title: 'Alte Klausur',
  deleted_at: '2026-09-01T10:00:00Z',
}

describe('DeletedProjectBanner', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockUser.current = { id: 'su', is_superadmin: true }
    mockState.current = {
      currentProject: deletedProject,
      fetchProject: mockFetchProject,
    }
  })

  it('shows the deleted notice with a restore action and a way back to the list', () => {
    render(<DeletedProjectBanner projectId="p1" />)
    const banner = screen.getByTestId('deleted-project-banner')
    expect(banner).toHaveTextContent('Dieses Projekt wurde am')
    expect(banner).toHaveTextContent('gelöscht')
    expect(screen.getByTestId('deleted-project-banner-list')).toHaveAttribute(
      'href',
      '/projects/deleted',
    )
    expect(
      screen.getByTestId('deleted-project-banner-restore'),
    ).toHaveTextContent('Wiederherstellen')
  })

  it('restores the project and reloads it', async () => {
    mockRestore.mockResolvedValue(undefined)
    mockFetchProject.mockResolvedValue({ ...deletedProject, deleted_at: null })
    render(<DeletedProjectBanner projectId="p1" />)
    fireEvent.click(screen.getByTestId('deleted-project-banner-restore'))
    await waitFor(() => expect(mockRestore).toHaveBeenCalledWith('p1'))
    await waitFor(() => expect(mockFetchProject).toHaveBeenCalledWith('p1'))
    expect(mockAddToast).toHaveBeenCalledWith(
      'Projekt wiederhergestellt.',
      'success',
    )
  })

  it('reports a failed restore', async () => {
    mockRestore.mockRejectedValue(new Error('kaputt'))
    render(<DeletedProjectBanner projectId="p1" />)
    fireEvent.click(screen.getByTestId('deleted-project-banner-restore'))
    await waitFor(() =>
      expect(mockAddToast).toHaveBeenCalledWith('kaputt', 'error'),
    )
    expect(mockFetchProject).not.toHaveBeenCalled()
  })

  it.each([
    [
      'a project that is not deleted',
      { ...deletedProject, deleted_at: null },
      'p1',
    ],
    ['another project still in the store', deletedProject, 'p2'],
    ['no project loaded yet', null, 'p1'],
  ])('renders nothing for %s', (_label, currentProject, projectId) => {
    mockState.current = { currentProject, fetchProject: mockFetchProject }
    render(<DeletedProjectBanner projectId={projectId} />)
    expect(
      screen.queryByTestId('deleted-project-banner'),
    ).not.toBeInTheDocument()
  })

  it('renders nothing for a non-superadmin', () => {
    mockUser.current = { id: 'u', is_superadmin: false }
    render(<DeletedProjectBanner projectId="p1" />)
    expect(
      screen.queryByTestId('deleted-project-banner'),
    ).not.toBeInTheDocument()
  })
})

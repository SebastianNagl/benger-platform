/**
 * @jest-environment jsdom
 *
 * /projects/deleted - superadmin-only soft-delete recovery view. It is the
 * shared project list in its deleted mode (ProjectListTable.deleted.test
 * covers the rows, restore and purge); this page only gates the route.
 */
import '@testing-library/jest-dom'
import { render, screen, waitFor } from '@testing-library/react'
import DeletedProjectsPage from '../page'

const mockReplace = jest.fn()
jest.mock('next/navigation', () => ({
  useRouter: () => ({ replace: mockReplace, push: jest.fn() }),
}))
const mockAuth = {
  current: { user: { id: 'a', is_superadmin: true } as any, isLoading: false },
}
jest.mock('@/contexts/AuthContext', () => ({
  useAuth: () => mockAuth.current,
}))
jest.mock('@/contexts/I18nContext', () =>
  require('@/test-utils/i18nMock').i18nMock('de'),
)
jest.mock('@/components/shared/Breadcrumb', () => ({
  Breadcrumb: () => <nav />,
}))
jest.mock('@/components/shared/ResponsiveContainer', () => ({
  ResponsiveContainer: ({ children }: any) => <div>{children}</div>,
}))
const mockTable = jest.fn()
jest.mock('@/components/projects/ProjectListTable', () => ({
  ProjectListTable: (props: any) => {
    mockTable(props)
    return <div data-testid="project-list-table" />
  },
}))

describe('DeletedProjectsPage', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockAuth.current = {
      user: { id: 'a', is_superadmin: true },
      isLoading: false,
    }
  })

  it('renders the shared project list in its deleted mode for superadmins', () => {
    render(<DeletedProjectsPage />)
    expect(screen.getByTestId('project-list-table')).toBeInTheDocument()
    expect(mockTable).toHaveBeenCalledWith({ showDeletedOnly: true })
    expect(mockReplace).not.toHaveBeenCalled()
  })

  it('non-superadmins are redirected away and never load the list', async () => {
    mockAuth.current = {
      user: { id: 'b', is_superadmin: false },
      isLoading: false,
    }
    render(<DeletedProjectsPage />)
    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith('/projects'))
    expect(screen.queryByTestId('project-list-table')).not.toBeInTheDocument()
  })

  it('renders nothing while the session loads', () => {
    mockAuth.current = { user: null, isLoading: true }
    render(<DeletedProjectsPage />)
    expect(screen.queryByTestId('project-list-table')).not.toBeInTheDocument()
    expect(mockReplace).not.toHaveBeenCalled()
  })
})

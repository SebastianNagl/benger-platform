/**
 * @jest-environment jsdom
 */

import { render, screen, waitFor } from '@testing-library/react'
import UsersOrganizationsPage from '../page'

const mockPush = jest.fn()

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
  useSearchParams: () => new URLSearchParams(),
}))

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string) => key,
  }),
}))

const mockSuperadmin = {
  id: 'u1',
  name: 'Admin',
  username: 'admin',
  email: 'admin@test.com',
  is_superadmin: true,
  is_active: true,
  created_at: '2024-01-01',
  updated_at: '2024-01-01',
}

const mockOrgs = [
  { id: 'org1', name: 'Org 1', slug: 'org1', role: 'admin' },
]

let mockAuthReturn: any = {
  user: mockSuperadmin,
  organizations: mockOrgs,
  isLoading: false,
}

jest.mock('@/contexts/AuthContext', () => ({
  useAuth: () => mockAuthReturn,
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

jest.mock('@/components/shared/ResponsiveContainer', () => ({
  ResponsiveContainer: ({ children }: any) => <div>{children}</div>,
}))

jest.mock('@headlessui/react', () => ({
  Tab: ({ children, className }: any) => (
    <button
      className={
        typeof className === 'function'
          ? className({ selected: false })
          : className
      }
    >
      {children}
    </button>
  ),
  TabGroup: ({ children }: any) => (
    <div data-testid="tab-group">{children}</div>
  ),
  TabList: ({ children }: any) => <div role="tablist">{children}</div>,
  TabPanel: ({ children }: any) => <div role="tabpanel">{children}</div>,
  TabPanels: ({ children }: any) => <div>{children}</div>,
}))

jest.mock('@heroicons/react/24/outline', () => ({
  BuildingOfficeIcon: () => <span data-testid="building-icon" />,
  UserGroupIcon: () => <span data-testid="user-group-icon" />,
}))

jest.mock('@/app/admin/users-organizations/components/GlobalUsersTab', () => ({
  GlobalUsersTab: () => (
    <div data-testid="global-users-tab">Global Users</div>
  ),
}))

jest.mock(
  '@/app/admin/users-organizations/components/OrganizationsTab',
  () => ({
    OrganizationsTab: () => (
      <div data-testid="organizations-tab">Organizations</div>
    ),
  })
)

describe('UsersOrganizationsPage', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockAuthReturn = {
      user: mockSuperadmin,
      organizations: mockOrgs,
      isLoading: false,
    }
  })

  describe('when user is superadmin', () => {
    it('should render page title', async () => {
      render(<UsersOrganizationsPage />)
      await waitFor(() => {
        const headings = screen.getAllByText('admin.usersOrganizations')
        expect(headings.length).toBeGreaterThanOrEqual(1)
      })
    })

    it('should render breadcrumb', async () => {
      render(<UsersOrganizationsPage />)
      await waitFor(() => {
        expect(screen.getByTestId('breadcrumb')).toBeInTheDocument()
        expect(
          screen.getByText('navigation.dashboard')
        ).toBeInTheDocument()
      })
    })

    it('should render description text', async () => {
      render(<UsersOrganizationsPage />)
      await waitFor(() => {
        expect(
          screen.getByText('admin.usersOrganizationsDescription')
        ).toBeInTheDocument()
      })
    })

    it('should show Global Users tab for superadmin', async () => {
      render(<UsersOrganizationsPage />)
      await waitFor(() => {
        expect(screen.getByText('admin.globalUsers')).toBeInTheDocument()
      })
    })

    it('should show Organizations tab', async () => {
      render(<UsersOrganizationsPage />)
      await waitFor(() => {
        expect(
          screen.getByText('admin.organizations.tabLabel')
        ).toBeInTheDocument()
      })
    })

    it('should render GlobalUsersTab component', async () => {
      render(<UsersOrganizationsPage />)
      await waitFor(() => {
        expect(screen.getByTestId('global-users-tab')).toBeInTheDocument()
      })
    })

    it('should render OrganizationsTab component', async () => {
      render(<UsersOrganizationsPage />)
      await waitFor(() => {
        expect(
          screen.getByTestId('organizations-tab')
        ).toBeInTheDocument()
      })
    })
  })

  describe('when user is null', () => {
    it('should redirect to login', () => {
      mockAuthReturn = { user: null, organizations: [], isLoading: false }
      render(<UsersOrganizationsPage />)
      expect(mockPush).toHaveBeenCalledWith('/login')
    })
  })

  describe('when user is not superadmin', () => {
    beforeEach(() => {
      mockAuthReturn = {
        user: { ...mockSuperadmin, is_superadmin: false },
        organizations: mockOrgs,
        isLoading: false,
      }
    })

    it('should not show Global Users tab', async () => {
      render(<UsersOrganizationsPage />)
      await waitFor(() => {
        expect(
          screen.queryByText('admin.globalUsers')
        ).not.toBeInTheDocument()
      })
    })

    it('should show Organizations tab', async () => {
      render(<UsersOrganizationsPage />)
      await waitFor(() => {
        expect(
          screen.getByText('admin.organizations.tabLabel')
        ).toBeInTheDocument()
      })
    })
  })
})

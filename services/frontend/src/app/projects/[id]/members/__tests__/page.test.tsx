/**
 * Unit tests for Project Members page
 * Tests member management, organization assignment, and permission checks
 *
 * @jest-environment jsdom
 */

import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { organizationsAPI } from '@/lib/api/organizations'
import { projectsAPI } from '@/lib/api/projects'
import { useProjectStore } from '@/stores/projectStore'
import '@testing-library/jest-dom'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useParams, useRouter } from 'next/navigation'
import ProjectMembersPage from '../page'

// Mock Next.js navigation
jest.mock('next/navigation', () => ({
  useRouter: jest.fn(),
  useParams: jest.fn(),
  useSearchParams: jest.fn(() => new URLSearchParams()),
  usePathname: jest.fn(() => '/'),
  notFound: jest.fn(),
  redirect: jest.fn(),
}))

// Mock AuthContext must come before the component import
jest.mock('@/contexts/AuthContext', () => ({
  useAuth: jest.fn(),
}))

// Mock I18nContext must come before the component import
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: jest.fn(),
}))

// Mock API modules
jest.mock('@/lib/api/projects', () => ({
  projectsAPI: {
    getMembers: jest.fn(),
    addMember: jest.fn(),
    removeMember: jest.fn(),
    getOrganizations: jest.fn(),
    addOrganization: jest.fn(),
    removeOrganization: jest.fn(),
  },
}))

jest.mock('@/lib/api/organizations', () => ({
  organizationsAPI: {
    getOrganizations: jest.fn(),
    getOrganizationMembers: jest.fn(),
  },
}))

// Mock project store
jest.mock('@/stores/projectStore', () => ({
  useProjectStore: jest.fn(),
}))

// Mock toast with stable function reference
const mockAddToast = jest.fn()
jest.mock('@/components/shared/Toast', () => ({
  useToast: () => ({
    addToast: mockAddToast,
  }),
}))

// Mock dialog hooks
jest.mock('@/hooks/useDialogs', () => ({
  useDeleteConfirm: () => jest.fn((itemName) => Promise.resolve(true)),
}))

// Mock Heroicons
jest.mock('@heroicons/react/24/outline', () => ({
  ArrowLeftIcon: () => <div data-testid="arrow-left-icon" />,
  UserGroupIcon: () => <div data-testid="user-group-icon" />,
  UserPlusIcon: () => <div data-testid="user-plus-icon" />,
  BuildingOfficeIcon: () => <div data-testid="building-icon" />,
  MagnifyingGlassIcon: () => <div data-testid="search-icon" />,
  TrashIcon: () => <div data-testid="trash-icon" />,
}))

// Mock Headless UI Dialog
jest.mock('@headlessui/react', () => {
  const React = require('react')
  return {
    Dialog: ({ open, onClose, children }: any) =>
      open ? <div role="dialog">{children}</div> : null,
    DialogBackdrop: ({ children }: any) => <div>{children}</div>,
    DialogPanel: ({ children }: any) => <div>{children}</div>,
    DialogTitle: ({ children }: any) => <h2>{children}</h2>,
  }
})

// Mock date-fns
jest.mock('date-fns', () => ({
  formatDistanceToNow: jest.fn(() => '2 days ago'),
}))

// Mock shared components
jest.mock('@/components/shared/Breadcrumb', () => ({
  Breadcrumb: ({ items }: any) => (
    <nav data-testid="breadcrumb">
      {items?.map((item: any, i: number) =>
        item.href ? (
          <a key={i} href={item.href}>
            {item.label}
          </a>
        ) : (
          <span key={i}>{item.label}</span>
        )
      )}
    </nav>
  ),
}))

jest.mock('@/components/shared/Button', () => ({
  Button: ({ children, onClick, disabled, ...props }: any) => (
    <button onClick={onClick} disabled={disabled} {...props}>
      {children}
    </button>
  ),
}))

jest.mock('@/components/shared/Badge', () => ({
  Badge: ({ children }: any) => <span data-testid="badge">{children}</span>,
}))

jest.mock('@/components/shared/Card', () => ({
  Card: ({ children }: any) => <div data-testid="card">{children}</div>,
}))

jest.mock('@/components/shared/Input', () => ({
  Input: (props: any) => <input {...props} />,
}))

jest.mock('@/components/shared/Tabs', () => ({
  Tabs: ({ children }: any) => <div data-testid="tabs">{children}</div>,
  TabsList: ({ children }: any) => (
    <div data-testid="tabs-list">{children}</div>
  ),
  TabsTrigger: ({ children, value, onClick }: any) => (
    <button data-testid={`tab-${value}`} onClick={onClick}>
      {children}
    </button>
  ),
  TabsContent: ({ children, value }: any) => (
    <div data-testid={`tab-content-${value}`}>{children}</div>
  ),
}))

jest.mock('@/components/projects/UserAvatar', () => ({
  UserAvatar: ({ user }: any) => (
    <div data-testid="user-avatar">{user?.username || 'User'}</div>
  ),
}))
jest.mock('@/components/shared/FilterToolbar', () => {
  const FilterToolbar = ({
    searchValue,
    onSearchChange,
    searchPlaceholder,
    searchLabel,
    clearLabel = 'Clear filters',
    onClearFilters,
    hasActiveFilters,
    leftExtras,
    rightExtras,
    children,
  }: any) => (
    <div data-testid="filter-toolbar">
      {leftExtras}
      {onSearchChange && (
        <input
          data-testid="filter-toolbar-search"
          type="search"
          placeholder={searchPlaceholder}
          title={searchPlaceholder || searchLabel}
          value={searchValue ?? ''}
          onChange={(e) => onSearchChange(e.target.value)}
        />
      )}
      <div data-testid="filter-toolbar-fields">{children}</div>
      {onClearFilters && (
        <button
          data-testid="filter-toolbar-clear"
          onClick={onClearFilters}
          disabled={!hasActiveFilters}
          title={clearLabel}
          aria-label={clearLabel}
        />
      )}
      {rightExtras}
    </div>
  )
  FilterToolbar.Field = ({ children }: any) => <div>{children}</div>
  return { FilterToolbar }
})


const mockRouter = {
  push: jest.fn(),
  back: jest.fn(),
  replace: jest.fn(),
  refresh: jest.fn(),
  prefetch: jest.fn(),
}

const mockSuperadmin = {
  id: 'user-1',
  username: 'admin',
  email: 'admin@example.com',
  is_superadmin: true,
  role: 'superadmin',
}

const mockOrgAdmin = {
  id: 'user-2',
  username: 'orgadmin',
  email: 'orgadmin@example.com',
  is_superadmin: false,
  role: 'org_admin',
  organization_memberships: [
    {
      organization_id: 'org-1',
      role: 'ORG_ADMIN',
    },
  ],
}

const mockAnnotator = {
  id: 'user-3',
  username: 'annotator',
  email: 'annotator@example.com',
  is_superadmin: false,
  role: 'annotator',
  organization_memberships: [
    {
      organization_id: 'org-1',
      role: 'ANNOTATOR',
    },
  ],
}

const mockProject = {
  id: 'project-1',
  title: 'Test Project',
  description: 'Test Description',
  organization_id: 'org-1',
  created_at: '2024-01-01T00:00:00Z',
}

const mockMembers = [
  {
    id: 'member-1',
    user_id: 'user-1',
    name: 'John Doe',
    email: 'john@example.com',
    role: 'CONTRIBUTOR',
    is_direct_member: true,
    organization_id: 'org-1',
    organization_name: 'Test Org',
    added_at: '2024-01-01T00:00:00Z',
  },
  {
    id: 'member-2',
    user_id: 'user-2',
    name: 'Jane Smith',
    email: 'jane@example.com',
    role: 'ANNOTATOR',
    is_direct_member: false,
    organization_id: 'org-1',
    organization_name: 'Test Org',
    added_at: '2024-01-02T00:00:00Z',
  },
]

const mockOrganizations = [
  {
    id: 'org-1',
    name: 'Test Org',
    slug: 'test-org',
    description: 'Test Organization',
  },
  {
    id: 'org-2',
    name: 'Another Org',
    slug: 'another-org',
    description: 'Another Organization',
  },
]

const mockProjectOrganizations = [
  {
    organization_id: 'org-1',
    organization_name: 'Test Org',
    assigned_at: '2024-01-01T00:00:00Z',
    assigned_by: 'admin',
  },
]

const mockOrgMembers = [
  {
    user_id: 'user-4',
    user_name: 'Bob Johnson',
    user_email: 'bob@example.com',
    role: 'CONTRIBUTOR',
  },
  {
    user_id: 'user-5',
    user_name: 'Alice Williams',
    user_email: 'alice@example.com',
    role: 'ANNOTATOR',
  },
]

// Translation map for tests
const translations: Record<string, string> = {
  'members.title': 'Project Members',
  'members.description':
    'Manage organizations and members with access to this project',
  'members.backToProject': 'Back to Project',
  'members.organizations': 'Organizations',
  'members.searchPlaceholder': 'Search members...',
  'members.addMember': 'Add Member',
  'members.addOrganization': 'Add Organization',
  'members.noMembers': 'No members added yet',
  'members.noMembersSearch': 'No members match your search',
  'projects.tabs.members': 'Members',
  'common.search': 'Search',
  'members.addProjectMember': 'Add Project Member',
  'members.addProjectMemberDescription':
    'Add members from your organizations to this project',
  'members.addOrgTitle': 'Add Organization',
  'members.addOrgDescription':
    'Select an organization to grant access to this project',
  'navigation.dashboard': 'Dashboard',
  'navigation.projects': 'Projects',
}

describe('ProjectMembersPage', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    ;(useRouter as jest.Mock).mockReturnValue(mockRouter)
    ;(useParams as jest.Mock).mockReturnValue({ id: 'project-1' })
    ;(useI18n as jest.Mock).mockReturnValue({
      t: (key: string, vars?: any) => {
        const translation = translations[key] || key
        if (vars) {
          return translation.replace(/\{(\w+)\}/g, (_, k) => vars[k] || '')
        }
        return translation
      },
    })
    ;(useProjectStore as jest.Mock).mockReturnValue({
      currentProject: mockProject,
      loading: false,
      fetchProject: jest.fn(),
    })
    ;(projectsAPI.getMembers as jest.Mock).mockResolvedValue(mockMembers)
    ;(projectsAPI.getOrganizations as jest.Mock).mockResolvedValue(
      mockProjectOrganizations
    )
    ;(organizationsAPI.getOrganizations as jest.Mock).mockResolvedValue(
      mockOrganizations
    )
    ;(organizationsAPI.getOrganizationMembers as jest.Mock).mockResolvedValue(
      mockOrgMembers
    )
  })

  describe('Page Rendering', () => {
    it('should render page with project title and breadcrumb', async () => {
      ;(useAuth as jest.Mock).mockReturnValue({ user: mockSuperadmin })

      render(<ProjectMembersPage />)

      await waitFor(() => {
        expect(screen.getByText('Project Members')).toBeInTheDocument()
        expect(
          screen.getByText(
            'Manage organizations and members with access to this project'
          )
        ).toBeInTheDocument()
      })

      // Check breadcrumb navigation
      expect(screen.getByText('Projects')).toBeInTheDocument()
      expect(screen.getAllByText('Test Project')[0]).toBeInTheDocument()
      expect(screen.getAllByText('Members').length).toBeGreaterThan(0)
    })

    it('should show loading state when project is not loaded', () => {
      ;(useAuth as jest.Mock).mockReturnValue({ user: mockSuperadmin })
      ;(useProjectStore as jest.Mock).mockReturnValue({
        currentProject: null,
        loading: true,
        fetchProject: jest.fn(),
      })

      render(<ProjectMembersPage />)

      expect(screen.getByText('Loading project...')).toBeInTheDocument()
    })

    it('should fetch project if not already loaded', async () => {
      const mockFetchProject = jest.fn()
      ;(useAuth as jest.Mock).mockReturnValue({ user: mockSuperadmin })
      ;(useProjectStore as jest.Mock).mockReturnValue({
        currentProject: null,
        loading: false,
        fetchProject: mockFetchProject,
      })

      render(<ProjectMembersPage />)

      expect(mockFetchProject).toHaveBeenCalledWith('project-1')
    })
  })

  describe('Members List Display', () => {
    it('should display list of project members', async () => {
      ;(useAuth as jest.Mock).mockReturnValue({ user: mockSuperadmin })

      render(<ProjectMembersPage />)

      await waitFor(() => {
        expect(screen.getAllByText('John Doe')[0]).toBeInTheDocument()
        expect(screen.getByText('john@example.com')).toBeInTheDocument()
        expect(screen.getAllByText('Jane Smith')[0]).toBeInTheDocument()
        expect(screen.getByText('jane@example.com')).toBeInTheDocument()
      })
    })

    it('should display member roles and organizations', async () => {
      ;(useAuth as jest.Mock).mockReturnValue({ user: mockSuperadmin })

      render(<ProjectMembersPage />)

      await waitFor(() => {
        // Test Org appears at least twice (once for each member)
        expect(screen.getAllByText('Test Org').length).toBeGreaterThanOrEqual(2)
        expect(screen.getByText('CONTRIBUTOR')).toBeInTheDocument()
        expect(screen.getByText('ANNOTATOR')).toBeInTheDocument()
      })
    })

    it('should show empty state when no members', async () => {
      ;(useAuth as jest.Mock).mockReturnValue({ user: mockSuperadmin })
      ;(projectsAPI.getMembers as jest.Mock).mockResolvedValue([])

      render(<ProjectMembersPage />)

      await waitFor(() => {
        expect(screen.getByText('No members added yet')).toBeInTheDocument()
      })
    })

    it('should show loading spinner while fetching members', () => {
      ;(useAuth as jest.Mock).mockReturnValue({ user: mockSuperadmin })
      ;(projectsAPI.getMembers as jest.Mock).mockImplementation(
        () => new Promise(() => {})
      )

      render(<ProjectMembersPage />)

      // Check for loading state in members tab
      const spinners = document.querySelectorAll('.animate-spin')
      expect(spinners.length).toBeGreaterThan(0)
    })
  })

  describe('Search Functionality', () => {
    it('should filter members by name', async () => {
      const user = userEvent.setup()
      ;(useAuth as jest.Mock).mockReturnValue({ user: mockSuperadmin })

      render(<ProjectMembersPage />)

      await waitFor(() => {
        expect(screen.getAllByText('John Doe').length).toBeGreaterThan(0)
      })

      const searchInput = screen.getByPlaceholderText('Search members...')
      await user.type(searchInput, 'John')

      await waitFor(() => {
        expect(screen.getAllByText('John Doe').length).toBeGreaterThan(0)
        expect(screen.queryByText('Jane Smith')).not.toBeInTheDocument()
      })
    })

    it('should filter members by email', async () => {
      const user = userEvent.setup()
      ;(useAuth as jest.Mock).mockReturnValue({ user: mockSuperadmin })

      render(<ProjectMembersPage />)

      await waitFor(() => {
        expect(screen.getAllByText('Jane Smith').length).toBeGreaterThan(0)
      })

      const searchInput = screen.getByPlaceholderText('Search members...')
      await user.type(searchInput, 'jane@')

      await waitFor(() => {
        expect(screen.getAllByText('Jane Smith').length).toBeGreaterThan(0)
        expect(screen.queryByText('John Doe')).not.toBeInTheDocument()
      })
    })

    it('should filter members by organization name', async () => {
      const user = userEvent.setup()
      ;(useAuth as jest.Mock).mockReturnValue({ user: mockSuperadmin })

      render(<ProjectMembersPage />)

      await waitFor(() => {
        expect(screen.getAllByText('John Doe').length).toBeGreaterThan(0)
      })

      const searchInput = screen.getByPlaceholderText('Search members...')
      await user.type(searchInput, 'Test Org')

      await waitFor(() => {
        expect(screen.getAllByText('John Doe').length).toBeGreaterThan(0)
        expect(screen.getAllByText('Jane Smith').length).toBeGreaterThan(0)
      })
    })

    it('should show no results message for non-matching search', async () => {
      const user = userEvent.setup()
      ;(useAuth as jest.Mock).mockReturnValue({ user: mockSuperadmin })

      render(<ProjectMembersPage />)

      await waitFor(() => {
        expect(screen.getAllByText('John Doe').length).toBeGreaterThan(0)
      })

      const searchInput = screen.getByPlaceholderText('Search members...')
      await user.type(searchInput, 'nonexistent')

      await waitFor(() => {
        expect(
          screen.getByText('No members match your search')
        ).toBeInTheDocument()
      })
    })
  })

  describe('Add Member', () => {
    it('should show add member button for users with permissions', async () => {
      ;(useAuth as jest.Mock).mockReturnValue({ user: mockSuperadmin })

      render(<ProjectMembersPage />)

      await waitFor(() => {
        expect(screen.getByText('Add Member')).toBeInTheDocument()
      })
    })

    it('should open add member dialog when clicking add button', async () => {
      const user = userEvent.setup()
      ;(useAuth as jest.Mock).mockReturnValue({ user: mockSuperadmin })

      render(<ProjectMembersPage />)

      await waitFor(() => {
        expect(screen.getByText('Add Member')).toBeInTheDocument()
      })

      await user.click(screen.getByText('Add Member'))

      await waitFor(() => {
        expect(screen.getByText('Add Project Member')).toBeInTheDocument()
        expect(
          screen.getByText(
            'Add members from your organizations to this project'
          )
        ).toBeInTheDocument()
      })
    })

    it('should load organization members when selecting organization', async () => {
      const user = userEvent.setup()
      ;(useAuth as jest.Mock).mockReturnValue({ user: mockSuperadmin })

      render(<ProjectMembersPage />)

      await waitFor(() => {
        expect(screen.getByText('Add Member')).toBeInTheDocument()
      })

      await user.click(screen.getByText('Add Member'))

      await waitFor(() => {
        expect(screen.getByText('Add Project Member')).toBeInTheDocument()
      })

      // Select organization from dropdown
      const selects = within(screen.getByRole('dialog')).getAllByRole('combobox')
      const orgSelect = selects[0] // First select is organization
      await user.selectOptions(orgSelect, 'org-1')

      await waitFor(() => {
        expect(organizationsAPI.getOrganizationMembers).toHaveBeenCalledWith(
          'org-1'
        )
      })
    })

    it('should successfully add a member to the project', async () => {
      const user = userEvent.setup()
      ;(useAuth as jest.Mock).mockReturnValue({ user: mockSuperadmin })
      ;(projectsAPI.addMember as jest.Mock).mockResolvedValue({
        user_name: 'Bob Johnson',
      })

      render(<ProjectMembersPage />)

      await waitFor(() => {
        expect(screen.getByText('Add Member')).toBeInTheDocument()
      })

      await user.click(screen.getByText('Add Member'))

      await waitFor(() => {
        expect(screen.getByText('Add Project Member')).toBeInTheDocument()
      })

      // Select organization
      const selects = within(screen.getByRole('dialog')).getAllByRole('combobox')
      const orgSelect = selects[0]
      await user.selectOptions(orgSelect, 'org-1')

      await waitFor(() => {
        expect(organizationsAPI.getOrganizationMembers).toHaveBeenCalled()
      })

      // Select member
      await waitFor(() => {
        const memberSelects = within(screen.getByRole('dialog')).getAllByRole('combobox')
        expect(memberSelects.length).toBeGreaterThan(1)
      })
      const memberSelect = within(screen.getByRole('dialog')).getAllByRole('combobox')[1]
      await user.selectOptions(memberSelect, 'user-4')

      // Click add button in dialog
      const addButtons = screen.getAllByText('Add Member')
      await user.click(addButtons[addButtons.length - 1])

      await waitFor(() => {
        expect(projectsAPI.addMember).toHaveBeenCalledWith(
          'project-1',
          'user-4',
          'CONTRIBUTOR'
        )
      })
    })

    it('should filter out already added members', async () => {
      const user = userEvent.setup()
      ;(useAuth as jest.Mock).mockReturnValue({ user: mockSuperadmin })
      ;(organizationsAPI.getOrganizationMembers as jest.Mock).mockResolvedValue(
        [
          {
            user_id: 'user-1', // Already a member
            user_name: 'John Doe',
            user_email: 'john@example.com',
            role: 'CONTRIBUTOR',
          },
          {
            user_id: 'user-4', // Not a member
            user_name: 'Bob Johnson',
            user_email: 'bob@example.com',
            role: 'CONTRIBUTOR',
          },
        ]
      )

      render(<ProjectMembersPage />)

      await waitFor(() => {
        expect(screen.getByText('Add Member')).toBeInTheDocument()
      })

      await user.click(screen.getByText('Add Member'))

      // Select organization
      const orgSelect = within(screen.getByRole('dialog')).getAllByRole('combobox')[0]
      await user.selectOptions(orgSelect, 'org-1')

      await waitFor(() => {
        const memberSelects = within(screen.getByRole('dialog')).getAllByRole('combobox')
        expect(memberSelects.length).toBeGreaterThan(1)
        const memberSelect = memberSelects[1]

        // John Doe should not appear in the member select
        expect(memberSelect.textContent).not.toContain('John Doe')
        // Bob Johnson should appear
        expect(memberSelect.textContent).toContain('Bob Johnson')
      })
    })
  })

  describe('Remove Member', () => {
    it('should show remove button only for direct members', async () => {
      ;(useAuth as jest.Mock).mockReturnValue({ user: mockSuperadmin })

      render(<ProjectMembersPage />)

      await waitFor(() => {
        expect(screen.getAllByText('John Doe').length).toBeGreaterThan(0)
      })

      // Find trash icons - should only be one for the direct member
      const trashIcons = screen.getAllByTestId('trash-icon')
      expect(trashIcons.length).toBe(1)
    })

    it('should confirm before removing a member', async () => {
      const user = userEvent.setup()
      const mockConfirm = jest.fn(() => Promise.resolve(true))
      jest.mock('@/hooks/useDialogs', () => ({
        useDeleteConfirm: () => mockConfirm,
      }))
      ;(useAuth as jest.Mock).mockReturnValue({ user: mockSuperadmin })
      ;(projectsAPI.removeMember as jest.Mock).mockResolvedValue(undefined)

      render(<ProjectMembersPage />)

      await waitFor(() => {
        expect(screen.getAllByText('John Doe').length).toBeGreaterThan(0)
      })

      // Click remove button for John Doe
      const trashIcons = screen.getAllByTestId('trash-icon')
      await user.click(trashIcons[0])

      await waitFor(() => {
        expect(projectsAPI.removeMember).toHaveBeenCalledWith(
          'project-1',
          'user-1'
        )
      })
    })

    it('should handle remove member errors gracefully', async () => {
      const user = userEvent.setup()
      ;(useAuth as jest.Mock).mockReturnValue({ user: mockSuperadmin })
      ;(projectsAPI.removeMember as jest.Mock).mockRejectedValue(
        new Error('Failed to remove member')
      )

      render(<ProjectMembersPage />)

      await waitFor(() => {
        expect(screen.getAllByText('John Doe').length).toBeGreaterThan(0)
      })

      const trashIcons = screen.getAllByTestId('trash-icon')
      await user.click(trashIcons[0])

      // Should not crash on error
      await waitFor(() => {
        expect(projectsAPI.removeMember).toHaveBeenCalled()
      })
    })
  })

  describe('Organization Management (Superadmin)', () => {
    it('should show organizations tab for superadmins', async () => {
      ;(useAuth as jest.Mock).mockReturnValue({ user: mockSuperadmin })

      render(<ProjectMembersPage />)

      await waitFor(() => {
        expect(screen.getByText('Organizations')).toBeInTheDocument()
      })
    })

    it('should not show organizations tab for non-superadmins', async () => {
      ;(useAuth as jest.Mock).mockReturnValue({ user: mockOrgAdmin })

      render(<ProjectMembersPage />)

      await waitFor(() => {
        expect(screen.queryByText('Organizations')).not.toBeInTheDocument()
      })
    })

    it('should display assigned organizations', async () => {
      const user = userEvent.setup()
      ;(useAuth as jest.Mock).mockReturnValue({ user: mockSuperadmin })

      render(<ProjectMembersPage />)

      // Switch to Organizations tab
      await waitFor(() => {
        expect(screen.getByText('Organizations')).toBeInTheDocument()
      })
      await user.click(screen.getByText('Organizations'))

      // Wait for the organizations tab content to appear
      await waitFor(() => {
        const orgTab = screen.getByTestId('tab-content-organizations')
        expect(within(orgTab).getAllByText('Test Org').length).toBeGreaterThan(
          0
        )
      })

      // Check that organization details are displayed
      const orgTab = screen.getByTestId('tab-content-organizations')
      expect(within(orgTab).getByText(/Added/)).toBeInTheDocument()
      expect(within(orgTab).getByText(/2 days ago/)).toBeInTheDocument()
      expect(within(orgTab).getByText(/admin/)).toBeInTheDocument()
    })

    it('should show add organization button', async () => {
      const user = userEvent.setup()
      ;(useAuth as jest.Mock).mockReturnValue({ user: mockSuperadmin })

      render(<ProjectMembersPage />)

      await user.click(screen.getByText('Organizations'))

      await waitFor(() => {
        expect(screen.getByText('Add Organization')).toBeInTheDocument()
      })
    })

    it('should open add organization dialog', async () => {
      const user = userEvent.setup()
      ;(useAuth as jest.Mock).mockReturnValue({ user: mockSuperadmin })

      render(<ProjectMembersPage />)

      await user.click(screen.getByText('Organizations'))

      await waitFor(() => {
        expect(screen.getByText('Add Organization')).toBeInTheDocument()
      })

      await user.click(screen.getByText('Add Organization'))

      await waitFor(() => {
        expect(
          screen.getByText(
            'Select an organization to grant access to this project'
          )
        ).toBeInTheDocument()
      })
    })

    it('should successfully add an organization', async () => {
      const user = userEvent.setup()
      ;(useAuth as jest.Mock).mockReturnValue({ user: mockSuperadmin })
      ;(projectsAPI.addOrganization as jest.Mock).mockResolvedValue({
        organization_name: 'Another Org',
      })

      render(<ProjectMembersPage />)

      await user.click(screen.getByText('Organizations'))
      await user.click(screen.getByText('Add Organization'))

      await waitFor(() => {
        expect(
          screen.getByText(
            'Select an organization to grant access to this project'
          )
        ).toBeInTheDocument()
      })

      // Select organization
      const orgSelect = within(screen.getByRole('dialog')).getByRole('combobox')
      await user.selectOptions(orgSelect, 'org-2')

      // Click add button
      const addButtons = screen.getAllByText('Add Organization')
      await user.click(addButtons[addButtons.length - 1])

      await waitFor(() => {
        expect(projectsAPI.addOrganization).toHaveBeenCalledWith(
          'project-1',
          'org-2'
        )
      })
    })

    it('should filter out already assigned organizations', async () => {
      const user = userEvent.setup()
      ;(useAuth as jest.Mock).mockReturnValue({ user: mockSuperadmin })

      render(<ProjectMembersPage />)

      await user.click(screen.getByText('Organizations'))
      await user.click(screen.getByText('Add Organization'))

      await waitFor(() => {
        const orgSelect = within(screen.getByRole('dialog')).getByRole('combobox')
        // Test Org (org-1) should not be in the select options
        expect(orgSelect.textContent).not.toContain('Test Org')
        // Another Org (org-2) should be available
        expect(orgSelect.textContent).toContain('Another Org')
      })
    })

    it('should remove organization with confirmation', async () => {
      const user = userEvent.setup()
      const mockConfirm = jest.fn(() => true)
      window.confirm = mockConfirm
      ;(useAuth as jest.Mock).mockReturnValue({ user: mockSuperadmin })
      ;(projectsAPI.getOrganizations as jest.Mock).mockResolvedValue([
        mockProjectOrganizations[0],
        {
          organization_id: 'org-2',
          organization_name: 'Another Org',
          assigned_at: '2024-01-02T00:00:00Z',
          assigned_by: 'admin',
        },
      ])
      ;(projectsAPI.removeOrganization as jest.Mock).mockResolvedValue(
        undefined
      )

      render(<ProjectMembersPage />)

      await user.click(screen.getByText('Organizations'))

      await waitFor(() => {
        expect(screen.getAllByText('Test Org').length).toBeGreaterThan(0)
      })

      // Find remove button in organizations tab
      const orgTab = screen.getByTestId('tab-content-organizations')
      const trashIcons = within(orgTab).getAllByTestId('trash-icon')
      await user.click(trashIcons[0])

      expect(mockConfirm).toHaveBeenCalledWith(
        'Are you sure you want to remove this organization from the project?'
      )
    })

    it('should not show remove button when only one organization', async () => {
      const user = userEvent.setup()
      ;(useAuth as jest.Mock).mockReturnValue({ user: mockSuperadmin })

      render(<ProjectMembersPage />)

      await user.click(screen.getByText('Organizations'))

      await waitFor(() => {
        expect(screen.getAllByText('Test Org').length).toBeGreaterThan(0)
      })

      // Should not show trash icon when only one organization
      // Look specifically in the organizations tab content
      const orgTab = screen.getByTestId('tab-content-organizations')
      const trashIcons = within(orgTab).queryAllByTestId('trash-icon')
      expect(trashIcons.length).toBe(0)
    })
  })

  describe('Permission Checks', () => {
    it('should allow superadmin to manage members', async () => {
      ;(useAuth as jest.Mock).mockReturnValue({ user: mockSuperadmin })

      render(<ProjectMembersPage />)

      await waitFor(() => {
        expect(screen.getByText('Add Member')).toBeInTheDocument()
      })
    })

    it('should allow org admin to manage members', async () => {
      ;(useAuth as jest.Mock).mockReturnValue({ user: mockOrgAdmin })

      render(<ProjectMembersPage />)

      await waitFor(() => {
        expect(screen.getByText('Add Member')).toBeInTheDocument()
      })
    })

    it('should not allow annotators to manage members', async () => {
      ;(useAuth as jest.Mock).mockReturnValue({ user: mockAnnotator })

      render(<ProjectMembersPage />)

      await waitFor(() => {
        expect(screen.queryByText('Add Member')).not.toBeInTheDocument()
      })
    })

    it('should hide remove buttons for users without permissions', async () => {
      ;(useAuth as jest.Mock).mockReturnValue({ user: mockAnnotator })

      render(<ProjectMembersPage />)

      await waitFor(() => {
        // Members should be visible even without permissions
        expect(screen.queryByText('Project Members')).toBeInTheDocument()
      })

      // No remove buttons should be visible
      const trashIcons = screen.queryAllByTestId('trash-icon')
      expect(trashIcons.length).toBe(0)
    })
  })

  describe('Error Handling', () => {
    it('should handle member loading errors', async () => {
      ;(useAuth as jest.Mock).mockReturnValue({ user: mockSuperadmin })
      ;(projectsAPI.getMembers as jest.Mock).mockRejectedValue(
        new Error('Failed to load members')
      )

      render(<ProjectMembersPage />)

      // Component should render without crashing
      await waitFor(() => {
        expect(screen.getByText('Project Members')).toBeInTheDocument()
      })
    })

    it('should handle organization loading errors', async () => {
      ;(useAuth as jest.Mock).mockReturnValue({ user: mockSuperadmin })
      ;(organizationsAPI.getOrganizations as jest.Mock).mockRejectedValue(
        new Error('Failed to load organizations')
      )

      render(<ProjectMembersPage />)

      // Component should render without crashing
      await waitFor(() => {
        expect(screen.getByText('Project Members')).toBeInTheDocument()
      })
    })

    it('should handle add member API errors', async () => {
      const user = userEvent.setup()
      ;(useAuth as jest.Mock).mockReturnValue({ user: mockSuperadmin })
      ;(projectsAPI.addMember as jest.Mock).mockRejectedValue(
        new Error('Failed to add member')
      )

      render(<ProjectMembersPage />)

      await waitFor(() => {
        expect(screen.getByText('Add Member')).toBeInTheDocument()
      })

      await user.click(screen.getByText('Add Member'))

      // Select organization
      const orgSelect = within(screen.getByRole('dialog')).getAllByRole('combobox')[0]
      await user.selectOptions(orgSelect, 'org-1')

      await waitFor(() => {
        const memberSelects = within(screen.getByRole('dialog')).getAllByRole('combobox')
        expect(memberSelects.length).toBeGreaterThan(1)
      })

      // Select member
      const memberSelect = within(screen.getByRole('dialog')).getAllByRole('combobox')[1]
      await user.selectOptions(memberSelect, 'user-4')

      // Click add button
      const addButtons = screen.getAllByText('Add Member')
      await user.click(addButtons[addButtons.length - 1])

      // Should not crash on error
      await waitFor(() => {
        expect(projectsAPI.addMember).toHaveBeenCalled()
      })
    })

    it('should handle add organization API errors', async () => {
      const user = userEvent.setup()
      ;(useAuth as jest.Mock).mockReturnValue({ user: mockSuperadmin })
      ;(projectsAPI.addOrganization as jest.Mock).mockRejectedValue(
        new Error('Failed to add organization')
      )

      render(<ProjectMembersPage />)

      await user.click(screen.getByText('Organizations'))
      await user.click(screen.getByText('Add Organization'))

      // Select organization
      const orgSelect = within(screen.getByRole('dialog')).getByRole('combobox')
      await user.selectOptions(orgSelect, 'org-2')

      // Click add button
      const addButtons = screen.getAllByText('Add Organization')
      await user.click(addButtons[addButtons.length - 1])

      // Should not crash on error
      await waitFor(() => {
        expect(projectsAPI.addOrganization).toHaveBeenCalled()
      })
    })
  })

  describe('Navigation', () => {
    it('should navigate back to project when clicking back button', async () => {
      const user = userEvent.setup()
      ;(useAuth as jest.Mock).mockReturnValue({ user: mockSuperadmin })

      render(<ProjectMembersPage />)

      await waitFor(() => {
        expect(screen.getByText('Back to Project')).toBeInTheDocument()
      })

      await user.click(screen.getByText('Back to Project'))

      expect(mockRouter.push).toHaveBeenCalledWith('/projects/project-1')
    })

    it('should have correct breadcrumb links', async () => {
      ;(useAuth as jest.Mock).mockReturnValue({ user: mockSuperadmin })

      render(<ProjectMembersPage />)

      await waitFor(() => {
        const projectsLink = screen.getByText('Projects')
        const projectLink = screen.getByText('Test Project')

        expect(projectsLink.closest('a')).toHaveAttribute('href', '/projects')
        expect(projectLink.closest('a')).toHaveAttribute(
          'href',
          '/projects/project-1'
        )
      })
    })
  })
})

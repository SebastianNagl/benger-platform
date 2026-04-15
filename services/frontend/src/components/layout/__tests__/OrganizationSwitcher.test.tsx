/* eslint-disable react-hooks/globals -- Valid test pattern: capturing hook values via external variables for assertions */
import { Organization } from '@/lib/api'
import { fireEvent, render, screen } from '@testing-library/react'
import { OrganizationSwitcher } from '../OrganizationSwitcher'



// Mock dependencies

// Mock useAuth hook
jest.mock('@/contexts/AuthContext', () => ({
  useAuth: jest.fn(() => ({
    organizations: [],
    currentOrganization: null,
    user: null,
    setCurrentOrganization: jest.fn(),
  })),
}))

// Mock subdomain utilities
jest.mock('@/lib/utils/subdomain', () => ({
  parseSubdomain: jest.fn(() => ({ orgSlug: null, isPrivateMode: true })),
}))

// Mock Heroicons
jest.mock('@heroicons/react/24/outline', () => {
  function ChevronUpDownIcon(props: any) {
    return <svg data-testid="chevron-icon" {...props} />
  }

  function ChevronDownIcon(props: any) {
    return <svg data-testid="chevron-icon" {...props} />
  }

  function CheckIcon(props: any) {
    return <svg data-testid="check-icon" {...props} />
  }

  function BuildingOfficeIcon(props: any) {
    return <svg data-testid="building-icon" {...props} />
  }

  function UserIcon(props: any) {
    return <svg data-testid="user-icon" {...props} />
  }

  return {
    ChevronUpDownIcon,
    ChevronDownIcon,
    CheckIcon,
    BuildingOfficeIcon,
    UserIcon,
  }
})

// Mock Headless UI Listbox
let mockListboxOnChange: any = null

jest.mock('@headlessui/react', () => {
  function MockListbox({ value, onChange, children }: any) {
    mockListboxOnChange = onChange
    return (
      <div data-testid="listbox-root">
        {typeof children === 'function' ? children({ open: true }) : children}
      </div>
    )
  }

  MockListbox.Button = function MockListboxButton({
    className,
    children,
    ...props
  }: any) {
    return (
      <button data-testid="listbox-button" className={className} {...props}>
        {children}
      </button>
    )
  }

  MockListbox.Options = function MockListboxOptions({
    className,
    children,
    ...props
  }: any) {
    return (
      <div data-testid="listbox-options" className={className} {...props}>
        {children}
      </div>
    )
  }

  MockListbox.Option = ({ className, children, value, ...props }: any) => {
    const mockProps = {
      active: false,
      selected: value?.id === 'private',
    }

    return (
      <div
        data-testid={`listbox-option-${value?.id}`}
        className={
          typeof className === 'function' ? className(mockProps) : className
        }
        onClick={() => mockListboxOnChange?.(value)}
        {...props}
      >
        {typeof children === 'function' ? children(mockProps) : children}
      </div>
    )
  }
  MockListbox.Option.displayName = 'MockListboxOption'

  return {
    Listbox: MockListbox,
  }
})

describe('OrganizationSwitcher', () => {
  const mockUseAuth = require('@/contexts/AuthContext').useAuth
  const mockParseSubdomain = require('@/lib/utils/subdomain').parseSubdomain

  const mockOrganizations: Organization[] = [
    {
      id: 'org-1',
      name: 'Organization One',
      display_name: 'Organization One',
      slug: 'org-one',
      description: 'First organization',
      is_active: true,
      member_count: 5,
      created_at: '2024-01-01T00:00:00Z',
      updated_at: '2024-01-01T00:00:00Z',
    },
    {
      id: 'org-2',
      name: 'Organization Two',
      display_name: 'Organization Two',
      slug: 'org-two',
      description: 'Second organization',
      is_active: true,
      member_count: 12,
      created_at: '2024-01-01T00:00:00Z',
      updated_at: '2024-01-01T00:00:00Z',
    },
    {
      id: 'org-3',
      name: 'Organization Three',
      display_name: 'Organization Three',
      slug: 'org-three',
      description: 'Third organization',
      is_active: true,
      member_count: undefined,
      created_at: '2024-01-01T00:00:00Z',
      updated_at: '2024-01-01T00:00:00Z',
    },
  ]

  const mockUser = {
    id: 'user-1',
    email: 'test@example.com',
    name: 'Test User',
  }

  beforeEach(() => {
    jest.clearAllMocks()
    mockUseAuth.mockReturnValue({
      organizations: [],
      currentOrganization: null,
      user: null,
      setCurrentOrganization: jest.fn(),
    })
    mockParseSubdomain.mockReturnValue({ orgSlug: null, isPrivateMode: true })
  })

  describe('visibility conditions', () => {
    it('does not render when user is not logged in', () => {
      mockUseAuth.mockReturnValue({
        organizations: mockOrganizations,
        currentOrganization: mockOrganizations[0],
        user: null,
        setCurrentOrganization: jest.fn(),
      })

      render(<OrganizationSwitcher />)

      expect(screen.queryByTestId('listbox-button')).not.toBeInTheDocument()
    })

    it('renders when user is logged in', () => {
      mockUseAuth.mockReturnValue({
        organizations: mockOrganizations,
        currentOrganization: mockOrganizations[0],
        user: mockUser,
        setCurrentOrganization: jest.fn(),
      })

      render(<OrganizationSwitcher />)

      expect(screen.getByTestId('listbox-button')).toBeInTheDocument()
    })

    it('renders even with no organizations (shows Private option)', () => {
      mockUseAuth.mockReturnValue({
        organizations: [],
        currentOrganization: null,
        user: mockUser,
        setCurrentOrganization: jest.fn(),
      })

      render(<OrganizationSwitcher />)

      expect(screen.getByTestId('listbox-button')).toBeInTheDocument()
    })
  })

  describe('basic rendering', () => {
    beforeEach(() => {
      mockUseAuth.mockReturnValue({
        organizations: mockOrganizations,
        currentOrganization: mockOrganizations[0],
        user: mockUser,
        setCurrentOrganization: jest.fn(),
      })
      mockParseSubdomain.mockReturnValue({ orgSlug: 'org-one', isPrivateMode: false })
    })

    it('renders the listbox button', () => {
      render(<OrganizationSwitcher />)

      expect(screen.getByTestId('listbox-button')).toBeInTheDocument()
    })

    it('shows current organization name when in org mode', () => {
      render(<OrganizationSwitcher />)

      expect(screen.getAllByText('Organization One').length).toBeGreaterThan(0)
    })

    it('displays chevron down icon', () => {
      render(<OrganizationSwitcher />)

      expect(screen.getByTestId('chevron-icon')).toBeInTheDocument()
    })

    it('applies custom className', () => {
      const { container } = render(
        <OrganizationSwitcher className="custom-class" />
      )

      const wrapper = container.querySelector('.relative')
      expect(wrapper).toHaveClass('custom-class')
    })
  })

  describe('private mode display', () => {
    beforeEach(() => {
      mockUseAuth.mockReturnValue({
        organizations: mockOrganizations,
        currentOrganization: null,
        user: mockUser,
        setCurrentOrganization: jest.fn(),
      })
      mockParseSubdomain.mockReturnValue({ orgSlug: null, isPrivateMode: true })
    })

    it('shows Private as selected when in private mode', () => {
      render(<OrganizationSwitcher />)

      expect(screen.getAllByText('Private').length).toBeGreaterThan(0)
    })

    it('shows user icon for Private option', () => {
      render(<OrganizationSwitcher />)

      expect(screen.getAllByTestId('user-icon').length).toBeGreaterThan(0)
    })
  })

  describe('button styling and attributes', () => {
    beforeEach(() => {
      mockUseAuth.mockReturnValue({
        organizations: mockOrganizations,
        currentOrganization: mockOrganizations[0],
        user: mockUser,
        setCurrentOrganization: jest.fn(),
      })
    })

    it('applies correct button classes', () => {
      render(<OrganizationSwitcher />)

      const button = screen.getByTestId('listbox-button')
      expect(button).toHaveClass(
        'relative',
        'w-full',
        'cursor-default',
        'rounded-lg',
        'bg-white',
        'py-2',
        'pl-3',
        'pr-10',
        'text-left',
        'shadow-md',
        'border',
        'border-gray-300'
      )
    })

    it('includes focus styling classes', () => {
      render(<OrganizationSwitcher />)

      const button = screen.getByTestId('listbox-button')
      expect(button).toHaveClass(
        'focus:outline-none',
        'focus-visible:border-indigo-500',
        'focus-visible:ring-2'
      )
    })

    it('has proper aria attributes for chevron icon', () => {
      render(<OrganizationSwitcher />)

      const chevronIcon = screen.getByTestId('chevron-icon')
      expect(chevronIcon).toHaveAttribute('aria-hidden', 'true')
    })
  })

  describe('organization options rendering', () => {
    beforeEach(() => {
      mockUseAuth.mockReturnValue({
        organizations: mockOrganizations,
        currentOrganization: mockOrganizations[0],
        user: mockUser,
        setCurrentOrganization: jest.fn(),
      })
    })

    it('renders options container', () => {
      render(<OrganizationSwitcher />)

      expect(screen.getByTestId('listbox-options')).toBeInTheDocument()
    })

    it('renders Private option and all organization options', () => {
      render(<OrganizationSwitcher />)

      expect(screen.getByTestId('listbox-option-private')).toBeInTheDocument()
      expect(screen.getByTestId('listbox-option-org-1')).toBeInTheDocument()
      expect(screen.getByTestId('listbox-option-org-2')).toBeInTheDocument()
      expect(screen.getByTestId('listbox-option-org-3')).toBeInTheDocument()
    })

    it('displays organization names in options', () => {
      render(<OrganizationSwitcher />)

      expect(screen.getByText('Organization Two')).toBeInTheDocument()
      expect(screen.getByText('Organization Three')).toBeInTheDocument()
    })

    it('displays member count when available', () => {
      render(<OrganizationSwitcher />)

      expect(screen.getByText('5 members')).toBeInTheDocument()
      expect(screen.getByText('12 members')).toBeInTheDocument()
    })

    it('does not display member count when unavailable', () => {
      render(<OrganizationSwitcher />)

      const orgThreeOption = screen.getByTestId('listbox-option-org-3')
      expect(orgThreeOption).not.toHaveTextContent('members')
    })
  })

  describe('selection state', () => {
    it('shows check icon for Private when in private mode', () => {
      mockUseAuth.mockReturnValue({
        organizations: mockOrganizations,
        currentOrganization: null,
        user: mockUser,
        setCurrentOrganization: jest.fn(),
      })
      mockParseSubdomain.mockReturnValue({ orgSlug: null, isPrivateMode: true })

      render(<OrganizationSwitcher />)

      // The mock sets selected: true for 'private' id
      expect(screen.getByTestId('check-icon')).toBeInTheDocument()
    })
  })

  describe('organization switching', () => {
    let mockSetCurrentOrganization: jest.Mock

    beforeEach(() => {
      mockSetCurrentOrganization = jest.fn()
      mockUseAuth.mockReturnValue({
        organizations: mockOrganizations,
        currentOrganization: mockOrganizations[0],
        user: mockUser,
        setCurrentOrganization: mockSetCurrentOrganization,
      })
    })

    it('calls setCurrentOrganization with org when org option is clicked', () => {
      render(<OrganizationSwitcher />)

      const secondOption = screen.getByTestId('listbox-option-org-2')
      fireEvent.click(secondOption)

      expect(mockSetCurrentOrganization).toHaveBeenCalledWith(mockOrganizations[1])
    })

    it('calls setCurrentOrganization with null when Private option is clicked', () => {
      render(<OrganizationSwitcher />)

      const privateOption = screen.getByTestId('listbox-option-private')
      fireEvent.click(privateOption)

      expect(mockSetCurrentOrganization).toHaveBeenCalledWith(null)
    })
  })

  describe('responsive and styling', () => {
    beforeEach(() => {
      mockUseAuth.mockReturnValue({
        organizations: mockOrganizations,
        currentOrganization: mockOrganizations[0],
        user: mockUser,
        setCurrentOrganization: jest.fn(),
      })
    })

    it('applies responsive text sizing', () => {
      render(<OrganizationSwitcher />)

      const button = screen.getByTestId('listbox-button')
      expect(button).toHaveClass('sm:text-sm')

      const options = screen.getByTestId('listbox-options')
      expect(options).toHaveClass('sm:text-sm')
    })

    it('uses truncate for long organization names', () => {
      const longNameOrg = {
        ...mockOrganizations[0],
        name: 'Very Long Organization Name That Should Be Truncated',
      }

      mockUseAuth.mockReturnValue({
        organizations: [longNameOrg, ...mockOrganizations.slice(1)],
        currentOrganization: longNameOrg,
        user: mockUser,
        setCurrentOrganization: jest.fn(),
      })

      const { container } = render(<OrganizationSwitcher />)

      const truncateElements = container.querySelectorAll('.truncate')
      expect(truncateElements.length).toBeGreaterThan(0)
    })

    it('handles z-index for dropdown layering', () => {
      render(<OrganizationSwitcher />)

      const options = screen.getByTestId('listbox-options')
      expect(options).toHaveClass('z-50')
    })
  })

  describe('accessibility', () => {
    beforeEach(() => {
      mockUseAuth.mockReturnValue({
        organizations: mockOrganizations,
        currentOrganization: mockOrganizations[0],
        user: mockUser,
        setCurrentOrganization: jest.fn(),
      })
    })

    it('provides proper focus management', () => {
      render(<OrganizationSwitcher />)

      const button = screen.getByTestId('listbox-button')
      expect(button).toHaveClass('focus:outline-none')
    })

    it('includes focus visible styling', () => {
      render(<OrganizationSwitcher />)

      const button = screen.getByTestId('listbox-button')
      expect(button).toHaveClass(
        'focus-visible:border-indigo-500',
        'focus-visible:ring-2',
        'focus-visible:ring-white'
      )
    })

    it('uses proper semantic structure', () => {
      render(<OrganizationSwitcher />)

      expect(screen.getByTestId('listbox-button')).toBeInTheDocument()
      expect(screen.getByTestId('listbox-options')).toBeInTheDocument()
    })

    it('hides decorative icons from screen readers', () => {
      render(<OrganizationSwitcher />)

      const chevronIcon = screen.getByTestId('chevron-icon')
      expect(chevronIcon).toHaveAttribute('aria-hidden', 'true')
    })
  })

  describe('edge cases', () => {
    it('renders with empty organizations but shows Private', () => {
      mockUseAuth.mockReturnValue({
        organizations: [],
        currentOrganization: null,
        user: mockUser,
        setCurrentOrganization: jest.fn(),
      })

      render(<OrganizationSwitcher />)

      expect(screen.getByTestId('listbox-button')).toBeInTheDocument()
      expect(screen.getByTestId('listbox-option-private')).toBeInTheDocument()
    })

    it('handles organizations with missing properties', () => {
      const incompleteOrg: Partial<Organization> = {
        id: 'incomplete-org',
        name: 'Incomplete Org',
        slug: 'incomplete-org',
        display_name: 'Incomplete Org',
        is_active: true,
        created_at: '2024-01-01T00:00:00Z',
      }

      mockUseAuth.mockReturnValue({
        organizations: [mockOrganizations[0], incompleteOrg as Organization],
        currentOrganization: mockOrganizations[0],
        user: mockUser,
        setCurrentOrganization: jest.fn(),
      })

      render(<OrganizationSwitcher />)

      expect(screen.getByText('Incomplete Org')).toBeInTheDocument()
    })

    it('handles very long organization names', () => {
      const longNameOrgs = mockOrganizations.map((org) => ({
        ...org,
        name: `Very Long Organization Name That Exceeds Normal Display Limits ${org.id}`,
      }))

      mockUseAuth.mockReturnValue({
        organizations: longNameOrgs,
        currentOrganization: longNameOrgs[0],
        user: mockUser,
        setCurrentOrganization: jest.fn(),
      })

      render(<OrganizationSwitcher />)

      expect(screen.getByTestId('listbox-button')).toBeInTheDocument()
    })
  })

  describe('integration with auth context', () => {
    it('responds to auth context changes', () => {
      const { rerender } = render(<OrganizationSwitcher />)

      // Initially no user
      expect(screen.queryByTestId('listbox-button')).not.toBeInTheDocument()

      // Update with user and organizations
      mockUseAuth.mockReturnValue({
        organizations: mockOrganizations,
        currentOrganization: mockOrganizations[0],
        user: mockUser,
        setCurrentOrganization: jest.fn(),
      })

      rerender(<OrganizationSwitcher />)

      expect(screen.getByTestId('listbox-button')).toBeInTheDocument()
    })

    it('handles user logout scenario', () => {
      mockUseAuth.mockReturnValue({
        organizations: mockOrganizations,
        currentOrganization: mockOrganizations[0],
        user: null,
        setCurrentOrganization: jest.fn(),
      })

      render(<OrganizationSwitcher />)

      expect(screen.queryByTestId('listbox-button')).not.toBeInTheDocument()
    })
  })
})

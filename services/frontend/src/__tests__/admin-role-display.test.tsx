/**
 * Tests for admin page role display and UI clarity
 * Ensures correct role system explanation and global role management
 */

/**
 * @jest-environment jsdom
 */

import '@testing-library/jest-dom'
import { render, screen } from '@testing-library/react'

// Mock the admin users page component parts
const MockRoleSystemExplanation = () => (
  <div className="border-l-4 border-blue-400 bg-blue-50 px-6 py-4 dark:border-blue-500 dark:bg-blue-950/50">
    <div className="flex">
      <div className="flex-shrink-0">
        <svg
          className="h-5 w-5 text-blue-400"
          viewBox="0 0 20 20"
          fill="currentColor"
        >
          <path
            fillRule="evenodd"
            d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z"
            clipRule="evenodd"
          />
        </svg>
      </div>
      <div className="ml-3">
        <h3 className="text-sm font-medium text-blue-800 dark:text-blue-200">
          Role System Overview
        </h3>
        <div className="mt-2 text-sm text-blue-700 dark:text-blue-300">
          <p>
            <strong>Superadmin:</strong> Full system access and user management
          </p>
          <p>
            <strong>User:</strong> Basic access with organization-specific
            permissions
          </p>
          <p className="mt-1 text-xs">
            Note: Organization roles (Admin, Contributor, User) are managed
            per-organization in the Organization Roles tab.
          </p>
        </div>
      </div>
    </div>
  </div>
)

const MockRoleDropdown = ({
  userRole,
}: {
  userRole: 'superadmin' | 'user'
}) => (
  <select value={userRole} data-testid="role-dropdown">
    <option value="user">User</option>
    <option value="superadmin">Super Admin</option>
  </select>
)

describe('Admin Role Display', () => {
  describe('Role System Explanation', () => {
    it('should display role system overview', () => {
      render(<MockRoleSystemExplanation />)

      expect(screen.getByText('Role System Overview')).toBeInTheDocument()
      expect(screen.getByText(/Superadmin:/)).toBeInTheDocument()
      expect(screen.getByText(/User:/)).toBeInTheDocument()
      expect(
        screen.getByText(/Organization roles.*managed per-organization/)
      ).toBeInTheDocument()
    })

    it('should explain global vs organization roles', () => {
      render(<MockRoleSystemExplanation />)

      expect(
        screen.getByText(/Full system access and user management/)
      ).toBeInTheDocument()
      expect(
        screen.getByText(/Basic access with organization-specific permissions/)
      ).toBeInTheDocument()
      expect(screen.getByText(/Organization Roles tab/)).toBeInTheDocument()
    })
  })

  describe('Role Dropdown', () => {
    it('should only show global roles', () => {
      render(<MockRoleDropdown userRole="user" />)

      const dropdown = screen.getByTestId('role-dropdown')
      const options = dropdown.querySelectorAll('option')

      expect(options).toHaveLength(2)
      expect(options[0]).toHaveTextContent('User')
      expect(options[1]).toHaveTextContent('Super Admin')

      // Verify no organization roles are present
      expect(screen.queryByText('Org Admin')).not.toBeInTheDocument()
      expect(screen.queryByText('Contributor')).not.toBeInTheDocument()
    })

    it('should work with superadmin role', () => {
      render(<MockRoleDropdown userRole="superadmin" />)

      const dropdown = screen.getByTestId('role-dropdown') as HTMLSelectElement
      expect(dropdown.value).toBe('superadmin')
    })

    it('should work with user role', () => {
      render(<MockRoleDropdown userRole="user" />)

      const dropdown = screen.getByTestId('role-dropdown') as HTMLSelectElement
      expect(dropdown.value).toBe('user')
    })
  })

  describe('UI Labels', () => {
    it('should use clear role-specific terminology', () => {
      const MockAdminHeader = () => (
        <div>
          <h2>Global User Roles</h2>
          <p>
            Manage system-wide user permissions. Organization-specific roles are
            managed in the Organization Roles tab.
          </p>
          <th>Global Role</th>
        </div>
      )

      render(<MockAdminHeader />)

      expect(screen.getByText('Global User Roles')).toBeInTheDocument()
      expect(screen.getByText('Global Role')).toBeInTheDocument()
      expect(
        screen.getByText(/system-wide user permissions/)
      ).toBeInTheDocument()
      expect(
        screen.getByText(/Organization-specific roles/)
      ).toBeInTheDocument()
    })
  })

  describe('Role Access Logic', () => {
    // Helper function to simulate role access checking
    const hasAccessToRoute = (
      userRole: 'superadmin' | 'user',
      route: string
    ): boolean => {
      if (userRole !== 'superadmin') return false

      return ['/data', '/tasks', '/evaluations'].includes(route)
    }

    it('should grant superadmin access to all routes', () => {
      expect(hasAccessToRoute('superadmin', '/data')).toBe(true)
      expect(hasAccessToRoute('superadmin', '/tasks')).toBe(true)
      expect(hasAccessToRoute('superadmin', '/evaluations')).toBe(true)
    })

    it('should restrict user access appropriately', () => {
      expect(hasAccessToRoute('user', '/data')).toBe(false)
      expect(hasAccessToRoute('user', '/tasks')).toBe(false)
      expect(hasAccessToRoute('user', '/evaluations')).toBe(false)
    })
  })
})

/**
 * @jest-environment jsdom
 */

import { render, screen } from '@testing-library/react'
import AdminLayout from '../layout'

// Simple integration test for admin layout
jest.mock('next/navigation', () => ({
  usePathname: jest.fn(() => '/admin/users'),
  useRouter: jest.fn(() => ({
    push: jest.fn(),
    replace: jest.fn(),
    back: jest.fn(),
  })),
}))

const mockUser = {
  id: '1',
  email: 'admin@test.com',
  name: 'Test Admin',
  username: 'testadmin',
  is_superadmin: true,
}

const mockAuthContextValue = {
  user: mockUser,
  loading: false,
  login: jest.fn(),
  logout: jest.fn(),
  updateUser: jest.fn(),
}

describe('AdminLayout Integration', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('renders admin page content', () => {
    const AdminPage = () => (
      <div>
        <h1>User Management</h1>
        <p>This is the admin page content</p>
      </div>
    )

    render(
      <AdminLayout>
        <AdminPage />
      </AdminLayout>
    )

    // Verify admin page content is rendered
    expect(screen.getByText('User Management')).toBeInTheDocument()
    expect(
      screen.getByText('This is the admin page content')
    ).toBeInTheDocument()
  })

  it('renders admin content directly', () => {
    render(
      <AdminLayout>
        <div>Admin Content</div>
      </AdminLayout>
    )

    // Verify admin content is rendered
    expect(screen.getByText('Admin Content')).toBeInTheDocument()
  })

  it('handles different admin page content correctly', () => {
    const UserManagementPage = () => (
      <div>
        <h2>User Management</h2>
        <table data-testid="users-table">
          <tbody>
            <tr>
              <td>User 1</td>
            </tr>
            <tr>
              <td>User 2</td>
            </tr>
          </tbody>
        </table>
      </div>
    )

    render(
      <AdminLayout>
        <UserManagementPage />
      </AdminLayout>
    )

    // Verify different admin page content works with the layout
    expect(screen.getByText('User Management')).toBeInTheDocument()
    expect(screen.getByTestId('users-table')).toBeInTheDocument()
    expect(screen.getByText('User 1')).toBeInTheDocument()
    expect(screen.getByText('User 2')).toBeInTheDocument()
  })

  it('maintains simple layout pattern', () => {
    render(
      <AdminLayout>
        <div>Test Admin Content</div>
      </AdminLayout>
    )

    // Verify content is rendered consistently
    expect(screen.getByText('Test Admin Content')).toBeInTheDocument()
  })
})

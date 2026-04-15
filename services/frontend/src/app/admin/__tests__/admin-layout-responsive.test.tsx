/**
 * @jest-environment jsdom
 */

import { render, screen } from '@testing-library/react'
import AdminLayout from '../layout'

// Simple test for responsive behavior
const mockUsePathname = jest.fn()
jest.mock('next/navigation', () => ({
  usePathname: mockUsePathname,
}))

describe('AdminLayout Responsive Behavior', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('renders admin users page', () => {
    mockUsePathname.mockReturnValue('/admin/users')

    render(
      <AdminLayout>
        <div>User Management Content</div>
      </AdminLayout>
    )

    // Admin content should be rendered
    expect(screen.getByText('User Management Content')).toBeInTheDocument()
  })

  it('renders admin feature flags page', () => {
    mockUsePathname.mockReturnValue('/admin/feature-flags')

    render(
      <AdminLayout>
        <div>Feature Flags Content</div>
      </AdminLayout>
    )

    // Admin content should be rendered
    expect(screen.getByText('Feature Flags Content')).toBeInTheDocument()
  })

  it('handles admin subroutes', () => {
    mockUsePathname.mockReturnValue('/admin/users/edit')

    render(
      <AdminLayout>
        <div>Edit User Management</div>
      </AdminLayout>
    )

    // Admin subroute content should be rendered
    expect(screen.getByText('Edit User Management')).toBeInTheDocument()
  })

  it('renders content for any route', () => {
    mockUsePathname.mockReturnValue('/login')

    render(
      <AdminLayout>
        <div>Login Content</div>
      </AdminLayout>
    )

    // Content should be rendered regardless of route
    expect(screen.getByText('Login Content')).toBeInTheDocument()
  })

  it('handles multiple admin routes', () => {
    // Test multiple admin routes
    const adminRoutes = [
      '/admin/users',
      '/admin/feature-flags',
      '/admin/annotations',
    ]

    adminRoutes.forEach((route) => {
      mockUsePathname.mockReturnValue(route)

      const { unmount } = render(
        <AdminLayout>
          <div>Content for {route}</div>
        </AdminLayout>
      )

      // Verify content is rendered for each admin route
      expect(screen.getByText(`Content for ${route}`)).toBeInTheDocument()
      unmount()
    })
  })
})

/**
 * @jest-environment jsdom
 *
 * Tests for the feature flags admin host route: superadmin guard first
 * (matching the other src/app/admin/* pages), then the platform console.
 */

import { render, screen } from '@testing-library/react'
import React from 'react'

jest.mock('@/components/admin/featureFlags/FeatureFlagsAdmin', () => ({
  FeatureFlagsAdmin: () => <div>flags console</div>,
}))

const mockUser: { current: { is_superadmin: boolean } | null } = {
  current: null,
}
jest.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({ user: mockUser.current }),
}))

import FeatureFlagsAdminPage from '../page'

beforeEach(() => {
  mockUser.current = { is_superadmin: true }
})

describe('Admin feature flags host route', () => {
  it('denies access to non-superadmins', () => {
    mockUser.current = { is_superadmin: false }
    render(<FeatureFlagsAdminPage />)
    // The global I18n test mock echoes unknown keys back.
    expect(screen.getByText('admin.accessDenied')).toBeInTheDocument()
    expect(screen.queryByText('flags console')).not.toBeInTheDocument()
  })

  it('denies access when signed out', () => {
    mockUser.current = null
    render(<FeatureFlagsAdminPage />)
    expect(screen.getByText('admin.accessDenied')).toBeInTheDocument()
  })

  it('renders the platform console for superadmins', () => {
    render(<FeatureFlagsAdminPage />)
    expect(screen.getByText('flags console')).toBeInTheDocument()
    expect(screen.queryByText('admin.accessDenied')).not.toBeInTheDocument()
  })
})

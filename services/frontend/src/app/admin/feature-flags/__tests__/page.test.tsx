/**
 * @jest-environment jsdom
 *
 * Tests for the feature flags admin host route: superadmin guard first
 * (matching the other src/app/admin/* pages), then the extended
 * 'FeatureFlagsAdmin' slot or the community "not available" message.
 */

import { render, screen } from '@testing-library/react'
import React from 'react'

const mockUseSlot = jest.fn()
jest.mock('@/lib/extensions/slots', () => ({
  useSlot: (name: string) => mockUseSlot(name),
}))

const mockUser: { current: { is_superadmin: boolean } | null } = {
  current: null,
}
jest.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({ user: mockUser.current }),
}))

import FeatureFlagsAdminPage from '../page'

beforeEach(() => {
  mockUseSlot.mockReset()
  mockUseSlot.mockReturnValue(null)
  mockUser.current = { is_superadmin: true }
})

describe('Admin feature flags host route', () => {
  it('denies access to non-superadmins', () => {
    mockUseSlot.mockReturnValue(() => <div>extended flags admin</div>)
    mockUser.current = { is_superadmin: false }
    render(<FeatureFlagsAdminPage />)
    // The global I18n test mock echoes unknown keys back.
    expect(screen.getByText('admin.accessDenied')).toBeInTheDocument()
    expect(screen.queryByText('extended flags admin')).not.toBeInTheDocument()
    expect(
      screen.queryByText('admin.featureFlagsNotAvailable'),
    ).not.toBeInTheDocument()
  })

  it('denies access when signed out', () => {
    mockUser.current = null
    render(<FeatureFlagsAdminPage />)
    expect(screen.getByText('admin.accessDenied')).toBeInTheDocument()
  })

  it('shows the not-available message when no slot is registered', () => {
    render(<FeatureFlagsAdminPage />)
    expect(mockUseSlot).toHaveBeenCalledWith('FeatureFlagsAdmin')
    expect(
      screen.getByText('admin.featureFlagsNotAvailable'),
    ).toBeInTheDocument()
    expect(screen.queryByText('admin.accessDenied')).not.toBeInTheDocument()
  })

  it('renders the registered FeatureFlagsAdmin slot for superadmins', () => {
    mockUseSlot.mockReturnValue(() => <div>extended flags admin</div>)
    render(<FeatureFlagsAdminPage />)
    expect(screen.getByText('extended flags admin')).toBeInTheDocument()
    expect(
      screen.queryByText('admin.featureFlagsNotAvailable'),
    ).not.toBeInTheDocument()
  })
})

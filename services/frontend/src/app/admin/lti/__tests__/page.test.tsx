/**
 * @jest-environment jsdom
 *
 * Tests for the LTI registrations admin host route: superadmin guard first
 * (matching the other src/app/admin/* pages), then the extended slot or the
 * community fallback.
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

import AdminLtiPage from '../page'

beforeEach(() => {
  mockUseSlot.mockReset()
  mockUseSlot.mockReturnValue(null)
  mockUser.current = { is_superadmin: true }
})

describe('Admin LTI host route', () => {
  it('denies access to non-superadmins', () => {
    mockUser.current = { is_superadmin: false }
    render(<AdminLtiPage />)
    // The global I18n test mock echoes unknown keys back.
    expect(screen.getByText('admin.accessDenied')).toBeInTheDocument()
    expect(
      screen.queryByText('LTI administration requires the extended edition.')
    ).not.toBeInTheDocument()
  })

  it('denies access when signed out', () => {
    mockUser.current = null
    render(<AdminLtiPage />)
    expect(screen.getByText('admin.accessDenied')).toBeInTheDocument()
  })

  it('renders the community fallback for superadmins without the extended package', () => {
    render(<AdminLtiPage />)
    expect(mockUseSlot).toHaveBeenCalledWith('LtiRegistrationsAdmin')
    expect(
      screen.getByText('LTI administration requires the extended edition.')
    ).toBeInTheDocument()
    expect(screen.queryByText('admin.accessDenied')).not.toBeInTheDocument()
  })

  it('renders the registered LtiRegistrationsAdmin slot for superadmins', () => {
    mockUseSlot.mockReturnValue(() => <div>extended lti admin</div>)
    render(<AdminLtiPage />)
    expect(screen.getByText('extended lti admin')).toBeInTheDocument()
    expect(
      screen.queryByText('LTI administration requires the extended edition.')
    ).not.toBeInTheDocument()
  })
})

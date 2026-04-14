/**
 * fn3 function coverage for AuthButton.tsx
 * Targets: handleClickOutside, org switching callbacks, superadmin feature flags link
 */

import React from 'react'
import { render, screen, fireEvent, act } from '@testing-library/react'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    locale: 'en',
    t: (key: string) => key,
    changeLocale: jest.fn(),
    isReady: true,
  }),
}))

jest.mock('@/contexts/HydrationContext', () => ({
  useHydration: () => true,
}))

jest.mock('@/contexts/FeatureFlagContext', () => ({
  useFeatureFlags: () => ({
    isEnabled: () => false,
  }),
}))

const mockLogout = jest.fn()
const mockSetCurrentOrganization = jest.fn()
jest.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({
    user: {
      id: 'user-1',
      username: 'testuser',
      is_superadmin: true,
    },
    logout: mockLogout,
    isLoading: false,
    currentOrganization: { id: 'org-1', name: 'Test Org' },
    organizations: [
      { id: 'org-1', name: 'Test Org' },
      { id: 'org-2', name: 'Other Org' },
    ],
    setCurrentOrganization: mockSetCurrentOrganization,
  }),
}))

// Mock modals
jest.mock('@/components/auth/LoginModal', () => ({
  LoginModal: () => null,
}))
jest.mock('@/components/auth/SignupModal', () => ({
  SignupModal: () => null,
}))

import { AuthButton } from '../AuthButton'

describe('AuthButton fn3', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('renders logged-in user dropdown toggle', () => {
    render(<AuthButton />)
    expect(screen.getByText('testuser')).toBeInTheDocument()
  })

  it('opens dropdown on click', () => {
    render(<AuthButton />)
    const toggle = screen.getByText('testuser').closest('button')!
    fireEvent.click(toggle)
    // Should now show dropdown items
    expect(screen.getByText('auth.profileSettings')).toBeInTheDocument()
  })

  it('switches to private context', () => {
    render(<AuthButton />)
    // Open dropdown
    fireEvent.click(screen.getByText('testuser').closest('button')!)
    // Click private option
    fireEvent.click(screen.getByText('auth.private'))
    expect(mockSetCurrentOrganization).toHaveBeenCalledWith(null)
  })

  it('switches organization', () => {
    render(<AuthButton />)
    fireEvent.click(screen.getByText('testuser').closest('button')!)
    fireEvent.click(screen.getByText('Other Org'))
    expect(mockSetCurrentOrganization).toHaveBeenCalledWith({ id: 'org-2', name: 'Other Org' })
  })

  it('shows feature flags link for superadmin', () => {
    render(<AuthButton />)
    fireEvent.click(screen.getByText('testuser').closest('button')!)
    expect(screen.getByText('admin.featureFlags')).toBeInTheDocument()
  })

  it('calls logout on sign out click', () => {
    render(<AuthButton />)
    fireEvent.click(screen.getByText('testuser').closest('button')!)
    fireEvent.click(screen.getByTestId('logout-button'))
    expect(mockLogout).toHaveBeenCalled()
  })

  it('closes dropdown when clicking outside', () => {
    render(
      <div>
        <AuthButton />
        <div data-testid="outside">Outside</div>
      </div>
    )
    // Open dropdown
    fireEvent.click(screen.getByText('testuser').closest('button')!)
    expect(screen.getByText('auth.profileSettings')).toBeInTheDocument()

    // Click outside
    fireEvent.mouseDown(screen.getByTestId('outside'))
    // Dropdown should close
    expect(screen.queryByText('auth.profileSettings')).not.toBeInTheDocument()
  })
})

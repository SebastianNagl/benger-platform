/**
 * Test suite for the Organizations Page redirect shell.
 *
 * The full organization-management UI moved to the unified admin interface at
 * `/admin/users-organizations` (see OrganizationsTab there). This route is now
 * a redirect-only shell, so these tests cover the redirect + route-level access
 * control only — the old render-body tests were removed along with the dead UI.
 */

/**
 * @jest-environment jsdom
 */

import { useToast } from '@/components/shared/Toast'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { render } from '@testing-library/react'
import { useRouter } from 'next/navigation'
import OrganizationsPage from '../page'

// Mock Next.js navigation
const mockPush = jest.fn()
jest.mock('next/navigation', () => ({
  useRouter: jest.fn(),
}))

// Mock contexts
jest.mock('@/contexts/AuthContext', () => ({
  useAuth: jest.fn(),
}))

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: jest.fn(),
}))

jest.mock('@/components/shared/Toast', () => ({
  useToast: jest.fn(),
}))

const mockSuperadminUser = {
  id: 'user-1',
  name: 'Admin User',
  email: 'admin@example.com',
  is_superadmin: true,
  is_active: true,
  created_at: '2024-01-01',
  updated_at: '2024-01-01',
}

const mockRegularUser = {
  id: 'user-2',
  name: 'Regular User',
  email: 'regular@example.com',
  is_superadmin: false,
  is_active: true,
  created_at: '2024-01-02',
  updated_at: '2024-01-02',
}

const mockAddToast = jest.fn()

const mockTranslations: Record<string, string> = {
  'admin.accessDeniedDesc': 'Access denied',
}

const mockT = (key: string) => mockTranslations[key] || key

describe('OrganizationsPage (redirect shell)', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    ;(useRouter as jest.Mock).mockReturnValue({ push: mockPush })
    ;(useAuth as jest.Mock).mockReturnValue({ user: mockSuperadminUser })
    ;(useI18n as jest.Mock).mockReturnValue({ t: mockT })
    ;(useToast as jest.Mock).mockReturnValue({ addToast: mockAddToast })
  })

  describe('Redirect', () => {
    it('redirects superadmins to the unified admin interface on mount', () => {
      render(<OrganizationsPage />)

      expect(mockPush).toHaveBeenCalledWith('/admin/users-organizations')
    })

    it('renders no UI (redirect-only shell)', () => {
      const { container } = render(<OrganizationsPage />)

      expect(container).toBeEmptyDOMElement()
    })
  })

  describe('Access Control', () => {
    it('redirects non-authenticated users to login', () => {
      ;(useAuth as jest.Mock).mockReturnValue({ user: null })

      render(<OrganizationsPage />)

      expect(mockPush).toHaveBeenCalledWith('/login')
      expect(mockPush).not.toHaveBeenCalledWith('/admin/users-organizations')
    })

    it('redirects non-superadmin users to dashboard with an access-denied toast', () => {
      ;(useAuth as jest.Mock).mockReturnValue({ user: mockRegularUser })

      render(<OrganizationsPage />)

      expect(mockAddToast).toHaveBeenCalledWith('Access denied', 'error')
      expect(mockPush).toHaveBeenCalledWith('/dashboard')
      expect(mockPush).not.toHaveBeenCalledWith('/admin/users-organizations')
    })

    it('allows superadmins through to the unified interface only', () => {
      ;(useAuth as jest.Mock).mockReturnValue({ user: mockSuperadminUser })

      render(<OrganizationsPage />)

      expect(mockPush).toHaveBeenCalledWith('/admin/users-organizations')
      expect(mockPush).not.toHaveBeenCalledWith('/login')
      expect(mockPush).not.toHaveBeenCalledWith('/dashboard')
    })
  })
})

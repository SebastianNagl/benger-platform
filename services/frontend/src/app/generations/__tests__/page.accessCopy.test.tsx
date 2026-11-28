/**
 * The generations page's access-denied state shows translated copy from the real
 * catalogs: the keys it once used (dataManagement.accessDenied*) existed in
 * no catalog, so users saw the raw key.
 *
 * @jest-environment jsdom
 */

import { render, screen } from '@testing-library/react'
import GenerationPage from '../page'

let mockLocale: 'en' | 'de' = 'en'
jest.mock('@/contexts/I18nContext', () =>
  require('@/test-utils/i18nMock').i18nMock(() => mockLocale),
)
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: jest.fn(), replace: jest.fn() }),
  useSearchParams: () => new URLSearchParams(),
}))
jest.mock('@/lib/api/projects', () => ({
  projectsAPI: { list: jest.fn().mockResolvedValue({ items: [] }) },
}))
jest.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 'u1', is_superadmin: false },
    isLoading: false,
    organizations: [],
  }),
}))
jest.mock('@/utils/permissions', () => ({
  canAccessProjectData: () => false,
}))
jest.mock('@/components/generation/GenerationTaskList', () => ({
  GenerationTaskList: () => null,
}))

describe('GenerationPage access denied', () => {
  it.each([
    [
      'en',
      'Access Denied',
      'Only superadmins, organization admins, and contributors can access project data',
    ],
    [
      'de',
      'Zugriff verweigert',
      'Nur Superadmins, Organisationsadministratoren und Mitwirkende können auf Projektdaten zugreifen',
    ],
  ] as const)('shows the %s copy', (locale, title, description) => {
    mockLocale = locale
    render(<GenerationPage />)
    expect(screen.getByText(title)).toBeInTheDocument()
    expect(screen.getByText(description)).toBeInTheDocument()
  })
})

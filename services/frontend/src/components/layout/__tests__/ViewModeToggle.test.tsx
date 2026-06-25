/**
 * @jest-environment jsdom
 *
 * Tests for the student⇄expert view-mode toggle (Issue #35, platform shell).
 *
 * The toggle is a pure gate: it renders nothing in the community edition or for
 * users without expert-view capability, and only appears for capable users in
 * the extended edition. Switching persists server-side via the API client.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import React from 'react'

const EDITION_KEY = 'NEXT_PUBLIC_BENGER_EDITION'
const originalEdition = process.env[EDITION_KEY]

// --- Mocks -----------------------------------------------------------------

const mockSetUiMode = jest.fn()
const mockUpdateUser = jest.fn()
let mockResolved: 'student' | 'expert' = 'student'
let mockHydrated = true
let mockAuth: any = {
  user: { id: 'u1', is_superadmin: true },
  organizations: [],
  isLoading: false,
  updateUser: mockUpdateUser,
}

const mockPush = jest.fn()
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
}))

jest.mock('@/stores', () => ({
  useUIStore: (selector: any) => selector({ setUiMode: mockSetUiMode }),
}))

jest.mock('@/contexts/AuthContext', () => ({
  useAuth: () => mockAuth,
}))

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({ t: (k: string) => k }),
}))

jest.mock('@/contexts/HydrationContext', () => ({
  useHydration: () => mockHydrated,
}))

// Hoist-safe shared mock for the API client's setUiMode. The jest.mock
// factories run before top-level consts initialize, so the fn is created
// inside the factory and re-grabbed in the test body.
jest.mock('@/contexts/ApiClientContext', () => {
  const fn = jest.fn().mockResolvedValue({ preferred_ui_mode: 'expert' })
  return {
    __esModule: true,
    useOptionalApiClient: () => ({ setUiMode: fn }),
    __mockApiSetUiMode: fn,
  }
})

jest.mock('@/lib/api', () => ({
  __esModule: true,
  default: { setUiMode: jest.fn().mockResolvedValue({ preferred_ui_mode: 'expert' }) },
}))

const mockApiSetUiMode = (require('@/contexts/ApiClientContext') as any)
  .__mockApiSetUiMode as jest.Mock

jest.mock('@/lib/utils/subdomain', () => ({
  parseSubdomain: () => ({ isPrivateMode: true, orgSlug: null }),
}))

jest.mock('@/hooks/useResolvedUiMode', () => ({
  isExtendedEdition: () => process.env.NEXT_PUBLIC_BENGER_EDITION === 'extended',
  useResolvedUiMode: () => mockResolved,
}))

import { ViewModeToggle } from '../ViewModeToggle'

describe('ViewModeToggle', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockResolved = 'student'
    mockHydrated = true
    mockAuth = {
      user: { id: 'u1', is_superadmin: true },
      organizations: [],
      isLoading: false,
      updateUser: mockUpdateUser,
    }
  })

  afterEach(() => {
    if (originalEdition === undefined) delete process.env[EDITION_KEY]
    else process.env[EDITION_KEY] = originalEdition
  })

  it('renders nothing in the community edition', () => {
    delete process.env[EDITION_KEY]
    const { container } = render(<ViewModeToggle />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders nothing when the user lacks expert-view capability', () => {
    process.env[EDITION_KEY] = 'extended'
    // Non-superadmin, no qualifying org membership → canUseExpertView=false.
    mockAuth = {
      user: { id: 'u2', is_superadmin: false },
      organizations: [],
      isLoading: false,
      updateUser: mockUpdateUser,
    }
    const { container } = render(<ViewModeToggle />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders a neutral skeleton while auth is loading (no role flicker)', () => {
    process.env[EDITION_KEY] = 'extended'
    mockAuth = { ...mockAuth, isLoading: true }
    render(<ViewModeToggle />)
    expect(screen.getByTestId('view-mode-toggle-skeleton')).toBeInTheDocument()
    expect(screen.queryByTestId('view-mode-toggle')).not.toBeInTheDocument()
  })

  it('renders the dropdown trigger for a capable user in the extended edition', () => {
    process.env[EDITION_KEY] = 'extended'
    render(<ViewModeToggle />)
    expect(screen.getByTestId('view-mode-toggle')).toBeInTheDocument()
  })

  it('opening the dropdown does NOT switch — only selecting an option does', async () => {
    process.env[EDITION_KEY] = 'extended'
    mockResolved = 'student'
    render(<ViewModeToggle />)
    fireEvent.click(screen.getByTestId('view-mode-toggle')) // open menu
    expect(mockSetUiMode).not.toHaveBeenCalled()

    // Select the expert option.
    const expertOption = await screen.findByText('student.view.expert')
    fireEvent.click(expertOption)
    // Local optimistic switch happens immediately.
    expect(mockSetUiMode).toHaveBeenCalledWith('expert')
    // Navigates to the classic dashboard so the expert interface renders
    // (staying on /student would keep showing the student dashboard).
    expect(mockPush).toHaveBeenCalledWith('/dashboard')
    // Server persistence + in-memory user sync.
    await waitFor(() => expect(mockApiSetUiMode).toHaveBeenCalledWith('expert'))
    expect(mockUpdateUser).toHaveBeenCalledWith({ preferred_ui_mode: 'expert' })
  })

  it('shows both modes; selecting the already-active mode is a no-op', async () => {
    process.env[EDITION_KEY] = 'extended'
    mockResolved = 'student'
    render(<ViewModeToggle />)
    fireEvent.click(screen.getByTestId('view-mode-toggle'))
    // Both option buttons are offered in the menu (queried by their data attr
    // so the trigger's current-mode label doesn't collide on text).
    await waitFor(() =>
      expect(
        document.querySelector('[data-ui-mode-option="expert"]')
      ).toBeInTheDocument()
    )
    const studentOption = document.querySelector(
      '[data-ui-mode-option="student"]'
    ) as HTMLElement
    expect(studentOption).toBeInTheDocument()
    // Re-selecting the current (student) mode does nothing.
    fireEvent.click(studentOption)
    expect(mockSetUiMode).not.toHaveBeenCalled()
    expect(mockApiSetUiMode).not.toHaveBeenCalled()
  })
})

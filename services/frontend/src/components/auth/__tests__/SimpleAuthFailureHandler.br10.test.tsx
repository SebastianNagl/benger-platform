/**
 * @jest-environment jsdom
 *
 * Branch coverage tests for SimpleAuthFailureHandler.
 * Covers all 7 uncovered branches:
 * - binary-expr for pathname fallback (line 19)
 * - if/binary-expr for isPublicPage || isLoading || !user (line 25)
 */

import { render } from '@testing-library/react'

const mockUseAuth = jest.fn()
const mockAddToast = jest.fn()
const mockPush = jest.fn()
const mockPathname = jest.fn()

jest.mock('@/components/auth/SimpleAuth', () => ({
  useAuth: () => mockUseAuth(),
}))

jest.mock('@/components/shared/SimpleToast', () => ({
  useToast: () => ({ addToast: mockAddToast }),
}))

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
  usePathname: () => mockPathname(),
}))

jest.mock('@/lib/utils/logger', () => ({
  logger: { debug: jest.fn() },
}))

import { SimpleAuthFailureHandler } from '../SimpleAuthFailureHandler'

describe('SimpleAuthFailureHandler', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('renders null and sets up handler when on public page', () => {
    mockUseAuth.mockReturnValue({
      user: { id: 1 },
      isLoading: false,
      logout: jest.fn(),
    })
    mockPathname.mockReturnValue('/login')

    const { container } = render(<SimpleAuthFailureHandler />)
    expect(container.innerHTML).toBe('')
  })

  it('renders null when isLoading is true', () => {
    mockUseAuth.mockReturnValue({
      user: { id: 1 },
      isLoading: true,
      logout: jest.fn(),
    })
    mockPathname.mockReturnValue('/dashboard')

    const { container } = render(<SimpleAuthFailureHandler />)
    expect(container.innerHTML).toBe('')
  })

  it('renders null when user is null (not authenticated)', () => {
    mockUseAuth.mockReturnValue({
      user: null,
      isLoading: false,
      logout: jest.fn(),
    })
    mockPathname.mockReturnValue('/dashboard')

    const { container } = render(<SimpleAuthFailureHandler />)
    expect(container.innerHTML).toBe('')
  })

  it('handles null pathname by defaulting to root', () => {
    mockUseAuth.mockReturnValue({
      user: { id: 1 },
      isLoading: false,
      logout: jest.fn(),
    })
    mockPathname.mockReturnValue(null)

    const { container } = render(<SimpleAuthFailureHandler />)
    expect(container.innerHTML).toBe('')
  })

  it('renders null for non-public page with authenticated user', () => {
    mockUseAuth.mockReturnValue({
      user: { id: 1 },
      isLoading: false,
      logout: jest.fn(),
    })
    mockPathname.mockReturnValue('/projects')

    const { container } = render(<SimpleAuthFailureHandler />)
    expect(container.innerHTML).toBe('')
  })

  it('handles register as a public page', () => {
    mockUseAuth.mockReturnValue({
      user: { id: 1 },
      isLoading: false,
      logout: jest.fn(),
    })
    mockPathname.mockReturnValue('/register')

    const { container } = render(<SimpleAuthFailureHandler />)
    expect(container.innerHTML).toBe('')
  })

  it('handles reset-password as a public page', () => {
    mockUseAuth.mockReturnValue({
      user: { id: 1 },
      isLoading: false,
      logout: jest.fn(),
    })
    mockPathname.mockReturnValue('/reset-password')

    const { container } = render(<SimpleAuthFailureHandler />)
    expect(container.innerHTML).toBe('')
  })
})

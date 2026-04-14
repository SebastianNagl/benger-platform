/**
 * Additional coverage for SimpleAuthFailureHandler
 */

import { render } from '@testing-library/react'
import { SimpleAuthFailureHandler } from '../SimpleAuthFailureHandler'

jest.mock('@/components/auth/SimpleAuth', () => ({
  useAuth: () => ({
    user: { id: '1', username: 'test' },
    isLoading: false,
    logout: jest.fn().mockResolvedValue(undefined),
  }),
}))

const mockDebug = jest.fn()
jest.mock('@/lib/utils/logger', () => ({
  logger: {
    debug: (...args: any[]) => mockDebug(...args),
  },
}))

jest.mock('@/components/shared/SimpleToast', () => ({
  useToast: () => ({
    addToast: jest.fn(),
  }),
}))

jest.mock('next/navigation', () => ({
  useRouter: () => ({
    push: jest.fn(),
  }),
  usePathname: () => '/dashboard',
}))

describe('SimpleAuthFailureHandler', () => {
  beforeEach(() => {
    mockDebug.mockClear()
  })

  it('renders null (no visible UI)', () => {
    const { container } = render(<SimpleAuthFailureHandler />)
    expect(container.innerHTML).toBe('')
  })

  it('logs ready message', () => {
    render(<SimpleAuthFailureHandler />)
    expect(mockDebug).toHaveBeenCalledWith('SimpleAuthFailureHandler ready')
  })
})

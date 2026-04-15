import React from 'react'
import { render, act } from '@testing-library/react'

jest.mock('next/navigation', () => ({
  usePathname: () => '/dashboard',
}))
jest.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({ isLoading: true, user: null }),
}))
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({ t: (k: string) => k }),
}))
jest.mock('@/components/auth/ProtectedRoute', () => ({
  ProtectedRoute: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))
jest.mock('@/components/layout/Layout', () => ({
  Layout: ({ children }: { children: React.ReactNode }) => <div data-testid="layout">{children}</div>,
}))
jest.mock('@/components/layout/MinimalLayout', () => ({
  MinimalLayout: ({ children }: { children: React.ReactNode }) => <div data-testid="minimal">{children}</div>,
}))

describe('ConditionalLayout loading delay', () => {
  beforeEach(() => jest.useFakeTimers())
  afterEach(() => jest.useRealTimers())

  it('triggers loading delay setTimeout callback after 200ms', () => {
    const { ConditionalLayout } = require('../ConditionalLayout')
    render(
      <ConditionalLayout allSections={{}}>
        <div>content</div>
      </ConditionalLayout>
    )
    // Advance past the 200ms setTimeout to trigger the anonymous callback on line 31
    act(() => { jest.advanceTimersByTime(250) })
  })
})

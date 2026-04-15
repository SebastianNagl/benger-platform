/**
 * @jest-environment jsdom
 */

import { render, screen } from '@testing-library/react'
import { Providers } from '../providers'

// Mock all provider dependencies
jest.mock('@/components/auth/SessionValidator', () => ({
  SessionValidator: () => null,
}))

jest.mock('@/components/shared/GlobalErrorBoundary', () => ({
  GlobalErrorBoundary: ({ children }: any) => <>{children}</>,
}))

jest.mock('@/components/shared/Toast', () => ({
  ToastProvider: ({ children }: any) => <>{children}</>,
}))

jest.mock('@/contexts/AuthContext', () => ({
  AuthProvider: ({ children }: any) => <>{children}</>,
}))

jest.mock('@/contexts/FeatureFlagContext', () => ({
  FeatureFlagProvider: ({ children }: any) => <>{children}</>,
}))

jest.mock('@/contexts/HydrationContext', () => ({
  HydrationProvider: ({ children }: any) => <>{children}</>,
}))

jest.mock('@/contexts/I18nContext', () => ({
  I18nProvider: ({ children }: any) => <>{children}</>,
}))

jest.mock('@/contexts/ProgressContext', () => ({
  ProgressProvider: ({ children }: any) => <>{children}</>,
}))

jest.mock('@/hooks/useDialogs', () => ({
  DialogProvider: ({ children }: any) => <>{children}</>,
}))

jest.mock('next-themes', () => ({
  ThemeProvider: ({ children }: any) => <>{children}</>,
}))

describe('Providers', () => {
  it('should render children', () => {
    render(
      <Providers>
        <div data-testid="child">Hello</div>
      </Providers>
    )

    expect(screen.getByTestId('child')).toBeInTheDocument()
    expect(screen.getByText('Hello')).toBeInTheDocument()
  })
})

/**
 * @jest-environment jsdom
 *
 * Host-aware branding on the verify-email ("check your inbox") page: on a
 * student-locked host (vertretbar.net) the header must show the Vertretbar
 * mark + name, never the BenGER wordmark. Separate file from page.test.tsx
 * because the subdomain mock is module-scoped and the main suite asserts the
 * default (BenGER) brand.
 */

import { render, screen } from '@testing-library/react'
import React from 'react'

jest.mock('@/lib/utils/subdomain', () => ({
  getHostBrandName: jest.fn(() => 'Vertretbar'),
  isStudentLockedHost: jest.fn(() => true),
}))

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({ t: (key: string) => key }),
}))

const mockPush = jest.fn()
const mockSearchParams = new URLSearchParams({ messageKey: 'registrationSuccess' })
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush, replace: jest.fn() }),
  useSearchParams: () => mockSearchParams,
}))

jest.mock('next/link', () => {
  return function MockLink({
    children,
    href,
  }: {
    children: React.ReactNode
    href: string
  }) {
    return <a href={href}>{children}</a>
  }
})

jest.mock('@/components/layout', () => ({
  LanguageSwitcher: () => <div data-testid="language-switcher" />,
  ThemeToggle: () => <div data-testid="theme-toggle" />,
}))

jest.mock('@/components/shared/Button', () => ({
  Button: ({ children }: { children: React.ReactNode }) => (
    <button>{children}</button>
  ),
}))

import VerifyEmailPage from '../page'

describe('verify-email page — vertretbar branding', () => {
  it('shows the Vertretbar wordmark on a student-locked host', () => {
    render(<VerifyEmailPage />)
    expect(screen.getAllByText('Vertretbar').length).toBeGreaterThan(0)
    expect(screen.queryByText('BenGER')).toBeNull()
  })
})

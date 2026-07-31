/**
 * @jest-environment jsdom
 *
 * Host-aware branding on the reset-password request page: on a
 * student-locked host (vertretbar.net) the header must show the Vertretbar
 * mark + name, never the BenGER wordmark. Separate file because the
 * subdomain mock is module-scoped and the main suite asserts the default.
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

import ResetPasswordPage from '../page'

describe('reset-password page — vertretbar branding', () => {
  it('shows the Vertretbar wordmark on a student-locked host', () => {
    render(<ResetPasswordPage />)
    expect(screen.getAllByText('Vertretbar').length).toBeGreaterThan(0)
    expect(screen.queryByText('BenGER')).toBeNull()
  })
})

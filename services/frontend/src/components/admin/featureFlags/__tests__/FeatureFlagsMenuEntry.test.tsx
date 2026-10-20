/**
 * @jest-environment jsdom
 *
 * FeatureFlagsMenuEntry: the account dropdown's link to
 * /admin/feature-flags, for superadmins only.
 */
import '@testing-library/jest-dom'
import { fireEvent, render, screen } from '@testing-library/react'

import { FeatureFlagsMenuEntry } from '../FeatureFlagsMenuEntry'

let mockUser: { is_superadmin?: boolean } | null = null
jest.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({ user: mockUser }),
}))
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({ t: (key: string) => key, locale: 'de' }),
}))

it('renders nothing for a regular user or when signed out', () => {
  mockUser = { is_superadmin: false }
  const { container, rerender } = render(<FeatureFlagsMenuEntry />)
  expect(container).toBeEmptyDOMElement()
  mockUser = null
  rerender(<FeatureFlagsMenuEntry />)
  expect(container).toBeEmptyDOMElement()
})

it('links superadmins to the console and reports navigation', () => {
  mockUser = { is_superadmin: true }
  const onNavigate = jest.fn()
  render(<FeatureFlagsMenuEntry onNavigate={onNavigate} />)
  const link = screen.getByTestId('auth-menu-feature-flags')
  expect(link).toHaveAttribute('href', '/admin/feature-flags')
  expect(link).toHaveTextContent('admin.featureFlagsConsole.menu')
  fireEvent.click(link)
  expect(onNavigate).toHaveBeenCalled()
})

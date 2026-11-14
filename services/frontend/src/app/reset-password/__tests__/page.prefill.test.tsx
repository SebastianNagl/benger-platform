/**
 * @jest-environment jsdom
 *
 * The register page sends someone whose address is already taken here with
 * that address, so the reset request is one click away.
 */

import ResetPasswordPage from '@/app/reset-password/page'
import { render, screen } from '@testing-library/react'

jest.mock('next/navigation', () => ({
  useSearchParams: () => new URLSearchParams('email=taken%40example.org'),
}))
jest.mock('@/components/layout', () => ({
  LanguageSwitcher: () => <div />,
  ThemeToggle: () => <div />,
}))

describe('Reset Password Page prefill', () => {
  it('starts with the address passed in the link', () => {
    render(<ResetPasswordPage />)

    expect(screen.getByRole('textbox')).toHaveValue('taken@example.org')
  })
})

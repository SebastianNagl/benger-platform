/**
 * Coverage for layout files with 0% coverage:
 * - reset-password/layout.tsx
 * - reset-password/[token]/layout.tsx
 * - verify-email/layout.tsx
 */

import { render, screen } from '@testing-library/react'
import React from 'react'

import ResetPasswordLayout from '../reset-password/layout'
import ResetPasswordTokenLayout from '../reset-password/[token]/layout'
import VerifyEmailLayout from '../verify-email/layout'

describe('ResetPasswordLayout', () => {
  it('renders children inside Suspense', () => {
    render(
      <ResetPasswordLayout>
        <div data-testid="child">Content</div>
      </ResetPasswordLayout>
    )
    expect(screen.getByTestId('child')).toBeInTheDocument()
  })
})

describe('ResetPasswordTokenLayout', () => {
  it('renders children inside Suspense', () => {
    render(
      <ResetPasswordTokenLayout>
        <div data-testid="child">Token Content</div>
      </ResetPasswordTokenLayout>
    )
    expect(screen.getByTestId('child')).toBeInTheDocument()
  })
})

describe('VerifyEmailLayout', () => {
  it('renders children inside Suspense', () => {
    render(
      <VerifyEmailLayout>
        <div data-testid="child">Verify Content</div>
      </VerifyEmailLayout>
    )
    expect(screen.getByTestId('child')).toBeInTheDocument()
  })
})

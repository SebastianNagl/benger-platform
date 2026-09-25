/**
 * @jest-environment jsdom
 *
 * app/lti/layout.tsx: the LMS launch steps before a session (consent,
 * account choice, link confirmation, launch errors) get the login page's
 * frame with the host's wordmark; the picker and the activity overview run
 * in the app layout and pass through unchanged.
 */

import { render, screen } from '@testing-library/react'
import React from 'react'

import LtiLayout from '../layout'

const mockPath = { current: '/lti/consent' }
jest.mock('next/navigation', () => ({
  usePathname: () => mockPath.current,
}))

jest.mock('@/components/layout/AuthPageFrame', () => ({
  AuthPageFrame: ({
    children,
    showBackLink,
  }: {
    children: React.ReactNode
    showBackLink?: boolean
  }) => (
    <div data-testid="auth-frame" data-back={String(showBackLink)}>
      {children}
    </div>
  ),
}))

describe('LtiLayout', () => {
  it.each([
    '/lti/consent',
    '/lti/link-account',
    '/lti/link-confirm/tok-1',
    '/lti/error',
  ])('frames the pre-session route %s', (path) => {
    mockPath.current = path
    render(
      <LtiLayout>
        <p>step</p>
      </LtiLayout>,
    )
    const frame = screen.getByTestId('auth-frame')
    expect(frame).toHaveTextContent('step')
    // A launch has no start page to go back to.
    expect(frame).toHaveAttribute('data-back', 'false')
  })

  it.each(['/lti/link', '/lti/activity', '/lti/errors-elsewhere'])(
    'leaves %s to the app layout',
    (path) => {
      mockPath.current = path
      render(
        <LtiLayout>
          <p>page</p>
        </LtiLayout>,
      )
      expect(screen.queryByTestId('auth-frame')).not.toBeInTheDocument()
      expect(screen.getByText('page')).toBeInTheDocument()
    },
  )
})

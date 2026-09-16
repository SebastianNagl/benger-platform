/**
 * @jest-environment jsdom
 *
 * Tests for the LTI host routes (link picker, launch error).
 *
 * The link host is a thin slot dispatcher: without the extended package it
 * must render a graceful community fallback and never crash. The error host
 * differs: its fallback is a working feature that translates ?code= into a
 * human-readable message, because launches can fail on a community install
 * too. The public consent and account-linking hosts are covered in
 * lti-public-pages.test.tsx.
 */

import { render, screen } from '@testing-library/react'
import React from 'react'

const mockUseSlot = jest.fn()
jest.mock('@/lib/extensions/slots', () => ({
  useSlot: (name: string) => mockUseSlot(name),
}))

const mockSearchParams = { current: new URLSearchParams() }
jest.mock('next/navigation', () => ({
  useSearchParams: () => mockSearchParams.current,
}))

import { LTI_LAUNCH_ERROR_CODES } from '@/lib/lti/launchErrors'

import LtiErrorPage from '../error/page'
import LtiLinkPage from '../link/page'

beforeEach(() => {
  mockUseSlot.mockReset()
  mockUseSlot.mockReturnValue(null)
  mockSearchParams.current = new URLSearchParams()
})

describe('LTI link host route', () => {
  it('renders the community fallback when no slot is registered', () => {
    render(<LtiLinkPage />)
    expect(mockUseSlot).toHaveBeenCalledWith('LtiLinkPicker')
    expect(
      screen.getByText('LTI content linking requires the extended edition.'),
    ).toBeInTheDocument()
  })

  it('renders the registered LtiLinkPicker slot', () => {
    mockUseSlot.mockReturnValue(() => <div>extended link picker</div>)
    render(<LtiLinkPage />)
    expect(screen.getByText('extended link picker')).toBeInTheDocument()
    expect(
      screen.queryByText('LTI content linking requires the extended edition.'),
    ).not.toBeInTheDocument()
  })
})

describe('LTI error host route', () => {
  const DEFAULT_MESSAGE =
    'The launch could not be completed. Go back to your learning platform and click the activity again; if the problem persists, contact your instructor.'

  it('requests the LtiLaunchError slot and prefers it when registered', () => {
    mockUseSlot.mockReturnValue(() => <div>extended error view</div>)
    render(<LtiErrorPage />)
    expect(mockUseSlot).toHaveBeenCalledWith('LtiLaunchError')
    expect(screen.getByText('extended error view')).toBeInTheDocument()
    expect(screen.queryByText('Launch failed')).not.toBeInTheDocument()
  })

  it('explains not_linked in instructor terms', () => {
    mockSearchParams.current = new URLSearchParams('code=not_linked')
    render(<LtiErrorPage />)
    expect(screen.getByText('Launch failed')).toBeInTheDocument()
    expect(
      screen.getByText(
        'Your instructor has not connected this activity to an exam yet.',
      ),
    ).toBeInTheDocument()
    expect(screen.getByText('Error code: not_linked')).toBeInTheDocument()
  })

  it.each(['invalid_state', 'nonce_reused'])(
    'tells the user to relaunch from the learning platform for %s',
    (code) => {
      mockSearchParams.current = new URLSearchParams(`code=${code}`)
      render(<LtiErrorPage />)
      expect(
        screen.getByText(
          'This launch link has expired or was already used. Go back to your learning platform and click the activity again.',
        ),
      ).toBeInTheDocument()
      expect(screen.getByText(`Error code: ${code}`)).toBeInTheDocument()
    },
  )

  it.each([...LTI_LAUNCH_ERROR_CODES])(
    'has a dedicated human-readable message for %s',
    (code) => {
      mockSearchParams.current = new URLSearchParams(`code=${code}`)
      render(<LtiErrorPage />)
      expect(screen.getByText('Launch failed')).toBeInTheDocument()
      // Every documented code maps to its own copy, not the generic fallback.
      expect(screen.queryByText(DEFAULT_MESSAGE)).not.toBeInTheDocument()
      expect(screen.getByText(`Error code: ${code}`)).toBeInTheDocument()
    },
  )

  it('does not blame cookies for a temporary server problem', () => {
    mockSearchParams.current = new URLSearchParams('code=state_unavailable')
    render(<LtiErrorPage />)
    expect(screen.getByText(/not caused by your browser/)).toBeInTheDocument()
    expect(screen.queryByText(/cookie/i)).not.toBeInTheDocument()
  })

  it('falls back to generic retry advice for unknown codes', () => {
    mockSearchParams.current = new URLSearchParams('code=some_future_code')
    render(<LtiErrorPage />)
    expect(screen.getByText(DEFAULT_MESSAGE)).toBeInTheDocument()
    expect(screen.getByText('Error code: some_future_code')).toBeInTheDocument()
  })

  it('renders the generic message and no code line when ?code= is absent', () => {
    render(<LtiErrorPage />)
    expect(screen.getByText(DEFAULT_MESSAGE)).toBeInTheDocument()
    expect(screen.queryByText(/Error code:/)).not.toBeInTheDocument()
  })
})

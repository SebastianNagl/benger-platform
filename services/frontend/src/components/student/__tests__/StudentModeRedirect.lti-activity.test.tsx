/**
 * @jest-environment jsdom
 *
 * StudentModeRedirect on the teacher activity view (/lti/activity), the
 * landing of a bound instructor launch. Like the link picker (/lti/link) it
 * is never bounced in either mode; the one-shot `lti_ui` picks the shell:
 * expert on the main host, student on a student host. Runs against the
 * real UI store, slot registry and UI mode resolution; only routing, auth
 * and the host check are stubbed (same setup as StudentModeRedirect.test).
 */

import { registerSlot } from '@/lib/extensions/slots'
import { useUIStore } from '@/stores'
import { render, waitFor } from '@testing-library/react'
import React from 'react'

const EDITION_KEY = 'NEXT_PUBLIC_BENGER_EDITION'
const originalEdition = process.env[EDITION_KEY]

const mockReplace = jest.fn()
let mockPathname = '/'
let mockAuth: {
  user: { id: string; preferred_ui_mode?: 'student' | 'expert' | null } | null
  isLoading: boolean
} = { user: null, isLoading: false }
let mockLockedHost = false

jest.mock('next/navigation', () => ({
  usePathname: () => mockPathname,
  useRouter: () => ({ replace: mockReplace, push: jest.fn() }),
}))
jest.mock('@/contexts/AuthContext', () => ({ useAuth: () => mockAuth }))
jest.mock('@/lib/utils/subdomain', () => ({
  ...jest.requireActual('@/lib/utils/subdomain'),
  isStudentLockedHost: () => mockLockedHost,
}))

import { StudentModeRedirect } from '../StudentModeRedirect'

registerSlot('StudentShell', () => null)

function visit(url: string) {
  window.history.replaceState(null, '', url)
  mockPathname = url.split('?')[0]
}

function signIn(preferred: 'student' | 'expert' | null) {
  mockAuth = {
    user: { id: 'u1', preferred_ui_mode: preferred },
    isLoading: false,
  }
}

beforeEach(() => {
  jest.clearAllMocks()
  process.env[EDITION_KEY] = 'extended'
  mockLockedHost = false
  mockAuth = { user: null, isLoading: false }
  useUIStore.setState({ uiMode: null, isHydrated: true })
  visit('/')
})

afterAll(() => {
  if (originalEdition === undefined) delete process.env[EDITION_KEY]
  else process.env[EDITION_KEY] = originalEdition
})

describe('StudentModeRedirect on /lti/activity', () => {
  it('puts an LMS teacher into the expert shell on the main host', async () => {
    // LMS accounts are saved with the student preference.
    signIn('student')
    visit('/lti/activity?rl=rl-1&lti_u=u1&lti_ui=expert')
    render(<StudentModeRedirect />)

    await waitFor(() => expect(useUIStore.getState().uiMode).toBe('expert'))
    expect(mockReplace).not.toHaveBeenCalled()
    expect(window.location.pathname).toBe('/lti/activity')
    expect(window.location.search).toBe('?rl=rl-1&lti_u=u1')
  })

  it('keeps the student shell on a student host without a bounce', async () => {
    mockLockedHost = true
    signIn('expert')
    useUIStore.setState({ uiMode: 'expert' })
    visit('/lti/activity?rl=rl-2&lti_u=u1&lti_ui=student')
    render(<StudentModeRedirect />)

    await waitFor(() => expect(useUIStore.getState().uiMode).toBe('student'))
    expect(mockReplace).not.toHaveBeenCalled()
    expect(window.location.search).toBe('?rl=rl-2&lti_u=u1')
  })

  it('ignores an expert request on a student host but still strips it', async () => {
    mockLockedHost = true
    signIn('student')
    visit('/lti/activity?rl=rl-3&lti_u=u1&lti_ui=expert')
    render(<StudentModeRedirect />)

    await waitFor(() =>
      expect(window.location.search).toBe('?rl=rl-3&lti_u=u1'),
    )
    expect(useUIStore.getState().uiMode).not.toBe('expert')
    expect(mockReplace).not.toHaveBeenCalled()
  })

  it('never bounces the activity view in either mode', async () => {
    for (const mode of ['student', 'expert'] as const) {
      mockReplace.mockClear()
      signIn(mode)
      useUIStore.setState({ uiMode: mode })
      visit('/lti/activity?rl=rl-4&lti_u=u1')
      render(<StudentModeRedirect />)
      await waitFor(() => expect(useUIStore.getState().uiMode).toBe(mode))
      expect(mockReplace).not.toHaveBeenCalled()
    }
  })
})

/**
 * @jest-environment jsdom
 *
 * Behavior tests for StudentModeRedirect: the mode-based bounces and the
 * one-shot `lti_ui` param an LMS launch appends next to `lti_u`/`rl`.
 * Runs against the real UI store, slot registry and UI mode resolution;
 * only routing, auth and the host check are stubbed.
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

/** Put the browser on `url` (path + query) and the router on its path. */
function visit(url: string) {
  window.history.replaceState(null, '', url)
  mockPathname = url.split('?')[0]
}

function signIn(preferred: 'student' | 'expert' | null = null) {
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

describe('StudentModeRedirect', () => {
  describe('mode bounces', () => {
    it('pulls student-mode users from the dashboard into /student', async () => {
      signIn('student')
      visit('/dashboard')
      render(<StudentModeRedirect />)
      await waitFor(() => expect(mockReplace).toHaveBeenCalledWith('/student'))
    })

    it('bounces expert-mode users off the student surface', async () => {
      signIn('expert')
      visit('/student/exams/p1')
      render(<StudentModeRedirect />)
      await waitFor(() =>
        expect(mockReplace).toHaveBeenCalledWith('/dashboard'),
      )
    })

    it('leaves logged-out visitors alone', () => {
      visit('/student/exams/p1')
      render(<StudentModeRedirect />)
      expect(mockReplace).not.toHaveBeenCalled()
    })

    it('waits for auth to settle', () => {
      mockAuth = {
        user: { id: 'u1', preferred_ui_mode: 'expert' },
        isLoading: true,
      }
      visit('/student/exams/p1')
      render(<StudentModeRedirect />)
      expect(mockReplace).not.toHaveBeenCalled()
    })
  })

  describe('one-shot lti_ui from an LMS launch', () => {
    it('keeps an LMS student on the exam despite a stale expert toggle', async () => {
      signIn('student')
      useUIStore.setState({ uiMode: 'expert' })
      visit('/student/exams/p1?lti_u=u1&lti_ui=student')
      render(<StudentModeRedirect />)

      await waitFor(() => expect(useUIStore.getState().uiMode).toBe('student'))
      expect(mockReplace).not.toHaveBeenCalled()
      // Only lti_ui is dropped from the address bar.
      expect(window.location.pathname).toBe('/student/exams/p1')
      expect(window.location.search).toBe('?lti_u=u1')
    })

    it('puts an LMS teacher into the expert shell on the LTI page', async () => {
      // LMS accounts are saved with the student preference.
      signIn('student')
      visit('/lti/link?rl=rl-1&lti_ui=expert')
      render(<StudentModeRedirect />)

      await waitFor(() => expect(useUIStore.getState().uiMode).toBe('expert'))
      expect(mockReplace).not.toHaveBeenCalled()
      expect(window.location.search).toBe('?rl=rl-1')
    })

    it('decides the bounce with the requested mode on the first run', async () => {
      signIn('student')
      visit('/dashboard?lti_u=u1&lti_ui=expert')
      render(<StudentModeRedirect />)

      await waitFor(() => expect(useUIStore.getState().uiMode).toBe('expert'))
      expect(mockReplace).not.toHaveBeenCalled()
    })

    it('keeps the hash and other params when stripping', async () => {
      signIn('expert')
      visit('/lti/link?x=1&lti_ui=expert&rl=rl-2#top')
      render(<StudentModeRedirect />)

      await waitFor(() => expect(window.location.search).toBe('?x=1&rl=rl-2'))
      expect(window.location.hash).toBe('#top')
    })

    it('ignores lti_ui without an LMS landing param', async () => {
      signIn('expert')
      useUIStore.setState({ uiMode: 'expert' })
      visit('/student/exams/p1?lti_ui=student')
      render(<StudentModeRedirect />)

      await waitFor(() =>
        expect(mockReplace).toHaveBeenCalledWith('/dashboard'),
      )
      expect(useUIStore.getState().uiMode).toBe('expert')
      expect(window.location.search).toBe('?lti_ui=student')
    })

    it('ignores unknown modes', async () => {
      signIn('expert')
      visit('/student/exams/p1?lti_u=u1&lti_ui=admin')
      render(<StudentModeRedirect />)

      await waitFor(() =>
        expect(mockReplace).toHaveBeenCalledWith('/dashboard'),
      )
      expect(useUIStore.getState().uiMode).toBeNull()
    })

    it('ignores expert on student-locked hosts', async () => {
      mockLockedHost = true
      signIn(null)
      visit('/student/exams/p1?lti_u=u1&lti_ui=expert')
      render(<StudentModeRedirect />)

      await waitFor(() => expect(window.location.search).toBe('?lti_u=u1'))
      expect(useUIStore.getState().uiMode).toBeNull()
      expect(mockReplace).not.toHaveBeenCalled()
    })

    it('keeps an LMS student with a saved expert choice in the student UI on a student-locked host', async () => {
      mockLockedHost = true
      signIn('expert')
      visit('/student/exams/p1?lti_u=u1&lti_ui=student')
      render(<StudentModeRedirect />)

      await waitFor(() => expect(useUIStore.getState().uiMode).toBe('student'))
      expect(mockReplace).not.toHaveBeenCalled()
      expect(window.location.search).toBe('?lti_u=u1')
    })

    it('leaves the signed-in account alone on the consent page', async () => {
      // An org admin testing a student launch in their own browser: consent
      // runs before any session of the launch exists.
      signIn('expert')
      useUIStore.setState({ uiMode: 'expert' })
      visit('/lti/consent?rl=rl-1&p=h&lti_ui=student')
      render(<StudentModeRedirect />)

      await new Promise((resolve) => setTimeout(resolve, 20))
      expect(useUIStore.getState().uiMode).toBe('expert')
      expect(mockReplace).not.toHaveBeenCalled()
      expect(window.location.search).toBe('?rl=rl-1&p=h&lti_ui=student')
    })

    it('ignores other pre-session pages too', async () => {
      signIn('expert')
      useUIStore.setState({ uiMode: 'expert' })
      for (const url of [
        '/lti/link-account?rl=rl-1&lti_ui=student',
        '/lti/link-confirm/tok?rl=rl-1&lti_ui=student',
        '/lti/error?code=x&rl=rl-1&lti_ui=student',
      ]) {
        visit(url)
        const { unmount } = render(<StudentModeRedirect />)
        await new Promise((resolve) => setTimeout(resolve, 10))
        expect(useUIStore.getState().uiMode).toBe('expert')
        unmount()
      }
      expect(mockReplace).not.toHaveBeenCalled()
    })

    it('ignores a landing meant for another user', async () => {
      signIn('expert')
      useUIStore.setState({ uiMode: 'expert' })
      visit('/student/exams/p1?lti_u=other&lti_ui=student')
      render(<StudentModeRedirect />)

      // The stored mode stays; the page follows it (LtiSessionGuard blocks
      // the foreign landing itself).
      await waitFor(() =>
        expect(mockReplace).toHaveBeenCalledWith('/dashboard'),
      )
      expect(useUIStore.getState().uiMode).toBe('expert')
      expect(window.location.search).toBe('?lti_u=other&lti_ui=student')
    })

    it('does nothing in the community edition', async () => {
      process.env[EDITION_KEY] = 'community'
      signIn(null)
      visit('/dashboard?lti_u=u1&lti_ui=student')
      render(<StudentModeRedirect />)

      await waitFor(() => expect(window.location.search).toBe('?lti_u=u1'))
      expect(useUIStore.getState().uiMode).toBeNull()
      expect(mockReplace).not.toHaveBeenCalled()
    })
  })
})

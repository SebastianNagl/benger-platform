/**
 * @jest-environment jsdom
 *
 * StudentModeRedirect while the extended package is still loading: the
 * one-shot `lti_ui` from an LMS launch must survive until the student shell
 * is registered, then decide the mode. Separate file because the slot
 * registry has no way to unregister a slot.
 */

import { registerSlot } from '@/lib/extensions/slots'
import { useUIStore } from '@/stores'
import { act, render, waitFor } from '@testing-library/react'
import React from 'react'

const EDITION_KEY = 'NEXT_PUBLIC_BENGER_EDITION'
const originalEdition = process.env[EDITION_KEY]

const mockReplace = jest.fn()
let mockPathname = '/'

jest.mock('next/navigation', () => ({
  usePathname: () => mockPathname,
  useRouter: () => ({ replace: mockReplace, push: jest.fn() }),
}))
jest.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 'u1', preferred_ui_mode: 'student' },
    isLoading: false,
  }),
}))
jest.mock('@/lib/utils/subdomain', () => ({
  ...jest.requireActual('@/lib/utils/subdomain'),
  isStudentLockedHost: () => false,
}))

import { StudentModeRedirect } from '../StudentModeRedirect'

afterAll(() => {
  if (originalEdition === undefined) delete process.env[EDITION_KEY]
  else process.env[EDITION_KEY] = originalEdition
})

it('waits for the student shell before it handles lti_ui', async () => {
  process.env[EDITION_KEY] = 'extended'
  useUIStore.setState({ uiMode: null, isHydrated: true })
  window.history.replaceState(null, '', '/lti/link?rl=rl-1&lti_ui=expert')
  mockPathname = '/lti/link'

  render(<StudentModeRedirect />)

  // Not registered yet: the param stays and nothing is decided.
  await new Promise((resolve) => setTimeout(resolve, 20))
  expect(window.location.search).toBe('?rl=rl-1&lti_ui=expert')
  expect(useUIStore.getState().uiMode).toBeNull()

  act(() => registerSlot('StudentShell', () => null))

  await waitFor(() => expect(useUIStore.getState().uiMode).toBe('expert'))
  expect(window.location.search).toBe('?rl=rl-1')
  expect(mockReplace).not.toHaveBeenCalled()
})

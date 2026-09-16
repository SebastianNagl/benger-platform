/**
 * @jest-environment jsdom
 *
 * Tests for the teacher activity host route (/lti/activity).
 *
 * A bound instructor launch lands here with `?rl=&lti_u=&lti_ui=`. The page
 * is a thin dispatcher to the extended LtiActivityView slot: it hands the
 * query over as props, renders a neutral notice in the community edition,
 * and belongs to the authenticated app surface (neither public nor
 * expert-only, so the shell follows the UI mode the launch asked for).
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

import { isExpertOnlyRoute } from '@/lib/utils/routeSurface'
import { authRedirect } from '@/utils/authRedirect'

import LtiActivityPage from '../activity/page'

const FALLBACK = 'The LMS activity view requires the extended edition.'

beforeEach(() => {
  mockUseSlot.mockReset()
  mockUseSlot.mockReturnValue(null)
  mockSearchParams.current = new URLSearchParams()
})

function ViewProbe(props: Record<string, unknown>) {
  return <pre data-testid="activity-props">{JSON.stringify(props)}</pre>
}

function renderedProps() {
  return JSON.parse(screen.getByTestId('activity-props').textContent || '{}')
}

describe('LTI activity host route', () => {
  it('renders the community fallback when no slot is registered', () => {
    render(<LtiActivityPage />)
    expect(mockUseSlot).toHaveBeenCalledWith('LtiActivityView')
    expect(screen.getByText(FALLBACK)).toBeInTheDocument()
  })

  it('renders the registered slot with the launch query as props', () => {
    mockUseSlot.mockReturnValue(ViewProbe)
    mockSearchParams.current = new URLSearchParams(
      'rl=link-1&lti_u=user-7&lti_ui=expert',
    )
    render(<LtiActivityPage />)
    expect(renderedProps()).toEqual({
      resourceLinkId: 'link-1',
      expectedUserId: 'user-7',
      requestedUiMode: 'expert',
    })
    expect(screen.queryByText(FALLBACK)).not.toBeInTheDocument()
  })

  it('passes the student mode of a student-host launch through', () => {
    mockUseSlot.mockReturnValue(ViewProbe)
    mockSearchParams.current = new URLSearchParams(
      'rl=link-2&lti_u=user-8&lti_ui=student',
    )
    render(<LtiActivityPage />)
    expect(renderedProps().requestedUiMode).toBe('student')
  })

  it('drops an unknown ui mode and tolerates a missing query', () => {
    mockUseSlot.mockReturnValue(ViewProbe)
    mockSearchParams.current = new URLSearchParams('lti_ui=admin')
    render(<LtiActivityPage />)
    expect(renderedProps()).toEqual({
      resourceLinkId: '',
      expectedUserId: '',
      requestedUiMode: null,
    })
  })

  it('needs a session like the link picker', () => {
    expect(authRedirect.isPublicRoute('/lti/activity')).toBe(false)
    expect(authRedirect.isPublicRoute('/lti/link')).toBe(false)
  })

  it('takes the shell of the resolved UI mode like the link picker', () => {
    // Not expert-only: on a student host the student shell renders it, on
    // the main host the expert shell (the launch sets the mode).
    expect(isExpertOnlyRoute('/lti/activity')).toBe(false)
    expect(isExpertOnlyRoute('/lti/link')).toBe(false)
  })
})

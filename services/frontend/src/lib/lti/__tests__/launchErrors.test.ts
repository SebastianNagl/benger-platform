import {
  isLtiLaunchErrorCode,
  LTI_DEFAULT_ERROR_ACTIONS,
  LTI_ERROR_ACTION_CATEGORIES,
  LTI_ERROR_ACTIONS,
  LTI_LAUNCH_ERROR_CODES,
  ltiErrorActions,
  ltiLaunchErrorPath,
} from '../launchErrors'

describe('LTI launch error registry', () => {
  it('lists every code once, in snake_case', () => {
    expect(new Set(LTI_LAUNCH_ERROR_CODES).size).toBe(
      LTI_LAUNCH_ERROR_CODES.length,
    )
    for (const code of LTI_LAUNCH_ERROR_CODES) {
      expect(code).toMatch(/^[a-z]+(_[a-z]+)*$/)
    }
  })

  it('gives every code at least one known action and no duplicates', () => {
    expect(Object.keys(LTI_ERROR_ACTIONS).sort()).toEqual(
      [...LTI_LAUNCH_ERROR_CODES].sort(),
    )
    for (const code of LTI_LAUNCH_ERROR_CODES) {
      const actions = LTI_ERROR_ACTIONS[code]
      expect(actions.length).toBeGreaterThan(0)
      expect(new Set(actions).size).toBe(actions.length)
      for (const action of actions) {
        expect(LTI_ERROR_ACTION_CATEGORIES).toContain(action)
      }
    }
  })

  it('asks to try later for server-side outages', () => {
    // state_unavailable means the state store is down, not a cookie problem.
    expect(LTI_ERROR_ACTIONS.state_unavailable).toEqual(['tryLater'])
    expect(LTI_ERROR_ACTIONS.internal).toEqual(['tryLater'])
  })

  it('sends connection problems to the organization admin', () => {
    expect(LTI_ERROR_ACTIONS.registration_disabled).toContain('orgAdmin')
    expect(LTI_ERROR_ACTIONS.deployment_disabled).toContain('orgAdmin')
    expect(LTI_ERROR_ACTIONS.membership_removed).toContain('orgAdmin')
    expect(LTI_ERROR_ACTIONS.not_linked).toEqual(['teacher'])
  })

  it('does not treat a host mismatch as an error', () => {
    expect(isLtiLaunchErrorCode('tool_host_mismatch')).toBe(false)
  })
})

describe('isLtiLaunchErrorCode', () => {
  it('accepts registered codes only', () => {
    expect(isLtiLaunchErrorCode('invalid_state')).toBe(true)
    expect(isLtiLaunchErrorCode('launch_expired')).toBe(true)
    expect(isLtiLaunchErrorCode('consent_incomplete')).toBe(false)
    expect(isLtiLaunchErrorCode('')).toBe(false)
    expect(isLtiLaunchErrorCode(null)).toBe(false)
    expect(isLtiLaunchErrorCode(undefined)).toBe(false)
    expect(isLtiLaunchErrorCode(42)).toBe(false)
    expect(isLtiLaunchErrorCode('toString')).toBe(false)
  })
})

describe('ltiErrorActions', () => {
  it('returns the actions of a known code', () => {
    expect(ltiErrorActions('unknown_deployment')).toEqual([
      'lmsAdmin',
      'orgAdmin',
    ])
  })

  it('falls back to reopening for unknown or missing codes', () => {
    expect(ltiErrorActions('something_new')).toBe(LTI_DEFAULT_ERROR_ACTIONS)
    expect(ltiErrorActions(null)).toEqual(['reopen'])
    expect(ltiErrorActions(undefined)).toEqual(['reopen'])
  })
})

describe('ltiLaunchErrorPath', () => {
  it('builds the error page URL for a launch code', () => {
    expect(ltiLaunchErrorPath('launch_expired')).toBe(
      '/lti/error?code=launch_expired',
    )
  })

  it('carries the support reference when given', () => {
    expect(ltiLaunchErrorPath('internal', '1a2b3c4d')).toBe(
      '/lti/error?code=internal&ref=1a2b3c4d',
    )
    expect(ltiLaunchErrorPath('internal', '')).toBe('/lti/error?code=internal')
    expect(ltiLaunchErrorPath('internal', null)).toBe(
      '/lti/error?code=internal',
    )
  })

  it('returns null for codes the calling page handles itself', () => {
    expect(ltiLaunchErrorPath('consent_incomplete')).toBeNull()
    expect(ltiLaunchErrorPath(null)).toBeNull()
    expect(ltiLaunchErrorPath(undefined)).toBeNull()
  })
})

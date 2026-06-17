/**
 * Additional behavioral coverage for AuthClient.
 *
 * auth.test.ts covers login/signup-basic/getUser/verify/logout/profile/
 * changePassword but leaves these uncovered (branch 25%, functions 64%):
 *  - signup with profileData (the Object.entries filter dropping
 *    undefined/null) and with invitationToken
 *  - getUserContexts, getMandatoryProfileStatus, confirmProfile,
 *    getProfileHistory (never called)
 *  - updateProfile / confirmProfile invalidateCache side effect
 *
 * Mirrors auth.test.ts: jest.mock('../base', ...) with a hand-written
 * MockBaseApiClient, then jest.spyOn on request/authCheckRequest to assert
 * the exact endpoint + body.
 */

import { AuthClient } from '../auth'

jest.mock('../base', () => ({
  BaseApiClient: class MockBaseApiClient {
    invalidateCache = jest.fn()
    clearCache = jest.fn()
    async request<T>(url: string, options?: RequestInit): Promise<T> {
      return { url, body: options?.body } as unknown as T
    }
    async authCheckRequest<T>(url: string, options?: RequestInit): Promise<T> {
      return { url, body: options?.body } as unknown as T
    }
  },
}))

describe('AuthClient - uncovered branches', () => {
  let client: AuthClient

  beforeEach(() => {
    client = new AuthClient()
  })

  describe('signup with profileData', () => {
    it('merges defined profile fields and drops undefined/null values', async () => {
      const requestSpy = jest.spyOn(client as any, 'request')

      await client.signup('u', 'e@x.de', 'Name', 'pw', {
        legal_expertise_level: 'student',
        current_semester: 4,
        // These should be filtered out by `value !== undefined && value !== null`
        german_proficiency: undefined,
        degree_program_type: null as unknown as string,
        legal_specializations: ['civil', 'public'],
        research_data_consent_accepted: false, // falsy but defined -> kept
      })

      const [endpoint, options] = requestSpy.mock.calls[0]
      expect(endpoint).toBe('/auth/signup')
      const parsed = JSON.parse((options as RequestInit).body as string)
      expect(parsed).toEqual({
        username: 'u',
        email: 'e@x.de',
        name: 'Name',
        password: 'pw',
        legal_expertise_level: 'student',
        current_semester: 4,
        legal_specializations: ['civil', 'public'],
        research_data_consent_accepted: false,
      })
      // Filtered-out keys must be absent, not present-as-undefined.
      expect(parsed).not.toHaveProperty('german_proficiency')
      expect(parsed).not.toHaveProperty('degree_program_type')
      expect(options).toMatchObject({ method: 'POST' })
    })

    it('includes the invitation_token when an invitation token is supplied', async () => {
      const requestSpy = jest.spyOn(client as any, 'request')

      await client.signup('u', 'e@x.de', 'Name', 'pw', undefined, 'tok-123')

      const [, options] = requestSpy.mock.calls[0]
      const parsed = JSON.parse((options as RequestInit).body as string)
      expect(parsed.invitation_token).toBe('tok-123')
      // No profileData provided -> only the four base fields + token.
      expect(Object.keys(parsed).sort()).toEqual([
        'email',
        'invitation_token',
        'name',
        'password',
        'username',
      ])
    })

    it('omits invitation_token when none is provided', async () => {
      const requestSpy = jest.spyOn(client as any, 'request')

      await client.signup('u', 'e@x.de', 'Name', 'pw')

      const [, options] = requestSpy.mock.calls[0]
      const parsed = JSON.parse((options as RequestInit).body as string)
      expect(parsed).not.toHaveProperty('invitation_token')
    })
  })

  describe('getUserContexts', () => {
    it('calls /auth/me/contexts via authCheckRequest', async () => {
      const authSpy = jest
        .spyOn(client as any, 'authCheckRequest')
        .mockResolvedValue({
          user: { id: 'u1' },
          organizations: [],
          private_mode_available: true,
        })

      const result = await client.getUserContexts()

      expect(authSpy).toHaveBeenCalledWith('/auth/me/contexts')
      expect(result.private_mode_available).toBe(true)
    })
  })

  describe('getMandatoryProfileStatus', () => {
    it('issues a GET to /auth/mandatory-profile-status', async () => {
      const requestSpy = jest
        .spyOn(client as any, 'request')
        .mockResolvedValue({ profile_complete: false })

      const result = await client.getMandatoryProfileStatus()

      expect(requestSpy).toHaveBeenCalledWith('/auth/mandatory-profile-status')
      expect(result).toEqual({ profile_complete: false })
    })
  })

  describe('confirmProfile', () => {
    it('POSTs to /auth/confirm-profile and invalidates the status cache', async () => {
      const requestSpy = jest
        .spyOn(client as any, 'request')
        .mockResolvedValue({ confirmed: true })
      const invalidateSpy = jest.spyOn(client as any, 'invalidateCache')

      const result = await client.confirmProfile()

      expect(requestSpy).toHaveBeenCalledWith('/auth/confirm-profile', {
        method: 'POST',
      })
      expect(invalidateSpy).toHaveBeenCalledWith(
        '/auth/mandatory-profile-status'
      )
      expect(result).toEqual({ confirmed: true })
    })
  })

  describe('getProfileHistory', () => {
    it('issues a GET to /auth/profile-history', async () => {
      const requestSpy = jest
        .spyOn(client as any, 'request')
        .mockResolvedValue([{ field: 'name', changed_at: 'now' }])

      const result = await client.getProfileHistory()

      expect(requestSpy).toHaveBeenCalledWith('/auth/profile-history')
      expect(result).toHaveLength(1)
    })
  })

  describe('updateProfile cache invalidation', () => {
    it('PUTs the profile and invalidates the mandatory-profile-status cache', async () => {
      const requestSpy = jest
        .spyOn(client as any, 'request')
        .mockResolvedValue({ id: 'u1', name: 'New' })
      const invalidateSpy = jest.spyOn(client as any, 'invalidateCache')

      const result = await client.updateProfile({ name: 'New' })

      expect(requestSpy).toHaveBeenCalledWith('/auth/profile', {
        method: 'PUT',
        body: JSON.stringify({ name: 'New' }),
      })
      expect(invalidateSpy).toHaveBeenCalledWith(
        '/auth/mandatory-profile-status'
      )
      expect(result).toEqual({ id: 'u1', name: 'New' })
    })
  })
})

import { authUserPatchFromProfile, profileFormFromProfile } from '../types'

describe('profile helpers', () => {
  it('never carries the view preference into the auth user', () => {
    const patch = authUserPatchFromProfile({
      id: 'u1',
      name: 'A',
      exam_bundesland: 'NW',
      preferred_ui_mode: 'student',
    })
    expect(patch).toEqual({ id: 'u1', name: 'A', exam_bundesland: 'NW' })
    expect(patch).not.toHaveProperty('preferred_ui_mode')
  })

  it('maps a profile to the form, dropping unknown state codes', () => {
    const form = profileFormFromProfile({
      name: 'A',
      email: 'a@example.org',
      exam_bundesland: 'XX',
    })
    expect(form.exam_bundesland).toBeUndefined()
    expect(form.use_pseudonym).toBe(true)
    expect(form.job).toBe('')
    expect(
      profileFormFromProfile({ name: 'A', email: 'a@x', exam_bundesland: 'BY' })
        .exam_bundesland,
    ).toBe('BY')
  })
})

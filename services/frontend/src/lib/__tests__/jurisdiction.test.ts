import {
  groupJurisdiction,
  isJurisdiction,
  offeredFor,
  orgJurisdiction,
  wizardJurisdictions,
} from '../jurisdiction'

const orgs = [
  { id: 'de', jurisdiction: 'DE' },
  { id: 'fr', jurisdiction: 'FR' },
  { id: 'legacy' },
  { id: 'odd', jurisdiction: 'XX' },
]

describe('jurisdiction', () => {
  it('reads an organization, unknown and missing values are German', () => {
    expect(orgJurisdiction(orgs[1])).toBe('FR')
    expect(orgJurisdiction(orgs[2])).toBe('DE')
    expect(orgJurisdiction(orgs[3])).toBe('DE')
    expect(orgJurisdiction(null)).toBe('DE')
    expect(isJurisdiction('FR')).toBe(true)
    expect(isJurisdiction('fr')).toBe(false)
  })

  it('uses the target organizations when the project goes to organizations', () => {
    expect(wizardJurisdictions(orgs, ['fr'])).toEqual(['FR'])
    expect(wizardJurisdictions(orgs, ['fr', 'legacy'])).toEqual(['DE', 'FR'])
  })

  it('otherwise every organization of the user, never empty', () => {
    expect(wizardJurisdictions(orgs, null)).toEqual(['DE', 'FR'])
    expect(wizardJurisdictions(orgs, [])).toEqual(['DE', 'FR'])
    expect(wizardJurisdictions([], null)).toEqual(['DE'])
    expect(wizardJurisdictions(orgs, ['gone'])).toEqual(['DE'])
  })

  it('a group override wins over its organization, unknown values do not', () => {
    const org = {
      id: 'tum',
      jurisdiction: 'DE',
      group_jurisdictions: { droit: 'FR', odd: 'XX' },
    }
    expect(groupJurisdiction(org, 'droit')).toBe('FR')
    expect(groupJurisdiction(org, 'odd')).toBe('DE')
    expect(groupJurisdiction(org, 'plain')).toBe('DE')
    expect(groupJurisdiction(org, null)).toBe('DE')
  })

  it('uses the target group of a target organization', () => {
    const tum = {
      id: 'tum',
      jurisdiction: 'DE',
      group_jurisdictions: { droit: 'FR' },
    }
    expect(wizardJurisdictions([tum], ['tum'], { tum: 'droit' })).toEqual([
      'FR',
    ])
    expect(wizardJurisdictions([tum], ['tum'], { tum: null })).toEqual(['DE'])
    expect(wizardJurisdictions([tum], ['tum'])).toEqual(['DE'])
  })

  it("adds the user's own groups for a private project", () => {
    const tum = {
      id: 'tum',
      jurisdiction: 'DE',
      group_jurisdictions: { droit: 'FR' },
      groups: [{ id: 'droit' }],
    }
    expect(wizardJurisdictions([tum], null)).toEqual(['DE', 'FR'])
    expect(wizardJurisdictions([{ ...tum, groups: [] }], null)).toEqual(['DE'])
  })

  it('offers unrestricted entries everywhere and restricted ones by match', () => {
    expect(offeredFor(undefined, ['DE'])).toBe(true)
    expect(offeredFor(['FR'], ['DE'])).toBe(false)
    expect(offeredFor(['FR'], ['DE', 'FR'])).toBe(true)
  })
})

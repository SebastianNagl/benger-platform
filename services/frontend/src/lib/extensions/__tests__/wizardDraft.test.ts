/**
 * Draft-mode registry of the creation wizard (CORE 2.55): policies (with
 * their leave guards) and the created / tasksSynced / configSynced hooks,
 * filtered by active owner.
 */

import { setActiveExtensions } from '../active'
import { setRegistrationOwner } from '../owner'
import {
  _resetWizardDraftRegistry,
  getApplyingWizardDraftPolicies,
  getWizardDraftHooks,
  getWizardDraftPolicies,
  registerWizardDraftHook,
  registerWizardDraftPolicy,
  wizardDraftApplies,
} from '../wizardDraft'

afterEach(() => {
  _resetWizardDraftRegistry()
  setRegistrationOwner(null)
  setActiveExtensions([])
})

describe('wizard draft policies', () => {
  it('applies when any active policy applies, and never on a throwing one', () => {
    expect(wizardDraftApplies({})).toBe(false)
    const throwing = {
      applies: () => {
        throw new Error('broken')
      },
    }
    registerWizardDraftPolicy(throwing)
    expect(wizardDraftApplies({})).toBe(false)
    const rubric = { applies: (d: any) => d.features?.rubric === true }
    registerWizardDraftPolicy(rubric)
    registerWizardDraftPolicy(rubric)
    expect(getWizardDraftPolicies()).toEqual([throwing, rubric])
    expect(wizardDraftApplies({ features: { rubric: true } })).toBe(true)
    expect(wizardDraftApplies({ features: { rubric: false } })).toBe(false)
  })

  it('lists the applying policies in registration order, without throwing ones', () => {
    const guard = jest.fn().mockResolvedValue(true)
    const exam = {
      applies: (d: any) => d.projectKind === 'exam',
      beforeLeaveStep: guard,
    }
    const throwing = {
      applies: () => {
        throw new Error('broken')
      },
    }
    const always = { applies: () => true }
    registerWizardDraftPolicy(exam)
    registerWizardDraftPolicy(throwing)
    registerWizardDraftPolicy(always)
    expect(getApplyingWizardDraftPolicies({ projectKind: 'exam' })).toEqual([
      exam,
      always,
    ])
    expect(getApplyingWizardDraftPolicies({ projectKind: 'generic' })).toEqual([
      always,
    ])
  })

  it('counts only registrations of active owners', () => {
    setRegistrationOwner('extended')
    const policy = { applies: () => true }
    registerWizardDraftPolicy(policy)
    const hook = jest.fn()
    registerWizardDraftHook('created', hook)
    setRegistrationOwner(null)
    expect(getWizardDraftPolicies()).toEqual([])
    expect(getWizardDraftHooks('created')).toEqual([])
    setActiveExtensions(['extended'])
    expect(getWizardDraftPolicies()).toEqual([policy])
    expect(getWizardDraftHooks('created')).toEqual([hook])
  })
})

describe('wizard draft hooks', () => {
  it('keeps hooks per name in registration order, without duplicates', () => {
    const a = jest.fn()
    const b = jest.fn()
    registerWizardDraftHook('tasksSynced', a)
    registerWizardDraftHook('tasksSynced', b)
    registerWizardDraftHook('tasksSynced', a)
    registerWizardDraftHook('configSynced', a)
    expect(getWizardDraftHooks('tasksSynced')).toEqual([a, b])
    expect(getWizardDraftHooks('configSynced')).toEqual([a])
    expect(getWizardDraftHooks('created')).toEqual([])
  })
})

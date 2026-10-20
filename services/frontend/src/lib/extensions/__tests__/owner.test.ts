/**
 * Registration owner attribution: the loader sets the owner around an
 * overlay's registerAll(); keyed registries remember it per key and warn when
 * a different owner overwrites a key. Registries outside this directory
 * (metric definitions, annotation components) are covered here too so the
 * attribution contract has one home.
 */

import { registerMetric } from '@/lib/api/evaluation-types'
import { getComponent, registerComponent } from '@/lib/labelConfig/registry'
import { _resetActiveExtensionsForTests, setActiveExtensions } from '../active'
import { getMetricEditor, registerMetricEditor } from '../metricEditors'
import {
  PLATFORM_OWNER,
  getRegistrationOwner,
  recordRegistration,
  setRegistrationOwner,
  type RegistrationOwners,
} from '../owner'
import {
  _resetWizardKindPresets,
  getWizardKindPreset,
  registerWizardKindPreset,
} from '../wizardTemplates'
import {
  getWritingPresenceReporter,
  registerWritingPresenceReporter,
} from '../writingPresence'

let warn: jest.SpyInstance

beforeEach(() => {
  setRegistrationOwner(null)
  setActiveExtensions(['extended', 'compliance'])
  warn = jest.spyOn(console, 'warn').mockImplementation(() => undefined)
})

afterEach(() => {
  setRegistrationOwner(null)
  _resetActiveExtensionsForTests()
  warn.mockRestore()
})

function as(owner: string | null, fn: () => void) {
  setRegistrationOwner(owner)
  try {
    fn()
  } finally {
    setRegistrationOwner(null)
  }
}

describe('registration owner', () => {
  test('defaults to null and round-trips', () => {
    expect(getRegistrationOwner()).toBeNull()
    setRegistrationOwner('extended')
    expect(getRegistrationOwner()).toBe('extended')
    setRegistrationOwner(null)
    expect(getRegistrationOwner()).toBeNull()
  })
})

describe('recordRegistration', () => {
  test('is silent for a first registration and for the same owner again', () => {
    const owners: RegistrationOwners = new Map()
    as('extended', () => recordRegistration(owners, 'slot', 'A'))
    as('extended', () => recordRegistration(owners, 'slot', 'A'))
    recordRegistration(owners, 'slot', 'B')
    recordRegistration(owners, 'slot', 'B')
    expect(warn).not.toHaveBeenCalled()
    expect(owners.get('A')).toBe('extended')
    expect(owners.get('B')).toBeNull()
  })

  test('warns when a different owner overwrites a key and remembers the new owner', () => {
    const owners: RegistrationOwners = new Map()
    as('extended', () => recordRegistration(owners, 'slot', 'A'))
    as('compliance', () => recordRegistration(owners, 'slot', 'A'))
    expect(warn).toHaveBeenCalledTimes(1)
    expect(warn).toHaveBeenCalledWith(
      '[extensions] slot "A" registered by compliance replaces extended',
    )
    expect(owners.get('A')).toBe('compliance')
    // Back to the same owner: silent again.
    as('compliance', () => recordRegistration(owners, 'slot', 'A'))
    expect(warn).toHaveBeenCalledTimes(1)
  })

  test('labels registrations outside any overlay as platform', () => {
    const owners: RegistrationOwners = new Map()
    recordRegistration(owners, 'metric', 'x')
    as('extended', () => recordRegistration(owners, 'metric', 'x'))
    recordRegistration(owners, 'metric', 'x')
    expect(PLATFORM_OWNER).toBe('platform')
    expect(warn.mock.calls.map((c) => c[0])).toEqual([
      '[extensions] metric "x" registered by extended replaces platform',
      '[extensions] metric "x" registered by platform replaces extended',
    ])
  })

  test('keys are independent', () => {
    const owners: RegistrationOwners = new Map()
    as('extended', () => recordRegistration(owners, 'slot', 'A'))
    as('compliance', () => recordRegistration(owners, 'slot', 'B'))
    expect(warn).not.toHaveBeenCalled()
  })
})

describe('registries attribute owners', () => {
  test('metric editors', () => {
    const First = (() => null) as any
    const Second = (() => null) as any
    as('extended', () => registerMetricEditor('owner_test_metric', First))
    as('extended', () => registerMetricEditor('owner_test_metric', First))
    expect(warn).not.toHaveBeenCalled()
    as('compliance', () => registerMetricEditor('owner_test_metric', Second))
    expect(warn).toHaveBeenCalledWith(
      '[extensions] metric editor "owner_test_metric" registered by compliance replaces extended',
    )
    expect(getMetricEditor('owner_test_metric')).toBe(Second)
  })

  test('wizard kind presets, including the test reset', () => {
    const first = () => ({ a: 1 })
    const second = () => ({ a: 2 })
    as('extended', () => registerWizardKindPreset('owner_kind', first))
    as('compliance', () => registerWizardKindPreset('owner_kind', second))
    expect(warn).toHaveBeenCalledWith(
      '[extensions] wizard kind preset "owner_kind" registered by compliance replaces extended',
    )
    expect(getWizardKindPreset('owner_kind')).toBe(second)
    // The reset drops the owner memory with the presets.
    _resetWizardKindPresets()
    warn.mockClear()
    as('extended', () => registerWizardKindPreset('owner_kind', first))
    expect(warn).not.toHaveBeenCalled()
    _resetWizardKindPresets()
  })

  test('writing presence reporter', () => {
    const first = jest.fn()
    const second = jest.fn()
    as('extended', () => registerWritingPresenceReporter(first))
    as('compliance', () => registerWritingPresenceReporter(second))
    expect(warn).toHaveBeenCalledWith(
      '[extensions] writing presence reporter "default" registered by compliance replaces extended',
    )
    expect(getWritingPresenceReporter()).toBe(second)
    // Clearing it from platform code is a registration too.
    registerWritingPresenceReporter(null)
    expect(warn).toHaveBeenLastCalledWith(
      '[extensions] writing presence reporter "default" registered by platform replaces compliance',
    )
    expect(getWritingPresenceReporter()).toBeNull()
  })

  test('metric definitions', () => {
    const def = {
      name: 'Owner test',
      description: 'd',
      nameKey: 'x',
      descriptionKey: 'y',
      requires_reference: false,
    } as any
    as('extended', () => registerMetric('owner_test_def', def))
    as('compliance', () => registerMetric('owner_test_def', def))
    expect(warn).toHaveBeenCalledWith(
      '[extensions] metric "owner_test_def" registered by compliance replaces extended',
    )
  })

  test('annotation components', () => {
    const component = { component: () => null, category: 'control' } as any
    as('extended', () => registerComponent('OwnerTestTag', component))
    as('compliance', () => registerComponent('OwnerTestTag', component))
    expect(warn).toHaveBeenCalledWith(
      '[extensions] annotation component "OwnerTestTag" registered by compliance replaces extended',
    )
    expect(getComponent('OwnerTestTag')).toBe(component)
  })
})

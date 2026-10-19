/**
 * @jest-environment jsdom
 *
 * Runtime activation of overlays: every registry resolves to the newest
 * registration whose owner is active (lib/extensions/active.ts), so a
 * switched-off overlay falls back to the registration below it. Platform
 * registrations are always active.
 */
import '@testing-library/jest-dom'
import { act, render, screen } from '@testing-library/react'

import {
  getActiveMetricDefinitions,
  getGroupedMetrics,
  getMetricDefinitions,
  registerMetric,
  registerMetricGroup,
} from '@/lib/api/evaluation-types'
import { getHowToGuides, registerHowToGuides } from '@/lib/howto/registry'
import {
  _resetActiveExtensionsForTests,
  getActiveExtensions,
  isOwnerActive,
  setActiveExtensions,
  subscribeActiveExtensions,
} from '../active'
import { getChangelogEntries, registerChangelogEntries } from '../changelog'
import { getMetricEditor, registerMetricEditor } from '../metricEditors'
import { setRegistrationOwner } from '../owner'
import { getSlot, hasSlot, registerSlot, useSlot } from '../slots'
import {
  getWizardFinishContributors,
  registerWizardFinishContributor,
} from '../wizardFinish'
import {
  _resetWizardKindPresets,
  _resetWizardPostCreateHooks,
  getRegisteredWizardTemplates,
  getWizardKindPreset,
  getWizardPostCreateHooks,
  registerWizardKindPreset,
  registerWizardPostCreateHook,
  registerWizardTemplate,
} from '../wizardTemplates'
import {
  getWritingPresenceReporter,
  registerWritingPresenceReporter,
} from '../writingPresence'

let warn: jest.SpyInstance

beforeEach(() => {
  setRegistrationOwner(null)
  _resetActiveExtensionsForTests()
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

describe('active set', () => {
  test('platform and unowned registrations are always active', () => {
    expect(isOwnerActive('platform')).toBe(true)
    expect(isOwnerActive(null)).toBe(true)
    expect(isOwnerActive(undefined)).toBe(true)
    expect(isOwnerActive('extended')).toBe(false)
  })

  test('notifies only on change and keeps a stable sorted snapshot', () => {
    const listener = jest.fn()
    const unsubscribe = subscribeActiveExtensions(listener)
    setActiveExtensions(['compliance', 'extended'])
    const first = getActiveExtensions()
    expect(first).toEqual(['compliance', 'extended'])
    setActiveExtensions(['extended', 'compliance'])
    expect(listener).toHaveBeenCalledTimes(1)
    expect(getActiveExtensions()).toBe(first)
    setActiveExtensions([])
    expect(listener).toHaveBeenCalledTimes(2)
    unsubscribe()
    setActiveExtensions(['extended'])
    expect(listener).toHaveBeenCalledTimes(2)
  })
})

describe('slots', () => {
  const Platform = () => <span>platform</span>
  const Extended = () => <span>extended</span>
  const Compliance = () => <span>compliance</span>

  test('an inactive owner registers but does not resolve', () => {
    as('extended', () => registerSlot('ActOnlyExtended', Extended))
    expect(getSlot('ActOnlyExtended')).toBeNull()
    expect(hasSlot('ActOnlyExtended')).toBe(false)
    setActiveExtensions(['extended'])
    expect(getSlot('ActOnlyExtended')).toBe(Extended)
    expect(hasSlot('ActOnlyExtended')).toBe(true)
  })

  test('falls back to the newest active registration', () => {
    registerSlot('ActStacked', Platform)
    as('extended', () => registerSlot('ActStacked', Extended))
    as('compliance', () => registerSlot('ActStacked', Compliance))
    setActiveExtensions(['extended', 'compliance'])
    expect(getSlot('ActStacked')).toBe(Compliance)
    setActiveExtensions(['extended'])
    expect(getSlot('ActStacked')).toBe(Extended)
    setActiveExtensions(['compliance'])
    expect(getSlot('ActStacked')).toBe(Compliance)
    setActiveExtensions([])
    expect(getSlot('ActStacked')).toBe(Platform)
  })

  test('a repeated registration by the same owner keeps its place', () => {
    as('extended', () => registerSlot('ActRepeat', Extended))
    as('compliance', () => registerSlot('ActRepeat', Compliance))
    as('extended', () => registerSlot('ActRepeat', Platform))
    setActiveExtensions(['extended', 'compliance'])
    expect(getSlot('ActRepeat')).toBe(Compliance)
    setActiveExtensions(['extended'])
    expect(getSlot('ActRepeat')).toBe(Platform)
  })

  test('useSlot re-renders when the active set changes', () => {
    as('extended', () => registerSlot('ActHook', Extended))
    function Host() {
      const Slot = useSlot('ActHook')
      // eslint-disable-next-line react-hooks/static-components
      return Slot ? <Slot /> : <span>none</span>
    }
    render(<Host />)
    expect(screen.getByText('none')).toBeInTheDocument()
    act(() => setActiveExtensions(['extended']))
    expect(screen.getByText('extended')).toBeInTheDocument()
    act(() => setActiveExtensions([]))
    expect(screen.getByText('none')).toBeInTheDocument()
  })
})

describe('metric registry', () => {
  const def = (name: string) =>
    ({
      name,
      display_name: name,
      description: name,
      requires_reference: false,
    }) as any

  test('pickers only offer active metrics, lookups keep inactive ones', () => {
    as('extended', () => {
      registerMetric('act_metric', def('extended version'))
      registerMetricGroup({
        name: 'Act group',
        description: 'd',
        metrics: ['act_metric'],
      })
    })
    as('compliance', () => registerMetric('act_metric', def('compliance')))

    // Nothing active: no group, no active definition, but the lookup still
    // names stored results.
    expect(getGroupedMetrics().some((g) => g.name === 'Act group')).toBe(false)
    expect(getActiveMetricDefinitions().act_metric).toBeUndefined()
    expect(getMetricDefinitions().act_metric.display_name).toBe('compliance')

    setActiveExtensions(['extended'])
    expect(
      getGroupedMetrics().find((g) => g.name === 'Act group')?.metrics,
    ).toEqual(['act_metric'])
    expect(getActiveMetricDefinitions().act_metric.display_name).toBe(
      'extended version',
    )
    expect(getMetricDefinitions().act_metric.display_name).toBe(
      'extended version',
    )

    setActiveExtensions(['extended', 'compliance'])
    expect(getMetricDefinitions().act_metric.display_name).toBe('compliance')
  })

  test('a metric merged into a core group disappears with its owner', () => {
    const core = getGroupedMetrics()[0]
    as('extended', () => {
      registerMetric('act_core_merge', def('merged'))
      registerMetricGroup({
        name: core.name,
        description: core.description,
        metrics: ['act_core_merge'],
      })
    })
    const find = () =>
      getGroupedMetrics().find((g) => g.name === core.name)?.metrics ?? []
    expect(find()).not.toContain('act_core_merge')
    setActiveExtensions(['extended'])
    expect(find()).toContain('act_core_merge')
    // Core metrics are never filtered.
    for (const metric of core.metrics) expect(find()).toContain(metric)
  })
})

describe('other registries', () => {
  test('metric editors fall back by owner', () => {
    const A = () => null
    const B = () => null
    as('extended', () => registerMetricEditor('act_editor', A))
    as('compliance', () => registerMetricEditor('act_editor', B))
    expect(getMetricEditor('act_editor')).toBeNull()
    setActiveExtensions(['extended'])
    expect(getMetricEditor('act_editor')).toBe(A)
    setActiveExtensions(['extended', 'compliance'])
    expect(getMetricEditor('act_editor')).toBe(B)
  })

  test('wizard templates, kind presets, post-create hooks and finish contributors', () => {
    const template = {
      id: 'act-template',
      nameKey: 'n',
      descriptionKey: 'd',
    } as any
    const preset = () => ({})
    const hook = jest.fn()
    const contributor = () => ({})
    as('extended', () => {
      registerWizardTemplate(template)
      registerWizardKindPreset('act-kind', preset)
      registerWizardPostCreateHook(hook)
      registerWizardFinishContributor(contributor)
    })
    const ids = () => getRegisteredWizardTemplates().map((t) => t.id)
    expect(ids()).not.toContain('act-template')
    expect(getWizardKindPreset('act-kind')).toBeUndefined()
    expect(getWizardPostCreateHooks()).not.toContain(hook)
    expect(getWizardFinishContributors()).not.toContain(contributor)

    setActiveExtensions(['extended'])
    expect(ids()).toContain('act-template')
    expect(getWizardKindPreset('act-kind')).toBe(preset)
    expect(getWizardPostCreateHooks()).toContain(hook)
    expect(getWizardFinishContributors()).toContain(contributor)

    _resetWizardKindPresets()
    _resetWizardPostCreateHooks()
  })

  test('a template id registered by two owners resolves to the newest active one', () => {
    const base = { id: 'act-shared', nameKey: 'base', descriptionKey: 'd' }
    const over = { id: 'act-shared', nameKey: 'over', descriptionKey: 'd' }
    as('extended', () => registerWizardTemplate(base as any))
    as('compliance', () => registerWizardTemplate(over as any))
    const shared = () =>
      getRegisteredWizardTemplates().filter((t) => t.id === 'act-shared')
    setActiveExtensions(['extended', 'compliance'])
    expect(shared().map((t) => t.nameKey)).toEqual(['over'])
    setActiveExtensions(['extended'])
    expect(shared().map((t) => t.nameKey)).toEqual(['base'])
  })

  test('writing presence reporter', () => {
    const reporter = jest.fn()
    as('extended', () => registerWritingPresenceReporter(reporter))
    expect(getWritingPresenceReporter()).toBeNull()
    setActiveExtensions(['extended'])
    expect(getWritingPresenceReporter()).toBe(reporter)
    as('extended', () => registerWritingPresenceReporter(null))
  })

  test('changelog and how-to sources follow their owner', () => {
    registerChangelogEntries('act-platform', [
      { id: 'act-p', date: '2026-10-19', audience: 'both' },
    ])
    as('extended', () =>
      registerChangelogEntries('act-extended', [
        { id: 'act-e', date: '2026-10-19', audience: 'both' },
      ]),
    )
    as('extended', () =>
      registerHowToGuides('act-extended', [
        { id: 'act-guide', category: 'start' },
      ]),
    )
    const changelogIds = () => getChangelogEntries().map((e) => e.id)
    const guideIds = () => getHowToGuides().map((g) => g.id)
    expect(changelogIds()).toContain('act-p')
    expect(changelogIds()).not.toContain('act-e')
    expect(guideIds()).not.toContain('act-guide')
    setActiveExtensions(['extended'])
    expect(changelogIds()).toContain('act-e')
    expect(guideIds()).toContain('act-guide')
  })
})

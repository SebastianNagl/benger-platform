/**
 * @jest-environment jsdom
 *
 * The platform feature flag store: `useFeatureFlag` and the active extension
 * packages read GET /api/feature-flags/me for the current viewer (signed in
 * or anonymous, once auth has settled), answer false while loading and after
 * errors, refetch on user change, window focus (throttled), a
 * `feature_disabled` 404 and `refreshFeatureFlags()`, and seed the active
 * packages from the viewer's last known set in localStorage.
 */
import '@testing-library/jest-dom'
import { act, render, screen } from '@testing-library/react'

import { _resetActiveExtensionsForTests } from '@/lib/extensions/active'

import {
  ACTIVE_EXTENSIONS_STORAGE_KEY,
  FEATURE_FLAGS_ME_PATH,
  FOCUS_REFETCH_MS,
  getFeatureFlag,
  isExtensionActive,
  refreshFeatureFlags,
  resetFeatureFlagsForTests,
  useActiveExtensions,
  useActiveExtensionsReady,
  useExtensionActive,
  useFeatureFlag,
  useFeatureFlagStatus,
} from '..'
import { reportFeatureDisabled } from '../disabled'

let mockAuth: { user: { id: string } | null; isLoading: boolean } = {
  user: null,
  isLoading: false,
}
jest.mock('@/contexts/AuthContext', () => ({
  useAuth: () => mockAuth,
}))

const mockGet = jest.fn()
const mockInvalidate = jest.fn()
jest.mock('@/lib/api', () => ({
  __esModule: true,
  default: {
    get: (...args: unknown[]) => mockGet(...args),
    invalidateCache: (...args: unknown[]) => mockInvalidate(...args),
  },
}))

function Probe() {
  const rubric = useFeatureFlag('rubric_generation')
  const status = useFeatureFlagStatus('billing_ui')
  const active = useActiveExtensions()
  const extended = useExtensionActive('extended')
  const ready = useActiveExtensionsReady()
  return (
    <div>
      <span data-testid="rubric">{String(rubric)}</span>
      <span data-testid="billing">{status}</span>
      <span data-testid="active">{active.join(',')}</span>
      <span data-testid="extended">{String(extended)}</span>
      <span data-testid="ready">{String(ready)}</span>
    </div>
  )
}

function deferred<T>() {
  let resolve!: (v: T) => void
  let reject!: (e: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

const flush = () => act(async () => {})
const text = (id: string) => screen.getByTestId(id).textContent

function stored() {
  return JSON.parse(
    window.localStorage.getItem(ACTIVE_EXTENSIONS_STORAGE_KEY) ?? 'null',
  )
}

let now = 1_000_000
beforeEach(() => {
  jest.clearAllMocks()
  window.localStorage.clear()
  resetFeatureFlagsForTests()
  _resetActiveExtensionsForTests()
  mockAuth = { user: null, isLoading: false }
  now = 1_000_000
  jest.spyOn(Date, 'now').mockImplementation(() => now)
})

afterEach(() => {
  jest.restoreAllMocks()
})

it('fetches nothing while auth has not settled', async () => {
  mockAuth = { user: null, isLoading: true }
  render(<Probe />)
  await flush()
  expect(mockGet).not.toHaveBeenCalled()
  expect(text('billing')).toBe('loading')
  expect(text('ready')).toBe('false')
})

it('fetches anonymously once auth settles without a user', async () => {
  mockGet.mockResolvedValueOnce({
    flags: { rubric_generation: true },
    extensions: { extended: true, compliance: false },
  })
  render(<Probe />)
  await flush()
  expect(mockGet).toHaveBeenCalledWith(FEATURE_FLAGS_ME_PATH)
  expect(mockInvalidate).toHaveBeenCalledWith(FEATURE_FLAGS_ME_PATH)
  expect(text('rubric')).toBe('true')
  expect(text('billing')).toBe('off')
  expect(text('active')).toBe('extended')
  expect(text('extended')).toBe('true')
  expect(isExtensionActive('extended')).toBe(true)
  expect(isExtensionActive('compliance')).toBe(false)
  expect(stored()).toEqual({
    last: 'anonymous',
    bySubject: { anonymous: ['extended'] },
  })
})

it('answers false while loading, then the server answer', async () => {
  mockAuth = { user: { id: 'u1' }, isLoading: false }
  const answer = deferred<unknown>()
  mockGet.mockReturnValueOnce(answer.promise)
  render(<Probe />)
  await flush()
  expect(mockGet).toHaveBeenCalledTimes(1)
  expect(text('rubric')).toBe('false')
  expect(text('billing')).toBe('loading')
  // No last known set for u1: nothing active, not ready.
  expect(text('active')).toBe('')
  expect(text('ready')).toBe('false')

  await act(async () => {
    answer.resolve({
      flags: { rubric_generation: true, billing_ui: false },
      extensions: { extended: true, compliance: true },
    })
  })
  expect(text('rubric')).toBe('true')
  expect(text('billing')).toBe('off')
  expect(text('active')).toBe('compliance,extended')
  expect(text('ready')).toBe('true')
  expect(getFeatureFlag('rubric_generation')).toBe(true)
  expect(getFeatureFlag('billing_ui')).toBe(false)
})

it('seeds the active packages from the same viewer and replaces them with the answer', async () => {
  window.localStorage.setItem(
    ACTIVE_EXTENSIONS_STORAGE_KEY,
    JSON.stringify({
      last: 'u2',
      bySubject: { u1: ['extended'], u2: ['compliance'] },
    }),
  )
  mockAuth = { user: { id: 'u1' }, isLoading: false }
  const answer = deferred<unknown>()
  mockGet.mockReturnValueOnce(answer.promise)
  render(<Probe />)
  await flush()
  expect(text('active')).toBe('extended')
  expect(text('ready')).toBe('true')
  // Flags themselves are never seeded.
  expect(text('billing')).toBe('loading')

  await act(async () => {
    answer.resolve({
      flags: {},
      extensions: { extended: false, compliance: true },
    })
  })
  expect(text('active')).toBe('compliance')
  expect(stored().last).toBe('u1')
  expect(stored().bySubject).toEqual({ u2: ['compliance'], u1: ['compliance'] })
})

it('treats anything but a literal true as off and tolerates odd answers', async () => {
  mockAuth = { user: { id: 'u1' }, isLoading: false }
  mockGet.mockResolvedValueOnce({
    flags: { rubric_generation: 'yes', billing_ui: 1 },
    extensions: { extended: 'true' },
  })
  render(<Probe />)
  await flush()
  expect(text('rubric')).toBe('false')
  expect(text('billing')).toBe('off')
  expect(text('active')).toBe('')

  mockGet.mockResolvedValueOnce(null)
  await act(async () => {
    await refreshFeatureFlags()
  })
  expect(text('billing')).toBe('off')
})

it('fails closed for flags on an error and keeps the active packages', async () => {
  mockAuth = { user: { id: 'u1' }, isLoading: false }
  mockGet.mockResolvedValueOnce({
    flags: { billing_ui: true },
    extensions: { extended: true },
  })
  render(<Probe />)
  await flush()
  expect(text('billing')).toBe('on')

  mockGet.mockRejectedValueOnce(new Error('500'))
  await act(async () => {
    await refreshFeatureFlags()
  })
  expect(text('billing')).toBe('off')
  expect(text('active')).toBe('extended')
  expect(text('ready')).toBe('true')
})

it('refetches for a new user and drops the old answer', async () => {
  mockAuth = { user: { id: 'u1' }, isLoading: false }
  mockGet.mockResolvedValueOnce({
    flags: { rubric_generation: true },
    extensions: { extended: true },
  })
  const { rerender } = render(<Probe />)
  await flush()
  expect(text('rubric')).toBe('true')

  const second = deferred<unknown>()
  mockGet.mockReturnValueOnce(second.promise)
  mockAuth = { user: { id: 'u2' }, isLoading: false }
  rerender(<Probe />)
  await flush()
  expect(text('rubric')).toBe('false')
  expect(text('billing')).toBe('loading')
  expect(text('active')).toBe('')

  await act(async () => {
    second.resolve({ flags: {}, extensions: {} })
  })
  expect(text('billing')).toBe('off')
})

it('refetches on focus at most every FOCUS_REFETCH_MS', async () => {
  mockAuth = { user: { id: 'u1' }, isLoading: false }
  mockGet.mockResolvedValue({ flags: {}, extensions: {} })
  render(<Probe />)
  await flush()
  expect(mockGet).toHaveBeenCalledTimes(1)

  await act(async () => {
    window.dispatchEvent(new Event('focus'))
  })
  expect(mockGet).toHaveBeenCalledTimes(1)

  now += FOCUS_REFETCH_MS
  await act(async () => {
    window.dispatchEvent(new Event('focus'))
  })
  expect(mockGet).toHaveBeenCalledTimes(2)
})

it('refetches when the API reports feature_disabled', async () => {
  mockAuth = { user: { id: 'u1' }, isLoading: false }
  mockGet.mockResolvedValueOnce({
    flags: {},
    extensions: { compliance: true },
  })
  render(<Probe />)
  await flush()
  expect(text('active')).toBe('compliance')

  mockGet.mockResolvedValueOnce({ flags: {}, extensions: {} })
  await act(async () => {
    reportFeatureDisabled(404, {
      detail: { code: 'feature_disabled', flag: 'extension.compliance' },
    })
  })
  expect(mockGet).toHaveBeenCalledTimes(2)
  expect(text('active')).toBe('')
})

it('keeps working when localStorage throws', async () => {
  jest.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
    throw new Error('blocked')
  })
  jest.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
    throw new Error('blocked')
  })
  mockAuth = { user: { id: 'u1' }, isLoading: false }
  mockGet.mockResolvedValueOnce({
    flags: { rubric_generation: true },
    extensions: { extended: true },
  })
  render(<Probe />)
  await flush()
  expect(text('rubric')).toBe('true')
  expect(text('active')).toBe('extended')
})

it('ignores a malformed stored value', async () => {
  window.localStorage.setItem(ACTIVE_EXTENSIONS_STORAGE_KEY, '{not json')
  mockAuth = { user: { id: 'u1' }, isLoading: false }
  mockGet.mockReturnValueOnce(new Promise(() => undefined))
  render(<Probe />)
  await flush()
  expect(text('active')).toBe('')
  expect(text('ready')).toBe('false')
})

it('seeds the last viewer of this browser at module load', () => {
  window.localStorage.setItem(
    ACTIVE_EXTENSIONS_STORAGE_KEY,
    JSON.stringify({ last: 'u9', bySubject: { u9: ['compliance'] } }),
  )
  jest.isolateModules(() => {
    const active = require('@/lib/extensions/active')
    require('..')
    expect(active.getActiveExtensions()).toEqual(['compliance'])
  })
})

/**
 * Feature flags for component tests.
 *
 *   jest.mock('@/lib/featureFlags', () =>
 *     jest.requireActual('@/test-utils/featureFlagsMock').featureFlagsMockModule(),
 *   )
 *   beforeEach(() => setMockFeatureFlags({ variant_experiments: true }))
 *
 * The flag hooks then answer from the map set here (every flag off by
 * default, as for a viewer the server gave no flags), without the auth
 * context or a request to /feature-flags/me.
 */

let flags: Record<string, boolean> = {}

// Every test starts with all flags off; a describe block's own beforeEach
// (registered later, so it runs after this one) may turn some on.
if (typeof beforeEach === 'function') {
  beforeEach(() => {
    flags = {}
  })
}

/** Replace the viewer's flags for the following renders. */
export function setMockFeatureFlags(next: Record<string, boolean> = {}): void {
  flags = { ...next }
}

/** The module `jest.mock('@/lib/featureFlags', ...)` should return. */
export function featureFlagsMockModule() {
  const actual = jest.requireActual('@/lib/featureFlags')
  return {
    ...actual,
    getFeatureFlag: (name: string) => flags[name] === true,
    useFeatureFlag: (name: string) => flags[name] === true,
    useFeatureFlagStatus: (name: string) =>
      flags[name] === true ? 'on' : 'off',
    useFeatureFlagMap: () => flags,
    useFeatureFlagsReady: () => true,
    useFeatureFlagsSync: () => undefined,
    FeatureFlagsSync: () => null,
  }
}

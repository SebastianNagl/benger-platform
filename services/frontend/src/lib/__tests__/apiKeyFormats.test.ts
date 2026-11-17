import { API_KEY_PROVIDERS, isValidApiKeyFormat } from '../apiKeyFormats'

// Fake key shapes only, modeled on each provider's documented key format.
const WELL_FORMED_KEYS: Record<string, string[]> = {
  openai: [
    'sk-proj-fake_Key-NotReal0123456789abcdef',
    'sk-svcacct-fakeKeyNotReal0123456789',
    'sk-fakeKeyNotReal0123456789abcdef',
  ],
  anthropic: ['sk-ant-api03-fake_Key-NotReal0123456789'],
  google: [
    'AQ.Ab8RN6Lfake-key_not.real0123456789abcdefXYZ',
    'AIzaSyFakeKeyNotReal0123456789abcdefgh',
  ],
  deepinfra: ['d'.repeat(32)],
  grok: ['xai-fakeKeyNotReal0123456789'],
  mistral: ['m'.repeat(32)],
  cohere: ['c'.repeat(40)],
}

describe('isValidApiKeyFormat', () => {
  it.each(
    Object.entries(WELL_FORMED_KEYS).flatMap(([provider, keys]) =>
      keys.map((key) => [provider, key]),
    ),
  )('accepts a valid %s key %s', (provider, key) => {
    expect(isValidApiKeyFormat(provider, key)).toBe(true)
  })

  it('accepts a well-formed key for every listed provider', () => {
    for (const { id } of API_KEY_PROVIDERS) {
      const keys = WELL_FORMED_KEYS[id] ?? []
      expect(keys.length).toBeGreaterThan(0)
      for (const key of keys) {
        expect(isValidApiKeyFormat(id, key)).toBe(true)
      }
    }
  })

  it('accepts the minimum Google key length the backend accepts', () => {
    expect(isValidApiKeyFormat('google', 'AQ.Ab8.RN6L')).toBe(true)
    expect(isValidApiKeyFormat('google', 'AQ.Ab8.RN6')).toBe(false)
  })

  it('ignores surrounding whitespace', () => {
    expect(isValidApiKeyFormat('google', '  AQ.Ab8RN6Lfake.key  \n')).toBe(true)
    expect(
      isValidApiKeyFormat('openai', '  sk-proj-fakeKeyNotReal0123456789\n'),
    ).toBe(true)
  })

  it.each([
    ['google', 'short'],
    ['google', '   '],
    ['openai', 'invalid-key-without-prefix'],
    ['openai', 'sk-short'],
    ['openai', 'sk-abc def1234567890123456789'],
    ['anthropic', 'sk-fakeKeyNotReal0123456789'],
    ['anthropic', 'sk-ant-tooShort0123'],
    ['grok', 'fakeKeyNotReal0123456789'],
    ['grok', 'xai-short'],
    ['deepinfra', 'short'],
    ['deepinfra', 'fake-DeepInfra-Key-0123456789'],
    ['mistral', 'tooShort'],
    ['mistral', 'fake.Mistral.Key.0123456789abc'],
    ['cohere', 'tooShort'],
    ['unknown', 'anything-long-enough-0123456789'],
  ])('rejects an invalid %s key %s', (provider, key) => {
    expect(isValidApiKeyFormat(provider, key)).toBe(false)
  })
})

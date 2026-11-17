import { API_KEY_PROVIDERS, isValidApiKeyFormat } from '../apiKeyFormats'

// Fake key shapes only. Each accepted case is a current official format that
// the backend shape check (EncryptionService.is_valid_api_key_format) accepts.
describe('isValidApiKeyFormat', () => {
  it.each([
    ['google', 'AQ.Ab8RN6Lfake-key_not.real0123456789abcdefXYZ'],
    ['google', 'AIzaSyFakeKeyNotReal0123456789abcdefgh'],
    ['openai', 'sk-proj-fake_Key-NotReal0123456789abcdef'],
    ['openai', 'sk-svcacct-fakeKeyNotReal0123456789'],
    ['openai', 'sk-fakeKeyNotReal0123456789abcdef'],
    ['anthropic', 'sk-ant-api03-fake_Key-NotReal0123456789'],
    ['deepinfra', 'd'.repeat(32)],
    ['grok', 'xai-fakeKeyNotReal0123456789'],
    ['mistral', 'm'.repeat(32)],
    ['cohere', 'c'.repeat(40)],
  ])('accepts a valid %s key', (provider, key) => {
    expect(isValidApiKeyFormat(provider, key)).toBe(true)
  })

  it('ignores surrounding whitespace', () => {
    expect(isValidApiKeyFormat('google', '  AQ.Ab8RN6Lfake.key  \n')).toBe(true)
  })

  it.each([
    ['google', 'short'],
    ['google', '   '],
    ['openai', 'invalid-key-without-prefix'],
    ['openai', 'sk-short'],
    ['anthropic', 'sk-fakeKeyNotReal0123456789'],
    ['grok', 'fakeKeyNotReal0123456789'],
    ['deepinfra', 'short'],
    ['mistral', 'tooShort'],
    ['cohere', 'tooShort'],
    ['unknown', 'anything-long-enough-0123456789'],
  ])('rejects an invalid %s key', (provider, key) => {
    expect(isValidApiKeyFormat(provider, key)).toBe(false)
  })

  it('has a format rule for every listed provider', () => {
    for (const { id } of API_KEY_PROVIDERS) {
      expect(isValidApiKeyFormat(id, '')).toBe(false)
    }
  })
})

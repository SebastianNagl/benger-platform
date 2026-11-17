/**
 * Provider API key shape rules shared by the user and organization key forms.
 *
 * This is only a typo guard before saving. The real check is the provider
 * connection test, and the backend runs its own best-effort shape check
 * (`EncryptionService.is_valid_api_key_format` in
 * `services/shared/encryption_service.py`). These rules mirror that check
 * exactly: a known prefix where the provider has a stable one, plus a minimum
 * length. Never make them stricter than the backend, or a key the provider and
 * the backend accept gets rejected in the UI (Google's "AQ." keys contain dots
 * and were blocked by an older character-class regex).
 */

export type ApiKeyProviderId =
  | 'openai'
  | 'anthropic'
  | 'google'
  | 'deepinfra'
  | 'grok'
  | 'mistral'
  | 'cohere'

export interface ApiKeyProvider {
  id: ApiKeyProviderId
  name: string
  /** Key-format hint; empty means the generic "your <provider> key" text. */
  placeholder: string
}

interface ApiKeyFormatRule {
  prefix?: string
  minLength: number
}

const FORMAT_RULES: Record<ApiKeyProviderId, ApiKeyFormatRule> = {
  openai: { prefix: 'sk-', minLength: 16 },
  anthropic: { prefix: 'sk-ant-', minLength: 20 },
  google: { minLength: 11 },
  deepinfra: { minLength: 8 },
  grok: { prefix: 'xai-', minLength: 10 },
  mistral: { minLength: 20 },
  cohere: { minLength: 20 },
}

export const API_KEY_PROVIDERS: readonly ApiKeyProvider[] = [
  { id: 'openai', name: 'OpenAI', placeholder: 'sk-...' },
  { id: 'anthropic', name: 'Anthropic', placeholder: 'sk-ant-...' },
  { id: 'google', name: 'Google', placeholder: 'AQ.A... / AIza...' },
  { id: 'deepinfra', name: 'DeepInfra', placeholder: '' },
  { id: 'grok', name: 'Grok (xAI)', placeholder: 'xai-...' },
  { id: 'mistral', name: 'Mistral AI', placeholder: '' },
  { id: 'cohere', name: 'Cohere', placeholder: '' },
]

export function isValidApiKeyFormat(provider: string, apiKey: string): boolean {
  const rule = FORMAT_RULES[provider as ApiKeyProviderId]
  const key = apiKey.trim()
  if (!rule || !key) return false
  if (rule.prefix && !key.startsWith(rule.prefix)) return false
  return key.length >= rule.minLength
}

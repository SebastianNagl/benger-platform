/**
 * Provider API key shape rules shared by the user and organization key forms.
 *
 * This is only a typo guard before saving, applied to the trimmed key. The
 * real check is the provider connection test, and the backend runs its own
 * best-effort shape check (`EncryptionService.is_valid_api_key_format` in
 * `services/shared/encryption_service.py`). A rule here may be stricter than
 * the backend, but it must never reject a key that the provider and the
 * backend accept. Google mirrors the backend exactly (length only), because
 * its keys come in several shapes: legacy "AIza..." keys and newer "AQ." keys
 * that contain dots.
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

const FORMAT_RULES: Record<ApiKeyProviderId, (key: string) => boolean> = {
  openai: (key) => /^sk-[a-zA-Z0-9_-]{20,}$/.test(key),
  anthropic: (key) => /^sk-ant-[a-zA-Z0-9-_]{30,}$/.test(key),
  google: (key) => key.length >= 11,
  deepinfra: (key) => /^[a-zA-Z0-9]{20,}$/.test(key),
  grok: (key) => /^xai-[a-zA-Z0-9_-]{10,}$/.test(key),
  mistral: (key) => /^[a-zA-Z0-9]{20,}$/.test(key),
  cohere: (key) => /^[a-zA-Z0-9]{20,}$/.test(key),
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
  return rule(key)
}

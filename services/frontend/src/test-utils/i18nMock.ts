// Auto-generated i18n test helper
import enLocale from '../locales/en/common.json'

function flattenKeys(obj: Record<string, any>, prefix = ''): Record<string, string> {
  const result: Record<string, string> = {}
  for (const [key, value] of Object.entries(obj)) {
    const fullKey = prefix ? `${prefix}.${key}` : key
    if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
      Object.assign(result, flattenKeys(value, fullKey))
    } else {
      result[fullKey] = String(value)
    }
  }
  return result
}

const translations = flattenKeys(enLocale as Record<string, any>)

export function mockT(key: string, varsOrDefault?: any): string {
  let value = translations[key] || key
  if (varsOrDefault && typeof varsOrDefault === 'object') {
    for (const [varKey, varValue] of Object.entries(varsOrDefault)) {
      value = value.replace(new RegExp(`\\{${varKey}\\}`, 'g'), String(varValue))
    }
  }
  return value
}

export const mockUseI18n = () => ({
  t: mockT,
  locale: 'en' as const,
})

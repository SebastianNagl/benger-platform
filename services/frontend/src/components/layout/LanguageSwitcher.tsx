'use client'

import { useHydration } from '@/contexts/HydrationContext'
import { useI18n } from '@/contexts/I18nContext'

type Locale = 'de' | 'en'

const localeFlags = {
  de: '🇩🇪',
  en: '🇺🇸',
} as const

const localeNames = {
  de: 'Deutsch',
  en: 'English',
} as const

export function LanguageSwitcher({
  // The button's full class list — overridable so shells can restyle the
  // whole control (e.g. the student sidebar's full-width bordered variant)
  // with the entire styled area staying the click target.
  className = 'flex size-6 items-center justify-center rounded-md transition hover:bg-zinc-900/5 dark:hover:bg-white/5',
}: {
  className?: string
} = {}) {
  const { locale, changeLocale } = useI18n()
  const mounted = useHydration()

  if (!mounted) {
    return (
      <div className={className}>
        <span className="text-sm">🇩🇪</span>
      </div>
    )
  }

  // Handle undefined/null locale by defaulting to 'de'
  const safeLocale: Locale = locale && localeFlags[locale] ? locale : 'de'
  const currentFlag = localeFlags[safeLocale]
  const otherLocale: Locale = safeLocale === 'de' ? 'en' : 'de'

  const handleLanguageChange = () => {
    try {
      // Language switch: locale -> otherLocale
      changeLocale(otherLocale)
    } catch (error) {
      // Error changing language - silently handle
    }
  }

  return (
    <button
      type="button"
      className={className}
      aria-label={`Language: ${localeNames[safeLocale]} → ${localeNames[otherLocale]}`}
      onClick={handleLanguageChange}
      title={`Language: ${localeNames[safeLocale]} → ${localeNames[otherLocale]}`}
      data-testid="language-switcher"
    >
      <span className="pointer-fine:hidden absolute size-12" />
      <span className="text-sm" role="img" aria-label={localeNames[safeLocale]}>
        {currentFlag}
      </span>
    </button>
  )
}

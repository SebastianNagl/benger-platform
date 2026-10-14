'use client'

import { useHydration } from '@/contexts/HydrationContext'
import {
  subscribeTranslations,
  translateKey,
  type TranslationVars,
} from '@/lib/i18n/catalog'
import {
  DEFAULT_LOCALE,
  LOCALE_STORAGE_KEY,
  readStoredLocale,
  type Locale,
} from '@/lib/i18n/locales'
import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'

export type { Locale } from '@/lib/i18n/locales'

/**
 * Translate a catalog key. There is deliberately no inline default: every
 * string lives in the locale JSONs (src/locales/<locale>/ for the platform,
 * registerTranslations() for extensions).
 */
export type TranslateFn = (key: string, variables?: TranslationVars) => any

interface I18nContextType {
  locale: Locale
  t: TranslateFn
  changeLocale: (locale: Locale) => void
  isReady: boolean
}

const I18nContext = createContext<I18nContextType | undefined>(undefined)

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [locale, setLocale] = useState<Locale>(DEFAULT_LOCALE)
  // Bumped when an extension registers copy after the first render.
  const [catalogVersion, setCatalogVersion] = useState(0)
  const mounted = useHydration()
  const hasLoadedPreference = useRef(false)

  // Load stored preference after hydration
  useEffect(() => {
    if (!mounted || hasLoadedPreference.current) return
    hasLoadedPreference.current = true
    // eslint-disable-next-line react-hooks/set-state-in-effect -- Intentional: load preference on mount
    setLocale(readStoredLocale())
  }, [mounted])

  useEffect(
    () => subscribeTranslations(() => setCatalogVersion((v) => v + 1)),
    [],
  )

  // SSR and the first client render use the default locale so markup matches.
  const activeLocale = mounted ? locale : DEFAULT_LOCALE

  useEffect(() => {
    if (mounted) document.documentElement.lang = activeLocale
  }, [mounted, activeLocale])

  const t = useCallback<TranslateFn>(
    (key, variables) => translateKey(activeLocale, key, variables),
    // catalogVersion: new identity after a registration so memoized
    // consumers re-translate.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [activeLocale, catalogVersion],
  )

  const changeLocale = useCallback((newLocale: Locale) => {
    try {
      localStorage.setItem(LOCALE_STORAGE_KEY, newLocale)
    } catch {
      // localStorage unavailable: the choice holds for this session only
    }
    setLocale(newLocale)
  }, [])

  const value = useMemo<I18nContextType>(
    () =>
      mounted
        ? { locale: activeLocale, t, changeLocale, isReady: true }
        : { locale: activeLocale, t, changeLocale: () => {}, isReady: false },
    [mounted, activeLocale, t, changeLocale],
  )

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>
}

export function useI18n(): I18nContextType {
  const context = useContext(I18nContext)
  if (context === undefined) {
    // Outside the provider (isolated renders): translate with the default
    // locale so copy still resolves from the catalog.
    return {
      locale: DEFAULT_LOCALE,
      t: (key, variables) => translateKey(DEFAULT_LOCALE, key, variables),
      changeLocale: () => {},
      isReady: false,
    }
  }
  return context
}

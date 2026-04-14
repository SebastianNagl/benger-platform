'use client'

import { useHydration } from '@/contexts/HydrationContext'
import React, { createContext, useContext, useEffect, useRef, useState } from 'react'

// Load translations with fallback
let deTranslations: any = {}
let enTranslations: any = {}

try {
  // Try ES6 import first
  deTranslations = require('@/locales/de/common.json')
  enTranslations = require('@/locales/en/common.json')
} catch (error) {
  console.error('Failed to load translations with require:', error)
  // Fallback to empty objects
  deTranslations = {}
  enTranslations = {}
}

const translations = {
  de: deTranslations,
  en: enTranslations,
}

type Locale = 'de' | 'en'

interface I18nContextType {
  locale: Locale
  t: (key: string, defaultValueOrVariables?: string | Record<string, any>, variables?: Record<string, any>) => any
  changeLocale: (locale: Locale) => void
  isReady: boolean
}

const I18nContext = createContext<I18nContextType | undefined>(undefined)

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [locale, setLocale] = useState<Locale>('de')
  const mounted = useHydration()
  const hasLoadedPreference = useRef(false)

  // Load stored preference after hydration
  useEffect(() => {
    if (!mounted || hasLoadedPreference.current) return
    hasLoadedPreference.current = true

    try {
      const storedLocale = localStorage.getItem('preferred-locale') as Locale
      if (storedLocale && (storedLocale === 'de' || storedLocale === 'en')) {
        // eslint-disable-next-line react-hooks/set-state-in-effect -- Intentional: load preference on mount
        setLocale(storedLocale)
      }
    } catch (error) {
      // localStorage might not be available, ignore
      // Failed to load language preference from localStorage
    }
  }, [mounted])

  const t = (key: string, defaultValueOrVariables?: string | Record<string, any>, variables?: Record<string, any>): any => {
    // Determine if second arg is default value (string) or variables (object)
    let defaultValue: string | undefined
    let vars: Record<string, any> | undefined

    if (typeof defaultValueOrVariables === 'string') {
      defaultValue = defaultValueOrVariables
      vars = variables
    } else {
      vars = defaultValueOrVariables
    }

    try {
      const keys = key.split('.')
      let value: any = translations[locale]

      for (const k of keys) {
        value = value?.[k]
      }

      if (value === undefined) {
        return defaultValue ?? key
      }

      // Guard: if the resolved value is a plain object (branch node, not a leaf),
      // return the key string to prevent React error #31 (object as child).
      // Arrays are allowed since some translations are intentionally arrays.
      if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
        return defaultValue ?? key
      }

      // Handle variable interpolation
      if (vars && typeof value === 'string') {
        return value.replace(/\{(\w+)\}/g, (match, variableName) => {
          return vars[variableName] !== undefined
            ? String(vars[variableName])
            : match
        })
      }

      return value
    } catch (error) {
      console.error('Translation error for key', key, error)
      return key
    }
  }

  const changeLocale = (newLocale: Locale) => {
    try {
      localStorage.setItem('preferred-locale', newLocale)
      setLocale(newLocale)
    } catch (error) {
      // Failed to save language preference - continue with locale change
      setLocale(newLocale)
    }
  }

  // Return default translations during SSR/hydration
  if (!mounted) {
    const defaultT = (key: string, defaultValueOrVariables?: string | Record<string, any>, variables?: Record<string, any>): any => {
      // Determine if second arg is default value (string) or variables (object)
      let defaultValue: string | undefined
      let vars: Record<string, any> | undefined

      if (typeof defaultValueOrVariables === 'string') {
        defaultValue = defaultValueOrVariables
        vars = variables
      } else {
        vars = defaultValueOrVariables
      }

      try {
        const keys = key.split('.')
        let value: any = translations['de'] // Use German as default

        for (const k of keys) {
          value = value?.[k]
        }

        if (value === undefined) {
          return defaultValue ?? key
        }

        // Handle variable interpolation
        if (vars && typeof value === 'string') {
          return value.replace(/\{(\w+)\}/g, (match, variableName) => {
            return vars[variableName] !== undefined
              ? String(vars[variableName])
              : match
          })
        }

        return value
      } catch (error) {
        // SSR Translation error for key - return key as fallback
        return defaultValue ?? key
      }
    }

    return (
      <I18nContext.Provider
        value={{
          locale: 'de',
          t: defaultT,
          changeLocale: () => {},
          isReady: false,
        }}
      >
        {children}
      </I18nContext.Provider>
    )
  }

  return (
    <I18nContext.Provider value={{ locale, t, changeLocale, isReady: true }}>
      {children}
    </I18nContext.Provider>
  )
}

export function useI18n() {
  const context = useContext(I18nContext)
  if (context === undefined) {
    // Provide a fallback for cases where the hook is called outside of provider
    // useI18n called outside of I18nProvider, using fallback
    return {
      locale: 'de' as Locale,
      t: (key: string, defaultValueOrVariables?: string | Record<string, any>) =>
        typeof defaultValueOrVariables === 'string' ? defaultValueOrVariables : key,
      changeLocale: () => {},
      isReady: false,
    }
  }
  return context
}

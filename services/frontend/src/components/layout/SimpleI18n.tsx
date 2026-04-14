'use client'

import React, { createContext, useContext, useState } from 'react'

// Simple static translations to avoid webpack issues
const translations = {
  de: {
    navigation: {
      dashboard: 'Dashboard',
      tasks: 'Aufgaben',
      about: 'Über uns',
    },
    common: {
      loading: 'Lädt...',
      save: 'Speichern',
      cancel: 'Abbrechen',
    },
  },
  en: {
    navigation: {
      dashboard: 'Dashboard',
      tasks: 'Tasks',
      about: 'About',
    },
    common: {
      loading: 'Loading...',
      save: 'Save',
      cancel: 'Cancel',
    },
  },
}

type Locale = 'de' | 'en'

interface I18nContextType {
  locale: Locale
  t: (key: string) => string
  changeLocale: (locale: Locale) => void
}

const I18nContext = createContext<I18nContextType | undefined>(undefined)

export function useI18n() {
  const context = useContext(I18nContext)
  if (!context) {
    throw new Error('useI18n must be used within an I18nProvider')
  }
  return context
}

export function SimpleI18nProvider({
  children,
}: {
  children: React.ReactNode
}) {
  const [locale, setLocale] = useState<Locale>('en')

  const t = (key: string): string => {
    const keys = key.split('.')
    let value: any = translations[locale]

    for (const k of keys) {
      value = value?.[k]
      if (!value) break
    }

    return value || key
  }

  const changeLocale = (newLocale: Locale) => {
    setLocale(newLocale)
    if (typeof window !== 'undefined') {
      localStorage.setItem('locale', newLocale)
    }
  }

  return (
    <I18nContext.Provider value={{ locale, t, changeLocale }}>
      {children}
    </I18nContext.Provider>
  )
}

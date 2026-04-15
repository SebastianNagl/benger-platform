import { renderWithProviders } from '@/test-utils'
import '@testing-library/jest-dom'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import React from 'react'

// Mock I18n context
const createI18nContext = (locale: string) => ({
  t: (key: string) => {
    const translations: Record<string, Record<string, string>> = {
      en: {
        'common.projects': 'Projects',
        'common.login': 'Login',
        'common.logout': 'Logout',
        'common.save': 'Save',
        'common.cancel': 'Cancel',
        'common.delete': 'Delete',
        'common.edit': 'Edit',
        'common.search': 'Search',
        'common.loading': 'Loading...',
        'projects.title': 'My Projects',
        'projects.create': 'Create Project',
        'projects.noProjects': 'No projects found',
        'annotations.title': 'Annotations',
        'annotations.submit': 'Submit Annotation',
        'annotations.skip': 'Skip',
        'annotations.next': 'Next Task',
        'annotations.previous': 'Previous Task',
        'auth.login': 'Sign In',
        'auth.register': 'Sign Up',
        'auth.forgotPassword': 'Forgot Password?',
        'date.format': 'MM/DD/YYYY',
        'number.format': '1,234.56',
        'currency.format': '$1,234.56',
      },
      de: {
        'common.projects': 'Projekte',
        'common.login': 'Anmelden',
        'common.logout': 'Abmelden',
        'common.save': 'Speichern',
        'common.cancel': 'Abbrechen',
        'common.delete': 'Löschen',
        'common.edit': 'Bearbeiten',
        'common.search': 'Suchen',
        'common.loading': 'Laden...',
        'projects.title': 'Meine Projekte',
        'projects.create': 'Projekt erstellen',
        'projects.noProjects': 'Keine Projekte gefunden',
        'annotations.title': 'Annotationen',
        'annotations.submit': 'Annotation einreichen',
        'annotations.skip': 'Überspringen',
        'annotations.next': 'Nächste Aufgabe',
        'annotations.previous': 'Vorherige Aufgabe',
        'auth.login': 'Einloggen',
        'auth.register': 'Registrieren',
        'auth.forgotPassword': 'Passwort vergessen?',
        'date.format': 'DD.MM.YYYY',
        'number.format': '1.234,56',
        'currency.format': '1.234,56 €',
      },
      ar: {
        'common.projects': 'المشاريع',
        'common.login': 'تسجيل الدخول',
        'common.logout': 'تسجيل الخروج',
        'common.save': 'حفظ',
        'common.cancel': 'إلغاء',
        'common.delete': 'حذف',
        'common.edit': 'تعديل',
        'common.search': 'بحث',
        'common.loading': 'جاري التحميل...',
        'projects.title': 'مشاريعي',
        'projects.create': 'إنشاء مشروع',
        'projects.noProjects': 'لم يتم العثور على مشاريع',
        'annotations.title': 'التعليقات التوضيحية',
        'annotations.submit': 'إرسال التعليق',
        'annotations.skip': 'تخطي',
        'annotations.next': 'المهمة التالية',
        'annotations.previous': 'المهمة السابقة',
        'auth.login': 'دخول',
        'auth.register': 'تسجيل',
        'auth.forgotPassword': 'نسيت كلمة المرور؟',
        'date.format': 'YYYY/MM/DD',
        'number.format': '١٬٢٣٤٫٥٦',
        'currency.format': '١٬٢٣٤٫٥٦ ر.س',
      },
    }

    return translations[locale]?.[key] || key
  },
  locale,
  changeLanguage: jest.fn(),
  languages: ['en', 'de', 'ar'],
  direction: locale === 'ar' ? 'rtl' : 'ltr',
})

// Components that use translations
const Navigation = ({ t }: any) => (
  <nav>
    <ul>
      <li>{t('common.projects')}</li>
      <li>{t('common.login')}</li>
    </ul>
  </nav>
)

const ProjectList = ({ t }: any) => (
  <div>
    <h1>{t('projects.title')}</h1>
    <button>{t('projects.create')}</button>
    <p>{t('projects.noProjects')}</p>
  </div>
)

const AnnotationInterface = ({ t }: any) => (
  <div>
    <h1>{t('annotations.title')}</h1>
    <button>{t('annotations.submit')}</button>
    <button>{t('annotations.skip')}</button>
    <button>{t('annotations.next')}</button>
    <button>{t('annotations.previous')}</button>
  </div>
)

const DateDisplay = ({ date, locale }: any) => {
  const formatDate = (date: Date, locale: string) => {
    const options: Intl.DateTimeFormatOptions = {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    }

    if (locale === 'de') {
      return date.toLocaleDateString('de-DE', options)
    } else if (locale === 'ar') {
      return date.toLocaleDateString('ar-SA', options)
    } else {
      return date.toLocaleDateString('en-US', options)
    }
  }

  return <span>{formatDate(date, locale)}</span>
}

const NumberDisplay = ({ value, locale }: any) => {
  const formatNumber = (value: number, locale: string) => {
    if (locale === 'de') {
      return value.toLocaleString('de-DE')
    } else if (locale === 'ar') {
      return value.toLocaleString('ar-SA')
    } else {
      return value.toLocaleString('en-US')
    }
  }

  return <span>{formatNumber(value, locale)}</span>
}

const CurrencyDisplay = ({ amount, locale }: any) => {
  const formatCurrency = (amount: number, locale: string) => {
    const options: Intl.NumberFormatOptions = {
      style: 'currency',
      currency: locale === 'de' ? 'EUR' : locale === 'ar' ? 'SAR' : 'USD',
    }

    if (locale === 'de') {
      return amount.toLocaleString('de-DE', options)
    } else if (locale === 'ar') {
      return amount.toLocaleString('ar-SA', options)
    } else {
      return amount.toLocaleString('en-US', options)
    }
  }

  return <span>{formatCurrency(amount, locale)}</span>
}

const LanguageSwitcher = ({ currentLanguage, onLanguageChange }: any) => (
  <select
    value={currentLanguage}
    onChange={(e) => onLanguageChange(e.target.value)}
    aria-label="Language selector"
  >
    <option value="en">English</option>
    <option value="de">Deutsch</option>
    <option value="ar">العربية</option>
  </select>
)

describe('Internationalization (i18n)', () => {
  describe('Language Switching', () => {
    it('renders content in English', () => {
      const i18n = createI18nContext('en')

      renderWithProviders(
        <div>
          <Navigation t={i18n.t} />
          <ProjectList t={i18n.t} />
        </div>
      )

      expect(screen.getByText('Projects')).toBeInTheDocument()
      expect(screen.getByText('Login')).toBeInTheDocument()
      expect(screen.getByText('My Projects')).toBeInTheDocument()
      expect(screen.getByText('Create Project')).toBeInTheDocument()
    })

    it('renders content in German', () => {
      const i18n = createI18nContext('de')

      renderWithProviders(
        <div>
          <Navigation t={i18n.t} />
          <ProjectList t={i18n.t} />
        </div>
      )

      expect(screen.getByText('Projekte')).toBeInTheDocument()
      expect(screen.getByText('Anmelden')).toBeInTheDocument()
      expect(screen.getByText('Meine Projekte')).toBeInTheDocument()
      expect(screen.getByText('Projekt erstellen')).toBeInTheDocument()
    })

    it('renders content in Arabic', () => {
      const i18n = createI18nContext('ar')

      renderWithProviders(
        <div>
          <Navigation t={i18n.t} />
          <ProjectList t={i18n.t} />
        </div>
      )

      expect(screen.getByText('المشاريع')).toBeInTheDocument()
      expect(screen.getByText('تسجيل الدخول')).toBeInTheDocument()
      expect(screen.getByText('مشاريعي')).toBeInTheDocument()
      expect(screen.getByText('إنشاء مشروع')).toBeInTheDocument()
    })

    it('switches language dynamically', async () => {
      const user = userEvent.setup()

      const TestComponent = () => {
        const [locale, setLocale] = React.useState('en')
        const i18n = createI18nContext(locale)

        return (
          <div>
            <LanguageSwitcher
              currentLanguage={locale}
              onLanguageChange={setLocale}
            />
            <Navigation t={i18n.t} />
          </div>
        )
      }

      renderWithProviders(<TestComponent />)

      // Initially in English
      expect(screen.getByText('Projects')).toBeInTheDocument()

      // Switch to German
      const select = screen.getByLabelText('Language selector')
      await user.selectOptions(select, 'de')

      await waitFor(() => {
        expect(screen.getByText('Projekte')).toBeInTheDocument()
      })

      // Switch to Arabic
      await user.selectOptions(select, 'ar')

      await waitFor(() => {
        expect(screen.getByText('المشاريع')).toBeInTheDocument()
      })
    })
  })

  describe('RTL Support', () => {
    it('applies RTL layout for Arabic', () => {
      const i18n = createI18nContext('ar')

      const { container } = renderWithProviders(
        <div dir={i18n.direction}>
          <Navigation t={i18n.t} />
        </div>
      )

      expect(container.firstChild).toHaveAttribute('dir', 'rtl')
    })

    it('applies LTR layout for English and German', () => {
      const i18nEn = createI18nContext('en')
      const i18nDe = createI18nContext('de')

      const { container: containerEn } = renderWithProviders(
        <div dir={i18nEn.direction}>
          <Navigation t={i18nEn.t} />
        </div>
      )

      const { container: containerDe } = renderWithProviders(
        <div dir={i18nDe.direction}>
          <Navigation t={i18nDe.t} />
        </div>
      )

      expect(containerEn.firstChild).toHaveAttribute('dir', 'ltr')
      expect(containerDe.firstChild).toHaveAttribute('dir', 'ltr')
    })
  })

  describe('Date Formatting', () => {
    it('formats dates according to locale', () => {
      const testDate = new Date('2024-01-15')

      const { rerender } = renderWithProviders(
        <DateDisplay date={testDate} locale="en" />
      )

      // US format
      expect(screen.getByText('01/15/2024')).toBeInTheDocument()

      // German format
      rerender(<DateDisplay date={testDate} locale="de" />)
      expect(screen.getByText('15.01.2024')).toBeInTheDocument()

      // Arabic format - check that the date content changes
      rerender(<DateDisplay date={testDate} locale="ar" />)
      // Arabic date format may use Arabic numerals, just verify content exists and is different from German
      expect(screen.queryByText('15.01.2024')).not.toBeInTheDocument()
      // Verify some date format is rendered by checking the span element exists
      expect(screen.getByText(/\S+/)).toBeInTheDocument()
    })
  })

  describe('Number Formatting', () => {
    it('formats numbers according to locale', () => {
      const { rerender } = renderWithProviders(
        <NumberDisplay value={1234.56} locale="en" />
      )

      // US format
      expect(screen.getByText('1,234.56')).toBeInTheDocument()

      // German format
      rerender(<NumberDisplay value={1234.56} locale="de" />)
      expect(screen.getByText('1.234,56')).toBeInTheDocument()
    })

    it('formats large numbers correctly', () => {
      const { rerender } = renderWithProviders(
        <NumberDisplay value={1000000} locale="en" />
      )

      expect(screen.getByText('1,000,000')).toBeInTheDocument()

      rerender(<NumberDisplay value={1000000} locale="de" />)
      expect(screen.getByText('1.000.000')).toBeInTheDocument()
    })
  })

  describe('Currency Formatting', () => {
    it('formats currency according to locale', () => {
      const { rerender } = renderWithProviders(
        <CurrencyDisplay amount={1234.56} locale="en" />
      )

      // US format
      expect(screen.getByText('$1,234.56')).toBeInTheDocument()

      // German format (EUR)
      rerender(<CurrencyDisplay amount={1234.56} locale="de" />)
      // Note: Exact format may vary by system
      expect(screen.getByText(/1\.234,56/)).toBeInTheDocument()
      expect(screen.getByText(/€/)).toBeInTheDocument()
    })
  })

  describe('Translation Fallbacks', () => {
    it('falls back to key when translation is missing', () => {
      const i18n = createI18nContext('en')

      const ComponentWithMissingTranslation = () => (
        <div>{i18n.t('missing.translation.key')}</div>
      )

      renderWithProviders(<ComponentWithMissingTranslation />)

      expect(screen.getByText('missing.translation.key')).toBeInTheDocument()
    })
  })

  describe('Translation Interpolation', () => {
    it('supports variable interpolation', () => {
      const i18nWithInterpolation = {
        t: (key: string, variables?: Record<string, any>) => {
          const templates: Record<string, string> = {
            'welcome.message': 'Welcome, {{name}}!',
            'items.count': 'You have {{count}} items',
          }

          let result = templates[key] || key

          if (variables) {
            Object.entries(variables).forEach(([key, value]) => {
              result = result.replace(`{{${key}}}`, String(value))
            })
          }

          return result
        },
      }

      const WelcomeMessage = () => (
        <div>
          {i18nWithInterpolation.t('welcome.message', { name: 'John' })}
        </div>
      )

      const ItemCount = () => (
        <div>{i18nWithInterpolation.t('items.count', { count: 5 })}</div>
      )

      renderWithProviders(
        <div>
          <WelcomeMessage />
          <ItemCount />
        </div>
      )

      expect(screen.getByText('Welcome, John!')).toBeInTheDocument()
      expect(screen.getByText('You have 5 items')).toBeInTheDocument()
    })
  })

  describe('Pluralization', () => {
    it('handles plural forms correctly', () => {
      const i18nWithPlurals = {
        t: (key: string, options?: { count?: number }) => {
          const plurals: Record<string, (count: number) => string> = {
            'tasks.remaining': (count: number) => {
              if (count === 0) return 'No tasks remaining'
              if (count === 1) return '1 task remaining'
              return `${count} tasks remaining`
            },
          }

          if (plurals[key] && options?.count !== undefined) {
            return plurals[key](options.count)
          }

          return key
        },
      }

      const TaskCount = ({ count }: { count: number }) => (
        <div>{i18nWithPlurals.t('tasks.remaining', { count })}</div>
      )

      const { rerender } = renderWithProviders(<TaskCount count={0} />)
      expect(screen.getByText('No tasks remaining')).toBeInTheDocument()

      rerender(<TaskCount count={1} />)
      expect(screen.getByText('1 task remaining')).toBeInTheDocument()

      rerender(<TaskCount count={5} />)
      expect(screen.getByText('5 tasks remaining')).toBeInTheDocument()
    })
  })

  describe('Language Persistence', () => {
    it('persists language preference', () => {
      const mockLocalStorage = {
        getItem: jest.fn(),
        setItem: jest.fn(),
        clear: jest.fn(),
      }

      Object.defineProperty(window, 'localStorage', {
        value: mockLocalStorage,
        writable: true,
      })

      const TestComponent = () => {
        const [locale, setLocale] = React.useState(() => {
          return mockLocalStorage.getItem('language') || 'en'
        })

        const handleLanguageChange = (newLocale: string) => {
          setLocale(newLocale)
          mockLocalStorage.setItem('language', newLocale)
        }

        return (
          <LanguageSwitcher
            currentLanguage={locale}
            onLanguageChange={handleLanguageChange}
          />
        )
      }

      renderWithProviders(<TestComponent />)

      const select = screen.getByLabelText('Language selector')
      fireEvent.change(select, { target: { value: 'de' } })

      expect(mockLocalStorage.setItem).toHaveBeenCalledWith('language', 'de')
    })
  })

  describe('Translation Keys Organization', () => {
    it('uses namespace-based keys', () => {
      const i18n = createI18nContext('en')

      // Test that keys are organized by namespace
      expect(i18n.t('common.save')).toBe('Save')
      expect(i18n.t('projects.title')).toBe('My Projects')
      expect(i18n.t('annotations.submit')).toBe('Submit Annotation')
      expect(i18n.t('auth.login')).toBe('Sign In')
    })
  })
})

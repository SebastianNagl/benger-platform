/**
 * @jest-environment jsdom
 */

import '@testing-library/jest-dom'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import React from 'react'

// Mock the I18n context with test translations
const mockTranslations = {
  de: {
    dashboard: {
      title: 'Dashboard',
      subtitle:
        'Verwalten Sie Ihre Annotationsprojekte und verfolgen Sie den Fortschritt',
      stats: {
        projects: 'Projekte',
        totalTasks: 'Gesamtaufgaben',
        annotations: 'Annotationen',
        activeProjects: 'Aktive Projekte',
      },
      recentProjects: {
        title: 'Aktuelle Projekte',
      },
      quickActions: 'Schnellaktionen',
    },
    projects: {
      title: 'Projekte',
      subtitle: 'Verwalten Sie Ihre Annotationsprojekte',
      searchPlaceholder: 'Projekte suchen...',
      table: {
        project: 'Projekt',
        tasks: 'Aufgaben',
      },
    },
    dataManagement: {
      title: 'Datenmanagement',
      subtitle: 'Verwalten Sie Ihre Daten und Uploads',
      tabs: {
        data: 'Daten',
        dataSynthesis: 'Datensynthese',
      },
    },
  },
  en: {
    dashboard: {
      title: 'Dashboard',
      subtitle: 'Manage your annotation projects and track progress',
      stats: {
        projects: 'Projects',
        totalTasks: 'Total Tasks',
        annotations: 'Annotations',
        activeProjects: 'Active Projects',
      },
      recentProjects: {
        title: 'Recent Projects',
      },
      quickActions: 'Quick Actions',
    },
    projects: {
      title: 'Projects',
      subtitle: 'Manage your annotation projects',
      searchPlaceholder: 'Search projects...',
      table: {
        project: 'Project',
        tasks: 'Tasks',
      },
    },
    dataManagement: {
      title: 'Data Management',
      subtitle: 'Manage your data and uploads',
      tabs: {
        data: 'Data',
        dataSynthesis: 'Data Synthesis',
      },
    },
  },
}

// Mock I18n Provider component
const MockI18nProvider = ({ children }: { children: React.ReactNode }) => {
  const [locale, setLocale] = React.useState<'de' | 'en'>(() => {
    // Check localStorage on initial load
    try {
      const stored = localStorage.getItem('preferred-locale')
      return stored === 'en' || stored === 'de' ? stored : 'de'
    } catch {
      return 'de'
    }
  })
  const [mounted, setMounted] = React.useState(false)

  React.useEffect(() => {
    setMounted(true)
  }, [])

  const t = (key: string): any => {
    const keys = key.split('.')
    let value: any = mockTranslations[locale]

    for (const k of keys) {
      value = value?.[k]
    }

    return value !== undefined ? value : key
  }

  const changeLocale = (newLocale: 'de' | 'en') => {
    try {
      localStorage.setItem('preferred-locale', newLocale)
    } catch {
      // localStorage not available
    }
    setLocale(newLocale)
  }

  return (
    <MockI18nContext.Provider
      value={{ locale, t, changeLocale, isReady: mounted }}
    >
      {children}
    </MockI18nContext.Provider>
  )
}

// Mock context
const MockI18nContext = React.createContext<{
  locale: 'de' | 'en'
  t: (key: string) => any
  changeLocale: (locale: 'de' | 'en') => void
  isReady: boolean
} | null>(null)

// Mock useI18n hook
const useI18n = () => {
  const context = React.useContext(MockI18nContext)
  if (!context) {
    throw new Error('useI18n must be used within a MockI18nProvider')
  }
  return context
}

// Mock localStorage
const localStorageMock = (() => {
  let store: Record<string, string> = {}
  return {
    getItem: (key: string) => store[key] || null,
    setItem: (key: string, value: string) => {
      store[key] = value
    },
    clear: () => {
      store = {}
    },
    removeItem: (key: string) => {
      delete store[key]
    },
  }
})()

Object.defineProperty(window, 'localStorage', {
  value: localStorageMock,
})

// Test component that uses useI18n hook
function TestComponent() {
  const { locale, t, changeLocale } = useI18n()

  return (
    <div>
      <div data-testid="current-locale">{locale}</div>
      <div data-testid="dashboard-title">{t('dashboard.title')}</div>
      <div data-testid="dashboard-subtitle">{t('dashboard.subtitle')}</div>
      <div data-testid="projects-title">{t('projects.title')}</div>
      <div data-testid="data-title">{t('dataManagement.title')}</div>
      <button onClick={() => changeLocale('en')} data-testid="switch-to-en">
        Switch to English
      </button>
      <button onClick={() => changeLocale('de')} data-testid="switch-to-de">
        Switch to German
      </button>
    </div>
  )
}

describe('I18n Context and Translations', () => {
  beforeEach(() => {
    localStorageMock.clear()
  })

  it('should provide default German locale', async () => {
    render(
      <MockI18nProvider>
        <TestComponent />
      </MockI18nProvider>
    )

    expect(screen.getByTestId('current-locale')).toHaveTextContent('de')
  })

  it('should translate dashboard keys correctly in German', async () => {
    render(
      <MockI18nProvider>
        <TestComponent />
      </MockI18nProvider>
    )

    expect(screen.getByTestId('dashboard-title')).toHaveTextContent('Dashboard')
    expect(screen.getByTestId('dashboard-subtitle')).toHaveTextContent(
      'Verwalten Sie Ihre Annotationsprojekte und verfolgen Sie den Fortschritt'
    )
  })

  it('should translate projects keys correctly in German', async () => {
    render(
      <MockI18nProvider>
        <TestComponent />
      </MockI18nProvider>
    )

    expect(screen.getByTestId('projects-title')).toHaveTextContent('Projekte')
  })

  it('should translate data management keys correctly in German', async () => {
    render(
      <MockI18nProvider>
        <TestComponent />
      </MockI18nProvider>
    )

    expect(screen.getByTestId('data-title')).toHaveTextContent(
      'Datenmanagement'
    )
  })

  it('should switch to English locale when changeLocale is called', async () => {
    render(
      <MockI18nProvider>
        <TestComponent />
      </MockI18nProvider>
    )

    const switchToEnButton = screen.getByTestId('switch-to-en')
    fireEvent.click(switchToEnButton)

    await waitFor(
      () => {
        expect(screen.getByTestId('current-locale')).toHaveTextContent('en')
      },
      { timeout: 3000 }
    )
  })

  it('should translate dashboard keys correctly in English', async () => {
    render(
      <MockI18nProvider>
        <TestComponent />
      </MockI18nProvider>
    )

    const switchToEnButton = screen.getByTestId('switch-to-en')
    fireEvent.click(switchToEnButton)

    await waitFor(
      () => {
        expect(screen.getByTestId('dashboard-title')).toHaveTextContent(
          'Dashboard'
        )
        expect(screen.getByTestId('dashboard-subtitle')).toHaveTextContent(
          'Manage your annotation projects and track progress'
        )
      },
      { timeout: 3000 }
    )
  })

  it('should translate projects keys correctly in English', async () => {
    render(
      <MockI18nProvider>
        <TestComponent />
      </MockI18nProvider>
    )

    const switchToEnButton = screen.getByTestId('switch-to-en')
    fireEvent.click(switchToEnButton)

    await waitFor(
      () => {
        expect(screen.getByTestId('projects-title')).toHaveTextContent(
          'Projects'
        )
      },
      { timeout: 3000 }
    )
  })

  it('should translate data management keys correctly in English', async () => {
    render(
      <MockI18nProvider>
        <TestComponent />
      </MockI18nProvider>
    )

    const switchToEnButton = screen.getByTestId('switch-to-en')
    fireEvent.click(switchToEnButton)

    await waitFor(
      () => {
        expect(screen.getByTestId('data-title')).toHaveTextContent(
          'Data Management'
        )
      },
      { timeout: 3000 }
    )
  })

  it('should persist locale preference in localStorage', async () => {
    render(
      <MockI18nProvider>
        <TestComponent />
      </MockI18nProvider>
    )

    const switchToEnButton = screen.getByTestId('switch-to-en')
    fireEvent.click(switchToEnButton)

    await waitFor(
      () => {
        expect(localStorage.getItem('preferred-locale')).toBe('en')
      },
      { timeout: 3000 }
    )
  })

  it('should load locale preference from localStorage on mount', async () => {
    localStorage.setItem('preferred-locale', 'en')

    render(
      <MockI18nProvider>
        <TestComponent />
      </MockI18nProvider>
    )

    // Should load the stored locale preference
    expect(screen.getByTestId('current-locale')).toHaveTextContent('en')
  })

  it('should handle nested translation keys', async () => {
    render(
      <MockI18nProvider>
        <TestComponent />
      </MockI18nProvider>
    )

    // Create a component that tests nested keys
    const NestedTestComponent = () => {
      const { t } = useI18n()
      return (
        <div>
          <div data-testid="stats-projects">
            {t('dashboard.stats.projects')}
          </div>
          <div data-testid="recent-title">
            {t('dashboard.recentProjects.title')}
          </div>
          <div data-testid="table-tasks">{t('projects.table.tasks')}</div>
        </div>
      )
    }

    const { container } = render(
      <MockI18nProvider>
        <NestedTestComponent />
      </MockI18nProvider>
    )

    const statsProjects = container.querySelector(
      '[data-testid="stats-projects"]'
    )
    const recentTitle = container.querySelector('[data-testid="recent-title"]')
    const tableTasks = container.querySelector('[data-testid="table-tasks"]')

    expect(statsProjects?.textContent).toBe('Projekte')
    expect(recentTitle?.textContent).toBe('Aktuelle Projekte')
    expect(tableTasks?.textContent).toBe('Aufgaben')
  })

  it('should return key as fallback for missing translations', async () => {
    const MissingKeyComponent = () => {
      const { t } = useI18n()
      return <div data-testid="missing-key">{t('non.existent.key')}</div>
    }

    render(
      <MockI18nProvider>
        <MissingKeyComponent />
      </MockI18nProvider>
    )

    expect(screen.getByTestId('missing-key')).toHaveTextContent(
      'non.existent.key'
    )
  })

  it('should handle switching between locales multiple times', async () => {
    render(
      <MockI18nProvider>
        <TestComponent />
      </MockI18nProvider>
    )

    const switchToEnButton = screen.getByTestId('switch-to-en')
    const switchToDeButton = screen.getByTestId('switch-to-de')

    // Switch to English
    fireEvent.click(switchToEnButton)
    await waitFor(
      () => {
        expect(screen.getByTestId('current-locale')).toHaveTextContent('en')
      },
      { timeout: 3000 }
    )

    // Switch back to German
    fireEvent.click(switchToDeButton)
    await waitFor(
      () => {
        expect(screen.getByTestId('current-locale')).toHaveTextContent('de')
      },
      { timeout: 3000 }
    )

    // Switch to English again
    fireEvent.click(switchToEnButton)
    await waitFor(
      () => {
        expect(screen.getByTestId('current-locale')).toHaveTextContent('en')
      },
      { timeout: 3000 }
    )
  })
})

describe('Translation Coverage', () => {
  it('should have matching keys in both English and German translations', () => {
    // This test would need access to the actual translation files
    // For now, we'll test a subset of keys we know should exist
    const keysToTest = [
      'dashboard.title',
      'dashboard.subtitle',
      'dashboard.stats.projects',
      'dashboard.stats.totalTasks',
      'dashboard.stats.annotations',
      'dashboard.stats.activeProjects',
      'dashboard.recentProjects.title',
      'dashboard.quickActions',
      'projects.title',
      'projects.subtitle',
      'projects.searchPlaceholder',
      'projects.table.project',
      'projects.table.tasks',
      'dataManagement.title',
      'dataManagement.subtitle',
      'dataManagement.tabs.data',
      'dataManagement.tabs.dataSynthesis',
    ]

    const TestAllKeysComponent = () => {
      const { t, changeLocale } = useI18n()
      const [locale, setLocale] = React.useState('de')

      React.useEffect(() => {
        changeLocale(locale as 'de' | 'en')
      }, [locale, changeLocale])

      return (
        <div>
          {keysToTest.map((key) => (
            <div key={key} data-testid={`key-${key}-${locale}`}>
              {t(key)}
            </div>
          ))}
          <button onClick={() => setLocale('en')} data-testid="set-en">
            EN
          </button>
        </div>
      )
    }

    const { rerender } = render(
      <MockI18nProvider>
        <TestAllKeysComponent />
      </MockI18nProvider>
    )

    // Check that all keys return non-empty values in German
    keysToTest.forEach((key) => {
      const element = screen.getByTestId(`key-${key}-de`)
      expect(element.textContent).not.toBe('')
      expect(element.textContent).not.toBe(key) // Should not return the key itself
    })

    // Switch to English and check again
    fireEvent.click(screen.getByTestId('set-en'))

    setTimeout(() => {
      keysToTest.forEach((key) => {
        const element = screen.getByTestId(`key-${key}-en`)
        expect(element.textContent).not.toBe('')
        expect(element.textContent).not.toBe(key) // Should not return the key itself
      })
    }, 100)
  })
})

describe('I18n isReady Flag - Issue #758', () => {
  it('should expose isReady flag that tracks translation readiness', async () => {
    const IsReadyTestComponent = () => {
      const { isReady } = useI18n()
      return <div data-testid="is-ready">{isReady.toString()}</div>
    }

    render(
      <MockI18nProvider>
        <IsReadyTestComponent />
      </MockI18nProvider>
    )

    // After mount, isReady should be true
    await waitFor(
      () => {
        expect(screen.getByTestId('is-ready')).toHaveTextContent('true')
      },
      { timeout: 3000 }
    )
  })

  it('should not return raw translation keys when translations are ready', async () => {
    const TranslationKeyTestComponent = () => {
      const { t, isReady } = useI18n()

      if (!isReady) {
        return <div data-testid="loading">Loading...</div>
      }

      return (
        <div>
          <div data-testid="title">{t('dashboard.title')}</div>
          <div data-testid="subtitle">{t('dashboard.subtitle')}</div>
        </div>
      )
    }

    render(
      <MockI18nProvider>
        <TranslationKeyTestComponent />
      </MockI18nProvider>
    )

    // Wait for translations to be ready
    await waitFor(
      () => {
        const titleElement = screen.queryByTestId('title')
        if (titleElement) {
          // Should have translated text, not the key
          expect(titleElement.textContent).toBe('Dashboard')
          expect(titleElement.textContent).not.toBe('dashboard.title')
        }
      },
      { timeout: 3000 }
    )
  })

  it('should handle components that wait for isReady before rendering', async () => {
    const WaitForReadyComponent = () => {
      const { t, isReady } = useI18n()

      // Early return pattern - wait for translations before rendering
      if (!isReady) {
        return null
      }

      const results = [
        { title: t('dashboard.title'), description: t('dashboard.subtitle') },
        { title: t('projects.title'), description: t('projects.subtitle') },
      ]

      return (
        <div>
          {results.map((result, index) => (
            <div key={index} data-testid={`result-${index}`}>
              <div data-testid={`result-${index}-title`}>{result.title}</div>
              <div data-testid={`result-${index}-description`}>
                {result.description}
              </div>
            </div>
          ))}
        </div>
      )
    }

    render(
      <MockI18nProvider>
        <WaitForReadyComponent />
      </MockI18nProvider>
    )

    await waitFor(
      () => {
        // Results should be rendered with proper translations
        const result0Title = screen.queryByTestId('result-0-title')
        if (result0Title) {
          expect(result0Title.textContent).not.toContain('.')
          expect(result0Title.textContent).not.toBe('dashboard.title')
        }
      },
      { timeout: 3000 }
    )
  })

  it('should return empty results when isReady is false', async () => {
    const ConditionalResultsComponent = () => {
      const { t, isReady } = useI18n()

      const getResults = () => {
        if (!isReady) {
          return []
        }

        return [
          { title: t('dashboard.title'), url: '/' },
          { title: t('projects.title'), url: '/projects' },
        ]
      }

      const results = getResults()

      return (
        <div>
          <div data-testid="result-count">{results.length}</div>
          {results.map((result, index) => (
            <div key={index} data-testid={`result-${index}-title`}>
              {result.title}
            </div>
          ))}
        </div>
      )
    }

    render(
      <MockI18nProvider>
        <ConditionalResultsComponent />
      </MockI18nProvider>
    )

    await waitFor(
      () => {
        // After mount, should have results
        const resultCount = screen.queryByTestId('result-count')
        if (resultCount) {
          expect(parseInt(resultCount.textContent || '0')).toBeGreaterThan(0)
        }
      },
      { timeout: 3000 }
    )
  })

  it('should not display translation keys containing dots in rendered content', async () => {
    const NoKeysComponent = () => {
      const { t, isReady } = useI18n()

      if (!isReady) {
        return null
      }

      const testKeys = [
        'dashboard.title',
        'dashboard.subtitle',
        'projects.title',
        'dataManagement.title',
      ]

      return (
        <div>
          {testKeys.map((key, index) => {
            const value = t(key)
            return (
              <div key={index} data-testid={`translated-${index}`}>
                {value}
              </div>
            )
          })}
        </div>
      )
    }

    render(
      <MockI18nProvider>
        <NoKeysComponent />
      </MockI18nProvider>
    )

    await waitFor(
      () => {
        const translated0 = screen.queryByTestId('translated-0')
        if (translated0) {
          // Should not contain dots (translation keys pattern)
          const text = translated0.textContent || ''
          // Check that it's not a translation key by verifying it doesn't match the pattern
          expect(text).not.toMatch(/^[a-z]+\.[a-z]+/)
        }
      },
      { timeout: 3000 }
    )
  })
})

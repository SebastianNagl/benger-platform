/**
 * @jest-environment jsdom
 */

import { act, render, screen } from '@testing-library/react'
import { SimpleI18nProvider, useI18n } from '../SimpleI18n'

// Test component to access i18n context
function TestComponent() {
  const { locale, t, changeLocale } = useI18n()

  return (
    <div>
      <div data-testid="locale">{locale}</div>
      <div data-testid="translation">{t('navigation.dashboard')}</div>
      <button onClick={() => changeLocale('de')}>Switch to DE</button>
      <button onClick={() => changeLocale('en')}>Switch to EN</button>
    </div>
  )
}

// Test component for translation testing
function TranslationTestComponent({
  translationKey,
}: {
  translationKey: string
}) {
  const { t } = useI18n()
  return <div data-testid="translation">{t(translationKey)}</div>
}

describe('SimpleI18n Component', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  afterEach(() => {
    localStorage.clear()
  })

  // 1. Basic Rendering
  describe('Basic Rendering', () => {
    it('should render children wrapped in provider', () => {
      render(
        <SimpleI18nProvider>
          <div data-testid="child">Test Child</div>
        </SimpleI18nProvider>
      )

      expect(screen.getByTestId('child')).toBeInTheDocument()
      expect(screen.getByTestId('child')).toHaveTextContent('Test Child')
    })

    it('should render multiple children', () => {
      render(
        <SimpleI18nProvider>
          <div data-testid="child1">Child 1</div>
          <div data-testid="child2">Child 2</div>
        </SimpleI18nProvider>
      )

      expect(screen.getByTestId('child1')).toBeInTheDocument()
      expect(screen.getByTestId('child2')).toBeInTheDocument()
    })

    it('should initialize with English locale by default', () => {
      render(
        <SimpleI18nProvider>
          <TestComponent />
        </SimpleI18nProvider>
      )

      expect(screen.getByTestId('locale')).toHaveTextContent('en')
    })
  })

  // 2. Translation Function
  describe('Translation Function', () => {
    it('should translate navigation.dashboard in English', () => {
      render(
        <SimpleI18nProvider>
          <TranslationTestComponent translationKey="navigation.dashboard" />
        </SimpleI18nProvider>
      )

      expect(screen.getByTestId('translation')).toHaveTextContent('Dashboard')
    })

    it('should translate navigation.tasks in English', () => {
      render(
        <SimpleI18nProvider>
          <TranslationTestComponent translationKey="navigation.tasks" />
        </SimpleI18nProvider>
      )

      expect(screen.getByTestId('translation')).toHaveTextContent('Tasks')
    })

    it('should translate navigation.about in English', () => {
      render(
        <SimpleI18nProvider>
          <TranslationTestComponent translationKey="navigation.about" />
        </SimpleI18nProvider>
      )

      expect(screen.getByTestId('translation')).toHaveTextContent('About')
    })

    it('should translate common.loading in English', () => {
      render(
        <SimpleI18nProvider>
          <TranslationTestComponent translationKey="common.loading" />
        </SimpleI18nProvider>
      )

      expect(screen.getByTestId('translation')).toHaveTextContent('Loading...')
    })

    it('should translate common.save in English', () => {
      render(
        <SimpleI18nProvider>
          <TranslationTestComponent translationKey="common.save" />
        </SimpleI18nProvider>
      )

      expect(screen.getByTestId('translation')).toHaveTextContent('Save')
    })

    it('should translate common.cancel in English', () => {
      render(
        <SimpleI18nProvider>
          <TranslationTestComponent translationKey="common.cancel" />
        </SimpleI18nProvider>
      )

      expect(screen.getByTestId('translation')).toHaveTextContent('Cancel')
    })
  })

  // 3. Language Switching
  describe('Language Switching', () => {
    it('should switch from English to German', () => {
      render(
        <SimpleI18nProvider>
          <TestComponent />
        </SimpleI18nProvider>
      )

      expect(screen.getByTestId('locale')).toHaveTextContent('en')
      expect(screen.getByTestId('translation')).toHaveTextContent('Dashboard')

      act(() => {
        screen.getByText('Switch to DE').click()
      })

      expect(screen.getByTestId('locale')).toHaveTextContent('de')
      expect(screen.getByTestId('translation')).toHaveTextContent('Dashboard')
    })

    it('should translate tasks correctly after switching to German', () => {
      function TasksComponent() {
        const { t, changeLocale } = useI18n()
        return (
          <div>
            <div data-testid="tasks">{t('navigation.tasks')}</div>
            <button onClick={() => changeLocale('de')}>Switch</button>
          </div>
        )
      }

      render(
        <SimpleI18nProvider>
          <TasksComponent />
        </SimpleI18nProvider>
      )

      expect(screen.getByTestId('tasks')).toHaveTextContent('Tasks')

      act(() => {
        screen.getByText('Switch').click()
      })

      expect(screen.getByTestId('tasks')).toHaveTextContent('Aufgaben')
    })

    it('should translate common phrases after switching to German', () => {
      function CommonComponent() {
        const { t, changeLocale } = useI18n()
        return (
          <div>
            <div data-testid="loading">{t('common.loading')}</div>
            <div data-testid="save">{t('common.save')}</div>
            <div data-testid="cancel">{t('common.cancel')}</div>
            <button onClick={() => changeLocale('de')}>Switch</button>
          </div>
        )
      }

      render(
        <SimpleI18nProvider>
          <CommonComponent />
        </SimpleI18nProvider>
      )

      expect(screen.getByTestId('loading')).toHaveTextContent('Loading...')
      expect(screen.getByTestId('save')).toHaveTextContent('Save')
      expect(screen.getByTestId('cancel')).toHaveTextContent('Cancel')

      act(() => {
        screen.getByText('Switch').click()
      })

      expect(screen.getByTestId('loading')).toHaveTextContent('Lädt...')
      expect(screen.getByTestId('save')).toHaveTextContent('Speichern')
      expect(screen.getByTestId('cancel')).toHaveTextContent('Abbrechen')
    })

    it('should switch back from German to English', () => {
      render(
        <SimpleI18nProvider>
          <TestComponent />
        </SimpleI18nProvider>
      )

      act(() => {
        screen.getByText('Switch to DE').click()
      })

      expect(screen.getByTestId('locale')).toHaveTextContent('de')

      act(() => {
        screen.getByText('Switch to EN').click()
      })

      expect(screen.getByTestId('locale')).toHaveTextContent('en')
    })

    it('should persist locale to localStorage when switching', () => {
      render(
        <SimpleI18nProvider>
          <TestComponent />
        </SimpleI18nProvider>
      )

      act(() => {
        screen.getByText('Switch to DE').click()
      })

      expect(localStorage.getItem('locale')).toBe('de')
    })

    it('should update localStorage when switching back to English', () => {
      render(
        <SimpleI18nProvider>
          <TestComponent />
        </SimpleI18nProvider>
      )

      act(() => {
        screen.getByText('Switch to DE').click()
      })

      act(() => {
        screen.getByText('Switch to EN').click()
      })

      expect(localStorage.getItem('locale')).toBe('en')
    })
  })

  // 4. Context Integration
  describe('Context Integration', () => {
    it('should provide locale through context', () => {
      render(
        <SimpleI18nProvider>
          <TestComponent />
        </SimpleI18nProvider>
      )

      expect(screen.getByTestId('locale')).toBeInTheDocument()
    })

    it('should provide t function through context', () => {
      function TranslationAccessComponent() {
        const { t } = useI18n()
        return (
          <div data-testid="has-t">
            {typeof t === 'function' ? 'function' : 'not-function'}
          </div>
        )
      }

      render(
        <SimpleI18nProvider>
          <TranslationAccessComponent />
        </SimpleI18nProvider>
      )

      expect(screen.getByTestId('has-t')).toHaveTextContent('function')
    })

    it('should provide changeLocale function through context', () => {
      function LocaleChangeComponent() {
        const { changeLocale } = useI18n()
        return (
          <div data-testid="has-change">
            {typeof changeLocale === 'function' ? 'function' : 'not-function'}
          </div>
        )
      }

      render(
        <SimpleI18nProvider>
          <LocaleChangeComponent />
        </SimpleI18nProvider>
      )

      expect(screen.getByTestId('has-change')).toHaveTextContent('function')
    })

    it('should share context across multiple consumer components', () => {
      function Component1() {
        const { locale } = useI18n()
        return <div data-testid="comp1">{locale}</div>
      }

      function Component2() {
        const { locale, changeLocale } = useI18n()
        return (
          <div>
            <div data-testid="comp2">{locale}</div>
            <button onClick={() => changeLocale('de')}>Change</button>
          </div>
        )
      }

      render(
        <SimpleI18nProvider>
          <Component1 />
          <Component2 />
        </SimpleI18nProvider>
      )

      expect(screen.getByTestId('comp1')).toHaveTextContent('en')
      expect(screen.getByTestId('comp2')).toHaveTextContent('en')

      act(() => {
        screen.getByText('Change').click()
      })

      expect(screen.getByTestId('comp1')).toHaveTextContent('de')
      expect(screen.getByTestId('comp2')).toHaveTextContent('de')
    })
  })

  // 5. useI18n Hook
  describe('useI18n Hook', () => {
    it('should throw error when used outside provider', () => {
      const consoleErrorSpy = jest
        .spyOn(console, 'error')
        .mockImplementation(() => {})

      function ComponentWithoutProvider() {
        useI18n()
        return <div>Test</div>
      }

      expect(() => {
        render(<ComponentWithoutProvider />)
      }).toThrow('useI18n must be used within an I18nProvider')

      consoleErrorSpy.mockRestore()
    })

    it('should return locale from hook', () => {
      function HookTestComponent() {
        const { locale } = useI18n()
        return <div data-testid="hook-locale">{locale}</div>
      }

      render(
        <SimpleI18nProvider>
          <HookTestComponent />
        </SimpleI18nProvider>
      )

      expect(screen.getByTestId('hook-locale')).toHaveTextContent('en')
    })

    it('should return t function from hook', () => {
      function HookTestComponent() {
        const { t } = useI18n()
        return <div data-testid="hook-t">{t('navigation.tasks')}</div>
      }

      render(
        <SimpleI18nProvider>
          <HookTestComponent />
        </SimpleI18nProvider>
      )

      expect(screen.getByTestId('hook-t')).toHaveTextContent('Tasks')
    })

    it('should return changeLocale function from hook', () => {
      function HookTestComponent() {
        const { locale, changeLocale } = useI18n()
        return (
          <div>
            <div data-testid="hook-locale">{locale}</div>
            <button onClick={() => changeLocale('de')}>Change Locale</button>
          </div>
        )
      }

      render(
        <SimpleI18nProvider>
          <HookTestComponent />
        </SimpleI18nProvider>
      )

      expect(screen.getByTestId('hook-locale')).toHaveTextContent('en')

      act(() => {
        screen.getByText('Change Locale').click()
      })

      expect(screen.getByTestId('hook-locale')).toHaveTextContent('de')
    })
  })

  // 6. Props/Attributes
  describe('Props/Attributes', () => {
    it('should accept single child element', () => {
      render(
        <SimpleI18nProvider>
          <div data-testid="single-child">Single</div>
        </SimpleI18nProvider>
      )

      expect(screen.getByTestId('single-child')).toBeInTheDocument()
    })

    it('should accept multiple child elements', () => {
      render(
        <SimpleI18nProvider>
          <>
            <div data-testid="child-a">A</div>
            <div data-testid="child-b">B</div>
            <div data-testid="child-c">C</div>
          </>
        </SimpleI18nProvider>
      )

      expect(screen.getByTestId('child-a')).toBeInTheDocument()
      expect(screen.getByTestId('child-b')).toBeInTheDocument()
      expect(screen.getByTestId('child-c')).toBeInTheDocument()
    })

    it('should accept nested components as children', () => {
      function NestedComponent() {
        return <div data-testid="nested">Nested Component</div>
      }

      render(
        <SimpleI18nProvider>
          <NestedComponent />
        </SimpleI18nProvider>
      )

      expect(screen.getByTestId('nested')).toBeInTheDocument()
    })

    it('should accept text nodes as children', () => {
      render(
        <SimpleI18nProvider>
          <div data-testid="text-container">Plain text content</div>
        </SimpleI18nProvider>
      )

      expect(screen.getByTestId('text-container')).toHaveTextContent(
        'Plain text content'
      )
    })
  })

  // 7. Edge Cases
  describe('Edge Cases', () => {
    it('should return key when translation not found', () => {
      render(
        <SimpleI18nProvider>
          <TranslationTestComponent translationKey="non.existent.key" />
        </SimpleI18nProvider>
      )

      expect(screen.getByTestId('translation')).toHaveTextContent(
        'non.existent.key'
      )
    })

    it('should handle empty translation key', () => {
      render(
        <SimpleI18nProvider>
          <TranslationTestComponent translationKey="" />
        </SimpleI18nProvider>
      )

      expect(screen.getByTestId('translation')).toHaveTextContent('')
    })

    it('should return object for partial translation path', () => {
      const consoleErrorSpy = jest
        .spyOn(console, 'error')
        .mockImplementation(() => {})

      function PartialPathComponent() {
        const { t } = useI18n()
        const result = t('navigation')
        return (
          <div data-testid="result">
            {typeof result === 'object' ? 'object' : result}
          </div>
        )
      }

      render(
        <SimpleI18nProvider>
          <PartialPathComponent />
        </SimpleI18nProvider>
      )

      expect(screen.getByTestId('result')).toHaveTextContent('object')

      consoleErrorSpy.mockRestore()
    })

    it('should handle deeply nested missing keys', () => {
      render(
        <SimpleI18nProvider>
          <TranslationTestComponent translationKey="navigation.tasks.subtask.deep" />
        </SimpleI18nProvider>
      )

      expect(screen.getByTestId('translation')).toHaveTextContent(
        'navigation.tasks.subtask.deep'
      )
    })

    it('should handle special characters in translation keys', () => {
      render(
        <SimpleI18nProvider>
          <TranslationTestComponent translationKey="special.key.with-dashes_underscores" />
        </SimpleI18nProvider>
      )

      expect(screen.getByTestId('translation')).toHaveTextContent(
        'special.key.with-dashes_underscores'
      )
    })

    it('should handle single-level translation keys', () => {
      render(
        <SimpleI18nProvider>
          <TranslationTestComponent translationKey="singlekey" />
        </SimpleI18nProvider>
      )

      expect(screen.getByTestId('translation')).toHaveTextContent('singlekey')
    })

    it('should handle translation with ellipsis', () => {
      render(
        <SimpleI18nProvider>
          <TranslationTestComponent translationKey="common.loading" />
        </SimpleI18nProvider>
      )

      expect(screen.getByTestId('translation')).toHaveTextContent('Loading...')
    })

    it('should handle German umlauts correctly', () => {
      function GermanComponent() {
        const { t, changeLocale } = useI18n()
        return (
          <div>
            <div data-testid="german">{t('common.loading')}</div>
            <button onClick={() => changeLocale('de')}>Switch</button>
          </div>
        )
      }

      render(
        <SimpleI18nProvider>
          <GermanComponent />
        </SimpleI18nProvider>
      )

      act(() => {
        screen.getByText('Switch').click()
      })

      expect(screen.getByTestId('german')).toHaveTextContent('Lädt...')
    })

    it('should maintain context when no children provided', () => {
      render(<SimpleI18nProvider>{null}</SimpleI18nProvider>)

      expect(true).toBe(true)
    })

    it('should handle rapid locale switching', () => {
      function RapidSwitchComponent() {
        const { locale, changeLocale } = useI18n()
        return (
          <div>
            <div data-testid="locale">{locale}</div>
            <button
              onClick={() => {
                changeLocale('de')
                changeLocale('en')
                changeLocale('de')
              }}
            >
              Rapid Switch
            </button>
          </div>
        )
      }

      render(
        <SimpleI18nProvider>
          <RapidSwitchComponent />
        </SimpleI18nProvider>
      )

      act(() => {
        screen.getByText('Rapid Switch').click()
      })

      expect(screen.getByTestId('locale')).toHaveTextContent('de')
    })
  })

  // 8. Nested Translations
  describe('Nested Translations', () => {
    it('should access nested navigation object', () => {
      function NestedComponent() {
        const { t } = useI18n()
        return (
          <div>
            <div data-testid="nav-dashboard">{t('navigation.dashboard')}</div>
            <div data-testid="nav-tasks">{t('navigation.tasks')}</div>
            <div data-testid="nav-about">{t('navigation.about')}</div>
          </div>
        )
      }

      render(
        <SimpleI18nProvider>
          <NestedComponent />
        </SimpleI18nProvider>
      )

      expect(screen.getByTestId('nav-dashboard')).toHaveTextContent('Dashboard')
      expect(screen.getByTestId('nav-tasks')).toHaveTextContent('Tasks')
      expect(screen.getByTestId('nav-about')).toHaveTextContent('About')
    })

    it('should access nested common object', () => {
      function NestedComponent() {
        const { t } = useI18n()
        return (
          <div>
            <div data-testid="common-loading">{t('common.loading')}</div>
            <div data-testid="common-save">{t('common.save')}</div>
            <div data-testid="common-cancel">{t('common.cancel')}</div>
          </div>
        )
      }

      render(
        <SimpleI18nProvider>
          <NestedComponent />
        </SimpleI18nProvider>
      )

      expect(screen.getByTestId('common-loading')).toHaveTextContent(
        'Loading...'
      )
      expect(screen.getByTestId('common-save')).toHaveTextContent('Save')
      expect(screen.getByTestId('common-cancel')).toHaveTextContent('Cancel')
    })

    it('should handle two-level nested keys', () => {
      render(
        <SimpleI18nProvider>
          <TranslationTestComponent translationKey="navigation.dashboard" />
        </SimpleI18nProvider>
      )

      expect(screen.getByTestId('translation')).toHaveTextContent('Dashboard')
    })

    it('should handle nested keys in German', () => {
      function GermanNestedComponent() {
        const { t, changeLocale } = useI18n()
        return (
          <div>
            <div data-testid="nested-de">{t('navigation.tasks')}</div>
            <button onClick={() => changeLocale('de')}>Switch</button>
          </div>
        )
      }

      render(
        <SimpleI18nProvider>
          <GermanNestedComponent />
        </SimpleI18nProvider>
      )

      act(() => {
        screen.getByText('Switch').click()
      })

      expect(screen.getByTestId('nested-de')).toHaveTextContent('Aufgaben')
    })

    it('should handle multiple nested translations in same component', () => {
      function MultiNestedComponent() {
        const { t } = useI18n()
        return (
          <div>
            <div data-testid="multi-1">{t('navigation.dashboard')}</div>
            <div data-testid="multi-2">{t('common.loading')}</div>
            <div data-testid="multi-3">{t('navigation.tasks')}</div>
            <div data-testid="multi-4">{t('common.save')}</div>
          </div>
        )
      }

      render(
        <SimpleI18nProvider>
          <MultiNestedComponent />
        </SimpleI18nProvider>
      )

      expect(screen.getByTestId('multi-1')).toHaveTextContent('Dashboard')
      expect(screen.getByTestId('multi-2')).toHaveTextContent('Loading...')
      expect(screen.getByTestId('multi-3')).toHaveTextContent('Tasks')
      expect(screen.getByTestId('multi-4')).toHaveTextContent('Save')
    })

    it('should correctly traverse nested object structure', () => {
      function TraversalComponent() {
        const { t } = useI18n()
        const keys = [
          'navigation.dashboard',
          'navigation.tasks',
          'navigation.about',
          'common.loading',
          'common.save',
          'common.cancel',
        ]
        return (
          <div>
            {keys.map((key, idx) => (
              <div key={key} data-testid={`key-${idx}`}>
                {t(key)}
              </div>
            ))}
          </div>
        )
      }

      render(
        <SimpleI18nProvider>
          <TraversalComponent />
        </SimpleI18nProvider>
      )

      expect(screen.getByTestId('key-0')).toHaveTextContent('Dashboard')
      expect(screen.getByTestId('key-1')).toHaveTextContent('Tasks')
      expect(screen.getByTestId('key-2')).toHaveTextContent('About')
      expect(screen.getByTestId('key-3')).toHaveTextContent('Loading...')
      expect(screen.getByTestId('key-4')).toHaveTextContent('Save')
      expect(screen.getByTestId('key-5')).toHaveTextContent('Cancel')
    })
  })
})

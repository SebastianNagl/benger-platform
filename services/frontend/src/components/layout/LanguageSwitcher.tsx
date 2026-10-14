'use client'

import { useHydration } from '@/contexts/HydrationContext'
import { useI18n } from '@/contexts/I18nContext'
import { LOCALES, LOCALE_META, toLocale } from '@/lib/i18n/locales'
import { Menu, MenuButton, MenuItem, MenuItems } from '@headlessui/react'

function CheckIcon(props: React.ComponentPropsWithoutRef<'svg'>) {
  return (
    <svg viewBox="0 0 20 20" fill="currentColor" aria-hidden="true" {...props}>
      <path
        fillRule="evenodd"
        d="M16.7 5.3a1 1 0 0 1 0 1.4l-7.5 7.5a1 1 0 0 1-1.4 0l-3.5-3.5a1 1 0 1 1 1.4-1.4l2.8 2.79 6.8-6.79a1 1 0 0 1 1.4 0Z"
        clipRule="evenodd"
      />
    </svg>
  )
}

/**
 * Language menu: the trigger shows the active language's flag, the menu
 * lists every supported language under its own name (endonyms are never
 * translated, so a user can always find theirs).
 */
export function LanguageSwitcher({
  // The trigger's full class list — overridable so shells can restyle the
  // whole control (e.g. the student sidebar's full-width bordered variant)
  // with the entire styled area staying the click target.
  className = 'relative flex size-6 items-center justify-center rounded-md transition hover:bg-zinc-900/5 dark:hover:bg-white/5',
  anchor = 'bottom end',
}: {
  className?: string
  anchor?: 'bottom end' | 'bottom start' | 'top end' | 'top start'
} = {}) {
  const { locale, changeLocale, t } = useI18n()
  const mounted = useHydration()
  const current = toLocale(locale)
  const label = t('layout.languageSwitcher.label')

  if (!mounted) {
    return (
      <div className={className}>
        <span className="text-sm">{LOCALE_META[current].flag}</span>
      </div>
    )
  }

  return (
    <Menu>
      <MenuButton
        type="button"
        className={className}
        aria-label={`${label}: ${LOCALE_META[current].name}`}
        title={label}
        data-testid="language-switcher"
        data-locale={current}
      >
        <span className="absolute size-12 pointer-fine:hidden" />
        <span className="text-sm" aria-hidden="true">
          {LOCALE_META[current].flag}
        </span>
      </MenuButton>
      <MenuItems
        anchor={anchor}
        className="z-50 mt-1 w-48 rounded-lg border border-zinc-200 bg-white p-1 shadow-lg focus:outline-none dark:border-white/10 dark:bg-zinc-800"
        data-testid="language-menu"
      >
        {LOCALES.map((option) => (
          <MenuItem key={option}>
            <button
              type="button"
              lang={option}
              onClick={() => changeLocale(option)}
              data-locale-option={option}
              aria-current={option === current ? 'true' : undefined}
              className="flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm text-zinc-700 data-focus:bg-zinc-900/5 dark:text-zinc-200 dark:data-focus:bg-white/5"
            >
              <span aria-hidden="true">{LOCALE_META[option].flag}</span>
              <span className="flex-1 text-left">
                {LOCALE_META[option].name}
              </span>
              {option === current && (
                <CheckIcon className="h-4 w-4 shrink-0 text-emerald-500" />
              )}
            </button>
          </MenuItem>
        ))}
      </MenuItems>
    </Menu>
  )
}

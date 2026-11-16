'use client'

import clsx from 'clsx'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type MouseEvent,
} from 'react'

import { useSectionStore } from '@/components/layout/SectionProvider'
import { Button } from '@/components/shared/Button'
import { useI18n } from '@/contexts/I18nContext'
import {
  CloseButton,
  Popover,
  PopoverButton,
  PopoverPanel,
} from '@headlessui/react'

/**
 * The landing sections, in page order. The landing page registers them with
 * the shell's section store (so the top bar can highlight the one in view);
 * the visitor top bar links to them from every public page.
 */
export const LANDING_SECTIONS = [
  { id: 'information', key: 'landing.nav.information' },
  { id: 'news', key: 'landing.nav.news' },
  { id: 'people', key: 'landing.nav.people' },
  { id: 'license', key: 'landing.nav.license' },
] as const

interface PublicNavItem {
  id: string
  href: string
  label: string
  active: boolean
  /** Landing section: scrolls smoothly when already on the landing page. */
  sectionId?: string
}

function isOnPage(pathname: string | null, page: string) {
  return pathname === page || !!pathname?.startsWith(`${page}/`)
}

/** What a visitor may open: the landing sections and the public pages. */
function usePublicNavItems(): PublicNavItem[] {
  const { t } = useI18n()
  const pathname = usePathname()
  const isHome = pathname === '/'
  const visibleSections = useSectionStore((s) => s.visibleSections)
  // The first landing section in view; none while the hero fills the top.
  const visibleSection = isHome
    ? visibleSections.find((id) => id !== '_top')
    : undefined

  return [
    ...LANDING_SECTIONS.map(({ id, key }) => ({
      id,
      href: `/#${id}`,
      label: t(key),
      active: visibleSection === id,
      sectionId: id,
    })),
    {
      id: 'reports',
      href: '/reports',
      label: t('navigation.reports'),
      active: isOnPage(pathname, '/reports'),
    },
    {
      id: 'changelog',
      href: '/changelog',
      label: t('layout.footer.changelog'),
      active: isOnPage(pathname, '/changelog'),
    },
  ]
}

/** On the landing page a section link scrolls there instead of navigating. */
function useSectionClick() {
  const isHome = usePathname() === '/'
  return useCallback(
    (item: PublicNavItem) => (event: MouseEvent<HTMLAnchorElement>) => {
      if (!isHome || !item.sectionId) return
      const target = document.getElementById(item.sectionId)
      if (!target) return
      event.preventDefault()
      target.scrollIntoView({ behavior: 'smooth' })
      window.history.replaceState(null, '', item.href)
    },
    [isHome],
  )
}

const useIsomorphicLayoutEffect =
  typeof window === 'undefined' ? useEffect : useLayoutEffect

function MenuIcon(props: React.ComponentPropsWithoutRef<'svg'>) {
  return (
    <svg viewBox="0 0 10 9" fill="none" strokeLinecap="round" {...props}>
      <path d="M.5 1h9M.5 8h9M.5 4.5h9" />
    </svg>
  )
}

function XIcon(props: React.ComponentPropsWithoutRef<'svg'>) {
  return (
    <svg viewBox="0 0 10 9" fill="none" strokeLinecap="round" {...props}>
      <path d="m1.5 1 7 7M8.5 1l-7 7" />
    </svg>
  )
}

/**
 * The visitor navigation of the top bar. The items sit in the bar as long
 * as they fit next to the other controls (measured, since their length
 * differs a lot between languages); otherwise, and on phones, they collapse
 * into a compact menu at the end of the bar.
 *
 * Renders the inline items where it is placed (a flex child that takes the
 * free width of the bar) and the menu button through `menuSlot`, so the bar
 * can put the button next to its other controls.
 */
export function usePublicNavigation() {
  const items = usePublicNavItems()
  const onSectionClick = useSectionClick()
  const containerRef = useRef<HTMLDivElement>(null)
  const listRef = useRef<HTMLUListElement>(null)
  // null until measured: CSS then decides (items from lg, menu below).
  const [fits, setFits] = useState<boolean | null>(null)

  const measure = useCallback(() => {
    const container = containerRef.current
    const list = listRef.current
    if (!container || !list) return
    // The list is always laid out at its natural width (w-max), also while
    // hidden, so it can be compared with the width the bar leaves free.
    // On phones the container is not displayed at all: the menu then holds
    // the items.
    const shown = container.getClientRects().length > 0
    setFits(shown && list.scrollWidth <= container.clientWidth)
  }, [])

  useIsomorphicLayoutEffect(() => {
    measure()
    const container = containerRef.current
    const list = listRef.current
    if (!container || !list || typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(measure)
    observer.observe(container)
    observer.observe(list)
    return () => observer.disconnect()
  }, [measure])

  const inline = (
    <div
      ref={containerRef}
      className="relative hidden h-full min-w-0 flex-1 items-center overflow-hidden md:flex"
      data-testid="public-nav-inline"
      data-fits={fits === null ? undefined : String(fits)}
    >
      <nav
        className={clsx(
          fits === false && 'invisible absolute',
          fits === null && 'invisible absolute lg:visible lg:static',
        )}
        aria-hidden={fits === false ? true : undefined}
      >
        <ul ref={listRef} role="list" className="flex w-max items-center gap-1">
          {items.map((item) => (
            <li key={item.id}>
              <Link
                href={item.href}
                onClick={onSectionClick(item)}
                tabIndex={fits === false ? -1 : undefined}
                aria-current={
                  item.active
                    ? item.sectionId
                      ? 'location'
                      : 'page'
                    : undefined
                }
                className={clsx(
                  'inline-flex h-8 items-center rounded-full px-3 text-sm font-medium whitespace-nowrap transition-colors',
                  item.active
                    ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-400'
                    : 'text-zinc-600 hover:bg-zinc-100 hover:text-zinc-900 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-white',
                )}
              >
                {item.label}
              </Link>
            </li>
          ))}
        </ul>
      </nav>
    </div>
  )

  const menu = (
    <PublicNavMenu
      items={items}
      onSectionClick={onSectionClick}
      className={clsx(fits === true && 'hidden', fits === null && 'lg:hidden')}
    />
  )

  return { inline, menu }
}

function PublicNavMenu({
  items,
  onSectionClick,
  className,
}: {
  items: PublicNavItem[]
  onSectionClick: (
    item: PublicNavItem,
  ) => (event: MouseEvent<HTMLAnchorElement>) => void
  className?: string
}) {
  const { t } = useI18n()

  return (
    <Popover
      className={clsx('relative flex', className)}
      data-testid="public-nav-menu-root"
    >
      {({ open }) => (
        <>
          <PopoverButton
            className="relative flex size-6 items-center justify-center rounded-md transition hover:bg-zinc-900/5 focus:outline-none data-focus:ring-2 data-focus:ring-emerald-500 dark:hover:bg-white/5"
            aria-label={t('navigation.mobile.toggleNavigation')}
            data-testid="public-nav-menu-button"
          >
            <span className="absolute size-12 pointer-fine:hidden" />
            {open ? (
              <XIcon
                aria-hidden="true"
                className="w-2.5 stroke-zinc-900 dark:stroke-white"
              />
            ) : (
              <MenuIcon
                aria-hidden="true"
                className="w-2.5 stroke-zinc-900 dark:stroke-white"
              />
            )}
          </PopoverButton>
          <PopoverPanel
            transition
            anchor={{ to: 'bottom end', gap: 12 }}
            className="z-50 w-64 max-w-[calc(100vw-2rem)] rounded-xl bg-white p-2 shadow-lg ring-1 ring-zinc-900/10 transition duration-150 ease-out data-closed:-translate-y-1 data-closed:opacity-0 dark:bg-zinc-900 dark:ring-white/10"
            data-testid="public-nav-menu"
          >
            <nav>
              <ul role="list" className="flex flex-col">
                {items.map((item) => (
                  <li key={item.id}>
                    <CloseButton
                      as={Link}
                      href={item.href}
                      onClick={onSectionClick(item)}
                      aria-current={
                        item.active
                          ? item.sectionId
                            ? 'location'
                            : 'page'
                          : undefined
                      }
                      className={clsx(
                        'flex rounded-lg px-3 py-2 text-sm font-medium transition-colors',
                        item.active
                          ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-400'
                          : 'text-zinc-700 hover:bg-zinc-100 hover:text-zinc-900 dark:text-zinc-300 dark:hover:bg-zinc-800 dark:hover:text-white',
                      )}
                    >
                      {item.label}
                    </CloseButton>
                  </li>
                ))}
              </ul>
              {/* The top bar has no room for the sign-in buttons on small
                  phones, so the menu offers them there. */}
              <div className="mt-2 flex flex-col gap-2 border-t border-zinc-900/10 px-1 pt-3 pb-1 min-[416px]:hidden dark:border-white/10">
                <CloseButton as={Button} href="/login" variant="outline">
                  {t('navigation.signIn')}
                </CloseButton>
                <CloseButton as={Button} href="/register" variant="filled">
                  {t('auth.signUp')}
                </CloseButton>
              </div>
            </nav>
          </PopoverPanel>
        </>
      )}
    </Popover>
  )
}

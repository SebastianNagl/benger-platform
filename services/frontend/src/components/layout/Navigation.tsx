'use client'

import clsx from 'clsx'
import { AnimatePresence, motion, useIsPresent } from 'framer-motion'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import React, { useEffect, useRef, useState } from 'react'

import { useIsInsideMobileNavigation } from '@/components/layout/MobileNavigation'
import { useSectionStore } from '@/components/layout/SectionProvider'
import { Button } from '@/components/shared/Button'
import { Tag } from '@/components/shared/Tag'
import { useAuth } from '@/contexts/AuthContext'
import { useFeatureFlags } from '@/contexts/FeatureFlagContext'
import { useHydration } from '@/contexts/HydrationContext'
import { useI18n } from '@/contexts/I18nContext'
import { parseSubdomain } from '@/lib/utils/subdomain'
import { remToPx } from '@/lib/remToPx'
import { CloseButton } from '@headlessui/react'

interface NavGroup {
  title: string
  links: Array<{
    title: string
    href: string
    icon?: React.ReactNode
    disabled?: boolean
  }>
}

function useInitialValue<T>(value: T, condition = true) {
  // eslint-disable-next-line react-hooks/refs -- Valid pattern: capturing initial value on first render
  let initialValue = useRef(value).current
  return condition ? value : initialValue
}

// Icon components for navigation items
const DashboardIcon = () => (
  <svg
    className="h-4 w-4"
    fill="none"
    stroke="currentColor"
    viewBox="0 0 24 24"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z"
    />
  </svg>
)

const ReportsIcon = () => (
  <svg
    className="h-4 w-4"
    fill="none"
    stroke="currentColor"
    viewBox="0 0 24 24"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z"
    />
  </svg>
)

const ArchitectureIcon = () => (
  <svg
    className="h-4 w-4"
    fill="none"
    stroke="currentColor"
    viewBox="0 0 24 24"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2M7 7h10"
    />
  </svg>
)



const ProjectsIcon = () => (
  <svg
    className="h-4 w-4"
    fill="none"
    stroke="currentColor"
    viewBox="0 0 24 24"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"
    />
  </svg>
)

const DataIcon = () => (
  <svg
    className="h-4 w-4"
    fill="none"
    stroke="currentColor"
    viewBox="0 0 24 24"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4"
    />
  </svg>
)

const GenerationIcon = () => (
  <svg
    className="h-4 w-4"
    fill="none"
    stroke="currentColor"
    viewBox="0 0 24 24"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M13 10V3L4 14h7v7l9-11h-7z"
    />
  </svg>
)

const EvaluationIcon = () => (
  <svg
    className="h-4 w-4"
    fill="none"
    stroke="currentColor"
    viewBox="0 0 24 24"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"
    />
  </svg>
)

const KnowledgeIcon = () => (
  <svg
    className="h-4 w-4"
    fill="none"
    stroke="currentColor"
    viewBox="0 0 24 24"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253"
    />
  </svg>
)

const HowToIcon = () => (
  <svg
    className="h-4 w-4"
    fill="none"
    stroke="currentColor"
    viewBox="0 0 24 24"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
    />
  </svg>
)

const ModelsIcon = () => (
  <svg
    className="h-4 w-4"
    fill="none"
    stroke="currentColor"
    viewBox="0 0 24 24"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"
    />
  </svg>
)

const LeaderboardIcon = () => (
  <svg
    className="h-4 w-4"
    fill="none"
    stroke="currentColor"
    viewBox="0 0 24 24"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M16 4v12l-4-2-4 2V4M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"
    />
  </svg>
)

const OrganizationsIcon = () => (
  <svg
    className="h-4 w-4"
    fill="none"
    stroke="currentColor"
    viewBox="0 0 24 24"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4"
    />
  </svg>
)

// User and profile icons moved to AuthButton dropdown

function NavLink({
  href,
  children,
  tag,
  active = false,
  isAnchorLink = false,
  icon,
  disabled = false,
}: {
  href: string
  children: React.ReactNode
  tag?: string
  active?: boolean
  isAnchorLink?: boolean
  icon?: React.ReactNode
  disabled?: boolean
}) {
  const isInsideMobileNavigation = useIsInsideMobileNavigation()

  // Disable prefetch for client component routes that cause RSC 404 errors
  const shouldDisablePrefetch = href.includes('/data')

  if (disabled) {
    return (
      <div
        className={clsx(
          'flex cursor-not-allowed items-center gap-2 py-1 text-sm opacity-50',
          isAnchorLink ? 'pl-7' : 'pl-4 pr-3',
          'text-zinc-400 dark:text-zinc-500'
        )}
      >
        {icon && !isAnchorLink && <span className="flex-shrink-0">{icon}</span>}
        <span className="truncate">{children}</span>
      </div>
    )
  }

  return (
    <CloseButton
      as={Link}
      href={href}
      prefetch={shouldDisablePrefetch ? false : undefined}
      aria-current={active ? 'page' : undefined}
      className={clsx(
        'group relative flex items-center gap-2 py-1 text-sm transition',
        isAnchorLink ? 'pl-7' : 'pl-4 pr-3',
        active
          ? 'text-zinc-900 dark:text-white'
          : 'text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white'
      )}
    >
      {icon && !isAnchorLink && <span className="flex-shrink-0">{icon}</span>}
      <span className="truncate">{children}</span>
      {tag && (
        <Tag variant="small" color="zinc">
          {tag}
        </Tag>
      )}
    </CloseButton>
  )
}

function VisibleSectionHighlight({
  group,
  pathname,
}: {
  group: NavGroup
  pathname: string
}) {
  let [sections, visibleSections] = useInitialValue(
    [
      useSectionStore((s) => s.sections),
      useSectionStore((s) => s.visibleSections),
    ],
    useIsInsideMobileNavigation()
  )

  let isPresent = useIsPresent()
  let firstVisibleSectionIndex = Math.max(
    0,
    [{ id: '_top' }, ...sections].findIndex(
      (section) => section.id === visibleSections[0]
    )
  )
  let itemHeight = remToPx(2)
  let height = isPresent
    ? Math.max(1, visibleSections.length) * itemHeight
    : itemHeight
  let top =
    group.links.findIndex((link) => link.href === pathname) * itemHeight +
    firstVisibleSectionIndex * itemHeight

  return (
    <motion.div
      layout
      initial={{ opacity: 0 }}
      animate={{ opacity: 1, transition: { delay: 0.2 } }}
      exit={{ opacity: 0 }}
      className="bg-zinc-800/2.5 dark:bg-white/2.5 absolute inset-x-0 top-0 will-change-transform"
      style={{ borderRadius: 8, height, top }}
    />
  )
}

function ActivePageMarker({
  group,
  pathname,
}: {
  group: NavGroup
  pathname: string
}) {
  let itemHeight = remToPx(2)
  let offset = remToPx(0.25)
  let activePageIndex = group.links.findIndex((link) => link.href === pathname)
  let top = offset + activePageIndex * itemHeight

  return (
    <motion.div
      layout
      className="absolute left-2 h-6 w-px bg-emerald-500"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1, transition: { delay: 0.2 } }}
      exit={{ opacity: 0 }}
      style={{ top }}
    />
  )
}

function NavigationGroup({
  group,
  className,
}: {
  group: NavGroup
  className?: string
}) {
  // If this is the mobile navigation then we always render the initial
  // state, so that the state does not change during the close animation.
  // The state will still update when we re-open (re-render) the navigation.
  let isInsideMobileNavigation = useIsInsideMobileNavigation()
  // Always call hooks, but conditionally use their values
  let currentPathname = usePathname()
  let currentSections = useSectionStore((s) => s.sections)
  let [initialPathname, initialSections] = useInitialValue(
    [currentPathname, currentSections],
    true
  )

  // For mobile navigation, use initial values to prevent changes during animations
  // For desktop navigation, use current values so active links update properly
  let pathname = isInsideMobileNavigation ? initialPathname : currentPathname
  let sections = isInsideMobileNavigation ? initialSections : currentSections

  let isActiveGroup =
    group.links.findIndex((link) => link.href === pathname) !== -1

  return (
    <li className={clsx('relative mt-6', className)}>
      <motion.h2
        layout="position"
        className="text-xs font-semibold text-zinc-900 dark:text-white"
      >
        {group.title}
      </motion.h2>
      <div className="relative mt-3 pl-2">
        <AnimatePresence initial={!isInsideMobileNavigation}>
          {isActiveGroup && (
            <VisibleSectionHighlight group={group} pathname={pathname || '/'} />
          )}
        </AnimatePresence>
        <motion.div
          layout
          className="absolute inset-y-0 left-2 w-px bg-zinc-900/10 dark:bg-white/5"
        />
        <AnimatePresence initial={false}>
          {isActiveGroup && (
            <ActivePageMarker group={group} pathname={pathname || '/'} />
          )}
        </AnimatePresence>
        <ul role="list" className="border-l border-transparent">
          {group.links.map((link) => {
            return (
              <motion.li key={link.href} layout="position" className="relative">
                <NavLink
                  href={link.href}
                  active={link.href === pathname}
                  icon={link.icon}
                  disabled={link.disabled}
                >
                  {link.title}
                </NavLink>
                <AnimatePresence mode="popLayout" initial={false}>
                  {link.href === pathname && sections.length > 0 && (
                    <motion.ul
                      role="list"
                      initial={{ opacity: 0 }}
                      animate={{
                        opacity: 1,
                        transition: { delay: 0.1 },
                      }}
                      exit={{
                        opacity: 0,
                        transition: { duration: 0.15 },
                      }}
                    >
                      {sections.map((section) => (
                        <li key={section.id}>
                          <NavLink
                            href={`${link.href}#${section.id}`}
                            tag={section.tag}
                            isAnchorLink
                          >
                            {section.title}
                          </NavLink>
                        </li>
                      ))}
                    </motion.ul>
                  )}
                </AnimatePresence>
              </motion.li>
            )
          })}
        </ul>
      </div>
    </li>
  )
}

export function Navigation(props: React.ComponentPropsWithoutRef<'nav'>) {
  const { user, organizations } = useAuth()
  const { t } = useI18n()
  const isClient = useHydration()
  const { flags, lastUpdate } = useFeatureFlags()

  // Directly use flags from context - no local state needed
  const isDataPageEnabled = Boolean(flags?.data)
  const isGenerationPageEnabled = Boolean(flags?.generations)
  const isEvaluationPageEnabled = Boolean(flags?.evaluations)
  const isReportsPageEnabled = Boolean(flags?.reports)
  const isHowToPageEnabled = Boolean(flags?.['how-to'])
  const isLeaderboardsPageEnabled = Boolean(flags?.leaderboards)

  // Parse current subdomain context
  const { isPrivateMode, orgSlug } = typeof window !== 'undefined' ? parseSubdomain() : { isPrivateMode: true, orgSlug: null }
  const currentOrgRole = orgSlug
    ? organizations.find((o) => o.slug === orgSlug)?.role
    : null

  // Helper function to check if user has access to specific routes
  const hasAccessToRoute = (href: string) => {
    if (!user) return true // Allow public routes when not logged in

    // Superadmins see everything regardless of context
    if (user.is_superadmin) return true

    // Private mode: Dashboard, Projects, Data, Generations, Evaluations
    if (isPrivateMode) {
      return ['/dashboard', '/projects', '/data', '/generations', '/evaluations', '/reports', '/leaderboards'].includes(href) ||
        href.startsWith('/about') || href.startsWith('/how-to') ||
        href === '/models' || href === '/architecture'
    }

    // Org mode: role-based access
    switch (href) {
      case '/data':
      case '/generations':
      case '/evaluations':
        // CONTRIBUTOR and above
        return currentOrgRole === 'ORG_ADMIN' || currentOrgRole === 'CONTRIBUTOR'
      case '/projects':
        return true // All org members can see projects
      default:
        return true
    }
  }

  // Build navigation data directly - React will re-render when flags change
  const buildNavigation = () => {
    const bengerLinks = [
      {
        title: isClient ? t('navigation.dashboard') : 'Dashboard',
        href: '/dashboard',
        icon: <DashboardIcon />,
      },
      {
        title: isClient ? t('navigation.reports') : 'Reports',
        href: '/reports',
        icon: <ReportsIcon />,
        disabled: !isReportsPageEnabled,
      },
      {
        title: isClient ? t('navigation.leaderboards') : 'Leaderboards',
        href: '/leaderboards',
        icon: <LeaderboardIcon />,
        disabled: !isLeaderboardsPageEnabled,
      },
    ]

    const projectsAndDataLinks = [
      {
        title: isClient ? t('navigation.projects') : 'Projects',
        href: '/projects',
        icon: <ProjectsIcon />,
      },
      {
        title: isClient ? t('navigation.dataManagement') : 'Data Management',
        href: '/data',
        icon: <DataIcon />,
        disabled: !isDataPageEnabled || !hasAccessToRoute('/data'),
      },
      {
        title: isClient ? t('navigation.generation') : 'Generation',
        href: '/generations',
        icon: <GenerationIcon />,
        disabled: !isGenerationPageEnabled || !hasAccessToRoute('/generations'),
      },
      {
        title: isClient ? t('navigation.evaluation') : 'Evaluation',
        href: '/evaluations',
        icon: <EvaluationIcon />,
        disabled: !isEvaluationPageEnabled || !hasAccessToRoute('/evaluations'),
      },
    ]

    const knowledgeLinks = [
      {
        title: isClient ? t('navigation.howTo') : 'How-To',
        href: '/how-to',
        icon: <HowToIcon />,
        disabled: !isHowToPageEnabled,
      },
      {
        title: isClient ? t('navigation.models') : 'Models',
        href: '/models',
        icon: <ModelsIcon />,
      },
      {
        title: isClient ? t('navigation.architecture') : 'Architecture',
        href: '/architecture',
        icon: <ArchitectureIcon />,
      },
    ]

    const navigationGroups = [
      {
        title: isClient ? t('navigation.quickStart') : 'Quick Start',
        links: bengerLinks,
      },
    ]

    // Only add Projects & Data group if user has access to any of its links
    if (projectsAndDataLinks.length > 0) {
      navigationGroups.push({
        title: isClient ? t('navigation.projectsAndData') : 'Projects & Data',
        links: projectsAndDataLinks,
      })
    }

    // Add Knowledge section
    navigationGroups.push({
      title: isClient ? t('navigation.knowledge') : 'Knowledge',
      links: knowledgeLinks,
    })

    return navigationGroups
  }

  const baseNavigation = buildNavigation()

  // User and admin navigation moved to header dropdown for cleaner sidebar

  return (
    <nav {...props}>
      <ul role="list">
        {baseNavigation.map((group, groupIndex) => (
          <NavigationGroup
            key={`${group.title}-${lastUpdate}`}
            group={group}
            className={groupIndex === 0 ? 'md:mt-0' : ''}
          />
        ))}

        <li className="sticky bottom-0 z-10 mt-6 min-[416px]:hidden">
          <Button href="#" variant="filled" className="w-full">
            {isClient ? t('navigation.signIn') : 'Sign in'}
          </Button>
        </li>
      </ul>
    </nav>
  )
}

// Export navigation data for Footer and Search components
// Note: This is a static export used by Footer for page navigation
// Titles here are kept in English as fallback; the actual Navigation component uses i18n
export const navigation: Array<NavGroup> = [
  {
    title: 'Quick Start',
    links: [
      { title: 'Dashboard', href: '/dashboard' },
      { title: 'Reports', href: '/reports' },
      { title: 'Leaderboards', href: '/leaderboards' },
    ],
  },
  {
    title: 'Projects & Data',
    links: [
      { title: 'Projects', href: '/projects' },
      { title: 'Data Management', href: '/data' },
      { title: 'Generation', href: '/generations' },
      { title: 'Evaluation', href: '/evaluations' },
    ],
  },
  {
    title: 'Knowledge',
    links: [
      { title: 'How-To', href: '/how-to' },
      { title: 'Models', href: '/models' },
      { title: 'Architecture', href: '/architecture' },
    ],
  },
]

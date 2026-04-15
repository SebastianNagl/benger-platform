'use client'

import {
  createAutocomplete,
  type AutocompleteApi,
  type AutocompleteCollection,
  type AutocompleteState,
} from '@algolia/autocomplete-core'
import { Dialog, DialogBackdrop, DialogPanel } from '@headlessui/react'
import clsx from 'clsx'
import { usePathname, useRouter, useSearchParams } from 'next/navigation'
import {
  Fragment,
  Suspense,
  forwardRef,
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
} from 'react'
import Highlighter from 'react-highlight-words'

import { navigation } from '@/components/layout/Navigation'
import { useAuth } from '@/contexts/AuthContext'
import { useFeatureFlags } from '@/contexts/FeatureFlagContext'
import { useI18n } from '@/contexts/I18nContext'
import { projectsAPI } from '@/lib/api/projects'
import type { Project } from '@/types/labelStudio'
import { type Result } from '@/types/search'
import { useMobileNavigationStore } from '../layout/MobileNavigation'

type EmptyObject = Record<string, never>

type Autocomplete = AutocompleteApi<
  Result,
  React.SyntheticEvent,
  React.MouseEvent,
  React.KeyboardEvent
>

// Helper function for fuzzy matching with multilingual support
function isCloseMatch(word1: string, word2: string): boolean {
  if (Math.abs(word1.length - word2.length) > 2) return false

  let distance = 0
  const minLength = Math.min(word1.length, word2.length)

  for (let i = 0; i < minLength; i++) {
    if (word1[i] !== word2[i]) distance++
    if (distance > 2) return false
  }

  return distance <= 1
}

// Cross-language mapping for search terms
const CROSS_LANGUAGE_MAPPINGS: Record<string, string[]> = {
  // English -> German mappings
  about: ['über', 'über uns', 'ueber'],
  projects: ['projekte', 'projekt'],
  tasks: ['aufgaben'],
  data: ['daten'],
  management: ['verwaltung', 'management'],
  evaluation: ['evaluierung', 'bewertung'],
  architecture: ['architektur'],
  profile: ['profil'],
  user: ['benutzer'],
  dashboard: ['dashboard', 'übersicht'],
  landing: ['startseite', 'home', 'landing'],
  reports: ['berichte', 'bericht'],
  generations: ['generierungen', 'generierung'],
  'how-to': ['anleitung', 'anleitungen', 'tutorial'],
  howto: ['anleitung', 'anleitungen', 'tutorial'],
  organizations: ['organisationen', 'organisation'],
  guides: ['anleitungen', 'leitfaden', 'tutorials'],
  models: ['modelle', 'llm', 'sprachmodelle'],
  llm: ['models', 'modelle', 'language models', 'sprachmodelle'],

  // German -> English mappings
  über: ['about'],
  projekte: ['projects'],
  projekt: ['project'],
  aufgaben: ['tasks'],
  daten: ['data'],
  verwaltung: ['management', 'administration'],
  evaluierung: ['evaluation'],
  architektur: ['architecture'],
  profil: ['profile'],
  benutzer: ['user'],
  übersicht: ['dashboard', 'overview'],
  startseite: ['landing', 'home'],
  berichte: ['reports'],
  bericht: ['report', 'reports'],
  generierungen: ['generations'],
  generierung: ['generation', 'generations'],
  anleitung: ['how-to', 'howto', 'guide'],
  anleitungen: ['how-to', 'guides', 'tutorials'],
  tutorial: ['how-to', 'tutorial', 'guide'],
  organisationen: ['organizations'],
  organisation: ['organization', 'organizations'],
  modelle: ['models', 'llm'],
  sprachmodelle: ['language models', 'llm', 'models'],
}

function useAutocomplete({ onNavigate }: { onNavigate: () => void }) {
  let id = useId()
  let router = useRouter()
  const { user, organizations } = useAuth()
  const { flags } = useFeatureFlags()
  const { t, locale, isReady } = useI18n()
  let [autocompleteState, setAutocompleteState] = useState<
    AutocompleteState<Result> | EmptyObject
  >({})

  // State for real-time project search
  const [projectResults, setProjectResults] = useState<Result[]>([])
  const searchTimeoutRef = useRef<NodeJS.Timeout | null>(null)

  function navigate({ itemUrl }: { itemUrl?: string }) {
    if (!itemUrl || typeof itemUrl !== 'string') {
      console.warn('Invalid navigation URL:', itemUrl)
      return
    }

    try {
      router.push(itemUrl)
      onNavigate()
    } catch (error) {
      console.error('Navigation failed:', error)
    }
  }

  // Get localized search results
  const getLocalizedResults = useCallback(() => {
    // Wait for translations to be ready to avoid displaying raw translation keys
    if (!isReady) {
      return []
    }

    const allPages = []

    // BenGER Core
    allPages.push(
      {
        url: '/',
        title: t('search.pages.landing.title'),
        description: t('search.pages.landing.description'),
        category: t('search.categories.benger'),
      },
      {
        url: '/dashboard',
        title: t('search.pages.dashboard.title'),
        description: t('search.pages.dashboard.description'),
        category: t('search.categories.benger'),
      }
    )

    // Add Reports if feature flag is enabled
    if (flags?.reports) {
      allPages.push({
        url: '/reports',
        title: t('search.pages.reports.title'),
        description: t('search.pages.reports.description'),
        category: t('search.categories.benger'),
      })
    }

    // Add Leaderboards if feature flag is enabled
    if (flags?.leaderboards) {
      allPages.push({
        url: '/leaderboards',
        title: t('search.pages.leaderboards.title'),
        description: t('search.pages.leaderboards.description'),
        category: t('search.categories.benger'),
      })
    }

    allPages.push({
      url: '/architecture',
      title: t('search.pages.architecture.title'),
      description: t('search.pages.architecture.description'),
      category: t('search.categories.benger'),
    })

    // Projects & Data
    allPages.push(
      {
        url: '/projects',
        title: t('search.pages.projects.title'),
        description: t('search.pages.projects.description'),
        category: t('search.categories.projectsAndData'),
      },
      {
        url: '/projects/create',
        title: t('search.pages.createProject.title'),
        description: t('search.pages.createProject.description'),
        category: t('search.categories.projectsAndData'),
      }
    )

    // Add Data Management if feature flag is enabled
    if (flags?.data) {
      allPages.push({
        url: '/data',
        title: t('search.pages.dataManagement.title'),
        description: t('search.pages.dataManagement.description'),
        category: t('search.categories.projectsAndData'),
      })
    }

    // Add Generations if feature flag is enabled
    if (flags?.generations) {
      allPages.push({
        url: '/generations',
        title: t('search.pages.generations.title'),
        description: t('search.pages.generations.description'),
        category: t('search.categories.projectsAndData'),
      })
    }

    // Add Evaluations if feature flag is enabled
    if (flags?.evaluations) {
      allPages.push({
        url: '/evaluations',
        title: t('search.pages.evaluations.title'),
        description: t('search.pages.evaluations.description'),
        category: t('search.categories.projectsAndData'),
      })
    }

    // Knowledge
    // Add How-To if feature flag is enabled
    if (flags?.['how-to']) {
      allPages.push({
        url: '/how-to',
        title: t('search.pages.howTo.title'),
        description: t('search.pages.howTo.description'),
        category: t('search.categories.knowledge'),
      })
    }

    // Add Models page (always available, public page)
    allPages.push({
      url: '/models',
      title: t('search.pages.models.title'),
      description: t('search.pages.models.description'),
      category: t('search.categories.knowledge'),
    })

    // User Management
    allPages.push({
      url: '/profile',
      title: t('search.pages.profile.title'),
      description: t('search.pages.profile.description'),
      category: t('search.categories.user'),
    })

    // Administration (role-based)
    // Add Organizations for admins
    if (
      user?.is_superadmin ||
      organizations?.some((org: any) => org.role === 'ORG_ADMIN')
    ) {
      allPages.push({
        url: '/organizations',
        title: t('search.pages.organizations.title'),
        description: t('search.pages.organizations.description'),
        category: t('search.categories.administration'),
      })
    }

    // User Management for superadmins
    if (user?.is_superadmin) {
      allPages.push({
        url: '/admin/users',
        title: t('search.pages.userManagement.title'),
        description: t('search.pages.userManagement.description'),
        category: t('search.categories.administration'),
      })
    }

    return allPages
  }, [t, flags, user, organizations, isReady])

  // Memoize the localized results to prevent unnecessary re-translations
  const localizedResults = useMemo(() => {
    return getLocalizedResults()
  }, [getLocalizedResults])

  // Use a ref to provide current localizedResults to autocomplete getSources
  // This avoids stale closure issues when feature flags load after initial render
  const localizedResultsRef = useRef(localizedResults)
  useEffect(() => {
    localizedResultsRef.current = localizedResults
  }, [localizedResults])

  // Ref for project results to avoid stale closures in autocomplete
  const projectResultsRef = useRef<Result[]>([])
  // Ref to store autocomplete instance for triggering refresh
  const autocompleteRef = useRef<Autocomplete | null>(null)

  useEffect(() => {
    projectResultsRef.current = projectResults
    // Trigger autocomplete refresh when project results arrive
    if (autocompleteRef.current && projectResults.length > 0) {
      autocompleteRef.current.refresh()
    }
  }, [projectResults])

  // Debounced project search function
  const searchProjects = useCallback(
    async (query: string) => {
      if (!query || query.trim().length < 2 || !user) {
        setProjectResults([])
        return
      }

      try {
        const response = await projectsAPI.list(1, 10, query.trim(), false)
        const results: Result[] = response.items.map((project: Project) => ({
          url: `/projects/${project.id}`,
          title: project.title,
          description:
            project.description || t('search.pages.projects.noDescription'),
          category: t('search.categories.projectsAndData'),
        }))
        setProjectResults(results)
      } catch (error) {
        console.error('Project search failed:', error)
        setProjectResults([])
      }
    },
    [user, t]
  )

  // Expand query with cross-language terms
  const expandQueryWithTranslations = (query: string): string[] => {
    const queryLower = query.toLowerCase()
    const expandedTerms = [queryLower]

    // Check if the query matches any cross-language mappings
    Object.entries(CROSS_LANGUAGE_MAPPINGS).forEach(([term, translations]) => {
      if (queryLower.includes(term.toLowerCase())) {
        translations.forEach((translation) => {
          expandedTerms.push(
            queryLower.replace(term.toLowerCase(), translation)
          )
        })
      }
    })

    // Also check individual words
    const words = queryLower.split(/\s+/)
    words.forEach((word) => {
      if (CROSS_LANGUAGE_MAPPINGS[word]) {
        expandedTerms.push(...CROSS_LANGUAGE_MAPPINGS[word])
      }
    })

    return [...new Set(expandedTerms)] // Remove duplicates
  }

  // eslint-disable-next-line react-hooks/refs -- Valid: one-time ref initialization in useState initializer
  let [autocomplete] = useState<Autocomplete>(() => {
    const instance = createAutocomplete<
      Result,
      React.SyntheticEvent,
      React.MouseEvent,
      React.KeyboardEvent
    >({
      id,
      placeholder: '',
      defaultActiveItemId: 0,
      onStateChange({ state }) {
        setAutocompleteState(state)
        // Trigger debounced project search when query changes
        if (searchTimeoutRef.current) {
          clearTimeout(searchTimeoutRef.current)
        }
        if (state.query && state.query.length >= 2) {
          searchTimeoutRef.current = setTimeout(() => {
            searchProjects(state.query)
          }, 300)
        } else {
          setProjectResults([])
        }
      },
      shouldPanelOpen({ state }) {
        return state.query !== ''
      },
      navigator: {
        navigate,
      },
      getSources({ query }) {
        return Promise.resolve([
          {
            sourceId: 'documentation',
            getItems() {
              try {
                if (!query || typeof query !== 'string') {
                  return []
                }

                const trimmedQuery = query.trim()
                if (trimmedQuery.length === 0) {
                  return []
                }

                // Combine static pages with dynamic project results
                const allMockResults = [
                  ...localizedResultsRef.current,
                  ...projectResultsRef.current,
                ]

                // Expand query with cross-language terms
                const expandedQueries =
                  expandQueryWithTranslations(trimmedQuery)

                // Multi-field search with enhanced multilingual relevance scoring
                const scoredResults = allMockResults.map((result) => {
                  if (
                    !result.title ||
                    !result.description ||
                    !result.url ||
                    !result.category
                  ) {
                    return null
                  }

                  let score = 0

                  // Check against all expanded queries
                  expandedQueries.forEach((queryTerm) => {
                    const lowerQuery = queryTerm.toLowerCase()

                    // Title matching (highest priority)
                    if (result.title.toLowerCase() === lowerQuery) {
                      score += 100
                    } else if (
                      result.title.toLowerCase().includes(lowerQuery)
                    ) {
                      score += 50
                    }

                    // Description matching
                    if (result.description.toLowerCase().includes(lowerQuery)) {
                      score += 25
                    }

                    // Category matching
                    if (result.category.toLowerCase().includes(lowerQuery)) {
                      score += 10
                    }

                    // URL matching (for direct paths)
                    if (result.url.toLowerCase().includes(lowerQuery)) {
                      score += 15
                    }

                    // Partial and multi-word matches
                    try {
                      const titleWords = result.title.toLowerCase().split(/\s+/)
                      const descWords = result.description
                        .toLowerCase()
                        .split(/\s+/)
                      const queryWords = lowerQuery.split(/\s+/)

                      queryWords.forEach((qWord) => {
                        if (qWord.length > 0) {
                          // Partial word matching
                          if (
                            titleWords.some((tWord: string) =>
                              tWord.startsWith(qWord)
                            )
                          ) {
                            score += 15
                          }
                          if (
                            descWords.some((dWord: string) =>
                              dWord.startsWith(qWord)
                            )
                          ) {
                            score += 5
                          }

                          // Fuzzy matching for common typos
                          if (
                            titleWords.some((tWord: string) =>
                              isCloseMatch(tWord, qWord)
                            )
                          ) {
                            score += 8
                          }
                        }
                      })
                    } catch (error) {
                      console.warn('Error in word matching:', error)
                    }
                  })

                  return score > 0 ? { ...result, score } : null
                })

                // Filter out null results
                const validResults = scoredResults.filter(
                  (
                    result
                  ): result is {
                    url: string
                    title: string
                    description: string
                    category: string
                    score: number
                  } => result !== null && result.score > 0
                )

                // Role-based filtering
                const filteredResults = validResults.filter((result) => {
                  if (
                    !result.url ||
                    !result.title ||
                    typeof result.url !== 'string'
                  ) {
                    return false
                  }

                  // Filter admin pages for non-superadmin users
                  if (
                    result.category === t('search.categories.administration')
                  ) {
                    return user?.is_superadmin
                  }
                  return true
                })

                // Sort by relevance score (descending) and return top 5 results
                return filteredResults
                  .sort((a, b) => b.score - a.score)
                  .slice(0, 5)
                  .map(({ score, ...result }) => result) // Remove score from final results
              } catch (error) {
                console.error('Search error:', error)
                // Return graceful fallback results from ref
                return localizedResultsRef.current.slice(0, 3)
              }
            },
            getItemUrl({ item }) {
              if (!item || !item.url || typeof item.url !== 'string') {
                console.warn('Invalid search result item:', item)
                return '#'
              }

              try {
                const url = item.url.trim()
                if (!url.startsWith('/') && !url.startsWith('http')) {
                  console.warn('Invalid URL format:', url)
                  return '#'
                }
                return url
              } catch (error) {
                console.error('URL validation error:', error)
                return '#'
              }
            },
            onSelect: navigate,
          },
        ])
      },
    })
    // Store instance in ref for triggering refresh
    autocompleteRef.current = instance
    return instance
  })

  return { autocomplete, autocompleteState }
}

function SearchIcon(props: React.ComponentPropsWithoutRef<'svg'>) {
  return (
    <svg viewBox="0 0 20 20" fill="none" aria-hidden="true" {...props}>
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M12.01 12a4.25 4.25 0 1 0-6.02-6 4.25 4.25 0 0 0 6.02 6Zm0 0 3.24 3.25"
      />
    </svg>
  )
}

function NoResultsIcon(props: React.ComponentPropsWithoutRef<'svg'>) {
  return (
    <svg viewBox="0 0 20 20" fill="none" aria-hidden="true" {...props}>
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M12.01 12a4.237 4.237 0 0 0 1.24-3c0-.62-.132-1.207-.37-1.738M12.01 12A4.237 4.237 0 0 1 9 13.25c-.635 0-1.237-.14-1.777-.388M12.01 12l3.24 3.25m-3.715-9.661a4.25 4.25 0 0 0-5.975 5.908M4.5 15.5l11-11"
      />
    </svg>
  )
}

function LoadingIcon(props: React.ComponentPropsWithoutRef<'svg'>) {
  let id = useId()

  return (
    <svg viewBox="0 0 20 20" fill="none" aria-hidden="true" {...props}>
      <circle cx="10" cy="10" r="5.5" strokeLinejoin="round" />
      <path
        stroke={`url(#${id})`}
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M15.5 10a5.5 5.5 0 1 0-5.5 5.5"
      />
      <defs>
        <linearGradient
          id={id}
          x1="13"
          x2="9.5"
          y1="9"
          y2="15"
          gradientUnits="userSpaceOnUse"
        >
          <stop stopColor="currentColor" />
          <stop offset="1" stopColor="currentColor" stopOpacity="0" />
        </linearGradient>
      </defs>
    </svg>
  )
}

function HighlightQuery({ text, query }: { text: string; query: string }) {
  return (
    <Highlighter
      highlightClassName="underline bg-transparent text-emerald-500 dark:text-emerald-400"
      searchWords={[query]}
      autoEscape={true}
      textToHighlight={text}
    />
  )
}

function SearchResult({
  result,
  resultIndex,
  autocomplete,
  collection,
  query,
}: {
  result: Result
  resultIndex: number
  autocomplete: Autocomplete
  collection: AutocompleteCollection<Result>
  query: string
}) {
  let id = useId()

  let sectionTitle = navigation.find((section) =>
    section.links.find(
      (link) => result.url && link.href === result.url.split('#')[0]
    )
  )?.title
  let hierarchy = [sectionTitle, result.pageTitle].filter(
    (x): x is string => typeof x === 'string'
  )

  // Use category from search result or fall back to navigation hierarchy
  let category = result.category || sectionTitle
  let displayHierarchy = category ? [category] : hierarchy

  return (
    <li
      className={clsx(
        'group block cursor-default px-4 py-3 hover:bg-zinc-50 aria-selected:bg-zinc-50 dark:hover:bg-zinc-700/30 dark:aria-selected:bg-zinc-700/50',
        resultIndex > 0 && 'border-t border-zinc-100 dark:border-zinc-700'
      )}
      aria-labelledby={`${id}-hierarchy ${id}-title`}
      {...autocomplete.getItemProps({
        item: result,
        source: collection.source,
      })}
    >
      <div
        id={`${id}-title`}
        aria-hidden="true"
        className="text-sm font-medium text-zinc-900 group-aria-selected:text-emerald-500 dark:text-white dark:group-aria-selected:text-emerald-400"
      >
        <HighlightQuery text={result.title} query={query} />
      </div>
      {result.description && (
        <div className="mt-1 line-clamp-2 text-xs text-zinc-600 dark:text-zinc-400">
          <HighlightQuery text={result.description} query={query} />
        </div>
      )}
      {displayHierarchy.length > 0 && (
        <div
          id={`${id}-hierarchy`}
          aria-hidden="true"
          className="mt-1 truncate whitespace-nowrap text-2xs text-zinc-500 dark:text-zinc-400"
        >
          {displayHierarchy.map((item, itemIndex, items) => (
            <Fragment key={itemIndex}>
              <HighlightQuery text={item} query={query} />
              <span
                className={
                  itemIndex === items.length - 1
                    ? 'sr-only'
                    : 'mx-2 text-zinc-300 dark:text-zinc-600'
                }
              >
                /
              </span>
            </Fragment>
          ))}
        </div>
      )}
    </li>
  )
}

function SearchResults({
  autocomplete,
  query,
  collection,
}: {
  autocomplete: Autocomplete
  query: string
  collection: AutocompleteCollection<Result>
}) {
  const { t } = useI18n()

  if (!collection || !collection.items || collection.items.length === 0) {
    return (
      <div className="p-6 text-center">
        <NoResultsIcon className="mx-auto h-5 w-5 stroke-zinc-900 dark:stroke-zinc-400" />
        <p className="mt-2 text-xs text-zinc-700 dark:text-zinc-300">
          {t('search.noResults')}{' '}
          <strong className="break-words font-semibold text-zinc-900 dark:text-white">
            &lsquo;{query}&rsquo;
          </strong>
          . {t('search.tryAgain')}
        </p>
      </div>
    )
  }

  return (
    <ul {...autocomplete.getListProps()}>
      {collection.items.map((result, resultIndex) => (
        <SearchResult
          key={result.url}
          result={result}
          resultIndex={resultIndex}
          autocomplete={autocomplete}
          collection={collection}
          query={query}
        />
      ))}
    </ul>
  )
}

const SearchInput = forwardRef<
  React.ElementRef<'input'>,
  {
    autocomplete: Autocomplete
    autocompleteState: AutocompleteState<Result> | EmptyObject
    onClose: () => void
  }
>(function SearchInput({ autocomplete, autocompleteState, onClose }, inputRef) {
  const { t } = useI18n()
  let inputProps = autocomplete.getInputProps({ inputElement: null })

  return (
    <div className="group relative flex h-12">
      <SearchIcon className="pointer-events-none absolute left-3 top-0 h-full w-5 stroke-zinc-500 dark:stroke-zinc-400" />
      <input
        ref={inputRef}
        data-autofocus
        className={clsx(
          'outline-hidden flex-auto appearance-none bg-transparent pl-10 text-zinc-900 placeholder:text-zinc-500 focus:w-full focus:flex-none dark:text-white dark:placeholder:text-zinc-400 sm:text-sm [&::-webkit-search-cancel-button]:hidden [&::-webkit-search-decoration]:hidden [&::-webkit-search-results-button]:hidden [&::-webkit-search-results-decoration]:hidden',
          autocompleteState.status === 'stalled' ? 'pr-11' : 'pr-4'
        )}
        {...inputProps}
        placeholder={inputProps.placeholder || t('search.placeholder')}
        onKeyDown={(event) => {
          if (
            event.key === 'Escape' &&
            !autocompleteState.isOpen &&
            autocompleteState.query === ''
          ) {
            if (document.activeElement instanceof HTMLElement) {
              document.activeElement.blur()
            }

            onClose()
          } else {
            inputProps.onKeyDown(event)
          }
        }}
      />
      {autocompleteState.status === 'stalled' && (
        <div className="absolute inset-y-0 right-3 flex items-center">
          <LoadingIcon className="h-5 w-5 animate-spin stroke-zinc-200 text-zinc-900 dark:stroke-zinc-800 dark:text-emerald-400" />
        </div>
      )}
    </div>
  )
})

function SearchDialog({
  open,
  setOpen,
  className,
  onNavigate = () => {},
}: {
  open: boolean
  setOpen: (open: boolean) => void
  className?: string
  onNavigate?: () => void
}) {
  let formRef = useRef<React.ElementRef<'form'>>(null)
  let panelRef = useRef<React.ElementRef<'div'>>(null)
  let inputRef = useRef<React.ElementRef<typeof SearchInput>>(null)
  let { autocomplete, autocompleteState } = useAutocomplete({
    onNavigate() {
      onNavigate()
      setOpen(false)
    },
  })
  let pathname = usePathname()
  let searchParams = useSearchParams()

  useEffect(() => {
    setOpen(false)
  }, [pathname, searchParams, setOpen])

  useEffect(() => {
    if (open) {
      return
    }

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'k' && (event.metaKey || event.ctrlKey)) {
        event.preventDefault()
        setOpen(true)
      }
    }

    window.addEventListener('keydown', onKeyDown)

    return () => {
      window.removeEventListener('keydown', onKeyDown)
    }
  }, [open, setOpen])

  return (
    <Dialog
      open={open}
      onClose={() => {
        setOpen(false)
        autocomplete.setQuery('')
      }}
      className={clsx('fixed inset-0 z-50', className)}
    >
      <DialogBackdrop
        transition
        className="backdrop-blur-xs data-closed:opacity-0 data-enter:duration-300 data-enter:ease-out data-leave:duration-200 data-leave:ease-in fixed inset-0 bg-zinc-400/25 dark:bg-black/40"
      />

      <div className="fixed inset-0 overflow-y-auto px-4 py-4 sm:px-6 sm:py-20 md:py-32 lg:px-8 lg:py-[15vh]">
        <DialogPanel
          transition
          className="ring-zinc-900/7.5 data-closed:scale-95 data-closed:opacity-0 data-enter:duration-300 data-enter:ease-out data-leave:duration-200 data-leave:ease-in mx-auto transform-gpu overflow-hidden rounded-lg bg-zinc-50 shadow-xl ring-1 dark:bg-zinc-900 dark:ring-zinc-800 sm:max-w-xl"
        >
          <div {...autocomplete.getRootProps({})}>
            <form
              ref={formRef}
              {...autocomplete.getFormProps({
                // eslint-disable-next-line react-hooks/refs -- Required by autocomplete library API
                inputElement: inputRef.current,
              })}
            >
              <SearchInput
                ref={inputRef}
                autocomplete={autocomplete}
                autocompleteState={autocompleteState}
                onClose={() => setOpen(false)}
              />
              <div
                ref={panelRef}
                className="border-t border-zinc-200 bg-white empty:hidden dark:border-zinc-100/5 dark:bg-zinc-800/90"
                {...autocomplete.getPanelProps({})}
              >
                {autocompleteState.isOpen && (
                  <SearchResults
                    autocomplete={autocomplete}
                    query={autocompleteState.query}
                    collection={autocompleteState.collections[0]}
                  />
                )}
              </div>
            </form>
          </div>
        </DialogPanel>
      </div>
    </Dialog>
  )
}

function useSearchProps() {
  let buttonRef = useRef<React.ElementRef<'button'>>(null)
  let [open, setOpen] = useState(false)

  return {
    buttonProps: {
      ref: buttonRef,
      onClick() {
        setOpen(true)
      },
    },
    dialogProps: {
      open,
      setOpen: useCallback(
        (open: boolean) => {
          let { width = 0, height = 0 } =
            buttonRef.current?.getBoundingClientRect() ?? {}
          if (!open || (width !== 0 && height !== 0)) {
            setOpen(open)
          }
        },
        [setOpen]
      ),
    },
  }
}

export function Search() {
  const { t } = useI18n()
  // Use lazy initializer for platform detection
  let [modifierKey] = useState<string | undefined>(() => {
    if (typeof navigator === 'undefined') return undefined
    return /(Mac|iPhone|iPod|iPad)/i.test(navigator.platform) ? '⌘' : 'Ctrl '
  })
  let { buttonProps, dialogProps } = useSearchProps()

  return (
    <div className="hidden w-full lg:block">
      <button
        type="button"
        className="hidden h-8 w-full items-center gap-2 rounded-full bg-white pl-2 pr-3 text-sm text-zinc-500 ring-1 ring-zinc-900/10 transition hover:ring-zinc-900/20 dark:bg-white/5 dark:text-zinc-400 dark:ring-inset dark:ring-white/10 dark:hover:ring-white/20 lg:flex"
        {...buttonProps}
      >
        <SearchIcon className="h-5 w-5 stroke-current" />
        {t('search.placeholder')}
        <kbd className="ml-auto text-2xs text-zinc-400 dark:text-zinc-500">
          <kbd className="font-sans">{modifierKey}</kbd>
          <kbd className="font-sans">K</kbd>
        </kbd>
      </button>
      <Suspense fallback={null}>
        <SearchDialog className="hidden lg:block" {...dialogProps} />
      </Suspense>
    </div>
  )
}

export function MobileSearch() {
  const { t } = useI18n()
  let { close } = useMobileNavigationStore()
  let { buttonProps, dialogProps } = useSearchProps()

  return (
    <div className="contents lg:hidden">
      <button
        type="button"
        className="relative flex size-6 items-center justify-center rounded-md transition hover:bg-zinc-900/5 dark:hover:bg-white/5 lg:hidden"
        aria-label={t('search.placeholder')}
        {...buttonProps}
      >
        <span className="pointer-fine:hidden absolute size-12" />
        <SearchIcon className="h-5 w-5 stroke-zinc-900 dark:stroke-white" />
      </button>
      <Suspense fallback={null}>
        <SearchDialog
          className="lg:hidden"
          onNavigate={close}
          {...dialogProps}
        />
      </Suspense>
    </div>
  )
}

'use client'

/**
 * Project picker of the evaluations page: a dropdown of the viewer's
 * projects with a search box (server-side `search`, debounced) and paging
 * ("Show more" loads the next page), so every project is reachable, not
 * only the first page.
 */

import { Button } from '@/components/shared/Button'
import { useI18n } from '@/contexts/I18nContext'
import { projectsAPI } from '@/lib/api/projects'
import type { Project } from '@/types/labelStudio'
import { ChevronDownIcon } from '@heroicons/react/24/outline'
import { useCallback, useEffect, useRef, useState } from 'react'

/** Projects per page of the picker. */
export const PROJECT_PAGE_SIZE = 100
/** Delay before a typed search is sent. */
export const PROJECT_SEARCH_DEBOUNCE_MS = 300

export interface ProjectListState {
  projects: Project[]
  total: number
  search: string
  setSearch: (value: string) => void
  hasMore: boolean
  loadMore: () => void
  loading: boolean
  /** Whether the first page has been answered (or failed). */
  loaded: boolean
}

/**
 * The viewer's projects, one page at a time, filtered by `search`. Waits
 * for `enabled` (auth resolved) before the first request.
 */
export function useProjectList(enabled: boolean): ProjectListState {
  const [projects, setProjects] = useState<Project[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(false)
  const [loaded, setLoaded] = useState(false)
  const requestRef = useRef(0)

  // Debounce the typed search into the query that is sent.
  useEffect(() => {
    if (search === query) return
    const timer = setTimeout(() => setQuery(search), PROJECT_SEARCH_DEBOUNCE_MS)
    return () => clearTimeout(timer)
  }, [search, query])

  const load = useCallback(async (nextPage: number, term: string) => {
    const request = ++requestRef.current
    setLoading(true)
    try {
      const response = term
        ? await projectsAPI.list(nextPage, PROJECT_PAGE_SIZE, term)
        : await projectsAPI.list(nextPage, PROJECT_PAGE_SIZE)
      if (request !== requestRef.current) return
      // API returns 'items' field for paginated results
      const items = response?.items || []
      setProjects((prev) => (nextPage === 1 ? items : [...prev, ...items]))
      setTotal(typeof response?.total === 'number' ? response.total : 0)
      setPage(nextPage)
    } catch (err) {
      console.error('Failed to load projects:', err)
    } finally {
      if (request === requestRef.current) {
        setLoading(false)
        setLoaded(true)
      }
    }
  }, [])

  useEffect(() => {
    if (!enabled) return
    void load(1, query)
  }, [enabled, query, load])

  const hasMore = total > projects.length
  const loadMore = useCallback(() => {
    if (!loading && hasMore) void load(page + 1, query)
  }, [loading, hasMore, load, page, query])

  return {
    projects,
    total,
    search,
    setSearch,
    hasMore,
    loadMore,
    loading,
    loaded,
  }
}

export interface ProjectPickerProps {
  list: ProjectListState
  selectedProject: Project | null
  onSelect: (project: Project) => void
}

export function ProjectPicker({
  list,
  selectedProject,
  onSelect,
}: ProjectPickerProps) {
  const { t } = useI18n()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  // Close the dropdown when clicking outside.
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  return (
    <div className="relative" ref={ref}>
      <span className="mb-1 block text-xs font-medium text-zinc-500">
        {t('evaluation.viewer.filters.project')}
      </span>
      <Button
        variant="outline"
        onClick={() => setOpen(!open)}
        className="w-40 justify-between"
      >
        <span className="truncate">
          {selectedProject?.title ||
            t('evaluation.viewer.filters.selectProject')}
        </span>
        <ChevronDownIcon
          className={`ml-2 h-4 w-4 opacity-70 transition-transform ${open ? 'rotate-180' : ''}`}
        />
      </Button>
      {open && (
        <div
          className="absolute z-50 mt-1 w-72 max-w-[calc(100vw-2rem)] rounded-lg border border-zinc-200 bg-white shadow-lg dark:border-zinc-700 dark:bg-zinc-800"
          data-testid="project-picker-panel"
        >
          <div className="border-b border-zinc-200 p-2 dark:border-zinc-700">
            <input
              type="search"
              value={list.search}
              onChange={(e) => list.setSearch(e.target.value)}
              placeholder={t('evaluation.viewer.filters.searchProjects')}
              aria-label={t('evaluation.viewer.filters.searchProjects')}
              className="w-full rounded-md border border-zinc-300 bg-white px-2.5 py-1.5 text-sm text-zinc-900 placeholder:text-zinc-400 focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 focus:outline-none dark:border-zinc-600 dark:bg-zinc-900 dark:text-zinc-100"
              data-testid="project-picker-search"
              autoFocus
            />
          </div>
          <div className="max-h-60 overflow-auto">
            {list.projects.map((project) => (
              <button
                key={project.id}
                onClick={() => {
                  onSelect(project)
                  setOpen(false)
                }}
                className={`w-full px-3 py-2 text-left text-sm text-zinc-900 hover:bg-zinc-50 dark:text-zinc-100 dark:hover:bg-zinc-700 ${
                  selectedProject?.id === project.id
                    ? 'bg-emerald-50 dark:bg-emerald-900/20'
                    : ''
                }`}
              >
                <div className="font-medium">{project.title}</div>
                <div className="text-xs text-zinc-500">
                  {project.task_count || 0}{' '}
                  {t('evaluation.viewer.filters.tasks')}
                </div>
              </button>
            ))}
            {list.loaded && !list.loading && list.projects.length === 0 && (
              <p className="px-3 py-3 text-sm text-zinc-500 dark:text-zinc-400">
                {t('evaluation.viewer.filters.noProjectsFound')}
              </p>
            )}
          </div>
          {list.hasMore && (
            <div className="border-t border-zinc-200 p-2 dark:border-zinc-700">
              <button
                type="button"
                onClick={list.loadMore}
                disabled={list.loading}
                className="w-full rounded px-2 py-1 text-left text-xs font-medium text-emerald-700 hover:bg-zinc-50 disabled:opacity-50 dark:text-emerald-400 dark:hover:bg-zinc-700"
                data-testid="project-picker-more"
              >
                {t('evaluation.viewer.filters.moreProjects', {
                  shown: list.projects.length,
                  total: list.total,
                })}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

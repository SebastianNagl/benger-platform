'use client'

/**
 * CloudImportPanel — the real body of the "Cloud-Speicher" import tab.
 *
 * Data flow: org picker (user's orgs) → connection picker (member-visible
 * org storage connections) → server-side object browser (breadcrumbs from
 * the '/'-delimited prefixes, file rows with checkboxes on importable
 * extensions, "load more" paging via next_token).
 *
 * Two modes:
 * - `select` (project-creation wizard): the selection is reported up via
 *   `onSelectionChange` and imported by the wizard after project creation.
 * - `immediate` (project-page ImportDataModal): an import button drives
 *   `runCloudImportJobs` with progress + toasts, plus a compact history of
 *   past cloud imports with a re-run action.
 */

import { Button } from '@/components/shared/Button'
import { useToast } from '@/components/shared/Toast'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { useProgress } from '@/contexts/ProgressContext'
import {
  organizationsAPI,
  type OrgStorageConnection,
  type OrgStorageObject,
} from '@/lib/api/organizations'
import {
  projectsAPI,
  type CloudImportHistoryEntry,
} from '@/lib/api/projects'
import {
  ArrowPathIcon,
  DocumentIcon,
  FolderIcon,
} from '@heroicons/react/24/outline'
import { useCallback, useEffect, useRef, useState } from 'react'

export interface CloudImportSelection {
  organizationId: string
  connectionId: string
  objectKeys: string[]
}

interface CloudImportPanelProps {
  /** `select`: report the selection up; `immediate`: import right here. */
  mode: 'select' | 'immediate'
  /** Required in `immediate` mode. */
  projectId?: string
  /** Restore a previous selection (wizard tab switches unmount the panel). */
  initialSelection?: CloudImportSelection | null
  onSelectionChange?: (selection: CloudImportSelection) => void
  onImportComplete?: () => void
}

/** File extensions the cloud-import worker accepts (mirror of the backend). */
export const IMPORTABLE_EXTENSIONS = [
  '.json',
  '.ndjson',
  '.json.gz',
  '.csv',
  '.tsv',
  '.txt',
]

/** Hard cap on files per cloud import (mirror of the backend). */
export const MAX_CLOUD_IMPORT_FILES = 20

export function isImportableKey(key: string): boolean {
  const lower = key.toLowerCase()
  return IMPORTABLE_EXTENSIONS.some((ext) => lower.endsWith(ext))
}

const basename = (key: string): string => {
  const trimmed = key.endsWith('/') ? key.slice(0, -1) : key
  const idx = trimmed.lastIndexOf('/')
  return idx >= 0 ? trimmed.slice(idx + 1) : trimmed
}

const formatSize = (size: number | null): string => {
  if (size === null || size === undefined) return ''
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  if (size < 1024 * 1024 * 1024) return `${(size / (1024 * 1024)).toFixed(1)} MB`
  return `${(size / (1024 * 1024 * 1024)).toFixed(1)} GB`
}

const formatDate = (iso: string | null): string => {
  if (!iso) return ''
  const d = new Date(iso)
  return isNaN(d.getTime()) ? '' : d.toLocaleString()
}

export function CloudImportPanel({
  mode,
  projectId,
  initialSelection,
  onSelectionChange,
  onImportComplete,
}: CloudImportPanelProps) {
  const { t } = useI18n()
  const { addToast } = useToast()
  const { organizations } = useAuth()
  const { startProgress, updateProgress, completeProgress } = useProgress()

  const [organizationId, setOrganizationId] = useState<string>(
    initialSelection?.organizationId ?? ''
  )
  const [connections, setConnections] = useState<OrgStorageConnection[]>([])
  const [connectionsLoading, setConnectionsLoading] = useState(false)
  const [connectionId, setConnectionId] = useState<string>(
    initialSelection?.connectionId ?? ''
  )

  const [currentPrefix, setCurrentPrefix] = useState('')
  const [objects, setObjects] = useState<OrgStorageObject[]>([])
  const [prefixes, setPrefixes] = useState<string[]>([])
  const [nextToken, setNextToken] = useState<string | null>(null)
  const [browseLoading, setBrowseLoading] = useState(false)
  const [browseError, setBrowseError] = useState<string | null>(null)

  const [selectedKeys, setSelectedKeys] = useState<string[]>(
    initialSelection?.objectKeys ?? []
  )
  const [importing, setImporting] = useState(false)

  const [history, setHistory] = useState<CloudImportHistoryEntry[]>([])
  const [historyLoading, setHistoryLoading] = useState(false)

  // Only restore the initial selection once — later org/connection changes
  // must start from a clean slate.
  const restoredRef = useRef(false)

  const connection = connections.find((c) => c.id === connectionId) || null

  const reportSelection = useCallback(
    (orgId: string, connId: string, keys: string[]) => {
      onSelectionChange?.({
        organizationId: orgId,
        connectionId: connId,
        objectKeys: keys,
      })
    },
    [onSelectionChange]
  )

  // Auto-select the only org.
  useEffect(() => {
    if (!organizationId && organizations.length === 1) {
      setOrganizationId(organizations[0].id)
    }
  }, [organizationId, organizations])

  // Org change → load its connections.
  useEffect(() => {
    if (!organizationId) {
      setConnections([])
      return
    }
    let cancelled = false
    setConnectionsLoading(true)
    organizationsAPI
      .listStorageConnections(organizationId)
      .then((data) => {
        if (!cancelled) setConnections(data || [])
      })
      .catch(() => {
        if (!cancelled) setConnections([])
      })
      .finally(() => {
        if (!cancelled) setConnectionsLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [organizationId])

  const loadListing = useCallback(
    async (
      orgId: string,
      connId: string,
      prefix: string,
      token?: string | null
    ) => {
      setBrowseLoading(true)
      setBrowseError(null)
      try {
        const page = await organizationsAPI.listStorageConnectionObjects(
          orgId,
          connId,
          {
            prefix,
            continuationToken: token || undefined,
            maxResults: 100,
          }
        )
        setObjects((prev) => (token ? [...prev, ...page.objects] : page.objects))
        setPrefixes((prev) =>
          token ? [...prev, ...page.prefixes] : page.prefixes
        )
        setNextToken(page.next_token)
      } catch (error: any) {
        setBrowseError(
          error?.response?.data?.detail || t('dataImport.cloud.browseFailed')
        )
      } finally {
        setBrowseLoading(false)
      }
    },
    [t]
  )

  // Connection change → jump to its root prefix and list it.
  useEffect(() => {
    if (!organizationId || !connectionId || !connection) return
    const restoring =
      !restoredRef.current &&
      initialSelection &&
      initialSelection.connectionId === connectionId
    restoredRef.current = true
    setCurrentPrefix(connection.prefix || '')
    setObjects([])
    setPrefixes([])
    setNextToken(null)
    if (!restoring) setSelectedKeys([])
    loadListing(organizationId, connectionId, connection.prefix || '')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [connectionId, connection?.id])

  const navigateTo = (prefix: string) => {
    if (!organizationId || !connectionId) return
    setCurrentPrefix(prefix)
    setObjects([])
    setPrefixes([])
    setNextToken(null)
    loadListing(organizationId, connectionId, prefix)
  }

  const handleOrgChange = (orgId: string) => {
    setOrganizationId(orgId)
    setConnectionId('')
    setObjects([])
    setPrefixes([])
    setNextToken(null)
    setSelectedKeys([])
    if (mode === 'select') reportSelection(orgId, '', [])
  }

  const handleConnectionChange = (connId: string) => {
    setConnectionId(connId)
    if (mode === 'select') reportSelection(organizationId, connId, [])
  }

  const toggleKey = (key: string) => {
    let next: string[]
    if (selectedKeys.includes(key)) {
      next = selectedKeys.filter((k) => k !== key)
    } else {
      if (selectedKeys.length >= MAX_CLOUD_IMPORT_FILES) return
      next = [...selectedKeys, key]
    }
    setSelectedKeys(next)
    if (mode === 'select') reportSelection(organizationId, connectionId, next)
  }

  const fetchHistory = useCallback(async () => {
    if (mode !== 'immediate' || !projectId) return
    setHistoryLoading(true)
    try {
      const data = await projectsAPI.listCloudImports(projectId)
      setHistory(data || [])
    } catch {
      setHistory([])
    } finally {
      setHistoryLoading(false)
    }
  }, [mode, projectId])

  useEffect(() => {
    fetchHistory()
  }, [fetchHistory])

  const runImport = async (connId: string, keys: string[]) => {
    if (!projectId || keys.length === 0 || importing) return
    const progressId = `cloud-import-${Date.now()}`
    setImporting(true)
    startProgress(progressId, t('dataImport.cloud.importing'), {
      sublabel: t('dataImport.cloud.importingFiles', { count: keys.length }),
      indeterminate: false,
    })
    try {
      let done = 0
      await projectsAPI.runCloudImportJobs(
        projectId,
        { connection_id: connId, object_keys: keys },
        {
          onStatus: (objectKey, status) => {
            if (status.status === 'completed' || status.status === 'failed') {
              done += 1
            }
            updateProgress(
              progressId,
              Math.min(95, Math.round((done / keys.length) * 100)),
              basename(objectKey)
            )
          },
        }
      )
      completeProgress(progressId, 'success')
      addToast(t('dataImport.cloud.importSuccess'), 'success')
      setSelectedKeys([])
      await fetchHistory()
      onImportComplete?.()
    } catch (error: any) {
      completeProgress(progressId, 'error')
      addToast(
        error?.message
          ? t('dataImport.cloud.importFailedWithReason', {
              reason: error.message,
            })
          : t('dataImport.cloud.importFailed'),
        'error'
      )
      await fetchHistory()
    } finally {
      setImporting(false)
    }
  }

  const handleImport = () => runImport(connectionId, selectedKeys)

  // Re-run resolves the connection by name — the history rows carry only the
  // connection's display name (the FK id is not serialized).
  const resolveHistoryConnection = (
    entry: CloudImportHistoryEntry
  ): string | null => {
    const match = connections.find((c) => c.name === entry.connection_name)
    return match ? match.id : null
  }

  const handleRerun = (entry: CloudImportHistoryEntry) => {
    const connId = resolveHistoryConnection(entry)
    if (!connId) return
    runImport(connId, [entry.object_key])
  }

  // Breadcrumbs relative to the connection's configured prefix (the jail).
  const rootPrefix = connection?.prefix || ''
  const relative = currentPrefix.startsWith(rootPrefix)
    ? currentPrefix.slice(rootPrefix.length)
    : currentPrefix
  const crumbs = relative.split('/').filter(Boolean)

  if (organizations.length === 0) {
    return (
      <div className="rounded-lg border border-zinc-200 bg-zinc-50 p-6 text-center dark:border-zinc-700 dark:bg-zinc-800/50">
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          {t('dataImport.cloud.noOrganizations')}
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-4" data-testid="cloud-import-panel">
      {/* Org + connection pickers */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div>
          <label className="mb-1 block text-xs font-medium text-zinc-700 dark:text-zinc-300">
            {t('dataImport.cloud.organization')}
          </label>
          <select
            value={organizationId}
            onChange={(e) => handleOrgChange(e.target.value)}
            className="w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 focus:outline-none focus:ring-2 focus:ring-emerald-500 dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-100"
            data-testid="cloud-import-org-select"
          >
            <option value="">
              {t('dataImport.cloud.selectOrganization')}
            </option>
            {organizations.map((org) => (
              <option key={org.id} value={org.id}>
                {org.display_name || org.name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-zinc-700 dark:text-zinc-300">
            {t('dataImport.cloud.connection')}
          </label>
          <select
            value={connectionId}
            onChange={(e) => handleConnectionChange(e.target.value)}
            disabled={!organizationId || connectionsLoading}
            className="w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 focus:outline-none focus:ring-2 focus:ring-emerald-500 disabled:opacity-50 dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-100"
            data-testid="cloud-import-connection-select"
          >
            <option value="">
              {connectionsLoading
                ? t('dataImport.cloud.loadingConnections')
                : t('dataImport.cloud.selectConnection')}
            </option>
            {connections.map((conn) => (
              <option key={conn.id} value={conn.id}>
                {conn.name} ({conn.bucket})
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* No connections in the chosen org */}
      {organizationId && !connectionsLoading && connections.length === 0 && (
        <div
          className="rounded-lg border border-zinc-200 bg-zinc-50 p-4 dark:border-zinc-700 dark:bg-zinc-800/50"
          data-testid="cloud-import-no-connections"
        >
          <p className="text-sm text-zinc-600 dark:text-zinc-400">
            {t('dataImport.cloud.noConnections')}
          </p>
        </div>
      )}

      {/* Object browser */}
      {connection && (
        <div className="rounded-lg border border-zinc-200 dark:border-zinc-700">
          {/* Breadcrumbs */}
          <div className="flex flex-wrap items-center gap-1 border-b border-zinc-200 px-3 py-2 text-sm dark:border-zinc-700">
            <button
              type="button"
              onClick={() => navigateTo(rootPrefix)}
              className="font-medium text-emerald-600 hover:underline dark:text-emerald-400"
              data-testid="cloud-import-breadcrumb-root"
            >
              {connection.bucket}
            </button>
            {crumbs.map((segment, i) => (
              <span key={i} className="flex items-center gap-1">
                <span className="text-zinc-400">/</span>
                <button
                  type="button"
                  onClick={() =>
                    navigateTo(
                      rootPrefix + crumbs.slice(0, i + 1).join('/') + '/'
                    )
                  }
                  className="text-emerald-600 hover:underline dark:text-emerald-400"
                >
                  {segment}
                </button>
              </span>
            ))}
            <button
              type="button"
              onClick={() => navigateTo(currentPrefix)}
              disabled={browseLoading}
              className="ml-auto p-1 text-zinc-400 hover:text-zinc-600 disabled:opacity-50 dark:hover:text-zinc-300"
              aria-label={t('dataImport.cloud.refresh')}
            >
              <ArrowPathIcon className="h-4 w-4" />
            </button>
          </div>

          {browseError ? (
            <div className="p-4 text-sm text-red-600 dark:text-red-400">
              {browseError}
            </div>
          ) : (
            <div className="max-h-72 overflow-y-auto">
              {/* Folders */}
              {prefixes.map((prefix) => (
                <button
                  key={prefix}
                  type="button"
                  onClick={() => navigateTo(prefix)}
                  className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-zinc-50 dark:hover:bg-zinc-800"
                  data-testid={`cloud-import-folder-${basename(prefix)}`}
                >
                  <FolderIcon className="h-4 w-4 flex-shrink-0 text-zinc-400" />
                  <span className="truncate text-zinc-900 dark:text-zinc-100">
                    {basename(prefix)}
                  </span>
                </button>
              ))}

              {/* Files */}
              {objects.map((obj) => {
                const importable = isImportableKey(obj.key)
                const checked = selectedKeys.includes(obj.key)
                const capReached =
                  !checked && selectedKeys.length >= MAX_CLOUD_IMPORT_FILES
                return (
                  <label
                    key={obj.key}
                    className={`flex items-center gap-2 px-3 py-2 text-sm ${
                      importable
                        ? 'cursor-pointer hover:bg-zinc-50 dark:hover:bg-zinc-800'
                        : 'opacity-50'
                    }`}
                    data-testid={`cloud-import-object-${basename(obj.key)}`}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      disabled={!importable || capReached || importing}
                      onChange={() => toggleKey(obj.key)}
                      className="h-4 w-4 rounded border-zinc-300 text-emerald-600 focus:ring-emerald-500"
                    />
                    <DocumentIcon className="h-4 w-4 flex-shrink-0 text-zinc-400" />
                    <span className="min-w-0 flex-1 truncate text-zinc-900 dark:text-zinc-100">
                      {basename(obj.key)}
                    </span>
                    <span className="whitespace-nowrap text-xs text-zinc-500 dark:text-zinc-400">
                      {formatSize(obj.size)}
                    </span>
                    <span className="whitespace-nowrap text-xs text-zinc-500 dark:text-zinc-400">
                      {formatDate(obj.last_modified)}
                    </span>
                  </label>
                )
              })}

              {!browseLoading &&
                prefixes.length === 0 &&
                objects.length === 0 && (
                  <p className="px-3 py-4 text-sm text-zinc-500 dark:text-zinc-400">
                    {t('dataImport.cloud.emptyFolder')}
                  </p>
                )}

              {browseLoading && (
                <p className="px-3 py-2 text-sm text-zinc-500 dark:text-zinc-400">
                  {t('dataImport.cloud.loadingObjects')}
                </p>
              )}

              {nextToken && !browseLoading && (
                <div className="px-3 py-2">
                  <Button
                    variant="outline"
                    onClick={() =>
                      loadListing(
                        organizationId,
                        connectionId,
                        currentPrefix,
                        nextToken
                      )
                    }
                    data-testid="cloud-import-load-more"
                  >
                    {t('dataImport.cloud.loadMore')}
                  </Button>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Selection summary + cap hint */}
      {connection && (
        <div className="flex items-center justify-between gap-3">
          <div className="text-sm text-zinc-600 dark:text-zinc-400">
            <span data-testid="cloud-import-selection-summary">
              {t('dataImport.cloud.selectionSummary', {
                count: selectedKeys.length,
              })}
            </span>
            {selectedKeys.length >= MAX_CLOUD_IMPORT_FILES && (
              <span className="ml-2 text-amber-600 dark:text-amber-400">
                {t('dataImport.cloud.selectionCapHint', {
                  max: MAX_CLOUD_IMPORT_FILES,
                })}
              </span>
            )}
          </div>
          {mode === 'immediate' && (
            <Button
              variant="filled"
              onClick={handleImport}
              disabled={selectedKeys.length === 0 || importing}
              data-testid="cloud-import-import-button"
            >
              {importing
                ? t('dataImport.cloud.importing')
                : t('dataImport.cloud.importButton')}
            </Button>
          )}
        </div>
      )}

      {/* Allowed extensions hint */}
      <p className="text-xs text-zinc-500 dark:text-zinc-400">
        {t('dataImport.cloud.allowedExtensions', {
          extensions: IMPORTABLE_EXTENSIONS.join(', '),
        })}
      </p>

      {/* Import history (immediate mode) */}
      {mode === 'immediate' && (
        <div data-testid="cloud-import-history">
          <h4 className="mb-2 text-sm font-medium text-zinc-900 dark:text-zinc-100">
            {t('dataImport.cloud.historyTitle')}
          </h4>
          {historyLoading ? (
            <p className="text-sm text-zinc-500 dark:text-zinc-400">
              {t('dataImport.cloud.historyLoading')}
            </p>
          ) : history.length === 0 ? (
            <p className="text-sm text-zinc-500 dark:text-zinc-400">
              {t('dataImport.cloud.historyEmpty')}
            </p>
          ) : (
            <div className="divide-y divide-zinc-200 rounded-lg border border-zinc-200 dark:divide-zinc-700 dark:border-zinc-700">
              {history.map((entry) => (
                <div
                  key={entry.job_id}
                  className="flex items-center gap-2 px-3 py-2 text-sm"
                >
                  <span className="min-w-0 flex-1 truncate text-zinc-900 dark:text-zinc-100">
                    {basename(entry.object_key)}
                  </span>
                  {entry.connection_name && (
                    <span className="whitespace-nowrap text-xs text-zinc-500 dark:text-zinc-400">
                      {entry.connection_name}
                    </span>
                  )}
                  <span
                    className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                      entry.status === 'completed'
                        ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400'
                        : entry.status === 'failed'
                          ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'
                          : 'bg-zinc-100 text-zinc-600 dark:bg-zinc-700 dark:text-zinc-400'
                    }`}
                  >
                    {t(`dataImport.cloud.status.${entry.status}`)}
                  </span>
                  <span className="whitespace-nowrap text-xs text-zinc-500 dark:text-zinc-400">
                    {formatDate(entry.created_at)}
                  </span>
                  <Button
                    variant="outline"
                    onClick={() => handleRerun(entry)}
                    disabled={importing || !resolveHistoryConnection(entry)}
                    title={
                      resolveHistoryConnection(entry)
                        ? undefined
                        : t('dataImport.cloud.rerunUnavailable')
                    }
                    data-testid={`cloud-import-rerun-${entry.job_id}`}
                  >
                    {t('dataImport.cloud.rerun')}
                  </Button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

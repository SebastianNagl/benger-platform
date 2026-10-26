'use client'

import { Button } from '@/components/shared/Button'
import { useI18n } from '@/contexts/I18nContext'
import { apiClient } from '@/lib/api/client'
import { formatDecimal, intlTag } from '@/lib/i18n/locales'
import { Dialog, Disclosure, Transition } from '@headlessui/react'
import {
  ArrowPathIcon,
  CheckIcon,
  ChevronDownIcon,
  ClipboardDocumentIcon,
  PlayIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline'
import { Fragment, useCallback, useEffect, useMemo, useState } from 'react'

interface GenerationResultModalProps {
  isOpen: boolean
  taskId: string
  modelId: string
  onClose: () => void
  onRegenerate?: (
    taskId: string,
    modelId: string,
    structureKeys?: string[],
  ) => void
  result?: any
  availableStructureKeys?: string[]
}

interface GenerationResult {
  task_id: string
  model_id: string
  generation_id: string
  status: string
  result?: Record<string, any>
  generated_at?: string
  generation_time_seconds?: number
  prompt_used?: string
  parameters?: Record<string, any>
  error_message?: string
  structure_key?: string
  created_by?: string
  created_by_name?: string
}

interface MultipleGenerationResults {
  task_id: string
  model_id: string
  results: GenerationResult[]
}

export function GenerationResultModal({
  isOpen,
  taskId,
  modelId,
  onClose,
  onRegenerate,
  result: providedResult,
  availableStructureKeys = [],
}: GenerationResultModalProps) {
  const { t, locale } = useI18n()
  const [loading, setLoading] = useState(true)
  const [results, setResults] = useState<GenerationResult[]>([])
  const [selectedStructureIndex, setSelectedStructureIndex] = useState(0)
  const [copied, setCopied] = useState(false)
  const [viewMode, setViewMode] = useState<'formatted' | 'raw'>('formatted')
  const [selectedStructureKeys, setSelectedStructureKeys] = useState<
    Set<string>
  >(new Set())
  const [showStructureSelection, setShowStructureSelection] = useState(false)

  // History tab state (Issue #1372)
  const [activeTab, setActiveTab] = useState<'current' | 'history'>('current')
  const [historyResults, setHistoryResults] = useState<GenerationResult[]>([])
  const [historyLoading, setHistoryLoading] = useState(false)
  const [historyFetched, setHistoryFetched] = useState(false)

  // Stabilize array reference to prevent infinite re-render loop
  const stableStructureKeys = useMemo(
    () => JSON.stringify(availableStructureKeys),
    [availableStructureKeys],
  )

  // Reset state when modal opens
  useEffect(() => {
    if (isOpen) {
      setSelectedStructureKeys(new Set(JSON.parse(stableStructureKeys)))
      setShowStructureSelection(false)
      setActiveTab('current')
      setHistoryResults([])
      setHistoryFetched(false)
      setHistoryLoading(false)
    }
  }, [isOpen, stableStructureKeys])

  const fetchResults = useCallback(async () => {
    try {
      setLoading(true)
      const params = new URLSearchParams({
        task_id: taskId,
        model_id: modelId,
      })
      const data: MultipleGenerationResults = await apiClient.get(
        `/generation-tasks/generation-result?${params}`,
      )
      setResults(data.results || [])
    } catch (error) {
      console.error('Failed to fetch generation results:', error)
      setResults([])
    } finally {
      setLoading(false)
    }
  }, [taskId, modelId])

  const fetchHistoryResults = useCallback(async () => {
    try {
      setHistoryLoading(true)
      const params = new URLSearchParams({
        task_id: taskId,
        model_id: modelId,
        include_history: 'true',
      })
      const data: MultipleGenerationResults = await apiClient.get(
        `/generation-tasks/generation-result?${params}`,
      )
      setHistoryResults(data.results || [])
    } catch (error) {
      console.error('Failed to fetch generation history:', error)
      setHistoryResults([])
    } finally {
      setHistoryLoading(false)
    }
  }, [taskId, modelId])

  useEffect(() => {
    if (providedResult) {
      // Use provided result (for testing)
      setResults([providedResult])
      setLoading(false)
    } else {
      // Fetch results from API (normal usage)
      fetchResults()
    }
  }, [taskId, modelId, providedResult, fetchResults])

  const handleCopy = async () => {
    const result = results[selectedStructureIndex]
    if (!result?.result) return

    try {
      const textToCopy =
        viewMode === 'raw'
          ? JSON.stringify(result.result, null, 2)
          : formatResult(result.result)

      await navigator.clipboard.writeText(textToCopy)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch (error) {
      console.error('Failed to copy to clipboard:', error)
    }
  }

  const formatResult = (data: any): string => {
    if (typeof data === 'string') return data
    if (typeof data === 'number' || typeof data === 'boolean')
      return String(data)
    if (Array.isArray(data)) return data.map(formatResult).join('\n')
    if (typeof data === 'object' && data !== null) {
      // If the data has a generated_text field, show it prominently first
      if (data.generated_text) {
        return data.generated_text
      }
      return Object.entries(data)
        .map(([key, value]) => `${key}: ${formatResult(value)}`)
        .join('\n')
    }
    return JSON.stringify(data)
  }

  const getStatusBadge = (status: string) => {
    const statusColors: Record<string, string> = {
      completed:
        'bg-emerald-100 dark:bg-emerald-900/30 text-emerald-800 dark:text-emerald-300',
      failed: 'bg-red-100 dark:bg-red-900/30 text-red-800 dark:text-red-300',
      running:
        'bg-amber-100 dark:bg-amber-900/30 text-amber-800 dark:text-amber-300',
      pending: 'bg-zinc-100 dark:bg-zinc-800 text-zinc-800 dark:text-zinc-200',
      cancelled:
        'bg-orange-100 dark:bg-orange-900/30 text-orange-800 dark:text-orange-300',
    }

    return (
      <span
        className={`inline-flex items-center rounded-full px-3 py-0.5 text-sm font-medium ${statusColors[status] || statusColors.pending}`}
      >
        {status}
      </span>
    )
  }

  // Filter history results by selected structure tab
  const filteredHistory = useMemo(() => {
    if (results.length <= 1) return historyResults
    const selectedResult = results[selectedStructureIndex]
    if (!selectedResult) return historyResults
    return historyResults.filter(
      (h) => h.structure_key === selectedResult.structure_key,
    )
  }, [historyResults, results, selectedStructureIndex])

  const handleHistoryTabClick = () => {
    setActiveTab('history')
    if (!historyFetched) {
      setHistoryFetched(true)
      fetchHistoryResults()
    }
  }

  const renderPrompt = (promptUsed: string | undefined) => {
    if (!promptUsed) {
      return (
        <details className="rounded-lg border p-4">
          <summary className="cursor-pointer text-sm font-medium text-zinc-700 dark:text-zinc-300">
            {t('generation.resultModal.viewPrompt')}
          </summary>
          <p className="mt-2 text-sm text-zinc-400 italic dark:text-zinc-500">
            {t('generation.resultModal.noPromptStored')}
          </p>
        </details>
      )
    }
    let parsed: { system_prompt?: string; instruction_prompt?: string } | null =
      null
    try {
      parsed = JSON.parse(promptUsed)
    } catch {
      // Not JSON, show as plain text
    }
    return (
      <details className="rounded-lg border p-4">
        <summary className="cursor-pointer text-sm font-medium text-zinc-700 dark:text-zinc-300">
          {t('generation.resultModal.viewPrompt')}
        </summary>
        {parsed ? (
          <div className="mt-2 space-y-3">
            {parsed.system_prompt && (
              <div>
                <p className="text-xs font-medium text-zinc-500 uppercase dark:text-zinc-400">
                  {t('generation.resultModal.systemPrompt')}
                </p>
                <pre className="mt-1 text-sm whitespace-pre-wrap text-zinc-600 dark:text-zinc-400">
                  {parsed.system_prompt}
                </pre>
              </div>
            )}
            {parsed.instruction_prompt && (
              <div>
                <p className="text-xs font-medium text-zinc-500 uppercase dark:text-zinc-400">
                  {t('generation.resultModal.instructionPrompt')}
                </p>
                <pre className="mt-1 text-sm whitespace-pre-wrap text-zinc-600 dark:text-zinc-400">
                  {parsed.instruction_prompt}
                </pre>
              </div>
            )}
          </div>
        ) : (
          <pre className="mt-2 text-sm whitespace-pre-wrap text-zinc-600 dark:text-zinc-400">
            {promptUsed}
          </pre>
        )}
      </details>
    )
  }

  const renderResultContent = (result: GenerationResult) => (
    <>
      {result.status === 'completed' && result.result ? (
        <div>
          <h4 className="mb-2 text-sm font-medium text-zinc-700 dark:text-zinc-300">
            {t('generation.resultModal.generatedText')}
          </h4>
          <div className="max-h-96 overflow-y-auto rounded-lg bg-zinc-50 p-4 dark:bg-zinc-800/50">
            <pre className="font-mono text-sm whitespace-pre-wrap text-zinc-800 dark:text-zinc-200">
              {viewMode === 'raw'
                ? JSON.stringify(result.result, null, 2)
                : formatResult(result.result)}
            </pre>
          </div>
        </div>
      ) : result.status === 'failed' && result.error_message ? (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 dark:border-red-800 dark:bg-red-900/20">
          <p className="text-sm font-medium text-red-800 dark:text-red-300">
            {t('generation.resultModal.error')}
          </p>
          <p className="mt-1 text-sm text-red-600 dark:text-red-400">
            {result.error_message}
          </p>
        </div>
      ) : result.status === 'running' ? (
        <div className="rounded-lg bg-amber-50 p-4 dark:bg-amber-900/20">
          <p className="text-sm text-amber-800 dark:text-amber-300">
            {t('generation.resultModal.runningMessage')}
          </p>
        </div>
      ) : result.status === 'pending' ? (
        <div className="rounded-lg bg-zinc-50 p-4 dark:bg-zinc-800/50">
          <p className="text-sm text-zinc-600 dark:text-zinc-400">
            {t('generation.resultModal.pendingMessage')}
          </p>
        </div>
      ) : result.status === 'cancelled' && result.error_message ? (
        <div className="rounded-lg border border-orange-200 bg-orange-50 p-4 dark:border-orange-800 dark:bg-orange-900/20">
          <p className="text-sm text-orange-800 dark:text-orange-300">
            {result.error_message}
          </p>
        </div>
      ) : (
        <div className="rounded-lg bg-zinc-50 p-4 dark:bg-zinc-800/50">
          <p className="text-sm text-zinc-600 dark:text-zinc-400">
            {t('generation.resultModal.noResultMessage')}
          </p>
        </div>
      )}
    </>
  )

  return (
    <Transition.Root show={isOpen} as={Fragment}>
      <Dialog as="div" className="relative z-50" onClose={onClose}>
        <Transition.Child
          as={Fragment}
          enter="ease-out duration-300"
          enterFrom="opacity-0"
          enterTo="opacity-100"
          leave="ease-in duration-200"
          leaveFrom="opacity-100"
          leaveTo="opacity-0"
        >
          <div className="fixed inset-0 bg-zinc-500/75 transition-opacity dark:bg-zinc-950/80" />
        </Transition.Child>

        <div className="fixed inset-0 z-10 overflow-y-auto">
          <div className="flex min-h-full items-end justify-center p-4 text-center sm:items-center sm:p-0">
            <Transition.Child
              as={Fragment}
              enter="ease-out duration-300"
              enterFrom="opacity-0 translate-y-4 sm:translate-y-0 sm:scale-95"
              enterTo="opacity-100 translate-y-0 sm:scale-100"
              leave="ease-in duration-200"
              leaveFrom="opacity-100 translate-y-0 sm:scale-100"
              leaveTo="opacity-0 translate-y-4 sm:translate-y-0 sm:scale-95"
            >
              <Dialog.Panel className="relative transform overflow-hidden rounded-lg bg-white text-left shadow-xl transition-all sm:my-8 sm:w-full sm:max-w-3xl dark:bg-zinc-900">
                <div className="bg-white px-4 pt-5 pb-4 sm:p-6 sm:pb-4 dark:bg-zinc-900">
                  <div className="mb-4 flex items-center justify-between">
                    <div>
                      <Dialog.Title
                        as="h3"
                        className="text-lg leading-6 font-semibold text-zinc-900 dark:text-white"
                      >
                        {t('generation.resultModal.title')}
                      </Dialog.Title>
                      <div className="mt-1 space-y-1">
                        <p className="text-sm text-zinc-500 dark:text-zinc-400">
                          <span className="font-medium">
                            {t('generation.resultModal.model')}
                          </span>{' '}
                          <span>{modelId}</span>
                        </p>
                        <p className="text-sm text-zinc-500 dark:text-zinc-400">
                          <span className="font-medium">
                            {t('generation.resultModal.task')}
                          </span>{' '}
                          {taskId.substring(0, 8)}...
                        </p>
                      </div>
                    </div>
                    <button
                      type="button"
                      className="rounded-md bg-white text-zinc-400 hover:text-zinc-500 focus:ring-2 focus:ring-emerald-500 focus:ring-offset-2 focus:outline-none dark:bg-zinc-900 dark:text-zinc-500 dark:hover:text-zinc-300"
                      onClick={onClose}
                    >
                      <span className="sr-only">
                        {t('shared.alertDialog.close')}
                      </span>
                      <XMarkIcon className="h-6 w-6" aria-hidden="true" />
                    </button>
                  </div>

                  {loading ? (
                    <div className="flex h-64 flex-col items-center justify-center space-y-4">
                      <div className="h-12 w-12 animate-spin rounded-full border-b-2 border-emerald-500"></div>
                      <p className="text-sm text-zinc-600 dark:text-zinc-400">
                        {t('generation.resultModal.loading')}
                      </p>
                    </div>
                  ) : results.length > 0 ? (
                    <>
                      {/* Current / History toggle */}
                      <div className="mb-4 inline-flex items-center gap-0.5 rounded-full bg-zinc-100 p-0.5 dark:bg-zinc-800">
                        <button
                          onClick={() => setActiveTab('current')}
                          className={`rounded-full px-3 py-1 text-sm font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 ${
                            activeTab === 'current'
                              ? 'bg-white text-zinc-900 shadow-sm dark:bg-zinc-700 dark:text-white'
                              : 'text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white'
                          }`}
                        >
                          {t('generation.resultModal.current')}
                        </button>
                        <button
                          onClick={handleHistoryTabClick}
                          className={`rounded-full px-3 py-1 text-sm font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 ${
                            activeTab === 'history'
                              ? 'bg-white text-zinc-900 shadow-sm dark:bg-zinc-700 dark:text-white'
                              : 'text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white'
                          }`}
                        >
                          {t('generation.resultModal.history')}
                        </button>
                      </div>

                      {/* Structure Tabs (if multiple structures) */}
                      {results.length > 1 && (
                        <div className="mb-4">
                          <nav className="inline-flex max-w-full items-center gap-0.5 overflow-x-auto rounded-full bg-zinc-100 p-0.5 dark:bg-zinc-800">
                            {results.map((result, index) => (
                              <button
                                key={index}
                                onClick={() => setSelectedStructureIndex(index)}
                                className={`rounded-full px-3 py-1 text-sm font-medium whitespace-nowrap transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 ${
                                  selectedStructureIndex === index
                                    ? 'bg-white text-zinc-900 shadow-sm dark:bg-zinc-700 dark:text-white'
                                    : 'text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white'
                                }`}
                              >
                                {result.structure_key ||
                                  t('generation.resultModal.default')}
                              </button>
                            ))}
                          </nav>
                        </div>
                      )}

                      {activeTab === 'current' ? (
                        /* ===== Current view (existing behavior) ===== */
                        (() => {
                          const result = results[selectedStructureIndex]
                          return (
                            <div className="space-y-4">
                              {/* Status and metadata */}
                              <div className="space-y-2 rounded-lg bg-zinc-50 p-4 dark:bg-zinc-800/50">
                                <div className="flex items-center justify-between">
                                  <span className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
                                    {t('generation.resultModal.status')}
                                  </span>
                                  {getStatusBadge(result.status)}
                                </div>
                                {result.generated_at && (
                                  <div className="flex items-center justify-between">
                                    <span className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
                                      {t('generation.resultModal.generatedAt')}
                                    </span>
                                    <span className="text-sm text-zinc-600 dark:text-zinc-400">
                                      {new Date(
                                        result.generated_at,
                                      ).toLocaleString(intlTag(locale))}
                                    </span>
                                  </div>
                                )}
                                {result.generation_time_seconds != null && (
                                  <div className="flex items-center justify-between">
                                    <span className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
                                      {t(
                                        'generation.resultModal.generationTime',
                                      )}
                                    </span>
                                    <span className="text-sm text-zinc-600 dark:text-zinc-400">
                                      {t('generation.resultModal.seconds', {
                                        value: formatDecimal(
                                          result.generation_time_seconds,
                                          locale,
                                          2,
                                        ),
                                      })}
                                    </span>
                                  </div>
                                )}
                              </div>

                              {/* View mode toggle */}
                              <div className="flex items-center justify-between">
                                <div className="inline-flex items-center gap-0.5 rounded-full bg-zinc-100 p-0.5 dark:bg-zinc-800">
                                  <button
                                    onClick={() => setViewMode('formatted')}
                                    className={`rounded-full px-3 py-1 text-sm font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 ${
                                      viewMode === 'formatted'
                                        ? 'bg-white text-zinc-900 shadow-sm dark:bg-zinc-700 dark:text-white'
                                        : 'text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white'
                                    }`}
                                  >
                                    {t('generation.resultModal.formatted')}
                                  </button>
                                  <button
                                    onClick={() => setViewMode('raw')}
                                    className={`rounded-full px-3 py-1 text-sm font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 ${
                                      viewMode === 'raw'
                                        ? 'bg-white text-zinc-900 shadow-sm dark:bg-zinc-700 dark:text-white'
                                        : 'text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white'
                                    }`}
                                  >
                                    {t('generation.resultModal.rawJson')}
                                  </button>
                                </div>
                                <Button variant="outline" onClick={handleCopy}>
                                  {copied ? (
                                    <>
                                      <CheckIcon className="h-4 w-4" />
                                      {t('generation.resultModal.copied')}
                                    </>
                                  ) : (
                                    <>
                                      <ClipboardDocumentIcon className="h-4 w-4" />
                                      {t('generation.resultModal.copy')}
                                    </>
                                  )}
                                </Button>
                              </div>

                              {/* Result content */}
                              {renderResultContent(result)}

                              {/* Prompt used */}
                              {renderPrompt(result.prompt_used)}

                              {/* Parameters (if available) */}
                              {result.parameters &&
                                Object.keys(result.parameters).length > 0 && (
                                  <details className="rounded-lg border p-4">
                                    <summary className="cursor-pointer text-sm font-medium text-zinc-700 dark:text-zinc-300">
                                      {t(
                                        'generation.resultModal.viewParameters',
                                      )}
                                    </summary>
                                    <pre className="mt-2 text-sm whitespace-pre-wrap text-zinc-600 dark:text-zinc-400">
                                      {JSON.stringify(
                                        result.parameters,
                                        null,
                                        2,
                                      )}
                                    </pre>
                                  </details>
                                )}
                            </div>
                          )
                        })()
                      ) : (
                        /* ===== History view (Issue #1372) ===== */
                        <div className="space-y-3">
                          {historyLoading ? (
                            <div className="flex h-32 items-center justify-center">
                              <div className="h-8 w-8 animate-spin rounded-full border-b-2 border-emerald-500" />
                            </div>
                          ) : filteredHistory.length > 0 ? (
                            <>
                              {/* View mode toggle (shared with current view) */}
                              <div className="flex items-center justify-between">
                                <div className="inline-flex items-center gap-0.5 rounded-full bg-zinc-100 p-0.5 dark:bg-zinc-800">
                                  <button
                                    onClick={() => setViewMode('formatted')}
                                    className={`rounded-full px-3 py-1 text-sm font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 ${
                                      viewMode === 'formatted'
                                        ? 'bg-white text-zinc-900 shadow-sm dark:bg-zinc-700 dark:text-white'
                                        : 'text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white'
                                    }`}
                                  >
                                    {t('generation.resultModal.formatted')}
                                  </button>
                                  <button
                                    onClick={() => setViewMode('raw')}
                                    className={`rounded-full px-3 py-1 text-sm font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 ${
                                      viewMode === 'raw'
                                        ? 'bg-white text-zinc-900 shadow-sm dark:bg-zinc-700 dark:text-white'
                                        : 'text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white'
                                    }`}
                                  >
                                    {t('generation.resultModal.rawJson')}
                                  </button>
                                </div>
                              </div>

                              {/* History entries */}
                              <div className="space-y-2">
                                {filteredHistory.map((entry, index) => (
                                  <Disclosure key={entry.generation_id}>
                                    {({ open }) => (
                                      <>
                                        <Disclosure.Button className="flex w-full items-center justify-between rounded-lg bg-zinc-50 px-4 py-3 text-sm hover:bg-zinc-100 dark:bg-zinc-800/50 dark:hover:bg-zinc-800">
                                          <div className="flex items-center gap-3">
                                            {getStatusBadge(entry.status)}
                                            <span className="text-zinc-600 dark:text-zinc-400">
                                              {entry.generated_at
                                                ? new Date(
                                                    entry.generated_at,
                                                  ).toLocaleString(
                                                    intlTag(locale),
                                                  )
                                                : '\u2014'}
                                            </span>
                                            {entry.generation_time_seconds !=
                                              null && (
                                              <span className="text-zinc-400 dark:text-zinc-500">
                                                {t(
                                                  'generation.resultModal.seconds',
                                                  {
                                                    value: formatDecimal(
                                                      entry.generation_time_seconds,
                                                      locale,
                                                      2,
                                                    ),
                                                  },
                                                )}
                                              </span>
                                            )}
                                            {entry.created_by_name && (
                                              <span className="text-zinc-400 dark:text-zinc-500">
                                                {t(
                                                  'generation.resultModal.by',
                                                  {
                                                    user: entry.created_by_name,
                                                  },
                                                )}
                                              </span>
                                            )}
                                            {index === 0 && (
                                              <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400">
                                                {t(
                                                  'generation.resultModal.currentLabel',
                                                )}
                                              </span>
                                            )}
                                          </div>
                                          <ChevronDownIcon
                                            className={`h-4 w-4 text-zinc-500 transition-transform ${open ? 'rotate-180' : ''}`}
                                          />
                                        </Disclosure.Button>
                                        <Disclosure.Panel className="px-4 pt-2 pb-3">
                                          <div className="space-y-3">
                                            {renderResultContent(entry)}

                                            {/* Prompt used */}
                                            {renderPrompt(entry.prompt_used)}

                                            {/* Parameters */}
                                            {entry.parameters &&
                                              Object.keys(entry.parameters)
                                                .length > 0 && (
                                                <details className="rounded-lg border p-3">
                                                  <summary className="cursor-pointer text-sm font-medium text-zinc-700 dark:text-zinc-300">
                                                    {t(
                                                      'generation.resultModal.viewParameters',
                                                    )}
                                                  </summary>
                                                  <pre className="mt-2 max-h-48 overflow-y-auto text-sm whitespace-pre-wrap text-zinc-600 dark:text-zinc-400">
                                                    {JSON.stringify(
                                                      entry.parameters,
                                                      null,
                                                      2,
                                                    )}
                                                  </pre>
                                                </details>
                                              )}
                                          </div>
                                        </Disclosure.Panel>
                                      </>
                                    )}
                                  </Disclosure>
                                ))}
                              </div>
                            </>
                          ) : (
                            <p className="py-8 text-center text-sm text-zinc-500 dark:text-zinc-400">
                              {t('generation.resultModal.noHistory')}
                            </p>
                          )}
                        </div>
                      )}
                    </>
                  ) : (
                    <div className="py-12 text-center">
                      <p className="text-zinc-500 dark:text-zinc-400">
                        {t('generation.resultModal.noResultsFound')}
                      </p>
                      {onRegenerate && (
                        <Button
                          variant="filled"
                          className="mt-4"
                          onClick={() => {
                            onRegenerate(
                              taskId,
                              modelId,
                              availableStructureKeys.length > 1
                                ? [...selectedStructureKeys]
                                : undefined,
                            )
                            onClose()
                          }}
                          disabled={
                            availableStructureKeys.length > 1 &&
                            selectedStructureKeys.size === 0
                          }
                        >
                          <PlayIcon className="h-4 w-4" />
                          {t('generation.resultModal.generate')}
                        </Button>
                      )}
                    </div>
                  )}
                </div>

                <div className="bg-zinc-50 px-4 py-3 sm:px-6 dark:bg-zinc-800/50">
                  {/* Structure selection (when multiple structures available) */}
                  {onRegenerate && availableStructureKeys.length > 1 && (
                    <div className="mb-3">
                      <button
                        onClick={() =>
                          setShowStructureSelection(!showStructureSelection)
                        }
                        className="mb-2 text-xs text-zinc-500 underline hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200"
                      >
                        {t('generation.resultModal.selectStructures')}
                      </button>
                      {showStructureSelection && (
                        <div className="flex flex-wrap gap-2">
                          {availableStructureKeys.map((key) => (
                            <label
                              key={key}
                              className="flex items-center gap-1.5 rounded-md bg-white px-2 py-1 text-xs shadow-sm dark:bg-zinc-900"
                            >
                              <input
                                type="checkbox"
                                checked={selectedStructureKeys.has(key)}
                                onChange={(e) => {
                                  setSelectedStructureKeys((prev) => {
                                    const next = new Set(prev)
                                    if (e.target.checked) {
                                      next.add(key)
                                    } else {
                                      next.delete(key)
                                    }
                                    return next
                                  })
                                }}
                                className="h-3.5 w-3.5 rounded border-zinc-300 text-emerald-600 focus:ring-emerald-500 dark:border-zinc-600 dark:text-emerald-400"
                              />
                              <span className="text-zinc-700 dark:text-zinc-300">
                                {key}
                              </span>
                            </label>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                  <div className="flex flex-row-reverse gap-2">
                    {onRegenerate && results.length > 0 && (
                      <Button
                        variant="filled"
                        onClick={() => {
                          onRegenerate(
                            taskId,
                            modelId,
                            availableStructureKeys.length > 1
                              ? [...selectedStructureKeys]
                              : undefined,
                          )
                          onClose()
                        }}
                        disabled={
                          availableStructureKeys.length > 1 &&
                          selectedStructureKeys.size === 0
                        }
                      >
                        <ArrowPathIcon className="h-4 w-4" />
                        {t('generation.resultModal.regenerate')}
                      </Button>
                    )}
                    <Button variant="outline" onClick={onClose}>
                      {t('generation.resultModal.close')}
                    </Button>
                  </div>
                </div>
              </Dialog.Panel>
            </Transition.Child>
          </div>
        </div>
      </Dialog>
    </Transition.Root>
  )
}

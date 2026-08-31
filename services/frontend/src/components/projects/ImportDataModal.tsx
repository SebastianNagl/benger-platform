/**
 * ImportDataModal - Modal for importing data into a project
 *
 * Supports multiple import methods:
 * - File upload (JSON, CSV, TSV, TXT)
 * - Paste data directly
 * - Cloud storage (org S3 storage connections, immediate-mode panel)
 *
 * Parsing/format detection and the tab DOM are shared with the
 * project-creation wizard (lib/import/parseImportData + ImportSourceTabs).
 */

'use client'

import { logger } from '@/lib/utils/logger'
import { CloudImportPanel } from '@/components/projects/import/CloudImportPanel'
import { ImportSourceTabs } from '@/components/projects/import/ImportSourceTabs'
import { Dialog } from '@/components/shared/Dialog'
import { useToast } from '@/components/shared/Toast'
import { ImportPreviewWithMapping } from '@/components/tasks/ImportPreviewWithMapping'
import { Button } from '@/components/ui/button'
import { useI18n } from '@/contexts/I18nContext'
import { useProgress } from '@/contexts/ProgressContext'
import { projectsAPI } from '@/lib/api/projects'
import {
  buildImportFile,
  detectFormat,
  parseImportData,
} from '@/lib/import/parseImportData'
import { useProjectStore } from '@/stores/projectStore'
import { ExclamationTriangleIcon } from '@heroicons/react/24/outline'
import React, { useCallback, useEffect, useState } from 'react'

interface ImportDataModalProps {
  isOpen: boolean
  onClose: () => void
  projectId: string
  /** Project kind steering the import-tab order (exam leads structured). */
  projectKind?: string
  onImportComplete?: () => void
}

export function ImportDataModal({
  isOpen,
  onClose,
  projectId,
  projectKind,
  onImportComplete,
}: ImportDataModalProps) {
  const { t } = useI18n()
  const { addToast } = useToast()
  const { startProgress, updateProgress, completeProgress } = useProgress()
  const { fetchProject } = useProjectStore()
  const [loading, setLoading] = useState(false)
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [pastedData, setPastedData] = useState('')
  const [showFieldMapping, setShowFieldMapping] = useState(false)
  const [templateFields, setTemplateFields] = useState<string[]>([])
  const [parsedData, setParsedData] = useState<any[]>([])
  const [validationErrors, setValidationErrors] = useState<string[]>([])

  // The two sources are mutually exclusive: picking one clears the other.
  const handleFileChange = useCallback((file: File | null) => {
    setSelectedFile(file)
    if (file) {
      setPastedData('')
    }
  }, [])

  const handlePastedDataChange = useCallback((data: string) => {
    setPastedData(data)
    if (data) {
      setSelectedFile(null)
    }
  }, [])

  const fetchProjectTemplate = useCallback(async () => {
    try {
      const project = await fetchProject(projectId)
      if ((project as any)?.label_config) {
        // Extract required fields from label config
        const fieldRegex = /\$([a-zA-Z_][a-zA-Z0-9_]*)/g
        const matches = (project as any).label_config.matchAll(fieldRegex)
        const fields = Array.from(matches, (m: any) => m[1])
        const uniqueFields = [...new Set(fields)]
        setTemplateFields(uniqueFields)
      }
    } catch (error) {
      console.error('Failed to fetch project template:', error)
    }
  }, [projectId, fetchProject])

  // Fetch project template fields when modal opens
  useEffect(() => {
    if (isOpen && projectId) {
      fetchProjectTemplate()
    }
  }, [isOpen, projectId, fetchProjectTemplate])

  const validateDataAgainstTemplate = (data: any[]) => {
    if (templateFields.length === 0) return { valid: true, errors: [] }

    const errors: string[] = []

    // Check each data item for missing fields (Label Studio style)
    const allDataFields = new Set<string>()
    data.forEach((item) => {
      // Check fields in the data wrapper (Label Studio format)
      const dataObj = item.data || item
      Object.keys(dataObj).forEach((field) => allDataFields.add(field))
    })

    const missingFields = templateFields.filter(
      (field) => !allDataFields.has(field)
    )

    if (missingFields.length > 0) {
      // Use Label Studio's exact error format
      errors.push(
        `Validation error - These fields are not present in the data: ${missingFields.join(', ')}`
      )
    }

    return { valid: errors.length === 0, errors }
  }

  const handleImport = async (mappedData?: any[]) => {
    const progressId = `import-${Date.now()}`

    logger.debug('[ImportDataModal] Starting import process', {
      hasSelectedFile: !!selectedFile,
      pastedDataLength: pastedData.length,
      hasMappedData: !!mappedData,
    })

    try {
      setLoading(true)
      let data: any[] = mappedData || []
      // Auxiliary arrays from the bulk-export envelope (eval runs, human-eval,
      // korrektur) — forwarded alongside the task rows when present.
      let extras: Record<string, unknown> = {}

      startProgress(progressId, 'Importing data...', {
        sublabel: 'Processing file...',
        indeterminate: false,
      })

      if (!mappedData) {
        // Determine which data source to use based on what's available
        if (selectedFile) {
          updateProgress(progressId, 10, `Reading ${selectedFile.name}...`)

          // Read file content
          const content = await new Promise<string>((resolve, reject) => {
            const reader = new FileReader()
            reader.onload = (e) => resolve(e.target?.result as string)
            reader.onerror = reject
            reader.readAsText(selectedFile)
          })

          updateProgress(progressId, 30, 'Parsing data...')

          const parsed = parseImportData(
            content,
            detectFormat(content, selectedFile.name)
          )
          data = parsed.rows
          extras = parsed.extras
        } else if (pastedData) {
          updateProgress(progressId, 10, 'Processing pasted data...')

          const trimmed = pastedData.trim()
          updateProgress(progressId, 30, 'Parsing data...')
          const parsed = parseImportData(trimmed, detectFormat(trimmed))
          data = parsed.rows
          extras = parsed.extras
        }
      }

      if (data.length === 0) {
        throw new Error(t('projects.import.noData'))
      }

      // Show validation warnings but don't block import (Label Studio style)
      updateProgress(progressId, 50, 'Validating data...')
      const validation = validateDataAgainstTemplate(data)

      if (!validation.valid && templateFields.length > 0) {
        // Show field mapping as an option, not a blocker
        addToast(
          `Some fields don't match your template. You can import as-is or use field mapping.`,
          'error'
        )
        setValidationErrors(validation.errors)
        setParsedData(data)
        setShowFieldMapping(true)
        completeProgress(progressId, 'error')
        return
      }

      updateProgress(progressId, 60, `Importing ${data.length} tasks...`)

      logger.debug('[ImportDataModal] Sending data to API', {
        projectId,
        dataLength: data.length,
        sampleData: data[0],
      })

      // Async job flow: serialize the assembled nested envelope to a JSON file,
      // upload it straight to object storage via a presigned URL, then let a
      // worker stream-import it. This keeps the bulk payload off the API request
      // path (the sync endpoint OOM-killed the pod on large imports). The
      // client-side parse/validation/field-mapping above is unchanged.
      const file = buildImportFile(data, extras)
      const job = await projectsAPI.runNestedImportJob(projectId, file, {
        onStatus: (status) => {
          if (status.status === 'running' || status.status === 'pending') {
            updateProgress(progressId, 80, `Importing ${data.length} tasks...`)
          }
        },
      })
      const result = job.result || {}

      logger.debug('[ImportDataModal] Import successful', result)

      updateProgress(progressId, 100, 'Import complete!')
      completeProgress(progressId, 'success')

      // Show toast immediately
      addToast(t('projects.data.importSuccess'), 'success')

      // Reset state
      setSelectedFile(null)
      setPastedData('')
      setParsedData([])
      setShowFieldMapping(false)
      setValidationErrors([])

      // Delay closing to ensure toast is displayed
      setTimeout(() => {
        onImportComplete?.()
        onClose()
      }, 100)
    } catch (error: any) {
      completeProgress(progressId, 'error')

      // Provide more detailed error message
      let errorMessage = t('projects.import.failed')

      if (error.message?.includes('Invalid JSON')) {
        errorMessage =
          'Invalid JSON format. Please check your data and try again.'
      } else if (error.message?.includes('Failed to parse')) {
        errorMessage = error.message
      } else if (error.response?.status === 401) {
        errorMessage = 'Authentication failed. Please login again.'
      } else if (error.response?.status === 403) {
        errorMessage =
          'You do not have permission to import data to this project.'
      } else if (error.response?.data?.detail) {
        errorMessage = error.response.data.detail
      } else if (error.message) {
        errorMessage = error.message
      }

      addToast(t('projects.data.importFailed'), 'error')
    } finally {
      setLoading(false)
    }
  }

  // Simplified canImport check - enable if we have any data to import
  const canImport =
    !!selectedFile || (pastedData && pastedData.trim().length > 0)

  if (showFieldMapping && parsedData.length > 0) {
    return (
      <Dialog
        isOpen={isOpen}
        onClose={() => {
          setShowFieldMapping(false)
          setParsedData([])
          setValidationErrors([])
          onClose()
        }}
        title={t('projects.data.import')}
        className="max-w-4xl"
      >
        <div className="space-y-4">
          {validationErrors.length > 0 && (
            <div className="rounded-lg border border-red-200 bg-red-50 p-4 dark:border-red-800 dark:bg-red-900/20">
              <div className="flex items-start space-x-2">
                <ExclamationTriangleIcon className="mt-0.5 h-5 w-5 flex-shrink-0 text-red-600 dark:text-red-400" />
                <div className="flex-1">
                  <h4 className="text-sm font-medium text-red-900 dark:text-red-100">
                    {t('tasks.importModal.validationError')}
                  </h4>
                  <p className="mt-1 text-sm text-red-800 dark:text-red-200">
                    {t('tasks.importModal.validationErrorDescription')}
                  </p>
                  {validationErrors.map((error, index) => (
                    <p
                      key={index}
                      className="mt-2 rounded bg-red-100 p-2 font-mono text-sm text-red-700 dark:bg-red-900/30 dark:text-red-300"
                    >
                      {error}
                    </p>
                  ))}
                  <div className="mt-3 flex gap-2">
                    <Button
                      variant="outline"
                      onClick={() => handleImport(parsedData)}
                      className="text-xs"
                    >
                      {t('tasks.importModal.importAnyway')}
                    </Button>
                    <span className="self-center text-xs text-red-600 dark:text-red-400">
                      {t('tasks.importModal.orUseFieldMapping')}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          )}

          <ImportPreviewWithMapping
            file={selectedFile || undefined}
            templateFields={templateFields}
            onImport={handleImport}
            onCancel={() => {
              setShowFieldMapping(false)
              setParsedData([])
              setValidationErrors([])
            }}
          />
        </div>
      </Dialog>
    )
  }

  return (
    <Dialog
      isOpen={isOpen}
      onClose={onClose}
      title={t('projects.data.import')}
      className="max-w-2xl"
    >
      <div className="space-y-4">
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          {t('tasks.importModal.description')}
        </p>

        {templateFields.length > 0 && (
          <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 dark:border-amber-800 dark:bg-amber-900/20">
            <div className="flex items-start space-x-2">
              <ExclamationTriangleIcon className="mt-0.5 h-5 w-5 flex-shrink-0 text-amber-600 dark:text-amber-400" />
              <div className="flex-1">
                <h4 className="text-sm font-medium text-amber-900 dark:text-amber-100">
                  {t('tasks.importModal.fieldRequirements')}
                </h4>
                <p className="mt-1 text-sm text-amber-800 dark:text-amber-200">
                  {t('tasks.importModal.fieldRequirementsDescription')}
                </p>
                <div className="mt-2 flex flex-wrap gap-2">
                  {templateFields.map((field) => (
                    <code
                      key={field}
                      className="inline-flex items-center rounded bg-amber-100 px-2 py-1 font-mono text-xs text-amber-800 dark:bg-amber-800 dark:text-amber-200"
                    >
                      ${field}
                    </code>
                  ))}
                </div>
                <p className="mt-2 text-xs text-amber-700 dark:text-amber-300">
                  {t('tasks.importModal.missingFieldsWarning')}
                </p>
              </div>
            </div>
          </div>
        )}

        <ImportSourceTabs
          selectedFile={selectedFile}
          pastedData={pastedData}
          onFileChange={handleFileChange}
          onPastedDataChange={handlePastedDataChange}
          projectKind={projectKind}
          testIdPrefix="import-modal"
          cloudPanel={
            <CloudImportPanel
              mode="immediate"
              projectId={projectId}
              onImportComplete={onImportComplete}
            />
          }
        />

        <div className="flex justify-end space-x-3 border-t border-zinc-200 pt-4 dark:border-zinc-800">
          <Button variant="outline" onClick={onClose} disabled={loading}>
            {t('common.cancel')}
          </Button>
          <Button
            onClick={(e) => {
              e.preventDefault()
              e.stopPropagation()
              if (!loading && canImport) {
                handleImport()
              }
            }}
            disabled={!canImport || loading}
            loading={loading}
            type="button"
          >
            {t('projects.data.import')}
          </Button>
        </div>
      </div>
    </Dialog>
  )
}

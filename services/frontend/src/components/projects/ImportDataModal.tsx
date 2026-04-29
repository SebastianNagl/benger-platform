/**
 * ImportDataModal - Modal for importing data into a project
 *
 * Supports multiple import methods:
 * - File upload (JSON, CSV, TSV, TXT)
 * - Paste data directly
 * - Cloud storage (future)
 */

'use client'

import { logger } from '@/lib/utils/logger'
import { Card } from '@/components/shared/Card'
import { Dialog } from '@/components/shared/Dialog'
import { Label } from '@/components/shared/Label'
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '@/components/shared/Tabs'
import { Textarea } from '@/components/shared/Textarea'
import { useToast } from '@/components/shared/Toast'
import { ImportPreviewWithMapping } from '@/components/tasks/ImportPreviewWithMapping'
import { Button } from '@/components/ui/button'
import { useI18n } from '@/contexts/I18nContext'
import { useProgress } from '@/contexts/ProgressContext'
import { projectsAPI } from '@/lib/api/projects'
import { useProjectStore } from '@/stores/projectStore'
import {
  CheckIcon,
  CloudArrowUpIcon,
  ExclamationTriangleIcon,
} from '@heroicons/react/24/outline'
import React, { useCallback, useEffect, useState } from 'react'

interface ImportDataModalProps {
  isOpen: boolean
  onClose: () => void
  projectId: string
  onImportComplete?: () => void
}

export function ImportDataModal({
  isOpen,
  onClose,
  projectId,
  onImportComplete,
}: ImportDataModalProps) {
  const { t } = useI18n()
  const { addToast } = useToast()
  const { startProgress, updateProgress, completeProgress } = useProgress()
  const { fetchProject } = useProjectStore()
  const [loading, setLoading] = useState(false)
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [pastedData, setPastedData] = useState('')
  const [activeTab, setActiveTab] = useState('upload')
  const [showFieldMapping, setShowFieldMapping] = useState(false)
  const [templateFields, setTemplateFields] = useState<string[]>([])
  const [parsedData, setParsedData] = useState<any[]>([])
  const [validationErrors, setValidationErrors] = useState<string[]>([])

  const handleFileSelect = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0]
      if (file) {
        setSelectedFile(file)
        // Clear pasted data when selecting a file
        if (pastedData) {
          setPastedData('')
        }
      }
    },
    [pastedData]
  )

  const handleDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault()
      const file = e.dataTransfer.files?.[0]
      if (file) {
        setSelectedFile(file)
        // Clear pasted data when dropping a file
        if (pastedData) {
          setPastedData('')
        }
      }
    },
    [pastedData]
  )

  const handleDragOver = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault()
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

  const parseData = async (content: string, format: string): Promise<any[]> => {
    try {
      if (format === 'json') {
        let parsed
        try {
          parsed = JSON.parse(content)
        } catch (jsonError: any) {
          throw new Error(`Invalid JSON format: ${jsonError.message}`)
        }

        // Handle both array and single object
        const dataArray = Array.isArray(parsed) ? parsed : [parsed]

        // Label Studio alignment: wrap data if not already wrapped
        return dataArray.map((item) => {
          // If already has 'data' field, use as-is (already in Label Studio format)
          if (item.data && typeof item.data === 'object') {
            return item
          }
          // Otherwise, wrap in 'data' field as Label Studio does
          return { data: item }
        })
      } else if (format === 'csv' || format === 'tsv') {
        const delimiter = format === 'csv' ? ',' : '\t'
        const lines = content.trim().split('\n')
        if (lines.length === 0) return []

        // Parse header
        const headers = lines[0]
          .split(delimiter)
          .map((h) => h.trim().replace(/^["']|["']$/g, ''))

        // Parse data rows
        return lines.slice(1).map((line, lineIndex) => {
          const values = line
            .split(delimiter)
            .map((v) => v.trim().replace(/^["']|["']$/g, ''))
          const obj: any = {}
          headers.forEach((header, index) => {
            obj[header] = values[index] || ''
          })
          // Label Studio alignment: wrap in data field
          return { data: obj }
        })
      } else {
        // Plain text - each line becomes a task
        return content
          .trim()
          .split('\n')
          .filter((line) => line.trim())
          .map((line, index) => ({
            data: { text: line.trim() },
          }))
      }
    } catch (error: any) {
      // Re-throw with the original error message if it's already formatted
      if (error.message && error.message.includes('Invalid JSON')) {
        throw error
      }
      throw new Error(
        `Failed to parse ${format.toUpperCase()} data: ${error.message || error}`
      )
    }
  }

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

          // Determine format from file extension
          const format =
            selectedFile.name.split('.').pop()?.toLowerCase() || 'txt'
          data = await parseData(content, format)
        } else if (pastedData) {
          updateProgress(progressId, 10, 'Processing pasted data...')

          // Try to detect format from content
          const trimmed = pastedData.trim()
          let format = 'txt'

          if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
            format = 'json'
          } else if (trimmed.includes('\t')) {
            format = 'tsv'
          } else if (
            trimmed.includes(',') &&
            trimmed.split('\n')[0]?.includes(',')
          ) {
            format = 'csv'
          }

          updateProgress(progressId, 30, 'Parsing data...')
          data = await parseData(trimmed, format)
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

      // Import data to project
      const result = await projectsAPI.importData(projectId, { data })

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

        <Tabs defaultValue={activeTab} className="w-full">
          <TabsList className="grid w-full grid-cols-3">
            <TabsTrigger value="upload">{t('tasks.importModal.uploadFiles')}</TabsTrigger>
            <TabsTrigger value="paste">{t('tasks.importModal.pasteData')}</TabsTrigger>
            <TabsTrigger value="cloud">{t('tasks.importModal.cloudStorage')}</TabsTrigger>
          </TabsList>

          <TabsContent value="upload" className="mt-6">
            <div
              onDrop={handleDrop}
              onDragOver={handleDragOver}
              className="rounded-lg border-2 border-dashed border-zinc-300 p-8 text-center transition-colors hover:border-emerald-500 dark:border-zinc-700 dark:hover:border-emerald-500"
            >
              {selectedFile ? (
                <div className="space-y-3">
                  <CheckIcon className="mx-auto h-12 w-12 text-emerald-500" />
                  <p className="text-lg font-medium">{selectedFile.name}</p>
                  <p className="text-sm text-zinc-600 dark:text-zinc-400">
                    {(selectedFile.size / 1024).toFixed(1)} KB
                  </p>
                  <Button
                    variant="outline"
                    onClick={() => setSelectedFile(null)}
                  >
                    {t('common.remove')}
                  </Button>
                </div>
              ) : (
                <>
                  <CloudArrowUpIcon className="mx-auto mb-4 h-12 w-12 text-zinc-400 dark:text-zinc-500" />
                  <p className="mb-2 text-lg font-medium">
                    {t('tasks.importModal.dropFilesHere')}
                  </p>
                  <p className="mb-4 text-sm text-zinc-600 dark:text-zinc-400">
                    {t('tasks.importModal.supportedFormats')}
                  </p>
                  <input
                    type="file"
                    id="file-upload"
                    className="sr-only"
                    accept=".json,.csv,.tsv,.txt"
                    onChange={handleFileSelect}
                  />
                  <label
                    htmlFor="file-upload"
                    className="inline-flex cursor-pointer items-center justify-center rounded-md border border-zinc-300 bg-transparent px-4 py-2 text-sm font-medium transition-colors hover:bg-zinc-100 dark:border-zinc-600 dark:hover:bg-zinc-800"
                  >
                    {t('tasks.importModal.chooseFiles')}
                  </label>
                </>
              )}
            </div>
          </TabsContent>

          <TabsContent value="paste" className="mt-6">
            <div className="space-y-4">
              <Label>{t('tasks.importModal.pasteYourData')}</Label>
              <Textarea
                placeholder={t('tasks.importModal.pastePlaceholder')}
                value={pastedData}
                onChange={(e) => {
                  setPastedData(e.target.value)
                  // Clear file selection when pasting data
                  if (e.target.value && selectedFile) {
                    setSelectedFile(null)
                  }
                }}
                rows={10}
                className="font-mono text-sm"
              />
              <p className="text-xs text-zinc-500 dark:text-zinc-400">
                {t('tasks.importModal.csvTip')}
              </p>
            </div>
          </TabsContent>

          <TabsContent value="cloud" className="mt-6">
            <Card>
              <div className="p-8 text-center">
                <p className="text-zinc-600 dark:text-zinc-400">
                  {t('tasks.importModal.cloudComingSoon')}
                </p>
              </div>
            </Card>
          </TabsContent>
        </Tabs>

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

'use client'

import { Button } from '@/components/shared/Button'
import { Card } from '@/components/shared/Card'
import { Label } from '@/components/shared/Label'
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '@/components/shared/Tabs'
import { Textarea } from '@/components/shared/Textarea'
import { useToast } from '@/components/shared/Toast'
import { useI18n } from '@/contexts/I18nContext'
import { CloudArrowUpIcon } from '@heroicons/react/24/outline'
import React, { useCallback } from 'react'

interface StepDataImportProps {
  pastedData: string
  selectedFile: File | null
  dataColumns: string[]
  onPastedDataChange: (data: string) => void
  onFileChange: (file: File | null) => void
  onDataColumnsChange: (columns: string[]) => void
}

/** Extract column names from a data string (JSON keys or CSV/TSV headers) */
function extractColumns(content: string): string[] {
  const trimmed = content.trim()
  if (!trimmed) return []

  try {
    if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
      const parsed = JSON.parse(trimmed)
      const firstItem = Array.isArray(parsed)
        ? parsed[0]
        : parsed.qa_samples?.[0] || parsed.questions?.[0] || parsed
      if (firstItem && typeof firstItem === 'object') {
        return Object.keys(firstItem)
      }
    } else if (trimmed.includes('\t')) {
      const firstLine = trimmed.split('\n')[0]
      return firstLine
        .split('\t')
        .map((h) => h.trim().replace(/^["']|["']$/g, ''))
        .filter(Boolean)
    } else if (trimmed.includes(',') && trimmed.split('\n')[0]?.includes(',')) {
      const firstLine = trimmed.split('\n')[0]
      return firstLine
        .split(',')
        .map((h) => h.trim().replace(/^["']|["']$/g, ''))
        .filter(Boolean)
    }
  } catch {
    // ignore parse errors
  }
  return []
}

export function StepDataImport({
  pastedData,
  selectedFile,
  dataColumns,
  onPastedDataChange,
  onFileChange,
  onDataColumnsChange,
}: StepDataImportProps) {
  const { t } = useI18n()
  const { addToast } = useToast()

  // Extract columns when pasted data changes
  const handlePastedDataChange = useCallback(
    (data: string) => {
      onPastedDataChange(data)
      onDataColumnsChange(extractColumns(data))
    },
    [onPastedDataChange, onDataColumnsChange]
  )

  // Extract columns when file is selected
  const handleFileWithColumns = useCallback(
    (file: File | null) => {
      onFileChange(file)
      if (file) {
        const reader = new FileReader()
        reader.onload = (e) => {
          const content = e.target?.result as string
          if (content) onDataColumnsChange(extractColumns(content))
        }
        reader.readAsText(file.slice(0, 10000)) // read first 10KB for column detection
      } else {
        onDataColumnsChange([])
      }
    },
    [onFileChange, onDataColumnsChange]
  )

  const handleFileSelect = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0]
      if (file) {
        handleFileWithColumns(file)
      }
    },
    [onFileChange]
  )

  const handleDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault()
      const file = e.dataTransfer.files?.[0]
      if (file) {
        handleFileWithColumns(file)
      }
    },
    [handleFileWithColumns]
  )

  const handleDragOver = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault()
  }, [])

  return (
    <div className="space-y-6">
      <div>
        <h2 className="mb-2 text-2xl font-semibold text-zinc-900 dark:text-white">
          {t('projects.creation.wizard.step2.title')}
        </h2>
        <p className="text-zinc-600 dark:text-zinc-400">
          {t('projects.creation.wizard.step2.subtitle')}
        </p>
      </div>

      <Tabs defaultValue="upload" data-testid="project-create-data-tabs">
        <TabsList className="grid w-full grid-cols-3">
          <TabsTrigger value="upload" data-testid="project-create-upload-tab">
            {t('projects.creation.wizard.step2.tabs.upload')}
          </TabsTrigger>
          <TabsTrigger value="paste" data-testid="project-create-paste-tab">
            {t('projects.creation.wizard.step2.tabs.paste')}
          </TabsTrigger>
          <TabsTrigger value="cloud" data-testid="project-create-cloud-tab">
            {t('projects.creation.wizard.step2.tabs.cloud')}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="upload" className="mt-6">
          <div
            className="cursor-pointer rounded-lg border border-dashed border-zinc-300 transition-colors hover:border-emerald-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 dark:border-zinc-700"
            onDrop={handleDrop}
            onDragOver={handleDragOver}
            onClick={() =>
              !selectedFile && document.getElementById('file-upload')?.click()
            }
            onKeyDown={(e) => {
              if ((e.key === 'Enter' || e.key === ' ') && !selectedFile) {
                e.preventDefault()
                document.getElementById('file-upload')?.click()
              }
            }}
            tabIndex={0}
            role="button"
            aria-label={t('projects.creation.wizard.step2.upload.dropzone')}
          >
            <div className="p-12 text-center">
              <CloudArrowUpIcon className="mx-auto mb-4 h-12 w-12 text-zinc-400 dark:text-zinc-500" />
              <p className="mb-2 text-lg font-medium">
                {t('projects.creation.wizard.step2.upload.dropzone')}
              </p>
              <p className="mb-4 text-sm text-zinc-600 dark:text-zinc-400">
                {t('projects.creation.wizard.step2.upload.supportedFormats')}
              </p>
              {selectedFile ? (
                <div className="mb-4">
                  <p className="text-sm text-emerald-600 dark:text-emerald-400">
                    {t('projects.creation.wizard.step2.upload.selectedFile', {
                      filename: selectedFile.name,
                    })}
                  </p>
                  <Button
                    variant="outline"
                    onClick={(e) => {
                      e.stopPropagation()
                      handleFileWithColumns(null)
                    }}
                    className="mt-2"
                    data-testid="project-create-remove-file-button"
                  >
                    {t('projects.creation.wizard.step2.upload.removeFile')}
                  </Button>
                </div>
              ) : (
                <Button
                  variant="outline"
                  onClick={(e) => {
                    e.stopPropagation()
                    document.getElementById('file-upload')?.click()
                  }}
                  data-testid="project-create-choose-files-button"
                >
                  {t('projects.creation.wizard.step2.upload.chooseFiles')}
                </Button>
              )}
              <input
                id="file-upload"
                type="file"
                accept=".json,.csv,.tsv,.txt"
                className="hidden"
                onChange={handleFileSelect}
                data-testid="project-create-file-input"
              />
            </div>
          </div>
        </TabsContent>

        <TabsContent value="paste" className="mt-6">
          <div className="space-y-4">
            <Label>{t('projects.creation.wizard.step2.paste.label')}</Label>
            <Textarea
              placeholder={t(
                'projects.creation.wizard.step2.paste.placeholder'
              )}
              rows={10}
              className="font-mono text-sm"
              value={pastedData}
              onChange={(e) => handlePastedDataChange(e.target.value)}
              data-testid="project-create-paste-data-textarea"
            />
            <div className="flex items-center justify-between">
              <div
                className="text-sm text-zinc-600 dark:text-zinc-400"
                data-testid="project-create-paste-line-count"
                data-line-count={
                  pastedData.trim()
                    ? pastedData.trim().split('\n').length
                    : 0
                }
              >
                {pastedData.trim()
                  ? t('projects.creation.wizard.step2.paste.lines', {
                      count: pastedData.trim().split('\n').length,
                    })
                  : t('projects.creation.wizard.step2.paste.noData')}
              </div>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  onClick={() => handlePastedDataChange('')}
                  disabled={!pastedData.trim()}
                  data-testid="project-create-clear-data-button"
                >
                  {t('projects.creation.wizard.step2.paste.clear')}
                </Button>
                <Button
                  variant="outline"
                  disabled={!pastedData.trim()}
                  data-testid="project-create-validate-data-button"
                  onClick={() => {
                    try {
                      const trimmed = pastedData.trim()
                      let format = 'txt'
                      if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
                        format = 'json'
                      } else if (trimmed.includes('\t')) {
                        format = 'tsv'
                      } else if (trimmed.includes(',')) {
                        format = 'csv'
                      }
                      addToast(
                        t(
                          'projects.creation.wizard.step2.paste.formatDetected',
                          { format: format.toUpperCase() }
                        ),
                        'success'
                      )
                    } catch {
                      addToast(
                        t('projects.creation.wizard.step2.paste.invalidFormat'),
                        'error'
                      )
                    }
                  }}
                >
                  {t('projects.creation.wizard.step2.paste.validate')}
                </Button>
              </div>
            </div>
          </div>
        </TabsContent>

        <TabsContent value="cloud" className="mt-6">
          <Card>
            <div className="p-8 text-center">
              <p className="text-zinc-600 dark:text-zinc-400">
                {t('projects.creation.wizard.step2.cloud.comingSoon')}
              </p>
            </div>
          </Card>
        </TabsContent>
      </Tabs>

      {dataColumns.length > 0 && (
        <div className="rounded-lg border border-zinc-200 p-3 dark:border-zinc-700">
          <p className="mb-2 text-xs font-medium text-zinc-700 dark:text-zinc-300">
            {t('projects.creation.wizard.step2.detectedColumns')}
          </p>
          <div className="flex flex-wrap gap-1">
            {dataColumns.map((col) => (
              <span
                key={col}
                className="rounded bg-zinc-100 px-2 py-0.5 text-xs font-mono text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300"
              >
                {col}
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="rounded-lg bg-zinc-50 p-4 dark:bg-zinc-800/50">
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          <strong>{t('projects.wizard.note')}:</strong>{' '}
          {t('projects.creation.wizard.step2.note')}
        </p>
      </div>
    </div>
  )
}

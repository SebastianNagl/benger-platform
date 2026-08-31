'use client'

/**
 * ImportSourceTabs - shared data-source picker for project data imports.
 *
 * Presentational component owning the tab DOM shared by the project-creation
 * wizard (step 2) and the project-page ImportDataModal: a file-upload
 * dropzone, a paste textarea with text extraction / validate / clear, an
 * injected cloud-storage panel, and an optional injected structured-entry tab
 * (the extended edition's typed exam editor). Kind-aware ordering: exam
 * projects lead with the structured tab.
 */

import { Button } from '@/components/shared/Button'
import { ExtractTextButton } from '@/components/projects/ExtractTextButton'
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
import { detectFormat, extractColumns } from '@/lib/import/parseImportData'
import {
  CheckCircleIcon,
  CloudArrowUpIcon,
} from '@heroicons/react/24/outline'
import React, { ReactNode, useCallback } from 'react'

export type ImportTabId = 'upload' | 'paste' | 'cloud' | 'structured'

/**
 * Tab order + default for a given project kind. Exam projects lead with the
 * structured Klausur editor; everything else is upload-first with the
 * structured tab (when present) appended last.
 */
export function getImportTabConfig(
  kind: string | undefined,
  hasStructured: boolean
): { order: ImportTabId[]; defaultTab: ImportTabId } {
  if (hasStructured && kind === 'exam') {
    return {
      order: ['structured', 'upload', 'paste', 'cloud'],
      defaultTab: 'structured',
    }
  }
  const order: ImportTabId[] = ['upload', 'paste', 'cloud']
  if (hasStructured) order.push('structured')
  return { order, defaultTab: 'upload' }
}

interface ImportSourceTabsProps {
  selectedFile: File | null
  pastedData: string
  onFileChange: (file: File | null) => void
  onPastedDataChange: (data: string) => void
  /** When provided, columns are extracted from pasted/uploaded content and
   *  reported here (wizard detected-columns chips). */
  onColumnsDetected?: (columns: string[]) => void
  /** Project kind steering tab order + default (exam leads structured). */
  projectKind?: string
  /** Extended structured-entry tab; omitted → no fourth tab. */
  structuredTab?: { label: ReactNode; content: ReactNode }
  /** Cloud tab body (CloudImportPanel in select or immediate mode). */
  cloudPanel?: ReactNode
  /** Prefix for every data-testid (e.g. "project-create", "import-modal"). */
  testIdPrefix: string
}

export function ImportSourceTabs({
  selectedFile,
  pastedData,
  onFileChange,
  onPastedDataChange,
  onColumnsDetected,
  projectKind,
  structuredTab,
  cloudPanel,
  testIdPrefix,
}: ImportSourceTabsProps) {
  const { t } = useI18n()
  const { addToast } = useToast()
  const p = testIdPrefix
  const fileInputId = `${p}-file-upload`

  const { order, defaultTab } = getImportTabConfig(projectKind, !!structuredTab)

  const handlePastedDataChange = useCallback(
    (data: string) => {
      onPastedDataChange(data)
      onColumnsDetected?.(extractColumns(data))
    },
    [onPastedDataChange, onColumnsDetected]
  )

  const handleFileWithColumns = useCallback(
    (file: File | null) => {
      onFileChange(file)
      if (!onColumnsDetected) return
      if (file) {
        const reader = new FileReader()
        reader.onload = (e) => {
          const content = e.target?.result as string
          if (content) onColumnsDetected(extractColumns(content))
        }
        reader.readAsText(file.slice(0, 10000)) // first 10KB for column detection
      } else {
        onColumnsDetected([])
      }
    },
    [onFileChange, onColumnsDetected]
  )

  const handleFileSelect = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0]
      if (file) {
        handleFileWithColumns(file)
      }
    },
    [handleFileWithColumns]
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

  const tabLabels: Record<ImportTabId, ReactNode> = {
    upload: t('dataImport.tabs.upload', 'Datei hochladen'),
    paste: t('dataImport.tabs.paste', 'Tabelle/JSON einfügen'),
    cloud: t('dataImport.tabs.cloud', 'Cloud-Speicher'),
    structured: structuredTab?.label,
  }

  return (
    <Tabs defaultValue={defaultTab} data-testid={`${p}-data-tabs`}>
      <TabsList
        className={
          order.length === 4
            ? 'grid w-full grid-cols-4'
            : 'grid w-full grid-cols-3'
        }
      >
        {order.map((tabId) => (
          <TabsTrigger
            key={tabId}
            value={tabId}
            data-testid={`${p}-${tabId}-tab`}
          >
            {tabLabels[tabId]}
          </TabsTrigger>
        ))}
      </TabsList>

      {structuredTab && (
        <TabsContent value="structured" className="mt-6">
          {structuredTab.content}
        </TabsContent>
      )}

      <TabsContent value="upload" className="mt-6">
        <div
          className={
            selectedFile
              ? 'cursor-pointer rounded-lg border border-solid border-emerald-500 bg-emerald-50 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 dark:bg-emerald-950/30'
              : 'cursor-pointer rounded-lg border border-dashed border-zinc-300 transition-colors hover:border-emerald-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 dark:border-zinc-700'
          }
          onDrop={handleDrop}
          onDragOver={handleDragOver}
          onClick={() =>
            !selectedFile && document.getElementById(fileInputId)?.click()
          }
          onKeyDown={(e) => {
            if ((e.key === 'Enter' || e.key === ' ') && !selectedFile) {
              e.preventDefault()
              document.getElementById(fileInputId)?.click()
            }
          }}
          tabIndex={0}
          role="button"
          aria-label={t('projects.creation.wizard.step2.upload.dropzone')}
        >
          <div className="p-12 text-center">
            {selectedFile ? (
              <CheckCircleIcon className="mx-auto mb-4 h-12 w-12 text-emerald-500" />
            ) : (
              <CloudArrowUpIcon className="mx-auto mb-4 h-12 w-12 text-zinc-400 dark:text-zinc-500" />
            )}
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
                  data-testid={`${p}-remove-file-button`}
                >
                  {t('projects.creation.wizard.step2.upload.removeFile')}
                </Button>
              </div>
            ) : (
              <Button
                variant="outline"
                onClick={(e) => {
                  e.stopPropagation()
                  document.getElementById(fileInputId)?.click()
                }}
                data-testid={`${p}-choose-files-button`}
              >
                {t('projects.creation.wizard.step2.upload.chooseFiles')}
              </Button>
            )}
            <input
              id={fileInputId}
              type="file"
              accept=".json,.csv,.tsv,.txt"
              className="hidden"
              onChange={handleFileSelect}
              data-testid={`${p}-file-input`}
            />
          </div>
        </div>
      </TabsContent>

      <TabsContent value="paste" className="mt-6">
        <div className="space-y-4">
          <div className="flex items-center justify-between gap-3">
            <Label>{t('projects.creation.wizard.step2.paste.label')}</Label>
            <ExtractTextButton
              onText={(text) =>
                handlePastedDataChange(JSON.stringify([{ text }], null, 2))
              }
            />
          </div>
          <Textarea
            placeholder={t('projects.creation.wizard.step2.paste.placeholder')}
            rows={10}
            className="font-mono text-sm"
            value={pastedData}
            onChange={(e) => handlePastedDataChange(e.target.value)}
            data-testid={`${p}-paste-data-textarea`}
          />
          <div className="flex items-center justify-between">
            <div
              className="text-sm text-zinc-600 dark:text-zinc-400"
              data-testid={`${p}-paste-line-count`}
              data-line-count={
                pastedData.trim() ? pastedData.trim().split('\n').length : 0
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
                data-testid={`${p}-clear-data-button`}
              >
                {t('projects.creation.wizard.step2.paste.clear')}
              </Button>
              <Button
                variant="outline"
                disabled={!pastedData.trim()}
                data-testid={`${p}-validate-data-button`}
                onClick={() => {
                  try {
                    const format = detectFormat(pastedData.trim())
                    addToast(
                      t('projects.creation.wizard.step2.paste.formatDetected', {
                        format: format.toUpperCase(),
                      }),
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
        {cloudPanel}
      </TabsContent>
    </Tabs>
  )
}

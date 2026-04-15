/**
 * Universal data import component with all formats and field mapping
 * Issue #220: Complete import solution like Label Studio
 */

import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useI18n } from '@/contexts/I18nContext'
import { cn } from '@/lib/utils'
import {
  CheckCircleIcon,
  CloudArrowUpIcon,
  DocumentPlusIcon,
  DocumentTextIcon,
  TableCellsIcon,
} from '@heroicons/react/24/outline'
import React, { useCallback, useState } from 'react'
import { ImportPreviewWithMapping } from './ImportPreviewWithMapping'

interface UniversalDataImportProps {
  onImport: (data: any[]) => void
  templateFields?: string[] // Optional template fields for mapping
  className?: string
}

export function UniversalDataImport({
  onImport,
  templateFields = [],
  className,
}: UniversalDataImportProps) {
  const { t } = useI18n()
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [isDragging, setIsDragging] = useState(false)
  const [importComplete, setImportComplete] = useState(false)

  const handleFileDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)

    const files = e.dataTransfer.files
    if (files.length > 0) {
      setSelectedFile(files[0])
    }
  }, [])

  const handleFileSelect = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = e.target.files
      if (files && files.length > 0) {
        setSelectedFile(files[0])
      }
    },
    []
  )

  const handleImport = (data: any[]) => {
    onImport(data)
    setImportComplete(true)

    // Reset after delay
    setTimeout(() => {
      setSelectedFile(null)
      setImportComplete(false)
    }, 2000)
  }

  const handleCancel = () => {
    setSelectedFile(null)
    setImportComplete(false)
  }

  if (importComplete) {
    return (
      <Card className={cn('border-green-200 bg-green-50', className)}>
        <CardContent className="py-12">
          <div className="flex flex-col items-center space-y-4">
            <CheckCircleIcon className="h-12 w-12 text-green-600" />
            <p className="text-lg font-medium text-green-900">
              {t('tasks.import.importSuccess')}
            </p>
            <p className="text-sm text-green-700">
              {t('tasks.import.importSuccessDesc')}
            </p>
          </div>
        </CardContent>
      </Card>
    )
  }

  if (selectedFile) {
    return (
      <ImportPreviewWithMapping
        file={selectedFile}
        templateFields={templateFields}
        onImport={handleImport}
        onCancel={handleCancel}
        className={className}
      />
    )
  }

  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle>{t('tasks.import.title')}</CardTitle>
      </CardHeader>
      <CardContent>
        <Alert className="mb-6">
          <AlertDescription>
            <strong>{t('tasks.import.supportedFormats')}</strong>
            <br />
            <strong>{t('tasks.import.smartMapping')}</strong>
          </AlertDescription>
        </Alert>

        {/* Drop zone */}
        <div
          className={cn(
            'rounded-lg border-2 border-dashed p-8 text-center transition-colors',
            isDragging ? 'border-blue-400 bg-blue-50' : 'border-gray-300',
            'hover:border-gray-400'
          )}
          onDragOver={(e) => {
            e.preventDefault()
            setIsDragging(true)
          }}
          onDragLeave={() => setIsDragging(false)}
          onDrop={handleFileDrop}
        >
          <CloudArrowUpIcon className="mx-auto mb-4 h-12 w-12 text-gray-400" />

          <p className="mb-2 text-lg font-medium text-gray-900">
            {t('tasks.import.dropHere')}
          </p>

          <p className="mb-6 text-sm text-gray-500">
            {t('tasks.import.clickBrowse')}
          </p>

          <input
            type="file"
            accept=".json,.jsonl,.csv,.tsv,.txt,.xlsx,.xls"
            onChange={handleFileSelect}
            className="hidden"
            id="file-upload"
          />

          <label htmlFor="file-upload">
            <Button as="span" variant="outline">
              {t('tasks.import.chooseFile')}
            </Button>
          </label>
        </div>

        {/* Format examples */}
        <div className="mt-8 grid grid-cols-2 gap-4 md:grid-cols-4">
          <div className="text-center">
            <DocumentTextIcon className="mx-auto mb-2 h-8 w-8 text-gray-400" />
            <p className="text-sm font-medium">
              {t('tasks.import.formatLabels.json')}
            </p>
            <p className="text-xs text-gray-500">
              {t('tasks.import.formatLabels.jsonDesc')}
            </p>
          </div>
          <div className="text-center">
            <TableCellsIcon className="mx-auto mb-2 h-8 w-8 text-gray-400" />
            <p className="text-sm font-medium">
              {t('tasks.import.formatLabels.csv')}
            </p>
            <p className="text-xs text-gray-500">
              {t('tasks.import.formatLabels.csvDesc')}
            </p>
          </div>
          <div className="text-center">
            <TableCellsIcon className="mx-auto mb-2 h-8 w-8 text-green-600" />
            <p className="text-sm font-medium">
              {t('tasks.import.formatLabels.excel')}
            </p>
            <p className="text-xs text-gray-500">
              {t('tasks.import.formatLabels.excelDesc')}
            </p>
          </div>
          <div className="text-center">
            <DocumentPlusIcon className="mx-auto mb-2 h-8 w-8 text-gray-400" />
            <p className="text-sm font-medium">
              {t('tasks.import.formatLabels.more')}
            </p>
            <p className="text-xs text-gray-500">
              {t('tasks.import.formatLabels.moreDesc')}
            </p>
          </div>
        </div>

        {/* Example data structure */}
        <details className="mt-6">
          <summary className="cursor-pointer text-sm text-gray-500 hover:text-gray-700">
            {t('tasks.import.examples.jsonTitle')}
          </summary>
          <pre className="mt-2 overflow-auto rounded bg-gray-50 p-4 text-xs">
            {`[
  {
    "id": "001",
    "text": "The plaintiff claims...",
    "question": "Is there a valid claim?",
    "answer": "Claim is valid",
    "category": "Civil Law"
  }
]`}
          </pre>
        </details>

        <details className="mt-2">
          <summary className="cursor-pointer text-sm text-gray-500 hover:text-gray-700">
            {t('tasks.import.examples.csvTitle')}
          </summary>
          <pre className="mt-2 overflow-auto rounded bg-gray-50 p-4 text-xs">
            {`id,text,question,answer,category
001,"The plaintiff claims...","Is there a valid claim?","Claim is valid","Civil Law"
002,"The defendant objects...","Is the claim admissible?","Claim dismissed","Civil Law"`}
          </pre>
        </details>
      </CardContent>
    </Card>
  )
}

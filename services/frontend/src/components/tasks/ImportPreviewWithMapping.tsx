/**
 * Import preview with field mapping UI
 * Issue #220: Smart field mapping for flexible data import
 */

import { useI18n } from '@/contexts/I18nContext'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/shared/Select'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  FieldMapping,
  MappingSuggestion,
  applyFieldMappings,
  suggestFieldMappings,
} from '@/lib/utils/fieldMapping'
import { truncate } from '@/lib/utils/stringUtils'
import {
  ImportResult,
  exportData,
  importFile,
} from '@/lib/utils/universalImport'
import {
  ArrowPathIcon,
  ArrowRightIcon,
  CheckCircleIcon,
  DocumentArrowDownIcon,
  ExclamationTriangleIcon,
  SparklesIcon,
} from '@heroicons/react/24/outline'
import { useCallback, useEffect, useMemo, useState } from 'react'

interface ImportPreviewWithMappingProps {
  file?: File
  templateFields?: string[]
  onImport: (data: any[]) => void
  onCancel: () => void
  className?: string
}

export function ImportPreviewWithMapping({
  file,
  templateFields = [],
  onImport,
  onCancel,
  className,
}: ImportPreviewWithMappingProps) {
  const { t } = useI18n()
  const [importResult, setImportResult] = useState<ImportResult | null>(null)
  const [mappingSuggestion, setMappingSuggestion] =
    useState<MappingSuggestion | null>(null)
  const [customMappings, setCustomMappings] = useState<Map<string, string>>(
    new Map()
  )
  const [isProcessing, setIsProcessing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<'preview' | 'mapping'>('preview')

  const processFile = useCallback(async () => {
    if (!file) return

    setIsProcessing(true)
    setError(null)

    try {
      const result = await importFile(file, {
        skipEmptyRows: true,
        detectTypes: true,
      })

      setImportResult(result)

      // Generate mapping suggestions if template fields are provided
      if (templateFields.length > 0 && result.headers) {
        const suggestion = suggestFieldMappings(
          result.headers,
          templateFields,
          result.data.slice(0, 10) // Use first 10 rows for content analysis
        )
        setMappingSuggestion(suggestion)

        // Initialize custom mappings with suggestions
        const initialMappings = new Map<string, string>()
        suggestion.mappings.forEach((m) => {
          initialMappings.set(m.source, m.target)
        })
        setCustomMappings(initialMappings)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to process file')
    } finally {
      setIsProcessing(false)
    }
  }, [file, templateFields])

  // Process file when it changes
  useEffect(() => {
    if (file) {
      processFile()
    }
  }, [file, processFile])

  // Get final mappings (including custom modifications)
  const finalMappings = useMemo((): FieldMapping[] => {
    if (!mappingSuggestion) return []

    return Array.from(customMappings.entries()).map(([source, target]) => {
      const original = mappingSuggestion.mappings.find(
        (m) => m.source === source
      )
      return {
        source,
        target,
        confidence: original?.confidence || 0.5,
        type:
          original?.source === source && original.target === target
            ? original.type
            : 'manual',
      }
    })
  }, [customMappings, mappingSuggestion])

  // Apply mappings to preview data
  const mappedData = useMemo(() => {
    if (!importResult || templateFields.length === 0)
      return importResult?.data || []
    return applyFieldMappings(importResult.data, finalMappings)
  }, [importResult, finalMappings, templateFields])

  const handleMapping = (source: string, target: string) => {
    const newMappings = new Map(customMappings)
    if (target === 'none') {
      newMappings.delete(source)
    } else {
      newMappings.set(source, target)
    }
    setCustomMappings(newMappings)
  }

  const handleImport = () => {
    onImport(mappedData)
  }

  const handleExportMapping = () => {
    const mappingConfig = {
      mappings: Object.fromEntries(customMappings),
      sourceFields: importResult?.headers || [],
      targetFields: templateFields,
      timestamp: new Date().toISOString(),
    }

    exportData([mappingConfig], 'json', 'field-mapping-config')
  }

  if (isProcessing) {
    return (
      <Card className={className}>
        <CardContent className="py-12">
          <div className="flex flex-col items-center space-y-4">
            <ArrowPathIcon className="h-8 w-8 animate-spin text-gray-400" />
            <p className="text-sm text-gray-500">{t('tasks.import.processingFile')}</p>
          </div>
        </CardContent>
      </Card>
    )
  }

  if (error) {
    return (
      <Card className={className}>
        <CardContent className="py-6">
          <Alert variant="destructive">
            <ExclamationTriangleIcon className="h-4 w-4" />
            <AlertDescription>{error}</AlertDescription>
          </Alert>
          <div className="mt-4 flex justify-end">
            <Button variant="outline" onClick={onCancel}>
              {t('tasks.import.cancel')}
            </Button>
          </div>
        </CardContent>
      </Card>
    )
  }

  if (!importResult) {
    return null
  }

  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          <span>{t('tasks.import.importPreview')}</span>
          <div className="flex items-center gap-2">
            <Badge variant="outline">{importResult.format.toUpperCase()}</Badge>
            <Badge>{t('tasks.import.rowCount', { count: importResult.data.length })}</Badge>
          </div>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <Tabs defaultValue={activeTab}>
          <TabsList className="grid w-full grid-cols-2">
            <TabsTrigger value="preview">
              {t('tasks.import.dataPreview')}
              {importResult.errors && (
                <ExclamationTriangleIcon className="ml-2 h-4 w-4 text-yellow-500" />
              )}
            </TabsTrigger>
            <TabsTrigger value="mapping" disabled={templateFields.length === 0}>
              <span>{t('tasks.import.fieldMapping')}</span>
              {mappingSuggestion && (
                <Badge
                  variant="outline"
                  className={`ml-2 ${
                    mappingSuggestion.quality === 'high'
                      ? 'text-green-600'
                      : mappingSuggestion.quality === 'medium'
                        ? 'text-yellow-600'
                        : 'text-red-600'
                  }`}
                >
                  {mappingSuggestion.quality}
                </Badge>
              )}
            </TabsTrigger>
          </TabsList>

          <TabsContent value="preview" className="space-y-4">
            {/* Import summary */}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-sm font-medium text-gray-500">{t('tasks.import.file')}</p>
                <p className="text-sm">{file?.name}</p>
              </div>
              <div>
                <p className="text-sm font-medium text-gray-500">{t('tasks.import.size')}</p>
                <p className="text-sm">{formatFileSize(file?.size || 0)}</p>
              </div>
              {importResult.metadata?.sheets && (
                <div className="col-span-2">
                  <p className="text-sm font-medium text-gray-500">{t('tasks.import.sheets')}</p>
                  <div className="mt-1 flex gap-2">
                    {importResult.metadata.sheets.map((sheet) => (
                      <Badge key={sheet} variant="outline">
                        {sheet}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Errors */}
            {importResult.errors && importResult.errors.length > 0 && (
              <Alert>
                <ExclamationTriangleIcon className="h-4 w-4" />
                <AlertDescription>
                  <p className="font-medium">{t('tasks.import.importWarnings')}</p>
                  <ul className="mt-1 list-inside list-disc">
                    {importResult.errors.slice(0, 3).map((err, i) => (
                      <li key={i} className="text-sm">
                        {err}
                      </li>
                    ))}
                    {importResult.errors.length > 3 && (
                      <li className="text-sm">
                        {t('tasks.import.andMoreErrors', { count: importResult.errors.length - 3 })}
                      </li>
                    )}
                  </ul>
                </AlertDescription>
              </Alert>
            )}

            {/* Data preview */}
            <div className="overflow-hidden rounded-lg border">
              <Table>
                <TableHeader>
                  <TableRow>
                    {(
                      importResult.headers ||
                      Object.keys(importResult.data[0] || {})
                    ).map((header) => (
                      <TableHead key={header} className="font-mono text-xs">
                        {header}
                      </TableHead>
                    ))}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {importResult.data.slice(0, 5).map((row, i) => (
                    <TableRow key={i}>
                      {(importResult.headers || Object.keys(row)).map(
                        (header) => (
                          <TableCell key={header} className="text-sm">
                            {truncate(String(row[header] || ''), 50)}
                          </TableCell>
                        )
                      )}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              {importResult.data.length > 5 && (
                <div className="bg-gray-50 p-2 text-center text-sm text-gray-500">
                  {t('tasks.import.andMoreRows', { count: importResult.data.length - 5 })}
                </div>
              )}
            </div>
          </TabsContent>

          <TabsContent value="mapping" className="space-y-4">
            {mappingSuggestion && (
              <>
                {/* Mapping quality indicator */}
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium">{t('tasks.import.mappingQuality')}</span>
                    <span className="text-sm text-gray-500">
                      {t('tasks.import.fieldsMapped', { mapped: finalMappings.length, total: importResult.headers?.length || 0 })}
                    </span>
                  </div>
                  <Progress
                    value={
                      (finalMappings.length /
                        (importResult.headers?.length || 1)) *
                      100
                    }
                    className="h-2"
                  />
                </div>

                {/* Field mappings */}
                <div className="space-y-2">
                  <div className="mb-2 flex items-center justify-between">
                    <h4 className="text-sm font-medium">{t('tasks.import.fieldMappings')}</h4>
                    <Button variant="outline" onClick={handleExportMapping}>
                      <DocumentArrowDownIcon className="mr-2 h-4 w-4" />
                      {t('tasks.import.exportMapping')}
                    </Button>
                  </div>

                  <div className="max-h-96 space-y-2 overflow-y-auto">
                    {importResult.headers?.map((sourceField) => {
                      const mapping = finalMappings.find(
                        (m) => m.source === sourceField
                      )
                      const confidence = mapping?.confidence || 0

                      return (
                        <div
                          key={sourceField}
                          className="flex items-center gap-3 rounded-lg bg-gray-50 p-2"
                        >
                          <div className="flex-1">
                            <div className="flex items-center gap-2">
                              <span className="font-mono text-sm">
                                {sourceField}
                              </span>
                              {mapping && (
                                <Badge
                                  variant="outline"
                                  className={`text-xs ${
                                    confidence > 0.9
                                      ? 'text-green-600'
                                      : confidence > 0.7
                                        ? 'text-yellow-600'
                                        : 'text-gray-600'
                                  }`}
                                >
                                  {mapping.type}
                                </Badge>
                              )}
                            </div>
                          </div>

                          <ArrowRightIcon className="h-4 w-4 text-gray-400" />

                          <Select
                            value={customMappings.get(sourceField) || 'none'}
                            onValueChange={(v) => handleMapping(sourceField, v)}
                          >
                            <SelectTrigger className="w-48">
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="none">
                                <span className="text-gray-500">
                                  {t('tasks.import.skipField')}
                                </span>
                              </SelectItem>
                              {templateFields.map((targetField) => (
                                <SelectItem
                                  key={targetField}
                                  value={targetField}
                                >
                                  {targetField}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        </div>
                      )
                    })}
                  </div>
                </div>

                {/* Unmapped fields warning */}
                {mappingSuggestion.unmappedSource.length > 0 && (
                  <Alert>
                    <ExclamationTriangleIcon className="h-4 w-4" />
                    <AlertDescription>
                      <p className="font-medium">{t('tasks.import.unmappedSourceFields')}</p>
                      <p className="mt-1 text-sm">
                        {mappingSuggestion.unmappedSource.join(', ')}
                      </p>
                    </AlertDescription>
                  </Alert>
                )}
              </>
            )}
          </TabsContent>
        </Tabs>

        {/* Actions */}
        <div className="mt-6 flex justify-between">
          <Button variant="outline" onClick={onCancel}>
            {t('tasks.import.cancel')}
          </Button>
          <div className="flex gap-2">
            {templateFields.length > 0 && (
              <Button
                variant="outline"
                onClick={() => setActiveTab('mapping')}
                disabled={activeTab === 'mapping'}
              >
                <SparklesIcon className="mr-2 h-4 w-4" />
                {t('tasks.import.configureMapping')}
              </Button>
            )}
            <Button onClick={handleImport}>
              <CheckCircleIcon className="mr-2 h-4 w-4" />
              {t('tasks.import.importItems', { count: importResult.data.length })}
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return bytes + ' bytes'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

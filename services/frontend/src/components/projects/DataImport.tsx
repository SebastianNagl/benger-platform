/**
 * DataImport component - Label Studio aligned flexible data import
 *
 * This component allows importing data in various formats (JSON, CSV, paste)
 * following Label Studio's "we adapt to your data" philosophy
 */

import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import { useI18n } from '@/contexts/I18nContext'
import { useProjectStore } from '@/stores/projectStore'
import {
  CheckCircleIcon,
  ClipboardDocumentIcon,
  CloudArrowUpIcon,
} from '@heroicons/react/24/outline'
import { useCallback, useState } from 'react'
import { useDropzone } from 'react-dropzone'
import { toast } from 'react-hot-toast'

interface DataImportProps {
  projectId: string
  onComplete?: () => void
}

export function DataImport({ projectId, onComplete }: DataImportProps) {
  const { t } = useI18n()
  const { importData, loading } = useProjectStore()
  const [importMethod, setImportMethod] = useState<'file' | 'paste'>('file')
  const [pasteContent, setPasteContent] = useState('')
  const [importStats, setImportStats] = useState<{
    total: number
    successful: number
    failed: number
  } | null>(null)

  // File upload handler
  const processFile = useCallback(
    async (file: File) => {
      try {
        const text = await file.text()
        let data: any[]

        // Try to parse based on file type
        if (file.name.endsWith('.json')) {
          data = JSON.parse(text)
          // Handle both array and object with data property
          if (!Array.isArray(data)) {
            if ((data as any).data && Array.isArray((data as any).data)) {
              data = (data as any).data
            } else {
              data = [data]
            }
          }
        } else if (file.name.endsWith('.csv') || file.name.endsWith('.tsv')) {
          // Simple CSV/TSV parser
          const delimiter = file.name.endsWith('.tsv') ? '\t' : ','
          const lines = text.trim().split('\n')
          const headers = lines[0].split(delimiter).map((h) => h.trim())

          data = lines.slice(1).map((line) => {
            const values = line.split(delimiter)
            const obj: any = {}
            headers.forEach((header, index) => {
              obj[header] = values[index]?.trim() || ''
            })
            return obj
          })
        } else if (file.name.endsWith('.txt')) {
          // Plain text - each line becomes a task
          data = text
            .trim()
            .split('\n')
            .map((line) => ({ text: line.trim() }))
        } else {
          throw new Error(t('projects.dataImport.unsupportedFormat'))
        }

        // Import the data
        await importData(projectId, data)

        setImportStats({
          total: data.length,
          successful: data.length,
          failed: 0,
        })

        toast.success(t('projects.dataImport.importSuccess', { count: data.length }))
        onComplete?.()
      } catch (error) {
        console.error('Import error:', error)
        toast.error(
          error instanceof Error ? error.message : t('projects.dataImport.importFileFailed')
        )
      }
    },
    [projectId, importData, onComplete]
  )

  // Dropzone configuration
  const { getRootProps, getInputProps, isDragActive, acceptedFiles } =
    useDropzone({
      onDrop: async (files) => {
        if (files.length > 0) {
          await processFile(files[0])
        }
      },
      accept: {
        'application/json': ['.json'],
        'text/csv': ['.csv'],
        'text/tab-separated-values': ['.tsv'],
        'text/plain': ['.txt'],
      },
      maxFiles: 1,
      disabled: loading,
    })

  // Paste import handler
  const handlePasteImport = async () => {
    if (!pasteContent.trim()) {
      toast.error(t('projects.dataImport.pasteEmpty'))
      return
    }

    try {
      let data: any[]

      // Try to parse as JSON first
      try {
        const parsed = JSON.parse(pasteContent)
        data = Array.isArray(parsed) ? parsed : [parsed]
      } catch {
        // If not JSON, treat each line as a text item
        data = pasteContent
          .trim()
          .split('\n')
          .map((line) => ({ text: line.trim() }))
      }

      await importData(projectId, data)

      setImportStats({
        total: data.length,
        successful: data.length,
        failed: 0,
      })

      setPasteContent('')
      toast.success(t('projects.dataImport.importSuccess', { count: data.length }))
      onComplete?.()
    } catch (error) {
      console.error('Import error:', error)
      toast.error(t('projects.dataImport.importFailed'))
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('projects.dataImport.title')}</CardTitle>
        <CardDescription>
          {t('projects.dataImport.subtitle')}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Tabs defaultValue={importMethod}>
          <TabsList className="grid w-full grid-cols-2">
            <TabsTrigger value="file">
              <CloudArrowUpIcon className="mr-2 h-4 w-4" />
              {t('projects.dataImport.uploadFile')}
            </TabsTrigger>
            <TabsTrigger value="paste">
              <ClipboardDocumentIcon className="mr-2 h-4 w-4" />
              {t('projects.dataImport.pasteData')}
            </TabsTrigger>
          </TabsList>

          {/* File Upload */}
          <TabsContent value="file" className="mt-4">
            <div
              {...getRootProps()}
              className={`cursor-pointer rounded-lg border-2 border-dashed p-8 text-center transition-colors duration-200 ${isDragActive ? 'border-primary bg-primary/5' : 'border-border hover:border-primary/50'} ${loading ? 'cursor-not-allowed opacity-50' : ''} `}
            >
              <input {...getInputProps()} />
              <CloudArrowUpIcon className="text-muted-foreground mx-auto mb-4 h-12 w-12" />

              {isDragActive ? (
                <p className="text-lg font-medium">{t('projects.dataImport.dropFile')}</p>
              ) : (
                <>
                  <p className="mb-2 text-lg font-medium">
                    {t('projects.dataImport.dragAndDrop')}
                  </p>
                  <p className="text-muted-foreground mb-4 text-sm">
                    {t('projects.dataImport.supportedFormats')}
                  </p>
                </>
              )}

              <div className="mt-4 flex justify-center gap-2">
                <Badge variant="secondary">JSON</Badge>
                <Badge variant="secondary">CSV</Badge>
                <Badge variant="secondary">TSV</Badge>
                <Badge variant="secondary">TXT</Badge>
              </div>
            </div>

            {/* File format examples */}
            <div className="mt-6 space-y-4">
              <div>
                <h4 className="mb-2 text-sm font-medium">{t('projects.dataImport.exampleFormats')}</h4>
                <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                  <div>
                    <p className="text-muted-foreground mb-1 font-mono text-xs">
                      JSON:
                    </p>
                    <pre className="bg-muted overflow-x-auto rounded p-2 text-xs">
                      {`[
  {"text": "Question 1"},
  {"text": "Question 2", "meta": "data"}
]`}
                    </pre>
                  </div>
                  <div>
                    <p className="text-muted-foreground mb-1 font-mono text-xs">
                      CSV:
                    </p>
                    <pre className="bg-muted overflow-x-auto rounded p-2 text-xs">
                      {`text,category
"Question 1","Legal"
"Question 2","Tax"`}
                    </pre>
                  </div>
                </div>
              </div>
            </div>
          </TabsContent>

          {/* Paste Data */}
          <TabsContent value="paste" className="mt-4 space-y-4">
            <Textarea
              placeholder={t('projects.dataImport.pastePlaceholder')}
              value={pasteContent}
              onChange={(e) => setPasteContent(e.target.value)}
              rows={10}
              className="font-mono text-sm"
              disabled={loading}
            />

            <Button
              onClick={handlePasteImport}
              disabled={loading || !pasteContent.trim()}
              className="w-full"
            >
              {loading ? t('projects.dataImport.importing') : t('projects.dataImport.importData')}
            </Button>
          </TabsContent>
        </Tabs>

        {/* Import Results */}
        {importStats && (
          <Alert className="mt-6">
            <CheckCircleIcon className="h-4 w-4" />
            <AlertDescription>
              {t('projects.dataImport.importStats', { successful: importStats.successful, total: importStats.total })}
              {importStats.failed > 0 && (
                <span className="text-destructive ml-2">
                  ({t('projects.dataImport.importStatsFailed', { count: importStats.failed })})
                </span>
              )}
            </AlertDescription>
          </Alert>
        )}
      </CardContent>
    </Card>
  )
}

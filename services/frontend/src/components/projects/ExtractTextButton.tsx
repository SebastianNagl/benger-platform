'use client'

import { useRef, useState } from 'react'
import { DocumentArrowUpIcon } from '@heroicons/react/24/outline'

import { Button } from '@/components/shared/Button'
import { useToast } from '@/components/shared/Toast'
import { useI18n } from '@/contexts/I18nContext'
import { EXTRACTABLE_ACCEPT, filesAPI } from '@/lib/api/files'

interface Props {
  /** Receives the extracted plain text of the chosen document. */
  onText: (text: string, fileName: string) => void
  className?: string
}

/**
 * "Text aus Dokument extrahieren": picks a .pdf/.docx/.txt/.md file, runs it
 * through the platform text extractor and hands the plain text to the
 * caller (data import pre-fill, structured editors). Warnings from the
 * extractor (e.g. scanned pages skipped) surface as a toast.
 */
export function ExtractTextButton({ onText, className }: Props) {
  const { t } = useI18n()
  const { showToast } = useToast()
  const inputRef = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState(false)

  const handleFile = async (file: File | null) => {
    if (!file) return
    setBusy(true)
    try {
      const res = await filesAPI.extractText(file)
      onText(res.text, file.name)
      if (res.warnings?.length) showToast(res.warnings.join(' '), 'warning')
    } catch (err: any) {
      showToast(
        err?.message || t('tasks.importModal.extractText.failed', 'Text konnte nicht extrahiert werden.'),
        'error',
      )
    } finally {
      setBusy(false)
      if (inputRef.current) inputRef.current.value = ''
    }
  }

  return (
    <span className={className}>
      <input
        ref={inputRef}
        type="file"
        accept={EXTRACTABLE_ACCEPT}
        className="hidden"
        data-testid="extract-text-input"
        onChange={(e) => handleFile(e.target.files?.[0] ?? null)}
      />
      <Button
        type="button"
        variant="outline"
        disabled={busy}
        onClick={() => inputRef.current?.click()}
        data-testid="extract-text-button"
      >
        <DocumentArrowUpIcon className="mr-2 h-4 w-4" />
        {busy
          ? t('tasks.importModal.extractText.busy', 'Extrahiere…')
          : t('tasks.importModal.extractText.button', 'Text aus Dokument (PDF/DOCX)')}
      </Button>
    </span>
  )
}

export default ExtractTextButton

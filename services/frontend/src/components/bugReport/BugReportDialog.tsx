'use client'

/**
 * The "Report a problem" dialog: a short form (what happened, what was
 * expected, an optional screenshot by file or paste, a contact address when
 * nobody is signed in) and a collapsible preview of the technical context
 * that goes with it. Sends `POST /api/bug-reports` (multipart).
 *
 * Works without the app's providers too (the last-resort crash card renders
 * it outside them): auth is optional, the copy falls back to the catalog and
 * the request is a plain same-origin fetch.
 */

import { PhotoIcon, XMarkIcon } from '@heroicons/react/24/outline'
import { useEffect, useMemo, useRef, useState } from 'react'

import { Button } from '@/components/shared/Button'
import { Dialog } from '@/components/shared/Dialog'
import { Input } from '@/components/shared/Input'
import { Label } from '@/components/shared/Label'
import { Textarea } from '@/components/shared/Textarea'
import { useOptionalAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { apiClient } from '@/lib/api/client'
import {
  buildBugReportContext,
  type BugReportContextInput,
} from '@/lib/bugReport/context'
import type { BugReportSource } from '@/lib/bugReport/store'
import { getActiveExtensions } from '@/lib/extensions/active'
import { getFeatureFlagMap } from '@/lib/featureFlags'

/** Limits of the server (services/shared/bug_reports.py). */
export const MAX_TITLE_CHARS = 150
export const MAX_TEXT_CHARS = 5000
export const MAX_SCREENSHOT_BYTES = 5 * 1024 * 1024
const SCREENSHOT_TYPES = ['image/png', 'image/jpeg', 'image/webp']

/** Error codes of the API with their own message. */
const ERROR_KEYS: Record<string, string> = {
  title_required: 'bugReport.errors.titleRequired',
  description_required: 'bugReport.errors.descriptionRequired',
  too_long: 'bugReport.errors.tooLong',
  invalid_email: 'bugReport.errors.invalidEmail',
  screenshot_too_large: 'bugReport.errors.screenshotTooLarge',
  screenshot_type: 'bugReport.errors.screenshotType',
  rate_limited: 'bugReport.errors.rateLimited',
  context_too_large: 'bugReport.errors.contextTooLarge',
}

interface Props {
  open: boolean
  onClose: () => void
  source: BugReportSource
  /** What only a host inside the providers knows (route params, UI mode). */
  extraContext?: Pick<BugReportContextInput, 'routeParams' | 'uiMode'>
}

type Phase = 'editing' | 'sending' | 'sent'

export function BugReportDialog({
  open,
  onClose,
  source,
  extraContext,
}: Props) {
  const { t, locale } = useI18n()
  const auth = useOptionalAuth()
  const user = auth?.user ?? null
  const organizations = auth?.organizations

  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [expected, setExpected] = useState('')
  const [email, setEmail] = useState('')
  const [screenshot, setScreenshot] = useState<File | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [phase, setPhase] = useState<Phase>('editing')
  const [context, setContext] = useState<Record<string, unknown>>({})
  const fileInput = useRef<HTMLInputElement>(null)

  // Snapshot the context when the dialog opens, so the preview is exactly
  // what is sent.
  useEffect(() => {
    if (!open) return
    setContext(
      buildBugReportContext({
        source,
        locale,
        // Plain reads, no auth hooks: the dialog also renders outside the
        // providers (crash card).
        featureFlags: getFeatureFlagMap(),
        extensions: getActiveExtensions(),
        orgRoles: organizations?.map((org) => org.role),
        ...extraContext,
      }),
    )
    // Only when it opens: later changes would make the preview drift.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  const preview = useMemo(
    () => (screenshot ? URL.createObjectURL(screenshot) : null),
    [screenshot],
  )
  useEffect(
    () => () => {
      if (preview) URL.revokeObjectURL(preview)
    },
    [preview],
  )

  const reset = () => {
    setTitle('')
    setDescription('')
    setExpected('')
    setEmail('')
    setScreenshot(null)
    setError(null)
    setPhase('editing')
  }

  const close = () => {
    if (phase === 'sending') return
    onClose()
    // After the closing transition, so the form does not flash empty.
    setTimeout(reset, 300)
  }

  const takeScreenshot = (file: File | null | undefined) => {
    if (!file) return
    if (!SCREENSHOT_TYPES.includes(file.type)) {
      setError(t('bugReport.errors.screenshotType'))
      return
    }
    if (file.size > MAX_SCREENSHOT_BYTES) {
      setError(t('bugReport.errors.screenshotTooLarge'))
      return
    }
    setError(null)
    setScreenshot(file)
  }

  const onPaste = (event: React.ClipboardEvent) => {
    const item = Array.from(event.clipboardData?.items ?? []).find((i) =>
      i.type.startsWith('image/'),
    )
    if (!item) return
    event.preventDefault()
    takeScreenshot(item.getAsFile())
  }

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!title.trim()) return setError(t('bugReport.errors.titleRequired'))
    if (!description.trim())
      return setError(t('bugReport.errors.descriptionRequired'))
    setError(null)
    setPhase('sending')
    const form = new FormData()
    form.append('title', title.trim())
    form.append('description', description.trim())
    if (expected.trim()) form.append('expected', expected.trim())
    if (!user && email.trim()) form.append('contact_email', email.trim())
    form.append('context', JSON.stringify(context))
    if (screenshot) form.append('screenshot', screenshot)
    try {
      // The report route also takes anonymous reports, so an expired access
      // token is no 401 there and the report would lose its author. Asking
      // for the session first lets the API client refresh it.
      if (user) await apiClient.getUser().catch(() => undefined)
      await apiClient.post('/bug-reports', form)
      setPhase('sent')
    } catch (err: any) {
      if (err?.response) {
        const code: string | undefined = err.response.data?.detail?.code
        setError(t(ERROR_KEYS[code ?? ''] ?? 'bugReport.errors.generic'))
      } else {
        setError(t('bugReport.errors.network'))
      }
      setPhase('editing')
    }
  }

  const sending = phase === 'sending'

  return (
    <Dialog
      open={open}
      onClose={close}
      title={t('bugReport.title')}
      className="max-w-lg"
    >
      {phase === 'sent' ? (
        <div data-testid="bug-report-sent">
          <p className="text-sm text-zinc-700 dark:text-zinc-300">
            {t('bugReport.sent')}
          </p>
          <div className="mt-6 flex justify-end">
            <Button variant="filled" onClick={close}>
              {t('common.close')}
            </Button>
          </div>
        </div>
      ) : (
        <form
          onSubmit={submit}
          onPaste={onPaste}
          className="space-y-4"
          data-testid="bug-report-form"
          noValidate
        >
          <p className="text-sm text-zinc-600 dark:text-zinc-400">
            {t('bugReport.intro')}
          </p>
          <div>
            <Label htmlFor="bug-report-title">
              {t('bugReport.fields.title')}
            </Label>
            <Input
              id="bug-report-title"
              value={title}
              maxLength={MAX_TITLE_CHARS}
              onChange={(e) => setTitle(e.target.value)}
              placeholder={t('bugReport.placeholders.title')}
              required
              autoFocus
            />
          </div>
          <div>
            <Label htmlFor="bug-report-description">
              {t('bugReport.fields.description')}
            </Label>
            <Textarea
              id="bug-report-description"
              value={description}
              maxLength={MAX_TEXT_CHARS}
              rows={4}
              onChange={(e) => setDescription(e.target.value)}
              placeholder={t('bugReport.placeholders.description')}
              required
            />
          </div>
          <div>
            <Label htmlFor="bug-report-expected">
              {t('bugReport.fields.expected')}
            </Label>
            <Textarea
              id="bug-report-expected"
              value={expected}
              maxLength={MAX_TEXT_CHARS}
              rows={2}
              onChange={(e) => setExpected(e.target.value)}
              placeholder={t('bugReport.placeholders.expected')}
            />
          </div>
          {!user && (
            <div>
              <Label htmlFor="bug-report-email">
                {t('bugReport.fields.contactEmail')}
              </Label>
              <Input
                id="bug-report-email"
                type="email"
                value={email}
                maxLength={254}
                onChange={(e) => setEmail(e.target.value)}
                placeholder={t('bugReport.placeholders.contactEmail')}
              />
              <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                {t('bugReport.contactEmailHint')}
              </p>
            </div>
          )}

          <div>
            <span className="block text-sm font-medium text-zinc-700 dark:text-zinc-300">
              {t('bugReport.fields.screenshot')}
            </span>
            {screenshot && preview ? (
              <div className="mt-2 flex items-start gap-3">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={preview}
                  alt={t('bugReport.screenshotPreview')}
                  className="max-h-32 max-w-[60%] rounded border border-zinc-200 object-contain dark:border-zinc-700"
                />
                <div className="min-w-0 text-xs text-zinc-500 dark:text-zinc-400">
                  <p className="truncate">{screenshot.name}</p>
                  <button
                    type="button"
                    onClick={() => setScreenshot(null)}
                    className="mt-1 inline-flex items-center gap-1 text-red-600 hover:text-red-700 dark:text-red-400"
                  >
                    <XMarkIcon className="h-4 w-4" />
                    {t('bugReport.removeScreenshot')}
                  </button>
                </div>
              </div>
            ) : (
              <div className="mt-2 flex flex-wrap items-center gap-3">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => fileInput.current?.click()}
                >
                  <PhotoIcon className="mr-1 h-4 w-4" />
                  {t('bugReport.chooseScreenshot')}
                </Button>
                <span className="text-xs text-zinc-500 dark:text-zinc-400">
                  {t('bugReport.pasteHint')}
                </span>
              </div>
            )}
            <input
              ref={fileInput}
              type="file"
              accept={SCREENSHOT_TYPES.join(',')}
              className="hidden"
              data-testid="bug-report-file"
              onChange={(e) => {
                takeScreenshot(e.target.files?.[0])
                e.target.value = ''
              }}
            />
          </div>

          <details className="rounded-lg border border-zinc-200 text-sm dark:border-zinc-700">
            <summary className="cursor-pointer px-3 py-2 text-zinc-700 dark:text-zinc-300">
              {t('bugReport.attachedSummary')}
            </summary>
            <div className="border-t border-zinc-200 px-3 py-2 dark:border-zinc-700">
              <p className="mb-2 text-xs text-zinc-500 dark:text-zinc-400">
                {t('bugReport.attachedHint')}
              </p>
              <pre
                className="max-h-60 overflow-auto rounded bg-zinc-100 p-2 text-xs break-all whitespace-pre-wrap text-zinc-700 dark:bg-zinc-900 dark:text-zinc-300"
                data-testid="bug-report-context"
              >
                {JSON.stringify(context, null, 2)}
              </pre>
            </div>
          </details>

          {error && (
            <p
              role="alert"
              className="text-sm text-red-600 dark:text-red-400"
              data-testid="bug-report-error"
            >
              {error}
            </p>
          )}

          <div className="flex justify-end gap-3 pt-2">
            <Button
              type="button"
              variant="outline"
              onClick={close}
              disabled={sending}
            >
              {t('common.cancel')}
            </Button>
            <Button type="submit" variant="filled" disabled={sending}>
              {sending ? t('bugReport.sending') : t('bugReport.send')}
            </Button>
          </div>
        </form>
      )}
    </Dialog>
  )
}

export default BugReportDialog

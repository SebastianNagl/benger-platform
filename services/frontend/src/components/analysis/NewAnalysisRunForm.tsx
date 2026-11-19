'use client'

/**
 * An analysis spec (JSON) with a name: validate it against the engine
 * (normalized form and hash, or every problem the engine names) and submit
 * it. `NewAnalysisRunForm` starts a run with it; the analysis plans editor
 * saves it as a plan. The spec format is documented in
 * docs/features/analysis-engine.md and returned by GET /api/analysis/engine.
 */

import { Button } from '@/components/shared/Button'
import { Input } from '@/components/shared/Input'
import { Textarea } from '@/components/shared/Textarea'
import { useI18n } from '@/contexts/I18nContext'
import { shortHash } from '@/lib/analysis/results'
import { analysisAPI, specErrorsOf, type AnalysisRun } from '@/lib/api/analysis'
import { useId, useState } from 'react'

type Feedback =
  | { kind: 'none' }
  | { kind: 'valid'; hash: string }
  | { kind: 'invalid'; errors: string[] }
  | { kind: 'error'; message: string }

/** A starting spec naming the project's designs (the rest is to be filled in). */
export function starterSpec(designs: readonly string[], name: string): string {
  return JSON.stringify(
    {
      spec_version: 1,
      name,
      inputs: { designs: designs.length > 0 ? [...designs] : ['<design key>'] },
      measures: {},
      estimands: [],
      families: [],
    },
    null,
    2,
  )
}

export interface AnalysisSpecFormProps {
  initialSpec?: string
  initialName?: string
  designKeys: readonly string[]
  nameLabel: string
  namePlaceholder?: string
  /** The name must not be empty (a plan's name). */
  nameRequired?: boolean
  submitLabel: string
  submittingLabel: string
  submitTestId?: string
  /** Shown when `onSubmit` fails with no message of its own. */
  failedMessage: string
  /** The saved plan's hash: a valid spec says whether it still matches. */
  planHash?: string | null
  onSubmit: (spec: unknown, name: string) => Promise<void>
}

export function AnalysisSpecForm({
  initialSpec,
  initialName,
  designKeys,
  nameLabel,
  namePlaceholder,
  nameRequired = false,
  submitLabel,
  submittingLabel,
  submitTestId,
  failedMessage,
  planHash = null,
  onSubmit,
}: AnalysisSpecFormProps) {
  const { t } = useI18n()
  const ids = useId()
  const nameId = `${ids}-name`
  const specId = `${ids}-spec`
  const hintId = `${ids}-hint`
  const [name, setName] = useState(initialName ?? '')
  const [text, setText] = useState(initialSpec ?? '')
  const [feedback, setFeedback] = useState<Feedback>({ kind: 'none' })
  const [busy, setBusy] = useState<'validate' | 'submit' | null>(null)

  const parse = (): unknown | undefined => {
    try {
      return JSON.parse(text)
    } catch (error) {
      setFeedback({
        kind: 'invalid',
        errors: [
          t('analysis.newRun.invalidJson', {
            error: (error as Error).message,
          }),
        ],
      })
      return undefined
    }
  }

  const report = (error: unknown) => {
    const errors = specErrorsOf(error)
    if (errors) setFeedback({ kind: 'invalid', errors })
    else
      setFeedback({
        kind: 'error',
        message: (error as Error)?.message || failedMessage,
      })
  }

  const validate = async () => {
    const spec = parse()
    if (spec === undefined) return
    setBusy('validate')
    try {
      const result = await analysisAPI.validateSpec(spec)
      setFeedback({ kind: 'valid', hash: result.spec_hash })
    } catch (error) {
      report(error)
    } finally {
      setBusy(null)
    }
  }

  const submit = async () => {
    const spec = parse()
    if (spec === undefined) return
    setBusy('submit')
    try {
      await onSubmit(spec, name.trim())
      setBusy(null)
    } catch (error) {
      report(error)
      setBusy(null)
    }
  }

  const missingName = nameRequired && !name.trim()

  return (
    <div className="space-y-3" data-testid="analysis-spec-form">
      <div>
        <label
          htmlFor={nameId}
          className="mb-1 block text-sm font-medium text-zinc-700 dark:text-zinc-300"
        >
          {nameLabel}
        </label>
        <Input
          id={nameId}
          value={name}
          maxLength={200}
          required={nameRequired}
          onChange={(e) => setName(e.target.value)}
          placeholder={namePlaceholder}
        />
      </div>
      <div>
        <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
          <label
            htmlFor={specId}
            className="block text-sm font-medium text-zinc-700 dark:text-zinc-300"
          >
            {t('analysis.newRun.spec')}
          </label>
          <button
            type="button"
            className="text-xs font-medium text-emerald-700 hover:underline dark:text-emerald-400"
            onClick={() => {
              setText(
                starterSpec(
                  designKeys,
                  name.trim() || t('analysis.newRun.defaultName'),
                ),
              )
              setFeedback({ kind: 'none' })
            }}
          >
            {t('analysis.newRun.insertStarter')}
          </button>
        </div>
        <Textarea
          id={specId}
          value={text}
          onChange={(e) => {
            setText(e.target.value)
            setFeedback({ kind: 'none' })
          }}
          rows={16}
          spellCheck={false}
          className="font-mono text-xs"
          placeholder={t('analysis.newRun.specPlaceholder')}
          aria-describedby={hintId}
        />
        <p
          id={hintId}
          className="mt-1 text-xs text-zinc-500 dark:text-zinc-400"
        >
          {t('analysis.newRun.specHint')}
        </p>
      </div>

      {feedback.kind === 'valid' && (
        <p
          className="rounded border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800 dark:border-emerald-900/60 dark:bg-emerald-900/20 dark:text-emerald-300"
          role="status"
        >
          {t('analysis.newRun.valid', { hash: shortHash(feedback.hash) })}
          {planHash &&
            ` ${
              planHash === feedback.hash
                ? t('analysis.plans.matchesPlan')
                : t('analysis.plans.differsFromPlan')
            }`}
        </p>
      )}
      {feedback.kind === 'invalid' && (
        <div
          className="rounded border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300"
          role="alert"
          data-testid="new-analysis-run-errors"
        >
          <p className="font-medium">{t('analysis.newRun.invalid')}</p>
          <ul className="mt-1 list-disc space-y-0.5 pl-5 font-mono text-xs break-words">
            {feedback.errors.map((e, i) => (
              <li key={i}>{e}</li>
            ))}
          </ul>
        </div>
      )}
      {feedback.kind === 'error' && (
        <p
          className="rounded border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300"
          role="alert"
        >
          {feedback.message}
        </p>
      )}

      <div className="flex flex-wrap gap-2">
        <Button
          variant="outline"
          onClick={validate}
          disabled={busy !== null || !text.trim()}
        >
          {busy === 'validate'
            ? t('analysis.newRun.validating')
            : t('analysis.newRun.validate')}
        </Button>
        <Button
          variant="primary"
          onClick={submit}
          disabled={busy !== null || !text.trim() || missingName}
          data-testid={submitTestId}
        >
          {busy === 'submit' ? submittingLabel : submitLabel}
        </Button>
      </div>
    </div>
  )
}

/** The spec form that starts a run of the project. */
export function NewAnalysisRunForm({
  projectId,
  initialSpec,
  initialName,
  designKeys,
  planHash,
  onStarted,
}: {
  projectId: string
  initialSpec?: string
  initialName?: string
  designKeys: readonly string[]
  /** The hash of the plan the spec was loaded from. */
  planHash?: string | null
  onStarted: (run: AnalysisRun) => void
}) {
  const { t } = useI18n()
  return (
    <div data-testid="new-analysis-run-form">
      <AnalysisSpecForm
        initialSpec={initialSpec}
        initialName={initialName}
        designKeys={designKeys}
        nameLabel={t('analysis.newRun.name')}
        namePlaceholder={t('analysis.newRun.namePlaceholder')}
        submitLabel={t('analysis.newRun.start')}
        submittingLabel={t('analysis.newRun.starting')}
        submitTestId="new-analysis-run-start"
        failedMessage={t('analysis.newRun.failed')}
        planHash={planHash}
        onSubmit={async (spec, name) => {
          const run = await analysisAPI.startRun(projectId, spec, name)
          onStarted(run)
        }}
      />
    </div>
  )
}

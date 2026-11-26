/**
 * EvaluationMethodDialog — the large modal that creates or edits one
 * evaluation method (including the Korrektur methods, which use the same
 * builder steps).
 *
 * Layout: a header with the title, the chosen metric and "Step x of n"; a
 * named step navigation (a side column from md up, a scrolling row of pills
 * below that) where every reachable step can be opened directly; the step
 * content in its own scroll area; and a footer with Cancel, Back, Next and
 * Save.
 *
 * Closing (Escape, a click outside, the close button or Cancel) while the
 * draft differs from what was opened asks first whether to discard the
 * changes. The shared Dialog traps focus and returns it to the trigger.
 */

'use client'

import { Button } from '@/components/shared/Button'
import { ConfirmationDialog } from '@/components/shared/ConfirmationDialog'
import { Dialog, DialogTitle } from '@/components/shared/Dialog'
import { useI18n } from '@/contexts/I18nContext'
import { CheckIcon, XMarkIcon } from '@heroicons/react/24/outline'
import clsx from 'clsx'
import { type ReactNode, useEffect, useRef, useState } from 'react'

export interface EvaluationMethodStepNavItem {
  id: string
  label: string
  /** Short summary of what the step holds, e.g. the chosen metric. */
  summary?: string
  status: 'complete' | 'current' | 'upcoming'
  /** Every earlier step is filled in, so this step may be opened. */
  reachable: boolean
}

export interface EvaluationMethodDialogProps {
  open: boolean
  title: string
  /** Display name of the chosen metric, shown under the title. */
  subtitle?: string
  stepIndicator: string
  steps: EvaluationMethodStepNavItem[]
  onStepSelect: (id: string) => void
  /** The draft differs from what was opened: closing asks first. */
  dirty: boolean
  /** Closes the dialog without saving (after the confirmation if dirty). */
  onDiscard: () => void
  canGoBack: boolean
  onBack: () => void
  /** False on the last step: the footer shows no Next button there. */
  hasNext: boolean
  canGoNext: boolean
  onNext: () => void
  canSave: boolean
  onSave: () => void
  saveLabel: string
  children: ReactNode
}

export function EvaluationMethodDialog({
  open,
  title,
  subtitle,
  stepIndicator,
  steps,
  onStepSelect,
  dirty,
  onDiscard,
  canGoBack,
  onBack,
  hasNext,
  canGoNext,
  onNext,
  canSave,
  onSave,
  saveLabel,
  children,
}: EvaluationMethodDialogProps) {
  const { t } = useI18n()
  const [confirmDiscard, setConfirmDiscard] = useState(false)

  // On narrow screens the steps form a scrolling row: keep the current one
  // in view as the user moves through them.
  const currentStepRef = useRef<HTMLButtonElement | null>(null)
  const currentStepId = steps.find((step) => step.status === 'current')?.id
  useEffect(() => {
    currentStepRef.current?.scrollIntoView?.({
      block: 'nearest',
      inline: 'nearest',
    })
  }, [currentStepId, open])

  const requestClose = () => {
    if (dirty) setConfirmDiscard(true)
    else onDiscard()
  }

  return (
    <Dialog
      open={open}
      onClose={requestClose}
      className="flex h-[calc(100dvh-2rem)] max-h-[56rem] max-w-5xl flex-col p-0"
    >
      <div data-testid="evaluation-method-modal" className="contents">
        {/* Header */}
        <div
          className="flex items-start justify-between gap-4 border-b border-zinc-200 px-5 py-4 sm:px-6 dark:border-zinc-700"
          data-testid="evaluation-wizard-header"
        >
          <div className="min-w-0">
            <DialogTitle>{title}</DialogTitle>
            <p className="mt-1 flex flex-wrap items-center gap-x-2 text-sm text-zinc-500 dark:text-zinc-400">
              {subtitle && (
                <span
                  className="truncate font-medium text-zinc-700 dark:text-zinc-300"
                  data-testid="evaluation-method-modal-metric"
                >
                  {subtitle}
                </span>
              )}
              {subtitle && <span aria-hidden="true">·</span>}
              <span data-testid="wizard-step-indicator">{stepIndicator}</span>
            </p>
          </div>
          <button
            type="button"
            onClick={requestClose}
            aria-label={t('common.close')}
            title={t('common.close')}
            className="-m-1 rounded-md p-1 text-zinc-400 hover:text-zinc-600 focus:ring-2 focus:ring-emerald-500 focus:outline-none dark:hover:text-zinc-300"
            data-testid="evaluation-method-modal-close"
          >
            <XMarkIcon className="h-5 w-5" />
          </button>
        </div>

        <div className="flex min-h-0 flex-1 flex-col md:flex-row">
          {/* Step navigation */}
          <nav
            aria-label={t('evaluationBuilder.nav.label')}
            className="shrink-0 border-b border-zinc-200 bg-zinc-50 md:w-60 md:border-r md:border-b-0 dark:border-zinc-700 dark:bg-zinc-900/40"
          >
            <ol className="flex gap-1 overflow-x-auto p-2 md:flex-col md:gap-0.5 md:overflow-visible md:p-3">
              {steps.map((step, index) => {
                const isCurrent = step.status === 'current'
                const isComplete = step.status === 'complete'
                return (
                  <li key={step.id} className="shrink-0 md:shrink">
                    <button
                      ref={isCurrent ? currentStepRef : undefined}
                      type="button"
                      onClick={() => onStepSelect(step.id)}
                      disabled={!step.reachable}
                      aria-current={isCurrent ? 'step' : undefined}
                      data-testid={`wizard-step-nav-${step.id}`}
                      className={clsx(
                        'flex w-full items-start gap-2.5 rounded-lg px-2.5 py-2 text-left transition-colors focus:ring-2 focus:ring-emerald-500 focus:outline-none',
                        isCurrent
                          ? 'bg-white shadow-sm ring-1 ring-zinc-900/10 dark:bg-zinc-800 dark:ring-white/10'
                          : step.reachable
                            ? 'hover:bg-zinc-100 dark:hover:bg-zinc-800/60'
                            : 'cursor-not-allowed opacity-50',
                      )}
                    >
                      <span
                        aria-hidden="true"
                        className={clsx(
                          'mt-px flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold',
                          isComplete
                            ? 'bg-emerald-600 text-white dark:bg-emerald-500'
                            : isCurrent
                              ? 'bg-zinc-900 text-white dark:bg-emerald-400/20 dark:text-emerald-300'
                              : 'bg-zinc-200 text-zinc-600 dark:bg-zinc-700 dark:text-zinc-300',
                        )}
                      >
                        {isComplete ? (
                          <CheckIcon className="h-3 w-3" strokeWidth={3} />
                        ) : (
                          index + 1
                        )}
                      </span>
                      <span className="min-w-0">
                        <span
                          className={clsx(
                            'block text-sm whitespace-nowrap md:whitespace-normal',
                            isCurrent
                              ? 'font-semibold text-zinc-900 dark:text-white'
                              : 'text-zinc-700 dark:text-zinc-300',
                          )}
                        >
                          {step.label}
                        </span>
                        {step.summary && (
                          <span className="hidden truncate text-xs text-zinc-500 md:block dark:text-zinc-400">
                            {step.summary}
                          </span>
                        )}
                      </span>
                    </button>
                  </li>
                )
              })}
            </ol>
          </nav>

          {/* Step content */}
          <div
            className="min-h-0 flex-1 overflow-y-auto px-5 py-5 sm:px-6"
            data-testid="evaluation-wizard-body"
          >
            {children}
          </div>
        </div>

        {/* Footer — Cancel on the left; Back, Next and Save on the right. */}
        <div className="flex flex-wrap items-center justify-between gap-2 border-t border-zinc-200 bg-zinc-50 px-5 py-3 sm:px-6 dark:border-zinc-700 dark:bg-zinc-900/40">
          <Button
            onClick={requestClose}
            variant="secondary"
            className="text-sm"
            data-testid="wizard-cancel-button"
          >
            {t('evaluationBuilder.cancel')}
          </Button>
          <div className="flex flex-wrap items-center gap-2">
            <Button
              onClick={onBack}
              variant="secondary"
              disabled={!canGoBack}
              className="text-sm"
              data-testid="wizard-back-button"
            >
              {t('evaluationBuilder.back')}
            </Button>
            {hasNext && (
              <Button
                onClick={onSave}
                variant="outline"
                disabled={!canSave}
                className="text-sm"
                data-testid="wizard-save-early-button"
              >
                {saveLabel}
              </Button>
            )}
            {hasNext ? (
              <Button
                onClick={onNext}
                disabled={!canGoNext}
                className="text-sm"
                data-testid="wizard-next-button"
              >
                {t('evaluationBuilder.next')}
              </Button>
            ) : (
              <Button
                onClick={onSave}
                disabled={!canSave}
                className="text-sm"
                data-testid="wizard-save-button"
              >
                <CheckIcon className="mr-1 h-4 w-4" />
                {saveLabel}
              </Button>
            )}
          </div>
        </div>
      </div>

      <ConfirmationDialog
        isOpen={confirmDiscard}
        onClose={() => setConfirmDiscard(false)}
        onConfirm={onDiscard}
        title={t('evaluationBuilder.discard.title')}
        message={t('evaluationBuilder.discard.message')}
        confirmText={t('evaluationBuilder.discard.confirm')}
        cancelText={t('evaluationBuilder.discard.keepEditing')}
        variant="warning"
      />
    </Dialog>
  )
}

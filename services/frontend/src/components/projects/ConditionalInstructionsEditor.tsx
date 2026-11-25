/**
 * Conditional instructions ("Bedingte Anweisungen"): instruction variants
 * that annotators are randomly assigned to, by weight.
 *
 * Always editable; the annotation card's auto-save stores the list, but
 * only while it is complete: every variant has an id and a text and the
 * weights add up to 100 (or there are no variants). Until then the list
 * stays unsaved and the problem is shown inline. Text fields save on blur.
 */

'use client'

import { Button } from '@/components/shared/Button'
import { Checkbox } from '@/components/shared/Checkbox'
import { Input } from '@/components/shared/Input'
import { Textarea } from '@/components/shared/Textarea'
import { TrashIcon } from '@heroicons/react/24/outline'
import { SettingsGroup } from './SettingsGroup'

export interface ConditionalInstruction {
  id: string
  content: string
  weight: number
  ai_allowed?: boolean
}

export function conditionalWeightTotal(variants: ConditionalInstruction[]) {
  return variants.reduce((sum, v) => sum + (Number(v.weight) || 0), 0)
}

/** Complete enough to save (see the module comment). */
export function conditionalInstructionsValid(
  variants: ConditionalInstruction[],
): boolean {
  if (variants.length === 0) return true
  return (
    conditionalWeightTotal(variants) === 100 &&
    variants.every((v) => v.id.trim() !== '' && v.content.trim() !== '')
  )
}

interface Props {
  t: (key: string, params?: any) => string
  variants: ConditionalInstruction[]
  /** `text: true` for typing in a text field (saved on blur). */
  onChange: (variants: ConditionalInstruction[], text?: boolean) => void
  /** Save pending text now (blur). */
  onCommit: () => void
  disabled?: boolean
}

export function ConditionalInstructionsEditor({
  t,
  variants,
  onChange,
  onCommit,
  disabled,
}: Props) {
  const update = (
    index: number,
    patch: Partial<ConditionalInstruction>,
    text = false,
  ) => {
    const next = [...variants]
    next[index] = { ...next[index], ...patch }
    onChange(next, text)
  }
  const total = conditionalWeightTotal(variants)
  const incomplete = variants.some(
    (v) => v.id.trim() === '' || v.content.trim() === '',
  )

  return (
    <SettingsGroup
      title={t('project.conditionalInstructions.title')}
      description={t('project.conditionalInstructions.description')}
      data-testid="conditional-instructions"
    >
      {variants.map((variant, index) => (
        <div
          key={index}
          className="space-y-3 rounded-md border border-zinc-200 p-3 dark:border-zinc-700"
          data-testid="conditional-instruction-variant"
        >
          <div className="flex flex-wrap items-end gap-3">
            <div className="min-w-40 flex-1">
              <label
                htmlFor={`conditional-id-${index}`}
                className="mb-1 block text-sm font-medium text-zinc-700 dark:text-zinc-300"
              >
                {t('project.conditionalInstructions.variantId')}
              </label>
              <Input
                id={`conditional-id-${index}`}
                type="text"
                value={variant.id}
                onChange={(e) => update(index, { id: e.target.value }, true)}
                onBlur={onCommit}
                placeholder={t(
                  'project.conditionalInstructions.variantIdPlaceholder',
                )}
                disabled={disabled}
              />
            </div>
            <div className="w-24">
              <label
                htmlFor={`conditional-weight-${index}`}
                className="mb-1 block text-sm font-medium text-zinc-700 dark:text-zinc-300"
              >
                {t('project.conditionalInstructions.weight')}
              </label>
              <Input
                id={`conditional-weight-${index}`}
                type="number"
                min="1"
                max="100"
                value={variant.weight}
                onChange={(e) =>
                  update(index, { weight: parseInt(e.target.value) || 0 }, true)
                }
                onBlur={onCommit}
                disabled={disabled}
              />
            </div>
            <div className="flex h-10 items-center">
              <Checkbox
                id={`ai-allowed-${index}`}
                label={t('project.conditionalInstructions.aiAllowed')}
                checked={variant.ai_allowed || false}
                onChange={(e) =>
                  update(index, { ai_allowed: e.target.checked })
                }
                disabled={disabled}
              />
            </div>
            <Button
              variant="outline"
              className="h-10 px-3"
              onClick={() => onChange(variants.filter((_, i) => i !== index))}
              disabled={disabled}
              aria-label={t('project.conditionalInstructions.removeVariant')}
              data-testid="conditional-instruction-remove"
            >
              <TrashIcon className="h-4 w-4" />
            </Button>
          </div>
          <div>
            <label
              htmlFor={`conditional-content-${index}`}
              className="mb-1 block text-sm font-medium text-zinc-700 dark:text-zinc-300"
            >
              {t('project.conditionalInstructions.content')}
            </label>
            <Textarea
              id={`conditional-content-${index}`}
              value={variant.content}
              onChange={(e) => update(index, { content: e.target.value }, true)}
              onBlur={onCommit}
              rows={2}
              className="resize-none"
              disabled={disabled}
            />
          </div>
        </div>
      ))}

      {variants.length > 0 && (total !== 100 || incomplete) ? (
        <p
          className="text-xs text-red-600 dark:text-red-400"
          role="alert"
          data-testid="conditional-instructions-invalid"
        >
          {total !== 100
            ? t('project.conditionalInstructions.weightWarning', { total })
            : t('project.conditionalInstructions.incomplete')}
        </p>
      ) : null}

      <div>
        <Button
          variant="outline"
          className="text-sm"
          onClick={() =>
            onChange([
              ...variants,
              { id: '', content: '', weight: 50, ai_allowed: false },
            ])
          }
          disabled={disabled}
        >
          {t('project.conditionalInstructions.addVariant')}
        </Button>
      </div>
    </SettingsGroup>
  )
}

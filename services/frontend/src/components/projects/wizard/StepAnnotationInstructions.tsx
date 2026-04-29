'use client'

import { Button } from '@/components/shared/Button'
import { Input } from '@/components/shared/Input'
import { Label } from '@/components/shared/Label'
import { Textarea } from '@/components/shared/Textarea'
import { useI18n } from '@/contexts/I18nContext'
import { cn } from '@/lib/utils'
import {
  ChevronDownIcon,
  ChevronUpIcon,
  PlusIcon,
  TrashIcon,
} from '@heroicons/react/24/outline'
import { useState } from 'react'
import { ConditionalInstruction } from './types'

interface StepAnnotationInstructionsProps {
  instructions: string
  conditionalInstructions: ConditionalInstruction[]
  showInstruction: boolean
  instructionsAlwaysVisible: boolean
  showSkipButton: boolean
  onInstructionsChange: (instructions: string) => void
  onConditionalInstructionsChange: (
    conditionalInstructions: ConditionalInstruction[]
  ) => void
  onShowInstructionChange: (val: boolean) => void
  onInstructionsAlwaysVisibleChange: (val: boolean) => void
  onShowSkipButtonChange: (val: boolean) => void
}

export function StepAnnotationInstructions({
  instructions,
  conditionalInstructions,
  showInstruction,
  instructionsAlwaysVisible,
  showSkipButton,
  onInstructionsChange,
  onConditionalInstructionsChange,
  onShowInstructionChange,
  onInstructionsAlwaysVisibleChange,
  onShowSkipButtonChange,
}: StepAnnotationInstructionsProps) {
  const { t } = useI18n()
  const [showVariants, setShowVariants] = useState(
    conditionalInstructions.length > 0
  )

  const weightSum = conditionalInstructions.reduce(
    (sum, v) => sum + v.weight,
    0
  )
  const hasWeightError =
    conditionalInstructions.length > 0 && Math.abs(weightSum - 100) > 0.01

  const addVariant = () => {
    onConditionalInstructionsChange([
      ...conditionalInstructions,
      {
        id: `variant_${conditionalInstructions.length + 1}`,
        content: '',
        weight: conditionalInstructions.length === 0 ? 100 : 0,
        ai_allowed: false,
      },
    ])
  }

  const removeVariant = (index: number) => {
    onConditionalInstructionsChange(
      conditionalInstructions.filter((_, i) => i !== index)
    )
  }

  const updateVariant = (
    index: number,
    field: keyof ConditionalInstruction,
    value: string | number | boolean
  ) => {
    const updated = [...conditionalInstructions]
    updated[index] = { ...updated[index], [field]: value }
    onConditionalInstructionsChange(updated)
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="mb-2 text-2xl font-semibold text-zinc-900 dark:text-white">
          {t('projects.creation.wizard.step4.title')}
        </h2>
        <p className="text-zinc-600 dark:text-zinc-400">
          {t('projects.creation.wizard.step4.subtitle')}
        </p>
      </div>

      <div className="space-y-4">
        <div>
          <Label htmlFor="instructions">
            {t('projects.creation.wizard.step4.instructionsLabel')}
          </Label>
          <Textarea
            id="instructions"
            placeholder={t(
              'projects.creation.wizard.step4.instructionsPlaceholder'
            )}
            value={instructions}
            onChange={(e) => onInstructionsChange(e.target.value)}
            rows={6}
            data-testid="wizard-instructions-textarea"
          />
        </div>

        {/* Conditional Variants */}
        <div className="rounded-lg border border-zinc-200 dark:border-zinc-700">
          <button
            type="button"
            onClick={() => setShowVariants(!showVariants)}
            className="flex w-full items-center justify-between p-4 text-left"
            data-testid="wizard-variants-toggle"
          >
            <div>
              <p className="text-sm font-medium text-zinc-900 dark:text-white">
                {t('projects.creation.wizard.step4.variantsTitle')}
              </p>
              <p className="text-xs text-zinc-500 dark:text-zinc-400">
                {t('projects.creation.wizard.step4.variantsDescription')}
              </p>
            </div>
            {showVariants ? (
              <ChevronUpIcon className="h-5 w-5 text-zinc-400" />
            ) : (
              <ChevronDownIcon className="h-5 w-5 text-zinc-400" />
            )}
          </button>

          {showVariants && (
            <div className="border-t border-zinc-200 p-4 dark:border-zinc-700">
              <div className="space-y-4">
                {conditionalInstructions.map((variant, index) => (
                  <div
                    key={index}
                    className="rounded-lg border border-zinc-200 p-4 dark:border-zinc-700"
                    data-testid={`wizard-variant-${index}`}
                  >
                    <div className="mb-3 flex items-center justify-between">
                      <span className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
                        {t('projects.creation.wizard.step4.variant')} {index + 1}
                      </span>
                      <Button
                        variant="outline"
                        onClick={() => removeVariant(index)}
                        className="h-8 w-8 p-0"
                        data-testid={`wizard-variant-remove-${index}`}
                      >
                        <TrashIcon className="h-4 w-4 text-red-500" />
                      </Button>
                    </div>

                    <div className="space-y-3">
                      <div className="grid grid-cols-2 gap-3">
                        <div>
                          <Label className="text-xs">
                            {t('projects.creation.wizard.step4.variantId')}
                          </Label>
                          <Input
                            value={variant.id}
                            onChange={(e) =>
                              updateVariant(index, 'id', e.target.value)
                            }
                            placeholder="e.g., variant_a"
                            className="text-sm"
                          />
                        </div>
                        <div>
                          <Label className="text-xs">
                            {t('projects.creation.wizard.step4.variantWeight')}
                          </Label>
                          <div className="flex items-center gap-1">
                            <Input
                              type="number"
                              min={0}
                              max={100}
                              value={variant.weight}
                              onChange={(e) =>
                                updateVariant(
                                  index,
                                  'weight',
                                  Number(e.target.value)
                                )
                              }
                              className="text-sm"
                            />
                            <span className="text-sm text-zinc-500">%</span>
                          </div>
                        </div>
                      </div>

                      <div>
                        <Label className="text-xs">
                          {t('projects.creation.wizard.step4.variantContent')}
                        </Label>
                        <Textarea
                          value={variant.content}
                          onChange={(e) =>
                            updateVariant(index, 'content', e.target.value)
                          }
                          rows={3}
                          className="text-sm"
                          placeholder={t(
                            'projects.creation.wizard.step4.variantContentPlaceholder'
                          )}
                        />
                      </div>

                      <div className="flex items-center justify-between">
                        <Label>
                          {t('projects.creation.wizard.step4.aiAllowed')}
                        </Label>
                        <input
                          type="checkbox"
                          checked={variant.ai_allowed ?? false}
                          onChange={(e) =>
                            updateVariant(
                              index,
                              'ai_allowed',
                              e.target.checked
                            )
                          }
                          className="h-4 w-4 rounded border-zinc-300 text-emerald-600 focus:ring-emerald-500 dark:border-zinc-600"
                        />
                      </div>
                    </div>
                  </div>
                ))}

                {hasWeightError && (
                  <p className="text-sm text-red-600 dark:text-red-400">
                    {t('projects.creation.wizard.step4.weightError', {
                      sum: weightSum,
                    })}
                  </p>
                )}

                <Button
                  variant="outline"
                  size="sm"
                  onClick={addVariant}
                  data-testid="wizard-add-variant"
                >
                  <PlusIcon className="mr-1 h-4 w-4" />
                  {t('projects.creation.wizard.step4.addVariant')}
                </Button>
              </div>
            </div>
          )}
        </div>

        {/* Annotation display settings */}
        <div className="space-y-4 border-t border-zinc-200 pt-4 dark:border-zinc-700">
          <Label>{t('projects.creation.wizard.step4.displaySettings')}</Label>

          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-zinc-900 dark:text-white">
                {t('projects.creation.wizard.step4.showInstructions')}
              </p>
              <p className="text-sm text-zinc-500 dark:text-zinc-400">
                {t('projects.creation.wizard.step4.showInstructionsHint')}
              </p>
            </div>
            <input
              type="checkbox"
              checked={showInstruction}
              onChange={(e) => onShowInstructionChange(e.target.checked)}
              className="h-4 w-4 rounded border-zinc-300 text-emerald-600 focus:ring-emerald-500 dark:border-zinc-600"
            />
          </div>

          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-zinc-900 dark:text-white">
                {t('projects.creation.wizard.step4.alwaysShowInstructions')}
              </p>
              <p className="text-sm text-zinc-500 dark:text-zinc-400">
                {t('projects.creation.wizard.step4.alwaysShowInstructionsHint')}
              </p>
            </div>
            <input
              type="checkbox"
              checked={instructionsAlwaysVisible}
              onChange={(e) => onInstructionsAlwaysVisibleChange(e.target.checked)}
              className="h-4 w-4 rounded border-zinc-300 text-emerald-600 focus:ring-emerald-500 dark:border-zinc-600"
            />
          </div>

          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-zinc-900 dark:text-white">
                {t('projects.creation.wizard.step4.showSkipButton')}
              </p>
              <p className="text-sm text-zinc-500 dark:text-zinc-400">
                {t('projects.creation.wizard.step4.showSkipButtonHint')}
              </p>
            </div>
            <input
              type="checkbox"
              checked={showSkipButton}
              onChange={(e) => onShowSkipButtonChange(e.target.checked)}
              className="h-4 w-4 rounded border-zinc-300 text-emerald-600 focus:ring-emerald-500 dark:border-zinc-600"
            />
          </div>
        </div>
      </div>
    </div>
  )
}

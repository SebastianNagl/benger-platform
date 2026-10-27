/**
 * Radio Field Component
 *
 * Single-choice selection field for the template system.
 *
 * Issue #216: Implement Unified Task Configuration and Display System
 */

import { useI18n } from '@/contexts/I18nContext'
import { RadioGroup } from '@headlessui/react'
import { BaseFieldProps, FieldWrapper } from './BaseField'

export function RadioField({
  field,
  value,
  onChange,
  readonly = false,
  errors = [],
  context,
  className = '',
}: BaseFieldProps) {
  const { t } = useI18n()
  const choices = field.choices || []

  if (choices.length === 0) {
    return (
      <FieldWrapper field={field} errors={errors} className={className}>
        <div className="text-sm text-zinc-500 dark:text-zinc-400">
          {t('fields.noChoices')}
        </div>
      </FieldWrapper>
    )
  }

  return (
    <FieldWrapper field={field} errors={errors} className={className}>
      <RadioGroup value={value} onChange={onChange} disabled={readonly}>
        <div className="space-y-2">
          {choices.map((choice) => (
            <RadioGroup.Option
              key={choice}
              value={choice}
              className={({ active, checked }) =>
                `${active ? 'ring-2 ring-emerald-500 ring-offset-2' : ''} ${checked ? 'border-emerald-500 bg-emerald-50 dark:border-emerald-500 dark:bg-emerald-900/20' : 'bg-white dark:bg-zinc-700'} ${readonly ? 'cursor-not-allowed opacity-50' : 'cursor-pointer'} relative rounded-lg border px-4 py-3 shadow-sm focus:outline-none`
              }
            >
              {({ checked }) => (
                <div className="flex items-center">
                  <div className="flex items-center">
                    <input
                      type="radio"
                      className="h-4 w-4 border-zinc-300 text-emerald-600 focus:ring-emerald-500 dark:border-zinc-600"
                      checked={checked}
                      readOnly
                    />
                    <label className="ml-3 block text-sm font-medium text-zinc-700 dark:text-zinc-300">
                      {choice}
                    </label>
                  </div>
                </div>
              )}
            </RadioGroup.Option>
          ))}
        </div>
      </RadioGroup>
    </FieldWrapper>
  )
}

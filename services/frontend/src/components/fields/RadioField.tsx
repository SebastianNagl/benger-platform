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
        <div className="text-sm text-gray-500 dark:text-gray-400">
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
                `${active ? 'ring-2 ring-blue-500 ring-offset-2' : ''} ${checked ? 'border-blue-200 bg-blue-100 dark:border-blue-700 dark:bg-blue-900' : 'bg-white dark:bg-gray-700'} ${readonly ? 'cursor-not-allowed opacity-50' : 'cursor-pointer'} relative rounded-lg border px-4 py-3 shadow-sm focus:outline-none`
              }
            >
              {({ checked }) => (
                <div className="flex items-center">
                  <div className="flex items-center">
                    <input
                      type="radio"
                      className="h-4 w-4 border-gray-300 text-blue-600 dark:border-gray-600"
                      checked={checked}
                      readOnly
                    />
                    <label className="ml-3 block text-sm font-medium text-gray-700 dark:text-gray-300">
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

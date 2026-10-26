/**
 * Checkbox Field Component
 *
 * Multiple-choice selection field for the template system.
 *
 * Issue #216: Implement Unified Task Configuration and Display System
 */

import { useI18n } from '@/contexts/I18nContext'
import { BaseFieldProps, FieldWrapper } from './BaseField'

export function CheckboxField({
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
  const selectedValues = Array.isArray(value) ? value : []

  const handleChange = (choice: string, checked: boolean) => {
    if (checked) {
      onChange([...selectedValues, choice])
    } else {
      onChange(selectedValues.filter((v) => v !== choice))
    }
  }

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
      <div className="space-y-2">
        {choices.map((choice) => (
          <label
            key={choice}
            className={`flex items-center ${readonly ? 'cursor-not-allowed opacity-50' : 'cursor-pointer'}`}
          >
            <input
              type="checkbox"
              className="h-4 w-4 rounded border-zinc-300 text-emerald-600 focus:ring-emerald-500 dark:border-zinc-600"
              checked={selectedValues.includes(choice)}
              onChange={(e) => handleChange(choice, e.target.checked)}
              disabled={readonly}
            />
            <span className="ml-3 text-sm text-zinc-700 dark:text-zinc-300">
              {choice}
            </span>
          </label>
        ))}
      </div>
    </FieldWrapper>
  )
}

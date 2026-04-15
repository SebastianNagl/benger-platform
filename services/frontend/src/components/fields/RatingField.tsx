/**
 * Rating Field Component
 *
 * Numeric rating/scale field for the template system.
 *
 * Issue #216: Implement Unified Task Configuration and Display System
 */

import { useI18n } from '@/contexts/I18nContext'
import { StarIcon as StarOutlineIcon } from '@heroicons/react/24/outline'
import { StarIcon } from '@heroicons/react/24/solid'
import { BaseFieldProps, FieldWrapper } from './BaseField'

export function RatingField({
  field,
  value,
  onChange,
  readonly = false,
  errors = [],
  context,
  className = '',
}: BaseFieldProps) {
  const { t } = useI18n()
  const min = field.validation?.find((v) => v.type === 'min')?.value || 1
  const max = field.validation?.find((v) => v.type === 'max')?.value || 5
  const currentValue = value || 0

  const labels = field.metadata?.labels || []
  const showLabels = field.metadata?.show_labels === true

  const handleClick = (rating: number) => {
    if (!readonly) {
      onChange(rating)
    }
  }

  return (
    <FieldWrapper field={field} errors={errors} className={className}>
      <div className="inline-flex items-center space-x-1 rounded-lg bg-gray-50 p-2 dark:bg-gray-800/50">
        {Array.from({ length: max - min + 1 }, (_, i) => i + min).map(
          (rating) => {
            const isFilled = rating <= currentValue
            const Icon = isFilled ? StarIcon : StarOutlineIcon

            return (
              <button
                key={rating}
                type="button"
                onClick={() => handleClick(rating)}
                disabled={readonly}
                className={`${
                  readonly
                    ? 'cursor-not-allowed'
                    : 'cursor-pointer hover:scale-110'
                } rounded p-1 transition-all duration-200 ${
                  isFilled ? 'bg-yellow-100 dark:bg-yellow-900/30' : ''
                }`}
                title={labels[rating - min] || t('fields.stars', { count: rating })}
              >
                <Icon
                  className={`h-8 w-8 ${
                    isFilled
                      ? 'text-yellow-400 drop-shadow-sm'
                      : 'text-gray-300 hover:text-gray-400 dark:text-gray-600 dark:hover:text-gray-500'
                  }`}
                />
              </button>
            )
          }
        )}
      </div>

      {currentValue > 0 && (
        <div className="mt-2 text-sm font-medium text-gray-700 dark:text-gray-300">
          {showLabels && labels.length > 0
            ? labels[currentValue - min] ||
              t('fields.selectedRating', { count: currentValue })
            : t('fields.selectedRating', { count: currentValue })}
        </div>
      )}
    </FieldWrapper>
  )
}

'use client'

import clsx from 'clsx'
import { useI18n } from '@/contexts/I18nContext'

interface LikertScaleProps {
  name: string
  label: string
  value: number | undefined
  onChange: (value: number) => void
  required?: boolean
  min?: number
  max?: number
}

const SCALE_POINTS = [1, 2, 3, 4, 5, 6, 7]

export function LikertScale({
  name,
  label,
  value,
  onChange,
  required = false,
  min = 1,
  max = 7,
}: LikertScaleProps) {
  const { t } = useI18n()
  const points = Array.from({ length: max - min + 1 }, (_, i) => min + i)

  return (
    <fieldset className="space-y-2">
      <legend className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
        {label}
        {required && <span className="ml-1 text-red-500">*</span>}
      </legend>
      <div className="flex items-center justify-between gap-1">
        <span className="hidden text-xs text-zinc-500 dark:text-zinc-400 sm:block">
          {t('likertScale.stronglyDisagree')}
        </span>
        <div className="flex items-center justify-center gap-1 sm:gap-2">
          {points.map((point) => (
            <label
              key={point}
              className={clsx(
                'flex h-9 w-9 cursor-pointer items-center justify-center rounded-full border-2 text-sm font-medium transition-colors',
                value === point
                  ? 'border-emerald-600 bg-emerald-600 text-white dark:border-emerald-500 dark:bg-emerald-500'
                  : 'border-zinc-300 text-zinc-700 hover:border-emerald-400 hover:bg-emerald-50 dark:border-zinc-600 dark:text-zinc-300 dark:hover:border-emerald-500 dark:hover:bg-emerald-900/30'
              )}
            >
              <input
                type="radio"
                name={name}
                value={point}
                checked={value === point}
                onChange={() => onChange(point)}
                className="sr-only"
                required={required && value === undefined}
              />
              {point}
            </label>
          ))}
        </div>
        <span className="hidden text-xs text-zinc-500 dark:text-zinc-400 sm:block">
          {t('likertScale.stronglyAgree')}
        </span>
      </div>
      {/* Mobile labels */}
      <div className="flex justify-between text-xs text-zinc-500 dark:text-zinc-400 sm:hidden">
        <span>{t('likertScale.stronglyDisagree')}</span>
        <span>{t('likertScale.stronglyAgree')}</span>
      </div>
    </fieldset>
  )
}

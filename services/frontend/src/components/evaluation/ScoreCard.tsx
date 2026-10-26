/**
 * Score Card Component
 *
 * Publication-ready metric score display with:
 * - Color-coded scores (green >0.7, yellow 0.5-0.7, red <0.5)
 * - Confidence intervals
 * - Sample size display (n)
 * - Academic formatting (3 decimal places by default)
 * - Tooltips explaining metrics
 * - Visual indicators
 *
 * Based on ACL/NeurIPS standards: 3 decimal places for 0-1 scores
 */

'use client'

import { useI18n } from '@/contexts/I18nContext'
import { formatDecimal, intlTag, readStoredLocale } from '@/lib/i18n/locales'
import { InformationCircleIcon } from '@heroicons/react/24/outline'
import { useState } from 'react'

interface ScoreCardProps {
  metric: string
  value: number
  confidenceInterval?: {
    lower: number
    upper: number
    level?: number // e.g., 95 for 95% CI
  }
  description?: string
  higherIsBetter?: boolean
  valueRange?: {
    min: number
    max: number
  }
  formatAs?: 'percentage' | 'decimal' | 'raw'
  /** Sample size for academic display */
  sampleSize?: number
  /** Number of clusters if data is clustered (for academic reporting) */
  clusterCount?: number
  /** Show compact version without CI visualization */
  compact?: boolean
  /**
   * Multi-run aggregate (migration 042). When `runs > 1`, the card renders
   * a secondary "± std (N runs)" line under the headline number so the
   * variance is visible at a glance. Omitting `runsAggregate` (or passing
   * `runs <= 1`) preserves the legacy single-run display unchanged.
   */
  runsAggregate?: {
    runs: number
    stdAcrossRuns: number
  }
  className?: string
}

interface ColorClasses {
  bg: string
  border: string
  text: string
  value: string
  indicator: string
}

const getScoreColor = (
  value: number,
  higherIsBetter: boolean = true,
  min: number = 0,
  max: number = 1,
): ColorClasses => {
  // Normalize value to 0-1 range
  const normalized = (value - min) / (max - min)
  const score = higherIsBetter ? normalized : 1 - normalized

  if (score >= 0.7) {
    return {
      bg: 'bg-emerald-50 dark:bg-emerald-900/20',
      border: 'border-emerald-200 dark:border-emerald-800',
      text: 'text-emerald-700 dark:text-emerald-300',
      value: 'text-emerald-900 dark:text-emerald-100',
      indicator: 'bg-emerald-500',
    }
  } else if (score >= 0.5) {
    return {
      bg: 'bg-amber-50 dark:bg-amber-900/20',
      border: 'border-amber-200 dark:border-amber-800',
      text: 'text-amber-700 dark:text-amber-300',
      value: 'text-amber-900 dark:text-amber-100',
      indicator: 'bg-amber-500',
    }
  } else {
    return {
      bg: 'bg-red-50 dark:bg-red-900/20',
      border: 'border-red-200 dark:border-red-800',
      text: 'text-red-700 dark:text-red-300',
      value: 'text-red-900 dark:text-red-100',
      indicator: 'bg-red-500',
    }
  }
}

const formatValue = (
  value: number,
  format: 'percentage' | 'decimal' | 'raw' = 'decimal',
  locale: string,
): string => {
  switch (format) {
    case 'percentage':
      return `${formatDecimal(value * 100, locale, 1)}%`
    case 'decimal':
      return formatDecimal(value, locale, 3)
    case 'raw':
      return formatDecimal(value, locale, 2)
    default:
      return formatDecimal(value, locale, 3)
  }
}

export function ScoreCard({
  metric,
  value,
  confidenceInterval,
  description,
  higherIsBetter = true,
  valueRange = { min: 0, max: 1 },
  formatAs = 'decimal',
  sampleSize,
  clusterCount,
  compact = false,
  runsAggregate,
  className = '',
}: ScoreCardProps) {
  const { t, locale } = useI18n()
  const [showTooltip, setShowTooltip] = useState(false)
  const colors = getScoreColor(
    value,
    higherIsBetter,
    valueRange.min,
    valueRange.max,
  )

  // Format sample size with commas for readability
  const formatSampleSize = (n: number) => n.toLocaleString(intlTag(locale))

  return (
    <div
      className={`relative rounded-lg border-2 p-4 transition-all hover:shadow-md ${colors.bg} ${colors.border} ${className}`}
    >
      {/* Metric Header */}
      <div className="mb-2 flex items-start justify-between">
        <div className="flex-1">
          <h3
            className={`text-sm font-medium tracking-wide uppercase ${colors.text}`}
          >
            {metric}
          </h3>
        </div>

        {/* Info Icon with Tooltip */}
        {description && (
          <div className="relative">
            <button
              onMouseEnter={() => setShowTooltip(true)}
              onMouseLeave={() => setShowTooltip(false)}
              className={`ml-2 transition-opacity ${colors.text} hover:opacity-75`}
              aria-label={t('evaluation.scoreCard.infoAbout', { metric })}
            >
              <InformationCircleIcon className="h-5 w-5" />
            </button>

            {showTooltip && (
              <div className="absolute top-6 right-0 z-50 w-64 rounded-lg bg-zinc-900 p-3 text-xs text-white shadow-xl dark:bg-zinc-700">
                <div className="relative">
                  {description}
                  <div className="absolute -top-1 right-4 h-2 w-2 rotate-45 bg-zinc-900 dark:bg-zinc-700" />
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Score Value */}
      <div className={compact ? 'mb-2' : 'mb-3'}>
        <div
          className={`${compact ? 'text-2xl' : 'text-3xl'} font-bold tabular-nums ${colors.value}`}
        >
          {formatValue(value, formatAs, locale)}
        </div>
        {/* Sample size display (academic standard) */}
        {sampleSize !== undefined && (
          <div className={`text-xs ${colors.text} mt-1`}>
            {t('evaluation.scoreCard.sampleSize', {
              n: formatSampleSize(sampleSize),
            })}
            {clusterCount !== undefined && (
              <span className="text-zinc-500 dark:text-zinc-400">
                {' '}
                (
                {t('evaluation.scoreCard.clusters', {
                  count: formatSampleSize(clusterCount),
                })}
                )
              </span>
            )}
          </div>
        )}
        {/* Multi-run variance (migration 042). Hidden for single-run results
            to keep legacy displays clean. */}
        {runsAggregate && runsAggregate.runs > 1 && (
          <div className={`mt-1 text-xs ${colors.text}`}>
            ± {formatValue(runsAggregate.stdAcrossRuns, formatAs, locale)}{' '}
            <span className="text-zinc-500 dark:text-zinc-400">
              (
              {t('evaluation.scoreCard.acrossRuns', {
                n: runsAggregate.runs,
              })}
              )
            </span>
          </div>
        )}
      </div>

      {/* Confidence Interval */}
      {confidenceInterval && !compact && (
        <div className="space-y-2">
          <div className={`text-xs font-medium ${colors.text}`}>
            {t('evaluation.scoreCard.ciLabel', {
              level: confidenceInterval.level || 95,
            })}
            : [{formatValue(confidenceInterval.lower, formatAs, locale)},{' '}
            {formatValue(confidenceInterval.upper, formatAs, locale)}]
          </div>

          {/* Visual CI Bar */}
          <div className="relative h-2 rounded-full bg-zinc-200 dark:bg-zinc-700">
            {/* CI Range */}
            <div
              className={`absolute h-full rounded-full ${colors.indicator} opacity-30`}
              style={{
                left: `${((confidenceInterval.lower - valueRange.min) / (valueRange.max - valueRange.min)) * 100}%`,
                right: `${100 - ((confidenceInterval.upper - valueRange.min) / (valueRange.max - valueRange.min)) * 100}%`,
              }}
            />

            {/* Point Estimate */}
            <div
              className={`absolute top-1/2 h-3 w-1 -translate-y-1/2 rounded-full ${colors.indicator}`}
              style={{
                left: `${((value - valueRange.min) / (valueRange.max - valueRange.min)) * 100}%`,
              }}
            />
          </div>
        </div>
      )}

      {/* Compact CI display */}
      {confidenceInterval && compact && (
        <div className={`text-xs ${colors.text}`}>
          {t('evaluation.scoreCard.ciShort')}: [
          {formatValue(confidenceInterval.lower, formatAs, locale)},{' '}
          {formatValue(confidenceInterval.upper, formatAs, locale)}]
        </div>
      )}

      {/* Color Indicator Bar */}
      <div
        className={`${compact ? 'mt-2' : 'mt-3'} h-1 w-full rounded-full ${colors.indicator}`}
      />
    </div>
  )
}

/**
 * Helper to format scores according to academic standards
 * Per ACL/NeurIPS: 3 decimal places for 0-1 scores, no redundant dual display
 */
export function formatAcademicScore(
  value: number,
  options?: {
    asPercentage?: boolean
    decimals?: number
    /** UI language; falls back to the stored choice. */
    locale?: string
  },
): string {
  const locale = options?.locale ?? readStoredLocale()
  const decimals = options?.decimals ?? 3
  if (options?.asPercentage) {
    return `${formatDecimal(value * 100, locale, 1)}%`
  }
  return formatDecimal(value, locale, decimals)
}

/**
 * Metric Parameter Input Component
 *
 * Provides UI for configuring advanced metric parameters.
 * Supports BLEU, ROUGE, METEOR, and chrF metrics with their specific parameters.
 */

'use client'

import { Button } from '@/components/shared/Button'
import { Input } from '@/components/shared/Input'
import { Label } from '@/components/shared/Label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/shared/Select'
import { Tooltip } from '@/components/shared/Tooltip'
import { useI18n } from '@/contexts/I18nContext'
import {
  AdjustmentsHorizontalIcon,
  InformationCircleIcon,
} from '@heroicons/react/24/outline'
import { useState } from 'react'

interface MetricParameters {
  // BLEU parameters
  max_order?: number
  weights?: number[]
  smoothing?: string

  // ROUGE parameters
  variant?: string
  use_stemmer?: boolean

  // METEOR parameters
  alpha?: number
  beta?: number
  gamma?: number

  // chrF parameters
  char_order?: number
  word_order?: number
  // Note: chrF also uses 'beta' parameter, shared with METEOR
}

interface MetricParameterInputProps {
  metric: string
  parameters: MetricParameters
  onChange: (parameters: MetricParameters) => void
}

const METRIC_DEFAULTS: Record<string, MetricParameters> = {
  bleu: {
    max_order: 4,
    weights: [0.25, 0.25, 0.25, 0.25],
    smoothing: 'method1',
  },
  rouge: {
    variant: 'rougeL',
    use_stemmer: true,
  },
  meteor: {
    alpha: 0.9,
    beta: 3.0,
    gamma: 0.5,
  },
  chrf: {
    char_order: 6,
    word_order: 0,
    beta: 2,
  },
}

const PARAMETER_DESCRIPTIONS: Record<string, Record<string, string>> = {
  bleu: {
    max_order:
      'Highest n-gram order (1-4). Use 1 for very short texts, 4 for standard.',
    weights: 'Weight for each n-gram level. Must sum to 1.0.',
    smoothing:
      'Smoothing method for short sentences (method1, method2, method3, method4).',
  },
  rouge: {
    variant:
      'ROUGE variant (rouge1: unigrams, rouge2: bigrams, rougeL: LCS, rougeLsum: LCS summary-level).',
    use_stemmer:
      'Enable stemming to match word variations (e.g., "running" matches "run").',
  },
  meteor: {
    alpha:
      'Precision weight (0.0-1.0). Higher values favor precision over recall.',
    beta: 'Recall preference (positive). Higher values favor recall over precision.',
    gamma:
      'Fragmentation penalty (positive). Higher values penalize non-contiguous matches.',
  },
  chrf: {
    char_order:
      'Maximum character n-gram order (1-6). Use 6 for German/morphologically rich languages.',
    word_order: 'Maximum word n-gram order (0-2). 0=chrF, 2=chrF++.',
    beta: 'F-beta score parameter (1-3). 2=F2 (recall-weighted), 1=F1 (balanced).',
  },
}

const METRICS_WITH_PARAMETERS = ['bleu', 'rouge', 'meteor', 'chrf']

export function MetricParameterInput({
  metric,
  parameters,
  onChange,
}: MetricParameterInputProps) {
  const { t } = useI18n()
  const [showAdvanced, setShowAdvanced] = useState(false)

  // Check if this metric supports parameters
  if (!METRICS_WITH_PARAMETERS.includes(metric)) {
    return null
  }

  const defaults = METRIC_DEFAULTS[metric] || {}
  const descriptions = PARAMETER_DESCRIPTIONS[metric] || {}

  const handleParameterChange = (key: string, value: any) => {
    onChange({ ...parameters, [key]: value })
  }

  const resetToDefaults = () => {
    onChange(defaults)
  }

  return (
    <div className="mt-2 border-t border-gray-200 pt-2">
      <Button
        variant="text"
        onClick={() => setShowAdvanced(!showAdvanced)}
        className="flex items-center gap-1 p-0 text-xs text-blue-600 hover:text-blue-700"
      >
        <AdjustmentsHorizontalIcon className="h-3 w-3" />
        {showAdvanced ? t('evaluation.metricParams.hide') : t('evaluation.metricParams.show')} {t('evaluation.metricParams.advancedParameters')}
      </Button>

      {showAdvanced && (
        <div className="mt-3 space-y-3 rounded-md bg-gray-50 p-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-gray-700">
              {t('evaluation.metricParams.configure', { metric: metric.toUpperCase() })}
            </span>
            <Button
              variant="text"
              onClick={resetToDefaults}
              className="p-0 text-xs text-gray-600 hover:text-gray-700"
            >
              {t('evaluation.metricParams.resetToDefaults')}
            </Button>
          </div>

          {/* BLEU Parameters */}
          {metric === 'bleu' && (
            <>
              <div>
                <div className="flex items-center gap-1">
                  <Label htmlFor="max_order" className="text-xs">
                    {t('evaluation.metricParams.bleu.maxNgramOrder')}
                  </Label>
                  <Tooltip content={t('evaluation.metricParams.bleu.maxNgramOrderHelp')}>
                    <InformationCircleIcon className="h-3 w-3 text-gray-400" />
                  </Tooltip>
                </div>
                <Select
                  value={(parameters.max_order || defaults.max_order)?.toString() ?? '4'}
                  onValueChange={(v) => handleParameterChange('max_order', parseInt(v))}
                >
                  <SelectTrigger className="mt-1">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="1">{t('evaluation.metricParams.bleu.ngram1')}</SelectItem>
                    <SelectItem value="2">{t('evaluation.metricParams.bleu.ngram2')}</SelectItem>
                    <SelectItem value="3">{t('evaluation.metricParams.bleu.ngram3')}</SelectItem>
                    <SelectItem value="4">{t('evaluation.metricParams.bleu.ngram4')}</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div>
                <div className="flex items-center gap-1">
                  <Label htmlFor="smoothing" className="text-xs">
                    {t('evaluation.metricParams.bleu.smoothingMethod')}
                  </Label>
                  <Tooltip content={t('evaluation.metricParams.bleu.smoothingMethodHelp')}>
                    <InformationCircleIcon className="h-3 w-3 text-gray-400" />
                  </Tooltip>
                </div>
                <Select
                  value={(parameters.smoothing || defaults.smoothing) ?? 'method1'}
                  onValueChange={(v) => handleParameterChange('smoothing', v)}
                >
                  <SelectTrigger className="mt-1">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="method1">{t('evaluation.metricParams.bleu.smoothing1')}</SelectItem>
                    <SelectItem value="method2">{t('evaluation.metricParams.bleu.smoothing2')}</SelectItem>
                    <SelectItem value="method3">{t('evaluation.metricParams.bleu.smoothing3')}</SelectItem>
                    <SelectItem value="method4">{t('evaluation.metricParams.bleu.smoothing4')}</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </>
          )}

          {/* ROUGE Parameters */}
          {metric === 'rouge' && (
            <>
              <div>
                <div className="flex items-center gap-1">
                  <Label htmlFor="variant" className="text-xs">
                    {t('evaluation.metricParams.rouge.variant')}
                  </Label>
                  <Tooltip content={t('evaluation.metricParams.rouge.variantHelp')}>
                    <InformationCircleIcon className="h-3 w-3 text-gray-400" />
                  </Tooltip>
                </div>
                <Select
                  value={(parameters.variant || defaults.variant) ?? 'rougeL'}
                  onValueChange={(v) => handleParameterChange('variant', v)}
                >
                  <SelectTrigger className="mt-1">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="rouge1">{t('evaluation.metricParams.rouge.rouge1')}</SelectItem>
                    <SelectItem value="rouge2">{t('evaluation.metricParams.rouge.rouge2')}</SelectItem>
                    <SelectItem value="rougeL">{t('evaluation.metricParams.rouge.rougeL')}</SelectItem>
                    <SelectItem value="rougeLsum">
                      {t('evaluation.metricParams.rouge.rougeLsum')}
                    </SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div>
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={
                      parameters.use_stemmer ?? defaults.use_stemmer ?? true
                    }
                    onChange={(e) =>
                      handleParameterChange('use_stemmer', e.target.checked)
                    }
                    className="rounded border-gray-300"
                  />
                  <span className="text-xs">{t('evaluation.metricParams.rouge.enableStemming')}</span>
                  <Tooltip content={t('evaluation.metricParams.rouge.enableStemmingHelp')}>
                    <InformationCircleIcon className="h-3 w-3 text-gray-400" />
                  </Tooltip>
                </label>
              </div>
            </>
          )}

          {/* METEOR Parameters */}
          {metric === 'meteor' && (
            <>
              <div>
                <div className="flex items-center gap-1">
                  <Label htmlFor="alpha" className="text-xs">
                    {t('evaluation.metricParams.meteor.alpha')}
                  </Label>
                  <Tooltip content={t('evaluation.metricParams.meteor.alphaHelp')}>
                    <InformationCircleIcon className="h-3 w-3 text-gray-400" />
                  </Tooltip>
                </div>
                <Input
                  id="alpha"
                  type="number"
                  min="0"
                  max="1"
                  step="0.1"
                  value={parameters.alpha || defaults.alpha}
                  onChange={(e) =>
                    handleParameterChange('alpha', parseFloat(e.target.value))
                  }
                  className="mt-1 text-sm"
                />
              </div>

              <div>
                <div className="flex items-center gap-1">
                  <Label htmlFor="beta" className="text-xs">
                    {t('evaluation.metricParams.meteor.beta')}
                  </Label>
                  <Tooltip content={t('evaluation.metricParams.meteor.betaHelp')}>
                    <InformationCircleIcon className="h-3 w-3 text-gray-400" />
                  </Tooltip>
                </div>
                <Input
                  id="beta"
                  type="number"
                  min="0"
                  step="0.5"
                  value={parameters.beta || defaults.beta}
                  onChange={(e) =>
                    handleParameterChange('beta', parseFloat(e.target.value))
                  }
                  className="mt-1 text-sm"
                />
              </div>

              <div>
                <div className="flex items-center gap-1">
                  <Label htmlFor="gamma" className="text-xs">
                    {t('evaluation.metricParams.meteor.gamma')}
                  </Label>
                  <Tooltip content={t('evaluation.metricParams.meteor.gammaHelp')}>
                    <InformationCircleIcon className="h-3 w-3 text-gray-400" />
                  </Tooltip>
                </div>
                <Input
                  id="gamma"
                  type="number"
                  min="0"
                  step="0.1"
                  value={parameters.gamma || defaults.gamma}
                  onChange={(e) =>
                    handleParameterChange('gamma', parseFloat(e.target.value))
                  }
                  className="mt-1 text-sm"
                />
              </div>
            </>
          )}

          {/* chrF Parameters */}
          {metric === 'chrf' && (
            <>
              <div>
                <div className="flex items-center gap-1">
                  <Label htmlFor="char_order" className="text-xs">
                    {t('evaluation.metricParams.chrf.charOrder')}
                  </Label>
                  <Tooltip content={t('evaluation.metricParams.chrf.charOrderHelp')}>
                    <InformationCircleIcon className="h-3 w-3 text-gray-400" />
                  </Tooltip>
                </div>
                <Select
                  value={(parameters.char_order || defaults.char_order)?.toString() ?? '6'}
                  onValueChange={(v) => handleParameterChange('char_order', parseInt(v))}
                >
                  <SelectTrigger className="mt-1">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="1">1</SelectItem>
                    <SelectItem value="2">2</SelectItem>
                    <SelectItem value="3">3</SelectItem>
                    <SelectItem value="4">4</SelectItem>
                    <SelectItem value="5">5</SelectItem>
                    <SelectItem value="6">{t('evaluation.metricParams.chrf.charOrder6')}</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div>
                <div className="flex items-center gap-1">
                  <Label htmlFor="word_order" className="text-xs">
                    {t('evaluation.metricParams.chrf.wordOrder')}
                  </Label>
                  <Tooltip content={t('evaluation.metricParams.chrf.wordOrderHelp')}>
                    <InformationCircleIcon className="h-3 w-3 text-gray-400" />
                  </Tooltip>
                </div>
                <Select
                  value={(parameters.word_order ?? defaults.word_order)?.toString() ?? '0'}
                  onValueChange={(v) => handleParameterChange('word_order', parseInt(v))}
                >
                  <SelectTrigger className="mt-1">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="0">{t('evaluation.metricParams.chrf.wordOrder0')}</SelectItem>
                    <SelectItem value="1">{t('evaluation.metricParams.chrf.wordOrder1')}</SelectItem>
                    <SelectItem value="2">{t('evaluation.metricParams.chrf.wordOrder2')}</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div>
                <div className="flex items-center gap-1">
                  <Label htmlFor="beta_chrf" className="text-xs">
                    {t('evaluation.metricParams.chrf.beta')}
                  </Label>
                  <Tooltip content={t('evaluation.metricParams.chrf.betaHelp')}>
                    <InformationCircleIcon className="h-3 w-3 text-gray-400" />
                  </Tooltip>
                </div>
                <Select
                  value={(parameters.beta || defaults.beta)?.toString() ?? '2'}
                  onValueChange={(v) => handleParameterChange('beta', parseInt(v))}
                >
                  <SelectTrigger className="mt-1">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="1">{t('evaluation.metricParams.chrf.beta1')}</SelectItem>
                    <SelectItem value="2">
                      {t('evaluation.metricParams.chrf.beta2')}
                    </SelectItem>
                    <SelectItem value="3">{t('evaluation.metricParams.chrf.beta3')}</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  )
}

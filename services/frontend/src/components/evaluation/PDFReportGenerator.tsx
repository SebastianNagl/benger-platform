/**
 * PDF Report Generator Component
 *
 * Publication-quality PDF export with customizable content sections.
 * Supports academic and business report formats with embedded charts,
 * statistical tables, and methodology disclosure.
 */

'use client'

import { Button } from '@/components/shared/Button'
import { Card } from '@/components/shared/Card'
import { Checkbox } from '@/components/shared/Checkbox'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/shared/Select'
import { useI18n } from '@/contexts/I18nContext'
import { formatDecimal, intlTag } from '@/lib/i18n/locales'
import { cn } from '@/lib/utils'
import { DocumentArrowDownIcon } from '@heroicons/react/24/outline'
import html2canvas from 'html2canvas'
import jsPDF from 'jspdf'
import { useRef, useState } from 'react'

export interface PDFReportOptions {
  includeCharts: boolean
  includeTables: boolean
  includeStatistics: boolean
  selectedModels: string[]
  selectedMetrics: string[]
  format: 'academic' | 'business'
}

interface ModelData {
  model_id: string
  model_name: string
  provider: string
  metrics: Record<string, number>
  ci_lower?: number
  ci_upper?: number
}

interface SignificanceTest {
  model_a: string
  model_b: string
  p_value: number
  significant: boolean
  effect_size: number
}

export interface PDFReportGeneratorProps {
  projectId: string
  projectName: string
  evaluationData: {
    models: ModelData[]
    significanceTests?: SignificanceTest[]
  }
  onGenerate?: () => void
}

const METRIC_CITATIONS: Record<string, string> = {
  bertscore:
    'Zhang et al. (2020) - BERTScore: Evaluating Text Generation with BERT',
  moverscore:
    'Zhao et al. (2019) - MoverScore: Text Generation Evaluating with Contextualized Embeddings',
  summac:
    'Laban et al. (2022) - SummaC: Re-Visiting NLI-based Models for Inconsistency Detection',
  factcc:
    'Kryscinski et al. (2020) - Evaluating the Factual Consistency of Abstractive Text Summarization',
  qags: 'Wang et al. (2020) - Asking and Answering Questions to Evaluate the Factual Consistency of Summaries',
  coherence:
    'Barzilay & Lapata (2008) - Modeling Local Coherence: An Entity-based Approach',
  rouge: 'Lin (2004) - ROUGE: A Package for Automatic Evaluation of Summaries',
  bleu: 'Papineni et al. (2002) - BLEU: A Method for Automatic Evaluation of Machine Translation',
  meteor:
    'Banerjee & Lavie (2005) - METEOR: An Automatic Metric for MT Evaluation',
}

export function PDFReportGenerator({
  projectId,
  projectName,
  evaluationData,
  onGenerate,
}: PDFReportGeneratorProps) {
  const [options, setOptions] = useState<PDFReportOptions>({
    includeCharts: true,
    includeTables: true,
    includeStatistics: true,
    selectedModels: evaluationData.models.map((m) => m.model_id),
    selectedMetrics: Array.from(
      new Set(
        evaluationData.models.flatMap((m) => Object.keys(m.metrics || {})),
      ),
    ),
    format: 'academic',
  })
  const { t, locale } = useI18n()
  const [isGenerating, setIsGenerating] = useState(false)
  const previewRef = useRef<HTMLDivElement>(null)

  const availableModels = evaluationData.models.map((m) => ({
    id: m.model_id,
    name: m.model_name || m.model_id,
  }))

  const availableMetrics = Array.from(
    new Set(evaluationData.models.flatMap((m) => Object.keys(m.metrics))),
  ).sort()

  const filteredModels = evaluationData.models.filter((m) =>
    options.selectedModels.includes(m.model_id),
  )

  const filteredMetrics = options.selectedMetrics

  const handleToggleModel = (modelId: string) => {
    setOptions((prev) => ({
      ...prev,
      selectedModels: prev.selectedModels.includes(modelId)
        ? prev.selectedModels.filter((id) => id !== modelId)
        : [...prev.selectedModels, modelId],
    }))
  }

  const handleToggleMetric = (metric: string) => {
    setOptions((prev) => ({
      ...prev,
      selectedMetrics: prev.selectedMetrics.includes(metric)
        ? prev.selectedMetrics.filter((m) => m !== metric)
        : [...prev.selectedMetrics, metric],
    }))
  }

  const handleGeneratePDF = async () => {
    if (!previewRef.current) return

    setIsGenerating(true)
    try {
      const canvas = await html2canvas(previewRef.current, {
        scale: 2,
        backgroundColor: '#ffffff',
        logging: false,
        windowWidth: 1200,
      })

      const imgData = canvas.toDataURL('image/png')
      const pdf = new jsPDF({
        orientation: 'portrait',
        unit: 'mm',
        format: 'a4',
      })

      const pageWidth = pdf.internal.pageSize.getWidth()
      const pageHeight = pdf.internal.pageSize.getHeight()
      const margin = 15
      const contentWidth = pageWidth - 2 * margin
      const imgWidth = contentWidth
      const imgHeight = (canvas.height * imgWidth) / canvas.width

      let heightLeft = imgHeight
      let position = margin

      pdf.addImage(imgData, 'PNG', margin, position, imgWidth, imgHeight)
      heightLeft -= pageHeight - 2 * margin

      while (heightLeft > 0) {
        position = heightLeft - imgHeight + margin
        pdf.addPage()
        pdf.addImage(imgData, 'PNG', margin, position, imgWidth, imgHeight)
        heightLeft -= pageHeight - 2 * margin
      }

      const filename = `${projectName.replace(/\s+/g, '-')}-evaluation-report-${options.format}.pdf`
      pdf.save(filename)

      onGenerate?.()
    } catch (error) {
      console.error('PDF generation failed:', error)
    } finally {
      setIsGenerating(false)
    }
  }

  const getModelRanking = () => {
    const modelScores = filteredModels.map((model) => {
      const scores = filteredMetrics.map((metric) => model.metrics[metric] || 0)
      const avgScore = scores.reduce((a, b) => a + b, 0) / scores.length
      return { model, avgScore }
    })
    return modelScores.sort((a, b) => b.avgScore - a.avgScore)
  }

  const rankedModels = getModelRanking()

  const formatMetricValue = (value: number): string => {
    if (value >= 0 && value <= 1) {
      return formatDecimal(value * 100, locale, 2) + '%'
    }
    return formatDecimal(value, locale, 4)
  }

  return (
    <div className="space-y-6">
      {/* Options Panel */}
      <Card className="p-6">
        <h3 className="mb-4 text-lg font-semibold text-zinc-900 dark:text-zinc-100">
          {t('evaluation.pdfReport.configTitle')}
        </h3>

        <div className="space-y-6">
          {/* Format Selection */}
          <div>
            <label className="mb-2 block text-sm font-medium text-zinc-700 dark:text-zinc-300">
              {t('evaluation.pdfReport.reportFormat')}
            </label>
            <Select
              value={options.format}
              onValueChange={(value) =>
                setOptions((prev) => ({
                  ...prev,
                  format: value as 'academic' | 'business',
                }))
              }
            >
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="academic">
                  {t('evaluation.pdfReport.academicFormat')}
                </SelectItem>
                <SelectItem value="business">
                  {t('evaluation.pdfReport.businessFormat')}
                </SelectItem>
              </SelectContent>
            </Select>
            <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
              {options.format === 'academic'
                ? t('evaluation.pdfReport.academicDescription')
                : t('evaluation.pdfReport.businessDescription')}
            </p>
          </div>

          {/* Content Sections */}
          <div>
            <label className="mb-2 block text-sm font-medium text-zinc-700 dark:text-zinc-300">
              {t('evaluation.pdfReport.includeSections')}
            </label>
            <div className="space-y-2">
              <Checkbox
                id="include-tables"
                label={t('evaluation.pdfReport.resultsTables')}
                checked={options.includeTables}
                onChange={(e) =>
                  setOptions((prev) => ({
                    ...prev,
                    includeTables: e.target.checked,
                  }))
                }
              />
              <Checkbox
                id="include-charts"
                label={t('evaluation.pdfReport.visualizations')}
                checked={options.includeCharts}
                onChange={(e) =>
                  setOptions((prev) => ({
                    ...prev,
                    includeCharts: e.target.checked,
                  }))
                }
              />
              <Checkbox
                id="include-statistics"
                label={t('evaluation.pdfReport.statisticalAnalysis')}
                checked={options.includeStatistics}
                onChange={(e) =>
                  setOptions((prev) => ({
                    ...prev,
                    includeStatistics: e.target.checked,
                  }))
                }
              />
            </div>
          </div>

          {/* Model Selection */}
          <div>
            <label className="mb-2 block text-sm font-medium text-zinc-700 dark:text-zinc-300">
              {t('evaluation.pdfReport.selectModels')}
            </label>
            <div className="max-h-32 space-y-2 overflow-y-auto rounded border border-zinc-200 p-3 dark:border-zinc-700">
              {availableModels.map((model) => (
                <Checkbox
                  key={model.id}
                  id={`model-${model.id}`}
                  label={model.name}
                  checked={options.selectedModels.includes(model.id)}
                  onChange={() => handleToggleModel(model.id)}
                />
              ))}
            </div>
          </div>

          {/* Metric Selection */}
          <div>
            <label className="mb-2 block text-sm font-medium text-zinc-700 dark:text-zinc-300">
              {t('evaluation.pdfReport.selectMetrics')}
            </label>
            <div className="max-h-32 space-y-2 overflow-y-auto rounded border border-zinc-200 p-3 dark:border-zinc-700">
              {availableMetrics.map((metric) => (
                <Checkbox
                  key={metric}
                  id={`metric-${metric}`}
                  label={metric}
                  checked={options.selectedMetrics.includes(metric)}
                  onChange={() => handleToggleMetric(metric)}
                />
              ))}
            </div>
          </div>

          {/* Generate Button */}
          <div className="flex items-center justify-between border-t pt-4 dark:border-zinc-700">
            <div className="text-sm text-zinc-600 dark:text-zinc-400">
              {t('evaluation.pdfReport.selectionSummary', {
                models: options.selectedModels.length,
                metrics: options.selectedMetrics.length,
              })}
            </div>
            <Button
              variant="primary"
              onClick={handleGeneratePDF}
              disabled={
                isGenerating ||
                options.selectedModels.length === 0 ||
                options.selectedMetrics.length === 0
              }
            >
              <DocumentArrowDownIcon className="h-5 w-5" />
              {isGenerating
                ? t('evaluation.pdfReport.generating')
                : t('evaluation.pdfReport.generatePdf')}
            </Button>
          </div>
        </div>
      </Card>

      {/* Preview Section */}
      <div className="rounded-lg border border-zinc-200 bg-zinc-50 p-4 dark:border-zinc-700 dark:bg-zinc-800">
        <h3 className="mb-4 text-sm font-medium text-zinc-700 dark:text-zinc-300">
          {t('evaluation.pdfReport.previewTitle')}
        </h3>
        <div
          ref={previewRef}
          className="mx-auto max-w-4xl rounded-lg bg-white p-8 shadow-sm dark:bg-zinc-900"
          style={{ minHeight: '400px' }}
        >
          {/* Header */}
          <div className="mb-8 border-b pb-6 dark:border-zinc-700">
            <h1 className="text-3xl font-bold text-zinc-900 dark:text-zinc-100">
              {t('evaluation.pdfReport.reportTitle', { project: projectName })}
            </h1>
            <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
              {t('evaluation.pdfReport.generatedOn')}{' '}
              {new Date().toLocaleDateString(intlTag(locale), {
                year: 'numeric',
                month: 'long',
                day: 'numeric',
              })}
            </p>
            <p className="text-sm text-zinc-600 dark:text-zinc-400">
              {t('evaluation.pdfReport.format')}{' '}
              {options.format === 'academic'
                ? t('evaluation.pdfReport.academicFormat')
                : t('evaluation.pdfReport.businessFormat')}
            </p>
          </div>

          {/* Executive Summary */}
          <div className="mb-8">
            <h2 className="mb-4 text-xl font-bold text-zinc-900 dark:text-zinc-100">
              {t('evaluation.pdfReport.executiveSummary')}
            </h2>
            <div className="space-y-3 text-sm text-zinc-700 dark:text-zinc-300">
              <p>
                {t('evaluation.pdfReport.summaryIntro', {
                  models: filteredModels.length,
                  metrics: filteredMetrics.length,
                })}
              </p>
              <div className="rounded-lg border border-zinc-200 bg-zinc-50 p-4 dark:border-zinc-700 dark:bg-zinc-800/50">
                <h3 className="mb-2 font-semibold text-zinc-900 dark:text-white">
                  {t('evaluation.pdfReport.topPerformingModel')}
                </h3>
                {rankedModels.length > 0 && (
                  <div>
                    <p className="text-zinc-700 dark:text-zinc-300">
                      <span className="font-bold">
                        {rankedModels[0].model.model_name}
                      </span>{' '}
                      ({rankedModels[0].model.provider})
                    </p>
                    <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
                      {t('evaluation.pdfReport.averageScore')}{' '}
                      {formatMetricValue(rankedModels[0].avgScore)}
                    </p>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Methodology (Academic Format Only) */}
          {options.format === 'academic' && (
            <div className="mb-8">
              <h2 className="mb-4 text-xl font-bold text-zinc-900 dark:text-zinc-100">
                {t('evaluation.pdfReport.methodology')}
              </h2>
              <div className="space-y-3 text-sm text-zinc-700 dark:text-zinc-300">
                <div>
                  <h3 className="mb-2 font-semibold text-zinc-800 dark:text-zinc-200">
                    {t('evaluation.pdfReport.evaluationMetrics')}
                  </h3>
                  <p className="mb-2">
                    {t('evaluation.pdfReport.metricsEmployed')}
                  </p>
                  <ul className="ml-6 list-disc space-y-1">
                    {filteredMetrics.map((metric) => (
                      <li key={metric}>
                        <span className="font-medium">{metric}</span>
                        {METRIC_CITATIONS[metric] && (
                          <span className="ml-1 text-xs text-zinc-600 dark:text-zinc-400">
                            ({METRIC_CITATIONS[metric]})
                          </span>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
                <div>
                  <h3 className="mb-2 font-semibold text-zinc-800 dark:text-zinc-200">
                    {t('evaluation.pdfReport.statisticalAnalysisSection')}
                  </h3>
                  <p>{t('evaluation.pdfReport.statisticalMethodology')}</p>
                </div>
              </div>
            </div>
          )}

          {/* Results Table */}
          {options.includeTables && (
            <div className="mb-8">
              <h2 className="mb-4 text-xl font-bold text-zinc-900 dark:text-zinc-100">
                {t('evaluation.pdfReport.results')}
              </h2>
              <div className="overflow-x-auto">
                <table className="w-full border-collapse text-sm">
                  <thead>
                    <tr className="border-b-2 border-zinc-300 dark:border-zinc-600">
                      <th className="px-4 py-3 text-left font-semibold text-zinc-800 dark:text-zinc-200">
                        {t('evaluation.pdfReport.rank')}
                      </th>
                      <th className="px-4 py-3 text-left font-semibold text-zinc-800 dark:text-zinc-200">
                        {t('evaluation.pdfReport.model')}
                      </th>
                      {filteredMetrics.map((metric) => (
                        <th
                          key={metric}
                          className="px-4 py-3 text-center font-semibold text-zinc-800 dark:text-zinc-200"
                        >
                          {metric}
                        </th>
                      ))}
                      <th className="px-4 py-3 text-center font-semibold text-zinc-800 dark:text-zinc-200">
                        {t('evaluation.pdfReport.average')}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {rankedModels.map((item, idx) => (
                      <tr
                        key={item.model.model_id}
                        className={cn(
                          'border-b border-zinc-200 dark:border-zinc-700',
                          idx % 2 === 0
                            ? 'bg-zinc-50 dark:bg-zinc-800'
                            : 'bg-white dark:bg-zinc-900',
                        )}
                      >
                        <td className="px-4 py-3 font-medium text-zinc-900 dark:text-zinc-100">
                          #{idx + 1}
                        </td>
                        <td className="px-4 py-3 font-medium text-zinc-900 dark:text-zinc-100">
                          <div>{item.model.model_name}</div>
                          <div className="text-xs text-zinc-500 dark:text-zinc-400">
                            {item.model.provider}
                          </div>
                        </td>
                        {filteredMetrics.map((metric) => {
                          const value = item.model.metrics[metric]
                          return (
                            <td
                              key={metric}
                              className="px-4 py-3 text-center text-zinc-700 tabular-nums dark:text-zinc-300"
                            >
                              {value !== undefined
                                ? formatMetricValue(value)
                                : 'N/A'}
                            </td>
                          )
                        })}
                        <td className="px-4 py-3 text-center font-bold text-zinc-900 tabular-nums dark:text-zinc-100">
                          {formatMetricValue(item.avgScore)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Statistical Significance */}
          {options.includeStatistics &&
            evaluationData.significanceTests &&
            evaluationData.significanceTests.length > 0 && (
              <div className="mb-8">
                <h2 className="mb-4 text-xl font-bold text-zinc-900 dark:text-zinc-100">
                  {t('evaluation.pdfReport.statisticalSignificance')}
                </h2>
                <div className="overflow-x-auto">
                  <table className="w-full border-collapse text-sm">
                    <thead>
                      <tr className="border-b-2 border-zinc-300 dark:border-zinc-600">
                        <th className="px-4 py-3 text-left font-semibold text-zinc-800 dark:text-zinc-200">
                          {t('evaluation.pdfReport.comparison')}
                        </th>
                        <th className="px-4 py-3 text-center font-semibold text-zinc-800 dark:text-zinc-200">
                          {t('evaluation.pdfReport.pValue')}
                        </th>
                        <th className="px-4 py-3 text-center font-semibold text-zinc-800 dark:text-zinc-200">
                          {t('evaluation.pdfReport.significant')}
                        </th>
                        <th className="px-4 py-3 text-center font-semibold text-zinc-800 dark:text-zinc-200">
                          {t('evaluation.pdfReport.effectSize')}
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {evaluationData.significanceTests.map((test, idx) => (
                        <tr
                          key={idx}
                          className={cn(
                            'border-b border-zinc-200 dark:border-zinc-700',
                            idx % 2 === 0
                              ? 'bg-zinc-50 dark:bg-zinc-800'
                              : 'bg-white dark:bg-zinc-900',
                          )}
                        >
                          <td className="px-4 py-3 text-zinc-700 dark:text-zinc-300">
                            {t('evaluation.pdfReport.versus', {
                              a: test.model_a,
                              b: test.model_b,
                            })}
                          </td>
                          <td className="px-4 py-3 text-center text-zinc-700 tabular-nums dark:text-zinc-300">
                            {formatDecimal(test.p_value, locale, 4)}
                          </td>
                          <td className="px-4 py-3 text-center">
                            <span
                              className={cn(
                                'inline-flex rounded-full px-2 py-1 text-xs font-medium',
                                test.significant
                                  ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-200'
                                  : 'bg-zinc-100 text-zinc-800 dark:bg-zinc-700 dark:text-zinc-200',
                              )}
                            >
                              {test.significant
                                ? t('common.yes')
                                : t('common.no')}
                            </span>
                          </td>
                          <td className="px-4 py-3 text-center text-zinc-700 tabular-nums dark:text-zinc-300">
                            {formatDecimal(test.effect_size, locale, 3)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

          {/* Model Performance Summary */}
          {options.includeCharts && (
            <div className="mb-8">
              <h2 className="mb-4 text-xl font-bold text-zinc-900 dark:text-zinc-100">
                {t('evaluation.pdfReport.performanceSummary')}
              </h2>
              <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
                <div className="rounded-lg border border-zinc-200 bg-zinc-50 p-4 text-center dark:border-zinc-700 dark:bg-zinc-800">
                  <div className="text-2xl font-bold text-zinc-900 dark:text-zinc-100">
                    {filteredModels.length}
                  </div>
                  <div className="text-sm text-zinc-600 dark:text-zinc-400">
                    {t('evaluation.pdfReport.modelsEvaluated')}
                  </div>
                </div>
                <div className="rounded-lg border border-zinc-200 bg-zinc-50 p-4 text-center dark:border-zinc-700 dark:bg-zinc-800">
                  <div className="text-2xl font-bold text-zinc-900 dark:text-zinc-100">
                    {filteredMetrics.length}
                  </div>
                  <div className="text-sm text-zinc-600 dark:text-zinc-400">
                    {t('evaluation.pdfReport.metricsComputed')}
                  </div>
                </div>
                <div className="rounded-lg border border-zinc-200 bg-zinc-50 p-4 text-center dark:border-zinc-700 dark:bg-zinc-800">
                  <div className="text-2xl font-bold text-zinc-900 dark:text-zinc-100">
                    {rankedModels.length > 0
                      ? formatMetricValue(rankedModels[0].avgScore)
                      : 'N/A'}
                  </div>
                  <div className="text-sm text-zinc-600 dark:text-zinc-400">
                    {t('evaluation.pdfReport.bestScore')}
                  </div>
                </div>
                <div className="rounded-lg border border-zinc-200 bg-zinc-50 p-4 text-center dark:border-zinc-700 dark:bg-zinc-800">
                  <div className="text-2xl font-bold text-zinc-900 dark:text-zinc-100">
                    {rankedModels.length > 0
                      ? formatMetricValue(
                          rankedModels.reduce(
                            (sum, item) => sum + item.avgScore,
                            0,
                          ) / rankedModels.length,
                        )
                      : 'N/A'}
                  </div>
                  <div className="text-sm text-zinc-600 dark:text-zinc-400">
                    {t('evaluation.pdfReport.averageScore')}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Footer */}
          <div className="border-t pt-6 text-xs text-zinc-500 dark:border-zinc-700 dark:text-zinc-400">
            <p>
              {t('evaluation.pdfReport.footerGenerated')}{' '}
              {new Date().toLocaleString(intlTag(locale))}
            </p>
            {options.format === 'academic' && (
              <p className="mt-2">
                {t('evaluation.pdfReport.academicDisclaimer')}
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

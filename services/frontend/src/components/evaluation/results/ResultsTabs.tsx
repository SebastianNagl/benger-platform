/**
 * ResultsTabs — the per-tab content panels of the result-details modal
 * (annotation / generation / evaluation). Pure presentational block
 * extracted verbatim from EvaluationResults.tsx's `ResultDetailsModal`.
 *
 * The tab *bar* stays in the modal (it owns `activeTab` and sits in the
 * modal header region); this component renders the *body* for the active
 * tab. Output is byte-identical to the inline version — moving this JSX
 * into a child that renders the same markup must not change anything the
 * tests assert on.
 */

'use client'

import { LoadingSpinner } from '@/components/shared/LoadingSpinner'
import { useI18n } from '@/contexts/I18nContext'
import { getMetricDetail } from '@/lib/extensions/metricRenderers'

import type {
  AnnotationData,
  EvaluationDetailData,
  GenerationData,
} from './types'

interface ResultsTabsProps {
  activeTab: 'annotation' | 'generation' | 'evaluation'
  annotationData: AnnotationData | null
  generationData: GenerationData | null
  evaluationData: EvaluationDetailData | null
  annotationLoading: boolean
  generationLoading: boolean
  evaluationLoading: boolean
  selectedStructureIndex: number
  setSelectedStructureIndex: (index: number) => void
  /** Filters Evaluation Results tab to rows for this metric only. */
  selectedMetricName?: string | null
}

// Format metric value for display
const formatMetricValue = (value: any): string => {
  if (value === null || value === undefined) {
    return 'N/A'
  }
  if (typeof value === 'number') {
    return value.toFixed(3)
  }
  if (typeof value === 'string') {
    return value
  }
  return JSON.stringify(value)
}

export function ResultsTabs({
  activeTab,
  annotationData,
  generationData,
  evaluationData,
  annotationLoading,
  generationLoading,
  evaluationLoading,
  selectedStructureIndex,
  setSelectedStructureIndex,
  selectedMetricName = null,
}: ResultsTabsProps) {
  const { t } = useI18n()

  return (
    <>
      {activeTab === 'annotation' ? (
        // Annotation Result Tab
        annotationLoading ? (
          <div className="flex items-center justify-center py-12">
            <LoadingSpinner />
          </div>
        ) : annotationData && annotationData.length > 0 ? (
          <div className="space-y-6">
            {annotationData.map((annotation, annIndex) => (
              <div key={annotation.id} className="rounded-lg border border-zinc-200 p-4 dark:border-zinc-700">
                {/* Annotation Header */}
                <div className="mb-4 flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${
                      annotation.ground_truth
                        ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/20 dark:text-emerald-400'
                        : 'bg-zinc-100 text-zinc-800 dark:bg-zinc-800 dark:text-zinc-300'
                    }`}>
                      {annotation.ground_truth ? t('evaluation.multiFieldResults.groundTruth', 'Ground Truth') : t('evaluation.multiFieldResults.annotation', 'Annotation')}
                    </span>
                    <span className="text-sm text-zinc-600 dark:text-zinc-400">
                      {t('evaluation.multiFieldResults.annotator', 'Annotator')}: {annotation.completed_by}
                    </span>
                  </div>
                  <span className="text-xs text-zinc-500 dark:text-zinc-400">
                    {new Date(annotation.created_at).toLocaleString()}
                  </span>
                </div>

                {/* Annotation Results */}
                {annotation.result && annotation.result.length > 0 ? (
                  <div className="space-y-3">
                    {annotation.result.map((res, resIndex) => (
                      <div key={resIndex} className="rounded-lg bg-zinc-50 p-3 dark:bg-zinc-800">
                        <div className="mb-1 flex items-center gap-2">
                          <span className="text-xs font-medium text-zinc-500 dark:text-zinc-400">
                            {res.from_name}
                          </span>
                          <span className="text-xs text-zinc-400 dark:text-zinc-500">
                            ({res.type})
                          </span>
                        </div>
                        <div className="text-sm text-zinc-900 dark:text-white">
                          {typeof res.value === 'string' ? (
                            <p className="whitespace-pre-wrap">{res.value}</p>
                          ) : (
                            <pre className="whitespace-pre-wrap text-xs">
                              {JSON.stringify(res.value, null, 2)}
                            </pre>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-zinc-500 dark:text-zinc-400">
                    {t('evaluation.multiFieldResults.noAnnotationResults', 'No annotation results')}
                  </p>
                )}

                {/* Metadata */}
                <div className="mt-4 grid grid-cols-2 gap-4 text-sm">
                  {annotation.lead_time != null && (
                    <div className="rounded-lg bg-zinc-50 p-3 dark:bg-zinc-800">
                      <span className="text-zinc-500 dark:text-zinc-400">{t('evaluation.multiFieldResults.duration')}:</span>
                      <span className="ml-2 text-zinc-900 dark:text-white">
                        {annotation.lead_time.toFixed(1)}s
                      </span>
                    </div>
                  )}
                  {annotation.was_cancelled && (
                    <div className="rounded-lg bg-red-50 p-3 dark:bg-red-900/20">
                      <span className="text-red-700 dark:text-red-300">{t('evaluation.multiFieldResults.cancelled', 'Cancelled')}</span>
                    </div>
                  )}
                </div>
              </div>
            ))}

            {/* Full JSON Section (collapsed) */}
            <details className="group">
              <summary className="cursor-pointer font-medium text-zinc-900 dark:text-white">
                {t('evaluation.multiFieldResults.rawJsonResponse')}
              </summary>
              <div className="mt-2 rounded-lg bg-zinc-50 p-4 dark:bg-zinc-800">
                <pre className="overflow-x-auto text-xs text-zinc-700 dark:text-zinc-300">
                  {JSON.stringify(annotationData, null, 2)}
                </pre>
              </div>
            </details>
          </div>
        ) : (
          <div className="py-12 text-center text-zinc-500 dark:text-zinc-400">
            {t('evaluation.multiFieldResults.noAnnotationData', 'No annotation data available for this task')}
          </div>
        )
      ) : activeTab === 'generation' ? (
        // Generation Results Tab
        generationLoading ? (
          <div className="flex items-center justify-center py-12">
            <LoadingSpinner />
          </div>
        ) : generationData && generationData.length > 0 ? (
          <div className="space-y-6">
            {/* Structure Tabs (if multiple structures) */}
            {generationData.length > 1 && (
              <div className="border-b border-zinc-200 dark:border-zinc-700">
                <nav className="-mb-px flex space-x-4">
                  {generationData.map((result, index) => (
                    <button
                      key={index}
                      onClick={() => setSelectedStructureIndex(index)}
                      className={`whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium ${
                        selectedStructureIndex === index
                          ? 'border-emerald-500 text-emerald-600 dark:text-emerald-400'
                          : 'border-transparent text-zinc-500 hover:border-zinc-300 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-300'
                      }`}
                    >
                      {result.structure_key || t('evaluation.multiFieldResults.default')}
                    </button>
                  ))}
                </nav>
              </div>
            )}

            {/* Selected Structure Content */}
            {(() => {
              const selectedGen = generationData[selectedStructureIndex]
              if (!selectedGen) return null
              return (
                <>
                  {/* Generated Text Section */}
                  {selectedGen.result?.generated_text && (
                    <div>
                      <h4 className="mb-2 font-medium text-zinc-900 dark:text-white">
                        {t('evaluation.multiFieldResults.generatedResponse')}
                      </h4>
                      <div className="rounded-lg bg-zinc-50 p-4 dark:bg-zinc-800">
                        <pre className="whitespace-pre-wrap text-sm text-zinc-700 dark:text-zinc-300">
                          {selectedGen.result.generated_text}
                        </pre>
                      </div>
                    </div>
                  )}

                  {/* Fields Section (for structured outputs) */}
                  {selectedGen.result?.fields && Object.keys(selectedGen.result.fields).length > 0 && (
                    <div>
                      <h4 className="mb-2 font-medium text-zinc-900 dark:text-white">
                        {t('evaluation.multiFieldResults.generatedFields')}
                      </h4>
                      <div className="rounded-lg bg-zinc-50 p-4 dark:bg-zinc-800">
                        <pre className="whitespace-pre-wrap text-sm text-zinc-700 dark:text-zinc-300">
                          {JSON.stringify(selectedGen.result.fields, null, 2)}
                        </pre>
                      </div>
                    </div>
                  )}

                  {/* Prompt Used Section */}
                  {selectedGen.prompt_used && (
                    <div>
                      <h4 className="mb-2 font-medium text-zinc-900 dark:text-white">
                        {t('evaluation.multiFieldResults.promptUsed')}
                      </h4>
                      <div className="rounded-lg bg-blue-50 p-4 dark:bg-blue-900/20">
                        <pre className="whitespace-pre-wrap text-sm text-blue-800 dark:text-blue-200">
                          {selectedGen.prompt_used}
                        </pre>
                      </div>
                    </div>
                  )}

                  {/* Metadata Section */}
                  <div>
                    <h4 className="mb-2 font-medium text-zinc-900 dark:text-white">
                      {t('evaluation.multiFieldResults.metadata')}
                    </h4>
                    <div className="grid grid-cols-2 gap-4 text-sm">
                      <div className="rounded-lg bg-zinc-50 p-3 dark:bg-zinc-800">
                        <span className="text-zinc-500 dark:text-zinc-400">{t('evaluation.multiFieldResults.statusLabel')}:</span>
                        <span className="ml-2 text-zinc-900 dark:text-white">
                          {selectedGen.status}
                        </span>
                      </div>
                      {selectedGen.generated_at && (
                        <div className="rounded-lg bg-zinc-50 p-3 dark:bg-zinc-800">
                          <span className="text-zinc-500 dark:text-zinc-400">{t('evaluation.multiFieldResults.generated')}:</span>
                          <span className="ml-2 text-zinc-900 dark:text-white">
                            {new Date(selectedGen.generated_at).toLocaleString()}
                          </span>
                        </div>
                      )}
                      {selectedGen.generation_time_seconds != null && (
                        <div className="rounded-lg bg-zinc-50 p-3 dark:bg-zinc-800">
                          <span className="text-zinc-500 dark:text-zinc-400">{t('evaluation.multiFieldResults.duration')}:</span>
                          <span className="ml-2 text-zinc-900 dark:text-white">
                            {selectedGen.generation_time_seconds.toFixed(2)}s
                          </span>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Full JSON Section (collapsed) */}
                  <details className="group">
                    <summary className="cursor-pointer font-medium text-zinc-900 dark:text-white">
                      {t('evaluation.multiFieldResults.rawJsonResponse')}
                    </summary>
                    <div className="mt-2 rounded-lg bg-zinc-50 p-4 dark:bg-zinc-800">
                      <pre className="overflow-x-auto text-xs text-zinc-700 dark:text-zinc-300">
                        {JSON.stringify(selectedGen, null, 2)}
                      </pre>
                    </div>
                  </details>
                </>
              )
            })()}
          </div>
        ) : (
          <div className="py-12 text-center text-zinc-500 dark:text-zinc-400">
            {t('evaluation.multiFieldResults.noGenerationData')}
          </div>
        )
      ) : (
        // Evaluation Results Tab
        evaluationLoading ? (
          <div className="flex items-center justify-center py-12">
            <LoadingSpinner />
          </div>
        ) : evaluationData && evaluationData.results.length > 0 ? (() => {
          // Filter to entries for the currently-selected metric.
          // field_name shape from worker: "<metric>-<slug>|<pred>|<ref>"
          // (see tasks.py: field_key = f"{config_id}|...", config_id = "{metric}-{slug}")
          const visibleResults = selectedMetricName
            ? evaluationData.results.filter((r) => {
                const fieldMetric = (r.field_name || '').split('-')[0]
                const inMetricsKeys =
                  r.metrics &&
                  Object.keys(r.metrics).some(
                    (k) => k === selectedMetricName || k.startsWith(`${selectedMetricName}_`)
                  )
                return fieldMetric === selectedMetricName || inMetricsKeys
              })
            : evaluationData.results
          if (visibleResults.length === 0) {
            return (
              <div className="py-8 text-center text-sm text-zinc-500 dark:text-zinc-400">
                {t('evaluation.multiFieldResults.noResultsForMetric', {
                  defaultValue: 'No evaluation results for the selected metric.',
                })}
              </div>
            )
          }
          return (
          <div className="space-y-6">
            {visibleResults.map((result, index) => (
              <div key={result.id} className="rounded-lg border border-zinc-200 p-4 dark:border-zinc-700">
                {/* Result Header */}
                <div className="mb-4 flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${
                      result.passed === null
                        ? 'bg-amber-100 text-amber-800 dark:bg-amber-900/20 dark:text-amber-400'
                        : result.passed
                          ? 'bg-green-100 text-green-800 dark:bg-green-900/20 dark:text-green-400'
                          : 'bg-red-100 text-red-800 dark:bg-red-900/20 dark:text-red-400'
                    }`}>
                      {result.passed === null ? t('evaluation.multiFieldResults.error') : result.passed ? t('evaluation.multiFieldResults.passed') : t('evaluation.multiFieldResults.failed')}
                    </span>
                    <span className="text-sm font-medium text-zinc-900 dark:text-white">
                      {t('evaluation.multiFieldResults.field')}: {result.field_name}
                    </span>
                    <span className="text-xs text-zinc-500 dark:text-zinc-400">
                      ({result.answer_type})
                    </span>
                  </div>
                  {result.confidence_score != null && (
                    <span className="text-sm text-zinc-600 dark:text-zinc-400">
                      {t('evaluation.multiFieldResults.confidence')}: {(result.confidence_score * 100).toFixed(1)}%
                    </span>
                  )}
                </div>

                {/* Metrics */}
                {result.metrics && Object.keys(result.metrics).length > 0 && (() => {
                  // Separate _response objects from numeric metrics
                  const llmResponses: Record<string, Record<string, any>> = {}
                  const numericMetrics: Record<string, any> = {}

                  Object.entries(result.metrics).forEach(([key, value]) => {
                    if (key.endsWith('_response') && value && typeof value === 'object') {
                      llmResponses[key.replace('_response', '')] = value as Record<string, any>
                    } else if (!key.endsWith('_response')) {
                      numericMetrics[key] = value
                    }
                  })

                  return (
                    <div className="mb-4">
                      <h5 className="mb-2 text-sm font-medium text-zinc-700 dark:text-zinc-300">
                        {t('evaluation.multiFieldResults.metrics')}
                      </h5>
                      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                        {Object.entries(numericMetrics).map(([key, value]) => {
                          // Extension hook: extended metrics may register
                          // a detail component that renders the full
                          // structured payload (dimensions, justification,
                          // grade points, etc.) instead of the bare
                          // formatMetricValue. Falls back to generic
                          // numeric display when nothing is registered.
                          const DetailComp = getMetricDetail(key)
                          if (DetailComp) {
                            return (
                              <div key={key} className="col-span-full">
                                <DetailComp value={value} evaluation={result as unknown as Record<string, unknown>} />
                              </div>
                            )
                          }
                          return (
                            <div key={key} className="rounded bg-zinc-50 p-2 dark:bg-zinc-800">
                              <span className="text-xs text-zinc-500 dark:text-zinc-400">{key}:</span>
                              <span className="ml-1 font-mono text-sm text-zinc-900 dark:text-white">
                                {formatMetricValue(value)}
                              </span>
                            </div>
                          )
                        })}
                      </div>

                      {/* Full LLM Judge Response */}
                      {Object.keys(llmResponses).length > 0 && (
                        <div className="mt-4">
                          <h5 className="mb-2 text-sm font-medium text-zinc-700 dark:text-zinc-300">
                            {t('evaluation.multiFieldResults.llmJudgeResponse')}
                          </h5>
                          {Object.entries(llmResponses).map(([metric, response]) => (
                            <div key={metric} className="mb-3 rounded-lg border border-amber-200 bg-amber-50 p-3 dark:border-amber-800 dark:bg-amber-900/20">
                              <span className="mb-2 block text-xs font-medium text-amber-700 dark:text-amber-400">
                                {metric}
                              </span>
                              <div className="space-y-2">
                                {Object.entries(response).map(([fieldKey, fieldValue]) => {
                                  if (fieldKey === 'score') return null
                                  return (
                                    <div key={fieldKey} className="text-sm">
                                      <span className="font-medium text-amber-800 dark:text-amber-300">
                                        {fieldKey}:
                                      </span>
                                      {typeof fieldValue === 'string' ? (
                                        <p className="mt-1 whitespace-pre-wrap text-amber-900 dark:text-amber-200">
                                          {fieldValue}
                                        </p>
                                      ) : (
                                        <pre className="mt-1 overflow-x-auto rounded bg-amber-100 p-2 text-xs text-amber-900 dark:bg-amber-900/40 dark:text-amber-200">
                                          {JSON.stringify(fieldValue, null, 2)}
                                        </pre>
                                      )}
                                    </div>
                                  )
                                })}
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )
                })()}

                {/* Ground Truth vs Prediction */}
                <div className="grid gap-4 md:grid-cols-2">
                  <div>
                    <h5 className="mb-2 text-sm font-medium text-zinc-700 dark:text-zinc-300">
                      {t('evaluation.multiFieldResults.groundTruth')}
                    </h5>
                    <div className="rounded-lg bg-green-50 p-3 dark:bg-green-900/20">
                      <pre className="whitespace-pre-wrap text-xs text-green-800 dark:text-green-200">
                        {typeof result.ground_truth === 'string'
                          ? result.ground_truth
                          : JSON.stringify(result.ground_truth, null, 2)}
                      </pre>
                    </div>
                  </div>
                  <div>
                    <h5 className="mb-2 text-sm font-medium text-zinc-700 dark:text-zinc-300">
                      {t('evaluation.multiFieldResults.modelPrediction')}
                    </h5>
                    <div className="rounded-lg bg-blue-50 p-3 dark:bg-blue-900/20">
                      <pre className="whitespace-pre-wrap text-xs text-blue-800 dark:text-blue-200">
                        {typeof result.prediction === 'string'
                          ? result.prediction
                          : JSON.stringify(result.prediction, null, 2)}
                      </pre>
                    </div>
                  </div>
                </div>

                {/* Error Message if any */}
                {result.error_message && (
                  <div className="mt-4 rounded-lg bg-red-50 p-3 dark:bg-red-900/20">
                    <p className="text-sm text-red-700 dark:text-red-300">
                      {t('evaluation.multiFieldResults.error')}: {result.error_message}
                    </p>
                  </div>
                )}

                {/* Evaluation Context */}
                {result.evaluation_context && (
                  <div className="mt-4 text-xs text-zinc-500 dark:text-zinc-400">
                    {t('evaluation.multiFieldResults.evaluation')}: {result.evaluation_context.evaluation_type} ({result.evaluation_context.status})
                    {result.created_at && ` | ${new Date(result.created_at).toLocaleString()}`}
                  </div>
                )}
              </div>
            ))}

            {/* Full JSON Section (collapsed) */}
            <details className="group">
              <summary className="cursor-pointer font-medium text-zinc-900 dark:text-white">
                {t('evaluation.multiFieldResults.rawJsonResponse')}
              </summary>
              <div className="mt-2 rounded-lg bg-zinc-50 p-4 dark:bg-zinc-800">
                <pre className="overflow-x-auto text-xs text-zinc-700 dark:text-zinc-300">
                  {JSON.stringify(evaluationData, null, 2)}
                </pre>
              </div>
            </details>
          </div>
          )
        })() : (
          <div className="py-12 text-center text-zinc-500 dark:text-zinc-400">
            {evaluationData?.message || t('evaluation.multiFieldResults.noEvalResults')}
          </div>
        )
      )}
    </>
  )
}

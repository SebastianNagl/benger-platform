/**
 * Confusion Matrix Visualization Component
 *
 * Interactive heatmap visualization using Plotly.js for classification metrics.
 * Issue #763: Per-sample evaluation results and visualization dashboard
 */

'use client'

import { useI18n } from '@/contexts/I18nContext'
import dynamic from 'next/dynamic'
import { useMemo } from 'react'

// Dynamically import Plot to avoid SSR issues
const Plot = dynamic(() => import('react-plotly.js'), { ssr: false })

interface ConfusionMatrixData {
  field_name: string
  labels: string[]
  matrix: number[][]
  accuracy: number
  precision_per_class: Record<string, number>
  recall_per_class: Record<string, number>
  f1_per_class: Record<string, number>
}

interface ConfusionMatrixChartProps {
  data: ConfusionMatrixData
  title?: string
  width?: number
  height?: number
}

export function ConfusionMatrixChart({
  data,
  title,
  width = 700,
  height = 700,
}: ConfusionMatrixChartProps) {
  const { t } = useI18n()

  const plotData = useMemo(() => {
    const { labels, matrix } = data

    // Calculate max value for text color contrast
    const maxValue = Math.max(...matrix.flat())

    // Create annotations for each cell
    const annotations = matrix.flatMap((row, i) =>
      row.map((value, j) => ({
        x: labels[j],
        y: labels[i],
        text: String(value),
        showarrow: false,
        font: {
          color: value > maxValue / 2 ? 'white' : 'black',
          size: 14,
          weight: 600,
        },
      }))
    )

    return [
      {
        z: matrix,
        x: labels,
        y: labels,
        type: 'heatmap' as const,
        colorscale: 'Viridis',
        showscale: true,
        hoverongaps: false,
        colorbar: {
          title: {
            text: t('evaluation.confusionMatrix.count'),
            side: 'right' as const,
          },
        },
        // @ts-ignore - Plotly types are incomplete
        annotations,
      },
    ]
  }, [data, t])

  const layout = useMemo(
    () => ({
      title: {
        text: title || t('evaluation.confusionMatrix.titleWithField', { field: data.field_name }),
        font: { size: 18 },
      },
      xaxis: {
        title: {
          text: t('evaluation.confusionMatrix.predictedLabel'),
          font: { size: 14 },
        },
        side: 'bottom' as const,
        tickfont: { size: 12 },
      },
      yaxis: {
        title: {
          text: t('evaluation.confusionMatrix.trueLabel'),
          font: { size: 14 },
        },
        autorange: 'reversed' as const,
        tickfont: { size: 12 },
      },
      width,
      height,
      margin: { l: 120, r: 80, t: 120, b: 100 },
      annotations: plotData[0].annotations,
    }),
    [data.field_name, title, width, height, plotData, t]
  )

  const config = useMemo(
    () => ({
      responsive: true,
      displayModeBar: true,
      displaylogo: false,
      modeBarButtonsToRemove: ['lasso2d', 'select2d'] as any[],
    }),
    []
  )

  return (
    <div className="space-y-4">
      <div className="flex flex-col items-center">
        <Plot data={plotData} layout={layout} config={config} />
      </div>

      {/* Metrics Summary */}
      <div className="rounded-lg border bg-gray-50 p-4">
        <h4 className="mb-3 font-medium">{t('evaluation.confusionMatrix.classificationMetrics')}</h4>
        <div className="mb-4">
          <span className="text-sm font-medium">{t('evaluation.confusionMatrix.overallAccuracy')}: </span>
          <span className="text-lg font-bold text-blue-600">
            {(data.accuracy * 100).toFixed(2)}%
          </span>
        </div>

        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
          {data.labels.map((label) => (
            <div key={label} className="rounded border bg-white p-3 shadow-sm">
              <div className="mb-2 font-medium text-gray-700">{label}</div>
              <div className="space-y-1 text-sm">
                <div className="flex justify-between">
                  <span className="text-gray-600">{t('evaluation.confusionMatrix.precision')}:</span>
                  <span className="font-medium">
                    {((data.precision_per_class[label] || 0) * 100).toFixed(1)}%
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600">{t('evaluation.confusionMatrix.recall')}:</span>
                  <span className="font-medium">
                    {((data.recall_per_class[label] || 0) * 100).toFixed(1)}%
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600">{t('evaluation.confusionMatrix.f1')}:</span>
                  <span className="font-medium">
                    {((data.f1_per_class[label] || 0) * 100).toFixed(1)}%
                  </span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

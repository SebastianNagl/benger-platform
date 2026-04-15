/**
 * Evaluation Heatmap Component
 *
 * Visualizes prediction × reference field scores in a matrix heatmap.
 * Allows comparison of different field combinations with export capabilities.
 */

'use client'

import {
  ArrowDownTrayIcon,
  ClipboardDocumentIcon,
} from '@heroicons/react/24/outline'
import { useI18n } from '@/contexts/I18nContext'
import dynamic from 'next/dynamic'
import { useMemo, useState } from 'react'

const Plot = dynamic(() => import('react-plotly.js'), { ssr: false })

interface EvaluationHeatmapProps {
  predictionFields: string[]
  referenceFields: string[]
  scores: Record<string, Record<string, number>> // predictionField -> referenceField -> score
  metric: string
  onCellClick?: (predictionField: string, referenceField: string) => void
}

const SCORE_COLORS = [
  [0, '#440154'],
  [0.25, '#3b528b'],
  [0.5, '#21918c'],
  [0.75, '#5ec962'],
  [1, '#fde725'],
]

export function EvaluationHeatmap({
  predictionFields,
  referenceFields,
  scores,
  metric,
  onCellClick,
}: EvaluationHeatmapProps) {
  const { t } = useI18n()
  const [exportStatus, setExportStatus] = useState<string | null>(null)

  const { heatmapData, annotations, minScore, maxScore } = useMemo(() => {
    const rows = predictionFields.length
    const cols = referenceFields.length
    const zMatrix: (number | null)[][] = Array(rows)
      .fill(null)
      .map(() => Array(cols).fill(null))

    let min = Infinity
    let max = -Infinity
    const annotationList: any[] = []

    for (let i = 0; i < rows; i++) {
      const predField = predictionFields[i]
      for (let j = 0; j < cols; j++) {
        const refField = referenceFields[j]
        const score = scores[predField]?.[refField]

        if (score !== undefined && score !== null) {
          zMatrix[i][j] = score
          min = Math.min(min, score)
          max = Math.max(max, score)

          // Add score as text annotation
          const textColor = score > 0.5 ? 'white' : 'black'
          annotationList.push({
            x: refField,
            y: predField,
            text: score.toFixed(3),
            showarrow: false,
            font: {
              color: textColor,
              size: 11,
              weight: 500,
            },
          })
        }
      }
    }

    return {
      heatmapData: zMatrix,
      annotations: annotationList,
      minScore: min === Infinity ? 0 : min,
      maxScore: max === -Infinity ? 1 : max,
    }
  }, [predictionFields, referenceFields, scores])

  const plotData = useMemo(() => {
    const customData = predictionFields.map((predField) =>
      referenceFields.map((refField) => ({
        predictionField: predField,
        referenceField: refField,
        score: scores[predField]?.[refField] ?? null,
      }))
    )

    return [
      {
        z: heatmapData,
        x: referenceFields,
        y: predictionFields,
        type: 'heatmap' as const,
        colorscale: SCORE_COLORS as any,
        zmin: 0,
        zmax: 1,
        showscale: true,
        hoverongaps: false,
        colorbar: {
          title: {
            text: metric,
            side: 'right' as const,
          },
          thickness: 15,
          len: 0.7,
        },
        customdata: customData,
        hovertemplate:
          '<b>Prediction: %{customdata.predictionField}</b><br>' +
          '<b>Reference: %{customdata.referenceField}</b><br>' +
          `${metric}: %{customdata.score:.4f}<extra></extra>`,
      } as any,
    ]
  }, [heatmapData, predictionFields, referenceFields, scores, metric])

  const layout = useMemo(
    () => ({
      title: {
        text: `${t('evaluation.charts.heatmap.fieldCombinationScores')} - ${metric}`,
        font: { size: 18 },
      },
      xaxis: {
        title: {
          text: t('evaluation.charts.heatmap.referenceField'),
          font: { size: 14 },
        },
        side: 'bottom' as const,
        tickfont: { size: 11 },
        tickangle: -45,
      },
      yaxis: {
        title: {
          text: t('evaluation.charts.heatmap.predictionField'),
          font: { size: 14 },
        },
        autorange: 'reversed' as const,
        tickfont: { size: 11 },
      },
      width: Math.max(600, referenceFields.length * 120),
      height: Math.max(400, predictionFields.length * 80),
      margin: { l: 150, r: 100, t: 100, b: 150 },
      annotations,
    }),
    [metric, predictionFields.length, referenceFields.length, annotations, t]
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

  const handleClick = (event: any) => {
    if (!onCellClick || !event.points || event.points.length === 0) return

    const point = event.points[0]
    const predictionField = point.y
    const referenceField = point.x

    if (predictionField && referenceField) {
      onCellClick(predictionField, referenceField)
    }
  }

  const exportToCSV = () => {
    const rows: string[] = []

    // Header row
    rows.push(['Prediction Field', ...referenceFields].join(','))

    // Data rows
    for (let i = 0; i < predictionFields.length; i++) {
      const predField = predictionFields[i]
      const rowData = [predField]
      for (let j = 0; j < referenceFields.length; j++) {
        const refField = referenceFields[j]
        const score = scores[predField]?.[refField]
        rowData.push(
          score !== undefined && score !== null ? score.toFixed(4) : 'N/A'
        )
      }
      rows.push(rowData.join(','))
    }

    const csvContent = rows.join('\n')
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' })
    const link = document.createElement('a')
    const url = URL.createObjectURL(blob)

    link.setAttribute('href', url)
    link.setAttribute('download', `field_scores_${metric}_${Date.now()}.csv`)
    link.style.visibility = 'hidden'
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)

    setExportStatus(t('evaluation.charts.heatmap.csvDownloaded'))
    setTimeout(() => setExportStatus(null), 3000)
  }

  const exportToLaTeX = () => {
    const lines: string[] = []

    // Table header
    lines.push('\\begin{table}[h]')
    lines.push('\\centering')
    lines.push(
      `\\caption{${metric} scores for prediction × reference field combinations}`
    )
    lines.push(
      `\\label{tab:field-scores-${metric.toLowerCase().replace(/\s+/g, '-')}}`
    )

    // Column specification
    const colSpec = 'l|' + 'c'.repeat(referenceFields.length)
    lines.push(`\\begin{tabular}{${colSpec}}`)
    lines.push('\\hline')

    // Header row
    const headerRow = [
      'Prediction Field',
      ...referenceFields.map((f) => `\\textbf{${f}}`),
    ].join(' & ')
    lines.push(`${headerRow} \\\\`)
    lines.push('\\hline')

    // Data rows
    for (let i = 0; i < predictionFields.length; i++) {
      const predField = predictionFields[i]
      const rowData = [`\\textbf{${predField}}`]
      for (let j = 0; j < referenceFields.length; j++) {
        const refField = referenceFields[j]
        const score = scores[predField]?.[refField]
        rowData.push(
          score !== undefined && score !== null ? score.toFixed(3) : '--'
        )
      }
      lines.push(rowData.join(' & ') + ' \\\\')
    }

    // Table footer
    lines.push('\\hline')
    lines.push('\\end{tabular}')
    lines.push('\\end{table}')

    const latexContent = lines.join('\n')

    // Copy to clipboard
    navigator.clipboard
      .writeText(latexContent)
      .then(() => {
        setExportStatus(t('evaluation.charts.heatmap.latexCopied'))
        setTimeout(() => setExportStatus(null), 3000)
      })
      .catch((err) => {
        console.error('Failed to copy LaTeX:', err)
        setExportStatus(t('evaluation.charts.heatmap.latexCopyFailed'))
        setTimeout(() => setExportStatus(null), 3000)
      })
  }

  return (
    <div className="space-y-4">
      {/* Export Buttons */}
      <div className="flex items-center justify-between">
        <div className="flex gap-2">
          <button
            onClick={exportToCSV}
            className="flex items-center gap-2 rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
          >
            <ArrowDownTrayIcon className="h-4 w-4" />
            {t('evaluation.charts.heatmap.exportCsv')}
          </button>
          <button
            onClick={exportToLaTeX}
            className="flex items-center gap-2 rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
          >
            <ClipboardDocumentIcon className="h-4 w-4" />
            {t('evaluation.charts.heatmap.exportLatex')}
          </button>
        </div>
        {exportStatus && (
          <div className="rounded-lg bg-green-50 px-3 py-2 text-sm text-green-800">
            {exportStatus}
          </div>
        )}
      </div>

      {/* Heatmap */}
      <div className="flex flex-col items-center">
        <Plot
          data={plotData}
          layout={layout}
          config={config}
          onClick={handleClick}
        />
      </div>

      {/* Legend */}
      <div className="rounded-lg border bg-gray-50 p-4">
        <h4 className="mb-3 font-medium">{t('evaluation.charts.heatmap.legend')}</h4>
        <div className="space-y-3">
          <div>
            <h5 className="mb-2 text-sm font-medium text-gray-700">
              {t('evaluation.charts.heatmap.colorScale')}
            </h5>
            <div className="space-y-1 text-sm">
              <div className="flex items-center gap-2">
                <div
                  className="h-4 w-4 rounded"
                  style={{ backgroundColor: '#fde725' }}
                />
                <span>{t('evaluation.charts.heatmap.highScore')}</span>
              </div>
              <div className="flex items-center gap-2">
                <div
                  className="h-4 w-4 rounded"
                  style={{ backgroundColor: '#21918c' }}
                />
                <span>{t('evaluation.charts.heatmap.mediumScore')}</span>
              </div>
              <div className="flex items-center gap-2">
                <div
                  className="h-4 w-4 rounded"
                  style={{ backgroundColor: '#440154' }}
                />
                <span>{t('evaluation.charts.heatmap.lowScore')}</span>
              </div>
            </div>
          </div>

          <div className="rounded border-l-4 border-blue-500 bg-blue-50 p-3 text-sm">
            <p className="text-gray-700">
              <strong>{t('evaluation.charts.heatmap.noteLabel')}:</strong> {t('evaluation.charts.heatmap.noteText', { metric })}
            </p>
          </div>

          <div>
            <h5 className="mb-2 text-sm font-medium text-gray-700">
              {t('evaluation.charts.heatmap.scoreRange')}
            </h5>
            <div className="space-y-1 text-sm">
              <div className="flex items-center gap-2">
                <span className="font-medium">{t('evaluation.charts.heatmap.min')}:</span>
                <span>{minScore.toFixed(4)}</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="font-medium">{t('evaluation.charts.heatmap.max')}:</span>
                <span>{maxScore.toFixed(4)}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

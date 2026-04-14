/**
 * Significance Heatmap Component
 *
 * Visualizes pairwise statistical significance between models using a heatmap.
 * Shows p-values, effect sizes, and significance stars for model comparisons.
 */

'use client'

import { useI18n } from '@/contexts/I18nContext'
import dynamic from 'next/dynamic'
import { useMemo } from 'react'

const Plot = dynamic(() => import('react-plotly.js'), { ssr: false })

interface SignificanceEntry {
  model_a: string
  model_b: string
  p_value: number
  significant: boolean
  effect_size: number
  stars: string
}

interface SignificanceHeatmapProps {
  modelIds: string[]
  metric: string
  significanceData: SignificanceEntry[]
  height?: number
  onCellClick?: (modelA: string, modelB: string) => void
}

const SIGNIFICANCE_COLORS = {
  p001: '#1e40af',
  p01: '#3b82f6',
  p05: '#93c5fd',
  ns: '#e5e7eb',
}

export function SignificanceHeatmap({
  modelIds,
  metric,
  significanceData,
  height = 400,
  onCellClick,
}: SignificanceHeatmapProps) {
  const { t } = useI18n()
  const { heatmapData, annotations } = useMemo(() => {
    const n = modelIds.length
    const zMatrix: (number | null)[][] = Array(n)
      .fill(null)
      .map(() => Array(n).fill(null))

    const dataMap = new Map<string, SignificanceEntry>()
    significanceData.forEach((entry) => {
      const key = `${entry.model_a}:${entry.model_b}`
      dataMap.set(key, entry)
    })

    const annotationList: any[] = []

    for (let i = 0; i < n; i++) {
      for (let j = 0; j < n; j++) {
        if (i === j) {
          zMatrix[i][j] = 0
          continue
        }

        if (i < j) {
          continue
        }

        const key = `${modelIds[j]}:${modelIds[i]}`
        const entry = dataMap.get(key)

        if (entry) {
          zMatrix[i][j] = entry.effect_size

          const textColor =
            Math.abs(entry.effect_size) > 0.5 ? 'white' : 'black'

          annotationList.push({
            x: modelIds[j],
            y: modelIds[i],
            text: entry.stars || '',
            showarrow: false,
            font: {
              color: textColor,
              size: 20,
              weight: 700,
            },
          })
        }
      }
    }

    return {
      heatmapData: zMatrix,
      annotations: annotationList,
    }
  }, [modelIds, significanceData])

  const plotData = useMemo(() => {
    const customData = modelIds.map((modelA, i) =>
      modelIds.map((modelB, j) => {
        if (i === j || i < j) {
          return {
            modelA,
            modelB,
            pValue: null,
            effectSize: null,
            significant: false,
            stars: '',
          }
        }

        const key = `${modelB}:${modelA}`
        const entry = significanceData.find(
          (e) => `${e.model_a}:${e.model_b}` === key
        )

        return {
          modelA,
          modelB,
          pValue: entry?.p_value ?? null,
          effectSize: entry?.effect_size ?? null,
          significant: entry?.significant ?? false,
          stars: entry?.stars ?? '',
        }
      })
    )

    return [
      {
        z: heatmapData,
        x: modelIds,
        y: modelIds,
        type: 'heatmap' as const,
        colorscale: [
          [0, '#dc2626'],
          [0.25, '#f87171'],
          [0.5, '#ffffff'],
          [0.75, '#60a5fa'],
          [1, '#1e40af'],
        ] as any,
        zmid: 0,
        showscale: true,
        hoverongaps: false,
        colorbar: {
          title: {
            text: t('evaluation.charts.significance.effectSize'),
            side: 'right' as const,
          },
          thickness: 15,
          len: 0.7,
        },
        customdata: customData,
        hovertemplate:
          '<b>%{customdata.modelB} vs %{customdata.modelA}</b><br>' +
          `${t('evaluation.charts.significance.pValue')}: %{customdata.pValue:.4f}<br>` +
          `${t('evaluation.charts.significance.effectSizeLabel')}: %{customdata.effectSize:.4f}<br>` +
          `${t('evaluation.charts.significance.significant')}: %{customdata.significant}<br>` +
          `${t('evaluation.charts.significance.stars')}: %{customdata.stars}<extra></extra>`,
      } as any,
    ]
  }, [heatmapData, modelIds, significanceData])

  const layout = useMemo(
    () => ({
      title: {
        text: `${t('evaluation.charts.significance.title')} - ${metric}`,
        font: { size: 18 },
      },
      xaxis: {
        title: {
          text: t('evaluation.charts.significance.modelB'),
          font: { size: 14 },
        },
        side: 'bottom' as const,
        tickfont: { size: 11 },
        tickangle: -45,
      },
      yaxis: {
        title: {
          text: t('evaluation.charts.significance.modelA'),
          font: { size: 14 },
        },
        autorange: 'reversed' as const,
        tickfont: { size: 11 },
      },
      width: height,
      height,
      margin: { l: 150, r: 100, t: 100, b: 150 },
      annotations,
    }),
    [metric, height, annotations, t]
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
    const modelA = point.y
    const modelB = point.x

    if (modelA && modelB && modelA !== modelB) {
      onCellClick(modelA, modelB)
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-col items-center">
        <Plot
          data={plotData}
          layout={layout}
          config={config}
          onClick={handleClick}
        />
      </div>

      <div className="rounded-lg border bg-gray-50 p-4">
        <h4 className="mb-3 font-medium">{t('evaluation.charts.significance.legend')}</h4>
        <div className="space-y-3">
          <div>
            <h5 className="mb-2 text-sm font-medium text-gray-700">
              {t('evaluation.charts.significance.colorScale')}
            </h5>
            <div className="space-y-1 text-sm">
              <div className="flex items-center gap-2">
                <div
                  className="h-4 w-4 rounded"
                  style={{ backgroundColor: '#1e40af' }}
                />
                <span>{t('evaluation.charts.significance.positiveEffect')}</span>
              </div>
              <div className="flex items-center gap-2">
                <div
                  className="h-4 w-4 rounded"
                  style={{
                    backgroundColor: '#ffffff',
                    border: '1px solid #d1d5db',
                  }}
                />
                <span>{t('evaluation.charts.significance.noEffect')}</span>
              </div>
              <div className="flex items-center gap-2">
                <div
                  className="h-4 w-4 rounded"
                  style={{ backgroundColor: '#dc2626' }}
                />
                <span>{t('evaluation.charts.significance.negativeEffect')}</span>
              </div>
            </div>
          </div>

          <div>
            <h5 className="mb-2 text-sm font-medium text-gray-700">
              {t('evaluation.charts.significance.significanceStars')}
            </h5>
            <div className="space-y-1 text-sm">
              <div className="flex items-center gap-2">
                <span className="font-mono font-bold">***</span>
                <span>{t('evaluation.charts.significance.pLt001')}</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="font-mono font-bold">**</span>
                <span>{t('evaluation.charts.significance.pLt01')}</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="font-mono font-bold">*</span>
                <span>{t('evaluation.charts.significance.pLt05')}</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="font-mono font-bold">{t('evaluation.charts.significance.empty')}</span>
                <span>{t('evaluation.charts.significance.pGte05')}</span>
              </div>
            </div>
          </div>

          <div className="rounded border-l-4 border-blue-500 bg-blue-50 p-3 text-sm">
            <p className="text-gray-700">
              <strong>{t('evaluation.charts.significance.noteLabel')}:</strong> {t('evaluation.charts.significance.noteText')}
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}

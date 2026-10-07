'use client'

import {
  ProjectScoresDialog,
  type ProjectScoreRow,
  type ScoresPeriod,
} from '@/components/shared/ProjectScoresDialog'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'

/** The minimum a caller has to know about a model to open the detail view. */
export interface ModelDetailModalModel {
  id: string
  name: string
  provider: string
}

interface ModelDetailModalProps {
  /** `null` keeps the dialog closed. */
  model: ModelDetailModalModel | null
  /**
   * Optional technical settings (the former JSON-only modal content). When
   * given, they render in a collapsed "Technical details" section.
   */
  settingsJson?: Record<string, unknown> | null
  onClose: () => void
}

/**
 * One model's evaluation scores across every project the viewer may read,
 * as a project x metric table. Opened from the model catalog (`/models`),
 * the custom model list and the LLM leaderboard rows.
 */
export function ModelDetailModal({
  model,
  settingsJson,
  onClose,
}: ModelDetailModalProps) {
  const { t } = useI18n()
  const { user, apiClient } = useAuth()
  const [period, setPeriod] = useState<ScoresPeriod>('overall')

  const scoresQuery = useQuery({
    queryKey: ['llm-model-project-scores', model?.id, period],
    queryFn: () =>
      apiClient.leaderboards.getLLMModelProjectScores(model!.id, { period }),
    enabled: !!model,
    staleTime: 5 * 60_000,
  })

  const rows: ProjectScoreRow[] = (scoresQuery.data?.projects ?? []).map(
    (p) => ({
      project_id: p.project_id,
      project_name: p.project_name,
      project_kind: p.project_kind,
      is_public: p.is_public,
      count: p.generation_count,
      samples_evaluated: p.samples_evaluated,
      last_evaluated: p.last_evaluated,
      metrics: p.metrics,
    }),
  )

  return (
    <ProjectScoresDialog
      open={!!model}
      onClose={onClose}
      title={model?.name ?? ''}
      subtitle={model?.id}
      badge={model?.provider}
      rows={rows}
      metrics={scoresQuery.data?.available_metrics ?? []}
      isLoading={scoresQuery.isLoading}
      isError={scoresQuery.isError}
      onRetry={() => scoresQuery.refetch()}
      period={period}
      onPeriodChange={setPeriod}
      countLabel={t('leaderboards.llm.generations')}
      hint={!user ? t('models.detail.anonymousHint') : undefined}
      settingsJson={settingsJson}
      testIdPrefix="model-detail"
    />
  )
}

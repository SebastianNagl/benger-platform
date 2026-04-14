/**
 * Leaderboard API client methods
 *
 * Privacy-first leaderboard APIs that respect user pseudonym preferences.
 * Also includes LLM model leaderboards based on evaluation metrics.
 * See Issue #790 for implementation details.
 */

import { BaseApiClient } from './base'

// Human Annotator Leaderboard Types
export interface LeaderboardEntry {
  rank: number
  user_id: string
  display_name: string
  annotation_count: number
  is_current_user: boolean
  metric_value?: number | null
  evaluated_count?: number
}

export interface LeaderboardResponse {
  leaderboard: LeaderboardEntry[]
  total_users: number
  available_metrics: string[]
  filters: {
    project_ids: string[]
    period: string
    metric?: string | null
    aggregation?: string
    limit: number
    offset?: number
  }
}

export interface MyRankResponse {
  my_rank: LeaderboardEntry | null
  above: LeaderboardEntry[]
  below: LeaderboardEntry[]
  total_users: number
  message?: string
}

export interface LeaderboardStatistics {
  total_annotations: number
  total_annotators: number
  average_annotations_per_user: number
  filters: {
    project_ids: string[]
    period: string
  }
}

// LLM Leaderboard Types
export interface LLMLeaderboardEntry {
  rank: number
  model_id: string
  model_name: string
  provider: string
  evaluation_count: number
  samples_evaluated: number
  metrics: Record<string, number | null>
  average_score: number | null // null for models without evaluations
  // 95% confidence interval for average score
  ci_lower: number | null
  ci_upper: number | null
  last_evaluated: string | null
}

export interface LLMLeaderboardResponse {
  leaderboard: LLMLeaderboardEntry[]
  total_models: number
  available_metrics: string[]
  available_evaluation_types: string[] // List of evaluation types in the data
  filters: {
    project_ids: string[]
    period: string
    metric: string
    aggregation: string
    evaluation_types: string[]
    include_all_models: boolean
    limit: number
    offset?: number
  }
  // Indicates if CI calculations are available (scipy installed)
  confidence_intervals_available: boolean
}

export interface LLMModelDetails {
  model_info: {
    id: string
    name: string
    provider: string
  }
  evaluations: Array<{
    id: string
    project_id: string
    metrics: Record<string, number>
    samples_evaluated: number
    created_at: string
    completed_at: string
  }>
  aggregate_metrics: Record<
    string,
    {
      mean: number
      min: number
      max: number
      count: number
    }
  >
  evaluation_count: number
  filters: {
    project_ids: string[]
    period: string
  }
}

export interface LLMModelComparison {
  models: Record<
    string,
    {
      info: { name: string; provider: string }
      metrics: Record<string, number>
    }
  >
  common_metrics: string[]
  all_metrics: string[]
  comparison: Record<string, Record<string, number | string | null>>
  filters: {
    model_ids: string[]
    project_ids: string[]
    period: string
  }
}

export class LeaderboardsClient extends BaseApiClient {
  /**
   * Get current user's rank with context
   */
  async getMyRank(params?: {
    project_ids?: string[]
    period?: 'overall' | 'monthly' | 'weekly'
    context_size?: number
  }): Promise<MyRankResponse> {
    const queryParams = new URLSearchParams()

    if (params?.project_ids && params.project_ids.length > 0) {
      params.project_ids.forEach((id) => queryParams.append('project_ids', id))
    }

    if (params?.period) {
      queryParams.append('period', params.period)
    }

    if (params?.context_size) {
      queryParams.append('context_size', params.context_size.toString())
    }

    return this.get(`/leaderboards/my-rank?${queryParams.toString()}`)
  }

  /**
   * Get leaderboard statistics
   */
  async getStatistics(params?: {
    project_ids?: string[]
    period?: 'overall' | 'monthly' | 'weekly'
  }): Promise<LeaderboardStatistics> {
    const queryParams = new URLSearchParams()

    if (params?.project_ids && params.project_ids.length > 0) {
      params.project_ids.forEach((id) => queryParams.append('project_ids', id))
    }

    if (params?.period) {
      queryParams.append('period', params.period)
    }

    return this.get(`/leaderboards/statistics?${queryParams.toString()}`)
  }

  // ============================================================================
  // LLM MODEL LEADERBOARD METHODS
  // ============================================================================

  /**
   * Get LLM model leaderboard with filtering
   */
  async getLLMLeaderboard(params?: {
    project_ids?: string[]
    period?: 'overall' | 'monthly' | 'weekly'
    metric?: string
    aggregation?: 'average' | 'sum'
    evaluation_types?: string[]
    include_all_models?: boolean
    limit?: number
    offset?: number
  }): Promise<LLMLeaderboardResponse> {
    const queryParams = new URLSearchParams()

    if (params?.project_ids && params.project_ids.length > 0) {
      params.project_ids.forEach((id) => queryParams.append('project_ids', id))
    }

    if (params?.period) {
      queryParams.append('period', params.period)
    }

    if (params?.metric) {
      queryParams.append('metric', params.metric)
    }

    if (params?.aggregation) {
      queryParams.append('aggregation', params.aggregation)
    }

    if (params?.evaluation_types && params.evaluation_types.length > 0) {
      params.evaluation_types.forEach((type) =>
        queryParams.append('evaluation_types', type)
      )
    }

    if (params?.include_all_models !== undefined) {
      queryParams.append('include_all_models', params.include_all_models.toString())
    }

    if (params?.limit) {
      queryParams.append('limit', params.limit.toString())
    }

    if (params?.offset !== undefined) {
      queryParams.append('offset', params.offset.toString())
    }

    return this.get(`/leaderboards/llm-models?${queryParams.toString()}`)
  }

  /**
   * Get detailed evaluation history for a specific LLM model
   */
  async getLLMModelDetails(
    modelId: string,
    params?: {
      project_ids?: string[]
      period?: 'overall' | 'monthly' | 'weekly'
    }
  ): Promise<LLMModelDetails> {
    const queryParams = new URLSearchParams()

    if (params?.project_ids && params.project_ids.length > 0) {
      params.project_ids.forEach((id) => queryParams.append('project_ids', id))
    }

    if (params?.period) {
      queryParams.append('period', params.period)
    }

    return this.get(
      `/leaderboards/llm-models/${encodeURIComponent(modelId)}?${queryParams.toString()}`
    )
  }

  /**
   * Compare multiple LLM models side-by-side
   */
  async compareLLMModels(params: {
    model_ids: string[]
    project_ids?: string[]
    period?: 'overall' | 'monthly' | 'weekly'
  }): Promise<LLMModelComparison> {
    const queryParams = new URLSearchParams()

    params.model_ids.forEach((id) => queryParams.append('model_ids', id))

    if (params.project_ids && params.project_ids.length > 0) {
      params.project_ids.forEach((id) => queryParams.append('project_ids', id))
    }

    if (params.period) {
      queryParams.append('period', params.period)
    }

    return this.get(
      `/leaderboards/llm-models/compare?${queryParams.toString()}`
    )
  }
}

/**
 * Tests for the LeaderboardsClient
 * Covers all leaderboard API endpoints including annotator, co-creation, and LLM model leaderboards.
 */

import { LeaderboardsClient } from '../leaderboards'

// Mock the BaseApiClient - capture the URL so we can assert on query parameters
jest.mock('../base', () => ({
  BaseApiClient: class MockBaseApiClient {
    async get(url: string): Promise<any> {
      return { _url: url }
    }
  },
}))

describe('LeaderboardsClient', () => {
  let client: LeaderboardsClient

  beforeEach(() => {
    client = new LeaderboardsClient()
  })

  // ============================================================================
  // getMyRank
  // ============================================================================

  describe('getMyRank', () => {
    it('should call the correct base URL with no params', async () => {
      const result = await client.getMyRank()
      expect((result as any)._url).toBe('/leaderboards/my-rank?')
    })

    it('should call the correct base URL with undefined params', async () => {
      const result = await client.getMyRank(undefined)
      expect((result as any)._url).toBe('/leaderboards/my-rank?')
    })

    it('should call the correct base URL with empty params object', async () => {
      const result = await client.getMyRank({})
      expect((result as any)._url).toBe('/leaderboards/my-rank?')
    })

    it('should append project_ids', async () => {
      const result = await client.getMyRank({
        project_ids: ['proj-1', 'proj-2'],
      })
      const url = (result as any)._url
      expect(url).toContain('project_ids=proj-1')
      expect(url).toContain('project_ids=proj-2')
    })

    it('should not append project_ids when array is empty', async () => {
      const result = await client.getMyRank({ project_ids: [] })
      expect((result as any)._url).not.toContain('project_ids')
    })

    it('should append period param', async () => {
      const result = await client.getMyRank({ period: 'weekly' })
      expect((result as any)._url).toContain('period=weekly')
    })

    it('should append context_size param', async () => {
      const result = await client.getMyRank({ context_size: 5 })
      expect((result as any)._url).toContain('context_size=5')
    })

    it('should not append context_size when it is 0 (falsy)', async () => {
      const result = await client.getMyRank({ context_size: 0 })
      expect((result as any)._url).not.toContain('context_size')
    })

    it('should handle all params together', async () => {
      const result = await client.getMyRank({
        project_ids: ['p1'],
        period: 'monthly',
        context_size: 3,
      })
      const url = (result as any)._url
      expect(url).toContain('project_ids=p1')
      expect(url).toContain('period=monthly')
      expect(url).toContain('context_size=3')
    })
  })

  // ============================================================================
  // getStatistics
  // ============================================================================

  describe('getStatistics', () => {
    it('should call the correct base URL with no params', async () => {
      const result = await client.getStatistics()
      expect((result as any)._url).toBe('/leaderboards/statistics?')
    })

    it('should call the correct base URL with undefined params', async () => {
      const result = await client.getStatistics(undefined)
      expect((result as any)._url).toBe('/leaderboards/statistics?')
    })

    it('should call the correct base URL with empty params object', async () => {
      const result = await client.getStatistics({})
      expect((result as any)._url).toBe('/leaderboards/statistics?')
    })

    it('should append project_ids', async () => {
      const result = await client.getStatistics({
        project_ids: ['proj-a', 'proj-b'],
      })
      const url = (result as any)._url
      expect(url).toContain('project_ids=proj-a')
      expect(url).toContain('project_ids=proj-b')
    })

    it('should not append project_ids when array is empty', async () => {
      const result = await client.getStatistics({ project_ids: [] })
      expect((result as any)._url).not.toContain('project_ids')
    })

    it('should append period param', async () => {
      const result = await client.getStatistics({ period: 'overall' })
      expect((result as any)._url).toContain('period=overall')
    })

    it('should handle both params together', async () => {
      const result = await client.getStatistics({
        project_ids: ['z1'],
        period: 'weekly',
      })
      const url = (result as any)._url
      expect(url).toContain('project_ids=z1')
      expect(url).toContain('period=weekly')
    })
  })

  // ============================================================================
  // getLLMLeaderboard
  // ============================================================================

  describe('getLLMLeaderboard', () => {
    it('should call the correct base URL with no params', async () => {
      const result = await client.getLLMLeaderboard()
      expect((result as any)._url).toBe('/leaderboards/llm-models?')
    })

    it('should call the correct base URL with undefined params', async () => {
      const result = await client.getLLMLeaderboard(undefined)
      expect((result as any)._url).toBe('/leaderboards/llm-models?')
    })

    it('should call the correct base URL with empty params object', async () => {
      const result = await client.getLLMLeaderboard({})
      expect((result as any)._url).toBe('/leaderboards/llm-models?')
    })

    it('should append project_ids', async () => {
      const result = await client.getLLMLeaderboard({
        project_ids: ['p1', 'p2'],
      })
      const url = (result as any)._url
      expect(url).toContain('project_ids=p1')
      expect(url).toContain('project_ids=p2')
    })

    it('should not append project_ids when array is empty', async () => {
      const result = await client.getLLMLeaderboard({ project_ids: [] })
      expect((result as any)._url).not.toContain('project_ids')
    })

    it('should append period param', async () => {
      const result = await client.getLLMLeaderboard({ period: 'monthly' })
      expect((result as any)._url).toContain('period=monthly')
    })

    it('should append metric param', async () => {
      const result = await client.getLLMLeaderboard({ metric: 'bleu' })
      expect((result as any)._url).toContain('metric=bleu')
    })

    it('should append aggregation param', async () => {
      const result = await client.getLLMLeaderboard({ aggregation: 'sum' })
      expect((result as any)._url).toContain('aggregation=sum')
    })

    it('should append evaluation_types', async () => {
      const result = await client.getLLMLeaderboard({
        evaluation_types: ['human', 'auto'],
      })
      const url = (result as any)._url
      expect(url).toContain('evaluation_types=human')
      expect(url).toContain('evaluation_types=auto')
    })

    it('should not append evaluation_types when array is empty', async () => {
      const result = await client.getLLMLeaderboard({ evaluation_types: [] })
      expect((result as any)._url).not.toContain('evaluation_types')
    })

    it('should append include_all_models=true when true', async () => {
      const result = await client.getLLMLeaderboard({
        include_all_models: true,
      })
      expect((result as any)._url).toContain('include_all_models=true')
    })

    it('should append include_all_models=false when false', async () => {
      const result = await client.getLLMLeaderboard({
        include_all_models: false,
      })
      expect((result as any)._url).toContain('include_all_models=false')
    })

    it('should not append include_all_models when undefined', async () => {
      const result = await client.getLLMLeaderboard({})
      expect((result as any)._url).not.toContain('include_all_models')
    })

    it('should append limit param', async () => {
      const result = await client.getLLMLeaderboard({ limit: 30 })
      expect((result as any)._url).toContain('limit=30')
    })

    it('should not append limit when limit is 0 (falsy)', async () => {
      const result = await client.getLLMLeaderboard({ limit: 0 })
      expect((result as any)._url).not.toContain('limit=')
    })

    it('should append offset param when defined', async () => {
      const result = await client.getLLMLeaderboard({ offset: 15 })
      expect((result as any)._url).toContain('offset=15')
    })

    it('should append offset=0 when offset is zero', async () => {
      const result = await client.getLLMLeaderboard({ offset: 0 })
      expect((result as any)._url).toContain('offset=0')
    })

    it('should handle all params together', async () => {
      const result = await client.getLLMLeaderboard({
        project_ids: ['p1'],
        period: 'weekly',
        metric: 'rouge',
        aggregation: 'average',
        evaluation_types: ['human', 'auto', 'hybrid'],
        include_all_models: true,
        limit: 10,
        offset: 5,
      })
      const url = (result as any)._url
      expect(url).toContain('project_ids=p1')
      expect(url).toContain('period=weekly')
      expect(url).toContain('metric=rouge')
      expect(url).toContain('aggregation=average')
      expect(url).toContain('evaluation_types=human')
      expect(url).toContain('evaluation_types=auto')
      expect(url).toContain('evaluation_types=hybrid')
      expect(url).toContain('include_all_models=true')
      expect(url).toContain('limit=10')
      expect(url).toContain('offset=5')
    })
  })

  // ============================================================================
  // getLLMModelDetails
  // ============================================================================

  describe('getLLMModelDetails', () => {
    it('should call the correct URL with just modelId', async () => {
      const result = await client.getLLMModelDetails('gpt-4')
      expect((result as any)._url).toBe(
        '/leaderboards/llm-models/gpt-4?'
      )
    })

    it('should encode special characters in modelId', async () => {
      const result = await client.getLLMModelDetails('model/with spaces')
      expect((result as any)._url).toContain(
        '/leaderboards/llm-models/model%2Fwith%20spaces?'
      )
    })

    it('should append project_ids', async () => {
      const result = await client.getLLMModelDetails('gpt-4', {
        project_ids: ['p1', 'p2'],
      })
      const url = (result as any)._url
      expect(url).toContain('/leaderboards/llm-models/gpt-4?')
      expect(url).toContain('project_ids=p1')
      expect(url).toContain('project_ids=p2')
    })

    it('should not append project_ids when array is empty', async () => {
      const result = await client.getLLMModelDetails('gpt-4', {
        project_ids: [],
      })
      expect((result as any)._url).not.toContain('project_ids')
    })

    it('should append period param', async () => {
      const result = await client.getLLMModelDetails('gpt-4', {
        period: 'monthly',
      })
      expect((result as any)._url).toContain('period=monthly')
    })

    it('should handle both params together', async () => {
      const result = await client.getLLMModelDetails('claude-3', {
        project_ids: ['p1'],
        period: 'weekly',
      })
      const url = (result as any)._url
      expect(url).toContain('/leaderboards/llm-models/claude-3?')
      expect(url).toContain('project_ids=p1')
      expect(url).toContain('period=weekly')
    })

    it('should handle empty params object', async () => {
      const result = await client.getLLMModelDetails('gpt-4', {})
      expect((result as any)._url).toBe(
        '/leaderboards/llm-models/gpt-4?'
      )
    })

    it('should handle undefined params', async () => {
      const result = await client.getLLMModelDetails('gpt-4', undefined)
      expect((result as any)._url).toBe(
        '/leaderboards/llm-models/gpt-4?'
      )
    })
  })

  // ============================================================================
  // compareLLMModels
  // ============================================================================

  describe('compareLLMModels', () => {
    it('should call the correct URL with required model_ids', async () => {
      const result = await client.compareLLMModels({
        model_ids: ['gpt-4', 'claude-3'],
      })
      const url = (result as any)._url
      expect(url).toContain('/leaderboards/llm-models/compare?')
      expect(url).toContain('model_ids=gpt-4')
      expect(url).toContain('model_ids=claude-3')
    })

    it('should handle a single model_id', async () => {
      const result = await client.compareLLMModels({
        model_ids: ['gpt-4'],
      })
      const url = (result as any)._url
      expect(url).toContain('model_ids=gpt-4')
    })

    it('should handle multiple model_ids', async () => {
      const result = await client.compareLLMModels({
        model_ids: ['m1', 'm2', 'm3', 'm4'],
      })
      const url = (result as any)._url
      expect(url).toContain('model_ids=m1')
      expect(url).toContain('model_ids=m2')
      expect(url).toContain('model_ids=m3')
      expect(url).toContain('model_ids=m4')
    })

    it('should append project_ids', async () => {
      const result = await client.compareLLMModels({
        model_ids: ['gpt-4'],
        project_ids: ['p1', 'p2'],
      })
      const url = (result as any)._url
      expect(url).toContain('project_ids=p1')
      expect(url).toContain('project_ids=p2')
    })

    it('should not append project_ids when array is empty', async () => {
      const result = await client.compareLLMModels({
        model_ids: ['gpt-4'],
        project_ids: [],
      })
      expect((result as any)._url).not.toContain('project_ids')
    })

    it('should append period param', async () => {
      const result = await client.compareLLMModels({
        model_ids: ['gpt-4'],
        period: 'overall',
      })
      expect((result as any)._url).toContain('period=overall')
    })

    it('should not append period when undefined', async () => {
      const result = await client.compareLLMModels({
        model_ids: ['gpt-4'],
      })
      expect((result as any)._url).not.toContain('period=')
    })

    it('should handle all params together', async () => {
      const result = await client.compareLLMModels({
        model_ids: ['gpt-4', 'claude-3'],
        project_ids: ['p1', 'p2'],
        period: 'weekly',
      })
      const url = (result as any)._url
      expect(url).toContain('/leaderboards/llm-models/compare?')
      expect(url).toContain('model_ids=gpt-4')
      expect(url).toContain('model_ids=claude-3')
      expect(url).toContain('project_ids=p1')
      expect(url).toContain('project_ids=p2')
      expect(url).toContain('period=weekly')
    })

    it('should not append project_ids when undefined', async () => {
      const result = await client.compareLLMModels({
        model_ids: ['gpt-4'],
        project_ids: undefined,
      })
      expect((result as any)._url).not.toContain('project_ids')
    })
  })
})

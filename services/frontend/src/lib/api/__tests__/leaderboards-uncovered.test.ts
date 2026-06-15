/**
 * Additional coverage for LeaderboardsClient.
 *
 * leaderboards.test.ts covers getMyRank / getStatistics / getLLMLeaderboard /
 * getLLMModelDetails but NEVER calls:
 *  - getAnnotatorLeaderboard
 *  - getCoCreationLeaderboard
 * and never exercises the getLLMLeaderboard `search` /
 * `min_generation_count` / `min_samples_evaluated` query-param branches.
 *
 * Mirrors leaderboards.test.ts exactly: jest.mock('../base', ...) returns the
 * built URL via `{ _url: url }`.
 */

import { LeaderboardsClient } from '../leaderboards'

jest.mock('../base', () => ({
  BaseApiClient: class MockBaseApiClient {
    async get(url: string): Promise<any> {
      return { _url: url }
    }
  },
}))

describe('LeaderboardsClient - uncovered methods/branches', () => {
  let client: LeaderboardsClient

  beforeEach(() => {
    client = new LeaderboardsClient()
  })

  describe('getAnnotatorLeaderboard', () => {
    it('hits /leaderboards/annotators with no params', async () => {
      const result = await client.getAnnotatorLeaderboard()
      expect((result as any)._url).toBe('/leaderboards/annotators?')
    })

    it('appends repeated project_ids', async () => {
      const result = await client.getAnnotatorLeaderboard({
        project_ids: ['p1', 'p2'],
      })
      const url = (result as any)._url
      expect(url).toContain('project_ids=p1')
      expect(url).toContain('project_ids=p2')
    })

    it('does not append project_ids for an empty array', async () => {
      const result = await client.getAnnotatorLeaderboard({ project_ids: [] })
      expect((result as any)._url).not.toContain('project_ids')
    })

    it('appends period, metric, aggregation, limit and offset', async () => {
      const result = await client.getAnnotatorLeaderboard({
        period: 'weekly',
        metric: 'accuracy',
        aggregation: 'sum',
        limit: 25,
        offset: 10,
      })
      const url = (result as any)._url
      expect(url).toContain('period=weekly')
      expect(url).toContain('metric=accuracy')
      expect(url).toContain('aggregation=sum')
      expect(url).toContain('limit=25')
      expect(url).toContain('offset=10')
    })

    it('appends offset=0 (offset uses !== undefined, not truthiness)', async () => {
      const result = await client.getAnnotatorLeaderboard({ offset: 0 })
      expect((result as any)._url).toContain('offset=0')
    })

    it('omits limit when limit is 0 (falsy)', async () => {
      const result = await client.getAnnotatorLeaderboard({ limit: 0 })
      expect((result as any)._url).not.toContain('limit=')
    })
  })

  describe('getCoCreationLeaderboard', () => {
    it('hits /leaderboards/co-creation with no params', async () => {
      const result = await client.getCoCreationLeaderboard()
      expect((result as any)._url).toBe('/leaderboards/co-creation?')
    })

    it('appends all supported params together', async () => {
      const result = await client.getCoCreationLeaderboard({
        project_ids: ['p1'],
        period: 'monthly',
        metric: 'rouge',
        aggregation: 'average',
        limit: 5,
        offset: 2,
      })
      const url = (result as any)._url
      expect(url).toContain('/leaderboards/co-creation?')
      expect(url).toContain('project_ids=p1')
      expect(url).toContain('period=monthly')
      expect(url).toContain('metric=rouge')
      expect(url).toContain('aggregation=average')
      expect(url).toContain('limit=5')
      expect(url).toContain('offset=2')
    })

    it('omits project_ids when the array is empty', async () => {
      const result = await client.getCoCreationLeaderboard({ project_ids: [] })
      expect((result as any)._url).not.toContain('project_ids')
    })
  })

  describe('getLLMLeaderboard - search/min filter branches', () => {
    it('appends the search param', async () => {
      const result = await client.getLLMLeaderboard({ search: 'gpt' })
      expect((result as any)._url).toContain('search=gpt')
    })

    it('appends min_generation_count when defined', async () => {
      const result = await client.getLLMLeaderboard({
        min_generation_count: 5,
      })
      expect((result as any)._url).toContain('min_generation_count=5')
    })

    it('appends min_generation_count=0 (uses !== undefined)', async () => {
      const result = await client.getLLMLeaderboard({
        min_generation_count: 0,
      })
      expect((result as any)._url).toContain('min_generation_count=0')
    })

    it('appends min_samples_evaluated when defined', async () => {
      const result = await client.getLLMLeaderboard({
        min_samples_evaluated: 12,
      })
      expect((result as any)._url).toContain('min_samples_evaluated=12')
    })

    it('appends min_samples_evaluated=0 (uses !== undefined)', async () => {
      const result = await client.getLLMLeaderboard({
        min_samples_evaluated: 0,
      })
      expect((result as any)._url).toContain('min_samples_evaluated=0')
    })

    it('omits search/min filters when not supplied', async () => {
      const result = await client.getLLMLeaderboard({})
      const url = (result as any)._url
      expect(url).not.toContain('search=')
      expect(url).not.toContain('min_generation_count')
      expect(url).not.toContain('min_samples_evaluated')
    })
  })
})

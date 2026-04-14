/**
 * @jest-environment jsdom
 */
import '@testing-library/jest-dom'
import { render, screen, waitFor } from '@testing-library/react'

const mockGetLLMLeaderboard = jest.fn()

jest.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 'u1', name: 'Test', is_superadmin: true },
    apiClient: {
      leaderboards: { getLLMLeaderboard: mockGetLLMLeaderboard },
    },
  }),
}))
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({ t: (key: string) => key, locale: 'en' }),
}))
jest.mock('@/hooks/useProjects', () => ({
  useProjects: () => ({ projects: [], loading: false, fetchProjects: jest.fn() }),
}))
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: jest.fn() }),
  useSearchParams: () => ({ get: jest.fn() }),
}))

import { LLMLeaderboardTable } from '../LLMLeaderboardTable'

const emptyResponse = {
  leaderboard: [],
  total_models: 0,
  available_metrics: [],
  available_evaluation_types: [],
  filters: {
    project_ids: [],
    period: 'overall',
    metric: 'average',
    aggregation: 'average',
    evaluation_types: [],
    include_all_models: false,
    limit: 20,
  },
  confidence_intervals_available: false,
}

const dataResponse = {
  ...emptyResponse,
  leaderboard: [
    {
      rank: 1,
      model_id: 'gpt-4o',
      model_name: 'GPT-4o',
      provider: 'openai',
      evaluation_count: 10,
      samples_evaluated: 500,
      metrics: { accuracy: 0.92 },
      average_score: 0.9,
      ci_lower: 0.85,
      ci_upper: 0.95,
      last_evaluated: '2026-01-15T10:00:00Z',
    },
  ],
  total_models: 1,
  available_metrics: ['accuracy'],
  confidence_intervals_available: true,
}

describe('LLMLeaderboardTable', () => {
  afterEach(() => {
    mockGetLLMLeaderboard.mockReset()
  })

  it('renders and calls API on mount', async () => {
    mockGetLLMLeaderboard.mockResolvedValue(emptyResponse)
    render(<LLMLeaderboardTable />)
    await waitFor(() => {
      expect(mockGetLLMLeaderboard).toHaveBeenCalled()
    })
  })

  it('renders model data when API returns results', async () => {
    mockGetLLMLeaderboard.mockResolvedValue(dataResponse)
    const { container } = render(<LLMLeaderboardTable />)
    await waitFor(() => {
      expect(container.textContent).toContain('GPT-4o')
      expect(container.textContent).toContain('openai')
    }, { timeout: 5000 })
  })

  it('handles empty leaderboard without crash', async () => {
    mockGetLLMLeaderboard.mockResolvedValue(emptyResponse)
    const { container } = render(<LLMLeaderboardTable />)
    await waitFor(() => {
      expect(mockGetLLMLeaderboard).toHaveBeenCalled()
    })
    expect(container).toBeTruthy()
  })

  it('handles API error gracefully', async () => {
    mockGetLLMLeaderboard.mockRejectedValue(new Error('Network error'))
    const { container } = render(<LLMLeaderboardTable />)
    await waitFor(() => {
      expect(mockGetLLMLeaderboard).toHaveBeenCalled()
    })
    expect(container).toBeTruthy()
  })

  it('calls API with period and metric params', async () => {
    mockGetLLMLeaderboard.mockResolvedValue(emptyResponse)
    render(<LLMLeaderboardTable />)
    await waitFor(() => {
      expect(mockGetLLMLeaderboard).toHaveBeenCalled()
    })
    // First call should include default params
    const firstCall = mockGetLLMLeaderboard.mock.calls[0][0]
    expect(firstCall.period).toBe('overall')
    expect(firstCall.include_all_models).toBe(true)
  })
})

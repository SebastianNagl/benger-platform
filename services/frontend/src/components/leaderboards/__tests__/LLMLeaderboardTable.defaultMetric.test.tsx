/**
 * @jest-environment jsdom
 *
 * The metric the LLM leaderboard opens on: the overlay's grade points while
 * the overlay that defines them is active, a platform metric otherwise (the
 * community edition, or the overlay switched off), never a metric no run of
 * this edition can produce.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '@testing-library/jest-dom'
import { act, render, waitFor } from '@testing-library/react'

import { registerMetric } from '@/lib/api/evaluation-types'
import {
  _resetActiveExtensionsForTests,
  setActiveExtensions,
} from '@/lib/extensions/active'
import { setRegistrationOwner } from '@/lib/extensions/owner'

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
  useProjects: () => ({
    projects: [],
    loading: false,
    fetchProjects: jest.fn(),
  }),
}))
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: jest.fn() }),
  useSearchParams: () => ({ get: jest.fn() }),
}))

import { LLMLeaderboardTable } from '../LLMLeaderboardTable'

const GRADE_POINTS = 'llm_judge_falloesung_grade_points'

const response = {
  leaderboard: [],
  total_models: 0,
  available_metrics: [],
  available_evaluation_types: [],
  confidence_intervals_available: false,
}

function renderTable() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0, staleTime: 0 } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <LLMLeaderboardTable />
    </QueryClientProvider>,
  )
}

const requestedMetrics = () =>
  mockGetLLMLeaderboard.mock.calls.map(([params]) => params.metric)

describe('LLMLeaderboardTable default metric', () => {
  beforeEach(() => {
    mockGetLLMLeaderboard.mockReset()
    mockGetLLMLeaderboard.mockResolvedValue(response)
    _resetActiveExtensionsForTests()
  })

  it('opens on a platform metric without the overlay', async () => {
    renderTable()
    await waitFor(() => expect(mockGetLLMLeaderboard).toHaveBeenCalled())
    expect(requestedMetrics()).not.toContain(GRADE_POINTS)
    expect(requestedMetrics()[0]).toBe('accuracy')
  })

  describe('with the overlay that defines the grade points', () => {
    beforeAll(() => {
      setRegistrationOwner('extended')
      registerMetric(GRADE_POINTS, {
        name: GRADE_POINTS,
        display_name: 'Notenpunkte',
        description: '',
        category: 'LLM-as-Judge',
        status: 'stable',
        supports_parameters: false,
        display_scale: '0-18',
      })
      setRegistrationOwner(null)
    })

    it('opens on its grade points while it is active', async () => {
      setActiveExtensions(['extended'])
      renderTable()
      await waitFor(() => expect(mockGetLLMLeaderboard).toHaveBeenCalled())
      expect(requestedMetrics()[0]).toBe(GRADE_POINTS)
    })

    it('switches to the grade points once the overlay turns active', async () => {
      renderTable()
      await waitFor(() => expect(mockGetLLMLeaderboard).toHaveBeenCalled())
      act(() => setActiveExtensions(['extended']))
      await waitFor(() => expect(requestedMetrics()).toContain(GRADE_POINTS))
    })

    it('opens on a platform metric while it is switched off', async () => {
      renderTable()
      await waitFor(() => expect(mockGetLLMLeaderboard).toHaveBeenCalled())
      expect(requestedMetrics()).not.toContain(GRADE_POINTS)
    })
  })
})

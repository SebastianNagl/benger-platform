import { act, renderHook, waitFor } from '@testing-library/react'

import { apiClient } from '@/lib/api/client'

import { useResultsData } from '../useResultsData'

jest.mock('@/lib/api/client', () => ({
  apiClient: {
    getProjectEvaluationResults: jest.fn(),
  },
}))
jest.mock('@/lib/auth/sessionExpired', () => ({
  redirectToLoginAsExpired: jest.fn(),
}))

const getResults = apiClient.getProjectEvaluationResults as jest.Mock

const payload = (status: string) => ({
  project_id: 'p1',
  evaluations: [{ evaluation_id: 'e1', status }],
  total_count: 1,
})

describe('useResultsData GET cache use', () => {
  afterEach(() => {
    jest.useRealTimers()
    getResults.mockReset()
  })

  it('may use the cache for the first load only; polls, refreshKey bumps and refetch go past it', async () => {
    jest.useFakeTimers()
    getResults.mockResolvedValue(payload('running'))

    const { result, rerender } = renderHook(
      ({ refreshKey }) =>
        useResultsData({
          projectId: 'p1',
          refreshKey,
          showHistory: false,
          failedLoadMessage: 'failed',
        }),
      { initialProps: { refreshKey: 0 } },
    )

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(getResults).toHaveBeenNthCalledWith(1, 'p1', false, undefined)

    // 5 s poll while a run is in flight.
    await act(async () => {
      await jest.advanceTimersByTimeAsync(5000)
    })
    expect(getResults).toHaveBeenLastCalledWith('p1', false, {
      cache: 'no-store',
    })

    // Parent-driven refresh (WebSocket tick).
    getResults.mockClear()
    rerender({ refreshKey: 1 })
    await waitFor(() => expect(getResults).toHaveBeenCalled())
    expect(getResults).toHaveBeenLastCalledWith('p1', false, {
      cache: 'no-store',
    })

    // Manual refetch, with a stable identity across renders.
    const refetch = result.current.refetch
    getResults.mockClear()
    await act(async () => {
      await result.current.refetch()
    })
    expect(getResults).toHaveBeenLastCalledWith('p1', false, {
      cache: 'no-store',
    })
    rerender({ refreshKey: 1 })
    expect(result.current.refetch).toBe(refetch)
  })
})

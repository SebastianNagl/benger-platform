import { renderHook, waitFor } from '@testing-library/react'

import { apiClient } from '@/lib/api/client'

import { useTaskModelData } from '../useResultsData'

jest.mock('@/lib/api/client', () => ({
  apiClient: {
    getProjectResultsByTaskModel: jest.fn(),
  },
}))
jest.mock('@/lib/auth/sessionExpired', () => ({
  redirectToLoginAsExpired: jest.fn(),
}))

const getByTaskModel = apiClient.getProjectResultsByTaskModel as jest.Mock

const matrix = {
  project_id: 'p-enabled',
  models: [],
  model_names: {},
  tasks: [],
  summary: {},
}

describe('useTaskModelData enabled gate', () => {
  afterEach(() => getByTaskModel.mockReset())

  it('sends no unscoped request while a method is still being selected', async () => {
    getByTaskModel.mockResolvedValue(matrix)

    const { result, rerender } = renderHook(
      (props: { configId: string; metric: string; enabled: boolean }) =>
        useTaskModelData({
          projectId: 'p-enabled',
          showHistory: true,
          selectedConfigId: props.configId,
          selectedMetricKey: props.metric,
          hasInflightSelectedRun: false,
          enabled: props.enabled,
        }),
      { initialProps: { configId: '', metric: '', enabled: false } },
    )

    expect(getByTaskModel).not.toHaveBeenCalled()
    expect(result.current.taskModelLoading).toBe(false)

    rerender({ configId: 'meteor-abc', metric: 'meteor', enabled: true })

    await waitFor(() => expect(result.current.taskModelData).toEqual(matrix))
    expect(getByTaskModel).toHaveBeenCalledTimes(1)
    expect(getByTaskModel).toHaveBeenCalledWith(
      'p-enabled',
      undefined,
      true,
      'meteor',
      'meteor-abc',
      expect.objectContaining({ signal: expect.anything() }),
    )
  })

  it('fetches unscoped when enabled without a method (project with no methods)', async () => {
    getByTaskModel.mockResolvedValue(matrix)

    renderHook(() =>
      useTaskModelData({
        projectId: 'p-no-methods',
        showHistory: false,
        selectedConfigId: '',
        selectedMetricKey: '',
        hasInflightSelectedRun: false,
      }),
    )

    await waitFor(() => expect(getByTaskModel).toHaveBeenCalledTimes(1))
    expect(getByTaskModel).toHaveBeenCalledWith(
      'p-no-methods',
      undefined,
      false,
      null,
      null,
      expect.objectContaining({ signal: expect.anything() }),
    )
  })
})

import { putEvaluationConfigs } from '../evaluationConfig'

const mockPut = jest.fn()
jest.mock('../client', () => ({
  apiClient: { put: (...args: unknown[]) => mockPut(...args) },
}))

describe('putEvaluationConfigs', () => {
  beforeEach(() => mockPut.mockReset().mockResolvedValue({ warnings: [] }))

  it('sends the base the writer last read along with the list', async () => {
    const configs = [{ id: 'c', metric_parameters: { threshold: 2 } }]
    const base = [{ id: 'c', metric_parameters: {} }]
    await expect(putEvaluationConfigs('p1', configs, base)).resolves.toEqual({
      warnings: [],
    })
    expect(mockPut).toHaveBeenCalledWith(
      '/evaluations/projects/p1/evaluation-config',
      { evaluation_configs: configs, evaluation_configs_base: base },
    )
  })

  it('sends the list alone when the writer has read nothing yet', async () => {
    await putEvaluationConfigs('p1', [], null)
    expect(mockPut).toHaveBeenCalledWith(
      '/evaluations/projects/p1/evaluation-config',
      { evaluation_configs: [] },
    )
  })
})

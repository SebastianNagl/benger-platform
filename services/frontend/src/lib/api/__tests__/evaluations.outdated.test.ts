/**
 * The outdated-gradings read and the re-grade flag of a run request
 * (shared/grading_basis.py on the server).
 */

import { EvaluationsClient } from '../evaluations'

const mockRequest = jest.fn()

jest.mock('../base', () => ({
  BaseApiClient: class MockBaseApiClient {
    protected request(url: string, options?: RequestInit) {
      return mockRequest(url, options)
    }
  },
}))

beforeEach(() => mockRequest.mockReset())

describe('EvaluationsClient re-grading', () => {
  it('reads how many gradings rest on an older basis', async () => {
    const body = { project_id: 'p1', total: 2, ai: 2, human: 0, configs: [] }
    mockRequest.mockResolvedValue(body)

    await expect(
      new EvaluationsClient().getOutdatedGradings('p1'),
    ).resolves.toBe(body)
    expect(mockRequest).toHaveBeenCalledWith(
      '/evaluations/projects/p1/outdated-gradings',
      undefined,
    )
  })

  it('starts a re-grade with outdated_only', async () => {
    mockRequest.mockResolvedValue({ evaluation_id: 'e1' })

    await new EvaluationsClient().runEvaluation({
      project_id: 'p1',
      evaluation_configs: [],
      outdated_only: true,
    })

    const [url, options] = mockRequest.mock.calls[0]
    expect(url).toBe('/evaluations/run')
    expect(JSON.parse(options.body)).toMatchObject({ outdated_only: true })
  })
})

/**
 * The old analysis routes redirect permanently to their places under
 * /evaluations.
 */

import { permanentRedirect } from 'next/navigation'
import AnalysisRunRedirect from '../[runId]/page'
import ProjectAnalysisRedirect from '../page'

jest.mock('next/navigation', () => ({
  permanentRedirect: jest.fn(),
}))

const redirects = () =>
  (permanentRedirect as jest.Mock).mock.calls.map(([url]) => url)

describe('old analysis routes', () => {
  beforeEach(() => jest.clearAllMocks())

  it('sends /projects/{id}/analysis to the Analyses view', async () => {
    await ProjectAnalysisRedirect({
      params: Promise.resolve({ id: 'p1' }),
      searchParams: Promise.resolve({}),
    })
    expect(redirects()).toEqual(['/evaluations?projectId=p1&type=analysis'])
  })

  it('turns ?from={runId} into the prefilled start dialog', async () => {
    await ProjectAnalysisRedirect({
      params: Promise.resolve({ id: 'p1' }),
      searchParams: Promise.resolve({ from: 'run-7' }),
    })
    expect(redirects()).toEqual([
      '/evaluations?projectId=p1&type=analysis&newRunFrom=run-7',
    ])
  })

  it('ignores a repeated or empty ?from', async () => {
    await ProjectAnalysisRedirect({
      params: Promise.resolve({ id: 'p1' }),
      searchParams: Promise.resolve({ from: ['a', 'b'] }),
    })
    await ProjectAnalysisRedirect({
      params: Promise.resolve({ id: 'p1' }),
      searchParams: Promise.resolve({ from: '' }),
    })
    expect(redirects()).toEqual([
      '/evaluations?projectId=p1&type=analysis',
      '/evaluations?projectId=p1&type=analysis',
    ])
  })

  it('sends /projects/{id}/analysis/{runId} to the run page', async () => {
    await AnalysisRunRedirect({
      params: Promise.resolve({ id: 'p1', runId: 'run 7/x' }),
    })
    expect(redirects()).toEqual(['/evaluations/analysis/run%207%2Fx'])
  })
})

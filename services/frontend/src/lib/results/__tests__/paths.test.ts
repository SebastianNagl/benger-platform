import { analysisRunPath, evaluationsPath, resultTypeOf } from '../paths'

describe('result paths', () => {
  it('builds the analysis run page path', () => {
    expect(analysisRunPath('run-1')).toBe('/evaluations/analysis/run-1')
    expect(analysisRunPath('a b/c')).toBe('/evaluations/analysis/a%20b%2Fc')
  })

  it('builds the evaluations page path per result type', () => {
    expect(evaluationsPath()).toBe('/evaluations')
    expect(evaluationsPath({ projectId: 'p1' })).toBe(
      '/evaluations?projectId=p1',
    )
    expect(evaluationsPath({ projectId: 7, type: 'metrics', run: 'r' })).toBe(
      '/evaluations?projectId=7',
    )
    expect(
      evaluationsPath({ projectId: 'p1', type: 'analysis', run: 'r1' }),
    ).toBe('/evaluations?projectId=p1&type=analysis&run=r1')
    expect(
      evaluationsPath({
        projectId: 'p&1',
        type: 'analysis',
        newRunFrom: 'r 2',
      }),
    ).toBe('/evaluations?projectId=p%261&type=analysis&newRunFrom=r+2')
    expect(evaluationsPath({ projectId: null, type: 'analysis' })).toBe(
      '/evaluations?type=analysis',
    )
  })

  it('reads the result type of a URL value', () => {
    expect(resultTypeOf('analysis')).toBe('analysis')
    expect(resultTypeOf(null)).toBe('metrics')
    expect(resultTypeOf('automated')).toBe('metrics')
  })
})

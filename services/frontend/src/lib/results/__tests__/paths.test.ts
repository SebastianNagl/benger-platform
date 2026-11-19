import {
  analysisRunPath,
  evaluationsPath,
  legacyAnalysisPath,
  resultTypeOf,
} from '../paths'

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

  it('maps the three old analysis URLs to their new places', () => {
    const none = new URLSearchParams()
    expect(legacyAnalysisPath('/projects/p1/analysis', none)).toBe(
      '/evaluations?projectId=p1&type=analysis',
    )
    expect(legacyAnalysisPath('/projects/p1/analysis/', none)).toBe(
      '/evaluations?projectId=p1&type=analysis',
    )
    expect(
      legacyAnalysisPath(
        '/projects/p1/analysis',
        new URLSearchParams('from=run-7&x=1'),
      ),
    ).toBe('/evaluations?projectId=p1&type=analysis&newRunFrom=run-7')
    expect(
      legacyAnalysisPath('/projects/p1/analysis', new URLSearchParams('from=')),
    ).toBe('/evaluations?projectId=p1&type=analysis')
    expect(legacyAnalysisPath('/projects/p1/analysis/run-7', none)).toBe(
      '/evaluations/analysis/run-7',
    )
    // Encoded segments are not encoded twice; a malformed one passes as is.
    expect(legacyAnalysisPath('/projects/p1/analysis/run%207', none)).toBe(
      '/evaluations/analysis/run%207',
    )
    expect(legacyAnalysisPath('/projects/p%2/analysis', none)).toBe(
      '/evaluations?projectId=p%252&type=analysis',
    )
  })

  it('leaves every other path alone', () => {
    const none = new URLSearchParams()
    for (const path of [
      '/projects/p1',
      '/projects/p1/analysis/run-7/x',
      '/projects/p1/analysisx',
      '/evaluations/analysis/run-7',
      '/analysis',
    ]) {
      expect(legacyAnalysisPath(path, none)).toBeNull()
    }
  })
})

/**
 * @jest-environment jsdom
 *
 * Branch coverage for universalImport.ts - 6 uncovered branches.
 * Focuses on detectFileFormat with different file types.
 */

import { detectFileFormat } from '../universalImport'

describe('detectFileFormat', () => {
  function makeFile(name: string): File {
    return new File([''], name, { type: '' })
  }

  it('detects json from .json extension', () => {
    expect(detectFileFormat(makeFile('data.json'))).toBe('json')
  })

  it('detects json from .jsonl extension', () => {
    expect(detectFileFormat(makeFile('data.jsonl'))).toBe('json')
  })

  it('detects csv from .csv extension', () => {
    expect(detectFileFormat(makeFile('data.csv'))).toBe('csv')
  })

  it('detects tsv from .tsv extension', () => {
    expect(detectFileFormat(makeFile('data.tsv'))).toBe('tsv')
  })

  it('detects tsv from .txt extension', () => {
    expect(detectFileFormat(makeFile('data.txt'))).toBe('tsv')
  })

  it('detects excel from .xlsx extension', () => {
    expect(detectFileFormat(makeFile('data.xlsx'))).toBe('excel')
  })

  it('detects excel from .xls extension', () => {
    expect(detectFileFormat(makeFile('data.xls'))).toBe('excel')
  })

  it('detects json from content when no extension match', () => {
    expect(detectFileFormat(makeFile('data.unknown'), '{"key": "value"}')).toBe('json')
  })

  it('returns unknown for unrecognized format', () => {
    expect(detectFileFormat(makeFile('data.xyz'))).toBe('unknown')
  })

  it('detects CSV from content with commas', () => {
    expect(detectFileFormat(makeFile('data'), 'a,b,c\n1,2,3')).toBe('csv')
  })

  it('handles file with no extension', () => {
    expect(detectFileFormat(makeFile('datafile'))).toBe('unknown')
  })
})

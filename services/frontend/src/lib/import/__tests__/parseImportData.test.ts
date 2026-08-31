/**
 * Tests for the shared import-parsing lib (lib/import/parseImportData):
 * format detection, column extraction, Label-Studio row wrapping across
 * JSON / envelope / qa_samples / questions / CSV / TSV / TXT, and the
 * nested-import envelope File assembly.
 */

import {
  buildImportFile,
  detectFormat,
  extractColumns,
  parseImportData,
} from '../parseImportData'

describe('detectFormat', () => {
  it('prefers a known file extension over content sniffing', () => {
    expect(detectFormat('a,b\n1,2', 'data.tsv')).toBe('tsv')
    expect(detectFormat('plain prose', 'data.json')).toBe('json')
    expect(detectFormat('[{"a":1}]', 'notes.txt')).toBe('txt')
    expect(detectFormat('x\ty', 'table.csv')).toBe('csv')
  })

  it('ignores unknown extensions and sniffs the content', () => {
    expect(detectFormat('[{"a":1}]', 'data.weird')).toBe('json')
  })

  it('sniffs JSON from a leading brace or bracket', () => {
    expect(detectFormat('{"a":1}')).toBe('json')
    expect(detectFormat('  [1,2]')).toBe('json')
  })

  it('sniffs TSV from a tab in the first line', () => {
    expect(detectFormat('col1\tcol2\nv1\tv2')).toBe('tsv')
  })

  it('sniffs CSV from a comma in the first line', () => {
    expect(detectFormat('col1,col2\nv1,v2')).toBe('csv')
  })

  it('falls back to TXT for plain prose', () => {
    expect(detectFormat('plain prose without delimiters')).toBe('txt')
    expect(detectFormat('')).toBe('txt')
  })
})

describe('extractColumns', () => {
  it('returns [] for empty content', () => {
    expect(extractColumns('')).toEqual([])
    expect(extractColumns('   ')).toEqual([])
  })

  it('extracts keys from the first item of a JSON array', () => {
    expect(
      extractColumns(JSON.stringify([{ question: 'q', answer: 'a' }]))
    ).toEqual(['question', 'answer'])
  })

  it('unwraps qa_samples and questions wrappers', () => {
    expect(
      extractColumns(JSON.stringify({ qa_samples: [{ q: '1', a: '2' }] }))
    ).toEqual(['q', 'a'])
    expect(
      extractColumns(JSON.stringify({ questions: [{ text: 'x' }] }))
    ).toEqual(['text'])
  })

  it('extracts TSV headers', () => {
    expect(extractColumns('col1\tcol2\nv1\tv2')).toEqual(['col1', 'col2'])
  })

  it('extracts CSV headers and strips surrounding quotes', () => {
    expect(extractColumns('"name","age"\nx,1')).toEqual(['name', 'age'])
  })

  it('returns [] for plain text and for invalid JSON', () => {
    expect(extractColumns('just some prose')).toEqual([])
    expect(extractColumns('{invalid json')).toEqual([])
  })
})

describe('parseImportData — JSON', () => {
  it('wraps plain-array items in a data field', () => {
    const { rows, extras } = parseImportData(
      JSON.stringify([{ text: 'a' }, { text: 'b' }]),
      'json'
    )
    expect(rows).toEqual([{ data: { text: 'a' } }, { data: { text: 'b' } }])
    expect(extras).toEqual({})
  })

  it('keeps items that already carry an object data field as-is', () => {
    const { rows } = parseImportData(
      JSON.stringify([
        { data: { text: 'wrapped' }, annotations: [1] },
        { text: 'bare' },
      ]),
      'json'
    )
    expect(rows).toEqual([
      { data: { text: 'wrapped' }, annotations: [1] },
      { data: { text: 'bare' } },
    ])
  })

  it('unwraps a qa_samples wrapper', () => {
    const { rows } = parseImportData(
      JSON.stringify({ qa_samples: [{ q: '1' }] }),
      'json'
    )
    expect(rows).toEqual([{ data: { q: '1' } }])
  })

  it('unwraps a questions wrapper preferring question_data', () => {
    const { rows } = parseImportData(
      JSON.stringify({
        questions: [{ question_data: { text: 'inner' } }, { text: 'outer' }],
      }),
      'json'
    )
    expect(rows).toEqual([
      { data: { text: 'inner' } },
      { data: { text: 'outer' } },
    ])
  })

  it('splits the bulk-export envelope into task rows + extras', () => {
    const envelope = {
      tasks: [{ data: { text: 't1' } }, { plain: 'row' }],
      evaluation_runs: [{ id: 'er1' }],
      korrektur_comments: [{ id: 'kc1' }],
      human_evaluation_configs: [],
      unrelated_key: [{ id: 'nope' }],
    }
    const { rows, extras } = parseImportData(JSON.stringify(envelope), 'json')
    expect(rows).toEqual([
      { data: { text: 't1' } },
      { data: { plain: 'row' } },
    ])
    expect(extras).toEqual({
      evaluation_runs: [{ id: 'er1' }],
      korrektur_comments: [{ id: 'kc1' }],
      human_evaluation_configs: [],
    })
  })

  it('wraps a single JSON object into one row', () => {
    const { rows } = parseImportData('{"text": "single"}', 'json')
    expect(rows).toEqual([{ data: { text: 'single' } }])
  })

  it('throws an Invalid JSON error for malformed JSON', () => {
    expect(() => parseImportData('{invalid', 'json')).toThrow(
      /Invalid JSON format/
    )
  })
})

describe('parseImportData — CSV/TSV/TXT', () => {
  it('parses CSV with quoted headers and values', () => {
    const { rows } = parseImportData('"name","age"\n"Alice",30\nBob,', 'csv')
    expect(rows).toEqual([
      { data: { name: 'Alice', age: '30' } },
      { data: { name: 'Bob', age: '' } },
    ])
  })

  it('parses TSV rows', () => {
    const { rows } = parseImportData('name\tvalue\nAlice\t100\nBob\t200', 'tsv')
    expect(rows).toEqual([
      { data: { name: 'Alice', value: '100' } },
      { data: { name: 'Bob', value: '200' } },
    ])
  })

  it('returns no rows for empty CSV content', () => {
    expect(parseImportData('', 'csv').rows).toEqual([])
  })

  it('turns each non-empty TXT line into a task', () => {
    const { rows } = parseImportData('Line 1\n\n  Line 2  \n', 'txt')
    expect(rows).toEqual([
      { data: { text: 'Line 1' } },
      { data: { text: 'Line 2' } },
    ])
  })
})

describe('buildImportFile', () => {
  it('serializes rows + extras into a JSON envelope file', async () => {
    const rows = [{ data: { text: 'a' } }]
    const extras = { evaluation_runs: [{ id: 'er1' }] }
    const file = buildImportFile(rows, extras)

    expect(file.name).toMatch(/^import-\d+\.json$/)
    expect(file.type).toBe('application/json')
    expect(JSON.parse(await file.text())).toEqual({
      data: rows,
      evaluation_runs: [{ id: 'er1' }],
    })
  })

  it('defaults extras to an empty object', async () => {
    const file = buildImportFile([{ data: { x: 1 } }])
    expect(JSON.parse(await file.text())).toEqual({ data: [{ data: { x: 1 } }] })
  })

  it('round-trips parseImportData output through the envelope', async () => {
    const source = {
      tasks: [{ sachverhalt: 'Fall', musterloesung: 'Lsg' }],
      evaluation_runs: [{ id: 'er1' }],
    }
    const { rows, extras } = parseImportData(JSON.stringify(source), 'json')
    const file = buildImportFile(rows, extras)
    expect(JSON.parse(await file.text())).toEqual({
      data: [{ data: { sachverhalt: 'Fall', musterloesung: 'Lsg' } }],
      evaluation_runs: [{ id: 'er1' }],
    })
  })
})

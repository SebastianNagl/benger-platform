/**
 * Pure helpers of the wizard's draft mode: the saved state, the row hash and
 * the task-sync plan (match by position, keep / replace / re-import / import
 * / delete).
 */

import type { WizardDraftTask } from '@/lib/api/wizardDrafts'
import {
  affectedTasks,
  canonicalJson,
  draftImportRows,
  hashRows,
  planIsEmpty,
  planTaskSync,
  restoreWizardState,
  rowHash,
  serializeWizardState,
  sha256Hex,
} from '../draftSync'
import { INITIAL_WIZARD_DATA } from '../types'

const task = (
  id: string,
  rowIndex: number | null,
  hash: string | null,
  extra: Partial<WizardDraftTask> = {},
): WizardDraftTask => ({
  id,
  inner_id: rowIndex === null ? 99 : rowIndex + 1,
  row_index: rowIndex,
  row_hash: hash,
  sheets: [],
  generating: 0,
  ...extra,
})

describe('sha256Hex', () => {
  it('matches the FIPS 180-4 test vectors', () => {
    expect(sha256Hex('')).toBe(
      'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
    )
    expect(sha256Hex('abc')).toBe(
      'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad',
    )
    expect(
      sha256Hex('abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq'),
    ).toBe('248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1')
  })

  it('hashes the UTF-8 bytes, also beyond one block', () => {
    // Python: hashlib.sha256("Prüfung ✓ 𝄞".encode()).hexdigest()
    expect(sha256Hex('Prüfung ✓ 𝄞')).toBe(
      '9bf53db76a4342862eda5ee0f1dba7aa8175abea00605e40238a6a424204efcc',
    )
    expect(sha256Hex('a'.repeat(1000))).toBe(
      '41edece42d63e8d9bf515a9ba6932e1c20cbc9f5a5d134645adb5db1b9737ea3',
    )
    expect(sha256Hex('Prüfung')).not.toBe(sha256Hex('Prufung'))
  })
})

describe('canonicalJson and rowHash', () => {
  it('sorts keys at every level and drops undefined', () => {
    expect(
      canonicalJson({ b: 1, a: { d: [3, { z: 1, y: 2 }], c: undefined } }),
    ).toBe('{"a":{"d":[3,{"y":2,"z":1}]},"b":1}')
    expect(canonicalJson(undefined)).toBe('null')
    expect(canonicalJson('x')).toBe('"x"')
  })

  it('gives one hash per content whatever the key order', () => {
    expect(rowHash({ data: { a: 1, b: 2 } })).toBe(
      rowHash({ data: { b: 2, a: 1 } }),
    )
    expect(rowHash({ data: { a: 1 } })).not.toBe(rowHash({ data: { a: 2 } }))
  })
})

describe('serializeWizardState / restoreWizardState', () => {
  it('drops the File, keeps the import record and fills missing keys', () => {
    const file = new File(['x'], 'exam.json')
    const state = serializeWizardState(
      { ...INITIAL_WIZARD_DATA, title: 'K', selectedFile: file },
      { rowCount: 2, fileName: 'exam.json' },
    )
    expect(state.selectedFile).toBeUndefined()
    expect(state.title).toBe('K')
    expect(state.draftImport).toEqual({ rowCount: 2, fileName: 'exam.json' })

    const restored = restoreWizardState({
      ...state,
      features: { rubric: true },
      settings: { strict_timer_enabled: true },
      draftCloudImported: ['a', 3, 'b'],
    })
    expect(restored.data.selectedFile).toBeNull()
    expect(restored.data.features).toEqual({
      ...INITIAL_WIZARD_DATA.features,
      rubric: true,
    })
    expect(restored.data.settings.strict_timer_enabled).toBe(true)
    expect(restored.data.settings.assignment_mode).toBe('open')
    expect(restored.draftImport).toEqual({ rowCount: 2, fileName: 'exam.json' })
    expect(restored.cloudImported).toEqual(['a', 'b'])
    expect('draftImport' in restored.data).toBe(false)
  })

  it('restores an empty state to the initial wizard state', () => {
    const restored = restoreWizardState(null)
    expect(restored.data).toEqual(INITIAL_WIZARD_DATA)
    expect(restored.draftImport).toBeNull()
    expect(restored.cloudImported).toEqual([])
    expect(
      restoreWizardState({ draftCloudImported: 'x' }).cloudImported,
    ).toEqual([])
  })
})

describe('planTaskSync', () => {
  const rows = hashRows([
    { data: { sv: 'Fall 1' } },
    { data: { sv: 'Fall 2' } },
    { data: { sv: 'Fall 3' } },
  ])

  it('imports every row into an empty draft', () => {
    const plan = planTaskSync(rows, [])
    expect(plan.create.map((r) => r.index)).toEqual([0, 1, 2])
    expect(plan.keep).toEqual([])
    expect(planIsEmpty(plan)).toBe(false)
  })

  it('keeps tasks whose row is unchanged and is empty then', () => {
    const tasks = rows.map((r) => task(`t${r.index}`, r.index, r.hash))
    const plan = planTaskSync(rows, tasks)
    expect(plan.keep.map((k) => k.task.id)).toEqual(['t0', 't1', 't2'])
    expect(planIsEmpty(plan)).toBe(true)
  })

  it('replaces a changed row in place, imports new rows and deletes extra tasks', () => {
    const tasks = [
      task('t0', 0, rows[0].hash),
      task('t1', 1, 'old'),
      task('t2', 2, rows[2].hash),
      task('t3', 3, 'gone'),
      task('manual', null, null),
    ]
    const plan = planTaskSync(rows.slice(0, 2), tasks)
    expect(plan.keep.map((k) => k.task.id)).toEqual(['t0'])
    expect(plan.update.map((u) => u.task.id)).toEqual(['t1'])
    expect(plan.remove.map((t) => t.id).sort()).toEqual(['t2', 't3'])
    expect(plan.create).toEqual([])
    // A task the wizard did not import is never touched.
    expect(JSON.stringify(plan)).not.toContain('manual')
  })

  it('re-imports a changed row that carries more than its data', () => {
    const nested = hashRows([
      { data: { sv: 'Fall 1' }, annotations: [{ result: [] }] },
    ])
    const plan = planTaskSync(nested, [task('t0', 0, 'old')])
    expect(plan.update).toEqual([])
    expect(plan.remove.map((t) => t.id)).toEqual(['t0'])
    expect(plan.create.map((r) => r.index)).toEqual([0])
  })

  it('removes a duplicate task at one position', () => {
    const plan = planTaskSync(rows.slice(0, 1), [
      task('a', 0, rows[0].hash),
      task('b', 0, rows[0].hash),
    ])
    expect(plan.keep.map((k) => k.task.id)).toEqual(['a'])
    expect(plan.remove.map((t) => t.id)).toEqual(['b'])
  })

  it('imports a whole-file envelope again on any change', () => {
    const tasks = [task('t0', 0, rows[0].hash), task('t1', 1, 'old')]
    const plan = planTaskSync(rows.slice(0, 2), tasks, { wholeFile: true })
    expect(plan.create.map((r) => r.index)).toEqual([0, 1])
    expect(plan.remove.map((t) => t.id).sort()).toEqual(['t0', 't1'])
    const same = planTaskSync(
      rows.slice(0, 2),
      [task('t0', 0, rows[0].hash), task('t1', 1, rows[1].hash)],
      { wholeFile: true },
    )
    expect(planIsEmpty(same)).toBe(true)
  })

  it('names the changed or deleted tasks that hold sheets or generations', () => {
    const sheet = { id: 's', status: 'active', review_state: 'confirmed' }
    const plan = planTaskSync(rows.slice(0, 1), [
      task('t0', 0, 'old', { sheets: [sheet] }),
      task('t1', 1, 'x', { generating: 1 }),
      task('t2', 2, 'y'),
    ])
    expect(affectedTasks(plan).map((t) => t.id)).toEqual(['t0', 't1'])
  })
})

describe('draftImportRows', () => {
  it('carries the position as id and the hash and position in meta', () => {
    const rows = hashRows([
      { data: { sv: 'A' }, meta: { source: 'x' } },
      { id: 7, data: { sv: 'B' } },
      { id: 'export-uuid', data: { sv: 'C' } },
    ])
    const out = draftImportRows(rows)
    expect(out[0]).toEqual({
      id: 1,
      data: { sv: 'A' },
      meta: { source: 'x', wizard_row_hash: rows[0].hash, wizard_row_index: 0 },
    })
    expect(out[1].id).toBe(2)
    expect(out[2].id).toBe('export-uuid')
    expect(out[2].meta.wizard_row_index).toBe(2)
  })
})

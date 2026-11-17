/**
 * Pure helpers of the wizard's draft mode (CORE 2.55): what is saved of the
 * wizard state, the row hash, and how the rows of the data step are matched
 * to the tasks of the draft project.
 *
 * Task sync rule: every imported row carries its position and the SHA-256 of
 * its canonical JSON (`meta.wizard_row_index`, `meta.wizard_row_hash`). Rows
 * are matched to the draft's tasks by position:
 * - same position, same hash: the task and its sheets are kept;
 * - same position, other hash: the task's data is replaced in place (its
 *   sheets are set aside, they were made for other content); a row that
 *   carries more than its data (annotations, sheets, ...) is re-imported at
 *   its position instead;
 * - rows beyond the old count are imported;
 * - tasks beyond the new count are deleted.
 * A file whose envelope carries project-level extras (evaluation runs that
 * reference its task ids) is imported as a whole: any change re-imports
 * every row. Tasks the wizard did not import (no position) are never
 * touched. The plan is idempotent by hash, so a sync interrupted halfway
 * converges on the next run.
 */

import type { WizardDraftTask } from '@/lib/api/wizardDrafts'
import { INITIAL_WIZARD_DATA, type WizardData } from './types'

/** What the draft keeps of the import source, for the resume notice. */
export interface DraftImportRecord {
  /** Rows synced into the draft at the last sync. */
  rowCount: number
  /** The file they came from, or null for pasted / generated rows. */
  fileName: string | null
}

/** Wizard state as stored on the draft (JSON; a `File` cannot be saved). */
export type SerializedWizardState = Record<string, unknown> & {
  draftImport?: DraftImportRecord | null
}

export function serializeWizardState(
  data: WizardData,
  draftImport: DraftImportRecord | null,
): SerializedWizardState {
  const { selectedFile: _file, ...rest } = data
  const plain = JSON.parse(JSON.stringify(rest)) as SerializedWizardState
  plain.draftImport = draftImport
  return plain
}

export function restoreWizardState(state: Record<string, any> | null): {
  data: WizardData
  draftImport: DraftImportRecord | null
  /** Cloud-storage object keys already imported into the draft. */
  cloudImported: string[]
} {
  const {
    draftImport = null,
    draftCloudImported = [],
    ...saved
  } = (state ?? {}) as Record<string, any>
  const data: WizardData = {
    ...INITIAL_WIZARD_DATA,
    ...saved,
    features: { ...INITIAL_WIZARD_DATA.features, ...(saved.features ?? {}) },
    settings: { ...INITIAL_WIZARD_DATA.settings, ...(saved.settings ?? {}) },
    generationParameters: {
      ...INITIAL_WIZARD_DATA.generationParameters,
      ...(saved.generationParameters ?? {}),
    },
    selectedFile: null,
  }
  return {
    data,
    draftImport: draftImport as DraftImportRecord | null,
    cloudImported: Array.isArray(draftCloudImported)
      ? draftCloudImported.filter((k): k is string => typeof k === 'string')
      : [],
  }
}

/** JSON with object keys sorted at every level (the hash input). */
export function canonicalJson(value: unknown): string {
  if (value === null || typeof value !== 'object') {
    return JSON.stringify(value === undefined ? null : value)
  }
  if (Array.isArray(value)) {
    return `[${value.map((v) => canonicalJson(v)).join(',')}]`
  }
  const obj = value as Record<string, unknown>
  const keys = Object.keys(obj)
    .filter((k) => obj[k] !== undefined)
    .sort()
  return `{${keys.map((k) => `${JSON.stringify(k)}:${canonicalJson(obj[k])}`).join(',')}}`
}

// SHA-256 (FIPS 180-4) over the UTF-8 bytes of a string. Pure, so the hash
// is the same in every browser and in tests (WebCrypto is async and absent
// on plain-http origins; TextEncoder is absent in some test environments).
const K = new Uint32Array([
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1,
  0x923f82a4, 0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
  0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786,
  0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147,
  0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
  0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b,
  0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a,
  0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
  0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
])

function utf8(text: string): Uint8Array {
  const out: number[] = []
  for (const ch of text) {
    const cp = ch.codePointAt(0) as number
    if (cp < 0x80) out.push(cp)
    else if (cp < 0x800) out.push(0xc0 | (cp >> 6), 0x80 | (cp & 0x3f))
    else if (cp < 0x10000)
      out.push(0xe0 | (cp >> 12), 0x80 | ((cp >> 6) & 0x3f), 0x80 | (cp & 0x3f))
    else
      out.push(
        0xf0 | (cp >> 18),
        0x80 | ((cp >> 12) & 0x3f),
        0x80 | ((cp >> 6) & 0x3f),
        0x80 | (cp & 0x3f),
      )
  }
  return Uint8Array.from(out)
}

export function sha256Hex(text: string): string {
  const bytes = utf8(text)
  const bitLength = bytes.length * 8
  const padded = new Uint8Array(((bytes.length + 9 + 63) >> 6) << 6)
  padded.set(bytes)
  padded[bytes.length] = 0x80
  const view = new DataView(padded.buffer)
  view.setUint32(padded.length - 8, Math.floor(bitLength / 0x100000000))
  view.setUint32(padded.length - 4, bitLength >>> 0)
  const h = new Uint32Array([
    0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c,
    0x1f83d9ab, 0x5be0cd19,
  ])
  const w = new Uint32Array(64)
  const rotr = (x: number, n: number) => (x >>> n) | (x << (32 - n))
  for (let offset = 0; offset < padded.length; offset += 64) {
    for (let i = 0; i < 16; i++) w[i] = view.getUint32(offset + i * 4)
    for (let i = 16; i < 64; i++) {
      const s0 = rotr(w[i - 15], 7) ^ rotr(w[i - 15], 18) ^ (w[i - 15] >>> 3)
      const s1 = rotr(w[i - 2], 17) ^ rotr(w[i - 2], 19) ^ (w[i - 2] >>> 10)
      w[i] = (w[i - 16] + s0 + w[i - 7] + s1) >>> 0
    }
    let [a, b, c, d, e, f, g, hh] = h
    for (let i = 0; i < 64; i++) {
      const S1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25)
      const ch = (e & f) ^ (~e & g)
      const t1 = (hh + S1 + ch + K[i] + w[i]) >>> 0
      const S0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22)
      const maj = (a & b) ^ (a & c) ^ (b & c)
      const t2 = (S0 + maj) >>> 0
      hh = g
      g = f
      f = e
      e = (d + t1) >>> 0
      d = c
      c = b
      b = a
      a = (t1 + t2) >>> 0
    }
    h[0] = (h[0] + a) >>> 0
    h[1] = (h[1] + b) >>> 0
    h[2] = (h[2] + c) >>> 0
    h[3] = (h[3] + d) >>> 0
    h[4] = (h[4] + e) >>> 0
    h[5] = (h[5] + f) >>> 0
    h[6] = (h[6] + g) >>> 0
    h[7] = (h[7] + hh) >>> 0
  }
  return Array.from(h, (x) => x.toString(16).padStart(8, '0')).join('')
}

export function rowHash(row: unknown): string {
  return sha256Hex(canonicalJson(row))
}

/** A parsed import row (Label Studio shape `{data, ...}`) with its hash. */
export interface HashedRow {
  index: number
  row: Record<string, any>
  hash: string
}

export function hashRows(rows: Record<string, any>[]): HashedRow[] {
  return rows.map((row, index) => ({ index, row, hash: rowHash(row) }))
}

const SIMPLE_ROW_KEYS = new Set(['data', 'meta', 'id'])

/** Whether a changed row can be applied by replacing the task's data. */
function isDataOnlyRow(row: Record<string, any>): boolean {
  return (
    !!row.data &&
    typeof row.data === 'object' &&
    !Array.isArray(row.data) &&
    Object.keys(row).every((k) => SIMPLE_ROW_KEYS.has(k))
  )
}

export interface TaskSyncPlan {
  keep: { task: WizardDraftTask; row: HashedRow }[]
  update: { task: WizardDraftTask; row: HashedRow }[]
  create: HashedRow[]
  remove: WizardDraftTask[]
}

export function planTaskSync(
  rows: HashedRow[],
  tasks: WizardDraftTask[],
  options: { wholeFile?: boolean } = {},
): TaskSyncPlan {
  const plan: TaskSyncPlan = { keep: [], update: [], create: [], remove: [] }
  const byIndex = new Map<number, WizardDraftTask>()
  for (const task of tasks) {
    if (task.row_index === null || task.row_index === undefined) continue
    if (task.row_index >= rows.length || byIndex.has(task.row_index)) {
      plan.remove.push(task)
    } else {
      byIndex.set(task.row_index, task)
    }
  }
  const changed = rows.some((r) => byIndex.get(r.index)?.row_hash !== r.hash)
  if (options.wholeFile && (changed || plan.remove.length > 0)) {
    return {
      keep: [],
      update: [],
      create: rows,
      remove: [...plan.remove, ...byIndex.values()],
    }
  }
  for (const row of rows) {
    const task = byIndex.get(row.index)
    if (!task) {
      plan.create.push(row)
    } else if (task.row_hash === row.hash) {
      plan.keep.push({ task, row })
    } else if (isDataOnlyRow(row.row)) {
      plan.update.push({ task, row })
    } else {
      plan.remove.push(task)
      plan.create.push(row)
    }
  }
  return plan
}

export function planIsEmpty(plan: TaskSyncPlan): boolean {
  return (
    plan.update.length === 0 &&
    plan.create.length === 0 &&
    plan.remove.length === 0
  )
}

/** The tasks a plan changes or deletes that hold sheets or generations. */
export function affectedTasks(plan: TaskSyncPlan): WizardDraftTask[] {
  return [...plan.update.map((u) => u.task), ...plan.remove].filter(
    (t) => t.sheets.length > 0 || t.generating > 0,
  )
}

/**
 * The import rows of a plan: each carries its position as integer `id` (the
 * nested importer numbers the task with it; an integer id is not kept as the
 * task's origin) unless the row brings its own string id, and its hash and
 * position in `meta`.
 */
export function draftImportRows(rows: HashedRow[]): Record<string, any>[] {
  return rows.map(({ index, row, hash }) => ({
    ...row,
    id: typeof row.id === 'string' && row.id ? row.id : index + 1,
    meta: {
      ...(row.meta && typeof row.meta === 'object' ? row.meta : {}),
      wizard_row_hash: hash,
      wizard_row_index: index,
    },
  }))
}

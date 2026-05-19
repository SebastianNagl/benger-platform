'use client'

import { useCallback, useEffect, useState } from 'react'
import { useI18n } from '@/contexts/I18nContext'
import {
  PlusIcon,
  TrashIcon,
  InformationCircleIcon,
} from '@heroicons/react/24/outline'
import clsx from 'clsx'
import type { CustomCriteriaDefinition } from '@/lib/api/evaluation-types'

interface DimensionsEditorProps {
  value: Record<string, CustomCriteriaDefinition>
  onChange: (dims: Record<string, CustomCriteriaDefinition>) => void
}

interface DimensionRow {
  rowId: string
  key: string
  name: string
  max_score: number
  description: string
  rubric: string
}

// snake_case keys keep the JSON shape stable and avoid escaping issues
// in the strict OpenAI schema. Non-conforming keys are surfaced as a
// warning rather than auto-rewritten — silent rewrites surprise users.
const KEY_PATTERN = /^[a-z][a-z0-9_]*$/

let rowIdSeed = 0
const nextRowId = () => `dim-${++rowIdSeed}-${Date.now()}`

function dimsToRows(
  dims: Record<string, CustomCriteriaDefinition>
): DimensionRow[] {
  return Object.entries(dims || {}).map(([key, def]) => ({
    rowId: nextRowId(),
    key,
    name: def.name || '',
    max_score: def.max_score ?? 0,
    description: def.description || '',
    rubric: def.rubric || '',
  }))
}

function rowsToDims(rows: DimensionRow[]): Record<string, CustomCriteriaDefinition> {
  const out: Record<string, CustomCriteriaDefinition> = {}
  for (const row of rows) {
    if (!row.key) continue
    out[row.key] = {
      name: row.name,
      description: row.description,
      rubric: row.rubric,
      max_score: row.max_score,
    }
  }
  return out
}

export function DimensionsEditor({ value, onChange }: DimensionsEditorProps) {
  const { t } = useI18n()
  const [rows, setRows] = useState<DimensionRow[]>(() => dimsToRows(value))

  // Hydrate rows from the value prop on external change (e.g. loading a
  // saved config). Re-syncing on every value change would clobber the
  // user's in-progress edits, so we only re-sync when the *set of keys*
  // changes — that's the marker for "config was loaded fresh".
  useEffect(() => {
    const incomingKeys = new Set(Object.keys(value || {}))
    const currentKeys = new Set(rows.map((r) => r.key).filter(Boolean))
    const sameKeys =
      incomingKeys.size === currentKeys.size &&
      Array.from(incomingKeys).every((k) => currentKeys.has(k))
    if (!sameKeys) {
      setRows(dimsToRows(value))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value])

  const commit = useCallback(
    (next: DimensionRow[]) => {
      setRows(next)
      onChange(rowsToDims(next))
    },
    [onChange]
  )

  const addRow = () => {
    commit([
      ...rows,
      {
        rowId: nextRowId(),
        key: '',
        name: '',
        max_score: 10,
        description: '',
        rubric: '',
      },
    ])
  }

  const removeRow = (rowId: string) => {
    commit(rows.filter((r) => r.rowId !== rowId))
  }

  const updateRow = (rowId: string, patch: Partial<DimensionRow>) => {
    commit(rows.map((r) => (r.rowId === rowId ? { ...r, ...patch } : r)))
  }

  const totalMax = rows.reduce((sum, r) => sum + (Number(r.max_score) || 0), 0)
  const duplicateKeys = rows
    .map((r) => r.key)
    .filter((k, i, arr) => k && arr.indexOf(k) !== i)
  const invalidKeys = rows
    .map((r) => r.key)
    .filter((k) => k && !KEY_PATTERN.test(k))

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <label className="block text-xs font-medium text-gray-700 dark:text-gray-300">
          {t('evaluationBuilder.parameters.dimensions', 'Scoring Dimensions')}
        </label>
        <div className="text-xs text-gray-500 dark:text-gray-400">
          {t('evaluationBuilder.parameters.totalMax', 'Total max')}:{' '}
          <span
            className={clsx(
              'font-mono',
              totalMax === 100
                ? 'text-green-600 dark:text-green-400'
                : totalMax === 0
                ? 'text-gray-400'
                : 'text-amber-600 dark:text-amber-400'
            )}
          >
            {totalMax}
          </span>
        </div>
      </div>

      <div className="rounded-md border border-blue-200 bg-blue-50 p-2 text-xs text-blue-800 dark:border-blue-800/40 dark:bg-blue-900/20 dark:text-blue-200">
        <div className="flex items-start gap-2">
          <InformationCircleIcon className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <div>
            {t(
              'evaluationBuilder.parameters.dimensionsHint',
              'Define weighted dimensions to switch the judge into single-call multi-dimension mode. The judge will return one JSON with per-dimension scores (each clamped to its max_score) plus a total_score. Leave max_score empty on every dimension to keep the legacy per-criterion 1-5 scoring.'
            )}
          </div>
        </div>
      </div>

      {rows.length === 0 && (
        <div className="rounded-md border border-dashed border-gray-300 p-4 text-center text-sm text-gray-500 dark:border-gray-700 dark:text-gray-400">
          {t(
            'evaluationBuilder.parameters.noDimensions',
            'No dimensions defined. Click "Add dimension" to start.'
          )}
        </div>
      )}

      <div className="space-y-3">
        {rows.map((row) => (
          <div
            key={row.rowId}
            className="rounded-md border border-gray-200 p-3 dark:border-gray-700"
          >
            <div className="grid grid-cols-12 gap-2">
              <div className="col-span-4">
                <label className="mb-1 block text-[10px] uppercase tracking-wider text-gray-500 dark:text-gray-400">
                  {t('evaluationBuilder.parameters.dimensionKey', 'Key')}
                </label>
                <input
                  type="text"
                  value={row.key}
                  placeholder="result_correctness"
                  onChange={(e) => updateRow(row.rowId, { key: e.target.value.trim() })}
                  className="w-full rounded-md border border-gray-300 px-2 py-1 font-mono text-xs dark:border-gray-600 dark:bg-gray-800"
                />
              </div>
              <div className="col-span-5">
                <label className="mb-1 block text-[10px] uppercase tracking-wider text-gray-500 dark:text-gray-400">
                  {t('evaluationBuilder.parameters.dimensionName', 'Display Name')}
                </label>
                <input
                  type="text"
                  value={row.name}
                  placeholder="Ergebnisrichtigkeit"
                  onChange={(e) => updateRow(row.rowId, { name: e.target.value })}
                  className="w-full rounded-md border border-gray-300 px-2 py-1 text-xs dark:border-gray-600 dark:bg-gray-800"
                />
              </div>
              <div className="col-span-2">
                <label className="mb-1 block text-[10px] uppercase tracking-wider text-gray-500 dark:text-gray-400">
                  {t('evaluationBuilder.parameters.dimensionMax', 'Max')}
                </label>
                <input
                  type="number"
                  min={0}
                  max={1000}
                  step={1}
                  value={row.max_score}
                  onChange={(e) =>
                    updateRow(row.rowId, { max_score: Number(e.target.value) || 0 })
                  }
                  className="w-full rounded-md border border-gray-300 px-2 py-1 text-xs dark:border-gray-600 dark:bg-gray-800"
                />
              </div>
              <div className="col-span-1 flex items-end justify-end">
                <button
                  type="button"
                  onClick={() => removeRow(row.rowId)}
                  className="rounded-md p-1.5 text-gray-400 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-900/20"
                  title={t('common.remove', 'Remove')}
                  aria-label={t('common.remove', 'Remove')}
                >
                  <TrashIcon className="h-4 w-4" />
                </button>
              </div>

              <div className="col-span-12">
                <label className="mb-1 block text-[10px] uppercase tracking-wider text-gray-500 dark:text-gray-400">
                  {t('evaluationBuilder.parameters.dimensionDescription', 'Description')}
                </label>
                <input
                  type="text"
                  value={row.description}
                  placeholder={t(
                    'evaluationBuilder.parameters.dimensionDescriptionPlaceholder',
                    'What this dimension assesses (optional, shown to the judge in the rubric)'
                  )}
                  onChange={(e) => updateRow(row.rowId, { description: e.target.value })}
                  className="w-full rounded-md border border-gray-300 px-2 py-1 text-xs dark:border-gray-600 dark:bg-gray-800"
                />
              </div>

              <div className="col-span-12">
                <label className="mb-1 block text-[10px] uppercase tracking-wider text-gray-500 dark:text-gray-400">
                  {t('evaluationBuilder.parameters.dimensionRubric', 'Rubric')}
                </label>
                <textarea
                  value={row.rubric}
                  placeholder={t(
                    'evaluationBuilder.parameters.dimensionRubricPlaceholder',
                    'Anchored guidance for the judge: what earns 0, what earns max_score (optional).'
                  )}
                  rows={2}
                  onChange={(e) => updateRow(row.rowId, { rubric: e.target.value })}
                  className="w-full rounded-md border border-gray-300 px-2 py-1 text-xs dark:border-gray-600 dark:bg-gray-800"
                />
              </div>
            </div>
          </div>
        ))}
      </div>

      <button
        type="button"
        onClick={addRow}
        className="flex items-center gap-1.5 rounded-md border border-dashed border-gray-300 px-3 py-1.5 text-xs text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-800"
      >
        <PlusIcon className="h-3.5 w-3.5" />
        {t('evaluationBuilder.parameters.addDimension', 'Add dimension')}
      </button>

      {(duplicateKeys.length > 0 || invalidKeys.length > 0) && (
        <div className="rounded-md border border-red-200 bg-red-50 p-2 text-xs text-red-700 dark:border-red-800/40 dark:bg-red-900/20 dark:text-red-300">
          {duplicateKeys.length > 0 && (
            <div>
              {t('evaluationBuilder.parameters.duplicateKeys', 'Duplicate keys')}:{' '}
              <code className="font-mono">{duplicateKeys.join(', ')}</code>
            </div>
          )}
          {invalidKeys.length > 0 && (
            <div>
              {t(
                'evaluationBuilder.parameters.invalidKeys',
                'Keys must be snake_case (lowercase, digits, underscores; start with a letter)'
              )}
              : <code className="font-mono">{invalidKeys.join(', ')}</code>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

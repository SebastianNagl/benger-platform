'use client'

/**
 * Variant unit viewer: the tasks of one unit of a variant design. Along a
 * chosen factor it puts twin tasks side by side (the reference level on the
 * left, the treated level on the right, agreeing on every other within-unit
 * factor); without one it lists the unit's tasks. The texts the design lets
 * differ show their declared spans highlighted, so a reader sees that twins
 * differ only there. Below each task are the answers of the chosen system
 * with their parsed values, flags and the request each one sent. The unit's
 * own assignment, balance and invariance check (the check a freeze runs) is
 * shown on top.
 *
 * `VariantUnitViewer` renders a loaded unit (`GET /api/projects/{id}/
 * variant-designs/{key}/units/{unit}`) from its props; `VariantUnitLoader`
 * fetches one and opens each answer's request with `RequestRecordLoader`.
 */

import { useI18n } from '@/contexts/I18nContext'
import { levelText } from '@/lib/analysis/labels'
import { MISSING } from '@/lib/analysis/results'
import {
  resolveFocus,
  segments,
  twinPairs,
  unitLevels,
  withinUnitFactors,
  type UnitFocus,
} from '@/lib/analysis/units'
import { statusOf } from '@/lib/api/analysis'
import {
  variantViewsAPI,
  type UnitGeneration,
  type UnitTask,
  type UnitText,
  type UnitView,
} from '@/lib/api/variantViews'
import {
  CheckCircleIcon,
  ExclamationTriangleIcon,
} from '@heroicons/react/20/solid'
import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { RequestRecordLoader } from './RequestRecordView'
import { Notice, ShortHash, SystemName } from './viewParts'

/** Renders the request record of one answer (a generation trial). */
export type RequestRenderer = (generation: UnitGeneration) => ReactNode

const SELECT =
  'min-w-0 max-w-full flex-1 truncate rounded-md border border-zinc-300 bg-white px-2 py-1 text-xs text-zinc-900 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100'

function cellLabel(task: UnitTask, except?: string | null): string {
  return Object.entries(task.factors)
    .filter(([k]) => k !== except)
    .map(([k, v]) => `${k} = ${levelText(v)}`)
    .join(', ')
}

function FieldValue({ value }: { value: unknown }) {
  if (Array.isArray(value)) return <>{value.map(String).join(', ')}</>
  if (value !== null && typeof value === 'object') {
    return <>{JSON.stringify(value)}</>
  }
  return <>{value === null || value === undefined ? MISSING : String(value)}</>
}

function Answer({
  g,
  requestView,
}: {
  g: UnitGeneration
  requestView?: RequestRenderer
}) {
  const { t } = useI18n()
  const [showText, setShowText] = useState(false)
  const [showRequest, setShowRequest] = useState(false)
  const fields = Object.entries(g.fields).sort(([a], [b]) =>
    a.localeCompare(b, undefined, { numeric: true }),
  )
  return (
    <li
      className="min-w-0 rounded-md border border-zinc-200 p-3 dark:border-zinc-800"
      data-testid="unit-answer"
    >
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-zinc-500 dark:text-zinc-400">
        <span className="font-medium text-zinc-700 dark:text-zinc-300">
          {t('analysis.views.unit.run', { run: g.run_index + 1 })}
        </span>
        <SystemName systemKey={g.system_key} />
        {g.structure_key && (
          <span className="font-mono">{g.structure_key}</span>
        )}
        {g.refusal && (
          <span className="font-medium text-amber-700 dark:text-amber-400">
            {t('analysis.views.unit.refusal')}
          </span>
        )}
        {g.parse_status && g.parse_status !== 'success' && (
          <span className="font-medium text-amber-700 dark:text-amber-400">
            {t('analysis.views.unit.parseStatus', { status: g.parse_status })}
          </span>
        )}
        {g.retried && <span>{t('analysis.views.unit.retried')}</span>}
      </div>
      {fields.length > 0 ? (
        <dl className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-sm">
          {fields.map(([name, value]) => (
            <div key={name} className="flex min-w-0 gap-1.5">
              <dt className="font-mono text-xs leading-5 text-zinc-500 dark:text-zinc-400">
                {name}
              </dt>
              <dd className="font-semibold break-words text-zinc-900 tabular-nums dark:text-zinc-100">
                <FieldValue value={value} />
              </dd>
            </div>
          ))}
        </dl>
      ) : (
        <p className="mt-2 text-sm text-zinc-500 italic dark:text-zinc-400">
          {t('analysis.views.unit.noValues')}
        </p>
      )}
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs">
        {g.response !== null && g.response !== '' && (
          <button
            type="button"
            className="font-medium text-emerald-700 hover:underline dark:text-emerald-400"
            onClick={() => setShowText((v) => !v)}
            aria-expanded={showText}
          >
            {showText
              ? t('analysis.views.unit.hideAnswer')
              : t('analysis.views.unit.showAnswer')}
          </button>
        )}
        {requestView && (
          <button
            type="button"
            className="font-medium text-emerald-700 hover:underline disabled:cursor-not-allowed disabled:text-zinc-400 disabled:no-underline dark:text-emerald-400 dark:disabled:text-zinc-500"
            onClick={() => setShowRequest((v) => !v)}
            aria-expanded={showRequest}
            disabled={!g.has_request_record}
            title={
              g.has_request_record
                ? undefined
                : t('analysis.views.unit.noRequest')
            }
            data-testid="unit-answer-request"
          >
            {showRequest
              ? t('analysis.views.unit.hideRequest')
              : t('analysis.views.unit.showRequest')}
          </button>
        )}
        {g.request_sha256 && (
          <span className="min-w-0 text-zinc-500 dark:text-zinc-400">
            SHA-256 <ShortHash value={g.request_sha256} />
          </span>
        )}
      </div>
      {showText && (
        <pre className="mt-2 max-h-60 overflow-auto rounded-md bg-zinc-50 p-2 font-mono text-xs break-words whitespace-pre-wrap text-zinc-800 dark:bg-zinc-800/60 dark:text-zinc-200">
          {g.response}
          {g.response_truncated ? '…' : ''}
        </pre>
      )}
      {showRequest && requestView && (
        <div className="mt-3 border-t border-zinc-200 pt-3 dark:border-zinc-800">
          {requestView(g)}
        </div>
      )}
    </li>
  )
}

/** Texts up to this length without a line break are listed compactly. */
const SHORT_TEXT = 60

const isShort = (text: UnitText) =>
  text.kind !== 'spanned' &&
  (text.text ?? '').length <= SHORT_TEXT &&
  !(text.text ?? '').includes('\n')

function TextBox({ text }: { text: UnitText }) {
  const { t } = useI18n()
  return (
    <div className="min-w-0">
      <p className="mb-1 font-mono text-xs break-all text-zinc-500 dark:text-zinc-400">
        {text.path}
        {text.kind === 'free' && ` · ${t('analysis.views.unit.free')}`}
      </p>
      <p
        className="rounded-md border border-zinc-200 bg-zinc-50 p-3 text-sm leading-relaxed break-words whitespace-pre-wrap text-zinc-800 dark:border-zinc-700 dark:bg-zinc-800/60 dark:text-zinc-200"
        data-testid="unit-text"
      >
        {segments(text.text ?? '', text.spans).map((piece, i) =>
          piece.marked ? (
            <mark
              key={i}
              className="rounded-sm bg-amber-200/80 px-0.5 text-zinc-900 dark:bg-amber-400/30 dark:text-amber-100"
              data-testid="unit-span"
            >
              {piece.text}
            </mark>
          ) : (
            <span key={i}>{piece.text}</span>
          ),
        )}
        {text.truncated && '…'}
      </p>
    </div>
  )
}

function ShortTexts({ texts }: { texts: UnitText[] }) {
  const { t } = useI18n()
  if (texts.length === 0) return null
  return (
    <dl className="grid min-w-0 gap-x-3 gap-y-1 text-xs sm:grid-cols-[max-content_minmax(0,1fr)]">
      {texts.map((text) => (
        <div key={text.path} className="contents" data-testid="unit-field">
          <dt className="font-mono break-all text-zinc-500 dark:text-zinc-400">
            {text.path}
          </dt>
          <dd className="min-w-0 break-words text-zinc-800 dark:text-zinc-200">
            {text.text ?? MISSING}
            {text.kind === 'free' && (
              <span className="ml-1 text-zinc-500 dark:text-zinc-400">
                ({t('analysis.views.unit.free')})
              </span>
            )}
          </dd>
        </div>
      ))}
    </dl>
  )
}

/**
 * The task's data: spanned and long texts in boxes, short values listed;
 * the fields that must match across the unit fold away when the design
 * also declares fields that may differ.
 */
function TaskTexts({ texts }: { texts: UnitText[] }) {
  const { t } = useI18n()
  const varying = texts.filter((x) => x.kind !== 'fixed')
  const fixed = texts.filter((x) => x.kind === 'fixed')
  const render = (list: UnitText[]) => (
    <>
      {list
        .filter((x) => !isShort(x))
        .map((x) => (
          <TextBox key={x.path} text={x} />
        ))}
      <ShortTexts texts={list.filter(isShort)} />
    </>
  )
  if (varying.length === 0) return render(fixed)
  return (
    <>
      {render(varying)}
      {fixed.length > 0 && (
        <details className="min-w-0 text-xs" data-testid="unit-fixed-fields">
          <summary className="cursor-pointer font-medium text-zinc-600 dark:text-zinc-400">
            {t('analysis.views.unit.fixedFields', { count: fixed.length })}
          </summary>
          <div className="mt-2 space-y-3">{render(fixed)}</div>
        </details>
      )}
    </>
  )
}

/** The items inside one answer (slots) with their factors. */
function SlotTable({ slots }: { slots: NonNullable<UnitTask['slots']> }) {
  const { t } = useI18n()
  const names = [...new Set(slots.flatMap((s) => Object.keys(s.factors)))]
  return (
    <div className="min-w-0 overflow-x-auto" data-testid="unit-slots">
      <table className="min-w-full text-xs">
        <thead className="text-left text-zinc-500 dark:text-zinc-400">
          <tr>
            <th className="py-1 pr-3 font-medium">
              {t('analysis.views.unit.slot')}
            </th>
            {names.map((n) => (
              <th key={n} className="py-1 pr-3 font-mono font-medium">
                {n}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="text-zinc-800 dark:text-zinc-200">
          {slots.map((slot) => (
            <tr
              key={slot.index}
              className="border-t border-zinc-100 dark:border-zinc-800"
            >
              <td className="py-1 pr-3 tabular-nums">{slot.index}</td>
              {names.map((n) => (
                <td key={n} className="py-1 pr-3 break-words">
                  {levelText(slot.factors[n]) || MISSING}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function TaskColumn({
  task,
  side,
  factor,
  requestView,
}: {
  task: UnitTask
  side: 'reference' | 'treated' | 'task'
  factor: string | null
  requestView?: RequestRenderer
}) {
  const { t } = useI18n()
  return (
    <div className="min-w-0 space-y-3" data-testid={`unit-${side}`}>
      <div>
        {side !== 'task' && (
          <p className="text-xs font-semibold tracking-wide text-zinc-500 uppercase dark:text-zinc-400">
            {side === 'reference'
              ? t('analysis.views.unit.reference')
              : t('analysis.views.unit.treated')}
          </p>
        )}
        <p className="mt-0.5 text-sm break-words text-zinc-800 dark:text-zinc-200">
          {factor && (
            <span className="mr-1 font-semibold">
              {factor} = {levelText(task.factors[factor])}
            </span>
          )}
          <span className="text-zinc-500 dark:text-zinc-400">
            {cellLabel(task, factor)}
          </span>
        </p>
        <p className="mt-0.5 text-xs text-zinc-500 dark:text-zinc-400">
          {t('analysis.views.unit.task', { id: task.inner_id ?? task.id })}
        </p>
      </div>
      {(task.slots ?? []).length > 0 && <SlotTable slots={task.slots!} />}
      <TaskTexts texts={task.texts} />
      {task.gold.length > 0 && (
        <p className="text-xs break-words text-zinc-600 dark:text-zinc-400">
          {t('analysis.views.unit.gold')}:{' '}
          {task.gold.map((g) => (
            <span key={g.name} className="mr-3">
              <span className="font-mono">{g.name}</span> ={' '}
              <span className="font-medium text-zinc-800 dark:text-zinc-200">
                <FieldValue value={g.value} />
              </span>
            </span>
          ))}
        </p>
      )}
      <div>
        <p className="mb-2 text-xs font-semibold text-zinc-700 dark:text-zinc-300">
          {t('analysis.views.unit.answers', { count: task.generations.length })}
        </p>
        {task.generations.length === 0 ? (
          <p className="text-sm text-zinc-500 italic dark:text-zinc-400">
            {t('analysis.views.unit.noAnswers')}
          </p>
        ) : (
          <ul className="space-y-2">
            {task.generations.map((g) => (
              <Answer key={g.id} g={g} requestView={requestView} />
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}

function CheckStatus({ view }: { view: UnitView }) {
  const { t } = useI18n()
  const c = view.check
  if (c.ok) {
    return (
      <span
        className="inline-flex items-center gap-1 text-xs font-medium text-emerald-700 dark:text-emerald-400"
        data-testid="unit-check-ok"
      >
        <CheckCircleIcon className="h-4 w-4" aria-hidden="true" />
        {t('analysis.views.unit.checkOk')}
      </span>
    )
  }
  const sections = ['invariance', 'balance', 'assignments'] as const
  const problems = sections.flatMap((section) =>
    c[section].problems.map((p) => ({ section, p })),
  )
  return (
    <Notice tone="warning" testId="unit-check-problems">
      <p className="flex items-center gap-1 font-medium">
        <ExclamationTriangleIcon className="h-4 w-4" aria-hidden="true" />
        {t('analysis.views.unit.checkProblems', {
          count: sections.reduce((n, s) => n + c[s].problem_count, 0),
        })}
      </p>
      <ul className="mt-1 list-disc space-y-0.5 pl-5 text-xs">
        {problems.slice(0, 10).map(({ section, p }, i) => (
          <li key={i} className="break-words">
            {t(`analysis.views.check.${section}`)}:{' '}
            {String(p.kind ?? p.message ?? '')}
            {p.path ? ` (${String(p.path)})` : ''}
            {p.excerpt_a
              ? ` · ${String(p.excerpt_a)} / ${String(p.excerpt_b)}`
              : ''}
          </li>
        ))}
      </ul>
    </Notice>
  )
}

export interface VariantUnitViewerProps {
  view: UnitView
  /** The factor (and levels) to pair along first; the reader can change it. */
  focus?: UnitFocus
  /** Renders an answer's request; without it the answers offer no request. */
  requestView?: RequestRenderer
}

/** One unit from its data (no fetching of the unit). */
export function VariantUnitViewer({
  view,
  focus,
  requestView,
}: VariantUnitViewerProps) {
  const { t } = useI18n()
  // By value, so a caller's new object with the same focus keeps the picks.
  const focusKey = JSON.stringify(focus ?? {})
  const initial = useMemo(
    () => resolveFocus(view, JSON.parse(focusKey) as UnitFocus),
    [view, focusKey],
  )
  // The reader's picks, kept while the unit and the focus stay the same.
  const [picks, setPicks] = useState<{
    base: typeof initial
    factor: string | null
    reference: string
    level: string
    pair: number
  } | null>(null)
  const current =
    picks && picks.base === initial
      ? picks
      : { base: initial, ...initial, pair: 0 }
  const { factor, reference, level, pair: pairIndex } = current
  const pick = (change: Partial<typeof current>) =>
    setPicks({ ...current, pair: 0, ...change })

  const within = withinUnitFactors(view.design.factors).map((f) => f.name)
  const levels = factor ? unitLevels(view, factor) : []
  const pairs = factor ? twinPairs(view, factor, reference, level) : []
  const pair = pairs[Math.min(pairIndex, Math.max(0, pairs.length - 1))]

  const pickFactor = (name: string) =>
    pick(resolveFocus(view, { factor: name }))

  return (
    <div className="min-w-0 space-y-4" data-testid="variant-unit-viewer">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0 text-sm text-zinc-700 dark:text-zinc-300">
          <span className="font-medium break-all">
            {t('analysis.views.unit.unit', {
              name: view.design.unit_name ?? t('analysis.views.unit.unitName'),
              unit: view.unit,
            })}
          </span>
          <span className="ml-2 text-xs text-zinc-500 dark:text-zinc-400">
            {t('analysis.views.unit.design', {
              design: view.design.key,
              status: t(
                `analysis.views.design.statusValue.${view.design.status}`,
              ),
            })}{' '}
            <ShortHash value={view.design.content_hash} />
          </span>
        </div>
        <CheckStatus view={view} />
      </div>

      <div className="flex flex-wrap items-center gap-3 text-xs text-zinc-600 empty:hidden dark:text-zinc-400">
        {view.system && (
          <span className="inline-flex min-w-0 items-center gap-1">
            {t('analysis.views.unit.system')}:{' '}
            <SystemName systemKey={view.system} />
          </span>
        )}
        {within.length > 0 && (
          <label className="inline-flex max-w-full min-w-0 items-center gap-2">
            {t('analysis.views.unit.factor')}
            <select
              className={SELECT}
              value={factor ?? ''}
              onChange={(e) => pickFactor(e.target.value)}
              name="unit-factor"
              data-testid="unit-factor"
            >
              {within.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </label>
        )}
        {factor && levels.length > 1 && (
          <>
            <label className="inline-flex max-w-full min-w-0 items-center gap-2">
              {t('analysis.views.unit.reference')}
              <select
                className={SELECT}
                value={reference}
                onChange={(e) => pick({ reference: e.target.value })}
                name="unit-reference-level"
                data-testid="unit-reference-level"
              >
                {levels.map((l) => (
                  <option key={l} value={l}>
                    {l}
                  </option>
                ))}
              </select>
            </label>
            <label className="inline-flex max-w-full min-w-0 items-center gap-2">
              {t('analysis.views.unit.treated')}
              <select
                className={SELECT}
                value={level}
                onChange={(e) => pick({ level: e.target.value })}
                name="unit-treated-level"
                data-testid="unit-treated-level"
              >
                {levels.map((l) => (
                  <option key={l} value={l}>
                    {l}
                  </option>
                ))}
              </select>
            </label>
          </>
        )}
        {pairs.length > 1 && (
          <label className="inline-flex max-w-full min-w-0 items-center gap-2">
            {t('analysis.views.unit.choosePair')}
            <select
              className={SELECT}
              value={Math.min(pairIndex, pairs.length - 1)}
              onChange={(e) =>
                setPicks({ ...current, pair: Number(e.target.value) })
              }
              name="unit-pair"
              data-testid="unit-pair"
            >
              {pairs.map(([r, tr], i) => (
                <option key={`${r.id}-${tr.id}`} value={i}>
                  {cellLabel(tr, factor) || tr.id}
                </option>
              ))}
            </select>
          </label>
        )}
        {view.tasks_truncated && (
          <span>{t('analysis.views.unit.truncated')}</span>
        )}
      </div>

      {factor && pair ? (
        <div className="grid min-w-0 gap-4 lg:grid-cols-2">
          <TaskColumn
            task={pair[0]}
            side="reference"
            factor={factor}
            requestView={requestView}
          />
          <TaskColumn
            task={pair[1]}
            side="treated"
            factor={factor}
            requestView={requestView}
          />
        </div>
      ) : (
        <>
          {factor && (
            <Notice testId="unit-no-twin">
              {t('analysis.views.unit.noTwin')}
            </Notice>
          )}
          <div className="grid min-w-0 gap-4 lg:grid-cols-2">
            {view.tasks.map((task) => (
              <TaskColumn
                key={task.id}
                task={task}
                side="task"
                factor={null}
                requestView={requestView}
              />
            ))}
          </div>
        </>
      )}
    </div>
  )
}

/** One unit loaded from the platform's unit route. */
export function VariantUnitLoader({
  projectId,
  designKey,
  unit,
  system,
  focus,
}: {
  projectId: string
  designKey: string
  unit: string
  /** Answers of this system only (its key or model id); all when null. */
  system: string | null
  focus?: UnitFocus
}) {
  const { t } = useI18n()
  const [view, setView] = useState<UnitView | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setView(null)
    setError(null)
    variantViewsAPI
      .getUnit(projectId, designKey, unit, system)
      .then((v) => !cancelled && setView(v))
      .catch(
        (e: unknown) =>
          !cancelled &&
          setError(
            statusOf(e) === 403
              ? t('analysis.views.unit.forbidden')
              : (e as Error)?.message || t('analysis.views.unit.loadFailed'),
          ),
      )
    return () => {
      cancelled = true
    }
    // t is stable per locale; a locale switch need not reload the unit.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, designKey, unit, system])

  if (error) return <Notice tone="error">{error}</Notice>
  if (!view) {
    return (
      <p className="text-sm text-zinc-500 dark:text-zinc-400" role="status">
        {t('analysis.views.unit.loading')}
      </p>
    )
  }
  return (
    <VariantUnitViewer
      view={view}
      focus={focus}
      requestView={(g) => (
        <RequestRecordLoader trialId={g.id} generationId={g.parent_id} />
      )}
    />
  )
}

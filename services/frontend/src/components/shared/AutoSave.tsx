/**
 * The one save mechanism for settings edited in place (the project page's
 * cards and every section inside them, platform and extension alike).
 *
 * Behaviour it guarantees:
 * - Changes save on their own: a moment after the last change, or on
 *   `commit()` (blur, Enter) for free text and sensitive fields.
 * - A value its validator rejects is never saved; the section stays marked
 *   unsaved and shows its own inline message.
 * - Every saved batch shows exactly ONE "Gespeichert" toast, with
 *   "Rückgängig" that restores the values from before that batch and saves
 *   them again. Save legs must not toast success themselves.
 * - Saves of one buffer never overlap; newer values always land last.
 * - A pending valid change is saved when its section unmounts (a closed
 *   sub-collapsible unmounts its content), so nothing typed is lost.
 * - The enclosing ConfigCard shows the unsaved / saving chip
 *   (`AutoSaveStatusProvider`).
 *
 * Risky changes are confirmed BEFORE they are applied, through
 * `useConfirmSettingChange` and the shared risk registry in
 * `settingRisk.tsx`.
 *
 * Building blocks:
 * - `useDebouncedSave(save)`: debounce core (schedule / flush).
 * - `useAutoSaveBuffer({ values, save, restore })`: a buffer of several
 *   parts (legs); the caller marks user changes, only changed legs save.
 * - `useAutoSave({ value, save, onUndo })`: one self-saving section; changes
 *   are detected against the stored value.
 */

'use client'

import { useToast } from '@/components/shared/Toast'
import { useI18n } from '@/contexts/I18nContext'
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'

/** Delay between the last change and the save. */
export const AUTOSAVE_DELAY_MS = 2000
/** Retry delay while another save of the same buffer is in flight. */
const RETRY_WHILE_SAVING_MS = 500

export interface AutoSaveStatus {
  /** Changes exist that are not saved yet (pending, invalid or failed). */
  dirty: boolean
  /** A save is in flight. */
  saving: boolean
}

// ---------------------------------------------------------------------------
// Status aggregation (the ConfigCard chip)
// ---------------------------------------------------------------------------

interface AutoSaveStatusContextValue {
  report: (id: string, status: AutoSaveStatus | null) => void
}

const AutoSaveStatusContext = createContext<AutoSaveStatusContextValue | null>(
  null,
)

/**
 * Collects the save status of every section below it. `children` is a
 * render function receiving the combined status.
 */
export function AutoSaveStatusProvider({
  children,
}: {
  children: (status: AutoSaveStatus) => ReactNode
}) {
  const [statuses, setStatuses] = useState<Record<string, AutoSaveStatus>>({})
  const report = useCallback((id: string, status: AutoSaveStatus | null) => {
    setStatuses((prev) => {
      const current = prev[id]
      if (status === null) {
        if (!current) return prev
        const next = { ...prev }
        delete next[id]
        return next
      }
      if (
        current &&
        current.dirty === status.dirty &&
        current.saving === status.saving
      ) {
        return prev
      }
      return { ...prev, [id]: status }
    })
  }, [])
  const value = useMemo(() => ({ report }), [report])
  const combined = useMemo(() => {
    const all = Object.values(statuses)
    return {
      dirty: all.some((s) => s.dirty),
      saving: all.some((s) => s.saving),
    }
  }, [statuses])
  return (
    <AutoSaveStatusContext.Provider value={value}>
      {children(combined)}
    </AutoSaveStatusContext.Provider>
  )
}

/** Report a section's save status to the enclosing provider (if any). */
export function useReportAutoSaveStatus({ dirty, saving }: AutoSaveStatus) {
  const ctx = useContext(AutoSaveStatusContext)
  const id = useId()
  useEffect(() => {
    ctx?.report(id, { dirty, saving })
  }, [ctx, id, dirty, saving])
  useEffect(() => () => ctx?.report(id, null), [ctx, id])
}

// ---------------------------------------------------------------------------
// The one saved toast
// ---------------------------------------------------------------------------

/**
 * Returns `showSaved(undo?)`: the single "Gespeichert" toast of a saved
 * batch, with "Rückgängig" when `undo` is given. Re-issuing it replaces the
 * previous one (the toast store dedups by message), so a burst of batches
 * never stacks toasts.
 */
export function useSavedToast() {
  const { t } = useI18n()
  const { addToast } = useToast()
  return useCallback(
    (undo?: () => void) => {
      addToast(
        t('shared.autoSave.saved'),
        'success',
        undefined,
        undo
          ? { action: { label: t('shared.autoSave.undo'), onClick: undo } }
          : undefined,
      )
    },
    [addToast, t],
  )
}

// ---------------------------------------------------------------------------
// Debounce core
// ---------------------------------------------------------------------------

export interface DebouncedSave {
  /** (Re)start the timer; the save runs after the delay. */
  schedule: () => void
  /** Cancel a waiting timer and save now (after an in-flight save). */
  flush: () => Promise<void>
  /** Whether a timer is waiting (read at call time). */
  isPending: () => boolean
  /** A save is in flight. */
  saving: boolean
}

export function useDebouncedSave(
  save: () => Promise<void>,
  { delayMs = AUTOSAVE_DELAY_MS }: { delayMs?: number } = {},
): DebouncedSave {
  // The timer must call the CURRENT render's closure when it fires, not the
  // one captured when it was scheduled (that change has not rendered yet).
  const saveRef = useRef(save)
  saveRef.current = save
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const inFlightRef = useRef<Promise<void> | null>(null)
  const [saving, setSaving] = useState(false)

  const run = useCallback(() => {
    const promise = (async () => {
      setSaving(true)
      try {
        await saveRef.current()
      } finally {
        inFlightRef.current = null
        setSaving(false)
      }
    })()
    inFlightRef.current = promise
    return promise
  }, [])

  const schedule = useCallback(() => {
    if (timerRef.current) clearTimeout(timerRef.current)
    const fire = () => {
      if (inFlightRef.current) {
        timerRef.current = setTimeout(fire, RETRY_WHILE_SAVING_MS)
        return
      }
      timerRef.current = null
      // Errors are the save function's to report (toast, inline); swallow
      // here so the timer's call never surfaces an unhandled rejection.
      run().catch(() => {})
    }
    timerRef.current = setTimeout(fire, delayMs)
  }, [delayMs, run])

  const flush = useCallback(async () => {
    if (timerRef.current) {
      clearTimeout(timerRef.current)
      timerRef.current = null
    }
    if (inFlightRef.current) {
      await inFlightRef.current.catch(() => {})
    }
    await run()
  }, [run])

  const isPending = useCallback(() => timerRef.current !== null, [])

  useEffect(
    () => () => {
      if (timerRef.current) clearTimeout(timerRef.current)
    },
    [],
  )

  return { schedule, flush, isPending, saving }
}

// ---------------------------------------------------------------------------
// Buffers of several legs
// ---------------------------------------------------------------------------

type Legs = Record<string, unknown>

const key = (value: unknown) => JSON.stringify(value ?? null)

function changedLegs<V extends Legs>(values: V, baseline: V): (keyof V)[] {
  return (Object.keys(values) as (keyof V)[]).filter(
    (leg) => key(values[leg]) !== key(baseline[leg]),
  )
}

function pick<V extends Legs>(values: V, legs: (keyof V)[]): Partial<V> {
  const out: Partial<V> = {}
  for (const leg of legs) out[leg] = values[leg]
  return out
}

export interface UseAutoSaveBufferOptions<V extends Legs> {
  /** The buffered values, one entry per leg. */
  values: V
  /**
   * Persist the changed legs (`changed`), given all current values. Report
   * errors yourself (toast or inline) and throw so the batch stays unsaved.
   * Do not toast success: the buffer shows the one saved toast.
   */
  save: (changed: (keyof V)[], values: V) => Promise<void>
  /** Put legs back to earlier values (undo). */
  restore: (values: Partial<V>) => void
  /**
   * A leg this rejects is not saved; it stays unsaved (and `invalid`)
   * while the other changed legs save.
   */
  isLegValid?: (leg: keyof V, values: V) => boolean
  /**
   * The stored values. When given, they are the baseline and a change of
   * them resets it. When omitted, values seen while the user has changed
   * nothing are taken as stored (buffers initialised from a fetched
   * record).
   */
  baseline?: V
  delayMs?: number
  /** Off: never saves (read-only viewers). */
  enabled?: boolean
}

export interface AutoSaveBuffer extends AutoSaveStatus {
  /**
   * Mark a user change. `schedule: false` only marks it (free text: the
   * caller flushes on blur through `commit`).
   */
  markChanged: (options?: { schedule?: boolean }) => void
  /** Save pending changes now (blur, Enter). */
  commit: () => Promise<void>
  /** A changed leg is rejected by `isLegValid`. */
  invalid: boolean
}

export function useAutoSaveBuffer<V extends Legs>({
  values,
  save,
  restore,
  isLegValid = () => true,
  baseline,
  delayMs = AUTOSAVE_DELAY_MS,
  enabled = true,
}: UseAutoSaveBufferOptions<V>): AutoSaveBuffer {
  const showSaved = useSavedToast()
  const valuesRef = useRef(values)
  valuesRef.current = values
  const isLegValidRef = useRef(isLegValid)
  isLegValidRef.current = isLegValid
  const restoreRef = useRef(restore)
  restoreRef.current = restore
  const saveRef = useRef(save)
  saveRef.current = save
  const enabledRef = useRef(enabled)
  enabledRef.current = enabled

  const baselineRef = useRef<V>(baseline ?? values)
  const userChangedRef = useRef(false)
  const [userChanged, setUserChanged] = useState(false)

  // Baseline: explicit stored values, or whatever the buffer holds while
  // the user has not changed anything (it was just loaded from the server).
  const baselineKey = baseline === undefined ? null : key(baseline)
  useEffect(() => {
    if (baseline !== undefined) baselineRef.current = baseline
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [baselineKey])
  if (baseline === undefined && !userChangedRef.current) {
    baselineRef.current = values
  }

  const setChanged = useCallback((changed: boolean) => {
    userChangedRef.current = changed
    setUserChanged(changed)
  }, [])

  const debouncedRef = useRef<DebouncedSave | null>(null)
  const [undoFlush, setUndoFlush] = useState(0)

  const runBatch = useCallback(async () => {
    if (!enabledRef.current) return
    const snapshot = valuesRef.current
    const changed = changedLegs(snapshot, baselineRef.current)
    if (changed.length === 0) {
      setChanged(false)
      return
    }
    const legs = changed.filter((leg) => isLegValidRef.current(leg, snapshot))
    if (legs.length === 0) return
    const previous = pick(baselineRef.current, legs)
    await saveRef.current(legs, snapshot)
    baselineRef.current = { ...baselineRef.current, ...pick(snapshot, legs) }
    // Values changed again while saving stay pending for the next batch.
    const stillChanged =
      changedLegs(valuesRef.current, baselineRef.current).length > 0
    if (!stillChanged && !debouncedRef.current?.isPending()) setChanged(false)
    showSaved(() => {
      restoreRef.current(previous)
      setChanged(true)
      // Save the restored values once they have rendered.
      setUndoFlush((n) => n + 1)
    })
  }, [setChanged, showSaved])

  const debounced = useDebouncedSave(runBatch, { delayMs })
  debouncedRef.current = debounced

  useEffect(() => {
    if (undoFlush > 0) debounced.flush().catch(() => {})
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [undoFlush])

  const markChanged = useCallback(
    ({ schedule = true }: { schedule?: boolean } = {}) => {
      if (!enabledRef.current) return
      setChanged(true)
      if (schedule) debounced.schedule()
    },
    [debounced, setChanged],
  )

  const commit = useCallback(async () => {
    if (!enabledRef.current || !userChangedRef.current) return
    await debounced.flush().catch(() => {})
  }, [debounced])

  // A pending valid change is saved when the buffer's owner unmounts.
  const flushRef = useRef(debounced.flush)
  flushRef.current = debounced.flush
  useEffect(
    () => () => {
      if (!enabledRef.current || !userChangedRef.current) return
      const pending = valuesRef.current
      if (
        changedLegs(pending, baselineRef.current).some((leg) =>
          isLegValidRef.current(leg, pending),
        )
      ) {
        flushRef.current().catch(() => {})
      }
    },
    [],
  )

  const pendingLegs =
    enabled && userChanged ? changedLegs(values, baselineRef.current) : []
  return {
    dirty: pendingLegs.length > 0,
    saving: debounced.saving,
    invalid: pendingLegs.some((leg) => !isLegValid(leg, values)),
    markChanged,
    commit,
  }
}

// ---------------------------------------------------------------------------
// One self-saving section
// ---------------------------------------------------------------------------

export interface UseAutoSaveOptions<T> {
  /** The section's current (edited) value. */
  value: T
  /** Persist a value. Report errors yourself and throw. Never toast success. */
  save: (value: T) => Promise<void>
  /** Put the value back (undo); without it the saved toast has no undo. */
  onUndo: (previous: T) => void
  /** A value this rejects is never saved; the section stays unsaved. */
  isValid?: (value: T) => boolean
  /**
   * The value as stored on the server. A change of it (refetch) becomes
   * the new baseline. Defaults to the first `value`.
   */
  savedValue?: T
  /**
   * 'change' (default): save a moment after the last change.
   * 'commit': save only on `commit()` (blur, Enter): free text, passwords.
   */
  saveOn?: 'change' | 'commit'
  delayMs?: number
  /** Off: never saves (read-only viewers). */
  enabled?: boolean
}

export interface AutoSaveState extends AutoSaveStatus {
  /** The current value differs from the saved one but is not valid. */
  invalid: boolean
  /** Save a pending valid change now (blur, Enter). */
  commit: () => Promise<void>
}

export function useAutoSave<T>({
  value,
  save,
  onUndo,
  isValid,
  savedValue,
  saveOn = 'change',
  delayMs,
  enabled = true,
}: UseAutoSaveOptions<T>): AutoSaveState {
  const [initial] = useState(value)
  const buffer = useAutoSaveBuffer<{ value: T }>({
    values: { value },
    baseline: { value: savedValue === undefined ? initial : savedValue },
    save: (_legs, values) => save(values.value),
    restore: (previous) => {
      if ('value' in previous) onUndo(previous.value as T)
    },
    isLegValid: isValid ? (_leg, values) => isValid(values.value) : undefined,
    delayMs,
    enabled,
  })

  // Every change of the value is a user change; the buffer compares it
  // with the last saved value and only saves what differs.
  const valueKey = key(value)
  const markRef = useRef(buffer.markChanged)
  markRef.current = buffer.markChanged
  const firstRef = useRef(true)
  useEffect(() => {
    if (firstRef.current) {
      firstRef.current = false
      return
    }
    markRef.current({ schedule: saveOn === 'change' })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [valueKey])

  useReportAutoSaveStatus({ dirty: buffer.dirty, saving: buffer.saving })

  return {
    dirty: buffer.dirty,
    saving: buffer.saving,
    invalid: buffer.invalid,
    commit: buffer.commit,
  }
}

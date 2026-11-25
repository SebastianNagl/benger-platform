/**
 * Shared registry of high-impact settings: changes that alter what
 * participants see or may do right away (visibility, access window, answer
 * reveal, timers, exam security, ...). Platform and extensions register
 * their own settings here; one confirmation dialog asks before such a
 * change is applied and names its concrete consequence. Cancelling leaves
 * the setting as it was (the change is never applied, so the control
 * snaps back).
 *
 * Usage:
 *   registerSettingRisk('strict_timer_enabled', {
 *     isRisky: (_from, to) => to === true,
 *     label: (t) => t('...'),
 *     consequence: (t, ctx) => t('...', { count: ctx.submittedCount }),
 *   })
 *
 *   const applyChange = useGatedSettingChange()
 *   applyChange([{ key: 'strict_timer_enabled', from, to }], () => setValue(to))
 *
 * `applyChange` runs `apply` right away (synchronously, so controlled text
 * inputs keep their cursor) unless a change needs confirming; then it runs
 * after the user confirmed, or not at all.
 *
 * `SettingRiskProvider` (on the project page) supplies the context the
 * consequence texts use and renders the dialog. Without a provider every
 * change passes unconfirmed.
 */

'use client'

import { ConfirmationDialog } from '@/components/shared/ConfirmationDialog'
import { useI18n } from '@/contexts/I18nContext'
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'

type Translate = (key: string, params?: Record<string, unknown>) => string

/** What the consequence texts may refer to. */
export interface SettingRiskContext {
  /** The project being edited (whatever shape the page holds). */
  project: Record<string, any> | null
  /** The access window is set and open right now (a running exam). */
  runningExam: boolean
  /** Annotations already submitted in the project. */
  submittedCount: number
}

export interface SettingRiskDefinition {
  /** Whether this particular change needs confirming (default: any change). */
  isRisky?: (from: unknown, to: unknown, ctx: SettingRiskContext) => boolean
  /** The setting's name as the user knows it. */
  label: (t: Translate) => string
  /** What happens for participants, concretely. */
  consequence: (
    t: Translate,
    ctx: SettingRiskContext,
    change: { from: unknown; to: unknown },
  ) => string
}

export interface SettingChange {
  key: string
  from: unknown
  to: unknown
}

const registry = new Map<string, SettingRiskDefinition>()

export function registerSettingRisk(
  key: string,
  definition: SettingRiskDefinition,
) {
  registry.set(key, definition)
}

const same = (a: unknown, b: unknown) =>
  JSON.stringify(a ?? null) === JSON.stringify(b ?? null)

/**
 * The changes between two settings objects that touch a registered key,
 * e.g. for a buffer updated through one setter.
 */
export function settingChanges(from: object, to: object): SettingChange[] {
  const a = from as Record<string, unknown>
  const b = to as Record<string, unknown>
  return Object.keys(b)
    .filter((k) => registry.has(k) && !same(a[k], b[k]))
    .map((k) => ({ key: k, from: a[k], to: b[k] }))
}

/** The changes of a list that need confirming in this context. */
export function riskyChanges(
  changes: SettingChange[],
  ctx: SettingRiskContext,
): SettingChange[] {
  return changes.filter((change) => {
    const definition = registry.get(change.key)
    if (!definition || same(change.from, change.to)) return false
    return definition.isRisky
      ? definition.isRisky(change.from, change.to, ctx)
      : true
  })
}

type Confirm = (changes: SettingChange[]) => Promise<boolean>

interface SettingRiskContextValue {
  confirm: Confirm
  needsConfirm: (changes: SettingChange[]) => boolean
}

const SettingRiskConfirmContext = createContext<SettingRiskContextValue | null>(
  null,
)

interface PendingConfirm {
  changes: SettingChange[]
  resolve: (ok: boolean) => void
}

export function SettingRiskProvider({
  context,
  children,
}: {
  context: SettingRiskContext
  children: ReactNode
}) {
  const { t } = useI18n()
  const [pending, setPending] = useState<PendingConfirm | null>(null)
  // Read by the callbacks below (event time), kept current after render.
  const contextRef = useRef(context)
  useEffect(() => {
    contextRef.current = context
  })

  const confirm = useCallback<Confirm>((changes) => {
    const risky = riskyChanges(changes, contextRef.current)
    if (risky.length === 0) return Promise.resolve(true)
    return new Promise<boolean>((resolve) => {
      setPending({ changes: risky, resolve })
    })
  }, [])

  const needsConfirm = useCallback(
    (changes: SettingChange[]) =>
      riskyChanges(changes, contextRef.current).length > 0,
    [],
  )
  const value = useMemo(
    () => ({ confirm, needsConfirm }),
    [confirm, needsConfirm],
  )

  const settle = (ok: boolean) => {
    setPending((current) => {
      current?.resolve(ok)
      return null
    })
  }

  const message = useMemo(() => {
    if (!pending) return ''
    const ctx = context
    const lines = pending.changes.map((change) => {
      const definition = registry.get(change.key)!
      return `${definition.label(t)}: ${definition.consequence(t, ctx, change)}`
    })
    if (ctx.runningExam) lines.push(t('shared.settingRisk.runningExam'))
    return lines.join('\n\n')
  }, [pending, t, context])

  return (
    <SettingRiskConfirmContext.Provider value={value}>
      {children}
      <ConfirmationDialog
        isOpen={pending !== null}
        // ConfirmationDialog calls onConfirm and then onClose; the first
        // call settles, the second finds nothing pending.
        onConfirm={() => settle(true)}
        onClose={() => settle(false)}
        title={t('shared.settingRisk.title')}
        message={message}
        confirmText={t('shared.settingRisk.confirm')}
        cancelText={t('shared.settingRisk.cancel')}
        variant="warning"
      />
    </SettingRiskConfirmContext.Provider>
  )
}

/**
 * Apply a change, asking first when it is risky. `apply` runs synchronously
 * when nothing needs confirming; otherwise after confirmation, or never
 * (cancel: the control keeps its old value; `onCancel` runs for controls
 * that already show the new value). Returns whether it applied
 * synchronously.
 */
export function useGatedSettingChange() {
  const ctx = useContext(SettingRiskConfirmContext)
  return useCallback(
    (
      changes: SettingChange[],
      apply: () => void,
      onCancel?: () => void,
    ): boolean => {
      if (!ctx || !ctx.needsConfirm(changes)) {
        apply()
        return true
      }
      void ctx.confirm(changes).then((ok) => {
        if (ok) apply()
        else onCancel?.()
      })
      return false
    },
    [ctx],
  )
}

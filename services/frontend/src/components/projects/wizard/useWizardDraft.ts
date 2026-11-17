/**
 * Draft mode of the project creation wizard (CORE 2.55).
 *
 * Active only when a registered draft policy applies as the user leaves the
 * first step (`@/lib/extensions/wizardDraft`), or when the wizard opens an
 * existing draft (`/projects/create?draft=<id>`). Without either, every
 * function here is a no-op and the wizard runs as before.
 *
 * In draft mode the wizard
 * 1. creates the draft project when the first step is left (idempotent per
 *    `client_key`), puts its id into the URL and runs the `created` hooks;
 * 2. saves its state with the draft's version on every step change and a few
 *    seconds after an edit (409 = changed elsewhere: saving stops and the
 *    user is offered the latest version);
 * 3. syncs the tasks of the data step into the draft when the user moves
 *    past that step and before the finish (see ./draftSync.ts for the rule),
 *    asking first when grading sheets would be set aside or deleted, then
 *    runs the `tasksSynced` hooks;
 * 4. writes title, label config and evaluation configs into the draft
 *    when the user moves to the rubric step and once more on "Create", runs
 *    the `configSynced` hooks and reads the evaluation configs back (the
 *    eval-config PUT replaces lists wholesale, so a later PUT of an older
 *    copy would drop keys the rubric setup added); leaving the rubric step
 *    reads them back again;
 * 5. finishes through the finish route, which applies the visibility.
 */

'use client'

import { useI18n } from '@/contexts/I18nContext'
import { apiClient } from '@/lib/api/client'
import { projectsAPI } from '@/lib/api/projects'
import {
  wizardDraftErrorCode,
  wizardDraftsAPI,
  type WizardDraft,
  type WizardDraftTask,
} from '@/lib/api/wizardDrafts'
import {
  getWizardDraftHooks,
  getWizardDraftPolicies,
  wizardDraftApplies,
  type WizardDraftHookContexts,
  type WizardDraftHookName,
  type WizardDraftSyncedTask,
} from '@/lib/extensions/wizardDraft'
import {
  buildImportFile,
  detectFormat,
  parseImportData,
} from '@/lib/import/parseImportData'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  affectedTasks,
  canonicalJson,
  draftImportRows,
  hashRows,
  planIsEmpty,
  planTaskSync,
  restoreWizardState,
  serializeWizardState,
  type DraftImportRecord,
} from './draftSync'
import { DEFAULT_LABEL_CONFIG, type WizardData } from './types'

/** Debounce of the state save after an edit. */
export const DRAFT_SAVE_DEBOUNCE_MS = 3000

export interface DraftConfirmRequest {
  title: string
  message: string
  confirmText: string
  variant?: 'warning' | 'danger'
}

export interface ActiveDraft {
  projectId: string
  clientKey: string
  kind: string | null
  title: string
}

export type DraftProblem = 'conflict' | 'expired' | null

type Toast = (message: string, type: 'success' | 'error' | 'warning') => void

function newClientKey(): string {
  const c = (globalThis as { crypto?: { randomUUID?: () => string } }).crypto
  if (c?.randomUUID) return c.randomUUID()
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (ch) => {
    const r = (Math.random() * 16) | 0
    return (ch === 'x' ? r : (r & 0x3) | 0x8).toString(16)
  })
}

function errorText(error: unknown, fallback: string): string {
  const detail = (error as { response?: { data?: { detail?: unknown } } })
    ?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (detail && typeof detail === 'object') {
    const message = (detail as { message?: unknown }).message
    if (typeof message === 'string') return message
  }
  return error instanceof Error && error.message ? error.message : fallback
}

/** The project kind the draft is created with (generic = NULL). */
function draftKind(data: WizardData): string | null {
  return data.projectKind === 'generic' ? null : data.projectKind
}

/** Where the finished project will live, as the draft stores it. */
function draftTarget(data: WizardData): {
  orgId: string | null
  groupId: string | null
} {
  if (data.visibility !== 'organization' || data.organizationIds.length === 0) {
    return { orgId: null, groupId: null }
  }
  const orgId = data.organizationIds[0]
  return { orgId, groupId: data.organizationGroupIds[orgId] ?? null }
}

function sameTarget(
  a: { orgId: string | null; groupId: string | null } | null,
  b: { orgId: string | null; groupId: string | null },
): boolean {
  return !!a && a.orgId === b.orgId && a.groupId === b.groupId
}

async function readFileText(file: File): Promise<string> {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = (e) => resolve(e.target?.result as string)
    reader.onerror = reject
    reader.readAsText(file)
  })
}

/** The rows of the data step, or null when it holds none (e.g. a resumed
 *  draft whose file is not chosen again: the draft keeps its tasks). */
async function readWizardRows(data: WizardData): Promise<{
  rows: Record<string, any>[]
  extras: Record<string, unknown>
  fileName: string | null
} | null> {
  if (!(data.features.dataImport || data.features.synthetic)) return null
  if (data.selectedFile) {
    const content = await readFileText(data.selectedFile)
    const parsed = parseImportData(
      content,
      detectFormat(content, data.selectedFile.name),
    )
    return { ...parsed, fileName: data.selectedFile.name }
  }
  const pasted = data.pastedData.trim()
  if (pasted) {
    const parsed = parseImportData(pasted, detectFormat(pasted))
    return { ...parsed, fileName: null }
  }
  return null
}

export function useWizardDraft(options: {
  wizardData: WizardData
  replaceWizardData: (data: WizardData) => void
  updateWizardData: (partial: Partial<WizardData>) => void
  stepIds: string[]
  currentStepId: string | undefined
  goToStepId: (stepId: string) => void
  confirm: (request: DraftConfirmRequest) => Promise<boolean>
  addToast: Toast
  importTimeoutMs: number
}) {
  const { t } = useI18n()
  const {
    wizardData,
    replaceWizardData,
    updateWizardData,
    stepIds,
    currentStepId,
    goToStepId,
    confirm,
    addToast,
    importTimeoutMs,
  } = options

  // Draft mode can only start where a policy is registered; an existing
  // draft opened by URL works without one.
  const policyRegistered = useMemo(
    () => getWizardDraftPolicies().length > 0,
    [],
  )

  const [draft, setDraft] = useState<ActiveDraft | null>(null)
  const [problem, setProblem] = useState<DraftProblem>(null)
  const [saving, setSaving] = useState(false)
  const [resuming, setResuming] = useState(false)
  const [draftImport, setDraftImport] = useState<DraftImportRecord | null>(null)

  const dataRef = useRef(wizardData)
  dataRef.current = wizardData
  const draftRef = useRef<ActiveDraft | null>(null)
  draftRef.current = draft
  const draftImportRef = useRef<DraftImportRecord | null>(null)
  draftImportRef.current = draftImport
  const versionRef = useRef(0)
  const clientKeyRef = useRef<string>('')
  if (!clientKeyRef.current) clientKeyRef.current = newClientKey()
  const problemRef = useRef<DraftProblem>(null)
  problemRef.current = problem
  // Last saved target; a save sends the target only when it changed.
  const savedTargetRef = useRef<{
    orgId: string | null
    groupId: string | null
  } | null>(null)
  // Canonical JSON of the evaluation configs last written or read back.
  const evalSnapshotRef = useRef<string | null>(null)
  // Cloud-storage objects already imported into the draft.
  const cloudImportedRef = useRef<Set<string>>(new Set())
  // A target the server refused; not sent again until it changes.
  const rejectedTargetRef = useRef<{
    orgId: string | null
    groupId: string | null
  } | null>(null)
  const saveChainRef = useRef<Promise<void>>(Promise.resolve())
  // The finish request is on its way: no state save may follow it.
  const finishingRef = useRef(false)
  // A finish request was sent but failed: it may have committed.
  const finishSentRef = useRef(false)
  // A sync after such a finish found the draft finished.
  const finishCommittedRef = useRef(false)
  const stepIdRef = useRef(currentStepId)
  stepIdRef.current = currentStepId

  const runHooks = useCallback(
    async <K extends WizardDraftHookName>(
      name: K,
      ctx: WizardDraftHookContexts[K],
    ) => {
      for (const hook of getWizardDraftHooks(name)) {
        try {
          await hook(ctx)
        } catch (hookError) {
          addToast(
            hookError instanceof Error && hookError.message
              ? hookError.message
              : t('projects.wizard.postCreateHookFailed'),
            'error',
          )
        }
      }
    },
    [addToast, t],
  )

  const setUrlDraft = useCallback((projectId: string | null) => {
    if (typeof window === 'undefined') return
    const url = new URL(window.location.href)
    if (projectId) url.searchParams.set('draft', projectId)
    else url.searchParams.delete('draft')
    window.history.replaceState(window.history.state, '', url.toString())
  }, [])

  const handleDraftError = useCallback(
    (error: unknown, fallbackKey: string): void => {
      const code = wizardDraftErrorCode(error)
      if (code === 'not_wizard_draft' && finishSentRef.current) {
        finishCommittedRef.current = true
        return
      }
      if (code === 'draft_version_conflict') {
        setProblem('conflict')
        return
      }
      if (code === 'draft_expired') {
        setProblem('expired')
        return
      }
      addToast(
        t(fallbackKey, {
          error: errorText(error, t('projects.wizard.unknownError')),
        }),
        'error',
      )
    },
    [addToast, t],
  )

  /** Save the state (serialized: one save at a time keeps the version). */
  const save = useCallback(
    (stepId?: string): Promise<void> => {
      const run = async () => {
        const current = draftRef.current
        if (!current || problemRef.current || finishingRef.current) return
        const data = dataRef.current
        const target = draftTarget(data)
        const last = savedTargetRef.current
        const body: Parameters<typeof wizardDraftsAPI.save>[1] = {
          state: {
            ...serializeWizardState(data, draftImportRef.current),
            draftCloudImported: Array.from(cloudImportedRef.current),
          },
          step_id: stepId ?? stepIdRef.current ?? null,
          if_version: versionRef.current,
        }
        const sendsTarget =
          !sameTarget(last, target) &&
          !sameTarget(rejectedTargetRef.current, target)
        if (sendsTarget) {
          body.target_organization_id = target.orgId
          body.target_group_id = target.groupId
        }
        const apply = (saved: WizardDraft) => {
          versionRef.current = saved.state_version
          savedTargetRef.current = {
            orgId: saved.target_organization_id,
            groupId: saved.target_group_id,
          }
        }
        setSaving(true)
        try {
          apply(await wizardDraftsAPI.save(current.projectId, body))
        } catch (error) {
          const status = (error as { response?: { status?: number } })?.response
            ?.status
          if (
            sendsTarget &&
            status !== undefined &&
            [400, 403, 404].includes(status)
          ) {
            // The server refused the organization or group (e.g. a role
            // that changed): say so once and keep saving the state; the
            // finish route checks the target again.
            rejectedTargetRef.current = target
            addToast(
              t('projects.creation.wizard.draft.targetFailed', {
                error: errorText(error, t('projects.wizard.unknownError')),
              }),
              'error',
            )
            const {
              target_organization_id: _org,
              target_group_id: _group,
              ...withoutTarget
            } = body
            try {
              apply(
                await wizardDraftsAPI.save(current.projectId, withoutTarget),
              )
            } catch (retryError) {
              handleDraftError(
                retryError,
                'projects.creation.wizard.draft.saveFailed',
              )
            }
          } else {
            handleDraftError(error, 'projects.creation.wizard.draft.saveFailed')
          }
        } finally {
          setSaving(false)
        }
      }
      const next = saveChainRef.current.then(run, run)
      saveChainRef.current = next
      return next
    },
    [addToast, handleDraftError, t],
  )

  // Debounced save after an edit.
  useEffect(() => {
    if (!draft || problem) return
    const timer = setTimeout(() => {
      void save()
    }, DRAFT_SAVE_DEBOUNCE_MS)
    return () => clearTimeout(timer)
  }, [wizardData, draft, problem, save])

  const adopt = useCallback(
    (loaded: WizardDraft, restoreState: boolean) => {
      versionRef.current = loaded.state_version
      clientKeyRef.current = loaded.client_key
      savedTargetRef.current = {
        orgId: loaded.target_organization_id,
        groupId: loaded.target_group_id,
      }
      const active: ActiveDraft = {
        projectId: loaded.project_id,
        clientKey: loaded.client_key,
        kind: loaded.kind,
        title: loaded.title,
      }
      draftRef.current = active
      setDraft(active)
      setProblem(null)
      if (restoreState) {
        const restored = restoreWizardState(loaded.state)
        dataRef.current = restored.data
        replaceWizardData(restored.data)
        draftImportRef.current = restored.draftImport
        setDraftImport(restored.draftImport)
        evalSnapshotRef.current = canonicalJson(
          restored.data.evaluationConfigs ?? [],
        )
        cloudImportedRef.current = new Set(restored.cloudImported)
      }
    },
    [replaceWizardData],
  )

  /** Open an existing draft (URL `?draft=`, the unfinished list, reload). */
  const resume = useCallback(
    async (projectId: string): Promise<boolean> => {
      setResuming(true)
      try {
        const loaded = await wizardDraftsAPI.get(projectId)
        adopt(loaded, true)
        setUrlDraft(loaded.project_id)
        if (loaded.step_id) goToStepId(loaded.step_id)
        return true
      } catch (error) {
        const code = wizardDraftErrorCode(error)
        if (code === 'draft_expired' || code === 'not_wizard_draft') {
          setUrlDraft(null)
        }
        addToast(
          t('projects.creation.wizard.draft.loadFailed', {
            error: errorText(error, t('projects.wizard.unknownError')),
          }),
          'error',
        )
        return false
      } finally {
        setResuming(false)
      }
    },
    [adopt, addToast, goToStepId, setUrlDraft, t],
  )

  // `?draft=<id>` on mount. Read from location, not useSearchParams, so the
  // wizard needs no Suspense boundary and no router mock in its tests.
  const resumedRef = useRef(false)
  useEffect(() => {
    if (resumedRef.current || typeof window === 'undefined') return
    resumedRef.current = true
    const id = new URLSearchParams(window.location.search).get('draft')
    if (id) void resume(id)
  }, [resume])

  const createDraft = useCallback(async (): Promise<boolean> => {
    const data = dataRef.current
    const target = draftTarget(data)
    try {
      const created = await wizardDraftsAPI.create({
        title: data.title.trim(),
        description: data.description.trim() || null,
        kind: draftKind(data),
        label_config: data.labelingConfig?.config || DEFAULT_LABEL_CONFIG,
        icon: data.icon.trim() || null,
        target_organization_id: target.orgId,
        target_group_id: target.groupId,
        client_key: clientKeyRef.current,
        state: serializeWizardState(data, null),
        step_id: 'projectInfo',
      })
      adopt(created, false)
      evalSnapshotRef.current = null
      setUrlDraft(created.project_id)
      await runHooks('created', {
        projectId: created.project_id,
        wizardData: data,
      })
      return true
    } catch (error) {
      addToast(
        t('projects.creation.wizard.draft.createFailed', {
          error: errorText(error, t('projects.wizard.unknownError')),
        }),
        'error',
      )
      return false
    }
  }, [adopt, addToast, runHooks, setUrlDraft, t])

  /** Drop the draft from the wizard (not from the server). */
  const forget = useCallback(() => {
    draftRef.current = null
    setDraft(null)
    setProblem(null)
    setDraftImport(null)
    versionRef.current = 0
    savedTargetRef.current = null
    evalSnapshotRef.current = null
    cloudImportedRef.current = new Set()
    finishSentRef.current = false
    finishCommittedRef.current = false
    clientKeyRef.current = newClientKey()
    setUrlDraft(null)
  }, [setUrlDraft])

  /** Discard the draft (after the caller confirmed). */
  const discardNow = useCallback(async (): Promise<boolean> => {
    const current = draftRef.current
    if (!current) return true
    try {
      await wizardDraftsAPI.discard(current.projectId)
    } catch (error) {
      const code = wizardDraftErrorCode(error)
      if (code !== 'draft_expired') {
        addToast(
          t('projects.creation.wizard.draft.discardFailed', {
            error: errorText(error, t('projects.wizard.unknownError')),
          }),
          'error',
        )
        return false
      }
    }
    forget()
    return true
  }, [addToast, forget, t])

  const discardMessage = useCallback(
    async (projectId: string, title: string): Promise<string> => {
      const lines = [
        t('projects.creation.wizard.draft.discardMessage', { title }),
      ]
      for (const policy of getWizardDraftPolicies()) {
        if (!policy.describeDiscard) continue
        try {
          lines.push(...(await policy.describeDiscard({ projectId })))
        } catch {
          // The confirmation still works without the extra lines.
        }
      }
      return lines.join('\n')
    },
    [t],
  )

  /** Ask, then discard. Resolves true when the draft is gone. */
  const discard = useCallback(async (): Promise<boolean> => {
    const current = draftRef.current
    if (!current) return true
    const ok = await confirm({
      title: t('projects.creation.wizard.draft.discardTitle'),
      message: await discardMessage(current.projectId, current.title),
      confirmText: t('projects.creation.wizard.draft.discardConfirm'),
      variant: 'danger',
    })
    if (!ok) return false
    const done = await discardNow()
    if (done) addToast(t('projects.creation.wizard.draft.discarded'), 'success')
    return done
  }, [addToast, confirm, discardMessage, discardNow, t])

  const taskImpactMessage = useCallback(
    (
      updated: WizardDraftTask[],
      removed: WizardDraftTask[],
      rowOf: (task: WizardDraftTask) => number,
    ): string => {
      const line = (task: WizardDraftTask, key: string) => {
        const checked = task.sheets.filter(
          (s) => s.review_state === 'confirmed',
        ).length
        const parts = [
          t(key, {
            n: rowOf(task) + 1,
            sheets: task.sheets.length,
            checked,
          }),
        ]
        if (task.generating > 0) {
          parts.push(t('projects.creation.wizard.draft.taskChangeGenerating'))
        }
        return { checked, text: parts.join(' ') }
      }
      const items = [
        ...updated.map((task) =>
          line(task, 'projects.creation.wizard.draft.taskChangeUpdated'),
        ),
        ...removed.map((task) =>
          line(task, 'projects.creation.wizard.draft.taskChangeRemoved'),
        ),
      ].sort((a, b) => b.checked - a.checked)
      return [
        t('projects.creation.wizard.draft.taskChangeMessage'),
        ...items.map((i) => `- ${i.text}`),
        t('projects.creation.wizard.draft.taskChangeNote'),
      ].join('\n')
    },
    [t],
  )

  /**
   * Sync the rows of the data step into the draft. Resolves false when the
   * user declined the change or the sync failed (the caller stays put).
   */
  const syncTasks = useCallback(async (): Promise<boolean> => {
    const current = draftRef.current
    if (!current || problemRef.current) return !current
    const data = dataRef.current
    const projectId = current.projectId
    try {
      const source = await readWizardRows(data)
      let statusById = new Map<string, WizardDraftSyncedTask['status']>()
      if (source) {
        const rows = hashRows(source.rows)
        const wholeFile = Object.keys(source.extras).length > 0
        const tasks = await wizardDraftsAPI.tasks(projectId)
        const plan = planTaskSync(rows, tasks, { wholeFile })
        if (!planIsEmpty(plan)) {
          const affected = affectedTasks(plan)
          if (affected.length > 0) {
            const updatedIds = new Set(plan.update.map((u) => u.task.id))
            const ok = await confirm({
              title: t('projects.creation.wizard.draft.taskChangeTitle'),
              message: taskImpactMessage(
                affected.filter((a) => updatedIds.has(a.id)),
                affected.filter((a) => !updatedIds.has(a.id)),
                (task) => task.row_index ?? 0,
              ),
              confirmText: t(
                'projects.creation.wizard.draft.taskChangeConfirm',
              ),
            })
            if (!ok) return false
          }
          for (const { task, row } of plan.update) {
            await wizardDraftsAPI.replaceTask(
              projectId,
              task.id,
              row.row.data,
              row.hash,
              row.row.meta && typeof row.row.meta === 'object'
                ? row.row.meta
                : {},
            )
          }
          if (plan.remove.length > 0) {
            await projectsAPI.bulkDeleteTasks(
              projectId,
              plan.remove.map((task) => task.id),
            )
          }
          if (plan.create.length > 0) {
            const file = buildImportFile(
              draftImportRows(plan.create),
              wholeFile ? source.extras : {},
            )
            await projectsAPI.runNestedImportJob(projectId, file, undefined, {
              timeoutMs: importTimeoutMs,
            })
          }
        }
        statusById = new Map([
          ...plan.keep.map((k) => [k.task.id, 'kept'] as const),
          ...plan.update.map((u) => [u.task.id, 'updated'] as const),
        ])
        const record = { rowCount: rows.length, fileName: source.fileName }
        draftImportRef.current = record
        setDraftImport(record)
      }
      // Cloud-storage objects: imported once each (they carry no row hash).
      const cloud = data.cloudImport
      const pendingKeys = (cloud?.objectKeys ?? []).filter(
        (key) => !cloudImportedRef.current.has(key),
      )
      if (cloud && pendingKeys.length > 0) {
        await projectsAPI.runCloudImportJobs(projectId, {
          connection_id: cloud.connectionId,
          object_keys: pendingKeys,
        })
        for (const key of pendingKeys) cloudImportedRef.current.add(key)
      }
      const after = await wizardDraftsAPI.tasks(projectId)
      await runHooks('tasksSynced', {
        projectId,
        wizardData: data,
        tasks: after
          .filter((task) => task.row_index !== null)
          .map((task) => ({
            id: task.id,
            rowIndex: task.row_index as number,
            status: statusById.get(task.id) ?? 'created',
          })),
      })
      await save()
      return true
    } catch (error) {
      if (error instanceof Error && error.name === 'ImportJobTimeoutError') {
        addToast(
          t('projects.wizard.importDataTimeout', {
            minutes: Math.round(importTimeoutMs / 60000),
          }),
          'error',
        )
        return false
      }
      handleDraftError(error, 'projects.creation.wizard.draft.syncFailed')
      return false
    }
  }, [
    addToast,
    confirm,
    handleDraftError,
    importTimeoutMs,
    runHooks,
    save,
    t,
    taskImpactMessage,
  ])

  /** Read the evaluation configs back into the wizard state. */
  const readBackEvalConfigs = useCallback(async () => {
    const current = draftRef.current
    if (!current) return
    const url = `/evaluations/projects/${current.projectId}/evaluation-config`
    apiClient.invalidateCache(url)
    const config: any = await apiClient.get(url)
    const configs = config?.evaluation_configs
    if (Array.isArray(configs)) {
      evalSnapshotRef.current = canonicalJson(configs)
      dataRef.current = { ...dataRef.current, evaluationConfigs: configs }
      updateWizardData({ evaluationConfigs: configs })
    }
  }, [updateWizardData])

  /** Whether `configs` differ from what was last written or read back. */
  const evalConfigsChanged = useCallback(
    (configs: unknown[]) => evalSnapshotRef.current !== canonicalJson(configs),
    [],
  )

  /** Title, description, icon and label config of the wizard state. */
  const basicFields = useCallback((data: WizardData) => {
    return {
      title: data.title.trim(),
      description: data.description.trim(),
      icon: data.icon.trim() || null,
      label_config: data.labelingConfig?.config || DEFAULT_LABEL_CONFIG,
    }
  }, [])

  /** Write the configuration the rubric step works with into the draft. */
  const syncConfig = useCallback(async (): Promise<boolean> => {
    const current = draftRef.current
    if (!current || problemRef.current) return !current
    const data = dataRef.current
    try {
      await projectsAPI.update(current.projectId, basicFields(data))
      if (
        data.features.evaluation &&
        data.evaluationConfigs.length > 0 &&
        evalConfigsChanged(data.evaluationConfigs)
      ) {
        await apiClient.put(
          `/evaluations/projects/${current.projectId}/evaluation-config`,
          { evaluation_configs: data.evaluationConfigs },
        )
        evalSnapshotRef.current = canonicalJson(data.evaluationConfigs)
      }
      await runHooks('configSynced', {
        projectId: current.projectId,
        wizardData: data,
      })
      await readBackEvalConfigs()
      return true
    } catch (error) {
      handleDraftError(error, 'projects.creation.wizard.draft.configSyncFailed')
      return false
    }
  }, [
    basicFields,
    evalConfigsChanged,
    handleDraftError,
    readBackEvalConfigs,
    runHooks,
  ])

  /**
   * Run before the wizard moves from `fromIndex` to `toIndex` (forward or
   * back). Resolves false to keep the user where they are.
   */
  const beforeNavigate = useCallback(
    async (fromIndex: number, toIndex: number): Promise<boolean> => {
      const fromId = stepIds[fromIndex]
      const toId = stepIds[toIndex]
      const forward = toIndex > fromIndex
      let current = draftRef.current
      if (forward && fromId === 'projectInfo') {
        const data = dataRef.current
        if (current && current.kind !== draftKind(data)) {
          // The kind is write-once: another type needs a new draft.
          const ok = await confirm({
            title: t('projects.creation.wizard.draft.kindChangeTitle'),
            message: t('projects.creation.wizard.draft.kindChangeMessage', {
              title: current.title,
            }),
            confirmText: t('projects.creation.wizard.draft.kindChangeConfirm'),
            variant: 'danger',
          })
          if (!ok || !(await discardNow())) return false
          current = null
        }
        if (!current && policyRegistered && wizardDraftApplies(data)) {
          if (!(await createDraft())) return false
          current = draftRef.current
        }
      }
      if (!current) return true
      if (problemRef.current) return false
      if (forward) {
        const dataIdx = stepIds.indexOf(
          stepIds.includes('dataImport') ? 'dataImport' : 'synthetic',
        )
        if (dataIdx >= 0 && fromIndex <= dataIdx && toIndex > dataIdx) {
          if (!(await syncTasks())) return false
        }
        if (toId === 'rubric') {
          if (!(await syncConfig())) return false
        }
      }
      if (fromId === 'rubric' && current) {
        try {
          await readBackEvalConfigs()
        } catch (error) {
          handleDraftError(
            error,
            'projects.creation.wizard.draft.configSyncFailed',
          )
          return false
        }
      }
      await save(toId)
      return true
    },
    [
      confirm,
      createDraft,
      discardNow,
      handleDraftError,
      policyRegistered,
      readBackEvalConfigs,
      save,
      stepIds,
      syncConfig,
      syncTasks,
      t,
    ],
  )

  /** Apply the visibility of the wizard state through the finish route. */
  const finish = useCallback(async (): Promise<string> => {
    const current = draftRef.current
    if (!current) throw new Error('No draft')
    // No save may run once the finish is on its way; a pending one settles.
    finishingRef.current = true
    await saveChainRef.current
    const data = dataRef.current
    let project: { id: string }
    try {
      project = await wizardDraftsAPI.finish(current.projectId, {
        client_key: current.clientKey,
        visibility: data.visibility,
        public_role: data.visibility === 'public' ? data.publicRole : null,
        organization_attachments:
          data.visibility === 'organization'
            ? data.organizationIds.map((orgId) => ({
                organization_id: orgId,
                group_id: data.organizationGroupIds[orgId] ?? null,
              }))
            : [],
      })
    } catch (error) {
      finishingRef.current = false
      finishSentRef.current = true
      throw error
    }
    finishingRef.current = false
    // Finished: no more saves for this draft.
    draftRef.current = null
    setDraft(null)
    return project.id
  }, [])

  return {
    /**
     * Navigation runs through the hook: a draft is open, or a registered
     * policy applies to the current state. Otherwise (generic projects,
     * also in an edition with a policy) the wizard navigates as it always
     * did.
     */
    capable:
      draft !== null || (policyRegistered && wizardDraftApplies(wizardData)),
    /** A draft policy is registered (the unfinished list is offered). */
    policyRegistered,
    /** The wizard state including read-backs not rendered yet. */
    currentData: () => dataRef.current,
    draft,
    problem,
    saving,
    resuming,
    draftImport,
    beforeNavigate,
    syncTasks,
    syncConfig,
    basicFields,
    evalConfigsChanged,
    finish,
    /**
     * A sync after a failed finish found the draft already finished (the
     * finish committed but its answer was lost): finish again with the
     * same client key to get the project.
     */
    finishCommitted: () => finishCommittedRef.current,
    discard,
    discardNow,
    discardMessage,
    forget,
    resume,
    save,
  }
}

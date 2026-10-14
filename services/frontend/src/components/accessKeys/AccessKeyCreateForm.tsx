'use client'

/**
 * Create form of an access key, written for non-technical staff: a name,
 * one of the plain-language presets (the scope list stays behind
 * "Erweitert"), and for organization keys the role, the group and an
 * optional project allowlist. Expiry defaults to one year.
 */

import { Button } from '@/components/shared/Button'
import { useI18n } from '@/contexts/I18nContext'
import type {
  AccessKeyCreate,
  AccessKeyOrgRole,
  ScopeCatalog,
} from '@/lib/api/types'
import { ChevronDownIcon, ChevronRightIcon } from '@heroicons/react/24/outline'
import { type FormEvent, useMemo, useState } from 'react'

import {
  type AccessKeyMode,
  catalogTextOr,
  DEFAULT_EXPIRY,
  EXPIRY_CHOICES,
  type ExpiryChoice,
  expiryToIso,
  isScopeGrantable,
  matchPreset,
  needsContributor,
  offeredScopes,
  presetIds,
  resolvePreset,
  scopeDescription,
} from './accessKeyUtils'

export interface GroupOption {
  id: string
  name: string
}

export interface ProjectOption {
  id: string
  title: string
}

interface AccessKeyCreateFormProps {
  mode: AccessKeyMode
  catalog: ScopeCatalog | null
  /** Org-wide admin (or superadmin). Group admins pass false. */
  isOrgAdmin?: boolean
  /** Groups the caller may create keys for. */
  groups?: GroupOption[]
  projects?: ProjectOption[]
  onSubmit: (body: AccessKeyCreate) => Promise<void>
  onCancel: () => void
}

const inputClass =
  'mt-1 w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 dark:border-zinc-600 dark:bg-zinc-700 dark:text-zinc-100'
const labelClass = 'block text-sm font-medium text-zinc-900 dark:text-zinc-100'
const hintClass = 'mt-1 text-xs text-zinc-500 dark:text-zinc-400'

const FIRST_PRESET = 'benchmark_read'

export function AccessKeyCreateForm({
  mode,
  catalog,
  isOrgAdmin = false,
  groups = [],
  projects = [],
  onSubmit,
  onCancel,
}: AccessKeyCreateFormProps) {
  const { t, locale } = useI18n()
  const ctxBase = useMemo(() => ({ mode, isOrgAdmin }), [mode, isOrgAdmin])
  const presets = presetIds(catalog)
  const initialPreset = presets.includes(FIRST_PRESET)
    ? FIRST_PRESET
    : (presets[0] ?? 'custom')

  const [name, setName] = useState('')
  const [role, setRole] = useState<AccessKeyOrgRole>('ANNOTATOR')
  const [scopes, setScopes] = useState<string[]>(() =>
    initialPreset === 'custom'
      ? []
      : resolvePreset(catalog, initialPreset, ctxBase).scopes,
  )
  const [groupId, setGroupId] = useState<string>(
    isOrgAdmin ? '' : (groups[0]?.id ?? ''),
  )
  const [projectIds, setProjectIds] = useState<string[]>([])
  const [expiry, setExpiry] = useState<ExpiryChoice>(DEFAULT_EXPIRY)
  const [perMinute, setPerMinute] = useState('')
  const [perDay, setPerDay] = useState('')
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [showLimits, setShowLimits] = useState(false)
  const [roleNotice, setRoleNotice] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const ctx = { ...ctxBase, role }
  const available = offeredScopes(catalog, ctxBase)
  const selectedPreset = matchPreset(catalog, scopes, ctxBase)

  const choosePreset = (id: string) => {
    setError(null)
    if (id === 'custom') {
      setShowAdvanced(true)
      return
    }
    const resolved = resolvePreset(catalog, id, ctxBase)
    if (mode === 'org' && resolved.needsContributor && role !== 'CONTRIBUTOR') {
      setRole('CONTRIBUTOR')
      setRoleNotice(true)
    }
    setScopes(resolved.scopes)
  }

  const toggleScope = (scopeName: string) => {
    setError(null)
    setScopes((prev) =>
      prev.includes(scopeName)
        ? prev.filter((s) => s !== scopeName)
        : [...prev, scopeName],
    )
  }

  const changeRole = (next: AccessKeyOrgRole) => {
    setRole(next)
    setRoleNotice(false)
    if (next === 'ANNOTATOR') {
      // Drop what an ANNOTATOR key may not hold.
      const blocked = new Set(
        available
          .filter((s) => !isScopeGrantable(s, { ...ctxBase, role: next }))
          .map((s) => s.name),
      )
      setScopes((prev) => prev.filter((s) => !blocked.has(s)))
    }
  }

  const toggleProject = (id: string) =>
    setProjectIds((prev) =>
      prev.includes(id) ? prev.filter((p) => p !== id) : [...prev, id],
    )

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (!name.trim()) {
      setError(t('accessKeys.form.nameRequired'))
      return
    }
    if (scopes.length === 0) {
      setError(t('accessKeys.form.noScopes'))
      return
    }
    const body: AccessKeyCreate = {
      name: name.trim(),
      scopes: [...scopes].sort(),
      expires_at: expiryToIso(expiry),
      project_ids: projectIds.length ? projectIds : null,
      rate_limit_per_minute: perMinute ? Number(perMinute) : null,
      rate_limit_per_day: perDay ? Number(perDay) : null,
    }
    if (mode === 'org') {
      body.org_role = role
      body.group_id = groupId || null
    }
    setBusy(true)
    setError(null)
    try {
      await onSubmit(body)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      setBusy(false)
    }
  }

  const presetLabel = (id: string) =>
    catalogTextOr(t, `accessKeys.presets.${id}.label`, id.replace(/_/g, ' '))
  // Overlay presets have no catalog entry: show their scope list instead.
  const presetDescription = (id: string) =>
    catalogTextOr(
      t,
      `accessKeys.presets.${id}.description`,
      (catalog?.presets?.[id] ?? []).join(', '),
    )

  return (
    <form
      onSubmit={submit}
      className="space-y-5"
      data-testid="access-key-create-form"
      noValidate
    >
      <h3 className="text-base font-semibold text-zinc-900 dark:text-white">
        {t('accessKeys.form.title')}
      </h3>

      <div>
        <label htmlFor="access-key-name" className={labelClass}>
          {t('accessKeys.form.name')}
        </label>
        <input
          id="access-key-name"
          type="text"
          value={name}
          maxLength={120}
          onChange={(e) => setName(e.target.value)}
          placeholder={t('accessKeys.form.namePlaceholder')}
          className={inputClass}
          data-testid="access-key-name"
        />
      </div>

      <fieldset>
        <legend className={labelClass}>
          {t('accessKeys.form.presetLabel')}
        </legend>
        <div className="mt-2 space-y-2">
          {[...presets, 'custom'].map((id) => (
            <label
              key={id}
              className={`flex cursor-pointer items-start gap-3 rounded-lg border p-3 ${
                selectedPreset === id
                  ? 'border-emerald-500 bg-emerald-50/50 dark:bg-emerald-950/20'
                  : 'border-zinc-200 dark:border-zinc-700'
              }`}
            >
              <input
                type="radio"
                name="access-key-preset"
                value={id}
                checked={selectedPreset === id}
                onChange={() => choosePreset(id)}
                className="mt-1"
                data-testid={`access-key-preset-${id}`}
              />
              <span>
                <span className="block text-sm font-medium text-zinc-900 dark:text-zinc-100">
                  {id === 'custom'
                    ? t('accessKeys.form.custom')
                    : presetLabel(id)}
                </span>
                <span className="block text-xs text-zinc-500 dark:text-zinc-400">
                  {id === 'custom'
                    ? t('accessKeys.form.customDescription')
                    : presetDescription(id)}
                </span>
              </span>
            </label>
          ))}
        </div>
        {roleNotice && (
          <p
            className="mt-2 text-xs text-amber-700 dark:text-amber-400"
            data-testid="access-key-role-notice"
          >
            {t('accessKeys.form.roleSwitched')}
          </p>
        )}
      </fieldset>

      <div>
        <button
          type="button"
          onClick={() => setShowAdvanced((v) => !v)}
          className="flex items-center gap-1 text-sm font-medium text-zinc-700 dark:text-zinc-300"
          aria-expanded={showAdvanced}
          data-testid="access-key-advanced-toggle"
        >
          {showAdvanced ? (
            <ChevronDownIcon className="h-4 w-4" />
          ) : (
            <ChevronRightIcon className="h-4 w-4" />
          )}
          {t('accessKeys.form.advanced')}
        </button>
        {showAdvanced && (
          <div className="mt-2 space-y-1" data-testid="access-key-scope-list">
            <p className={hintClass}>{t('accessKeys.form.advancedHint')}</p>
            {available.map((scope) => {
              const grantable = isScopeGrantable(scope, ctx)
              return (
                <label
                  key={scope.name}
                  className={`flex items-start gap-2 py-1 text-sm ${
                    grantable ? '' : 'opacity-50'
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={scopes.includes(scope.name)}
                    disabled={!grantable}
                    onChange={() => toggleScope(scope.name)}
                    className="mt-1"
                    data-testid={`access-key-scope-${scope.name}`}
                  />
                  <span>
                    <span className="font-mono text-xs text-zinc-900 dark:text-zinc-100">
                      {scope.name}
                    </span>{' '}
                    <span className="text-zinc-600 dark:text-zinc-400">
                      {scopeDescription(scope, locale)}
                    </span>
                    {scope.implies.length > 0 && (
                      <span className="block text-xs text-zinc-500">
                        {t('accessKeys.form.implies', {
                          scopes: scope.implies.join(', '),
                        })}
                      </span>
                    )}
                    {needsContributor(scope, ctx) && !grantable && (
                      <span className="block text-xs text-amber-700 dark:text-amber-400">
                        {t('accessKeys.form.needsContributor')}
                      </span>
                    )}
                  </span>
                </label>
              )
            })}
          </div>
        )}
      </div>

      {mode === 'org' && (
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label htmlFor="access-key-role" className={labelClass}>
              {t('accessKeys.form.roleLabel')}
            </label>
            <select
              id="access-key-role"
              value={role}
              onChange={(e) => changeRole(e.target.value as AccessKeyOrgRole)}
              className={inputClass}
              data-testid="access-key-role"
            >
              <option value="ANNOTATOR">
                {t('admin.organizations.roleAnnotator')}
              </option>
              <option value="CONTRIBUTOR">
                {t('admin.organizations.roleContributor')}
              </option>
            </select>
            <p className={hintClass}>{t('accessKeys.form.roleHint')}</p>
          </div>
          {(isOrgAdmin ? groups.length > 0 : true) && (
            <div>
              <label htmlFor="access-key-group" className={labelClass}>
                {t('accessKeys.form.groupLabel')}
              </label>
              <select
                id="access-key-group"
                value={groupId}
                onChange={(e) => setGroupId(e.target.value)}
                className={inputClass}
                data-testid="access-key-group"
              >
                {isOrgAdmin && (
                  <option value="">{t('accessKeys.orgWide')}</option>
                )}
                {groups.map((g) => (
                  <option key={g.id} value={g.id}>
                    {g.name}
                  </option>
                ))}
              </select>
              <p className={hintClass}>
                {isOrgAdmin
                  ? t('accessKeys.form.groupHint')
                  : t('accessKeys.form.groupAdminHint')}
              </p>
            </div>
          )}
        </div>
      )}

      {mode === 'org' && (
        <div>
          <p className={labelClass}>{t('accessKeys.form.projectsLabel')}</p>
          <p className={hintClass}>{t('accessKeys.form.projectsHint')}</p>
          <div
            className="mt-2 max-h-40 space-y-1 overflow-y-auto rounded-md border border-zinc-200 p-2 dark:border-zinc-700"
            data-testid="access-key-projects"
          >
            {projects.length === 0 ? (
              <p className="text-xs text-zinc-500">
                {t('accessKeys.form.noProjects')}
              </p>
            ) : (
              projects.map((p) => (
                <label key={p.id} className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={projectIds.includes(p.id)}
                    onChange={() => toggleProject(p.id)}
                    data-testid={`access-key-project-${p.id}`}
                  />
                  <span className="truncate text-zinc-800 dark:text-zinc-200">
                    {p.title}
                  </span>
                </label>
              ))
            )}
          </div>
        </div>
      )}

      <div>
        <label htmlFor="access-key-expiry" className={labelClass}>
          {t('accessKeys.form.expiryLabel')}
        </label>
        <select
          id="access-key-expiry"
          value={expiry}
          onChange={(e) => setExpiry(e.target.value as ExpiryChoice)}
          className={inputClass}
          data-testid="access-key-expiry"
        >
          {EXPIRY_CHOICES.map((choice) => (
            <option key={choice} value={choice}>
              {t(
                choice === 'never'
                  ? 'accessKeys.form.expiryNever'
                  : `accessKeys.form.expiry${choice}`,
              )}
            </option>
          ))}
        </select>
      </div>

      <div>
        <button
          type="button"
          onClick={() => setShowLimits((v) => !v)}
          className="flex items-center gap-1 text-sm font-medium text-zinc-700 dark:text-zinc-300"
          aria-expanded={showLimits}
          data-testid="access-key-limits-toggle"
        >
          {showLimits ? (
            <ChevronDownIcon className="h-4 w-4" />
          ) : (
            <ChevronRightIcon className="h-4 w-4" />
          )}
          {t('accessKeys.form.rateLimits')}
        </button>
        {showLimits && (
          <div className="mt-2 grid gap-4 sm:grid-cols-2">
            <div>
              <label htmlFor="access-key-rpm" className={labelClass}>
                {t('accessKeys.form.perMinute')}
              </label>
              <input
                id="access-key-rpm"
                type="number"
                min={1}
                value={perMinute}
                onChange={(e) => setPerMinute(e.target.value)}
                className={inputClass}
                data-testid="access-key-rpm"
              />
            </div>
            <div>
              <label htmlFor="access-key-rpd" className={labelClass}>
                {t('accessKeys.form.perDay')}
              </label>
              <input
                id="access-key-rpd"
                type="number"
                min={1}
                value={perDay}
                onChange={(e) => setPerDay(e.target.value)}
                className={inputClass}
                data-testid="access-key-rpd"
              />
            </div>
            <p className={`${hintClass} sm:col-span-2`}>
              {t('accessKeys.form.rateLimitsHint')}
            </p>
          </div>
        )}
      </div>

      {error && (
        <p
          className="text-sm text-red-600 dark:text-red-400"
          role="alert"
          data-testid="access-key-form-error"
        >
          {error}
        </p>
      )}

      <div className="flex justify-end gap-2">
        <Button type="button" variant="outline" onClick={onCancel}>
          {t('accessKeys.cancel')}
        </Button>
        <Button
          type="submit"
          variant="filled"
          disabled={busy}
          data-testid="access-key-create-submit"
        >
          {busy ? t('accessKeys.form.creating') : t('accessKeys.form.create')}
        </Button>
      </div>
    </form>
  )
}

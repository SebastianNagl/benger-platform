'use client'

/**
 * Create form of an access key, written for non-technical staff: a name,
 * one of the plain-language presets (the scope list stays behind
 * "Erweitert"), and for organization keys the role, the group and an
 * optional project allowlist. Expiry defaults to one year.
 *
 * The scope list only offers what the creator may grant for this kind of
 * key (app/core/scopes.py); scopes that need a higher org-key role stay
 * visible but disabled, with the role they need. ORG_ADMIN keys are
 * org-wide only and only org-wide admins create them.
 */

import { Button } from '@/components/shared/Button'
import { Input } from '@/components/shared/Input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/shared/Select'
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
  offeredScopes,
  orgRoleLabelKey,
  presetIds,
  requiredRole,
  resolvePreset,
  roleAtLeast,
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
  /** The creator is a superadmin: personal keys may carry admin:platform. */
  isSuperadmin?: boolean
  /** Groups the caller may create keys for. */
  groups?: GroupOption[]
  projects?: ProjectOption[]
  onSubmit: (body: AccessKeyCreate) => Promise<void>
  onCancel: () => void
}

const labelClass = 'block text-sm font-medium text-zinc-900 dark:text-zinc-100'
const hintClass = 'mt-1 text-xs text-zinc-500 dark:text-zinc-400'

const FIRST_PRESET = 'benchmark_read'
// The Select treats an empty value as unset, so org-wide gets a sentinel.
const ORG_WIDE = '__org_wide__'

export function AccessKeyCreateForm({
  mode,
  catalog,
  isOrgAdmin = false,
  isSuperadmin = false,
  groups = [],
  projects = [],
  onSubmit,
  onCancel,
}: AccessKeyCreateFormProps) {
  const { t, locale } = useI18n()
  const ctxBase = useMemo(
    () => ({ mode, isOrgAdmin, isSuperadmin }),
    [mode, isOrgAdmin, isSuperadmin],
  )
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
  const [roleNotice, setRoleNotice] = useState<
    'contributor' | 'admin' | 'groupLowered' | null
  >(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const ctx = { ...ctxBase, role }
  const available = offeredScopes(catalog, ctxBase)
  const selectedPreset = matchPreset(catalog, scopes, ctxBase)
  // ORG_ADMIN keys: org-wide only, and only an org-wide admin creates them.
  const adminRoleOffered = mode === 'org' && isOrgAdmin && !groupId
  const roleOptions: AccessKeyOrgRole[] = adminRoleOffered
    ? ['ANNOTATOR', 'CONTRIBUTOR', 'ORG_ADMIN']
    : ['ANNOTATOR', 'CONTRIBUTOR']

  // Drop the selected scopes a key with `next` may not hold.
  const dropBlocked = (next: AccessKeyOrgRole) => {
    const blocked = new Set(
      available
        .filter((s) => !isScopeGrantable(s, { ...ctxBase, role: next }))
        .map((s) => s.name),
    )
    setScopes((prev) => prev.filter((s) => !blocked.has(s)))
  }

  const choosePreset = (id: string) => {
    setError(null)
    if (id === 'custom') {
      setShowAdvanced(true)
      return
    }
    const resolved = resolvePreset(catalog, id, ctxBase)
    const minRole = resolved.minRole
    if (mode === 'org' && minRole && !roleAtLeast(role, minRole)) {
      setRole(minRole)
      if (minRole === 'ORG_ADMIN') {
        // Admin keys are org-wide (only offered to org-wide admins).
        setGroupId('')
        setRoleNotice('admin')
      } else {
        setRoleNotice('contributor')
      }
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
    setRoleNotice(null)
    dropBlocked(next)
  }

  const changeGroup = (next: string) => {
    setGroupId(next)
    if (next && role === 'ORG_ADMIN') {
      // A group key cannot be an admin key.
      setRole('CONTRIBUTOR')
      setRoleNotice('groupLowered')
      dropBlocked('CONTRIBUTOR')
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
        <Input
          id="access-key-name"
          type="text"
          value={name}
          maxLength={120}
          onChange={(e) => setName(e.target.value)}
          placeholder={t('accessKeys.form.namePlaceholder')}
          className="mt-1"
          data-testid="access-key-name"
        />
      </div>

      <fieldset>
        <legend className={labelClass}>
          {t('accessKeys.form.presetLabel')}
        </legend>
        <div
          className="mt-2 flex flex-wrap gap-2"
          role="radiogroup"
          aria-label={t('accessKeys.form.presetLabel')}
        >
          {[...presets, 'custom'].map((id) => {
            const isSelected = selectedPreset === id
            return (
              <Button
                key={id}
                variant={isSelected ? 'filled' : 'outline'}
                role="radio"
                aria-checked={isSelected}
                value={id}
                title={
                  id === 'custom'
                    ? t('accessKeys.form.customDescription')
                    : presetDescription(id)
                }
                onClick={() => choosePreset(id)}
                className="px-4 py-2"
                data-testid={`access-key-preset-${id}`}
              >
                {id === 'custom'
                  ? t('accessKeys.form.custom')
                  : presetLabel(id)}
              </Button>
            )
          })}
        </div>
        <p className={hintClass} data-testid="access-key-preset-description">
          {selectedPreset === 'custom'
            ? t('accessKeys.form.customDescription')
            : presetDescription(selectedPreset)}
        </p>
        {roleNotice && (
          <p
            className="mt-2 text-xs text-amber-700 dark:text-amber-400"
            data-testid="access-key-role-notice"
          >
            {t(
              roleNotice === 'admin'
                ? 'accessKeys.form.roleSwitchedAdmin'
                : roleNotice === 'groupLowered'
                  ? 'accessKeys.form.roleLoweredForGroup'
                  : 'accessKeys.form.roleSwitched',
            )}
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
              const minRole = requiredRole(scope, ctx)
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
                    {minRole && !grantable && (
                      <span
                        className="block text-xs text-amber-700 dark:text-amber-400"
                        data-testid={`access-key-scope-needs-${scope.name}`}
                      >
                        {t(
                          minRole === 'ORG_ADMIN'
                            ? 'accessKeys.form.needsOrgAdmin'
                            : 'accessKeys.form.needsContributor',
                        )}
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
            <Select
              value={role}
              onValueChange={(v) => changeRole(v as AccessKeyOrgRole)}
            >
              <SelectTrigger
                id="access-key-role"
                className="mt-1"
                data-testid="access-key-role"
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {roleOptions.map((r) => (
                  <SelectItem key={r} value={r}>
                    {t(orgRoleLabelKey(r))}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className={hintClass}>{t('accessKeys.form.roleHint')}</p>
          </div>
          {(isOrgAdmin ? groups.length > 0 : true) && (
            <div>
              <label htmlFor="access-key-group" className={labelClass}>
                {t('accessKeys.form.groupLabel')}
              </label>
              <Select
                // Group admins get no org-wide option: until a group is
                // picked, show the placeholder rather than the sentinel.
                value={groupId || (isOrgAdmin ? ORG_WIDE : '')}
                onValueChange={(v) => changeGroup(v === ORG_WIDE ? '' : v)}
              >
                <SelectTrigger
                  id="access-key-group"
                  className="mt-1"
                  data-testid="access-key-group"
                >
                  <SelectValue placeholder={t('accessKeys.form.groupLabel')} />
                </SelectTrigger>
                <SelectContent>
                  {isOrgAdmin && (
                    <SelectItem value={ORG_WIDE}>
                      {t('accessKeys.orgWide')}
                    </SelectItem>
                  )}
                  {groups.map((g) => (
                    <SelectItem key={g.id} value={g.id}>
                      {g.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
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
        <Select
          value={expiry}
          onValueChange={(v) => setExpiry(v as ExpiryChoice)}
        >
          <SelectTrigger
            id="access-key-expiry"
            className="mt-1"
            data-testid="access-key-expiry"
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {EXPIRY_CHOICES.map((choice) => (
              <SelectItem key={choice} value={choice}>
                {t(
                  choice === 'never'
                    ? 'accessKeys.form.expiryNever'
                    : `accessKeys.form.expiry${choice}`,
                )}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
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
              <Input
                id="access-key-rpm"
                type="number"
                min={1}
                value={perMinute}
                onChange={(e) => setPerMinute(e.target.value)}
                className="mt-1"
                data-testid="access-key-rpm"
              />
            </div>
            <div>
              <label htmlFor="access-key-rpd" className={labelClass}>
                {t('accessKeys.form.perDay')}
              </label>
              <Input
                id="access-key-rpd"
                type="number"
                min={1}
                value={perDay}
                onChange={(e) => setPerDay(e.target.value)}
                className="mt-1"
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

'use client'

/**
 * OrgStorageConnections — admin modal for the org's S3-compatible storage
 * connections (cloud imports). Mirrors the OrgApiKeys modal UX: list with
 * status hints, inline add/edit form, per-connection test, delete with an
 * inline confirm step. Credentials are write-only — the server never returns
 * them (only a last-4 access-key hint).
 */

import { Button } from '@/components/shared/Button'
import { useI18n } from '@/contexts/I18nContext'
import {
  organizationsAPI,
  type OrgStorageConnection,
  type OrgStorageConnectionCreate,
  type OrgStorageConnectionUpdate,
} from '@/lib/api/organizations'
import { Dialog } from '@headlessui/react'
import {
  EyeIcon,
  EyeSlashIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline'
import { useCallback, useEffect, useState } from 'react'

interface OrgStorageConnectionsProps {
  organizationId: string
  isAdmin: boolean
  open: boolean
  onOpenChange: (open: boolean) => void
}

interface TestResult {
  type: 'success' | 'error'
  message: string
}

interface ConnectionForm {
  name: string
  endpoint_url: string
  bucket: string
  prefix: string
  region: string
  use_ssl: boolean
  access_key: string
  secret_key: string
}

const EMPTY_FORM: ConnectionForm = {
  name: '',
  endpoint_url: '',
  bucket: '',
  prefix: '',
  region: '',
  use_ssl: true,
  access_key: '',
  secret_key: '',
}

const inputClass =
  'w-full rounded-full bg-white px-4 py-2 text-sm text-zinc-900 ring-1 ring-zinc-900/10 transition placeholder:text-zinc-500 hover:ring-zinc-900/20 focus:outline-none focus:ring-2 focus:ring-emerald-500 dark:bg-white/5 dark:text-white dark:ring-inset dark:ring-white/10 dark:placeholder:text-zinc-400 dark:hover:ring-white/20 dark:focus:ring-emerald-400'

export function OrgStorageConnections({
  organizationId,
  isAdmin,
  open,
  onOpenChange,
}: OrgStorageConnectionsProps) {
  const { t } = useI18n()

  const [connections, setConnections] = useState<OrgStorageConnection[]>([])
  const [listLoading, setListLoading] = useState(false)
  const [message, setMessage] = useState<{
    type: 'success' | 'error'
    text: string
  } | null>(null)

  // 'new' = create form, a connection id = edit form, null = closed.
  const [editingId, setEditingId] = useState<string | null>(null)
  const [form, setForm] = useState<ConnectionForm>(EMPTY_FORM)
  const [showAccessKey, setShowAccessKey] = useState(false)
  const [showSecretKey, setShowSecretKey] = useState(false)
  const [saving, setSaving] = useState(false)

  // Keyed by connection id, or 'form' for the test-before-save button.
  const [testLoading, setTestLoading] = useState<Record<string, boolean>>({})
  const [testResults, setTestResults] = useState<
    Record<string, TestResult | null>
  >({})

  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null)
  const [deletingId, setDeletingId] = useState<string | null>(null)

  const fetchConnections = useCallback(async () => {
    setListLoading(true)
    try {
      const data = await organizationsAPI.listStorageConnections(organizationId)
      setConnections(data || [])
    } catch {
      setConnections([])
    } finally {
      setListLoading(false)
    }
  }, [organizationId])

  useEffect(() => {
    if (open) {
      setMessage(null)
      setEditingId(null)
      setForm(EMPTY_FORM)
      setTestResults({})
      setConfirmDeleteId(null)
      fetchConnections()
    }
  }, [open, fetchConnections])

  const startCreate = () => {
    setEditingId('new')
    setForm(EMPTY_FORM)
    setShowAccessKey(false)
    setShowSecretKey(false)
    setTestResults((prev) => ({ ...prev, form: null }))
    setMessage(null)
  }

  const startEdit = (conn: OrgStorageConnection) => {
    setEditingId(conn.id)
    setForm({
      name: conn.name,
      endpoint_url: conn.endpoint_url || '',
      bucket: conn.bucket,
      prefix: conn.prefix || '',
      region: conn.region || '',
      use_ssl: conn.use_ssl,
      access_key: '',
      secret_key: '',
    })
    setShowAccessKey(false)
    setShowSecretKey(false)
    setTestResults((prev) => ({ ...prev, form: null }))
    setMessage(null)
  }

  const cancelForm = () => {
    setEditingId(null)
    setForm(EMPTY_FORM)
    setTestResults((prev) => ({ ...prev, form: null }))
  }

  const setField = <K extends keyof ConnectionForm>(
    field: K,
    value: ConnectionForm[K]
  ) => {
    setForm((prev) => ({ ...prev, [field]: value }))
  }

  const isCreate = editingId === 'new'
  const canSave = isCreate
    ? !!(
        form.name.trim() &&
        form.bucket.trim() &&
        form.access_key.trim() &&
        form.secret_key.trim()
      )
    : !!(form.name.trim() && form.bucket.trim())

  const buildCreateBody = (): OrgStorageConnectionCreate => ({
    name: form.name.trim(),
    endpoint_url: form.endpoint_url.trim() || null,
    bucket: form.bucket.trim(),
    prefix: form.prefix.trim(),
    region: form.region.trim() || null,
    use_ssl: form.use_ssl,
    access_key: form.access_key.trim(),
    secret_key: form.secret_key.trim(),
  })

  const handleSave = async () => {
    if (!canSave || saving) return
    setSaving(true)
    setMessage(null)
    try {
      if (isCreate) {
        await organizationsAPI.createStorageConnection(
          organizationId,
          buildCreateBody()
        )
        setMessage({
          type: 'success',
          text: t('organizations.storageConnections.saved', {
            name: form.name.trim(),
          }),
        })
      } else if (editingId) {
        const body: OrgStorageConnectionUpdate = {
          name: form.name.trim(),
          endpoint_url: form.endpoint_url.trim() || null,
          bucket: form.bucket.trim(),
          prefix: form.prefix.trim(),
          region: form.region.trim() || null,
          use_ssl: form.use_ssl,
        }
        // Credentials optional on edit — only replace when re-entered.
        if (form.access_key.trim()) body.access_key = form.access_key.trim()
        if (form.secret_key.trim()) body.secret_key = form.secret_key.trim()
        await organizationsAPI.updateStorageConnection(
          organizationId,
          editingId,
          body
        )
        setMessage({
          type: 'success',
          text: t('organizations.storageConnections.updated', {
            name: form.name.trim(),
          }),
        })
      }
      cancelForm()
      await fetchConnections()
    } catch (error: any) {
      setMessage({
        type: 'error',
        text:
          error.response?.data?.detail ||
          t('organizations.storageConnections.saveFailed'),
      })
    } finally {
      setSaving(false)
    }
  }

  const handleTestForm = async () => {
    setTestLoading((prev) => ({ ...prev, form: true }))
    setTestResults((prev) => ({ ...prev, form: null }))
    try {
      const result = await organizationsAPI.testStorageConnection(
        organizationId,
        buildCreateBody()
      )
      setTestResults((prev) => ({
        ...prev,
        form: {
          type: result.status === 'success' ? 'success' : 'error',
          message: result.message,
        },
      }))
    } catch (error: any) {
      setTestResults((prev) => ({
        ...prev,
        form: {
          type: 'error',
          message:
            error.response?.data?.detail ||
            t('organizations.storageConnections.testFailed'),
        },
      }))
    } finally {
      setTestLoading((prev) => ({ ...prev, form: false }))
    }
  }

  const handleTestSaved = async (connId: string) => {
    setTestLoading((prev) => ({ ...prev, [connId]: true }))
    setTestResults((prev) => ({ ...prev, [connId]: null }))
    try {
      const result = await organizationsAPI.testSavedStorageConnection(
        organizationId,
        connId
      )
      setTestResults((prev) => ({
        ...prev,
        [connId]: {
          type: result.status === 'success' ? 'success' : 'error',
          message: result.message,
        },
      }))
    } catch (error: any) {
      setTestResults((prev) => ({
        ...prev,
        [connId]: {
          type: 'error',
          message:
            error.response?.data?.detail ||
            t('organizations.storageConnections.testFailed'),
        },
      }))
    } finally {
      setTestLoading((prev) => ({ ...prev, [connId]: false }))
    }
  }

  const handleDelete = async (conn: OrgStorageConnection) => {
    setDeletingId(conn.id)
    setMessage(null)
    try {
      await organizationsAPI.deleteStorageConnection(organizationId, conn.id)
      setMessage({
        type: 'success',
        text: t('organizations.storageConnections.deleted', {
          name: conn.name,
        }),
      })
      if (editingId === conn.id) cancelForm()
      await fetchConnections()
    } catch (error: any) {
      setMessage({
        type: 'error',
        text:
          error.response?.data?.detail ||
          t('organizations.storageConnections.deleteFailed'),
      })
    } finally {
      setDeletingId(null)
      setConfirmDeleteId(null)
    }
  }

  // The credential fields are required for a pre-save test; on edit the test
  // needs re-entered credentials too (the server never returns stored ones).
  const canTestForm = !!(
    form.bucket.trim() &&
    form.access_key.trim() &&
    form.secret_key.trim()
  )

  const renderTestResult = (result: TestResult | null | undefined) =>
    result ? (
      <div
        className={`rounded-md p-3 text-sm ${
          result.type === 'success'
            ? 'border border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-400'
            : 'border border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-950/50 dark:text-red-400'
        }`}
      >
        <div className="whitespace-pre-wrap">{result.message}</div>
      </div>
    ) : null

  return (
    <Dialog
      open={open}
      onClose={() => onOpenChange(false)}
      className="relative z-50"
    >
      <div className="fixed inset-0 bg-black/30" aria-hidden="true" />

      <div className="fixed inset-0 flex items-center justify-center p-4">
        <Dialog.Panel className="mx-auto w-full max-w-2xl rounded-lg bg-white shadow-xl dark:bg-zinc-800">
          {/* Header */}
          <div className="flex items-center justify-between border-b border-zinc-200 px-6 py-4 dark:border-zinc-700">
            <div>
              <Dialog.Title className="text-lg font-semibold text-zinc-900 dark:text-white">
                {t('organizations.storageConnections.dialogTitle')}
              </Dialog.Title>
              <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
                {t('organizations.storageConnections.dialogDescription')}
              </p>
            </div>
            <button
              onClick={() => onOpenChange(false)}
              className="rounded-md p-2 text-zinc-400 transition-colors hover:text-zinc-500 dark:text-zinc-500 dark:hover:text-zinc-400"
              aria-label="Close modal"
            >
              <XMarkIcon className="h-5 w-5" />
            </button>
          </div>

          {/* Content */}
          <div className="max-h-[70vh] overflow-y-auto px-6 py-4">
            <div className="space-y-6">
              {message && (
                <div
                  className={`rounded-md border p-4 text-sm ${
                    message.type === 'success'
                      ? 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-400'
                      : 'border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-950/50 dark:text-red-400'
                  }`}
                >
                  {message.text}
                </div>
              )}

              {!isAdmin && (
                <div className="rounded-lg border border-zinc-200 bg-zinc-50 p-4 dark:border-zinc-700 dark:bg-zinc-800/50">
                  <p className="text-sm text-zinc-600 dark:text-zinc-400">
                    {t('organizations.storageConnections.adminOnly')}
                  </p>
                </div>
              )}

              {/* Connection list */}
              {listLoading ? (
                <p className="text-sm text-zinc-500 dark:text-zinc-400">
                  {t('organizations.storageConnections.loading')}
                </p>
              ) : connections.length === 0 && editingId !== 'new' ? (
                <div className="rounded-lg border border-zinc-200 bg-zinc-50 p-4 dark:border-zinc-700 dark:bg-zinc-800/50">
                  <p className="text-sm text-zinc-600 dark:text-zinc-400">
                    {t('organizations.storageConnections.empty')}
                  </p>
                </div>
              ) : (
                <div className="grid grid-cols-1 gap-4">
                  {connections.map((conn) => {
                    const isTestLoading = testLoading[conn.id] || false
                    const isDeleting = deletingId === conn.id
                    return (
                      <div
                        key={conn.id}
                        className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-700 dark:bg-zinc-800"
                        data-testid={`storage-connection-${conn.id}`}
                      >
                        <div className="mb-2 flex items-start justify-between">
                          <div>
                            <h3 className="font-medium text-zinc-900 dark:text-white">
                              {conn.name}
                            </h3>
                            <p className="text-xs text-zinc-500 dark:text-zinc-400">
                              {conn.endpoint_url ||
                                t(
                                  'organizations.storageConnections.awsDefaultEndpoint'
                                )}
                            </p>
                            <p className="text-xs text-zinc-500 dark:text-zinc-400">
                              {conn.bucket}
                              {conn.prefix ? `/${conn.prefix}` : ''}
                            </p>
                          </div>
                          {conn.access_key_hint && (
                            <span className="inline-flex items-center rounded-full bg-zinc-100 px-2 py-1 font-mono text-xs text-zinc-600 dark:bg-zinc-700 dark:text-zinc-400">
                              {t(
                                'organizations.storageConnections.accessKeyHint',
                                { hint: conn.access_key_hint }
                              )}
                            </span>
                          )}
                        </div>

                        {renderTestResult(testResults[conn.id])}

                        {isAdmin && (
                          <div className="mt-3 flex justify-end space-x-2">
                            {confirmDeleteId === conn.id ? (
                              <>
                                <span className="self-center text-sm text-red-600 dark:text-red-400">
                                  {t(
                                    'organizations.storageConnections.deleteConfirm'
                                  )}
                                </span>
                                <Button
                                  variant="outline"
                                  onClick={() => handleDelete(conn)}
                                  disabled={isDeleting}
                                  className="text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-950/50"
                                >
                                  {isDeleting
                                    ? t(
                                        'organizations.storageConnections.deleting'
                                      )
                                    : t(
                                        'organizations.storageConnections.deleteConfirmYes'
                                      )}
                                </Button>
                                <Button
                                  variant="outline"
                                  onClick={() => setConfirmDeleteId(null)}
                                  disabled={isDeleting}
                                >
                                  {t('common.cancel')}
                                </Button>
                              </>
                            ) : (
                              <>
                                <Button
                                  variant="outline"
                                  onClick={() => handleTestSaved(conn.id)}
                                  disabled={isTestLoading}
                                  className="text-blue-600 hover:bg-blue-50 dark:text-blue-400 dark:hover:bg-blue-950/50"
                                >
                                  {isTestLoading
                                    ? t(
                                        'organizations.storageConnections.testing'
                                      )
                                    : t(
                                        'organizations.storageConnections.testConnection'
                                      )}
                                </Button>
                                <Button
                                  variant="outline"
                                  onClick={() => startEdit(conn)}
                                >
                                  {t('organizations.storageConnections.edit')}
                                </Button>
                                <Button
                                  variant="outline"
                                  onClick={() => setConfirmDeleteId(conn.id)}
                                  className="text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-950/50"
                                >
                                  {t('organizations.storageConnections.delete')}
                                </Button>
                              </>
                            )}
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              )}

              {/* Add / edit form */}
              {isAdmin && editingId !== null && (
                <div
                  className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-700 dark:bg-zinc-800"
                  data-testid="storage-connection-form"
                >
                  <h3 className="mb-3 font-medium text-zinc-900 dark:text-white">
                    {isCreate
                      ? t('organizations.storageConnections.addTitle')
                      : t('organizations.storageConnections.editTitle')}
                  </h3>
                  <div className="space-y-3">
                    <input
                      type="text"
                      placeholder={t(
                        'organizations.storageConnections.namePlaceholder'
                      )}
                      value={form.name}
                      onChange={(e) => setField('name', e.target.value)}
                      className={inputClass}
                      aria-label={t('organizations.storageConnections.name')}
                    />
                    <input
                      type="text"
                      placeholder={t(
                        'organizations.storageConnections.endpointPlaceholder'
                      )}
                      value={form.endpoint_url}
                      onChange={(e) => setField('endpoint_url', e.target.value)}
                      className={inputClass}
                      aria-label={t(
                        'organizations.storageConnections.endpoint'
                      )}
                    />
                    <div className="grid grid-cols-2 gap-3">
                      <input
                        type="text"
                        placeholder={t(
                          'organizations.storageConnections.bucketPlaceholder'
                        )}
                        value={form.bucket}
                        onChange={(e) => setField('bucket', e.target.value)}
                        className={inputClass}
                        aria-label={t(
                          'organizations.storageConnections.bucket'
                        )}
                      />
                      <input
                        type="text"
                        placeholder={t(
                          'organizations.storageConnections.prefixPlaceholder'
                        )}
                        value={form.prefix}
                        onChange={(e) => setField('prefix', e.target.value)}
                        className={inputClass}
                        aria-label={t(
                          'organizations.storageConnections.prefix'
                        )}
                      />
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                      <input
                        type="text"
                        placeholder={t(
                          'organizations.storageConnections.regionPlaceholder'
                        )}
                        value={form.region}
                        onChange={(e) => setField('region', e.target.value)}
                        className={inputClass}
                        aria-label={t(
                          'organizations.storageConnections.region'
                        )}
                      />
                      <label className="flex items-center gap-2 text-sm text-zinc-700 dark:text-zinc-300">
                        <input
                          type="checkbox"
                          checked={form.use_ssl}
                          onChange={(e) =>
                            setField('use_ssl', e.target.checked)
                          }
                          className="h-4 w-4 rounded border-zinc-300 text-emerald-600 focus:ring-emerald-500"
                        />
                        {t('organizations.storageConnections.useSsl')}
                      </label>
                    </div>
                    <div className="relative">
                      <input
                        type={showAccessKey ? 'text' : 'password'}
                        placeholder={
                          isCreate
                            ? t(
                                'organizations.storageConnections.accessKeyPlaceholder'
                              )
                            : t(
                                'organizations.storageConnections.accessKeyKeepPlaceholder'
                              )
                        }
                        value={form.access_key}
                        onChange={(e) =>
                          setField('access_key', e.target.value)
                        }
                        className={`${inputClass} pr-10`}
                        aria-label={t(
                          'organizations.storageConnections.accessKey'
                        )}
                      />
                      <button
                        type="button"
                        onClick={() => setShowAccessKey((v) => !v)}
                        className="absolute inset-y-0 right-0 flex items-center pr-3 text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300"
                        aria-label={t(
                          'organizations.storageConnections.toggleAccessKey'
                        )}
                      >
                        {showAccessKey ? (
                          <EyeSlashIcon className="h-4 w-4" />
                        ) : (
                          <EyeIcon className="h-4 w-4" />
                        )}
                      </button>
                    </div>
                    <div className="relative">
                      <input
                        type={showSecretKey ? 'text' : 'password'}
                        placeholder={
                          isCreate
                            ? t(
                                'organizations.storageConnections.secretKeyPlaceholder'
                              )
                            : t(
                                'organizations.storageConnections.secretKeyKeepPlaceholder'
                              )
                        }
                        value={form.secret_key}
                        onChange={(e) =>
                          setField('secret_key', e.target.value)
                        }
                        className={`${inputClass} pr-10`}
                        aria-label={t(
                          'organizations.storageConnections.secretKey'
                        )}
                      />
                      <button
                        type="button"
                        onClick={() => setShowSecretKey((v) => !v)}
                        className="absolute inset-y-0 right-0 flex items-center pr-3 text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300"
                        aria-label={t(
                          'organizations.storageConnections.toggleSecretKey'
                        )}
                      >
                        {showSecretKey ? (
                          <EyeSlashIcon className="h-4 w-4" />
                        ) : (
                          <EyeIcon className="h-4 w-4" />
                        )}
                      </button>
                    </div>

                    {renderTestResult(testResults.form)}

                    <div className="flex justify-end space-x-2">
                      <Button
                        variant="outline"
                        onClick={cancelForm}
                        disabled={saving}
                      >
                        {t('common.cancel')}
                      </Button>
                      <Button
                        variant="outline"
                        onClick={handleTestForm}
                        disabled={!canTestForm || !!testLoading.form || saving}
                        className="text-blue-600 hover:bg-blue-50 dark:text-blue-400 dark:hover:bg-blue-950/50"
                      >
                        {testLoading.form
                          ? t('organizations.storageConnections.testing')
                          : t(
                              'organizations.storageConnections.testConnection'
                            )}
                      </Button>
                      <Button
                        variant="filled"
                        onClick={handleSave}
                        disabled={!canSave || saving}
                      >
                        {saving
                          ? t('organizations.storageConnections.saving')
                          : t('organizations.storageConnections.save')}
                      </Button>
                    </div>
                  </div>
                </div>
              )}

              {isAdmin && editingId === null && (
                <div className="flex justify-end">
                  <Button variant="filled" onClick={startCreate}>
                    {t('organizations.storageConnections.addConnection')}
                  </Button>
                </div>
              )}

              {isAdmin && (
                <div className="space-y-1 text-xs text-zinc-500 dark:text-zinc-400">
                  <p>{t('organizations.storageConnections.encryptedInfo')}</p>
                  <p>{t('organizations.storageConnections.membersInfo')}</p>
                </div>
              )}
            </div>
          </div>

          {/* Footer */}
          <div className="flex items-center justify-end border-t border-zinc-200 px-6 py-4 dark:border-zinc-700">
            <button
              onClick={() => onOpenChange(false)}
              className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-emerald-700 dark:bg-emerald-500 dark:hover:bg-emerald-600"
            >
              {t('common.done')}
            </button>
          </div>
        </Dialog.Panel>
      </div>
    </Dialog>
  )
}

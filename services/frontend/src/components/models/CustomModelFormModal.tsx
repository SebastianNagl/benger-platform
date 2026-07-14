'use client'

/**
 * CustomModelFormModal - register or edit a custom model (BYOM).
 *
 * Modal shell follows APIKeysModal. Create mode POSTs the full payload
 * (optionally including an api_key that is stored as the creator's own
 * credential); edit mode PATCHes only the changed fields and never touches
 * credentials (those are managed in CustomModelCredentialRow).
 *
 * After a successful create the modal stays open on a success step that
 * offers an immediate connection test against the new model.
 */

import { Button } from '@/components/shared/Button'
import { ToggleSwitch } from '@/components/shared/ToggleSwitch'
import { useI18n } from '@/contexts/I18nContext'
import { customModelsAPI } from '@/lib/api/customModels'
import type {
  CustomModel,
  CustomModelCreate,
  CustomModelUpdate,
} from '@/lib/api/types'
import { Dialog } from '@headlessui/react'
import { EyeIcon, EyeSlashIcon, XMarkIcon } from '@heroicons/react/24/outline'
import { useEffect, useState } from 'react'

/** Flatten any error `detail` shape (string, FastAPI 422 array of
 * {loc,msg}, or object) into a single human-readable string, so it can
 * never reach React as a non-string child. */
function coerceErrorDetail(detail: unknown): string | null {
  if (detail == null) return null
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    const msgs = detail
      .map((d) =>
        d && typeof d === 'object' && 'msg' in d
          ? String((d as { msg: unknown }).msg)
          : typeof d === 'string'
            ? d
            : null
      )
      .filter(Boolean)
    return msgs.length ? msgs.join('; ') : null
  }
  if (typeof detail === 'object' && 'msg' in (detail as object)) {
    return String((detail as { msg: unknown }).msg)
  }
  return null
}

interface CustomModelFormModalProps {
  isOpen: boolean
  onClose: () => void
  /** Pass an existing model to switch to edit mode. */
  model?: CustomModel | null
  /** Called with the created/updated model after a successful save. */
  onSaved?: (model: CustomModel) => void
}

interface FormState {
  name: string
  description: string
  base_url: string
  endpoint_model_name: string
  requires_api_key: boolean
  input_cost: string
  output_cost: string
  api_key: string
}

const emptyForm: FormState = {
  name: '',
  description: '',
  base_url: '',
  endpoint_model_name: '',
  requires_api_key: true,
  input_cost: '',
  output_cost: '',
  api_key: '',
}

function formFromModel(model: CustomModel): FormState {
  return {
    name: model.name ?? '',
    description: model.description ?? '',
    base_url: model.base_url ?? '',
    endpoint_model_name: model.endpoint_model_name ?? '',
    requires_api_key: model.requires_api_key,
    input_cost:
      model.input_cost_per_million != null
        ? String(model.input_cost_per_million)
        : '',
    output_cost:
      model.output_cost_per_million != null
        ? String(model.output_cost_per_million)
        : '',
    api_key: '',
  }
}

export function CustomModelFormModal({
  isOpen,
  onClose,
  model = null,
  onSaved,
}: CustomModelFormModalProps) {
  const { t } = useI18n()
  const isEdit = !!model

  const [form, setForm] = useState<FormState>(emptyForm)
  const [errors, setErrors] = useState<Partial<Record<keyof FormState, string>>>(
    {}
  )
  const [showApiKey, setShowApiKey] = useState(false)
  const [saving, setSaving] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [createdModel, setCreatedModel] = useState<CustomModel | null>(null)
  const [testLoading, setTestLoading] = useState(false)
  const [testResult, setTestResult] = useState<{
    type: 'success' | 'error'
    message: string
  } | null>(null)

  // Reset on open (and prefill in edit mode).
  useEffect(() => {
    if (isOpen) {
      setForm(model ? formFromModel(model) : emptyForm)
      setErrors({})
      setSubmitError(null)
      setCreatedModel(null)
      setTestResult(null)
      setShowApiKey(false)
      setSaving(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, model?.id])

  const setField = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }))
    setErrors((prev) => ({ ...prev, [key]: undefined }))
  }

  const parseBaseUrl = (value: string): URL | null => {
    try {
      const url = new URL(value)
      if (url.protocol !== 'http:' && url.protocol !== 'https:') return null
      return url
    } catch {
      return null
    }
  }

  const parsedUrl = parseBaseUrl(form.base_url.trim())
  const showHttpWarning =
    !!parsedUrl &&
    parsedUrl.protocol === 'http:' &&
    !['localhost', '127.0.0.1'].includes(parsedUrl.hostname)

  const validate = (): boolean => {
    const next: Partial<Record<keyof FormState, string>> = {}

    if (!form.name.trim()) {
      next.name = t('customModels.form.nameRequired')
    } else if (form.name.trim().length > 100) {
      next.name = t('customModels.form.nameTooLong')
    }

    if (!form.base_url.trim()) {
      next.base_url = t('customModels.form.baseUrlRequired')
    } else if (!parseBaseUrl(form.base_url.trim())) {
      next.base_url = t('customModels.form.baseUrlInvalid')
    }

    if (!form.endpoint_model_name.trim()) {
      next.endpoint_model_name = t(
        'customModels.form.endpointModelNameRequired'
      )
    } else if (form.endpoint_model_name.trim().length > 255) {
      // Backend caps endpoint_model_name at 255 (CustomModelCreate); catch
      // it here so an over-long value is a field error, not a 422.
      next.endpoint_model_name = t(
        'customModels.form.endpointModelNameTooLong'
      )
    }

    const inputCost = form.input_cost.trim()
    const outputCost = form.output_cost.trim()
    if ((inputCost === '') !== (outputCost === '')) {
      next.input_cost = t('customModels.form.pricingBothOrNeither')
    } else if (inputCost !== '') {
      const inVal = Number(inputCost)
      const outVal = Number(outputCost)
      if (
        !Number.isFinite(inVal) ||
        !Number.isFinite(outVal) ||
        inVal < 0 ||
        outVal < 0
      ) {
        next.input_cost = t('customModels.form.pricingInvalid')
      }
    }

    setErrors(next)
    return Object.keys(next).length === 0
  }

  const buildCreatePayload = (): CustomModelCreate => {
    const payload: CustomModelCreate = {
      name: form.name.trim(),
      base_url: form.base_url.trim(),
      endpoint_model_name: form.endpoint_model_name.trim(),
      requires_api_key: form.requires_api_key,
    }
    if (form.description.trim()) payload.description = form.description.trim()
    if (form.input_cost.trim() !== '') {
      payload.input_cost_per_million = Number(form.input_cost.trim())
      payload.output_cost_per_million = Number(form.output_cost.trim())
    }
    if (form.requires_api_key && form.api_key.trim()) {
      payload.api_key = form.api_key.trim()
    }
    return payload
  }

  const buildUpdatePayload = (original: CustomModel): CustomModelUpdate => {
    const payload: CustomModelUpdate = {}
    const name = form.name.trim()
    if (name !== original.name) payload.name = name

    const description = form.description.trim()
    if (description !== (original.description ?? '')) {
      payload.description = description
    }

    const baseUrl = form.base_url.trim()
    if (baseUrl !== original.base_url) payload.base_url = baseUrl

    const endpointName = form.endpoint_model_name.trim()
    if (endpointName !== original.endpoint_model_name) {
      payload.endpoint_model_name = endpointName
    }

    if (form.requires_api_key !== original.requires_api_key) {
      payload.requires_api_key = form.requires_api_key
    }

    const inputCost =
      form.input_cost.trim() === '' ? null : Number(form.input_cost.trim())
    const outputCost =
      form.output_cost.trim() === '' ? null : Number(form.output_cost.trim())
    if (inputCost !== (original.input_cost_per_million ?? null)) {
      payload.input_cost_per_million = inputCost
    }
    if (outputCost !== (original.output_cost_per_million ?? null)) {
      payload.output_cost_per_million = outputCost
    }

    return payload
  }

  const handleSubmit = async () => {
    if (!validate()) return

    setSaving(true)
    setSubmitError(null)

    try {
      if (isEdit && model) {
        const payload = buildUpdatePayload(model)
        const updated = await customModelsAPI.update(model.id, payload)
        onSaved?.(updated)
        onClose()
      } else {
        const created = await customModelsAPI.create(buildCreatePayload())
        setCreatedModel(created)
        onSaved?.(created)
      }
    } catch (error: any) {
      const rawDetail =
        error?.response?.data?.detail ??
        (error instanceof Error ? error.message : null)
      // FastAPI 422 returns `detail` as an array of {loc,msg,...} objects.
      // Rendering that array as a JSX child throws ("Objects are not valid
      // as a React child") and takes the whole page down, so flatten any
      // non-string shape into a readable string first.
      const detail = coerceErrorDetail(rawDetail)
      setSubmitError(
        detail ||
          (isEdit
            ? t('customModels.form.updateFailed')
            : t('customModels.form.createFailed'))
      )
    } finally {
      setSaving(false)
    }
  }

  const handleTestCreated = async () => {
    if (!createdModel) return
    setTestLoading(true)
    setTestResult(null)
    try {
      const result = await customModelsAPI.testConnection(createdModel.id)
      setTestResult({ type: result.status, message: result.message })
    } catch (error: any) {
      const detail =
        error?.response?.data?.detail || t('customModels.form.testFailed')
      setTestResult({ type: 'error', message: detail })
    } finally {
      setTestLoading(false)
    }
  }

  const inputClass =
    'w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 placeholder:text-zinc-400 focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500 dark:border-zinc-600 dark:bg-zinc-900 dark:text-white'

  const fieldError = (key: keyof FormState) =>
    errors[key] && (
      <p
        className="mt-1 text-sm text-red-600 dark:text-red-400"
        data-testid={`custom-model-error-${key}`}
      >
        {errors[key]}
      </p>
    )

  return (
    <Dialog open={isOpen} onClose={onClose} className="relative z-50">
      {/* Backdrop */}
      <div className="fixed inset-0 bg-black/30" aria-hidden="true" />

      {/* Full-screen container to center the panel */}
      <div className="fixed inset-0 flex items-center justify-center p-4">
        <Dialog.Panel
          className="mx-auto w-full max-w-2xl rounded-lg bg-white shadow-xl dark:bg-zinc-800"
          data-testid="custom-model-form-modal"
        >
          {/* Header */}
          <div className="flex items-center justify-between border-b border-zinc-200 px-6 py-4 dark:border-zinc-700">
            <div>
              <Dialog.Title className="text-lg font-semibold text-zinc-900 dark:text-white">
                {isEdit
                  ? t('customModels.form.editTitle')
                  : t('customModels.form.createTitle')}
              </Dialog.Title>
              <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
                {t('customModels.form.subtitle')}
              </p>
            </div>
            <button
              onClick={onClose}
              className="rounded-md p-2 text-zinc-400 transition-colors hover:text-zinc-500 dark:text-zinc-500 dark:hover:text-zinc-400"
              aria-label={t('shared.alertDialog.close')}
            >
              <XMarkIcon className="h-5 w-5" />
            </button>
          </div>

          {/* Content */}
          <div className="max-h-[70vh] overflow-y-auto px-6 py-4">
            {createdModel ? (
              /* Success step after create: offer an immediate connection test. */
              <div className="space-y-4" data-testid="custom-model-form-success">
                <div className="rounded-md border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-400">
                  {t('customModels.form.successMessage', {
                    name: createdModel.name,
                  })}
                </div>

                {testResult && (
                  <div
                    className={`rounded-md p-3 text-sm ${
                      testResult.type === 'success'
                        ? 'border border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-400'
                        : 'border border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-950/50 dark:text-red-400'
                    }`}
                    data-testid="custom-model-form-test-result"
                  >
                    <div className="whitespace-pre-wrap">
                      {testResult.message}
                    </div>
                  </div>
                )}

                <div className="flex justify-end space-x-2">
                  <Button
                    variant="outline"
                    onClick={handleTestCreated}
                    disabled={testLoading}
                    data-testid="custom-model-form-test-button"
                  >
                    {testLoading
                      ? t('customModels.form.testing')
                      : t('customModels.form.testConnection')}
                  </Button>
                  <Button
                    variant="filled"
                    onClick={onClose}
                    data-testid="custom-model-form-close-button"
                  >
                    {t('customModels.form.close')}
                  </Button>
                </div>
              </div>
            ) : (
              <div className="space-y-4">
                {submitError && (
                  <div
                    className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-950/50 dark:text-red-400"
                    data-testid="custom-model-form-error"
                  >
                    {submitError}
                  </div>
                )}

                {/* Name */}
                <div>
                  <label className="mb-1 block text-sm font-medium text-zinc-700 dark:text-zinc-300">
                    {t('customModels.form.name')}
                    <span className="ml-1 text-red-600 dark:text-red-400">
                      *
                    </span>
                  </label>
                  <input
                    type="text"
                    maxLength={100}
                    value={form.name}
                    onChange={(e) => setField('name', e.target.value)}
                    placeholder={t('customModels.form.namePlaceholder')}
                    className={inputClass}
                    data-testid="custom-model-name-input"
                  />
                  {fieldError('name')}
                </div>

                {/* Description */}
                <div>
                  <label className="mb-1 block text-sm font-medium text-zinc-700 dark:text-zinc-300">
                    {t('customModels.form.description')}
                  </label>
                  <textarea
                    rows={2}
                    value={form.description}
                    onChange={(e) => setField('description', e.target.value)}
                    placeholder={t('customModels.form.descriptionPlaceholder')}
                    className={inputClass}
                    data-testid="custom-model-description-input"
                  />
                </div>

                {/* Base URL */}
                <div>
                  <label className="mb-1 block text-sm font-medium text-zinc-700 dark:text-zinc-300">
                    {t('customModels.form.baseUrl')}
                    <span className="ml-1 text-red-600 dark:text-red-400">
                      *
                    </span>
                  </label>
                  <input
                    type="text"
                    value={form.base_url}
                    onChange={(e) => setField('base_url', e.target.value)}
                    placeholder="https://api.example.com/v1"
                    className={inputClass}
                    data-testid="custom-model-base-url-input"
                  />
                  <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                    {t('customModels.form.baseUrlHelp')}
                  </p>
                  {fieldError('base_url')}
                  {showHttpWarning && (
                    <p
                      className="mt-1 text-sm text-amber-600 dark:text-amber-400"
                      data-testid="custom-model-http-warning"
                    >
                      {t('customModels.form.httpWarning')}
                    </p>
                  )}
                </div>

                {/* Endpoint model name */}
                <div>
                  <label className="mb-1 block text-sm font-medium text-zinc-700 dark:text-zinc-300">
                    {t('customModels.form.endpointModelName')}
                    <span className="ml-1 text-red-600 dark:text-red-400">
                      *
                    </span>
                  </label>
                  <input
                    type="text"
                    value={form.endpoint_model_name}
                    onChange={(e) =>
                      setField('endpoint_model_name', e.target.value)
                    }
                    placeholder="llama-3.3-70b-instruct"
                    maxLength={255}
                    className={inputClass}
                    data-testid="custom-model-endpoint-name-input"
                  />
                  <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                    {t('customModels.form.endpointModelNameHelp')}
                  </p>
                  {fieldError('endpoint_model_name')}
                </div>

                {/* Requires API key */}
                <div className="flex items-start justify-between gap-4 rounded-lg border border-zinc-200 p-3 dark:border-zinc-700">
                  <div>
                    <span className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
                      {t('customModels.form.requiresApiKey')}
                    </span>
                    <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                      {t('customModels.form.requiresApiKeyHelp')}
                    </p>
                  </div>
                  <div data-testid="custom-model-requires-key-toggle">
                    <ToggleSwitch
                      enabled={form.requires_api_key}
                      onChange={(enabled) =>
                        setField('requires_api_key', enabled)
                      }
                    />
                  </div>
                </div>

                {/* API key (create mode only, when a key is required) */}
                {!isEdit && form.requires_api_key && (
                  <div>
                    <label className="mb-1 block text-sm font-medium text-zinc-700 dark:text-zinc-300">
                      {t('customModels.form.apiKey')}
                    </label>
                    <div className="relative">
                      <input
                        type={showApiKey ? 'text' : 'password'}
                        value={form.api_key}
                        onChange={(e) => setField('api_key', e.target.value)}
                        placeholder={t('customModels.form.apiKeyPlaceholder')}
                        className={`${inputClass} pr-10`}
                        data-testid="custom-model-api-key-input"
                      />
                      <button
                        type="button"
                        onClick={() => setShowApiKey((prev) => !prev)}
                        className="absolute inset-y-0 right-0 flex items-center pr-3 text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300"
                      >
                        {showApiKey ? (
                          <EyeSlashIcon className="h-4 w-4" />
                        ) : (
                          <EyeIcon className="h-4 w-4" />
                        )}
                      </button>
                    </div>
                    <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                      {t('customModels.form.apiKeyHelp')}
                    </p>
                  </div>
                )}

                {/* Pricing */}
                <div>
                  <label className="mb-1 block text-sm font-medium text-zinc-700 dark:text-zinc-300">
                    {t('customModels.form.pricing')}
                  </label>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <input
                        type="number"
                        min={0}
                        step="0.01"
                        value={form.input_cost}
                        onChange={(e) => setField('input_cost', e.target.value)}
                        placeholder={t('customModels.form.inputCost')}
                        className={inputClass}
                        data-testid="custom-model-input-cost-input"
                      />
                    </div>
                    <div>
                      <input
                        type="number"
                        min={0}
                        step="0.01"
                        value={form.output_cost}
                        onChange={(e) =>
                          setField('output_cost', e.target.value)
                        }
                        placeholder={t('customModels.form.outputCost')}
                        className={inputClass}
                        data-testid="custom-model-output-cost-input"
                      />
                    </div>
                  </div>
                  <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                    {t('customModels.form.pricingHelp')}
                  </p>
                  {fieldError('input_cost')}
                </div>
              </div>
            )}
          </div>

          {/* Footer */}
          {!createdModel && (
            <div className="flex items-center justify-end space-x-2 border-t border-zinc-200 px-6 py-4 dark:border-zinc-700">
              <Button
                variant="outline"
                onClick={onClose}
                disabled={saving}
                data-testid="custom-model-form-cancel"
              >
                {t('customModels.form.cancel')}
              </Button>
              <Button
                variant="filled"
                onClick={handleSubmit}
                disabled={saving}
                data-testid="custom-model-form-submit"
              >
                {saving
                  ? t('customModels.form.saving')
                  : isEdit
                    ? t('customModels.form.saveChanges')
                    : t('customModels.form.create')}
              </Button>
            </div>
          )}
        </Dialog.Panel>
      </div>
    </Dialog>
  )
}

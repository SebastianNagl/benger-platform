'use client'

import { HeroPattern } from '@/components/shared'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/shared/Select'
import { useI18n } from '@/contexts/I18nContext'
import { useEffect, useState } from 'react'

interface LLMModel {
  id: string
  name: string
  description: string | null
  provider: string
  model_type: string
  capabilities: string[]
  config_schema: Record<string, unknown> | null
  default_config: Record<string, unknown> | null
  parameter_constraints?: {
    temperature?: {
      supported: boolean
      required_value?: number
      default?: number
      min?: number
      max?: number
      reason?: string
    }
    max_tokens?: { default: number }
    reproducibility_impact?: string
  } | null
  input_cost_per_million: number | null
  output_cost_per_million: number | null
  is_active: boolean
}

interface ProviderCapability {
  display_name: string
  temperature: { min: number; max: number; default: number }
  structured_output: { method: string; strict_mode: boolean; guaranteed: boolean }
  determinism: { seed_support: boolean; recommended_seed?: number }
}

export default function ModelsPage() {
  const { t } = useI18n()
  const [models, setModels] = useState<LLMModel[]>([])
  const [providerCapabilities, setProviderCapabilities] = useState<
    Record<string, ProviderCapability>
  >({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [providerFilter, setProviderFilter] = useState('all')
  const [selectedModel, setSelectedModel] = useState<LLMModel | null>(null)

  // Build model settings JSON for modal
  const getModelSettings = (model: LLMModel) => {
    const providerKey = model.provider.toLowerCase()
    const provider = providerCapabilities[providerKey]

    return {
      model: {
        id: model.id,
        name: model.name,
        description: model.description,
        provider: model.provider,
        model_type: model.model_type,
        capabilities: model.capabilities,
        is_active: model.is_active,
      },
      provider_settings: provider
        ? {
            display_name: provider.display_name,
            temperature: provider.temperature,
            structured_output: provider.structured_output,
            determinism: provider.determinism,
          }
        : null,
      pricing:
        model.input_cost_per_million != null && model.output_cost_per_million != null
          ? {
              input_per_million_tokens: model.input_cost_per_million,
              output_per_million_tokens: model.output_cost_per_million,
              currency: 'USD',
            }
          : null,
    }
  }

  useEffect(() => {
    async function fetchData() {
      try {
        const [modelsRes, capabilitiesRes] = await Promise.all([
          fetch('/api/llm_models/public/models'),
          fetch('/api/llm_models/public/provider-capabilities'),
        ])

        if (!modelsRes.ok) {
          throw new Error(t('models.fetchFailed'))
        }

        const modelsData = await modelsRes.json()
        setModels(modelsData)

        if (capabilitiesRes.ok) {
          const capData = await capabilitiesRes.json()
          setProviderCapabilities(capData)
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : t('models.unknownError'))
      } finally {
        setLoading(false)
      }
    }

    fetchData()
  }, [])

  // Get unique providers for filter
  const providers = [...new Set(models.map((m) => m.provider))].sort()

  // Filter models
  const filteredModels = models.filter((model) => {
    const matchesSearch =
      searchQuery === '' ||
      model.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      model.id.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (model.description?.toLowerCase().includes(searchQuery.toLowerCase()) ?? false)

    const matchesProvider = providerFilter === 'all' || model.provider === providerFilter

    return matchesSearch && matchesProvider
  })

  // Group by provider
  const groupedModels = filteredModels.reduce(
    (acc, model) => {
      if (!acc[model.provider]) {
        acc[model.provider] = []
      }
      acc[model.provider].push(model)
      return acc
    },
    {} as Record<string, LLMModel[]>
  )

  // Sort providers alphabetically
  const sortedProviders = Object.keys(groupedModels).sort()

  return (
    <>
      <HeroPattern />

      <div className="container mx-auto max-w-6xl px-4 pb-10 pt-16">
        <div className="mb-8">
          <h1 className="text-3xl font-bold tracking-tight text-zinc-900 dark:text-white">
            {t('models.title')}
          </h1>
          <p className="mt-2 text-lg text-zinc-600 dark:text-zinc-400">
            {t('models.subtitle', { count: models.length })}
          </p>
        </div>

        {/* Filters */}
        <div className="mb-6 flex flex-col gap-4 sm:flex-row">
          <div className="flex-1">
            <input
              type="text"
              placeholder={t('models.searchPlaceholder')}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full rounded-full bg-white px-4 py-2 text-sm text-zinc-900 ring-1 ring-zinc-900/10 transition placeholder:text-zinc-500 hover:ring-zinc-900/20 focus:outline-none focus:ring-2 focus:ring-emerald-500 dark:bg-white/5 dark:text-white dark:ring-inset dark:ring-white/10 dark:placeholder:text-zinc-400 dark:hover:ring-white/20 dark:focus:ring-emerald-400"
            />
          </div>
          <div className="w-full sm:w-48">
            <Select value={providerFilter} onValueChange={setProviderFilter}>
              <SelectTrigger>
                <SelectValue placeholder={t('models.allProviders')} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">{t('models.allProviders')}</SelectItem>
                {providers.map((provider) => (
                  <SelectItem key={provider} value={provider}>
                    {provider}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        {/* Loading state */}
        {loading && (
          <div className="flex items-center justify-center py-12">
            <div className="text-zinc-600 dark:text-zinc-400">{t('models.loading')}</div>
          </div>
        )}

        {/* Error state */}
        {error && (
          <div className="rounded-lg bg-red-50 p-4 text-red-600 dark:bg-red-900/20 dark:text-red-400">
            {t('models.error')}: {error}
          </div>
        )}

        {/* Models list */}
        {!loading && !error && (
          <div className="space-y-8">
            {sortedProviders.length === 0 ? (
              <div className="py-12 text-center text-zinc-600 dark:text-zinc-400">
                {t('models.noModels')}
              </div>
            ) : (
              sortedProviders.map((provider) => (
                <div key={provider}>
                  <div className="mb-4 flex items-center gap-3">
                    <h2 className="text-xl font-semibold text-zinc-900 dark:text-white">
                      {provider}
                    </h2>
                    <span className="rounded-full bg-zinc-100 px-2.5 py-0.5 text-sm text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400">
                      {t('models.modelCount', { count: groupedModels[provider].length })}
                    </span>
                  </div>

                  <div className="overflow-hidden rounded-lg border border-zinc-200 dark:border-zinc-700">
                    <table className="w-full">
                      <thead className="bg-zinc-50 dark:bg-zinc-800">
                        <tr>
                          <th className="px-4 py-3 text-left text-sm font-medium text-zinc-600 dark:text-zinc-400">
                            {t('models.columns.model')}
                          </th>
                          <th className="hidden px-4 py-3 text-left text-sm font-medium text-zinc-600 dark:text-zinc-400 md:table-cell">
                            {t('models.columns.description')}
                          </th>
                          <th className="hidden px-4 py-3 text-left text-sm font-medium text-zinc-600 dark:text-zinc-400 lg:table-cell">
                            {t('models.columns.capabilities')}
                          </th>
                          <th className="px-4 py-3 text-right text-sm font-medium text-zinc-600 dark:text-zinc-400">
                            {t('models.columns.pricing')}
                          </th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-zinc-200 dark:divide-zinc-700">
                        {groupedModels[provider].map((model) => (
                          <tr
                            key={model.id}
                            onClick={() => setSelectedModel(model)}
                            className="cursor-pointer bg-white hover:bg-zinc-50 dark:bg-zinc-900 dark:hover:bg-zinc-800"
                          >
                            <td className="px-4 py-3">
                              <div className="font-medium text-zinc-900 dark:text-white">
                                {model.name}
                              </div>
                              <div className="text-xs text-zinc-500 dark:text-zinc-500">
                                {model.id}
                              </div>
                              {model.id === 'gemini-2.5-pro' && (
                                <div className="mt-1 text-xs text-amber-600 dark:text-amber-400">
                                  {t('models.contentPolicyWarning')}
                                </div>
                              )}
                              {model.parameter_constraints?.temperature && !model.parameter_constraints.temperature.supported && (
                                <div className="mt-1 text-xs text-amber-600 dark:text-amber-400">
                                  Temp: fixed at {model.parameter_constraints.temperature.required_value}
                                </div>
                              )}
                              {model.parameter_constraints?.temperature?.min != null && model.parameter_constraints.temperature.supported && model.parameter_constraints.temperature.min > 0 && (
                                <div className="mt-1 text-xs text-amber-600 dark:text-amber-400">
                                  Temp: min {model.parameter_constraints.temperature.min}
                                </div>
                              )}
                            </td>
                            <td className="hidden px-4 py-3 md:table-cell">
                              <div className="max-w-xs text-sm text-zinc-600 dark:text-zinc-400">
                                {model.description || '-'}
                              </div>
                            </td>
                            <td className="hidden px-4 py-3 lg:table-cell">
                              <div className="flex flex-wrap gap-1">
                                {model.capabilities.slice(0, 3).map((cap) => (
                                  <span
                                    key={cap}
                                    className="inline-flex rounded-full bg-zinc-100 px-2 py-0.5 text-xs text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400"
                                  >
                                    {cap}
                                  </span>
                                ))}
                                {model.capabilities.length > 3 && (
                                  <span className="inline-flex rounded-full bg-zinc-100 px-2 py-0.5 text-xs text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400">
                                    +{model.capabilities.length - 3}
                                  </span>
                                )}
                              </div>
                            </td>
                            <td className="px-4 py-3 text-right">
                              {model.input_cost_per_million != null &&
                              model.output_cost_per_million != null ? (
                                <div className="text-sm">
                                  <div className="text-zinc-900 dark:text-white">
                                    ${model.input_cost_per_million.toFixed(2)} / $
                                    {model.output_cost_per_million.toFixed(2)}
                                  </div>
                                  <div className="text-xs text-zinc-500 dark:text-zinc-500">
                                    {t('models.input')} / {t('models.output')}
                                  </div>
                                </div>
                              ) : (
                                <span className="text-sm text-zinc-400">-</span>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              ))
            )}
          </div>
        )}
      </div>

      {/* Model Settings Modal */}
      {selectedModel && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
          onClick={() => setSelectedModel(null)}
        >
          <div
            className="max-h-[80vh] w-full max-w-2xl overflow-hidden rounded-lg bg-white shadow-xl dark:bg-zinc-900"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-zinc-200 px-6 py-4 dark:border-zinc-700">
              <div>
                <h3 className="text-lg font-semibold text-zinc-900 dark:text-white">
                  {selectedModel.name}
                </h3>
                <p className="text-sm text-zinc-500 dark:text-zinc-400">{selectedModel.id}</p>
              </div>
              <button
                onClick={() => setSelectedModel(null)}
                className="rounded-lg p-2 text-zinc-500 hover:bg-zinc-100 hover:text-zinc-700 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-zinc-200"
              >
                <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M6 18L18 6M6 6l12 12"
                  />
                </svg>
              </button>
            </div>
            <div className="max-h-[60vh] overflow-auto p-6">
              <pre className="overflow-x-auto rounded-lg bg-zinc-100 p-4 text-sm text-zinc-800 dark:bg-zinc-800 dark:text-zinc-200">
                {JSON.stringify(getModelSettings(selectedModel), null, 2)}
              </pre>
            </div>
            <div className="flex justify-end border-t border-zinc-200 px-6 py-4 dark:border-zinc-700">
              <button
                onClick={() => {
                  navigator.clipboard.writeText(
                    JSON.stringify(getModelSettings(selectedModel), null, 2)
                  )
                }}
                className="mr-3 rounded-lg border border-zinc-300 px-4 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-50 dark:border-zinc-600 dark:text-zinc-300 dark:hover:bg-zinc-800"
              >
                {t('models.copyJson')}
              </button>
              <button
                onClick={() => setSelectedModel(null)}
                className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
              >
                {t('models.close')}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}

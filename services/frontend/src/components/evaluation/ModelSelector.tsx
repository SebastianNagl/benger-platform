/**
 * Model Selector Component
 *
 * Multi-select dropdown for selecting LLM models to compare in evaluations.
 * Fetches available models from the available-models API (filtered by API key
 * availability) and displays them with colorblind-safe provider badges.
 */

'use client'

import { Button } from '@/components/shared/Button'
import { Card } from '@/components/shared/Card'
import { Checkbox } from '@/components/shared/Checkbox'
import { SearchInput } from '@/components/shared/SearchInput'
import { useI18n } from '@/contexts/I18nContext'
import { api } from '@/lib/api'
import { ChevronDownIcon, ChevronUpIcon, ExclamationTriangleIcon } from '@heroicons/react/24/outline'
import { useCallback, useEffect, useState } from 'react'

interface AvailableModel {
  id: string
  name: string
  description: string
  provider: string
  model_type: string
  capabilities: string[]
  is_active: boolean
}

interface ModelSelectorProps {
  projectId?: string
  selectedModels: string[]
  onSelectionChange: (modelIds: string[]) => void
  maxSelections?: number
}

// Okabe-Ito colorblind-safe palette
const OKABE_ITO = {
  orange: '#E69F00',
  skyBlue: '#56B4E9',
  green: '#009E73',
  yellow: '#F0E442',
  blue: '#0072B2',
  vermillion: '#D55E00',
  purple: '#CC79A7',
  gray: '#999999',
}

// Map providers to colorblind-safe colors
const PROVIDER_COLORS: Record<string, string> = {
  OpenAI: OKABE_ITO.green,
  Anthropic: OKABE_ITO.orange,
  Google: OKABE_ITO.blue,
  Meta: OKABE_ITO.purple,
  Mistral: OKABE_ITO.skyBlue,
  DeepInfra: OKABE_ITO.vermillion,
  Grok: OKABE_ITO.gray,
  Cohere: OKABE_ITO.purple,
}

function getProviderColor(provider: string): string {
  return PROVIDER_COLORS[provider] || OKABE_ITO.gray
}

export function ModelSelector({
  projectId,
  selectedModels,
  onSelectionChange,
  maxSelections = 5,
}: ModelSelectorProps) {
  const { t } = useI18n()
  const [models, setModels] = useState<AvailableModel[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [isOpen, setIsOpen] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')

  const fetchModels = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await api.getAvailableModels()
      setModels(data)
    } catch (err) {
      console.error('Failed to fetch models:', err)
      setError(t('evaluation.modelSelector.failedToLoad'))
    } finally {
      setLoading(false)
    }
  }, [t])

  useEffect(() => {
    fetchModels()
  }, [fetchModels])

  const filteredModels = models.filter((model) =>
    model.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    model.id.toLowerCase().includes(searchQuery.toLowerCase())
  )

  const handleToggleModel = (modelId: string) => {
    if (selectedModels.includes(modelId)) {
      onSelectionChange(selectedModels.filter((id) => id !== modelId))
    } else {
      if (selectedModels.length >= maxSelections) {
        return
      }
      onSelectionChange([...selectedModels, modelId])
    }
  }

  const handleSelectAll = () => {
    const allModelIds = filteredModels
      .slice(0, maxSelections)
      .map((m) => m.id)
    onSelectionChange(allModelIds)
  }

  const handleClear = () => {
    onSelectionChange([])
  }

  if (loading) {
    return (
      <Card className="p-4">
        <div className="flex items-center justify-center py-8 text-sm text-gray-600">
          {t('evaluation.modelSelector.loading')}
        </div>
      </Card>
    )
  }

  if (error) {
    return (
      <Card className="p-4">
        <div className="flex items-center justify-center py-8 text-sm text-red-600">
          {error}
        </div>
      </Card>
    )
  }

  if (models.length === 0) {
    return (
      <Card className="p-4">
        <div className="flex items-center space-x-2 py-8">
          <ExclamationTriangleIcon className="h-5 w-5 text-amber-500" />
          <p className="text-sm text-amber-700 dark:text-amber-400">
            {t('evaluation.modelSelector.noModelsAvailable', 'No models available. Configure API keys in your profile settings.')}
          </p>
        </div>
      </Card>
    )
  }

  const selectedCount = selectedModels.length
  const canSelectMore = selectedCount < maxSelections

  return (
    <Card className="overflow-hidden">
      <div
        className="flex cursor-pointer items-center justify-between p-4 hover:bg-gray-50 dark:hover:bg-gray-800"
        onClick={() => setIsOpen(!isOpen)}
      >
        <div>
          <h4 className="font-medium text-gray-900 dark:text-gray-100">
            {t('evaluation.modelSelector.modelSelection')}
          </h4>
          <span className="text-sm text-gray-500 dark:text-gray-400">
            {t('evaluation.modelSelector.selectedCount', { selected: selectedCount, max: maxSelections })}
          </span>
        </div>
        {isOpen ? (
          <ChevronUpIcon className="h-5 w-5 text-gray-400" />
        ) : (
          <ChevronDownIcon className="h-5 w-5 text-gray-400" />
        )}
      </div>

      {isOpen && (
        <div className="border-t border-gray-200 p-4 dark:border-gray-700">
          <div className="mb-4 flex items-center gap-2">
            <SearchInput
              value={searchQuery}
              onChange={setSearchQuery}
              placeholder={t('evaluation.modelSelector.searchPlaceholder')}
              className="flex-1"
            />
            <Button
              variant="outline"
              onClick={handleSelectAll}
              disabled={!canSelectMore && selectedCount === 0}
              className="text-sm"
            >
              {t('evaluation.modelSelector.selectAll')}
            </Button>
            <Button
              variant="outline"
              onClick={handleClear}
              disabled={selectedCount === 0}
              className="text-sm"
            >
              {t('evaluation.modelSelector.clear')}
            </Button>
          </div>

          {!canSelectMore && (
            <div className="mb-4 rounded-md bg-yellow-50 p-3 dark:bg-yellow-900/20">
              <p className="text-sm text-yellow-800 dark:text-yellow-200">
                {t('evaluation.modelSelector.maxSelectionWarning', { max: maxSelections })}
              </p>
            </div>
          )}

          <div className="max-h-96 space-y-2 overflow-y-auto">
            {filteredModels.length === 0 ? (
              <div className="py-8 text-center text-sm text-gray-500">
                {searchQuery
                  ? t('evaluation.modelSelector.noSearchResults')
                  : t('evaluation.modelSelector.noModels')}
              </div>
            ) : (
              filteredModels.map((model) => {
                const isSelected = selectedModels.includes(model.id)
                const isDisabled = !isSelected && !canSelectMore

                return (
                  <label
                    key={model.id}
                    className={`flex items-center space-x-3 rounded-lg border border-gray-200 p-3 transition-colors dark:border-gray-700 ${
                      isDisabled
                        ? 'cursor-not-allowed opacity-50'
                        : 'cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800'
                    }`}
                  >
                    <Checkbox
                      checked={isSelected}
                      onChange={() => handleToggleModel(model.id)}
                      disabled={isDisabled}
                    />
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-gray-900 dark:text-gray-100">
                          {model.name}
                        </span>
                        <span
                          className="inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium"
                          style={{
                            borderColor: getProviderColor(model.provider),
                            color: getProviderColor(model.provider),
                          }}
                        >
                          {model.provider}
                        </span>
                      </div>
                      <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                        {model.description}
                      </p>
                    </div>
                  </label>
                )
              })
            )}
          </div>
        </div>
      )}
    </Card>
  )
}

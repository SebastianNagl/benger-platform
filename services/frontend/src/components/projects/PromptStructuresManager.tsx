/**
 * Prompt Structures Manager Component
 *
 * Manages multiple prompt structures for LLM generation tasks.
 * Issue #762: Support for multiple prompt structures per project
 */

'use client'

import { GenerationStructureEditor } from '@/components/projects/GenerationStructureEditor'
import { TaskFieldReferencePanel } from '@/components/shared/TaskFieldReferencePanel'
import { Button } from '@/components/shared/Button'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { useI18n } from '@/contexts/I18nContext'
import { apiClient } from '@/lib/api/client'
import { logger } from '@/lib/utils/logger'
import {
  PencilIcon,
  PlusIcon,
  TrashIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline'
import { useCallback, useEffect, useState } from 'react'

interface PromptStructure {
  key: string
  name: string
  description?: string
  system_prompt: string | object
  instruction_prompt: string | object
  evaluation_prompt?: string | object | null
}

interface PromptStructuresManagerProps {
  projectId: string
  onStructuresChange?: () => void
}

export function PromptStructuresManager({
  projectId,
  onStructuresChange,
}: PromptStructuresManagerProps) {
  const { t } = useI18n()
  const [structures, setStructures] = useState<Record<string, PromptStructure>>(
    {}
  )
  const [activeStructures, setActiveStructures] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [expanded, setExpanded] = useState(false)

  // Modal state
  const [showModal, setShowModal] = useState(false)
  const [editingKey, setEditingKey] = useState<string | null>(null)
  const [modalData, setModalData] = useState<{
    key: string
    name: string
    description: string
    config: string
  }>({
    key: '',
    name: '',
    description: '',
    config: '',
  })
  const [modalError, setModalError] = useState<string | null>(null)

  // Delete confirmation
  const [deletingKey, setDeletingKey] = useState<string | null>(null)

  const fetchStructures = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      // Fetch structures
      const structuresData = await apiClient.get(
        `/projects/${projectId}/generation-config/structures`
      )
      setStructures(structuresData || {})

      // Fetch active structures from project
      const project = await apiClient.getProject(projectId)
      const activeKeys =
        project?.generation_config?.selected_configuration?.active_structures ||
        []
      setActiveStructures(activeKeys)
    } catch (err) {
      console.error('Failed to fetch prompt structures:', err)
      setError(t('projects.promptStructures.loadFailed'))
      setStructures({})
      setActiveStructures([])
    } finally {
      setLoading(false)
    }
  }, [projectId])

  // Fetch structures on mount
  useEffect(() => {
    fetchStructures()
  }, [fetchStructures])

  const handleToggleActive = async (key: string) => {
    const newActiveStructures = activeStructures.includes(key)
      ? activeStructures.filter((k) => k !== key)
      : [...activeStructures, key]

    setActiveStructures(newActiveStructures)

    try {
      await apiClient.put(
        `/projects/${projectId}/generation-config/structures`,
        newActiveStructures
      )
      if (onStructuresChange) {
        onStructuresChange()
      }
    } catch (err) {
      console.error('Failed to update active structures:', err)
      setError(t('projects.promptStructures.updateFailed'))
      // Revert on error
      setActiveStructures(activeStructures)
    }
  }

  const openAddModal = () => {
    setEditingKey(null)
    setModalData({
      key: '',
      name: '',
      description: '',
      config: '',
    })
    setModalError(null)
    setShowModal(true)
  }

  const openEditModal = (key: string, structure: PromptStructure) => {
    setEditingKey(key)
    setModalData({
      key,
      name: structure.name,
      description: structure.description || '',
      config: JSON.stringify(
        {
          system_prompt: structure.system_prompt,
          instruction_prompt: structure.instruction_prompt,
          evaluation_prompt: structure.evaluation_prompt,
        },
        null,
        2
      ),
    })
    setModalError(null)
    setShowModal(true)
  }

  const validateStructureKey = (key: string): string | null => {
    if (!key || key.length < 1 || key.length > 50) {
      return t('projects.promptStructures.keyLengthError')
    }
    if (!/^[a-zA-Z0-9_-]+$/.test(key)) {
      return t('projects.promptStructures.keyCharacterError')
    }
    if (!editingKey && structures[key]) {
      return t('projects.promptStructures.keyExistsError')
    }
    return null
  }

  const handleSaveModal = async () => {
    logger.debug('handleSaveModal called')
    logger.debug('modalData:', modalData)
    setModalError(null)

    // Validate inputs
    if (!modalData.name.trim()) {
      logger.debug('Validation failed: Name is required')
      setModalError(t('projects.promptStructures.nameRequired'))
      return
    }

    if (!editingKey) {
      const keyError = validateStructureKey(modalData.key)
      if (keyError) {
        logger.debug('Validation failed: Key error:', keyError)
        setModalError(keyError)
        return
      }
    }

    if (!modalData.config.trim()) {
      logger.debug('Validation failed: Config is required')
      setModalError(t('projects.promptStructures.configRequired'))
      return
    }

    // Parse and validate config
    let parsedConfig: any
    try {
      parsedConfig = JSON.parse(modalData.config)
    } catch (err) {
      logger.debug('Validation failed: Invalid JSON')
      setModalError(t('projects.promptStructures.invalidJson'))
      return
    }

    if (!parsedConfig.system_prompt && !parsedConfig.instruction_prompt) {
      logger.debug('Validation failed: No prompts defined')
      setModalError(
        t('projects.promptStructures.missingPrompts')
      )
      return
    }

    logger.debug('Validation passed, saving...')
    setSaving(true)
    try {
      const key = editingKey || modalData.key
      const structureData = {
        name: modalData.name,
        description: modalData.description || undefined,
        system_prompt: parsedConfig.system_prompt,
        instruction_prompt: parsedConfig.instruction_prompt,
        evaluation_prompt: parsedConfig.evaluation_prompt || null,
      }

      logger.debug('Calling API with:', key, structureData)
      await apiClient.put(
        `/projects/${projectId}/generation-config/structures/${key}`,
        structureData
      )

      // Refresh structures
      await fetchStructures()

      setShowModal(false)
      if (onStructuresChange) {
        onStructuresChange()
      }
      logger.debug('Save successful')
    } catch (err: any) {
      console.error('Failed to save structure:', err)
      setModalError(err?.detail || err?.message || t('projects.promptStructures.saveFailed'))
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (key: string) => {
    setSaving(true)
    try {
      await apiClient.delete(
        `/projects/${projectId}/generation-config/structures/${key}`
      )

      // Refresh structures
      await fetchStructures()

      setDeletingKey(null)
      if (onStructuresChange) {
        onStructuresChange()
      }
    } catch (err) {
      console.error('Failed to delete structure:', err)
      setError(t('projects.promptStructures.deleteFailed'))
    } finally {
      setSaving(false)
    }
  }

  // Extract field references from a structure
  const extractFieldReferences = (structure: PromptStructure): string[] => {
    const refs: string[] = []

    const extract = (value: any) => {
      if (typeof value === 'string' && value.startsWith('$')) {
        refs.push(value.substring(1))
      } else if (typeof value === 'object' && value !== null) {
        Object.values(value).forEach(extract)
      }
    }

    extract(structure.system_prompt)
    extract(structure.instruction_prompt)
    if (structure.evaluation_prompt) {
      extract(structure.evaluation_prompt)
    }

    return [...new Set(refs)] // Remove duplicates
  }

  const structureKeys = Object.keys(structures)
  const activeCount = activeStructures.length
  const totalCount = structureKeys.length

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <div className="text-sm text-zinc-600 dark:text-zinc-400">
          {t('project.promptStructures.loadingStructures')}
        </div>
      </div>
    )
  }

  return (
    <>
      {/* Header - matches other collapsible sections */}
      <div className="mb-6 flex items-center justify-between">
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex items-center space-x-3 text-left"
        >
          <h2 className="text-lg font-semibold text-zinc-900 dark:text-white">
            {t('project.promptStructures.title')}
          </h2>
          {!expanded && (
            <span className="rounded-md bg-zinc-100 px-2 py-1 text-sm leading-tight text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400">
              {totalCount === 0
                ? t('project.promptStructures.notConfigured')
                : t('project.promptStructures.activeStatus', {
                    active: activeCount,
                    total: totalCount,
                  })}
            </span>
          )}
          <svg
            className={`h-5 w-5 flex-shrink-0 text-zinc-400 transition-transform ${expanded ? 'rotate-90 transform' : ''}`}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M9 5l7 7-7 7"
            />
          </svg>
        </button>
        {expanded && (
          <Button onClick={openAddModal} variant="outline" className="text-sm">
            <PlusIcon className="mr-2 h-4 w-4" />
            {t('project.promptStructures.addStructure')}
          </Button>
        )}
      </div>

      {/* Expanded content */}
      {expanded && (
        <>
          {error && (
            <Alert variant="destructive">
              <XMarkIcon className="h-4 w-4" />
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          {totalCount === 0 ? (
            <div className="py-8 text-center">
              <p className="mb-4 text-zinc-600 dark:text-zinc-400">
                {t('project.promptStructures.noStructuresYet')}
              </p>
              <Button onClick={openAddModal} variant="outline">
                <PlusIcon className="mr-2 h-4 w-4" />
                {t('project.promptStructures.createFirstStructure')}
              </Button>
            </div>
          ) : (
            <div className="space-y-3">
              {structureKeys.map((key) => {
                const structure = structures[key]
                const isActive = activeStructures.includes(key)
                const fieldRefs = extractFieldReferences(structure)

                return (
                  <Card key={key} className="overflow-hidden">
                    <div className="flex items-start justify-between p-4 hover:bg-zinc-50 dark:hover:bg-zinc-800/50">
                      <div className="flex min-w-0 flex-1 items-start space-x-3">
                        <input
                          type="checkbox"
                          checked={isActive}
                          onChange={() => handleToggleActive(key)}
                          className="mt-0.5 h-4 w-4 flex-shrink-0 rounded border-zinc-300 bg-white text-emerald-600 focus:ring-emerald-500 dark:border-zinc-600 dark:bg-zinc-700"
                          title={isActive ? t('projects.promptStructures.activeTooltip') : t('projects.promptStructures.inactiveTooltip')}
                        />
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2">
                            <h4 className="font-medium text-zinc-900 dark:text-white">
                              {structure.name}
                            </h4>
                            <span className="inline-flex items-center rounded-md bg-zinc-100 px-2 py-0.5 text-xs text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400">
                              {key}
                            </span>
                            {isActive && (
                              <span className="inline-flex items-center rounded-md bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400">
                                {t('project.promptStructures.active')}
                              </span>
                            )}
                          </div>
                          {structure.description && (
                            <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
                              {structure.description}
                            </p>
                          )}
                          {fieldRefs.length > 0 && (
                            <div className="mt-2">
                              <p className="mb-1 text-xs text-zinc-500 dark:text-zinc-500">
                                {t('project.promptStructures.referencesFields')}
                              </p>
                              <div className="flex flex-wrap gap-1">
                                {fieldRefs.map((field, i) => (
                                  <span
                                    key={i}
                                    className="rounded-md bg-zinc-100 px-2 py-0.5 text-xs text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300"
                                  >
                                    {field}
                                  </span>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      </div>
                      <div className="flex flex-shrink-0 items-start gap-2">
                        <button
                          onClick={() => openEditModal(key, structure)}
                          className="flex h-9 w-9 items-center justify-center rounded-md border border-zinc-300 bg-white text-zinc-700 transition-colors hover:bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-700"
                          title={t('projects.promptStructures.editTooltip')}
                        >
                          <PencilIcon className="h-4 w-4" />
                        </button>
                        <button
                          onClick={() => setDeletingKey(key)}
                          className="flex h-9 w-9 items-center justify-center rounded-md border border-red-300 bg-white text-red-600 transition-colors hover:bg-red-50 dark:border-red-800 dark:bg-zinc-800 dark:text-red-400 dark:hover:bg-red-950"
                          title={t('projects.promptStructures.deleteTooltip')}
                        >
                          <TrashIcon className="h-4 w-4" />
                        </button>
                      </div>
                    </div>
                  </Card>
                )
              })}
            </div>
          )}
        </>
      )}

      {/* Add/Edit Modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50 p-4">
          <div className="max-h-[90vh] w-full max-w-4xl overflow-y-auto rounded-lg bg-white p-6 shadow-xl dark:bg-zinc-900">
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-lg font-semibold text-zinc-900 dark:text-white">
                {editingKey
                  ? t('project.promptStructures.editPromptStructure')
                  : t('project.promptStructures.addPromptStructure')}
              </h3>
              <Button
                onClick={() => setShowModal(false)}
                variant="outline"
                className="text-sm"
              >
                <XMarkIcon className="h-4 w-4" />
              </Button>
            </div>

            <div className="space-y-4">
              {/* Key input (only for new structures) */}
              {!editingKey && (
                <div>
                  <Label htmlFor="structure-key">
                    {t('project.promptStructures.structureKey')}
                  </Label>
                  <Input
                    id="structure-key"
                    value={modalData.key}
                    onChange={(e) =>
                      setModalData({ ...modalData, key: e.target.value })
                    }
                    placeholder={t(
                      'project.promptStructures.structureKeyPlaceholder'
                    )}
                    className="mt-1"
                  />
                  <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                    {t('project.promptStructures.structureKeyHelp')}
                  </p>
                </div>
              )}

              {/* Name input */}
              <div>
                <Label htmlFor="structure-name">
                  {t('project.promptStructures.name')}
                </Label>
                <Input
                  id="structure-name"
                  value={modalData.name}
                  onChange={(e) =>
                    setModalData({ ...modalData, name: e.target.value })
                  }
                  placeholder={t('project.promptStructures.namePlaceholder')}
                  className="mt-1"
                />
              </div>

              {/* Description input */}
              <div>
                <Label htmlFor="structure-description">
                  {t('project.promptStructures.description')}
                </Label>
                <Textarea
                  id="structure-description"
                  value={modalData.description}
                  onChange={(e) =>
                    setModalData({ ...modalData, description: e.target.value })
                  }
                  placeholder={t(
                    'project.promptStructures.descriptionPlaceholder'
                  )}
                  rows={2}
                  className="mt-1"
                />
              </div>

              {/* Available task fields reference */}
              <TaskFieldReferencePanel
                projectId={projectId}
                defaultExpanded={false}
                description={t(
                  'project.promptStructures.fieldReferenceHelp',
                  'Use $fieldname or $nested.path syntax to reference task data fields in your prompts.'
                )}
              />

              {/* Structure configuration */}
              <div>
                <Label htmlFor="structure-config">
                  {t('project.promptStructures.structureConfiguration')}
                </Label>
                <p className="mb-2 text-xs text-zinc-500 dark:text-zinc-400">
                  {t('project.promptStructures.structureConfigHelp')}
                </p>
                <GenerationStructureEditor
                  initialConfig={modalData.config}
                  onChange={(config) => {
                    logger.debug(
                      'Editor onChange called with config length:',
                      config.length
                    )
                    setModalData({ ...modalData, config })
                  }}
                  onSave={(config) => {
                    logger.debug('Editor onSave called with config:', config)
                    setModalData({ ...modalData, config })
                  }}
                  onCancel={() => {
                    // Just update the internal state without closing modal
                  }}
                  showActionButtons={false}
                />
              </div>

              {modalError && (
                <Alert variant="destructive">
                  <XMarkIcon className="h-4 w-4" />
                  <AlertDescription>{modalError}</AlertDescription>
                </Alert>
              )}

              <div className="flex justify-end space-x-3 border-t border-zinc-200 pt-4 dark:border-zinc-700">
                <Button
                  onClick={() => {
                    logger.debug('Cancel button clicked')
                    setShowModal(false)
                  }}
                  variant="outline"
                  disabled={saving}
                >
                  {t('project.promptStructures.cancel')}
                </Button>
                <Button
                  onClick={() => {
                    logger.debug('Create Structure button clicked')
                    handleSaveModal()
                  }}
                  disabled={saving}
                >
                  {saving
                    ? t('project.promptStructures.saving')
                    : editingKey
                      ? t('project.promptStructures.updateStructure')
                      : t('project.promptStructures.createStructure')}
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {deletingKey && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50 p-4">
          <div className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl dark:bg-zinc-900">
            <h3 className="mb-4 text-lg font-semibold text-zinc-900 dark:text-white">
              {t('project.promptStructures.deletePromptStructure')}
            </h3>
            <p className="mb-6 text-zinc-600 dark:text-zinc-400">
              {t('project.promptStructures.deleteConfirmMessage', {
                name: structures[deletingKey]?.name,
              })}
            </p>
            <div className="flex justify-end space-x-3">
              <Button
                variant="outline"
                onClick={() => setDeletingKey(null)}
                disabled={saving}
              >
                {t('project.promptStructures.cancel')}
              </Button>
              <Button
                onClick={() => handleDelete(deletingKey)}
                className="bg-red-600 text-white hover:bg-red-700"
                disabled={saving}
              >
                {saving
                  ? t('project.promptStructures.deleting')
                  : t('project.promptStructures.delete')}
              </Button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}

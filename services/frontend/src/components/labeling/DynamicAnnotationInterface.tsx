/**
 * DynamicAnnotationInterface Component
 *
 * Renders annotation interface dynamically based on label configuration
 */

import { Alert } from '@/components/shared/Alert'
import { AutoSaveIndicator } from '@/components/shared/AutoSaveIndicator'
import { useAutoSave } from '@/hooks/useAutoSave'
import { logger } from '@/lib/utils/logger'
import { Skeleton } from '@/components/shared/Skeleton'
import { useI18n } from '@/contexts/I18nContext'
import {
  AnnotationResult,
  resolvePropsDataBindings,
  validateTaskDataFields,
} from '@/lib/labelConfig/dataBinding'
import {
  extractRequiredDataFields,
  ParsedComponent,
  parseLabelConfig,
  validateParsedConfig,
} from '@/lib/labelConfig/parser'
import { getComponent } from '@/lib/labelConfig/registry'
import { LegalMarkdownProvider } from './annotations/LegalMarkdownContext'
import React, {
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'

interface DynamicAnnotationInterfaceProps {
  labelConfig: string
  taskData: Record<string, any>
  initialValues?: AnnotationResult[]
  onSubmit: (annotations: AnnotationResult[]) => void
  onSkip?: () => void
  onChange?: (annotations: AnnotationResult[]) => void // Notify parent of changes
  taskId?: string | number // Add taskId to properly track task changes
  showSubmitButton?: boolean // Control submit button visibility (defaults to true)
  requireConfirmBeforeSubmit?: boolean // Require confirmation checkbox before submit
  startTime?: number // Start time for lead_time tracking (defaults to now)
  enableAutoSave?: boolean // Enable auto-save functionality (defaults to true)
  readOnly?: boolean // When true, components display content but disable editing
}

export function DynamicAnnotationInterface({
  labelConfig,
  taskData,
  initialValues,
  onSubmit,
  onSkip,
  onChange,
  taskId,
  showSubmitButton = true, // Default to true for backwards compatibility
  requireConfirmBeforeSubmit = false,
  startTime,
  enableAutoSave = true,
  readOnly = false,
}: DynamicAnnotationInterfaceProps) {
  const { t } = useI18n()

  // Track start time for lead_time calculation - use lazy initializer to avoid calling Date.now() on every render
  const [initialStartTime] = useState(() => startTime || Date.now())
  const startTimeRef = useRef(initialStartTime)

  const [annotations, setAnnotations] = useState<Map<string, AnnotationResult>>(
    () => {
      const map = new Map()
      if (initialValues) {
        initialValues.forEach((annotation) => {
          map.set(annotation.from_name, annotation)
        })
      }
      return map
    }
  )
  const [componentValues, setComponentValues] = useState<Map<string, any>>(
    () => {
      const map = new Map()
      if (initialValues) {
        initialValues.forEach((annotation) => {
          // Extract the actual value based on annotation type
          let value = annotation.value
          if (
            annotation.type === 'textarea' &&
            typeof value === 'object' &&
            value?.text
          ) {
            value = Array.isArray(value.text)
              ? value.text.join(' ')
              : value.text
          }
          // Handle Gliederung/Loesung types - extract markdown string from object
          else if (
            (annotation.type === 'gliederung' || annotation.type === 'loesung') &&
            typeof value === 'object' &&
            value?.markdown
          ) {
            value = value.markdown
          }
          // Handle complex annotation types - pass through the full value object
          else if (
            annotation.type === 'angabe' &&
            typeof value === 'object'
          ) {
            // Keep the full value as-is for complex input components
          }
          map.set(annotation.from_name, value)
        })
      }
      return map
    }
  )
  const [submissionErrors, setSubmissionErrors] = useState<string[]>([])
  const [confirmedDone, setConfirmedDone] = useState(false)
  const previousTaskId = useRef(taskId)

  // Auto-save functionality
  const autoSave = useAutoSave(
    taskId?.toString() || null,
    annotations,
    componentValues,
    initialStartTime, // Use the stable initial value instead of ref.current
    { enabled: enableAutoSave }
  )

  // Load draft from localStorage on mount (Issue #1110 - restore drafts after page refresh)
  useEffect(() => {
    const draft = autoSave.loadDraft()
    if (draft && draft.componentValues && Object.keys(draft.componentValues).length > 0) {
      // Restore componentValues from draft
      const valuesMap = new Map<string, any>()
      Object.entries(draft.componentValues).forEach(([key, value]) => {
        valuesMap.set(key, value)
      })
      setComponentValues(valuesMap)

      // Also restore annotations if available
      if (draft.annotations && draft.annotations.length > 0) {
        const annotationsMap = new Map<string, AnnotationResult>()
        draft.annotations.forEach((annotation) => {
          annotationsMap.set(annotation.from_name, annotation)
        })
        setAnnotations(annotationsMap)
      }
      logger.debug('Restored form from localStorage draft:', Object.keys(draft.componentValues).length, 'fields')
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- Only run on mount
  }, [])

  // Reset start time when task changes
  useEffect(() => {
    if (previousTaskId.current !== taskId && previousTaskId.current !== undefined) {
      startTimeRef.current = Date.now()
    }
  }, [taskId])

  // Clear form state when task changes (Fix for Issue #413: Form data persistence)
  useEffect(() => {
    // Only clear if taskId actually changed (not on initial mount)
    if (
      previousTaskId.current !== taskId &&
      previousTaskId.current !== undefined
    ) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- Clearing form on task change is valid state reset
      setAnnotations(new Map())

      setComponentValues(new Map())

      setSubmissionErrors([])
      setConfirmedDone(false)
    }
    previousTaskId.current = taskId
  }, [taskId]) // Use taskId for more reliable task change detection

  // Populate form with initialValues when they change (Issue #1082 - Draft persistence)
  useEffect(() => {
    if (initialValues && initialValues.length > 0) {
      // Populate annotations map
      const annotationsMap = new Map<string, AnnotationResult>()
      initialValues.forEach((annotation) => {
        annotationsMap.set(annotation.from_name, annotation)
      })
      setAnnotations(annotationsMap)

      // Populate componentValues map
      const valuesMap = new Map<string, any>()
      initialValues.forEach((annotation) => {
        let value = annotation.value
        // Extract text from textarea type
        if (
          annotation.type === 'textarea' &&
          typeof value === 'object' &&
          value?.text
        ) {
          value = Array.isArray(value.text)
            ? value.text.join(' ')
            : value.text
        }
        // Handle Gliederung/Loesung types
        else if (
          (annotation.type === 'gliederung' || annotation.type === 'loesung') &&
          typeof value === 'object' &&
          value?.markdown
        ) {
          value = value.markdown
        }
        // Handle complex annotation types - pass through full value
        else if (
          annotation.type === 'angabe' &&
          typeof value === 'object'
        ) {
          // Keep the full value as-is for complex input components
        }
        valuesMap.set(annotation.from_name, value)
      })
      setComponentValues(valuesMap)
      logger.debug('Populated form with initial values:', initialValues.length, 'annotations')
    }
  }, [initialValues])

  // Parse label configuration - returns config and errors together
  const { parsedConfig, configErrors } = useMemo(() => {
    const parsed = parseLabelConfig(labelConfig)

    if ('message' in parsed) {
      return { parsedConfig: null, configErrors: [parsed.message] }
    }

    // Validate configuration
    const validation = validateParsedConfig(parsed)
    if (!validation.valid) {
      return { parsedConfig: null, configErrors: validation.errors }
    }

    // Validate required data fields (only those marked with required="true")
    const requiredFields = extractRequiredDataFields(parsed)
    if (requiredFields.length > 0) {
      const dataValidation = validateTaskDataFields(requiredFields, taskData)
      if (!dataValidation.valid) {
        return {
          parsedConfig: null,
          configErrors: [
            t('annotation.interface.missingFields', {
              fields: dataValidation.missingFields.join(', '),
            }),
          ],
        }
      }
    }

    return { parsedConfig: parsed, configErrors: [] }
  }, [labelConfig, taskData, t])

  // Handle component value change
  const handleComponentChange = (componentName: string, value: any) => {
    logger.debug('handleComponentChange called:', componentName, value)
    setComponentValues((prev) => {
      const updated = new Map(prev)
      updated.set(componentName, value)
      logger.debug('Updated componentValues size:', updated.size)
      return updated
    })
  }

  // Notify parent when component values change (outside render cycle to avoid setState-during-render)
  useEffect(() => {
    if (onChange && componentValues.size > 0) {
      // Merge: prefer properly formatted annotations (from blur) over raw componentValues
      const results = Array.from(componentValues.entries()).map(([name, val]) => {
        const existingAnnotation = annotations.get(name)
        if (existingAnnotation) {
          return existingAnnotation
        }
        return {
          from_name: name,
          to_name: 'text',
          type: 'textarea' as const,
          value: val,
        }
      })
      onChange(results)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [componentValues])

  // Notify parent when annotations change (outside render cycle to avoid setState-during-render)
  useEffect(() => {
    if (onChange) {
      onChange(Array.from(annotations.values()))
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [annotations])

  // Handle annotation from component
  const handleAnnotation = (result: AnnotationResult) => {
    logger.debug('handleAnnotation called:', result)
    setAnnotations((prev) => {
      const updated = new Map(prev)
      updated.set(result.from_name, result)
      logger.debug('Updated annotations size:', updated.size)
      return updated
    })
  }

  // Wrapper for saveNow that passes field info directly to avoid race conditions
  const handleSaveToDb = useCallback(async (fieldName: string, value: unknown): Promise<void> => {
    await autoSave.saveNow({ fieldName, value })
  }, [autoSave])

  // Simplified validation to prevent recursion issues
  const validateAnnotations = (
    annotationResults: AnnotationResult[]
  ): string[] => {
    const validationErrors: string[] = []

    if (annotationResults.length === 0) {
      validationErrors.push(t('annotation.interface.atLeastOne'))
      return validationErrors
    }

    // Basic validation only - check if values exist
    for (const annotation of annotationResults) {
      const fieldName = annotation.from_name || 'Unknown field'

      if (
        annotation.value === null ||
        annotation.value === undefined ||
        annotation.value === ''
      ) {
        validationErrors.push(
          t('annotation.interface.fieldRequired', { fieldName })
        )
      }
    }

    return validationErrors
  }

  // Handle submit - simplified to prevent stack overflow
  const handleSubmit = useCallback(async () => {
    try {
      const annotationResults = Array.from(annotations.values())

      logger.debug('handleSubmit called, annotations:', annotationResults.length)

      // If we have annotations, use them
      let finalResults = annotationResults

      // If no annotations but we have component values, build from those
      if (annotationResults.length === 0 && componentValues.size > 0) {
        logger.debug('Building from component values:', componentValues.size)
        finalResults = Array.from(componentValues.entries()).map(
          ([name, value]) => ({
            from_name: name,
            to_name: 'text',
            type: 'textarea',
            value: value,
          })
        )
      }

      // Basic validation
      if (finalResults.length === 0) {
        setSubmissionErrors([t('annotation.interface.atLeastOne')])
        return
      }

      logger.debug('Submitting', finalResults.length, 'annotations')
      setSubmissionErrors([])
      await onSubmit(finalResults)

      // Clear the state after successful submission
      setAnnotations(new Map())
      setComponentValues(new Map())

      // Clear draft after successful submission
      if (enableAutoSave) {
        autoSave.clearDraft()
      }
    } catch (error) {
      console.error('Error in handleSubmit:', error)
      setSubmissionErrors([t('annotation.interface.submissionError')])
    }
  }, [annotations, componentValues, onSubmit, t, enableAutoSave, autoSave])

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Submit on Ctrl/Cmd + Enter (blocked if confirmation required but not checked)
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        if (requireConfirmBeforeSubmit && !confirmedDone) return
        e.preventDefault()
        handleSubmit()
      }
      // Skip on Ctrl/Cmd+Escape (blocked if confirmation required but not checked)
      else if ((e.ctrlKey || e.metaKey) && e.key === 'Escape' && onSkip) {
        if (requireConfirmBeforeSubmit && !confirmedDone) return
        e.preventDefault()
        onSkip()
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [handleSubmit, onSkip, requireConfirmBeforeSubmit, confirmedDone])

  // Render component tree recursively
  const renderComponent = (
    config: ParsedComponent,
    key: string = '0'
  ): React.ReactNode => {
    const component = getComponent(config.type)

    if (!component) {
      // Label and Choice are child elements of Labels/Choices in Label Studio XML,
      // not standalone components - silently skip them
      if (config.type !== 'Label' && config.type !== 'Choice') {
        console.warn(`Unknown component type: ${config.type}`)
      }
      return null
    }

    const Component = component.component
    const componentName =
      config.props.name || config.name || `${config.type}_${key}`
    const value = componentValues.get(componentName)

    // Resolve data bindings in props
    const resolvedProps = resolvePropsDataBindings(config.props, taskData)

    // Render component with children
    const children = config.children.map((child, index) =>
      renderComponent(child, `${key}_${index}`)
    )

    return (
      <Suspense key={key} fallback={<Skeleton className="h-20 w-full" />}>
        <Component
          config={{ ...config, props: resolvedProps }}
          taskData={taskData}
          value={value}
          onChange={readOnly ? () => {} : (val) => handleComponentChange(componentName, val)}
          onAnnotation={readOnly ? () => {} : handleAnnotation}
          hideSubmitButton={showSubmitButton} // Hide individual submit buttons when main button is shown (Issue #251, #1030)
          onSaveToDb={enableAutoSave && !readOnly ? handleSaveToDb : undefined} // Pass immediate save handler for Ctrl+S
          readOnly={readOnly}
        />
        {/* Render children separately for container components */}
        {component.category === 'visual' && children.length > 0 && (
          <>{children}</>
        )}
      </Suspense>
    )
  }

  // Check if config contains Gliederung, Loesung, or Angabe fields
  // NOTE: This must be BEFORE any early returns to avoid hooks rule violation
  const hasLegalFields = useMemo(() => {
    if (!parsedConfig) return false
    const checkForLegalFields = (component: ParsedComponent): boolean => {
      if (component.type === 'Gliederung' || component.type === 'Loesung' || component.type === 'Angabe') {
        return true
      }
      return component.children.some(checkForLegalFields)
    }
    return checkForLegalFields(parsedConfig)
  }, [parsedConfig])

  // Show configuration errors if any
  if (configErrors.length > 0) {
    return (
      <div className="space-y-4">
        <Alert variant="error">
          <div>
            <p className="font-semibold">
              {t('annotation.interface.configError')}
            </p>
            <ul className="mt-2 list-inside list-disc">
              {configErrors.map((error, index) => (
                <li key={index}>{error}</li>
              ))}
            </ul>
          </div>
        </Alert>

        {/* Fallback to showing raw data */}
        <div className="rounded-lg bg-zinc-100 p-4 dark:bg-zinc-800">
          <h3 className="mb-2 font-medium">
            {t('annotation.interface.taskData')}
          </h3>
          <pre className="overflow-x-auto text-sm">
            {JSON.stringify(taskData, null, 2)}
          </pre>
        </div>
      </div>
    )
  }

  // Render dynamic interface
  const interfaceContent = (
    <div className="dynamic-annotation-interface space-y-6">
      {/* Render parsed configuration */}
      {parsedConfig && renderComponent(parsedConfig)}

      {/* Show submission errors if any */}
      {submissionErrors.length > 0 && (
        <Alert variant="error">
          <ul className="list-inside list-disc">
            {submissionErrors.map((error, index) => (
              <li key={index}>{error}</li>
            ))}
          </ul>
        </Alert>
      )}

      {/* Action buttons */}
      <div className="border-t pt-6">
        {requireConfirmBeforeSubmit && (
          <div className="mb-4 border-b border-zinc-200 pb-4 dark:border-zinc-700">
            <label className="flex items-center gap-2 text-sm text-zinc-700 dark:text-zinc-300">
              <input
                type="checkbox"
                checked={confirmedDone}
                onChange={(e) => setConfirmedDone(e.target.checked)}
                className="h-4 w-4 rounded border-zinc-300 text-emerald-600 focus:ring-emerald-500 dark:border-zinc-600"
              />
              {t('annotation.interface.confirmDone', { defaultValue: 'I confirm that I have read the annotation instructions and am ready to submit' })}
            </label>
          </div>
        )}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            {onSkip && (
              <button
                type="button"
                onClick={onSkip}
                disabled={requireConfirmBeforeSubmit && !confirmedDone}
                className="rounded-md border border-zinc-300 bg-white px-4 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-700"
              >
                {t('annotation.interface.skip')}{' '}
                <span className="ml-2 text-xs opacity-60">
                  {t('annotation.interface.skipShortcut')}
                </span>
              </button>
            )}

            {/* Auto-save indicator */}
            {enableAutoSave && (
              <AutoSaveIndicator
                isSaving={autoSave.isSaving}
                lastSaved={autoSave.lastSaved}
                error={autoSave.error}
              />
            )}
          </div>

          {showSubmitButton && (
            <div className="ml-auto flex items-center gap-4">
              <button
                type="button"
                onClick={handleSubmit}
                disabled={(annotations.size === 0 && componentValues.size === 0) || (requireConfirmBeforeSubmit && !confirmedDone)}
                className="rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {t('annotation.interface.submit')}{' '}
                <span className="ml-2 text-xs opacity-90">
                  {t('annotation.interface.submitShortcut')}
                </span>
              </button>
            </div>
          )}
        </div>
        <div className="mt-2 text-center text-xs text-zinc-500 dark:text-zinc-400">
          {t('annotation.interface.tip')}
        </div>
      </div>
    </div>
  )

  // Wrap with LegalMarkdownProvider if Gliederung/Loesung fields are present
  if (hasLegalFields) {
    return <LegalMarkdownProvider>{interfaceContent}</LegalMarkdownProvider>
  }

  return interfaceContent
}

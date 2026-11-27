/**
 * DynamicAnnotationInterface Component
 *
 * Renders annotation interface dynamically based on label configuration
 */

import { Alert } from '@/components/shared/Alert'
import { AutoSaveIndicator } from '@/components/shared/AutoSaveIndicator'
import { Skeleton } from '@/components/shared/Skeleton'
import { useI18n } from '@/contexts/I18nContext'
import { useAutoSave } from '@/hooks/useAutoSave'
import { useModernExamLayout } from '@/hooks/useModernExamLayout'
import {
  AnnotationResult,
  resolvePropsDataBindings,
  validateTaskDataFields,
} from '@/lib/labelConfig/dataBinding'
import type { HostExamChrome } from '@/lib/labelConfig/examLayout'
import {
  extractRequiredDataFields,
  ParsedComponent,
  parseLabelConfig,
  validateParsedConfig,
} from '@/lib/labelConfig/parser'
import { getComponent } from '@/lib/labelConfig/registry'
import { missingRequiredControls } from '@/lib/labelConfig/requiredControls'
import { logger } from '@/lib/utils/logger'
import React, {
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'

/**
 * Whether a window-level keyboard shortcut is meant for the editor rendered
 * at `root`. It is not when the key came from inside another annotation
 * interface (a questionnaire's form shown next to or over the task) or from
 * inside a dialog that is not part of this editor, nor while a modal dialog
 * that is not part of this editor is open, since the editor then sits behind
 * that dialog. A dialog is part of the editor when it holds the editor (a
 * questionnaire's own form) or the editor holds it (an exam layout's own
 * panels).
 */
function shortcutTargetsEditor(
  root: HTMLElement | null,
  target: EventTarget | null,
): boolean {
  if (!root) return false
  const partOfEditor = (dialog: Element) =>
    dialog.contains(root) || root.contains(dialog)
  if (target instanceof Element) {
    const editor = target.closest('[data-annotation-interface]')
    if (editor && editor !== root) return false
    const dialog = target.closest('[role="dialog"], [role="alertdialog"]')
    if (dialog && !partOfEditor(dialog)) return false
  }
  const modals = root.ownerDocument.querySelectorAll('[aria-modal="true"]')
  return Array.from(modals).every(partOfEditor)
}

interface DynamicAnnotationInterfaceProps {
  labelConfig: string
  taskData: Record<string, any>
  initialValues?: AnnotationResult[]
  // A host whose onSubmit rejects keeps the answers in the form and shows
  // its own error message.
  onSubmit: (annotations: AnnotationResult[]) => void | Promise<void>
  onSkip?: () => void
  onChange?: (annotations: AnnotationResult[]) => void // Notify parent of changes
  taskId?: string | number // Add taskId to properly track task changes
  showSubmitButton?: boolean // Control submit button visibility (defaults to true)
  // A host that submits through its own controls: no field submit buttons,
  // no Ctrl/Cmd+Enter submit, no shortcut tip and no empty action bar.
  hostOwnsSubmit?: boolean
  requireConfirmBeforeSubmit?: boolean // Require confirmation checkbox before submit
  startTime?: number // Start time for lead_time tracking (defaults to now)
  enableAutoSave?: boolean // Enable auto-save functionality (defaults to true)
  readOnly?: boolean // When true, components display content but disable editing
  // Block submit while a control marked required="true" is unanswered and
  // name the missing ones. The questionnaire modal opts in. The annotation
  // hosts do not: existing exam configs mark answer fields required that
  // submissions legitimately leave empty.
  enforceRequired?: boolean
  // Host opt-in for the modern exam layout (extended). Only the interactive
  // labeling hosts pass true; review surfaces stay classic by never opting in.
  // The layout additionally requires the user preference, the ModernExamLayout
  // slot, and an exam-shaped config — see useModernExamLayout.
  allowModernLayout?: boolean
  // Host chrome for a state-specific exam interface (prefs mode 'state'):
  // the slot renders the host's timer and leave action in its own bar, and
  // this component's action bar gives way to the slot's submit button.
  examChrome?: HostExamChrome
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
  hostOwnsSubmit = false,
  requireConfirmBeforeSubmit = false,
  startTime,
  enableAutoSave = true,
  readOnly = false,
  enforceRequired = false,
  allowModernLayout = false,
  examChrome,
}: DynamicAnnotationInterfaceProps) {
  const { t } = useI18n()

  // Modern exam layout (extended): when active, the registered slot arranges
  // WHERE the parsed nodes render (sheet + side panels) while this component
  // keeps sole ownership of annotation state, submit merging, autosave, and
  // the action bar. Inactive (community edition, classic preference, review
  // hosts, non-exam configs) -> the classic stacked render below, unchanged.
  const {
    active: modernLayoutActive,
    state: stateLayoutActive,
    prefs: examLayoutPrefs,
    Layout: ModernLayout,
  } = useModernExamLayout(labelConfig)
  const useModernRender =
    allowModernLayout && modernLayoutActive && !!ModernLayout
  const useStateRender = useModernRender && stateLayoutActive

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
    },
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
          map.set(annotation.from_name, value)
        })
      }
      return map
    },
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
    { enabled: enableAutoSave },
  )

  // Load draft from localStorage on mount (Issue #1110 - restore drafts after page refresh)
  // Skip when auto-save is disabled (e.g. review mode) — initialValues take precedence
  useEffect(() => {
    if (!enableAutoSave) return
    const draft = autoSave.loadDraft()
    if (
      draft &&
      draft.componentValues &&
      Object.keys(draft.componentValues).length > 0
    ) {
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
      logger.debug(
        'Restored form from localStorage draft:',
        Object.keys(draft.componentValues).length,
        'fields',
      )
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- Only run on mount
  }, [])

  // Reset start time when task changes
  useEffect(() => {
    if (
      previousTaskId.current !== taskId &&
      previousTaskId.current !== undefined
    ) {
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
          value = Array.isArray(value.text) ? value.text.join(' ') : value.text
        }
        valuesMap.set(annotation.from_name, value)
      })
      setComponentValues(valuesMap)
      logger.debug(
        'Populated form with initial values:',
        initialValues.length,
        'annotations',
      )
    }
  }, [initialValues])

  // Parse label configuration - returns config and errors together
  const { parsedConfig, configErrors } = useMemo(() => {
    // taskData expands every <Repeater> into the task's indexed controls
    const parsed = parseLabelConfig(labelConfig, taskData || {})

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

  // The form shows in one step: the code of every field type in the config
  // is loaded first (one placeholder meanwhile) instead of each field
  // swapping its own placeholder for itself as its code arrives, which
  // moved the form around several times on a first visit. Types without
  // `preload` (an overlay's own lazy components) still load on render.
  const fieldTypes = useMemo(() => {
    const types = new Set<string>()
    const walk = (node: ParsedComponent) => {
      types.add(node.type)
      node.children.forEach(walk)
    }
    if (parsedConfig) walk(parsedConfig)
    return [...types].sort()
  }, [parsedConfig])
  const fieldTypesKey = fieldTypes.join(',')
  const fieldsLoaded = fieldTypes.every(
    (type) => getComponent(type)?.isLoaded?.() ?? true,
  )
  const [preloadedTypes, setPreloadedTypes] = useState<string | null>(null)
  useEffect(() => {
    if (fieldsLoaded) return
    let cancelled = false
    Promise.allSettled(
      fieldTypes.map((type) => getComponent(type)?.preload?.()),
    ).then(() => {
      if (!cancelled) setPreloadedTypes(fieldTypesKey)
    })
    return () => {
      cancelled = true
    }
    // fieldTypesKey stands for fieldTypes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fieldTypesKey, fieldsLoaded])
  const fieldsReady = fieldsLoaded || preloadedTypes === fieldTypesKey

  // Handle component value change. Memoized (stable identity): annotation
  // components keep callbacks in effect dependency arrays, and a per-render
  // identity re-fires those effects after every state landing — with a
  // publish-on-effect component (Loesung/Gliederung) that becomes an infinite
  // publish → setState → new callback → publish loop.
  const handleComponentChange = useCallback(
    (componentName: string, value: any) => {
      logger.debug('handleComponentChange called:', componentName, value)
      setComponentValues((prev) => {
        const updated = new Map(prev)
        updated.set(componentName, value)
        logger.debug('Updated componentValues size:', updated.size)
        return updated
      })
    },
    [],
  )

  // Notify parent when component values change (outside render cycle to avoid setState-during-render)
  useEffect(() => {
    if (onChange && componentValues.size > 0) {
      // Merge: prefer properly formatted annotations (from blur) over raw componentValues
      const results = Array.from(componentValues.entries()).map(
        ([name, val]) => {
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
        },
      )
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

  // Handle annotation from component. Memoized for the same reason as
  // handleComponentChange above — this exact callback sat in the Loesung/
  // Gliederung publish-effect deps and looped the render cycle.
  const handleAnnotation = useCallback((result: AnnotationResult) => {
    logger.debug('handleAnnotation called:', result)
    setAnnotations((prev) => {
      const updated = new Map(prev)
      updated.set(result.from_name, result)
      logger.debug('Updated annotations size:', updated.size)
      return updated
    })
  }, [])

  // Wrapper for saveNow that passes field info directly to avoid race conditions
  const handleSaveToDb = useCallback(
    async (fieldName: string, value: unknown): Promise<void> => {
      await autoSave.saveNow({ fieldName, value })
    },
    [autoSave],
  )

  // Handle submit - simplified to prevent stack overflow
  const handleSubmit = useCallback(async () => {
    try {
      // Assemble the submit payload the SAME way the draft/onChange effect does
      // (see the componentValues effect above): for every field, prefer its
      // properly-shaped annotation but fall back to the live componentValue.
      //
      // Reading only `annotations` here was a submission-truncation bug: content
      // still sitting in the live componentValues (because a field's annotation
      // flush was outstanding) was dropped, so the submitted result could be
      // staler and shorter than the autosaved draft. Merging both sources
      // guarantees submit and draft can never diverge. (The extended editors now
      // also flush synchronously, so `annotations` is normally already current;
      // this merge is the belt-and-suspenders backstop.)
      const mergedResults = new Map<string, AnnotationResult>()
      componentValues.forEach((value, name) => {
        const existingAnnotation = annotations.get(name)
        mergedResults.set(
          name,
          existingAnnotation ?? {
            from_name: name,
            to_name: 'text',
            type: 'textarea',
            value,
          },
        )
      })
      // Include any annotation-only fields that never emitted a componentValue.
      annotations.forEach((annotation, name) => {
        if (!mergedResults.has(name)) {
          mergedResults.set(name, annotation)
        }
      })

      const finalResults = Array.from(mergedResults.values())

      logger.debug('handleSubmit called, merged results:', finalResults.length)

      // Basic validation
      if (finalResults.length === 0) {
        setSubmissionErrors([t('annotation.interface.atLeastOne')])
        return
      }

      if (enforceRequired && parsedConfig) {
        const missing = missingRequiredControls(parsedConfig, finalResults)
        if (missing.length > 0) {
          setSubmissionErrors([
            t('annotation.interface.requiredMissing', {
              fields: missing.map((control) => control.label).join(', '),
            }),
          ])
          return
        }
      }

      logger.debug('Submitting', finalResults.length, 'annotations')
      setSubmissionErrors([])
      try {
        await onSubmit(finalResults)
      } catch {
        return
      }

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
  }, [
    annotations,
    componentValues,
    onSubmit,
    t,
    enableAutoSave,
    autoSave,
    enforceRequired,
    parsedConfig,
  ])

  // Keyboard shortcuts. They listen on the window, so each one first checks
  // that the key is meant for this editor and not for a questionnaire or
  // another dialog on the same page.
  const rootRef = useRef<HTMLDivElement>(null)
  const submitShortcut = !hostOwnsSubmit && !readOnly
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!(e.ctrlKey || e.metaKey)) return
      if (!shortcutTargetsEditor(rootRef.current, e.target)) return
      // Submit on Ctrl/Cmd + Enter (blocked if confirmation required but not
      // checked), unless the host submits through its own controls or the
      // editor is read-only.
      if (e.key === 'Enter' && submitShortcut) {
        if (requireConfirmBeforeSubmit && !confirmedDone) return
        e.preventDefault()
        handleSubmit()
      }
      // Skip on Ctrl/Cmd+Escape (blocked if confirmation required but not checked)
      else if (e.key === 'Escape' && onSkip) {
        if (requireConfirmBeforeSubmit && !confirmedDone) return
        e.preventDefault()
        onSkip()
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [
    handleSubmit,
    onSkip,
    requireConfirmBeforeSubmit,
    confirmedDone,
    submitShortcut,
  ])

  // Render component tree recursively
  const renderComponent = (
    config: ParsedComponent,
    key: string = '0',
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
      renderComponent(child, `${key}_${index}`),
    )

    return (
      <Suspense key={key} fallback={<Skeleton className="h-20 w-full" />}>
        <Component
          config={{ ...config, props: resolvedProps }}
          taskData={taskData}
          taskId={taskId?.toString()}
          value={value}
          onChange={
            readOnly
              ? () => {}
              : (val) => handleComponentChange(componentName, val)
          }
          onAnnotation={readOnly ? () => {} : handleAnnotation}
          hideSubmitButton={showSubmitButton || hostOwnsSubmit} // Hide individual submit buttons when main button is shown (Issue #251, #1030) or the host submits
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
    <div
      ref={rootRef}
      className="dynamic-annotation-interface space-y-6"
      data-annotation-interface=""
    >
      {/* Exam tools (extended ExamToolDock slot via the host). The modern
          and state layouts render them themselves (renderTools 'modern' /
          'state' via chrome), so only the classic render shows them here. */}
      {!useModernRender && examChrome?.renderTools?.('default')}
      {/* Render parsed configuration. Modern exam layout: the slot arranges
          the SAME nodes (via renderComponent, which closes over the live
          state and memoized handlers) into sheet + side panels. It must call
          renderComponent for every field node exactly once — including
          fields the user placed 'none' (they stay mounted and render null so
          drafts, context registration, and heading sync keep working). */}
      {parsedConfig && !fieldsReady && (
        <div data-testid="annotation-fields-loading">
          <Skeleton className="h-20 w-full" />
        </div>
      )}
      {parsedConfig &&
        fieldsReady &&
        (useModernRender && ModernLayout ? (
          <Suspense fallback={<Skeleton className="h-96 w-full" />}>
            <ModernLayout
              parsedConfig={parsedConfig}
              renderComponent={renderComponent}
              prefs={examLayoutPrefs}
              readOnly={readOnly}
              taskId={taskId?.toString()}
              chrome={
                useStateRender
                  ? {
                      ...examChrome,
                      onSubmit: showSubmitButton ? handleSubmit : undefined,
                      canSubmit:
                        annotations.size > 0 || componentValues.size > 0,
                      requireConfirmBeforeSubmit,
                    }
                  : examChrome?.renderTools
                    ? { renderTools: examChrome.renderTools }
                    : undefined
              }
            />
          </Suspense>
        ) : (
          renderComponent(parsedConfig)
        ))}

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

      {/* Action buttons. A state-specific interface carries its own submit
          (chrome.onSubmit) in its bar, so the bar here is omitted. A host
          that submits, skips and saves on its own, or a read-only view
          without skip, leaves the bar empty, so it is omitted too. */}
      {!useStateRender &&
        (submitShortcut ||
          showSubmitButton ||
          onSkip ||
          enableAutoSave ||
          requireConfirmBeforeSubmit) && (
          <div className="border-t pt-6" data-testid="annotation-action-bar">
            {requireConfirmBeforeSubmit && (
              <div className="mb-4 border-b border-zinc-200 pb-4 dark:border-zinc-700">
                <label className="flex items-center gap-2 text-sm text-zinc-700 dark:text-zinc-300">
                  <input
                    type="checkbox"
                    checked={confirmedDone}
                    onChange={(e) => setConfirmedDone(e.target.checked)}
                    className="h-4 w-4 rounded border-zinc-300 text-emerald-600 focus:ring-emerald-500 dark:border-zinc-600"
                  />
                  {t('annotation.interface.confirmDone')}
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
                    className="h-8 rounded-full border border-zinc-300 bg-white px-4 text-sm font-medium text-zinc-700 hover:bg-zinc-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-700"
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
                    disabled={
                      (annotations.size === 0 && componentValues.size === 0) ||
                      (requireConfirmBeforeSubmit && !confirmedDone)
                    }
                    className="h-8 rounded-full bg-zinc-900 px-4 text-sm font-medium text-white hover:bg-zinc-700 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-emerald-500 dark:hover:bg-emerald-400"
                  >
                    {t('annotation.interface.submit')}{' '}
                    <span className="ml-2 text-xs opacity-90">
                      {t('annotation.interface.submitShortcut')}
                    </span>
                  </button>
                </div>
              )}
            </div>
            {/* The tip advertises the submit and skip shortcuts, so only show
              it while one of them does something. */}
            {(submitShortcut || onSkip) && (
              <div className="mt-2 text-center text-xs text-zinc-500 dark:text-zinc-400">
                {t('annotation.interface.tip')}
              </div>
            )}
          </div>
        )}
    </div>
  )

  return interfaceContent
}

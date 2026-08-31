/**
 * ProjectCreationWizard - Dynamic multi-step project creation
 *
 * Step 1 (Project Info) includes feature checkboxes that control which
 * subsequent steps appear. All data is collected locally, then the project
 * is created with all configuration in a single batch at the end.
 */

'use client'

import { Button } from '@/components/shared/Button'
import { Card } from '@/components/shared/Card'
import { useI18n } from '@/contexts/I18nContext'
import { apiClient } from '@/lib/api/client'
import { projectsAPI } from '@/lib/api/projects'
import { getRegisteredWizardTemplates, getWizardKindPreset, getWizardPostCreateHooks } from '@/lib/extensions'
import { useSlot } from '@/lib/extensions/slots'
import { defaultIconForKind } from '@/lib/projectKind'
import { getWizardFinishContributors } from '@/lib/extensions/wizardFinish'
import { extractFieldsFromLabelConfig } from '@/lib/labelConfig/fieldExtractor'
import {
  buildImportFile,
  detectFormat,
  parseImportData,
} from '@/lib/import/parseImportData'
import { useProjectStore } from '@/stores/projectStore'
import { ArrowLeftIcon, ArrowRightIcon } from '@heroicons/react/24/outline'
import { useRouter } from 'next/navigation'
import { useCallback, useMemo, useRef, useState } from 'react'
import { useToast } from '@/components/shared/Toast'
import { StepAnnotationInstructions } from './wizard/StepAnnotationInstructions'
import { StepDataImport } from './wizard/StepDataImport'
import { StepEvaluationMethods } from './wizard/StepEvaluationMethods'
import { StepLabelingSetup } from './wizard/StepLabelingSetup'
import { StepModels } from './wizard/StepModels'
import { StepProjectInfo } from './wizard/StepProjectInfo'
import { StepPrompts } from './wizard/StepPrompts'
import { StepSettings } from './wizard/StepSettings'
import {
  INITIAL_WIZARD_DATA,
  LabelingTemplate,
  WizardData,
  WizardStepDef,
} from './wizard/types'
import { WizardStepIndicator } from './wizard/WizardStepIndicator'

export function ProjectCreationWizard() {
  const router = useRouter()
  const { t } = useI18n()
  const { addToast } = useToast()
  const { createProject, fetchProject, loading } = useProjectStore()

  const [wizardData, setWizardData] = useState<WizardData>(INITIAL_WIZARD_DATA)
  const [currentStepIndex, setCurrentStepIndex] = useState(0)
  const [errors, setErrors] = useState<Record<string, string>>({})
  // Re-entrancy guard for the final "Create Project" action. The global store
  // `loading` flag only covers the createProject/fetchProject calls and flips
  // back to false mid-flight (during import + the settings PATCH/PUTs), which
  // would otherwise re-enable the button and let a second click create a
  // duplicate project. The ref blocks re-entry synchronously (state updates are
  // async); the state drives the disabled UI.
  const isFinishingRef = useRef(false)
  const [isFinishing, setIsFinishing] = useState(false)

  const nlpTemplates: LabelingTemplate[] = useMemo(
    () => [
      {
        id: 'question-answering',
        name: t('projects.creation.wizard.templates.questionAnswering.name'),
        description: t(
          'projects.creation.wizard.templates.questionAnswering.description'
        ),
        icon: '\u2753',
        category: 'NLP',
        config: `<View>
  <Text name="context" value="$context"/>
  <Text name="question" value="$question"/>
  <TextArea name="answer" toName="context"
            placeholder="Enter your answer..."
            rows="3" maxSubmissions="1"/>
</View>`,
      },
      {
        id: 'multiple-choice',
        name: t('projects.creation.wizard.templates.multipleChoice.name'),
        description: t(
          'projects.creation.wizard.templates.multipleChoice.description'
        ),
        icon: '\uD83D\uDD18',
        category: 'NLP',
        config: `<View>
  <Text name="question" value="$question"/>
  <Text name="context" value="$context"/>
  <Choices name="answer" toName="question" choice="single" showInline="true">
    <Choice value="A"/>
    <Choice value="B"/>
    <Choice value="C"/>
    <Choice value="D"/>
  </Choices>
  <TextArea name="reasoning" toName="question"
            placeholder="Explain your reasoning..."
            rows="2" required="false"/>
</View>`,
      },
      {
        id: 'span-annotation',
        name: t('projects.creation.wizard.templates.spanAnnotation.name'),
        description: t(
          'projects.creation.wizard.templates.spanAnnotation.description'
        ),
        icon: '\uD83C\uDFF7\uFE0F',
        category: 'NLP',
        config: `<View>
  <Text name="text" value="$text"/>
  <Labels name="label" toName="text">
    <Label value="Person" background="#FF6B6B"/>
    <Label value="Organization" background="#4ECDC4"/>
    <Label value="Location" background="#45B7D1"/>
    <Label value="Legal_Term" background="#F7B731"/>
    <Label value="Law_Reference" background="#5F27CD"/>
  </Labels>
</View>`,
      },
      {
        id: 'custom',
        name: t('projects.creation.wizard.templates.custom.name'),
        description: t('projects.creation.wizard.templates.custom.description'),
        icon: '\u2699\uFE0F',
        category: 'Custom',
        config: `<View>
  <!-- Define your custom annotation interface -->
  <Text name="text" value="$text"/>
  <!-- Add your components here -->
</View>`,
      },
      ...getRegisteredWizardTemplates().map((r) => ({
        ...r,
        name: t(r.nameKey),
        description: t(r.descriptionKey),
      })),
    ],
    [t]
  )

  // Extended-edition step body for the experimental KI-Generator feature
  // (checkbox row = ProjectWizardSyntheticEntry slot in StepProjectInfo).
  const SyntheticStep = useSlot('ProjectWizardSyntheticStep')
  // Extended-edition step body for the experimental AI-Bewertungsbogen
  // (checkbox row = ProjectWizardRubricEntry slot in StepProjectInfo). The
  // generated per-task rubrics become a SECOND evaluation method
  // (llm_judge_rubric) next to the configured judges.
  const RubricStep = useSlot('ProjectWizardRubricStep')

  // Build dynamic step list from features
  const activeSteps: WizardStepDef[] = useMemo(() => {
    const steps: WizardStepDef[] = [
      {
        id: 'projectInfo',
        name: t('projects.creation.wizard.steps.projectInfo.name'),
        description: t(
          'projects.creation.wizard.steps.projectInfo.description'
        ),
      },
    ]

    if (wizardData.features.synthetic) {
      steps.push({
        id: 'synthetic',
        name: t('projects.creation.wizard.steps.synthetic.name'),
        description: t(
          'projects.creation.wizard.steps.synthetic.description'
        ),
      })
    }

    if (wizardData.features.dataImport) {
      steps.push({
        id: 'dataImport',
        name: t('projects.creation.wizard.steps.dataImport.name'),
        description: t(
          'projects.creation.wizard.steps.dataImport.description'
        ),
      })
    }

    if (wizardData.features.annotation) {
      steps.push(
        {
          id: 'labelingSetup',
          name: t('projects.creation.wizard.steps.labelingSetup.name'),
          description: t(
            'projects.creation.wizard.steps.labelingSetup.description'
          ),
        },
        {
          id: 'annotationInstructions',
          name: t(
            'projects.creation.wizard.steps.annotationInstructions.name'
          ),
          description: t(
            'projects.creation.wizard.steps.annotationInstructions.description'
          ),
        }
      )
    }

    if (wizardData.features.llmGeneration) {
      steps.push(
        {
          id: 'models',
          name: t('projects.creation.wizard.steps.models.name'),
          description: t(
            'projects.creation.wizard.steps.models.description'
          ),
        },
        {
          id: 'prompts',
          name: t('projects.creation.wizard.steps.prompts.name'),
          description: t(
            'projects.creation.wizard.steps.prompts.description'
          ),
        }
      )
    }

    if (wizardData.features.evaluation) {
      steps.push({
        id: 'evaluation',
        name: t('projects.creation.wizard.steps.evaluation.name'),
        description: t(
          'projects.creation.wizard.steps.evaluation.description'
        ),
      })
    }

    // AI-Bewertungsbogen sits after evaluation: by then the tasks
    // (dataImport/synthetic) and the judge configs are declared, and the
    // post-create hook runs after the awaited import so generation sees the
    // tasks. Extended-only (the step body slot registers nothing in
    // community builds — the entry row can then never enable it either).
    if (wizardData.features.rubric) {
      steps.push({
        id: 'rubric',
        name: t('projects.creation.wizard.steps.rubric.name'),
        description: t(
          'projects.creation.wizard.steps.rubric.description'
        ),
      })
    }

    steps.push({
      id: 'settings',
      name: t('projects.creation.wizard.steps.settings.name'),
      description: t(
        'projects.creation.wizard.steps.settings.description'
      ),
    })

    return steps
  }, [wizardData.features, t])

  // Clamp step index when steps change (e.g., user unchecks a feature)
  const clampedStepIndex = Math.min(currentStepIndex, activeSteps.length - 1)
  if (clampedStepIndex !== currentStepIndex) {
    setCurrentStepIndex(clampedStepIndex)
  }

  const currentStep = activeSteps[currentStepIndex]
  const isLastStep = currentStepIndex === activeSteps.length - 1

  // Derive fields from earlier wizard steps for cross-step data flow
  const labelConfigFields = useMemo(
    // eslint-disable-next-line react-hooks/preserve-manual-memoization
    () =>
      wizardData.labelingConfig?.config
        ? extractFieldsFromLabelConfig(wizardData.labelingConfig.config)
        : { outputFields: [], inputFields: [] },
    [wizardData.labelingConfig?.config]
  )

  const availableVariables = useMemo(() => {
    const vars = new Set<string>()
    for (const f of labelConfigFields.inputFields) vars.add(f)
    for (const col of wizardData.dataColumns) vars.add(col)
    return Array.from(vars)
  }, [labelConfigFields.inputFields, wizardData.dataColumns])

  const updateWizardData = useCallback(
    (partial: Partial<WizardData>) => {
      setWizardData((prev) => {
        const next = { ...prev, ...partial }
        // Choosing a project type pre-selects the matching labeling template
        // (Klausurlösung / Karteikarten, registered by the extended edition)
        // and switches annotation on, so the project gets the shape the
        // student surfaces, discovery and the deck workspace recognise. The
        // user can still pick another template afterwards.
        if (partial.projectKind && partial.projectKind !== prev.projectKind) {
          const templateId =
            partial.projectKind === 'exam'
              ? 'exam-solving'
              : partial.projectKind === 'flashcard_collection'
                ? 'flashcard-deck'
                : null
          const template = templateId
            ? nlpTemplates.find((tpl) => tpl.id === templateId)
            : undefined
          // An update that carries its own labelingConfig (e.g. the
          // KI-Generator stamping type + its synthetic template together)
          // wins over the type's default template.
          if (template && !partial.labelingConfig) {
            next.labelingConfig = template
            next.features = { ...next.features, annotation: true }
          } else if (partial.labelingConfig) {
            next.features = { ...next.features, annotation: true }
          }
          // The icon follows the type default until the user picked their own.
          const prevDefault = defaultIconForKind(
            prev.projectKind === 'generic' ? null : prev.projectKind
          )
          if (!prev.icon || prev.icon === prevDefault) {
            next.icon = defaultIconForKind(
              partial.projectKind === 'generic' ? null : partial.projectKind
            )
          }
          // Extended kind preset: prefills judge pair / immediate eval /
          // exam settings so the project works on both surfaces.
          const preset = getWizardKindPreset(partial.projectKind)
          if (preset) {
            Object.assign(next, preset(next))
          }
        }
        // Reverse coupling: picking the Karteikarten template while the type
        // is still "Generisch" stamps the deck kind — kind is the single
        // source of truth for the student surfaces, so a deck-shaped project
        // must not be created kind-NULL by the template path. Guarded on the
        // template actually changing so re-renders can't loop.
        if (
          partial.labelingConfig &&
          partial.labelingConfig !== prev.labelingConfig &&
          partial.labelingConfig.id === 'flashcard-deck' &&
          next.projectKind === 'generic'
        ) {
          next.projectKind = 'flashcard_collection'
          const prevDefault = defaultIconForKind(null)
          if (!next.icon || next.icon === prevDefault) {
            next.icon = defaultIconForKind('flashcard_collection')
          }
        }
        return next
      })
    },
    [nlpTemplates]
  )

  const validateStep = (): boolean => {
    const newErrors: Record<string, string> = {}

    if (currentStep?.id === 'projectInfo') {
      if (!wizardData.title.trim()) {
        newErrors.title = t(
          'projects.creation.wizard.step1.validation.nameRequired'
        )
      }
      if (
        wizardData.visibility === 'organization' &&
        wizardData.organizationIds.length === 0
      ) {
        newErrors.organizationIds = t(
          'projects.creation.wizard.step1.validation.orgRequired',
          'Pick at least one organization, or change visibility.'
        )
      }
    }

    setErrors(newErrors)
    return Object.keys(newErrors).length === 0
  }

  const handleNext = () => {
    if (validateStep() && currentStepIndex < activeSteps.length - 1) {
      setCurrentStepIndex(currentStepIndex + 1)
    }
  }

  const handleBack = () => {
    if (currentStepIndex > 0) {
      setCurrentStepIndex(currentStepIndex - 1)
    }
  }

  const handleFinish = async () => {
    if (isFinishingRef.current) return
    if (!validateStep()) return

    isFinishingRef.current = true
    setIsFinishing(true)

    try {
      // 1. Create project with basic info + label config
      const defaultLabelConfig = `<View>
  <Text name="text" value="$text"/>
  <TextArea name="answer" toName="text"
            placeholder="Enter your answer..."
            rows="4" maxSubmissions="1"/>
</View>`

      const createData: {
        title: string
        description: string
        label_config: string
        is_private?: boolean
        is_public?: boolean
        public_role?: 'ANNOTATOR' | 'CONTRIBUTOR' | null
        kind?: string | null
        icon?: string | null
        organization_group_id?: string | null
      } = {
        title: wizardData.title.trim(),
        description: wizardData.description.trim(),
        label_config:
          wizardData.labelingConfig?.config || defaultLabelConfig,
        // Write-once project type; generic stays NULL so plain benchmark
        // projects are unaffected.
        kind: wizardData.projectKind === 'generic' ? null : wizardData.projectKind,
        icon: wizardData.icon.trim() || null,
      }
      if (wizardData.visibility === 'private') {
        createData.is_private = true
      } else if (wizardData.visibility === 'public') {
        createData.is_public = true
        createData.public_role = wizardData.publicRole
      } else if (wizardData.organizationIds.length === 1) {
        // Single-org creation flow: scope the context-created attachment to
        // the selected group right away (null = org-wide), so there is no
        // window where the whole org can see a group-scoped project.
        createData.organization_group_id =
          wizardData.organizationGroupIds[wizardData.organizationIds[0]] ?? null
      }
      // For 'organization' visibility, create_project honours
      // X-Organization-Context. We then explicitly PATCH the visibility with
      // the wizard-selected org ids so the result is independent of the
      // current subdomain context.

      const project = await createProject(createData)

      if (
        wizardData.visibility === 'organization' &&
        wizardData.organizationIds.length > 0
      ) {
        try {
          await projectsAPI.updateVisibility(project.id, {
            is_private: false,
            // Per-org group scope (null = the whole organization).
            organization_attachments: wizardData.organizationIds.map(
              (orgId) => ({
                organization_id: orgId,
                group_id: wizardData.organizationGroupIds[orgId] ?? null,
              })
            ),
          })
        } catch (err) {
           
          console.error('Failed to assign organizations after project create', err)
          addToast(
            t(
              'projects.creation.wizard.orgAssignFailed',
              'Project was created but could not be assigned to the selected organizations. Please assign them from the project settings.'
            ),
            'error'
          )
        }
      }

      // 2. Import data if provided (the synthetic step feeds generated rows
      // through pastedData, so it imports even without the dataImport step)
      if (
        (wizardData.features.dataImport || wizardData.features.synthetic) &&
        (wizardData.pastedData.trim() ||
          wizardData.selectedFile ||
          wizardData.cloudImport?.objectKeys?.length)
      ) {
        try {
          let rows: any[] = []
          let extras: Record<string, unknown> = {}

          if (wizardData.selectedFile) {
            const content = await new Promise<string>((resolve, reject) => {
              const reader = new FileReader()
              reader.onload = (e) => resolve(e.target?.result as string)
              reader.onerror = reject
              reader.readAsText(wizardData.selectedFile!)
            })
            const parsed = parseImportData(
              content,
              detectFormat(content, wizardData.selectedFile.name)
            )
            rows = parsed.rows
            extras = parsed.extras
          } else if (wizardData.pastedData.trim()) {
            const trimmed = wizardData.pastedData.trim()
            const parsed = parseImportData(trimmed, detectFormat(trimmed))
            rows = parsed.rows
            extras = parsed.extras
          }

          if (rows.length > 0) {
            // Async job flow (object storage is the only import path): serialize
            // the nested envelope to a JSON file, upload it via a presigned URL,
            // then let a worker stream-import it.
            const file = buildImportFile(rows, extras)
            await projectsAPI.runNestedImportJob(project.id, file)
          }

          // Cloud-storage selection: the workers pull the selected objects
          // straight from the org storage connection (one job per key).
          if (wizardData.cloudImport?.objectKeys?.length) {
            await projectsAPI.runCloudImportJobs(project.id, {
              connection_id: wizardData.cloudImport.connectionId,
              object_keys: wizardData.cloudImport.objectKeys,
            })
          }
        } catch (importError) {
          addToast(
            t('projects.wizard.importDataFailed', {
              error:
                importError instanceof Error
                  ? importError.message
                  : t('projects.wizard.unknownError'),
            }),
            'error'
          )
        }
      }

      // 3. Update project with instructions + generation config (single PATCH)
      const updatePayload: Record<string, any> = {}

      if (wizardData.features.annotation && wizardData.instructions.trim()) {
        updatePayload.instructions = wizardData.instructions.trim()
      }

      if (
        wizardData.features.annotation &&
        wizardData.conditionalInstructions.length > 0
      ) {
        updatePayload.conditional_instructions =
          wizardData.conditionalInstructions
      }

      if (wizardData.features.llmGeneration) {
        const gp = wizardData.generationParameters
        const selectedConfig: Record<string, any> = {
          parameters: {
            temperature: gp.temperature,
            max_tokens: gp.max_tokens,
            batch_size: gp.batch_size,
          },
          prompts: {
            system: wizardData.systemPrompt || undefined,
            instruction: wizardData.instructionPrompt || undefined,
          },
        }
        if (wizardData.selectedModelIds.length > 0) {
          selectedConfig.models = wizardData.selectedModelIds
          selectedConfig.model_configs = wizardData.modelConfigs
        }
        updatePayload.generation_config = {
          selected_configuration: selectedConfig,
        }
      }

      // Annotation display settings (from instructions step)
      if (wizardData.features.annotation) {
        updatePayload.show_instruction = wizardData.show_instruction
        updatePayload.instructions_always_visible = wizardData.instructions_always_visible
        updatePayload.show_skip_button = wizardData.show_skip_button
      }

      // Evaluation settings
      if (wizardData.features.evaluation) {
        updatePayload.immediate_evaluation_enabled = wizardData.immediate_evaluation_enabled
      }

      // Let extended packages contribute additional fields based on the
      // accumulated wizard state (e.g. korrektur_enabled derived from the
      // selected eval metrics). Contributors run in registration order.
      for (const contribute of getWizardFinishContributors()) {
        Object.assign(
          updatePayload,
          contribute({
            evaluationConfigs: wizardData.evaluationConfigs,
            features: {
              annotation: wizardData.features.annotation,
              // Wizard's internal name is llmGeneration; the contributor
              // contract uses the project-detail flag name `generation`.
              generation: wizardData.features.llmGeneration,
              evaluation: wizardData.features.evaluation,
            },
          }),
        )
      }

      // Always include settings
      const s = wizardData.settings
      updatePayload.assignment_mode = s.assignment_mode
      updatePayload.maximum_annotations = s.maximum_annotations
      updatePayload.min_annotations_per_task = s.min_annotations_per_task
      updatePayload.randomize_task_order = s.randomize_task_order
      updatePayload.require_confirm_before_submit = s.require_confirm_before_submit
      updatePayload.annotator_full_visibility_after_submit =
        s.annotator_full_visibility_after_submit
      updatePayload.annotation_time_limit_enabled = s.annotation_time_limit_enabled
      updatePayload.annotation_time_limit_seconds = s.annotation_time_limit_seconds
      updatePayload.strict_timer_enabled = s.strict_timer_enabled
      updatePayload.window_start_at = s.window_start_at
      updatePayload.window_end_at = s.window_end_at

      // Persist the wizard's feature checkboxes as project-level visibility
      // flags so the detail page knows which configuration cards to render.
      updatePayload.enable_annotation = wizardData.features.annotation
      updatePayload.enable_generation = wizardData.features.llmGeneration
      updatePayload.enable_evaluation = wizardData.features.evaluation

      if (Object.keys(updatePayload).length > 0) {
        await projectsAPI.update(project.id, updatePayload)
      }

      // 4. Save evaluation configs if any
      if (
        wizardData.features.evaluation &&
        wizardData.evaluationConfigs.length > 0
      ) {
        try {
          await apiClient.put(
            `/evaluations/projects/${project.id}/evaluation-config`,
            { evaluation_configs: wizardData.evaluationConfigs }
          )
        } catch (evalError) {
          addToast(t('projects.creation.wizard.evalSaveFailed'), 'error')
        }
      }

      // 5. Save prompt structure if both prompts are configured
      // Backend requires both system_prompt and instruction_prompt to be non-empty
      if (
        wizardData.features.llmGeneration &&
        wizardData.systemPrompt.trim() &&
        wizardData.instructionPrompt.trim()
      ) {
        try {
          await apiClient.put(
            `/projects/${project.id}/generation-config/structures/default`,
            {
              name: wizardData.promptTemplate !== 'custom'
                ? wizardData.promptTemplate
                : 'Default',
              system_prompt: wizardData.systemPrompt,
              instruction_prompt: wizardData.instructionPrompt,
            }
          )
          await apiClient.put(
            `/projects/${project.id}/generation-config/structures`,
            ['default']
          )
        } catch {
          // Non-critical — prompts are also saved in generation_config.selected_configuration
          addToast(
            t('projects.creation.wizard.promptStructureSaveFailed'),
            'error'
          )
        }
      }

      // 5. Extended post-create hooks (e.g. rubric generation). The project
      // exists at this point, so a failing hook only toasts.
      for (const hook of getWizardPostCreateHooks()) {
        try {
          await hook({ projectId: project.id, wizardData })
        } catch (hookError) {
          addToast(
            hookError instanceof Error
              ? hookError.message
              : t('projects.wizard.postCreateHookFailed', 'Nachbearbeitung fehlgeschlagen'),
            'error'
          )
        }
      }

      // 6. Refresh and redirect
      await new Promise((resolve) => setTimeout(resolve, 100))
      await fetchProject(project.id)
      addToast(t('projects.wizard.projectCreated'), 'success')
      router.push(`/projects/${project.id}`)
    } catch (error) {
      addToast(
        error instanceof Error
          ? error.message
          : t('projects.wizard.createFailed'),
        'error'
      )
      // Re-enable the button so the user can retry. On the success path we
      // navigate away (router.push) and the component unmounts, so the guard
      // intentionally stays set there to keep the button disabled.
      isFinishingRef.current = false
      setIsFinishing(false)
    }
  }

  const renderCurrentStep = () => {
    switch (currentStep?.id) {
      case 'projectInfo':
        return (
          <StepProjectInfo
            data={wizardData}
            onChange={updateWizardData}
            errors={errors}
          />
        )
      case 'synthetic':
        // Extended-only step; the feature checkbox exists only when the
        // entry slot is registered, so this can't be reached without the
        // step slot in practice. Null keeps the frame rendering regardless.
        // The step feeds generated rows back through the normal wizard state
        // (pastedData/dataColumns/labelingConfig), so finishing the wizard
        // imports them like hand-uploaded data.
        return SyntheticStep ? (
          // eslint-disable-next-line react-hooks/static-components
          <SyntheticStep data={wizardData} onChange={updateWizardData} />
        ) : null
      case 'labelingSetup':
        return (
          <StepLabelingSetup
            labelingConfig={wizardData.labelingConfig}
            onChange={(config) => updateWizardData({ labelingConfig: config })}
            nlpTemplates={nlpTemplates}
          />
        )
      case 'annotationInstructions':
        return (
          <StepAnnotationInstructions
            instructions={wizardData.instructions}
            conditionalInstructions={wizardData.conditionalInstructions}
            showInstruction={wizardData.show_instruction}
            instructionsAlwaysVisible={wizardData.instructions_always_visible}
            showSkipButton={wizardData.show_skip_button}
            onInstructionsChange={(instructions) =>
              updateWizardData({ instructions })
            }
            onConditionalInstructionsChange={(conditionalInstructions) =>
              updateWizardData({ conditionalInstructions })
            }
            onShowInstructionChange={(show_instruction) =>
              updateWizardData({ show_instruction })
            }
            onInstructionsAlwaysVisibleChange={(instructions_always_visible) =>
              updateWizardData({ instructions_always_visible })
            }
            onShowSkipButtonChange={(show_skip_button) =>
              updateWizardData({ show_skip_button })
            }
          />
        )
      case 'dataImport':
        return (
          <StepDataImport
            pastedData={wizardData.pastedData}
            selectedFile={wizardData.selectedFile}
            dataColumns={wizardData.dataColumns}
            onPastedDataChange={(pastedData) =>
              updateWizardData({ pastedData })
            }
            onFileChange={(selectedFile) =>
              updateWizardData({ selectedFile })
            }
            onDataColumnsChange={(dataColumns) =>
              updateWizardData({ dataColumns })
            }
            syntheticActive={wizardData.features.synthetic}
            syntheticColumns={wizardData.dataColumns}
            wizardData={wizardData}
            onWizardChange={updateWizardData}
          />
        )
      case 'models':
        return (
          <StepModels
            selectedModelIds={wizardData.selectedModelIds}
            modelConfigs={wizardData.modelConfigs}
            generationParameters={wizardData.generationParameters}
            onSelectedModelsChange={(selectedModelIds) =>
              updateWizardData({ selectedModelIds })
            }
            onModelConfigsChange={(modelConfigs) =>
              updateWizardData({ modelConfigs })
            }
            onGenerationParametersChange={(generationParameters) =>
              updateWizardData({ generationParameters })
            }
          />
        )
      case 'prompts':
        return (
          <StepPrompts
            promptTemplate={wizardData.promptTemplate}
            systemPrompt={wizardData.systemPrompt}
            instructionPrompt={wizardData.instructionPrompt}
            availableVariables={availableVariables}
            onPromptTemplateChange={(promptTemplate) =>
              updateWizardData({ promptTemplate })
            }
            onSystemPromptChange={(systemPrompt) =>
              updateWizardData({ systemPrompt })
            }
            onInstructionPromptChange={(instructionPrompt) =>
              updateWizardData({ instructionPrompt })
            }
          />
        )
      case 'evaluation':
        return (
          <StepEvaluationMethods
            evaluationConfigs={wizardData.evaluationConfigs}
            onEvaluationConfigsChange={(evaluationConfigs) =>
              updateWizardData({ evaluationConfigs })
            }
            immediateEvaluationEnabled={wizardData.immediate_evaluation_enabled}
            onImmediateEvaluationChange={(immediate_evaluation_enabled) =>
              updateWizardData({ immediate_evaluation_enabled })
            }
            annotationFields={labelConfigFields.outputFields}
            dataColumns={wizardData.dataColumns}
            selectedModelIds={wizardData.selectedModelIds}
          />
        )
      case 'rubric':
        // Extended-only step (mirrors 'synthetic'): the AI-Bewertungsbogen —
        // per-task rubric generation installed as a SECOND evaluation method
        // (llm_judge_rubric) by the post-create hook once tasks exist.
        return RubricStep ? (
          // eslint-disable-next-line react-hooks/static-components
          <RubricStep data={wizardData} onChange={updateWizardData} />
        ) : null
      case 'settings':
        return (
          <StepSettings
            settings={wizardData.settings}
            onSettingsChange={(settings) => updateWizardData({ settings })}
          />
        )
      default:
        return null
    }
  }

  return (
    <div
      className="mx-auto max-w-5xl"
      data-testid="project-create-step-indicator"
      data-step={currentStepIndex + 1}
      data-total-steps={activeSteps.length}
      data-current-step-id={currentStep?.id ?? ''}
    >
      <WizardStepIndicator
        steps={activeSteps}
        currentStepIndex={currentStepIndex}
        onStepClick={(index) => setCurrentStepIndex(index)}
      />

      <Card className="mb-8">
        <div className="p-8">{renderCurrentStep()}</div>
      </Card>

      {/* Navigation */}
      <div className="flex justify-between">
        <Button
          variant="outline"
          onClick={
            currentStepIndex === 0
              ? () => router.push('/projects')
              : handleBack
          }
          disabled={loading}
          data-testid={
            currentStepIndex === 0
              ? 'project-create-cancel-button'
              : 'project-create-back-button'
          }
        >
          <ArrowLeftIcon className="mr-2 h-4 w-4" />
          {currentStepIndex === 0
            ? t('projects.creation.wizard.navigation.cancel')
            : t('projects.creation.wizard.navigation.back')}
        </Button>

        <div className="flex gap-3">
          {isLastStep ? (
            <Button
              onClick={handleFinish}
              disabled={loading || isFinishing}
              data-testid="project-create-submit-button"
            >
              {loading || isFinishing
                ? t('projects.creation.wizard.navigation.creating')
                : t('projects.creation.wizard.navigation.create')}
            </Button>
          ) : (
            <Button
              onClick={handleNext}
              disabled={loading}
              data-testid="project-create-next-button"
            >
              {t('projects.creation.wizard.navigation.next')}
              <ArrowRightIcon className="ml-2 h-4 w-4" />
            </Button>
          )}
        </div>
      </div>
    </div>
  )
}

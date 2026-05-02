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
import { getRegisteredWizardTemplates } from '@/lib/extensions'
import { getWizardFinishContributors } from '@/lib/extensions/wizardFinish'
import { extractFieldsFromLabelConfig } from '@/lib/labelConfig/fieldExtractor'
import { useProjectStore } from '@/stores/projectStore'
import { ArrowLeftIcon, ArrowRightIcon } from '@heroicons/react/24/outline'
import { useRouter } from 'next/navigation'
import { useCallback, useMemo, useState } from 'react'
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
      setWizardData((prev) => ({ ...prev, ...partial }))
    },
    []
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

  const parseData = async (
    content: string,
    format: string
  ): Promise<{ data: any[]; extras: Record<string, unknown> }> => {
    try {
      if (format === 'json') {
        const parsed = JSON.parse(content)
        if (Array.isArray(parsed)) return { data: parsed, extras: {} }
        if (parsed.qa_samples && Array.isArray(parsed.qa_samples))
          return { data: parsed.qa_samples, extras: {} }
        if (parsed.questions && Array.isArray(parsed.questions))
          return {
            data: parsed.questions.map((q: any) => q.question_data || q),
            extras: {},
          }
        // Bulk-export envelope: extract tasks + forward auxiliary arrays so
        // judge scores, korrektur threads, etc. round-trip into the new project.
        if (Array.isArray(parsed.tasks)) {
          const extras: Record<string, unknown> = {}
          for (const k of [
            'evaluation_runs',
            'human_evaluation_configs',
            'human_evaluation_sessions',
            'human_evaluation_results',
            'preference_rankings',
            'likert_scale_evaluations',
            'korrektur_comments',
          ] as const) {
            if (Array.isArray(parsed[k])) extras[k] = parsed[k]
          }
          return { data: parsed.tasks, extras }
        }
        return { data: [parsed], extras: {} }
      } else if (format === 'csv' || format === 'tsv') {
        const delimiter = format === 'csv' ? ',' : '\t'
        const lines = content.trim().split('\n')
        if (lines.length === 0) return { data: [], extras: {} }
        const headers = lines[0]
          .split(delimiter)
          .map((h) => h.trim().replace(/^["']|["']$/g, ''))
        const data = lines.slice(1).map((line) => {
          const values = line
            .split(delimiter)
            .map((v) => v.trim().replace(/^["']|["']$/g, ''))
          const obj: any = {}
          headers.forEach((header, index) => {
            obj[header] = values[index] || ''
          })
          return obj
        })
        return { data, extras: {} }
      } else {
        const data = content
          .trim()
          .split('\n')
          .filter((line) => line.trim())
          .map((line) => ({ text: line.trim() }))
        return { data, extras: {} }
      }
    } catch (error) {
      throw new Error(`Failed to parse ${format.toUpperCase()} data: ${error}`)
    }
  }

  const handleFinish = async () => {
    if (!validateStep()) return

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
      } = {
        title: wizardData.title.trim(),
        description: wizardData.description.trim(),
        label_config:
          wizardData.labelingConfig?.config || defaultLabelConfig,
      }
      if (wizardData.visibility === 'private') {
        createData.is_private = true
      } else if (wizardData.visibility === 'public') {
        createData.is_public = true
        createData.public_role = wizardData.publicRole
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
            organization_ids: wizardData.organizationIds,
          })
        } catch (err) {
          // eslint-disable-next-line no-console
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

      // 2. Import data if provided
      if (
        wizardData.features.dataImport &&
        (wizardData.pastedData.trim() || wizardData.selectedFile)
      ) {
        try {
          let data: any[] = []
          let extras: Record<string, unknown> = {}

          if (wizardData.selectedFile) {
            const content = await new Promise<string>((resolve, reject) => {
              const reader = new FileReader()
              reader.onload = (e) => resolve(e.target?.result as string)
              reader.onerror = reject
              reader.readAsText(wizardData.selectedFile!)
            })
            const format =
              wizardData.selectedFile.name.split('.').pop()?.toLowerCase() ||
              'txt'
            const parsed = await parseData(content, format)
            data = parsed.data
            extras = parsed.extras
          } else if (wizardData.pastedData.trim()) {
            const trimmed = wizardData.pastedData.trim()
            let format = 'txt'
            if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
              format = 'json'
            } else if (trimmed.includes('\t')) {
              format = 'tsv'
            } else if (
              trimmed.includes(',') &&
              trimmed.split('\n')[0]?.includes(',')
            ) {
              format = 'csv'
            }
            const parsed = await parseData(trimmed, format)
            data = parsed.data
            extras = parsed.extras
          }

          if (data.length > 0) {
            await projectsAPI.importData(project.id, { data, ...extras })
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
      updatePayload.annotation_time_limit_enabled = s.annotation_time_limit_enabled
      updatePayload.annotation_time_limit_seconds = s.annotation_time_limit_seconds
      updatePayload.strict_timer_enabled = s.strict_timer_enabled

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

      // 5. Refresh and redirect
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
              disabled={loading}
              data-testid="project-create-submit-button"
            >
              {loading
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

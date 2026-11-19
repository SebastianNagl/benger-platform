/**
 * ProjectCreationWizard - Dynamic multi-step project creation
 *
 * Step 1 (Project Info) includes feature checkboxes that control which
 * subsequent steps appear. All data is collected locally, then the project
 * is created with all configuration in a single batch at the end.
 *
 * Draft mode (CORE 2.55, ./wizard/useWizardDraft.ts): when a registered draft
 * policy applies as the user leaves step 1, the wizard works on a draft
 * project instead (saved state, resumable from `?draft=<id>` or the
 * unfinished list, tasks synced after the data step, finished through the
 * finish route). Without a policy nothing of it runs.
 */

'use client'

import { Alert } from '@/components/shared/Alert'
import { Button } from '@/components/shared/Button'
import { Card } from '@/components/shared/Card'
import { ConfirmationDialog } from '@/components/shared/ConfirmationDialog'
import { useToast } from '@/components/shared/Toast'
import { useOptionalAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { ModelScopeProvider } from '@/contexts/ModelScopeContext'
import { apiClient } from '@/lib/api/client'
import { projectsAPI } from '@/lib/api/projects'
import { describeEvaluationConfigWarnings } from '@/lib/evaluation/configWarnings'
import {
  getRegisteredWizardProjectTypes,
  getRegisteredWizardTemplates,
  getWizardKindPreset,
  getWizardPostCreateHooks,
} from '@/lib/extensions'
import { useSlot } from '@/lib/extensions/slots'
import { getWizardFinishContributors } from '@/lib/extensions/wizardFinish'
import {
  buildImportFile,
  detectFormat,
  parseImportData,
} from '@/lib/import/parseImportData'
import { offeredFor, type Jurisdiction } from '@/lib/jurisdiction'
import { extractFieldsFromLabelConfig } from '@/lib/labelConfig/fieldExtractor'
import { canCreateInOrganization } from '@/lib/permissions/groupScope'
import { defaultIconForKind } from '@/lib/projectKind'
import { useProjectStore } from '@/stores/projectStore'
import { ArrowLeftIcon, ArrowRightIcon } from '@heroicons/react/24/outline'
import { useRouter } from 'next/navigation'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { wizardDataJurisdictions } from './wizard/jurisdictions'
import { preselectActiveOrganization } from './wizard/orgPreselect'
import { StepAnnotationInstructions } from './wizard/StepAnnotationInstructions'
import { StepDataImport } from './wizard/StepDataImport'
import { StepEvaluationMethods } from './wizard/StepEvaluationMethods'
import { StepLabelingSetup } from './wizard/StepLabelingSetup'
import { StepModels } from './wizard/StepModels'
import { StepProjectInfo } from './wizard/StepProjectInfo'
import { StepPrompts } from './wizard/StepPrompts'
import { StepSettings } from './wizard/StepSettings'
import {
  DEFAULT_LABEL_CONFIG,
  INITIAL_WIZARD_DATA,
  LabelingTemplate,
  WizardData,
  WizardStepDef,
} from './wizard/types'
import {
  useWizardDraft,
  type DraftConfirmRequest,
} from './wizard/useWizardDraft'
import { WizardDraftList } from './wizard/WizardDraftList'
import { WizardKeyWarning } from './wizard/WizardKeyWarning'
import { WizardStepIndicator } from './wizard/WizardStepIndicator'

const EMPTY_ORGANIZATIONS: never[] = []

// How long "Projekt erstellen" waits for the import of the wizard's own rows
// (a handful of tasks, done in seconds on the interactive queue) before it
// stops the spinner, says the import has not finished, and opens the project.
// A worker that crashed or never took the job would otherwise keep the wizard
// spinning for good (rubric e2e D01).
const WIZARD_IMPORT_TIMEOUT_MS = 3 * 60 * 1000

export function ProjectCreationWizard() {
  const router = useRouter()
  const { t } = useI18n()
  const { addToast } = useToast()
  const { createProject, fetchProject, loading } = useProjectStore()

  const [wizardData, setWizardData] = useState<WizardData>(INITIAL_WIZARD_DATA)
  // There is no selected organization any more: the wizard names the
  // organization a project belongs to. A user with exactly one organization
  // where they may create projects gets it preselected (left private, the
  // worker resolves API keys per user and every AI feature fails with "No
  // API key found" although the organization has a key); anyone with
  // several chooses explicitly. Private stays one click away.
  // `useOptionalAuth` rather than `useAuth`: the wizard also mounts without
  // an AuthProvider (tests, embeds).
  const organizations = useOptionalAuth()?.organizations ?? EMPTY_ORGANIZATIONS
  const activeOrganization = useMemo(() => {
    // Org role Contributor/Admin (org-wide projects) or a group role
    // Contributor/Admin (that group's projects; the step then pins the
    // group for an org Annotator).
    const creatable = organizations.filter(canCreateInOrganization)
    return creatable.length === 1 ? creatable[0] : null
  }, [organizations])
  // The membership list arrives after the first render. The preselection is
  // applied when it arrives, once per organization, and never after anyone
  // has made a visibility choice. Adjusted during render rather than in an
  // effect, so it costs no extra commit.
  const [visibilityTouched, setVisibilityTouched] = useState(false)
  const [preselectedOrgId, setPreselectedOrgId] = useState<string | null>(null)
  if (
    activeOrganization &&
    !visibilityTouched &&
    activeOrganization.id !== preselectedOrgId
  ) {
    setPreselectedOrgId(activeOrganization.id)
    setWizardData((prev) =>
      preselectActiveOrganization(prev, activeOrganization),
    )
  }
  // The organization a synthetic generation and the model pickers of this
  // wizard run against: the first selected organization, else none
  // (personal keys).
  const creationOrganizationId =
    wizardData.visibility === 'organization'
      ? (wizardData.organizationIds[0] ?? null)
      : null
  // What the footer says next to "Create": where the project will live.
  const creationTargetName = (() => {
    if (wizardData.visibility === 'public') {
      return t('projects.creation.wizard.navigation.publicTarget')
    }
    if (wizardData.visibility === 'organization') {
      const names = wizardData.organizationIds.map(
        (id) => organizations.find((o) => o.id === id)?.name ?? id,
      )
      if (names.length > 0) return names.join(', ')
    }
    return t('projects.creation.wizard.navigation.privateTarget')
  })()
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
  // A confirmation of the draft mode (discard, replaced sheets, ...),
  // answered through the dialog at the bottom.
  const [confirmRequest, setConfirmRequest] = useState<
    (DraftConfirmRequest & { resolve: (ok: boolean) => void }) | null
  >(null)
  const askConfirm = useCallback(
    (request: DraftConfirmRequest) =>
      new Promise<boolean>((resolve) =>
        setConfirmRequest({ ...request, resolve }),
      ),
    [],
  )
  const answerConfirm = (ok: boolean) => {
    confirmRequest?.resolve(ok)
    setConfirmRequest(null)
  }
  // A resumed draft names its step together with its restored state (one
  // batched update); the index is set on the render that has both. A step
  // the restored features no longer have leaves the wizard on its step.
  const [pendingStepId, setPendingStepId] = useState<string | null>(null)
  const navigatingRef = useRef(false)
  const [navigating, setNavigating] = useState(false)

  // Every template incl. the jurisdiction-restricted ones: a registered
  // project type selects its template by id from here.
  const allTemplates: (LabelingTemplate & { jurisdictions?: string[] })[] =
    useMemo(
      () => [
        {
          id: 'question-answering',
          name: t('projects.creation.wizard.templates.questionAnswering.name'),
          description: t(
            'projects.creation.wizard.templates.questionAnswering.description',
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
            'projects.creation.wizard.templates.multipleChoice.description',
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
            'projects.creation.wizard.templates.spanAnnotation.description',
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
          description: t(
            'projects.creation.wizard.templates.custom.description',
          ),
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
      [t],
    )
  // The templates the labeling step offers for this project's jurisdictions,
  // plus the selected one (a project type of another jurisdiction picked
  // via "show all" brings its template along).
  const jurisdictionKey = wizardDataJurisdictions(
    organizations,
    wizardData,
  ).join(',')
  const selectedTemplateId = wizardData.labelingConfig?.id
  const nlpTemplates: LabelingTemplate[] = useMemo(() => {
    const active = jurisdictionKey.split(',') as Jurisdiction[]
    return allTemplates.filter(
      (tpl) =>
        offeredFor(tpl.jurisdictions, active) || tpl.id === selectedTemplateId,
    )
  }, [allTemplates, jurisdictionKey, selectedTemplateId])

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
          'projects.creation.wizard.steps.projectInfo.description',
        ),
      },
    ]

    if (wizardData.features.synthetic) {
      steps.push({
        id: 'synthetic',
        name: t('projects.creation.wizard.steps.synthetic.name'),
        description: t('projects.creation.wizard.steps.synthetic.description'),
      })
    }

    if (wizardData.features.dataImport) {
      steps.push({
        id: 'dataImport',
        name: t('projects.creation.wizard.steps.dataImport.name'),
        description: t('projects.creation.wizard.steps.dataImport.description'),
      })
    }

    if (wizardData.features.annotation) {
      steps.push(
        {
          id: 'labelingSetup',
          name: t('projects.creation.wizard.steps.labelingSetup.name'),
          description: t(
            'projects.creation.wizard.steps.labelingSetup.description',
          ),
        },
        {
          id: 'annotationInstructions',
          name: t('projects.creation.wizard.steps.annotationInstructions.name'),
          description: t(
            'projects.creation.wizard.steps.annotationInstructions.description',
          ),
        },
      )
    }

    if (wizardData.features.llmGeneration) {
      steps.push(
        {
          id: 'models',
          name: t('projects.creation.wizard.steps.models.name'),
          description: t('projects.creation.wizard.steps.models.description'),
        },
        {
          id: 'prompts',
          name: t('projects.creation.wizard.steps.prompts.name'),
          description: t('projects.creation.wizard.steps.prompts.description'),
        },
      )
    }

    if (wizardData.features.evaluation) {
      steps.push({
        id: 'evaluation',
        name: t('projects.creation.wizard.steps.evaluation.name'),
        description: t('projects.creation.wizard.steps.evaluation.description'),
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
        description: t('projects.creation.wizard.steps.rubric.description'),
      })
    }

    steps.push({
      id: 'settings',
      name: t('projects.creation.wizard.steps.settings.name'),
      description: t('projects.creation.wizard.steps.settings.description'),
    })

    return steps
  }, [wizardData.features, t])

  // Clamp step index when steps change (e.g., user unchecks a feature)
  const clampedStepIndex = Math.min(currentStepIndex, activeSteps.length - 1)
  if (clampedStepIndex !== currentStepIndex) {
    setCurrentStepIndex(clampedStepIndex)
  }

  if (pendingStepId) {
    const pendingIndex = activeSteps.findIndex((s) => s.id === pendingStepId)
    setPendingStepId(null)
    if (pendingIndex >= 0 && pendingIndex !== currentStepIndex) {
      setCurrentStepIndex(pendingIndex)
    }
  }

  const currentStep = activeSteps[currentStepIndex]
  const isLastStep = currentStepIndex === activeSteps.length - 1

  // A <Repeater> config lists its indexed fields only against the imported
  // tasks, so the selected file is read when the config has one.
  const configHasRepeater =
    !!wizardData.labelingConfig?.config?.includes('<Repeater')
  const [readFile, setReadFile] = useState<{
    file: File
    content: string
  } | null>(null)
  useEffect(() => {
    const file = wizardData.selectedFile
    if (!file || !configHasRepeater) return
    let cancelled = false
    const reader = new FileReader()
    reader.onload = (e) => {
      if (!cancelled) {
        setReadFile({ file, content: e.target?.result as string })
      }
    }
    reader.readAsText(file)
    return () => {
      cancelled = true
    }
  }, [wizardData.selectedFile, configHasRepeater])
  const selectedFileContent =
    readFile && readFile.file === wizardData.selectedFile
      ? readFile.content
      : null

  const importedTasksData = useMemo(() => {
    if (!configHasRepeater) return []
    const content = (
      wizardData.selectedFile ? selectedFileContent : wizardData.pastedData
    )?.trim()
    if (!content) return []
    try {
      const { rows } = parseImportData(
        content,
        detectFormat(content, wizardData.selectedFile?.name),
      )
      return rows.map((row) => row.data)
    } catch {
      return []
    }
  }, [
    configHasRepeater,
    selectedFileContent,
    wizardData.pastedData,
    wizardData.selectedFile,
  ])

  // Derive fields from earlier wizard steps for cross-step data flow
  const labelConfigFields = useMemo(
    () =>
      wizardData.labelingConfig?.config
        ? extractFieldsFromLabelConfig(
            wizardData.labelingConfig.config,
            importedTasksData,
          )
        : { outputFields: [], inputFields: [] },
    [wizardData.labelingConfig?.config, importedTasksData],
  )

  const availableVariables = useMemo(() => {
    const vars = new Set<string>()
    for (const f of labelConfigFields.inputFields) vars.add(f)
    for (const col of wizardData.dataColumns) vars.add(col)
    return Array.from(vars)
  }, [labelConfigFields.inputFields, wizardData.dataColumns])

  const updateWizardData = useCallback(
    (partial: Partial<WizardData>) => {
      if ('visibility' in partial || 'organizationIds' in partial) {
        setVisibilityTouched(true)
      }
      setWizardData((prev) => {
        const next = { ...prev, ...partial }
        // Choosing a project type pre-selects the matching labeling template
        // (Klausurlösung / Karteikarten, registered by the extended edition)
        // and switches annotation on, so the project gets the shape the
        // student surfaces, discovery and the deck workspace recognise. The
        // user can still pick another template afterwards.
        // A base-kind change without an explicit option (e.g. the
        // KI-Generator stamping the exam kind) selects that kind's option.
        if (
          partial.projectKind &&
          partial.projectKind !== prev.projectKind &&
          !('projectTypeId' in partial)
        ) {
          next.projectTypeId = partial.projectKind
        }
        const prevTypeId = prev.projectTypeId ?? prev.projectKind
        const nextTypeId = next.projectTypeId ?? next.projectKind
        if (
          (partial.projectKind && partial.projectKind !== prev.projectKind) ||
          nextTypeId !== prevTypeId
        ) {
          const registeredType = getRegisteredWizardProjectTypes().find(
            (r) => r.id === nextTypeId,
          )
          const templateId =
            registeredType?.templateId ??
            (next.projectKind === 'exam'
              ? 'exam-solving'
              : next.projectKind === 'flashcard_collection'
                ? 'flashcard-deck'
                : null)
          const template = templateId
            ? allTemplates.find((tpl) => tpl.id === templateId)
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
            prev.projectKind === 'generic' ? null : prev.projectKind,
          )
          if (!prev.icon || prev.icon === prevDefault) {
            next.icon = defaultIconForKind(
              next.projectKind === 'generic' ? null : next.projectKind,
            )
          }
          // Extended kind preset: prefills judge pair / immediate eval /
          // exam settings so the project works on both surfaces; a
          // registered type's own preset refines it afterwards.
          const preset = getWizardKindPreset(next.projectKind)
          if (preset) {
            Object.assign(next, preset(next))
          }
          if (registeredType?.preset) {
            Object.assign(next, registeredType.preset(next))
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
    [allTemplates],
  )

  // A restored draft state replaces the wizard state as a whole; it already
  // carries its visibility choice, so the organization preselection stays off.
  const replaceWizardData = useCallback((data: WizardData) => {
    setVisibilityTouched(true)
    setWizardData(data)
  }, [])

  const draftCtl = useWizardDraft({
    wizardData,
    replaceWizardData,
    updateWizardData,
    stepIds: activeSteps.map((s) => s.id),
    currentStepId: currentStep?.id,
    goToStepId: setPendingStepId,
    confirm: askConfirm,
    addToast,
    importTimeoutMs: WIZARD_IMPORT_TIMEOUT_MS,
  })
  const draftProjectId = draftCtl.draft?.projectId ?? null

  const validateStep = (): boolean => {
    const newErrors: Record<string, string> = {}

    if (currentStep?.id === 'projectInfo') {
      if (!wizardData.title.trim()) {
        newErrors.title = t(
          'projects.creation.wizard.step1.validation.nameRequired',
        )
      }
      if (
        wizardData.visibility === 'organization' &&
        wizardData.organizationIds.length === 0
      ) {
        newErrors.organizationIds = t(
          'projects.creation.wizard.step1.validation.orgRequired',
        )
      }
    }

    setErrors(newErrors)
    return Object.keys(newErrors).length === 0
  }

  // Every step change goes through here. Without draft mode it is the plain
  // index change it always was; in draft mode the draft is created, saved
  // and synced first, and the move is dropped when that fails or the user
  // declines a confirmation.
  const navigateTo = (targetIndex: number) => {
    if (!draftCtl.capable) {
      setCurrentStepIndex(targetIndex)
      return
    }
    if (navigatingRef.current || targetIndex === currentStepIndex) return
    if (
      currentStep?.id === 'projectInfo' &&
      targetIndex > currentStepIndex &&
      !validateStep()
    ) {
      return
    }
    navigatingRef.current = true
    setNavigating(true)
    const fromIndex = currentStepIndex
    void (async () => {
      try {
        if (await draftCtl.beforeNavigate(fromIndex, targetIndex)) {
          setCurrentStepIndex(targetIndex)
        }
      } finally {
        navigatingRef.current = false
        setNavigating(false)
      }
    })()
  }

  const handleNext = () => {
    if (validateStep() && currentStepIndex < activeSteps.length - 1) {
      navigateTo(currentStepIndex + 1)
    }
  }

  const handleBack = () => {
    if (currentStepIndex > 0) {
      navigateTo(currentStepIndex - 1)
    }
  }

  const handleDiscardDraft = async () => {
    if (await draftCtl.discard()) router.push('/projects')
  }

  const handleFinish = async () => {
    if (isFinishingRef.current) return
    if (!validateStep()) return

    isFinishingRef.current = true
    setIsFinishing(true)

    try {
      // 1. The project: the draft (draft mode, its tasks synced once more),
      // else created now with its visibility and data import.
      const ready = draftProjectId
        ? await ensureDraftReady()
        : { projectId: await createProjectNow(), committed: false }
      const projectId = ready.projectId
      if (projectId === null) {
        // A leave guard held the finish, or the final task or configuration
        // sync of the draft did not go through (declined, or failed with
        // its own message).
        isFinishingRef.current = false
        setIsFinishing(false)
        return
      }

      // In draft mode the state as the final sync left it (it reads the
      // evaluation configs back, a write the closure has not seen yet).
      // A finish that already committed configured the project before.
      if (!ready.committed) {
        await configureProject(
          projectId,
          draftProjectId ? draftCtl.currentData() : wizardData,
        )
      }

      if (draftProjectId) {
        // The last write: visibility and organizations, so the project
        // becomes visible to others only now that it is complete.
        await draftCtl.finish()
        addToast(t('store.project.created'), 'success')
      }

      // 6. Refresh and redirect
      await new Promise((resolve) => setTimeout(resolve, 100))
      await fetchProject(projectId)
      // No success toast here: `createProject` in the store already confirmed
      // the creation, and a second toast repeated it.
      router.push(`/projects/${projectId}`)
    } catch (error) {
      addToast(
        error instanceof Error
          ? error.message
          : t('projects.wizard.createFailed'),
        'error',
      )
      // Re-enable the button so the user can retry. On the success path we
      // navigate away (router.push) and the component unmounts, so the guard
      // intentionally stays set there to keep the button disabled.
      isFinishingRef.current = false
      setIsFinishing(false)
    }
  }

  /**
   * Draft mode: the policies' leave guards, then the final task sync and the
   * final configuration sync (so the configSynced hooks run whether or not
   * the rubric step was visited); a null project when a guard held the
   * finish or a sync did not go through. `committed`: an earlier
   * finish went through although its answer was lost; only the finish
   * (idempotent per client key) is left.
   */
  const ensureDraftReady = async (): Promise<{
    projectId: string | null
    committed: boolean
  }> => {
    if (!(await draftCtl.beforeFinish())) {
      return { projectId: null, committed: false }
    }
    const synced = (await draftCtl.syncTasks()) && (await draftCtl.syncConfig())
    if (synced) return { projectId: draftProjectId, committed: false }
    if (draftCtl.finishCommitted()) {
      return { projectId: draftProjectId, committed: true }
    }
    return { projectId: null, committed: false }
  }

  /** Create the project with its visibility and import the wizard's data. */
  const createProjectNow = async (): Promise<string> => {
    // 1. Create project with basic info + label config
    const createData: {
      title: string
      description: string
      label_config: string
      is_private?: boolean
      is_public?: boolean
      public_role?: 'ANNOTATOR' | 'CONTRIBUTOR' | null
      kind?: string | null
      icon?: string | null
      organization_id?: string
      organization_group_id?: string | null
    } = {
      title: wizardData.title.trim(),
      description: wizardData.description.trim(),
      label_config: wizardData.labelingConfig?.config || DEFAULT_LABEL_CONFIG,
      // Write-once project type; generic stays NULL so plain benchmark
      // projects are unaffected.
      kind:
        wizardData.projectKind === 'generic' ? null : wizardData.projectKind,
      icon: wizardData.icon.trim() || null,
    }
    if (wizardData.visibility === 'private') {
      createData.is_private = true
    } else if (wizardData.visibility === 'public') {
      createData.is_public = true
      createData.public_role = wizardData.publicRole
    } else if (wizardData.organizationIds.length > 0) {
      // The first selected organization is the creation target; the
      // attachment is scoped to its selected group right away (null =
      // org-wide), so there is no window where the whole org can see a
      // group-scoped project. Further organizations are attached by the
      // visibility PATCH below.
      const [firstOrgId] = wizardData.organizationIds
      createData.organization_id = firstOrgId
      createData.organization_group_id =
        wizardData.organizationGroupIds[firstOrgId] ?? null
    }

    const project = await createProject(createData)

    if (
      wizardData.visibility === 'organization' &&
      wizardData.organizationIds.length > 0
    ) {
      try {
        await projectsAPI.updateVisibility(project.id, {
          is_private: false,
          // Per-org group scope (null = the whole organization).
          organization_attachments: wizardData.organizationIds.map((orgId) => ({
            organization_id: orgId,
            group_id: wizardData.organizationGroupIds[orgId] ?? null,
          })),
        })
      } catch (err) {
        console.error(
          'Failed to assign organizations after project create',
          err,
        )
        addToast(t('projects.creation.wizard.orgAssignFailed'), 'error')
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
            detectFormat(content, wizardData.selectedFile.name),
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
          await projectsAPI.runNestedImportJob(project.id, file, undefined, {
            timeoutMs: WIZARD_IMPORT_TIMEOUT_MS,
          })
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
          // By name, not instanceof: an ImportJobTimeoutError (lib/api/projects).
          importError instanceof Error &&
            importError.name === 'ImportJobTimeoutError'
            ? t('projects.wizard.importDataTimeout', {
                minutes: Math.round(WIZARD_IMPORT_TIMEOUT_MS / 60000),
              })
            : t('projects.wizard.importDataFailed', {
                error:
                  importError instanceof Error
                    ? importError.message
                    : t('projects.wizard.unknownError'),
              }),
          'error',
        )
      }
    }
    return project.id
  }

  /** The settings, evaluation, prompt and extension writes of the finish. */
  const configureProject = async (
    projectId: string,
    wizardData: WizardData,
  ): Promise<void> => {
    // 3. Update project with instructions + generation config (single PATCH)
    // (in draft mode with the basic fields too: they may have changed
    // since the draft was created)
    const updatePayload: Record<string, any> = draftProjectId
      ? { ...draftCtl.basicFields(wizardData) }
      : {}

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
      updatePayload.instructions_always_visible =
        wizardData.instructions_always_visible
      updatePayload.show_skip_button = wizardData.show_skip_button
    }

    // Evaluation settings
    if (wizardData.features.evaluation) {
      updatePayload.immediate_evaluation_enabled =
        wizardData.immediate_evaluation_enabled
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
    updatePayload.require_confirm_before_submit =
      s.require_confirm_before_submit
    updatePayload.annotator_full_visibility_after_submit =
      s.annotator_full_visibility_after_submit
    updatePayload.annotation_time_limit_enabled =
      s.annotation_time_limit_enabled
    updatePayload.annotation_time_limit_seconds =
      s.annotation_time_limit_seconds
    updatePayload.strict_timer_enabled = s.strict_timer_enabled
    updatePayload.window_start_at = s.window_start_at
    updatePayload.window_end_at = s.window_end_at

    // Persist the wizard's feature checkboxes as project-level visibility
    // flags so the detail page knows which configuration cards to render.
    updatePayload.enable_annotation = wizardData.features.annotation
    updatePayload.enable_generation = wizardData.features.llmGeneration
    updatePayload.enable_evaluation = wizardData.features.evaluation

    if (Object.keys(updatePayload).length > 0) {
      await projectsAPI.update(projectId, updatePayload)
    }

    // 4. Save evaluation configs if any (in draft mode only when they
    // changed since they were last written or read back: the PUT replaces
    // the list, and the rubric step may have added keys since)
    if (
      wizardData.features.evaluation &&
      wizardData.evaluationConfigs.length > 0 &&
      (!draftProjectId ||
        draftCtl.evalConfigsChanged(wizardData.evaluationConfigs))
    ) {
      try {
        const evalResponse: any = await apiClient.put(
          `/evaluations/projects/${projectId}/evaluation-config`,
          { evaluation_configs: wizardData.evaluationConfigs },
        )
        // Saved, but some configs will grade nothing as written.
        const evalWarnings = describeEvaluationConfigWarnings(
          evalResponse?.warnings,
          wizardData.evaluationConfigs,
          t,
        )
        if (evalWarnings.length > 0) {
          addToast(
            t('toasts.project.evaluationConfigsSavedWithWarnings', {
              warnings: evalWarnings.join(' '),
            }),
            'warning',
            10000,
          )
        }
      } catch (evalError) {
        // The project already exists, so a rejected config must not abort
        // creation. The reason still has to reach the user: the API names
        // the evaluation and the field to choose instead.
        const reason = evalError instanceof Error ? evalError.message : ''
        addToast(
          reason
            ? t('toasts.project.evaluationConfigsSaveFailed', {
                error: reason,
              })
            : t('projects.creation.wizard.evalSaveFailed'),
          'error',
        )
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
          `/projects/${projectId}/generation-config/structures/default`,
          {
            name:
              wizardData.promptTemplate !== 'custom'
                ? wizardData.promptTemplate
                : 'Default',
            system_prompt: wizardData.systemPrompt,
            instruction_prompt: wizardData.instructionPrompt,
          },
        )
        await apiClient.put(
          `/projects/${projectId}/generation-config/structures`,
          ['default'],
        )
      } catch {
        // Non-critical — prompts are also saved in generation_config.selected_configuration
        addToast(
          t('projects.creation.wizard.promptStructureSaveFailed'),
          'error',
        )
      }
    }

    // 5. Extended post-create hooks (e.g. rubric generation). The project
    // exists at this point, so a failing hook only toasts. In draft mode
    // they run before the finish route and are told so.
    for (const hook of getWizardPostCreateHooks()) {
      try {
        await hook(
          draftProjectId
            ? { projectId, wizardData, draft: true }
            : { projectId, wizardData },
        )
      } catch (hookError) {
        addToast(
          hookError instanceof Error
            ? hookError.message
            : t('projects.wizard.postCreateHookFailed'),
          'error',
        )
      }
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
            preselectedOrganization={activeOrganization}
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
            onFileChange={(selectedFile) => updateWizardData({ selectedFile })}
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
            wizardData={wizardData}
            onWizardChange={updateWizardData}
          />
        )
      case 'rubric':
        // Extended-only step (mirrors 'synthetic'): the AI-Bewertungsbogen —
        // per-task rubric generation installed as a SECOND evaluation method
        // (llm_judge_rubric) by the post-create hook once tasks exist.
        // In draft mode the step also gets the draft's id: its tasks and
        // sheets exist there, so sheets are generated and checked in place.
        return RubricStep ? (
          <RubricStep
            data={wizardData}
            onChange={updateWizardData}
            {...(draftProjectId ? { draftProjectId } : {})}
          />
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
      {draftCtl.policyRegistered &&
        !draftProjectId &&
        !draftCtl.resuming &&
        currentStepIndex === 0 && (
          <WizardDraftList
            onContinue={(id) => void draftCtl.resume(id)}
            confirm={askConfirm}
            discardMessage={draftCtl.discardMessage}
            onError={(message) => addToast(message, 'error')}
          />
        )}

      {draftCtl.problem === 'conflict' && draftProjectId && (
        <div className="mb-4" data-testid="wizard-draft-conflict">
          <Alert variant="warning">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <span>{t('projects.creation.wizard.draft.conflict')}</span>
              <Button
                variant="outline"
                onClick={() => void draftCtl.resume(draftProjectId)}
              >
                {t('projects.creation.wizard.draft.reload')}
              </Button>
            </div>
          </Alert>
        </div>
      )}
      {draftCtl.problem === 'expired' && (
        <div className="mb-4" data-testid="wizard-draft-expired">
          <Alert variant="error">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <span>{t('projects.creation.wizard.draft.expired')}</span>
              <Button
                variant="outline"
                onClick={() => {
                  // Back to an empty wizard on step 1; the expired draft is
                  // gone on the server already.
                  draftCtl.forget()
                  replaceWizardData(INITIAL_WIZARD_DATA)
                  setCurrentStepIndex(0)
                }}
              >
                {t('projects.creation.wizard.draft.startOver')}
              </Button>
            </div>
          </Alert>
        </div>
      )}

      <WizardStepIndicator
        steps={activeSteps}
        currentStepIndex={currentStepIndex}
        onStepClick={(index) => navigateTo(index)}
      />

      {draftProjectId &&
        currentStep?.id === 'dataImport' &&
        !wizardData.selectedFile &&
        draftCtl.draftImport?.fileName &&
        draftCtl.draftImport.rowCount > 0 && (
          <div className="mb-4" data-testid="wizard-draft-import-notice">
            <Alert variant="info">
              {t('projects.creation.wizard.draft.importedNotice', {
                count: draftCtl.draftImport.rowCount,
                name: draftCtl.draftImport.fileName,
              })}
            </Alert>
          </div>
        )}

      <Card className="mb-8">
        {/* Model pickers and the synthetic step list what the creation
            target can run (its organization key, else personal keys). */}
        <ModelScopeProvider organizationId={creationOrganizationId}>
          <div className="p-8">{renderCurrentStep()}</div>
        </ModelScopeProvider>
      </Card>

      {/* Before "Create": say which AI features will lack a provider key.
          Only on the last step, where every choice that decides it is made. */}
      {isLastStep && <WizardKeyWarning data={wizardData} />}

      {/* Navigation */}
      <div className="flex justify-between">
        <Button
          variant="outline"
          onClick={
            currentStepIndex === 0 ? () => router.push('/projects') : handleBack
          }
          disabled={loading || navigating}
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

        <div className="flex items-center gap-3">
          {draftProjectId && (
            <>
              <span
                className="text-xs text-zinc-500 dark:text-zinc-400"
                data-testid="wizard-draft-status"
              >
                {draftCtl.saving
                  ? t('projects.creation.wizard.draft.saving')
                  : t('projects.creation.wizard.draft.saved')}
              </span>
              <Button
                variant="outline"
                onClick={() => void handleDiscardDraft()}
                disabled={isFinishing || navigating}
                data-testid="wizard-draft-discard-button"
              >
                {t('projects.creation.wizard.draft.discardDraft')}
              </Button>
            </>
          )}
          {isLastStep && (
            // Where the project will live, as chosen on the first step.
            <span
              className="text-xs text-zinc-500 dark:text-zinc-400"
              data-testid="project-create-target"
            >
              {t('projects.creation.wizard.navigation.creationTarget', {
                name: creationTargetName,
              })}
            </span>
          )}
          {isLastStep ? (
            <Button
              onClick={handleFinish}
              disabled={loading || isFinishing || navigating}
              data-testid="project-create-submit-button"
            >
              {loading || isFinishing
                ? t('projects.creation.wizard.navigation.creating')
                : t('projects.creation.wizard.navigation.create')}
            </Button>
          ) : (
            <Button
              onClick={handleNext}
              disabled={loading || navigating}
              data-testid="project-create-next-button"
            >
              {t('projects.creation.wizard.navigation.next')}
              <ArrowRightIcon className="ml-2 h-4 w-4" />
            </Button>
          )}
        </div>
      </div>

      {confirmRequest && (
        <ConfirmationDialog
          isOpen
          onClose={() => answerConfirm(false)}
          onConfirm={() => answerConfirm(true)}
          title={confirmRequest.title}
          message={confirmRequest.message}
          confirmText={confirmRequest.confirmText}
          variant={confirmRequest.variant ?? 'warning'}
        />
      )}
    </div>
  )
}

/**
 * ProjectCreationWizard - Label Studio aligned multi-step project creation
 *
 * Three-step wizard for creating projects:
 * 1. Project Info - Name and description
 * 2. Data Import - Upload or connect data (optional)
 * 3. Labeling Setup - Configure annotation interface
 */

'use client'

import { Badge } from '@/components/shared/Badge'
import { Button } from '@/components/shared/Button'
import { Card } from '@/components/shared/Card'
import { Input } from '@/components/shared/Input'
import { Label } from '@/components/shared/Label'
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '@/components/shared/Tabs'
import { Textarea } from '@/components/shared/Textarea'
import { useI18n } from '@/contexts/I18nContext'
import { projectsAPI } from '@/lib/api/projects'
import { cn } from '@/lib/utils'
import { useProjectStore } from '@/stores/projectStore'
import {
  ArrowLeftIcon,
  ArrowRightIcon,
  CheckIcon,
  CloudArrowUpIcon,
  Cog6ToothIcon,
  DocumentTextIcon,
} from '@heroicons/react/24/outline'
import { useRouter } from 'next/navigation'
import React, { useCallback, useState } from 'react'
import { toast } from 'react-hot-toast'

interface Step {
  id: number
  name: string
  description: string
  icon: React.ComponentType<{ className?: string }>
}

export function ProjectCreationWizard() {
  const router = useRouter()
  const { t } = useI18n()
  const { createProject, fetchProject, loading } = useProjectStore()

  const steps: Step[] = [
    {
      id: 1,
      name: t('projects.creation.wizard.steps.projectInfo.name'),
      description: t('projects.creation.wizard.steps.projectInfo.description'),
      icon: DocumentTextIcon,
    },
    {
      id: 2,
      name: t('projects.creation.wizard.steps.dataImport.name'),
      description: t('projects.creation.wizard.steps.dataImport.description'),
      icon: CloudArrowUpIcon,
    },
    {
      id: 3,
      name: t('projects.creation.wizard.steps.labelingSetup.name'),
      description: t(
        'projects.creation.wizard.steps.labelingSetup.description'
      ),
      icon: Cog6ToothIcon,
    },
  ]

  const nlpTemplates = [
    {
      id: 'question-answering',
      name: t('projects.creation.wizard.templates.questionAnswering.name'),
      description: t(
        'projects.creation.wizard.templates.questionAnswering.description'
      ),
      icon: '❓',
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
      icon: '🔘',
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
      id: 'exam-solving',
      name: t('projects.creation.wizard.templates.examSolving.name'),
      description: t(
        'projects.creation.wizard.templates.examSolving.description'
      ),
      icon: '📚',
      category: 'NLP',
      config: `<View>
  <Header value="Angabe"/>
  <Angabe name="angabe" value="$sachverhalt" toName="sachverhalt"
          linkedTo="gliederung">
    <Label value="Wichtig" background="#fef08a"/>
    <Label value="Problematisch" background="#fca5a5"/>
    <Label value="Zu pruefen" background="#fed7aa"/>
    <Label value="Begruendung" background="#bbf7d0"/>
    <Label value="Norm" background="#bfdbfe"/>
    <Label value="Sonstiges" background="#e9d5ff"/>
  </Angabe>

  <Header value="Notizen"/>
  <Notizen name="notizen" toName="sachverhalt"
           placeholder="Eigene Notizen und Anmerkungen..."/>

  <Header value="Gliederung"/>
  <Gliederung name="gliederung" toName="sachverhalt"
              placeholder="A. Anspruch des X gegen Y..."
              required="true"/>

  <Header value="Loesung"/>
  <Loesung name="loesung" toName="sachverhalt"
           linkedTo="gliederung"
           placeholder="A. Anspruch des X gegen Y auf Schadensersatz..."
           required="true"/>
</View>`,
    },
    {
      id: 'span-annotation',
      name: t('projects.creation.wizard.templates.spanAnnotation.name'),
      description: t(
        'projects.creation.wizard.templates.spanAnnotation.description'
      ),
      icon: '🏷️',
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
      icon: '⚙️',
      category: 'Custom',
      config: `<View>
  <!-- Define your custom annotation interface -->
  <Text name="text" value="$text"/>
  <!-- Add your components here -->
</View>`,
    },
  ]

  const [currentStep, setCurrentStep] = useState(1)
  const [projectData, setProjectData] = useState({
    title: '',
    description: '',
    importData: null as any,
    labelingConfig: null as any,
  })
  const [pastedData, setPastedData] = useState('')
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [errors, setErrors] = useState<Record<string, string>>({})

  const handleFileSelect = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0]
      if (file) {
        setSelectedFile(file)
      }
    },
    []
  )

  const handleDrop = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    const file = e.dataTransfer.files?.[0]
    if (file) {
      setSelectedFile(file)
    }
  }, [])

  const handleDragOver = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault()
  }, [])

  const validateStep = (step: number): boolean => {
    const newErrors: Record<string, string> = {}

    if (step === 1) {
      if (!projectData.title.trim()) {
        newErrors.title = t(
          'projects.creation.wizard.step1.validation.nameRequired'
        )
      }
    }

    setErrors(newErrors)
    return Object.keys(newErrors).length === 0
  }

  const handleNext = () => {
    if (validateStep(currentStep)) {
      if (currentStep < steps.length) {
        setCurrentStep(currentStep + 1)
      }
    }
  }

  const handleBack = () => {
    if (currentStep > 1) {
      setCurrentStep(currentStep - 1)
    }
  }

  const parseData = async (content: string, format: string): Promise<any[]> => {
    try {
      if (format === 'json') {
        const parsed = JSON.parse(content)
        // Handle both array and single object
        if (Array.isArray(parsed)) {
          return parsed
        } else if (parsed.qa_samples && Array.isArray(parsed.qa_samples)) {
          // Handle nested structure like our mock data
          return parsed.qa_samples
        } else if (parsed.questions && Array.isArray(parsed.questions)) {
          // Handle Label Studio format with questions array
          return parsed.questions.map((q: any) => q.question_data || q)
        } else {
          return [parsed]
        }
      } else if (format === 'csv' || format === 'tsv') {
        const delimiter = format === 'csv' ? ',' : '\t'
        const lines = content.trim().split('\n')
        if (lines.length === 0) return []

        // Parse header
        const headers = lines[0]
          .split(delimiter)
          .map((h) => h.trim().replace(/^["']|["']$/g, ''))

        // Parse data rows
        return lines.slice(1).map((line) => {
          const values = line
            .split(delimiter)
            .map((v) => v.trim().replace(/^["']|["']$/g, ''))
          const obj: any = {}
          headers.forEach((header, index) => {
            obj[header] = values[index] || ''
          })
          return obj
        })
      } else {
        // Plain text - each line becomes a task
        return content
          .trim()
          .split('\n')
          .filter((line) => line.trim())
          .map((line) => ({
            text: line.trim(),
          }))
      }
    } catch (error) {
      throw new Error(`Failed to parse ${format.toUpperCase()} data: ${error}`)
    }
  }

  const handleFinish = async () => {
    if (!validateStep(currentStep)) return

    try {
      // Create project with all configuration including labeling config
      // Always include a default label_config if none is selected
      const defaultLabelConfig = `<View>
  <Text name="text" value="$text"/>
  <TextArea name="answer" toName="text" 
            placeholder="Enter your answer..." 
            rows="4" maxSubmissions="1"/>
</View>`

      const createData = {
        title: projectData.title.trim(),
        description: projectData.description.trim(),
        label_config: projectData.labelingConfig?.config || defaultLabelConfig,
      }

      const project = await createProject(createData)

      // Import data if provided
      if (pastedData.trim() || selectedFile) {
        try {
          let data: any[] = []

          if (selectedFile) {
            // Read file content
            const content = await new Promise<string>((resolve, reject) => {
              const reader = new FileReader()
              reader.onload = (e) => resolve(e.target?.result as string)
              reader.onerror = reject
              reader.readAsText(selectedFile)
            })

            // Determine format from file extension
            const format =
              selectedFile.name.split('.').pop()?.toLowerCase() || 'txt'
            data = await parseData(content, format)
          } else if (pastedData.trim()) {
            // Try to detect format from content
            const trimmed = pastedData.trim()
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

            data = await parseData(trimmed, format)
          }

          if (data.length > 0) {
            await projectsAPI.importData(project.id, { data })
            // Refresh project data to get updated task count
            await new Promise((resolve) => setTimeout(resolve, 100)) // Small delay for backend processing
            await fetchProject(project.id) // This updates both currentProject and projects list
            toast.success(
              t('projects.wizard.projectCreatedWithTasks', { count: data.length })
            )
          } else {
            toast.success(t('projects.wizard.projectCreated'))
          }
        } catch (importError) {
          toast.success(t('projects.wizard.projectCreated'))
          toast.error(
            t('projects.wizard.importDataFailed', { error: importError instanceof Error ? importError.message : t('projects.wizard.unknownError') })
          )
        }
      } else {
        toast.success(t('projects.wizard.projectCreated'))
      }

      router.push(`/projects/${project.id}`)
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : t('projects.wizard.createFailed')
      )
    }
  }

  const renderStepIndicator = () => (
    <div className="mb-8 flex items-center justify-between">
      {steps.map((step, index) => {
        const Icon = step.icon
        const isActive = step.id === currentStep
        const isCompleted = step.id < currentStep

        return (
          <React.Fragment key={step.id}>
            <div className="flex items-center">
              <div
                className={cn(
                  'flex h-10 w-10 items-center justify-center rounded-full border-2 transition-colors',
                  isActive && 'border-emerald-600 bg-emerald-600 text-white',
                  isCompleted && 'border-emerald-600 bg-emerald-600 text-white',
                  !isActive &&
                    !isCompleted &&
                    'border-zinc-300 dark:border-zinc-600'
                )}
                data-testid={`project-create-step-${step.id}`}
              >
                {isCompleted ? (
                  <CheckIcon className="h-5 w-5" />
                ) : (
                  <Icon className="h-5 w-5" />
                )}
              </div>
              <div className="ml-3">
                <p
                  className={cn(
                    'text-sm font-medium',
                    (isActive || isCompleted) &&
                      'text-zinc-900 dark:text-white',
                    !isActive &&
                      !isCompleted &&
                      'text-zinc-500 dark:text-zinc-400'
                  )}
                >
                  {step.name}
                </p>
                <p className="text-xs text-zinc-600 dark:text-zinc-400">
                  {step.description}
                </p>
              </div>
            </div>
            {index < steps.length - 1 && (
              <div
                className={cn(
                  'mx-4 h-0.5 flex-1',
                  isCompleted
                    ? 'bg-emerald-600'
                    : 'bg-zinc-300 dark:bg-zinc-700'
                )}
              />
            )}
          </React.Fragment>
        )
      })}
    </div>
  )

  const renderStep1 = () => (
    <div className="space-y-6">
      <div>
        <h2 className="mb-2 text-2xl font-semibold text-zinc-900 dark:text-white">
          {t('projects.creation.wizard.step1.title')}
        </h2>
        <p className="text-zinc-600 dark:text-zinc-400">
          {t('projects.creation.wizard.step1.subtitle')}
        </p>
      </div>

      <div className="space-y-4">
        <div>
          <Label htmlFor="title">
            {t('projects.creation.wizard.step1.projectName')}{' '}
            <span className="text-red-600 dark:text-red-400">*</span>
          </Label>
          <Input
            id="title"
            placeholder={t(
              'projects.creation.wizard.step1.projectNamePlaceholder'
            )}
            value={projectData.title}
            onChange={(e) =>
              setProjectData({ ...projectData, title: e.target.value })
            }
            className={cn(errors.title && 'border-red-500 dark:border-red-400')}
            data-testid="project-create-name-input"
          />
          {errors.title && (
            <p className="mt-1 text-sm text-red-600 dark:text-red-400">
              {errors.title}
            </p>
          )}
        </div>

        <div>
          <Label htmlFor="description">
            {t('projects.creation.wizard.step1.description')}
            <span className="ml-2 text-sm text-zinc-500 dark:text-zinc-400">
              {t('projects.creation.wizard.step1.optional')}
            </span>
          </Label>
          <Textarea
            id="description"
            placeholder={t(
              'projects.creation.wizard.step1.descriptionPlaceholder'
            )}
            value={projectData.description}
            onChange={(e) =>
              setProjectData({ ...projectData, description: e.target.value })
            }
            rows={4}
            data-testid="project-create-description-textarea"
          />
        </div>
      </div>
    </div>
  )

  const renderStep2 = () => (
    <div className="space-y-6">
      <div>
        <h2 className="mb-2 text-2xl font-semibold text-zinc-900 dark:text-white">
          {t('projects.creation.wizard.step2.title')}
        </h2>
        <p className="text-zinc-600 dark:text-zinc-400">
          {t('projects.creation.wizard.step2.subtitle')}
        </p>
      </div>

      <Tabs defaultValue="upload" data-testid="project-create-data-tabs">
        <TabsList className="grid w-full grid-cols-3">
          <TabsTrigger value="upload" data-testid="project-create-upload-tab">
            {t('projects.creation.wizard.step2.tabs.upload')}
          </TabsTrigger>
          <TabsTrigger value="paste" data-testid="project-create-paste-tab">
            {t('projects.creation.wizard.step2.tabs.paste')}
          </TabsTrigger>
          <TabsTrigger value="cloud" data-testid="project-create-cloud-tab">
            {t('projects.creation.wizard.step2.tabs.cloud')}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="upload" className="mt-6">
          <div
            className="cursor-pointer rounded-lg border border-dashed border-zinc-300 transition-colors hover:border-emerald-500 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:ring-offset-2 dark:border-zinc-700"
            onDrop={handleDrop}
            onDragOver={handleDragOver}
            onClick={() =>
              !selectedFile && document.getElementById('file-upload')?.click()
            }
            onKeyDown={(e) => {
              if ((e.key === 'Enter' || e.key === ' ') && !selectedFile) {
                e.preventDefault()
                document.getElementById('file-upload')?.click()
              }
            }}
            tabIndex={0}
            role="button"
            aria-label={t('projects.creation.wizard.step2.upload.dropzone')}
          >
            <div className="p-12 text-center">
              <CloudArrowUpIcon className="mx-auto mb-4 h-12 w-12 text-zinc-400 dark:text-zinc-500" />
              <p className="mb-2 text-lg font-medium">
                {t('projects.creation.wizard.step2.upload.dropzone')}
              </p>
              <p className="mb-4 text-sm text-zinc-600 dark:text-zinc-400">
                {t('projects.creation.wizard.step2.upload.supportedFormats')}
              </p>
              {selectedFile ? (
                <div className="mb-4">
                  <p className="text-sm text-emerald-600 dark:text-emerald-400">
                    {t('projects.creation.wizard.step2.upload.selectedFile', {
                      filename: selectedFile.name,
                    })}
                  </p>
                  <Button
                    variant="outline"
                    onClick={(e) => {
                      e.stopPropagation()
                      setSelectedFile(null)
                    }}
                    className="mt-2"
                    data-testid="project-create-remove-file-button"
                  >
                    {t('projects.creation.wizard.step2.upload.removeFile')}
                  </Button>
                </div>
              ) : (
                <Button
                  variant="outline"
                  onClick={(e) => {
                    e.stopPropagation()
                    document.getElementById('file-upload')?.click()
                  }}
                  data-testid="project-create-choose-files-button"
                >
                  {t('projects.creation.wizard.step2.upload.chooseFiles')}
                </Button>
              )}
              <input
                id="file-upload"
                type="file"
                accept=".json,.csv,.tsv,.txt"
                className="hidden"
                onChange={handleFileSelect}
                data-testid="project-create-file-input"
              />
            </div>
          </div>
        </TabsContent>

        <TabsContent value="paste" className="mt-6">
          <div className="space-y-4">
            <Label>{t('projects.creation.wizard.step2.paste.label')}</Label>
            <Textarea
              placeholder={t(
                'projects.creation.wizard.step2.paste.placeholder'
              )}
              rows={10}
              className="font-mono text-sm"
              value={pastedData}
              onChange={(e) => setPastedData(e.target.value)}
              data-testid="project-create-paste-data-textarea"
            />
            <div className="flex items-center justify-between">
              <div className="text-sm text-zinc-600 dark:text-zinc-400">
                {pastedData.trim()
                  ? t('projects.creation.wizard.step2.paste.lines', {
                      count: pastedData.trim().split('\n').length,
                    })
                  : t('projects.creation.wizard.step2.paste.noData')}
              </div>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  onClick={() => setPastedData('')}
                  disabled={!pastedData.trim()}
                  data-testid="project-create-clear-data-button"
                >
                  {t('projects.creation.wizard.step2.paste.clear')}
                </Button>
                <Button
                  variant="outline"
                  disabled={!pastedData.trim()}
                  data-testid="project-create-validate-data-button"
                  onClick={() => {
                    // Preview parsing
                    try {
                      const trimmed = pastedData.trim()
                      let format = 'txt'
                      if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
                        format = 'json'
                      } else if (trimmed.includes('\t')) {
                        format = 'tsv'
                      } else if (trimmed.includes(',')) {
                        format = 'csv'
                      }
                      toast.success(
                        t(
                          'projects.creation.wizard.step2.paste.formatDetected',
                          { format: format.toUpperCase() }
                        )
                      )
                    } catch (error) {
                      toast.error(
                        t('projects.creation.wizard.step2.paste.invalidFormat')
                      )
                    }
                  }}
                >
                  {t('projects.creation.wizard.step2.paste.validate')}
                </Button>
              </div>
            </div>
          </div>
        </TabsContent>

        <TabsContent value="cloud" className="mt-6">
          <Card>
            <div className="p-8 text-center">
              <p className="text-zinc-600 dark:text-zinc-400">
                {t('projects.creation.wizard.step2.cloud.comingSoon')}
              </p>
            </div>
          </Card>
        </TabsContent>
      </Tabs>

      <div className="rounded-lg bg-zinc-50 p-4 dark:bg-zinc-800/50">
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          <strong>{t('projects.wizard.note')}:</strong> {t('projects.creation.wizard.step2.note')}
        </p>
      </div>
    </div>
  )

  const renderStep3 = () => (
    <div className="space-y-6">
      <div>
        <h2 className="mb-2 text-2xl font-semibold text-zinc-900 dark:text-white">
          {t('projects.creation.wizard.step3.title')}
        </h2>
        <p className="text-zinc-600 dark:text-zinc-400">
          {t('projects.creation.wizard.step3.subtitle')}
        </p>
      </div>

      <Tabs
        defaultValue="templates"
        className="w-full"
        data-testid="project-create-labeling-tabs"
      >
        <TabsList className="grid w-full grid-cols-2">
          <TabsTrigger
            value="templates"
            data-testid="project-create-templates-tab"
          >
            {t('projects.creation.wizard.step3.tabs.templates')}
          </TabsTrigger>
          <TabsTrigger value="custom" data-testid="project-create-custom-tab">
            {t('projects.creation.wizard.step3.tabs.custom')}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="templates" className="mt-6">
          <div className="space-y-4">
            <div>
              <Label>
                {t('projects.creation.wizard.step3.templates.label')}
              </Label>
              <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
                {t('projects.creation.wizard.step3.templates.description')}
              </p>
            </div>

            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
              {nlpTemplates.map((template) => (
                <Card
                  key={template.id}
                  className={cn(
                    'cursor-pointer transition-colors hover:border-emerald-600',
                    projectData.labelingConfig?.id === template.id &&
                      'border-emerald-600 bg-emerald-50 dark:bg-emerald-900/20'
                  )}
                  onClick={() =>
                    setProjectData({
                      ...projectData,
                      labelingConfig: template,
                    })
                  }
                  data-testid={`project-create-template-${template.id}`}
                >
                  <div className="p-4">
                    <div className="mb-3 flex items-start gap-3">
                      <div className="text-2xl">{template.icon}</div>
                      <div className="flex-1">
                        <h4 className="mb-1 font-medium text-zinc-900 dark:text-white">
                          {template.name}
                        </h4>
                        <p className="text-sm text-zinc-600 dark:text-zinc-400">
                          {template.description}
                        </p>
                      </div>
                    </div>
                    {projectData.labelingConfig?.id === template.id && (
                      <div className="border-t border-emerald-200 pt-2 dark:border-emerald-800">
                        <Badge variant="default" className="text-xs">
                          {t(
                            'projects.creation.wizard.step3.templates.selected'
                          )}
                        </Badge>
                      </div>
                    )}
                  </div>
                </Card>
              ))}
            </div>
          </div>
        </TabsContent>

        <TabsContent value="custom" className="mt-6">
          <div className="space-y-4">
            <div>
              <Label>{t('projects.creation.wizard.step3.custom.label')}</Label>
              <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
                {t('projects.creation.wizard.step3.custom.description')}
              </p>
            </div>

            <Textarea
              placeholder={`<View>
  <Text name="text" value="$text"/>
  <Labels name="label" toName="text">
    <Label value="Category1" background="red"/>
    <Label value="Category2" background="blue"/>
  </Labels>
</View>`}
              rows={12}
              className="font-mono text-sm"
              value={projectData.labelingConfig?.config || ''}
              onChange={(e) =>
                setProjectData({
                  ...projectData,
                  labelingConfig: {
                    id: 'custom',
                    name: t('projects.wizard.customConfigName'),
                    description: t('projects.wizard.customConfigDescription'),
                    icon: '⚙️',
                    category: 'Custom',
                    config: e.target.value,
                  },
                })
              }
              data-testid="project-create-custom-config-textarea"
            />

            <div className="rounded-lg border border-blue-200 bg-blue-50 p-4 dark:border-blue-800 dark:bg-blue-900/20">
              <div className="flex items-start gap-3">
                <div className="text-blue-600 dark:text-blue-400">ℹ️</div>
                <div className="text-sm text-blue-800 dark:text-blue-200">
                  <p className="mb-1 font-medium">
                    {t('projects.creation.wizard.step3.custom.helpTitle')}
                  </p>
                  <p>
                    {t('projects.creation.wizard.step3.custom.helpText')}{' '}
                    <a
                      href="https://labelstud.io/tags/"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="underline hover:no-underline"
                    >
                      {t('projects.wizard.labelStudioDocs')}
                    </a>
                    .
                  </p>
                </div>
              </div>
            </div>
          </div>
        </TabsContent>
      </Tabs>

      {/* Preview */}
      {projectData.labelingConfig && (
        <div>
          <Label>{t('projects.creation.wizard.step3.preview.title')}</Label>
          <Card className="mt-2">
            <div className="p-4">
              <div className="mb-3 flex items-center gap-3">
                <span className="text-2xl">
                  {projectData.labelingConfig.icon}
                </span>
                <div>
                  <h4 className="font-medium text-zinc-900 dark:text-white">
                    {projectData.labelingConfig.name}
                  </h4>
                  <p className="text-sm text-zinc-600 dark:text-zinc-400">
                    {projectData.labelingConfig.description}
                  </p>
                </div>
              </div>
              <details className="group">
                <summary className="cursor-pointer text-sm font-medium text-zinc-700 hover:text-emerald-600 dark:text-zinc-300 dark:hover:text-emerald-400">
                  {t('projects.creation.wizard.step3.preview.viewXml')}
                </summary>
                <pre className="mt-2 overflow-x-auto rounded-md bg-zinc-100 p-3 text-xs text-zinc-800 dark:bg-zinc-800 dark:text-zinc-200">
                  {projectData.labelingConfig.config}
                </pre>
              </details>
            </div>
          </Card>
        </div>
      )}
    </div>
  )

  const renderCurrentStep = () => {
    switch (currentStep) {
      case 1:
        return renderStep1()
      case 2:
        return renderStep2()
      case 3:
        return renderStep3()
      default:
        return null
    }
  }

  return (
    <div className="mx-auto max-w-5xl">
      {/* Progress Indicator */}
      {renderStepIndicator()}

      {/* Step Content */}
      <Card className="mb-8">
        <div className="p-8">{renderCurrentStep()}</div>
      </Card>

      {/* Navigation */}
      <div className="flex justify-between">
        <Button
          variant="outline"
          onClick={
            currentStep === 1 ? () => router.push('/projects') : handleBack
          }
          disabled={loading}
          data-testid={
            currentStep === 1
              ? 'project-create-cancel-button'
              : 'project-create-back-button'
          }
        >
          <ArrowLeftIcon className="mr-2 h-4 w-4" />
          {currentStep === 1
            ? t('projects.creation.wizard.navigation.cancel')
            : t('projects.creation.wizard.navigation.back')}
        </Button>

        <div className="flex gap-3">
          {currentStep === 2 && (
            <Button
              variant="outline"
              onClick={() => setCurrentStep(3)}
              disabled={loading}
              data-testid="project-create-skip-data-button"
            >
              {t('projects.creation.wizard.navigation.skip')}
            </Button>
          )}

          {currentStep < steps.length ? (
            <Button
              onClick={handleNext}
              disabled={loading}
              data-testid="project-create-next-button"
            >
              {t('projects.creation.wizard.navigation.next')}
              <ArrowRightIcon className="ml-2 h-4 w-4" />
            </Button>
          ) : (
            <Button
              onClick={handleFinish}
              disabled={loading}
              data-testid="project-create-submit-button"
            >
              {loading
                ? t('projects.creation.wizard.navigation.creating')
                : t('projects.creation.wizard.navigation.create')}
            </Button>
          )}
        </div>
      </div>
    </div>
  )
}

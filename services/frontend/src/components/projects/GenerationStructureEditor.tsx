/**
 * Generation Structure Editor
 *
 * Editor for generation structure with template interpolation support
 * Issue #519: Support for system/instruction prompts with {{placeholder}} syntax
 */

import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Textarea } from '@/components/ui/textarea'
import { CheckIcon, EyeIcon, XMarkIcon } from '@heroicons/react/24/outline'
import { useMemo, useState } from 'react'
import { useI18n } from '@/contexts/I18nContext'

interface GenerationStructureEditorProps {
  initialConfig?: string
  onSave: (config: string) => void
  onCancel?: () => void
  onChange?: (config: string) => void // Called when config changes (for embedded usage)
  availableFields?: string[] // Available fields from task data
  showActionButtons?: boolean // Whether to show Save/Cancel buttons
}

const DEFAULT_TEMPLATES = {
  simple_qa: `{
  "system_prompt": "You are a helpful assistant. Answer questions accurately and concisely.",
  "instruction_prompt": "$question"
}`,

  template_qa: `{
  "system_prompt": {
    "template": "You are an expert assistant specializing in {{domain}}.",
    "fields": {
      "domain": "$metadata.domain"
    }
  },
  "instruction_prompt": {
    "template": "Question: {{question}}\\n\\nContext: {{context}}\\n\\nProvide a comprehensive answer.",
    "fields": {
      "question": "$question",
      "context": "$context"
    }
  }
}`,

  legal_analysis: `{
  "system_prompt": {
    "template": "You are a {{jurisdiction}} legal expert specializing in {{area_of_law}}.",
    "fields": {
      "jurisdiction": "$context.jurisdiction",
      "area_of_law": "$area"
    }
  },
  "instruction_prompt": {
    "template": "Analyze the following legal question:\\n\\n{{question}}\\n\\nRelevant statutes: {{references}}\\n\\nProvide detailed legal analysis.",
    "fields": {
      "question": "$prompts.prompt_clean",
      "references": "$context.references"
    }
  },
  "exclude_fields": ["annotations", "ground_truth"]
}`,

  classification: `{
  "system_prompt": "You are a text classification expert. Classify texts accurately based on their content.",
  "instruction_prompt": {
    "template": "Classify the following text into one of these categories: {{categories}}\\n\\nText: {{text}}\\n\\nProvide your classification and reasoning.",
    "fields": {
      "text": "$text",
      "categories": "$metadata.categories"
    }
  }
}`,

  nested_data: `{
  "system_prompt": "$prompts.system",
  "instruction_prompt": "$prompts.instruction",
  "context_fields": ["$context.jurisdiction", "$context.legal_system"],
  "parameters": {
    "temperature": 0.7,
    "max_tokens": 1500
  }
}`,

  multi_field_combo: `{
  "system_prompt": "You are a legal expert. Provide clear and accurate legal analysis.",
  "instruction_prompt": {
    "template": "{{prompt}}\\n\\n{{case}}",
    "fields": {
      "prompt": "$prompt_clean",
      "case": "$fall"
    }
  }
}`,
}

export function GenerationStructureEditor({
  initialConfig = '',
  onSave,
  onCancel,
  onChange,
  availableFields = [],
  showActionButtons = true,
}: GenerationStructureEditorProps) {
  const { t } = useI18n()
  const [config, setConfig] = useState(initialConfig)
  const [selectedTemplate, setSelectedTemplate] = useState<string>('')
  const [showPreview, setShowPreview] = useState(false)

  // Derive error and previewData from config using useMemo (pure validation)
  const { error, previewData } = useMemo<{ error: string | null; previewData: any }>(() => {
    if (!config.trim()) {
      return { error: t('projects.generationStructure.errorEmpty'), previewData: null }
    }

    try {
      const parsed = JSON.parse(config)

      // Check for at least one prompt definition
      const hasPrompts =
        parsed.system_prompt || parsed.instruction_prompt || parsed.fields
      if (!hasPrompts) {
        return {
          error: t('projects.generationStructure.errorMissingPrompt'),
          previewData: null,
        }
      }

      // Validate prompt structures if they're objects
      if (parsed.system_prompt && typeof parsed.system_prompt === 'object') {
        if (!parsed.system_prompt.template) {
          return { error: t('projects.generationStructure.errorSystemPromptTemplate'), previewData: null }
        }
        if (
          parsed.system_prompt.fields &&
          typeof parsed.system_prompt.fields !== 'object'
        ) {
          return { error: t('projects.generationStructure.errorSystemPromptFields'), previewData: null }
        }
      }

      if (
        parsed.instruction_prompt &&
        typeof parsed.instruction_prompt === 'object'
      ) {
        if (!parsed.instruction_prompt.template) {
          return { error: t('projects.generationStructure.errorInstructionPromptTemplate'), previewData: null }
        }
        if (
          parsed.instruction_prompt.fields &&
          typeof parsed.instruction_prompt.fields !== 'object'
        ) {
          return { error: t('projects.generationStructure.errorInstructionPromptFields'), previewData: null }
        }
      }

      // Validate exclude_fields if present
      if (parsed.exclude_fields && !Array.isArray(parsed.exclude_fields)) {
        return { error: t('projects.generationStructure.errorExcludeFieldsArray'), previewData: null }
      }

      // Validate parameters if present
      if (parsed.parameters && typeof parsed.parameters !== 'object') {
        return { error: t('projects.generationStructure.errorParametersObject'), previewData: null }
      }

      return { error: null, previewData: parsed }
    } catch (e) {
      return { error: t('projects.generationStructure.errorInvalidJson') + (e as Error).message, previewData: null }
    }
  }, [config, t])

  const handleSave = () => {
    if (!error) {
      onSave(config)
    }
  }

  const handleTemplateSelect = (templateKey: string) => {
    if (
      templateKey &&
      DEFAULT_TEMPLATES[templateKey as keyof typeof DEFAULT_TEMPLATES]
    ) {
      const newConfig =
        DEFAULT_TEMPLATES[templateKey as keyof typeof DEFAULT_TEMPLATES]
      setConfig(newConfig)
      setSelectedTemplate(templateKey)
      if (onChange) {
        onChange(newConfig)
      }
    }
  }

  // Extract field references from the config
  const extractFieldReferences = (obj: any): string[] => {
    const refs: string[] = []

    const extract = (value: any) => {
      if (typeof value === 'string' && value.startsWith('$')) {
        refs.push(value.substring(1))
      } else if (typeof value === 'object' && value !== null) {
        Object.values(value).forEach(extract)
      }
    }

    extract(obj)
    return refs
  }

  // Generate preview of how the prompts would look
  const generatePreview = () => {
    if (!previewData) return null

    const usedFields = extractFieldReferences(previewData)

    return (
      <Card className="mt-4">
        <CardHeader>
          <CardTitle className="text-sm">{t('projects.generationStructure.previewTitle')}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          {previewData.system_prompt && (
            <div>
              <strong>{t('projects.generationStructure.systemPromptLabel')}</strong>
              <div className="mt-1 rounded bg-zinc-100 p-2 dark:bg-zinc-800">
                {typeof previewData.system_prompt === 'string'
                  ? previewData.system_prompt.startsWith('$')
                    ? t('projects.generationStructure.willUseField', { field: previewData.system_prompt.substring(1) })
                    : previewData.system_prompt
                  : t('projects.generationStructure.templateWithPlaceholders') +
                    (
                      previewData.system_prompt.template?.match(/{{(\w+)}}/g) ||
                      []
                    ).join(', ')}
              </div>
            </div>
          )}

          {previewData.instruction_prompt && (
            <div>
              <strong>{t('projects.generationStructure.instructionPromptLabel')}</strong>
              <div className="mt-1 rounded bg-zinc-100 p-2 dark:bg-zinc-800">
                {typeof previewData.instruction_prompt === 'string'
                  ? previewData.instruction_prompt.startsWith('$')
                    ? t('projects.generationStructure.willUseField', { field: previewData.instruction_prompt.substring(1) })
                    : previewData.instruction_prompt
                  : t('projects.generationStructure.templateWithPlaceholders') +
                    (
                      previewData.instruction_prompt.template?.match(
                        /{{(\w+)}}/g
                      ) || []
                    ).join(', ')}
              </div>
            </div>
          )}

          {usedFields.length > 0 && (
            <div>
              <strong>{t('projects.generationStructure.referencedFields')}</strong>
              <div className="mt-1 flex flex-wrap gap-1">
                {usedFields.map((field, i) => (
                  <span
                    key={i}
                    className="rounded bg-blue-100 px-2 py-1 text-xs dark:bg-blue-900"
                  >
                    {field}
                  </span>
                ))}
              </div>
            </div>
          )}

          {previewData.exclude_fields && (
            <div>
              <strong>{t('projects.generationStructure.excludedFields')}</strong>
              <div className="mt-1 flex flex-wrap gap-1">
                {previewData.exclude_fields.map((field: string, i: number) => (
                  <span
                    key={i}
                    className="rounded bg-red-100 px-2 py-1 text-xs dark:bg-red-900"
                  >
                    {field}
                  </span>
                ))}
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="space-y-4">
      {/* Template Selection */}
      <Card>
        <CardHeader>
          <CardTitle>{t('projects.generationStructure.templatesTitle')}</CardTitle>
          <CardDescription>
            {t('projects.generationStructure.templatesDescription')}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 gap-2 md:grid-cols-2 lg:grid-cols-3">
            <Button
              variant={selectedTemplate === 'simple_qa' ? 'default' : 'outline'}
              onClick={() => handleTemplateSelect('simple_qa')}
              className="justify-start text-left"
            >
              <div>
                <div>{t('projects.generationStructure.templateSimpleQA')}</div>
                <div className="text-xs opacity-70">{t('projects.generationStructure.templateSimpleQADesc')}</div>
              </div>
            </Button>
            <Button
              variant={
                selectedTemplate === 'template_qa' ? 'default' : 'outline'
              }
              onClick={() => handleTemplateSelect('template_qa')}
              className="justify-start text-left"
            >
              <div>
                <div>{t('projects.generationStructure.templateTemplateQA')}</div>
                <div className="text-xs opacity-70">
                  {t('projects.generationStructure.templateTemplateQADesc')}
                </div>
              </div>
            </Button>
            <Button
              variant={
                selectedTemplate === 'legal_analysis' ? 'default' : 'outline'
              }
              onClick={() => handleTemplateSelect('legal_analysis')}
              className="justify-start text-left"
            >
              <div>
                <div>{t('projects.generationStructure.templateLegalAnalysis')}</div>
                <div className="text-xs opacity-70">{t('projects.generationStructure.templateLegalAnalysisDesc')}</div>
              </div>
            </Button>
            <Button
              variant={
                selectedTemplate === 'classification' ? 'default' : 'outline'
              }
              onClick={() => handleTemplateSelect('classification')}
              className="justify-start text-left"
            >
              <div>
                <div>{t('projects.generationStructure.templateClassification')}</div>
                <div className="text-xs opacity-70">{t('projects.generationStructure.templateClassificationDesc')}</div>
              </div>
            </Button>
            <Button
              variant={
                selectedTemplate === 'nested_data' ? 'default' : 'outline'
              }
              onClick={() => handleTemplateSelect('nested_data')}
              className="justify-start text-left"
            >
              <div>
                <div>{t('projects.generationStructure.templateNestedData')}</div>
                <div className="text-xs opacity-70">{t('projects.generationStructure.templateNestedDataDesc')}</div>
              </div>
            </Button>
            <Button
              variant={
                selectedTemplate === 'multi_field_combo' ? 'default' : 'outline'
              }
              onClick={() => handleTemplateSelect('multi_field_combo')}
              className="justify-start text-left"
            >
              <div>
                <div>{t('projects.generationStructure.templateMultiFieldCombo')}</div>
                <div className="text-xs opacity-70">
                  {t('projects.generationStructure.templateMultiFieldComboDesc')}
                </div>
              </div>
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Configuration Editor */}
      <Card>
        <CardHeader>
          <CardTitle>{t('projects.generationStructure.configTitle')}</CardTitle>
          <CardDescription>
            {t('projects.generationStructure.configDescription')}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <span className="text-sm text-zinc-500">
              {t('projects.generationStructure.editorHint')}
            </span>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setShowPreview(!showPreview)}
            >
              <EyeIcon className="mr-2 h-4 w-4" />
              {showPreview ? t('projects.generationStructure.hidePreview') : t('projects.generationStructure.showPreview')}
            </Button>
          </div>

          <Textarea
            value={config}
            onChange={(e) => {
              const newConfig = e.target.value
              setConfig(newConfig)
              if (onChange) {
                onChange(newConfig)
              }
            }}
            placeholder={t('projects.generationStructure.placeholder')}
            className="font-mono text-sm"
            rows={20}
          />

          {error && (
            <Alert variant="destructive">
              <XMarkIcon className="h-4 w-4" />
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          {!error && config && (
            <Alert>
              <CheckIcon className="h-4 w-4" />
              <AlertDescription>{t('projects.generationStructure.valid')}</AlertDescription>
            </Alert>
          )}

          {showPreview && generatePreview()}

          {showActionButtons && (
            <div className="flex justify-end gap-2">
              {onCancel && (
                <Button variant="outline" onClick={onCancel}>
                  {t('common.cancel')}
                </Button>
              )}
              <Button onClick={handleSave} disabled={!config || !!error}>
                {t('projects.generationStructure.saveButton')}
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Documentation */}
      <Card>
        <CardHeader>
          <CardTitle>{t('projects.generationStructure.docTitle')}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="text-sm text-zinc-600 dark:text-zinc-400">
            <p className="mb-2">
              <strong>{t('projects.generationStructure.docPromptFields')}</strong>
            </p>
            <ul className="ml-4 space-y-2">
              <li>
                <code>system_prompt</code>: {t('projects.generationStructure.docSystemPromptDesc')}
                <ul className="ml-4 mt-1 text-xs">
                  <li>{t('projects.generationStructure.docStringOption')}</li>
                  <li>
                    {t('projects.generationStructure.docObjectOption')}
                  </li>
                </ul>
              </li>
              <li>
                <code>instruction_prompt</code>: {t('projects.generationStructure.docInstructionPromptDesc')}
                <ul className="ml-4 mt-1 text-xs">
                  <li>{t('projects.generationStructure.docStringOption')}</li>
                  <li>
                    {t('projects.generationStructure.docObjectOption')}
                  </li>
                </ul>
              </li>
            </ul>

            <p className="mb-2 mt-4">
              <strong>{t('projects.generationStructure.docFieldReferences')}</strong>
            </p>
            <ul className="ml-4 space-y-1">
              <li>
                <code>$field</code>: {t('projects.generationStructure.docSimpleFieldRef')}
              </li>
              <li>
                <code>$parent.child</code>: {t('projects.generationStructure.docNestedFieldRef')}
              </li>
              <li>
                <code>$items[0].name</code>: {t('projects.generationStructure.docArrayAccessRef')}
              </li>
            </ul>

            <p className="mb-2 mt-4">
              <strong>{t('projects.generationStructure.docTemplateSyntax')}</strong>
            </p>
            <ul className="ml-4 space-y-1">
              <li>
                <code>{'{{placeholder}}'}</code>: {t('projects.generationStructure.docTemplateVariable')}
              </li>
              <li>
                {t('projects.generationStructure.docFieldsMapping')}
              </li>
            </ul>

            <p className="mb-2 mt-4">
              <strong>{t('projects.generationStructure.docOptionalFields')}</strong>
            </p>
            <ul className="ml-4 space-y-1">
              <li>
                <code>context_fields</code>: {t('projects.generationStructure.docContextFields')}
              </li>
              <li>
                <code>exclude_fields</code>: {t('projects.generationStructure.docExcludeFields')}
              </li>
              <li>
                <code>parameters</code>: {t('projects.generationStructure.docParameters')}
              </li>
            </ul>

            <p className="mb-2 mt-4">
              <strong>{t('projects.generationStructure.docSecurityNote')}</strong>
            </p>
            <p className="ml-4 text-xs">
              {t('projects.generationStructure.docSecurityNoteText')}
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

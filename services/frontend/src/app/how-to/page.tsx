'use client'

import { HowToSection } from '@/components/howto'
import { HeroPattern } from '@/components/shared'
import { useI18n } from '@/contexts/I18nContext'

export default function HowToPage() {
  const { t } = useI18n()

  return (
    <>
      <HeroPattern />

      <div className="container mx-auto max-w-5xl px-6 pb-16 pt-16">
        <h1 className="text-4xl font-bold tracking-tight text-zinc-900 dark:text-white">
          {t('howTo.title')}
        </h1>
        <p className="mt-6 text-lg text-zinc-600 dark:text-zinc-400">
          {t('howTo.subtitle')}
        </p>

        <div className="mt-16 space-y-20">
          {/* Platform Overview */}
          <HowToSection
            title={t('howTo.sections.platformOverview.title')}
            id="platform-overview"
          >
            <div className="space-y-12">
              <p>{t('howTo.sections.platformOverview.description')}</p>

              <div>
                <h3 className="mb-4 text-xl font-semibold text-zinc-900 dark:text-white">
                  {t('howTo.sections.platformOverview.workflow.title')}
                </h3>
                <p className="mb-6">
                  {t('howTo.sections.platformOverview.workflow.description')}
                </p>
                <ol className="list-inside list-decimal space-y-4">
                  {(['step1', 'step2', 'step3', 'step4', 'step5', 'step6'] as const).map((step) => (
                    <li key={step}>
                      <span className="font-medium">
                        {t(`howTo.sections.platformOverview.workflow.${step}.title`)}
                      </span>
                      <p className="ml-6 mt-1 text-zinc-600 dark:text-zinc-400">
                        {t(`howTo.sections.platformOverview.workflow.${step}.description`)}
                      </p>
                    </li>
                  ))}
                </ol>
              </div>

              <div>
                <h3 className="mb-4 text-xl font-semibold text-zinc-900 dark:text-white">
                  {t('howTo.sections.platformOverview.navigation.title')}
                </h3>
                <p className="mb-6">
                  {t('howTo.sections.platformOverview.navigation.description')}
                </p>
                <div className="space-y-3">
                  {(['quickStart', 'projectsAndData', 'knowledge'] as const).map((group) => (
                    <div
                      key={group}
                      className="rounded-lg border border-zinc-200 p-4 dark:border-zinc-700"
                    >
                      <h4 className="font-semibold text-zinc-900 dark:text-white">
                        {t(`howTo.sections.platformOverview.navigation.${group}.title`)}
                      </h4>
                      <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
                        {t(`howTo.sections.platformOverview.navigation.${group}.description`)}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </HowToSection>

          {/* Projects */}
          <HowToSection
            title={t('howTo.sections.projects.title')}
            id="projects"
          >
            <div className="space-y-12">
              <div>
                <h3
                  id="creating-projects"
                  className="mb-4 text-xl font-semibold text-zinc-900 dark:text-white"
                >
                  {t('howTo.sections.projects.creating.title')}
                </h3>
                <p className="mb-6">
                  {t('howTo.sections.projects.creating.description')}
                </p>
                <ol className="list-inside list-decimal space-y-4">
                  {(['step1', 'step2', 'step3'] as const).map((step) => (
                    <li key={step}>
                      <span className="font-medium">
                        {t(`howTo.sections.projects.creating.${step}.title`)}
                      </span>
                      <p className="ml-6 mt-1 text-zinc-600 dark:text-zinc-400">
                        {t(`howTo.sections.projects.creating.${step}.description`)}
                      </p>
                    </li>
                  ))}
                </ol>
              </div>

              <div>
                <h3 className="mb-4 text-xl font-semibold text-zinc-900 dark:text-white">
                  {t('howTo.sections.projects.templates.title')}
                </h3>
                <div className="grid gap-4 md:grid-cols-2">
                  {(['qa', 'multipleChoice', 'examSolving', 'spanAnnotation'] as const).map(
                    (tmpl) => (
                      <div
                        key={tmpl}
                        className="rounded-lg border border-zinc-200 p-4 dark:border-zinc-700"
                      >
                        <h4 className="font-semibold text-emerald-600 dark:text-emerald-400">
                          {t(`howTo.sections.projects.templates.${tmpl}.title`)}
                        </h4>
                        <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
                          {t(`howTo.sections.projects.templates.${tmpl}.description`)}
                        </p>
                      </div>
                    )
                  )}
                </div>
              </div>

              <div>
                <h3 className="mb-4 text-xl font-semibold text-zinc-900 dark:text-white">
                  {t('howTo.sections.projects.projectPage.title')}
                </h3>
                <p>{t('howTo.sections.projects.projectPage.description')}</p>
              </div>
            </div>
          </HowToSection>

          {/* Data Import */}
          <HowToSection
            title={t('howTo.sections.dataImport.title')}
            id="data-import"
          >
            <div className="space-y-8">
              <div>
                <h3 className="mb-4 text-xl font-semibold text-zinc-900 dark:text-white">
                  {t('howTo.sections.dataImport.formats.title')}
                </h3>
                <p className="mb-6">
                  {t('howTo.sections.dataImport.formats.description')}
                </p>
                <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                  {(['json', 'csv', 'tsv', 'txt'] as const).map((fmt) => (
                    <div
                      key={fmt}
                      className="rounded-lg border border-zinc-200 p-4 dark:border-zinc-700"
                    >
                      <h4 className="font-semibold text-emerald-600 dark:text-emerald-400">
                        {t(`howTo.sections.dataImport.formats.${fmt}.title`)}
                      </h4>
                      <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
                        {t(`howTo.sections.dataImport.formats.${fmt}.description`)}
                      </p>
                    </div>
                  ))}
                </div>
              </div>

              <div>
                <h3 className="mb-4 text-xl font-semibold text-zinc-900 dark:text-white">
                  {t('howTo.sections.dataImport.methods.title')}
                </h3>
                <ul className="list-inside list-disc space-y-3">
                  <li>{t('howTo.sections.dataImport.methods.upload')}</li>
                  <li>{t('howTo.sections.dataImport.methods.paste')}</li>
                </ul>
              </div>

              <div>
                <h3 className="mb-4 text-xl font-semibold text-zinc-900 dark:text-white">
                  {t('howTo.sections.dataImport.structure.title')}
                </h3>
                <p>{t('howTo.sections.dataImport.structure.description')}</p>
              </div>
            </div>
          </HowToSection>

          {/* Annotation */}
          <HowToSection
            title={t('howTo.sections.annotation.title')}
            id="annotation"
          >
            <div className="space-y-8">
              <div>
                <h3 className="mb-4 text-xl font-semibold text-zinc-900 dark:text-white">
                  {t('howTo.sections.annotation.interface.title')}
                </h3>
                <p className="mb-4">
                  {t('howTo.sections.annotation.interface.description')}
                </p>
                <ul className="list-inside list-disc space-y-3">
                  <li>{t('howTo.sections.annotation.interface.navigation')}</li>
                  <li>{t('howTo.sections.annotation.interface.timer')}</li>
                  <li>{t('howTo.sections.annotation.interface.skip')}</li>
                </ul>
              </div>

              <div>
                <h3 className="mb-4 text-xl font-semibold text-zinc-900 dark:text-white">
                  {t('howTo.sections.annotation.labelConfig.title')}
                </h3>
                <p className="mb-6">
                  {t('howTo.sections.annotation.labelConfig.description')}
                </p>

                <div className="rounded-lg bg-zinc-900 p-6 dark:bg-zinc-950">
                  <p className="mb-3 text-sm font-medium text-zinc-300">
                    {t('howTo.sections.annotation.labelConfig.example')}
                  </p>
                  <pre className="overflow-x-auto text-sm text-zinc-100">
                    <code>{`<View>
  <Text name="text" value="$text"/>
  <TextArea name="answer"
    toName="text"
    placeholder="Enter your answer..."
    rows="4"/>
</View>`}</code>
                  </pre>
                </div>

                <div className="mt-6">
                  <h4 className="mb-3 font-semibold text-zinc-900 dark:text-white">
                    {t('howTo.sections.annotation.labelConfig.tags.title')}
                  </h4>
                  <div className="space-y-2">
                    {(['text', 'textarea', 'choices', 'labels'] as const).map((tag) => (
                      <div
                        key={tag}
                        className="rounded-lg border border-zinc-200 p-3 dark:border-zinc-700"
                      >
                        <p className="text-sm text-zinc-700 dark:text-zinc-300">
                          <code className="mr-2 rounded bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-300">
                            {`<${tag.charAt(0).toUpperCase() + tag.slice(1)}>`}
                          </code>
                          {t(`howTo.sections.annotation.labelConfig.tags.${tag}`).split(' - ').slice(1).join(' - ')}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </HowToSection>

          {/* Generation */}
          <HowToSection
            title={t('howTo.sections.generation.title')}
            id="generation"
          >
            <div className="space-y-8">
              <div>
                <h3
                  id="api-keys"
                  className="mb-4 text-xl font-semibold text-zinc-900 dark:text-white"
                >
                  {t('howTo.sections.generation.apiKeys.title')}
                </h3>
                <p className="mb-4">
                  {t('howTo.sections.generation.apiKeys.description')}
                </p>
                <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 dark:border-amber-800 dark:bg-amber-950">
                  <p className="text-sm text-amber-700 dark:text-amber-300">
                    {t('howTo.sections.generation.apiKeys.note')}
                  </p>
                </div>
              </div>

              <div>
                <h3 className="mb-4 text-xl font-semibold text-zinc-900 dark:text-white">
                  {t('howTo.sections.generation.providers.title')}
                </h3>
                <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4">
                  {(['openai', 'anthropic', 'google', 'deepinfra', 'mistral', 'cohere', 'grok'] as const).map(
                    (provider) => (
                      <div
                        key={provider}
                        className="rounded-lg border border-zinc-200 p-3 text-center dark:border-zinc-700"
                      >
                        <p className="text-sm text-zinc-700 dark:text-zinc-300">
                          {t(`howTo.sections.generation.providers.${provider}`)}
                        </p>
                      </div>
                    )
                  )}
                </div>
              </div>

              <div>
                <h3 className="mb-4 text-xl font-semibold text-zinc-900 dark:text-white">
                  {t('howTo.sections.generation.running.title')}
                </h3>
                <p className="mb-4">
                  {t('howTo.sections.generation.running.description')}
                </p>
                <ol className="list-inside list-decimal space-y-3">
                  {(['step1', 'step2', 'step3', 'step4', 'step5'] as const).map((step) => (
                    <li key={step} className="text-zinc-700 dark:text-zinc-300">
                      {t(`howTo.sections.generation.running.${step}`)}
                    </li>
                  ))}
                </ol>
              </div>

              {/* Prompt Structure - kept from original, accurate content */}
              <div>
                <h3
                  id="prompt-structure"
                  className="mb-4 text-xl font-semibold text-zinc-900 dark:text-white"
                >
                  {t('howTo.sections.generation.promptStructure.title')}
                </h3>
                <p className="mb-6">
                  {t('howTo.sections.generation.promptStructure.description')}
                </p>

                <div className="space-y-6">
                  <div>
                    <h4 className="mb-3 font-semibold text-zinc-900 dark:text-white">
                      {t('howTo.sections.generation.promptStructure.basicFormat.title')}
                    </h4>
                    <p className="mb-4 text-sm text-zinc-600 dark:text-zinc-400">
                      {t('howTo.sections.generation.promptStructure.basicFormat.description')}
                    </p>
                    <div className="rounded-lg bg-zinc-900 p-6 dark:bg-zinc-950">
                      <p className="mb-3 text-sm font-medium text-zinc-300">
                        {t('howTo.sections.generation.promptStructure.basicFormat.codeLabel')}
                      </p>
                      <pre className="overflow-x-auto text-sm text-zinc-100">
                        <code>{`{
  "system_prompt": "You are a helpful assistant. Answer questions accurately.",
  "instruction_prompt": {
    "template": "{{prompt_clean}} Case: {{fall}}",
    "fields": {
      "prompt_clean": "$prompt_clean",
      "fall": "$fall"
    }
  }
}`}</code>
                      </pre>
                    </div>
                  </div>

                  <div>
                    <h4 className="mb-3 font-semibold text-zinc-900 dark:text-white">
                      {t('howTo.sections.generation.promptStructure.fieldMapping.title')}
                    </h4>
                    <p className="mb-4 text-sm text-zinc-600 dark:text-zinc-400">
                      {t('howTo.sections.generation.promptStructure.fieldMapping.description')}
                    </p>
                    <ul className="mb-4 list-inside list-disc space-y-2 text-sm text-zinc-600 dark:text-zinc-400">
                      <li>
                        <strong>
                          {t('howTo.sections.generation.promptStructure.fieldMapping.placeholder.label')}
                        </strong>
                        :{' '}
                        {t('howTo.sections.generation.promptStructure.fieldMapping.placeholder.description')}
                      </li>
                      <li>
                        <strong>
                          {t('howTo.sections.generation.promptStructure.fieldMapping.fieldPath.label')}
                        </strong>
                        :{' '}
                        {t('howTo.sections.generation.promptStructure.fieldMapping.fieldPath.description')}
                      </li>
                      <li>
                        {t('howTo.sections.generation.promptStructure.fieldMapping.nested')}
                      </li>
                    </ul>
                  </div>

                  <div>
                    <h4 className="mb-3 font-semibold text-zinc-900 dark:text-white">
                      {t('howTo.sections.generation.promptStructure.completeExample.title')}
                    </h4>
                    <p className="mb-4 text-sm text-zinc-600 dark:text-zinc-400">
                      {t('howTo.sections.generation.promptStructure.completeExample.description')}
                    </p>
                    <div className="rounded-lg bg-zinc-900 p-6 dark:bg-zinc-950">
                      <p className="mb-3 text-sm font-medium text-zinc-300">
                        {t('howTo.sections.generation.promptStructure.completeExample.codeLabel')}
                      </p>
                      <pre className="overflow-x-auto text-sm text-zinc-100">
                        <code>{`{
  "system_prompt": "You are a legal expert. Analyze cases using German civil law.",
  "instruction_prompt": {
    "template": "{{instructions}}\\n\\nCase:\\n{{case_facts}}\\n\\nQuestion: {{question}}",
    "fields": {
      "instructions": "$prompt_clean",
      "case_facts": "$fall",
      "question": "$task"
    }
  }
}`}</code>
                      </pre>
                    </div>
                    <p className="mt-4 text-sm text-zinc-600 dark:text-zinc-400">
                      {t('howTo.sections.generation.promptStructure.completeExample.explanation')}
                    </p>
                  </div>

                  <div className="rounded-lg border border-red-200 bg-red-50 p-4 dark:border-red-800 dark:bg-red-950">
                    <p className="text-sm font-medium text-red-900 dark:text-red-100">
                      {t('howTo.sections.generation.promptStructure.commonMistakes.title')}
                    </p>
                    <div className="mt-3 space-y-3 text-sm text-red-700 dark:text-red-300">
                      <div>
                        <strong>
                          {t('howTo.sections.generation.promptStructure.commonMistakes.mistake1.label')}
                        </strong>{' '}
                        {t('howTo.sections.generation.promptStructure.commonMistakes.mistake1.description')}
                        <pre className="mt-1 overflow-x-auto rounded bg-red-900/20 p-2 text-xs">
                          <code>{`"instruction_prompt": "{{prompt}} Case: {{fall}}"`}</code>
                        </pre>
                        <p className="mt-1 text-xs">
                          {t('howTo.sections.generation.promptStructure.commonMistakes.mistake1.explanation')}
                        </p>
                      </div>
                      <div>
                        <strong>
                          {t('howTo.sections.generation.promptStructure.commonMistakes.mistake2.label')}
                        </strong>{' '}
                        {t('howTo.sections.generation.promptStructure.commonMistakes.mistake2.description')}
                        <pre className="mt-1 overflow-x-auto rounded bg-red-900/20 p-2 text-xs">
                          <code>{`"fields": {
  "prompt": "prompt_clean"  // Missing $
}`}</code>
                        </pre>
                      </div>
                      <div>
                        <strong>
                          {t('howTo.sections.generation.promptStructure.commonMistakes.correct.label')}
                        </strong>{' '}
                        {t('howTo.sections.generation.promptStructure.commonMistakes.correct.description')}
                        <pre className="mt-1 overflow-x-auto rounded bg-emerald-900/20 p-2 text-xs">
                          <code>{`"instruction_prompt": {
  "template": "{{prompt}} Case: {{fall}}",
  "fields": {
    "prompt": "$prompt_clean",
    "fall": "$fall"
  }
}`}</code>
                        </pre>
                      </div>
                    </div>
                  </div>

                  <div className="rounded-lg border border-blue-200 bg-blue-50 p-4 dark:border-blue-800 dark:bg-blue-950">
                    <p className="text-sm font-medium text-blue-900 dark:text-blue-100">
                      {t('howTo.sections.generation.promptStructure.bestPractices.title')}
                    </p>
                    <ul className="mt-2 list-inside list-disc space-y-1 text-sm text-blue-700 dark:text-blue-300">
                      {(['practice1', 'practice2', 'practice3', 'practice4', 'practice5'] as const).map(
                        (p) => (
                          <li key={p}>
                            {t(`howTo.sections.generation.promptStructure.bestPractices.${p}`)}
                          </li>
                        )
                      )}
                    </ul>
                  </div>
                </div>
              </div>

              <div>
                <h3 className="mb-4 text-xl font-semibold text-zinc-900 dark:text-white">
                  {t('howTo.sections.generation.reasoning.title')}
                </h3>
                <p className="mb-4">
                  {t('howTo.sections.generation.reasoning.description')}
                </p>
                <ul className="list-inside list-disc space-y-2 text-sm text-zinc-600 dark:text-zinc-400">
                  <li>{t('howTo.sections.generation.reasoning.openai')}</li>
                  <li>{t('howTo.sections.generation.reasoning.anthropic')}</li>
                  <li>{t('howTo.sections.generation.reasoning.google')}</li>
                  <li>{t('howTo.sections.generation.reasoning.qwen')}</li>
                </ul>
              </div>

              <div>
                <h3 className="mb-4 text-xl font-semibold text-zinc-900 dark:text-white">
                  {t('howTo.sections.generation.monitoring.title')}
                </h3>
                <p>{t('howTo.sections.generation.monitoring.description')}</p>
              </div>
            </div>
          </HowToSection>

          {/* Evaluation */}
          <HowToSection
            title={t('howTo.sections.evaluation.title')}
            id="evaluation"
          >
            <div className="space-y-8">
              <div>
                <h3 className="mb-4 text-xl font-semibold text-zinc-900 dark:text-white">
                  {t('howTo.sections.evaluation.overview.title')}
                </h3>
                <p>{t('howTo.sections.evaluation.overview.description')}</p>
              </div>

              <div>
                <h3 className="mb-4 text-xl font-semibold text-zinc-900 dark:text-white">
                  {t('howTo.sections.evaluation.types.title')}
                </h3>
                <div className="space-y-3">
                  {(['automated', 'llmJudge', 'human'] as const).map((type) => (
                    <div
                      key={type}
                      className="rounded-lg border border-zinc-200 p-4 dark:border-zinc-700"
                    >
                      <h4 className="font-semibold text-zinc-900 dark:text-white">
                        {t(`howTo.sections.evaluation.types.${type}.title`)}
                      </h4>
                      <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
                        {t(`howTo.sections.evaluation.types.${type}.description`)}
                      </p>
                    </div>
                  ))}
                </div>
              </div>

              <div>
                <h3 className="mb-4 text-xl font-semibold text-zinc-900 dark:text-white">
                  {t('howTo.sections.evaluation.configuring.title')}
                </h3>
                <p className="mb-4">
                  {t('howTo.sections.evaluation.configuring.description')}
                </p>
                <ol className="list-inside list-decimal space-y-3">
                  {(['step1', 'step2', 'step3'] as const).map((step) => (
                    <li key={step} className="text-zinc-700 dark:text-zinc-300">
                      {t(`howTo.sections.evaluation.configuring.${step}`)}
                    </li>
                  ))}
                </ol>
              </div>

              <div>
                <h3 className="mb-4 text-xl font-semibold text-zinc-900 dark:text-white">
                  {t('howTo.sections.evaluation.results.title')}
                </h3>
                <p className="mb-4">
                  {t('howTo.sections.evaluation.results.description')}
                </p>
                <ul className="list-inside list-disc space-y-2 text-zinc-600 dark:text-zinc-400">
                  <li>{t('howTo.sections.evaluation.results.table')}</li>
                  <li>{t('howTo.sections.evaluation.results.chart')}</li>
                  <li>{t('howTo.sections.evaluation.results.statistics')}</li>
                </ul>
              </div>

              <div>
                <h3 className="mb-4 text-xl font-semibold text-zinc-900 dark:text-white">
                  {t('howTo.sections.evaluation.evaluationPage.title')}
                </h3>
                <p>{t('howTo.sections.evaluation.evaluationPage.description')}</p>
              </div>
            </div>
          </HowToSection>

          {/* Organizations & Roles */}
          <HowToSection
            title={t('howTo.sections.organizations.title')}
            id="organizations"
          >
            <div className="space-y-8">
              <div>
                <h3 className="mb-4 text-xl font-semibold text-zinc-900 dark:text-white">
                  {t('howTo.sections.organizations.overview.title')}
                </h3>
                <p className="mb-4">
                  {t('howTo.sections.organizations.overview.description')}
                </p>
                <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 dark:border-amber-800 dark:bg-amber-950">
                  <p className="text-sm text-amber-700 dark:text-amber-300">
                    {t('howTo.sections.organizations.overview.note')}
                  </p>
                </div>
              </div>

              <div>
                <h3 className="mb-4 text-xl font-semibold text-zinc-900 dark:text-white">
                  {t('howTo.sections.organizations.roles.title')}
                </h3>
                <p className="mb-4">
                  {t('howTo.sections.organizations.roles.description')}
                </p>
                <div className="space-y-3">
                  {([
                    { key: 'superadmin', color: 'red' },
                    { key: 'orgAdmin', color: 'blue' },
                    { key: 'contributor', color: 'green' },
                    { key: 'annotator', color: 'purple' },
                  ] as const).map(({ key, color }) => (
                    <div
                      key={key}
                      className="flex items-center gap-4 rounded-lg border border-zinc-200 p-4 dark:border-zinc-700"
                    >
                      <div
                        className={`flex h-10 w-10 items-center justify-center rounded-full bg-${color}-100 text-${color}-600 dark:bg-${color}-900/20 dark:text-${color}-400`}
                      >
                        {t(`howTo.sections.organizations.roles.${key}.short`)}
                      </div>
                      <div>
                        <h4 className="font-semibold text-zinc-900 dark:text-white">
                          {t(`howTo.sections.organizations.roles.${key}.title`)}
                        </h4>
                        <p className="text-sm text-zinc-600 dark:text-zinc-400">
                          {t(`howTo.sections.organizations.roles.${key}.description`)}
                        </p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </HowToSection>

          {/* API Key Management */}
          <HowToSection
            title={t('howTo.sections.apiKeyManagement.title')}
            id="api-key-management"
          >
            <div className="space-y-8">
              <div>
                <h3 className="mb-4 text-xl font-semibold text-zinc-900 dark:text-white">
                  {t('howTo.sections.apiKeyManagement.setup.title')}
                </h3>
                <p className="mb-4">
                  {t('howTo.sections.apiKeyManagement.setup.description')}
                </p>
                <ol className="list-inside list-decimal space-y-3">
                  {(['step1', 'step2', 'step3', 'step4'] as const).map((step) => (
                    <li key={step} className="text-zinc-700 dark:text-zinc-300">
                      {t(`howTo.sections.apiKeyManagement.setup.${step}`)}
                    </li>
                  ))}
                </ol>
              </div>

              <div>
                <h3 className="mb-4 text-xl font-semibold text-zinc-900 dark:text-white">
                  {t('howTo.sections.apiKeyManagement.providers.title')}
                </h3>
                <p className="mb-4">
                  {t('howTo.sections.apiKeyManagement.providers.description')}
                </p>
                <p className="font-medium text-zinc-700 dark:text-zinc-300">
                  {t('howTo.sections.apiKeyManagement.providers.list')}
                </p>
              </div>

              <div>
                <h3 className="mb-4 text-xl font-semibold text-zinc-900 dark:text-white">
                  {t('howTo.sections.apiKeyManagement.security.title')}
                </h3>
                <p>{t('howTo.sections.apiKeyManagement.security.description')}</p>
              </div>
            </div>
          </HowToSection>

          {/* Troubleshooting */}
          <HowToSection
            title={t('howTo.sections.troubleshooting.title')}
            id="troubleshooting"
          >
            <div className="space-y-8">
              <div>
                <h3 className="mb-4 text-xl font-semibold text-zinc-900 dark:text-white">
                  {t('howTo.sections.troubleshooting.issues.title')}
                </h3>
                <div className="space-y-4">
                  {(['noProjects', 'generationFails', 'cannotAnnotate', 'evaluationEmpty'] as const).map(
                    (issue) => (
                      <div
                        key={issue}
                        className="rounded-lg border border-zinc-200 p-4 dark:border-zinc-700"
                      >
                        <h4 className="font-semibold text-zinc-900 dark:text-white">
                          {t(`howTo.sections.troubleshooting.issues.${issue}.question`)}
                        </h4>
                        <p className="mb-3 mt-2 text-sm text-zinc-600 dark:text-zinc-400">
                          {t(`howTo.sections.troubleshooting.issues.${issue}.description`)}
                        </p>
                        <div className="text-sm">
                          <p className="text-emerald-600 dark:text-emerald-400">
                            {t(`howTo.sections.troubleshooting.issues.${issue}.solution`)}
                          </p>
                        </div>
                      </div>
                    )
                  )}
                </div>
              </div>

              <div className="rounded-lg border border-blue-200 bg-blue-50 p-4 dark:border-blue-800 dark:bg-blue-950">
                <p className="text-sm font-medium text-blue-800 dark:text-blue-200">
                  {t('howTo.sections.troubleshooting.help.title')}
                </p>
                <p className="mt-1 text-sm text-blue-700 dark:text-blue-300">
                  {t('howTo.sections.troubleshooting.help.description')}
                </p>
              </div>
            </div>
          </HowToSection>
        </div>
      </div>
    </>
  )
}

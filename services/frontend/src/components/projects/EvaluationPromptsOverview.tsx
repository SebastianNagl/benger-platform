/**
 * Evaluation prompts of a project, read-only, for the Prompts card.
 *
 * One entry per configured LLM-judge method (metric `llm_judge_*`, or any
 * metric an overlay registered a prompt preview for):
 * - a registered preview (./lib/extensions/promptPreviews) renders as is;
 * - methods on the worker's generic judge path (classic, custom and
 *   llm_judge_* without an own editor) show the system prompt and the
 *   template the judge resolves (custom, answer-type default or fallback);
 * - other judge methods show their custom template if they carry one, else
 *   a note that they assemble the prompt at grading time.
 *
 * Below the methods, the default judge templates are listed as a reference
 * for writing own prompts.
 */

'use client'

import { PromptTemplateEditor } from '@/components/evaluation/PromptTemplateEditor'
import { PromptText } from '@/components/projects/PromptText'
import { Button } from '@/components/shared/Button'
import { useI18n } from '@/contexts/I18nContext'
import {
  DEFAULT_PROMPT_TEMPLATES,
  type EvaluationConfig,
  getMetricDefinitions,
  JUDGE_FALLBACK_PROMPT_TEMPLATE,
  JUDGE_SYSTEM_PROMPT,
  LLM_JUDGE_TEMPLATES,
  metricDisplayName,
  resolveJudgePrompt,
} from '@/lib/api/evaluation-types'
import { hasMetricEditor } from '@/lib/extensions/metricEditors'
import { getPromptPreview } from '@/lib/extensions/promptPreviews'
import { type ReactNode, useState } from 'react'

interface EvaluationPromptsOverviewProps {
  projectId: string
  evaluationConfigs: EvaluationConfig[]
  /** When set, generic judge prompts are editable in place; the page saves
   * the changed configs through the evaluation card's auto-save. */
  onConfigsChange?: (configs: EvaluationConfig[]) => void
}

function isPromptMethod(metric: string): boolean {
  return metric.startsWith('llm_judge_') || getPromptPreview(metric) !== null
}

function Disclosure({
  title,
  badge,
  children,
}: {
  title: string
  badge?: string
  children: ReactNode
}) {
  const [open, setOpen] = useState(false)
  return (
    <div className="rounded-lg border border-zinc-200 dark:border-zinc-700">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left hover:bg-zinc-50 dark:hover:bg-zinc-800/50"
      >
        <span className="flex min-w-0 items-center gap-2">
          <span className="truncate text-sm font-medium text-zinc-900 dark:text-white">
            {title}
          </span>
          {badge && (
            <span className="shrink-0 rounded-full bg-zinc-100 px-2.5 py-0.5 text-xs font-medium text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400">
              {badge}
            </span>
          )}
        </span>
        <svg
          className={`h-4 w-4 shrink-0 text-zinc-400 transition-transform ${
            open ? 'rotate-90 transform' : ''
          }`}
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
      {open && <div className="space-y-3 px-4 pb-4">{children}</div>}
    </div>
  )
}

/**
 * System prompt + resolved evaluation prompt of a method on the worker's
 * generic judge path, with in-place editing of the template when
 * `onChange` is set. Editing starts from the prompt in use; applying an
 * unchanged default keeps the method on the default (no custom copy), and
 * a custom template can be dropped to fall back to the default again.
 */
function GenericJudgePrompt({
  config,
  editorTestId,
  answerTypeName,
  onChange,
}: {
  config: EvaluationConfig
  editorTestId: string
  answerTypeName: (answerType: string) => string
  onChange?: (template: string | undefined) => void
}) {
  const { t } = useI18n()
  const params = config.metric_parameters || {}
  const resolved = resolveJudgePrompt(params)
  const [draft, setDraft] = useState<string | null>(null)

  const sourceLabel =
    resolved.source === 'custom'
      ? t('project.prompts.evaluation.sourceCustom')
      : resolved.source === 'answerType'
        ? t('project.prompts.evaluation.sourceAnswerType', {
            type: answerTypeName(resolved.answerType || ''),
          })
        : t('project.prompts.evaluation.sourceFallback')
  const defaultTemplate = resolveJudgePrompt({
    ...params,
    custom_prompt_template: undefined,
  }).template

  const apply = () => {
    if (draft === null || !onChange) return
    const next = draft.trim()
    if (resolved.source !== 'custom' && next === defaultTemplate.trim()) {
      setDraft(null)
      return
    }
    onChange(next ? draft : undefined)
    setDraft(null)
  }

  return (
    <>
      <PromptText
        label={t('generation.prompts.system')}
        value={JUDGE_SYSTEM_PROMPT}
      />
      {draft === null ? (
        <>
          <PromptText
            label={`${t('project.prompts.evaluation.prompt')} (${sourceLabel})`}
            value={resolved.template}
          />
          {onChange && (
            <div className="flex flex-wrap gap-2">
              <Button
                variant="outline"
                className="text-xs"
                onClick={() => setDraft(resolved.template)}
              >
                {t('project.prompts.evaluation.edit')}
              </Button>
              {resolved.source === 'custom' && (
                <Button
                  variant="outline"
                  className="text-xs"
                  onClick={() => onChange(undefined)}
                >
                  {t('project.prompts.evaluation.useDefault')}
                </Button>
              )}
            </div>
          )}
        </>
      ) : (
        <div className="space-y-2" data-testid={editorTestId}>
          <PromptTemplateEditor
            value={draft}
            onChange={setDraft}
            knownVariables={[
              'context',
              'ground_truth',
              'prediction',
              ...Object.keys(
                (params.field_mappings as Record<string, string> | undefined) ||
                  {},
              ),
            ]}
            dimensionKeys={Object.keys(
              (params.custom_criteria as Record<string, unknown> | undefined) ||
                {},
            )}
          />
          <p className="text-xs text-zinc-500 dark:text-zinc-400">
            {t('project.prompts.evaluation.editHint')}
          </p>
          <div className="flex gap-2">
            <Button className="text-xs" onClick={apply}>
              {t('project.prompts.evaluation.apply')}
            </Button>
            <Button
              variant="outline"
              className="text-xs"
              onClick={() => setDraft(null)}
            >
              {t('project.prompts.evaluation.cancel')}
            </Button>
          </div>
        </div>
      )}
    </>
  )
}

export function EvaluationPromptsOverview({
  projectId,
  evaluationConfigs,
  onConfigsChange,
}: EvaluationPromptsOverviewProps) {
  const { t } = useI18n()
  const definitions = getMetricDefinitions()
  // Configs are identified by their position: legacy rows may carry no id
  // (or a shared one), so neither keys nor edits can rely on `id`.
  const methods = evaluationConfigs
    .map((config, index) => ({ config, index }))
    .filter(({ config }) => isPromptMethod(config.metric))
  const siblingConfigs = evaluationConfigs.map((c) => ({
    metric: c.metric,
    metric_parameters: c.metric_parameters,
  }))

  const methodName = (config: EvaluationConfig) => {
    if (config.display_name) return config.display_name
    const def = definitions[config.metric]
    return def ? metricDisplayName(def, t) : config.metric
  }

  const answerTypeName = (answerType: string) => {
    const tpl = LLM_JUDGE_TEMPLATES[answerType]
    return tpl ? t(tpl.nameKey) : answerType
  }

  const renderMethodPrompts = (config: EvaluationConfig, index: number) => {
    const params = config.metric_parameters || {}
    const Preview = getPromptPreview(config.metric)
    if (Preview) {
      return (
        <Preview
          metric={config.metric}
          parameters={params}
          siblingConfigs={siblingConfigs}
          projectId={projectId}
        />
      )
    }

    if (!hasMetricEditor(config.metric)) {
      return (
        <GenericJudgePrompt
          config={config}
          editorTestId={`judge-prompt-editor-${config.id ?? index}`}
          answerTypeName={answerTypeName}
          onChange={
            onConfigsChange
              ? (template) =>
                  onConfigsChange(
                    evaluationConfigs.map((c, i) =>
                      i === index
                        ? {
                            ...c,
                            metric_parameters: {
                              ...(c.metric_parameters || {}),
                              custom_prompt_template: template,
                            },
                          }
                        : c,
                    ),
                  )
              : undefined
          }
        />
      )
    }

    const custom = params.custom_prompt_template
    if (typeof custom === 'string' && custom.trim()) {
      return (
        <PromptText
          label={`${t('project.prompts.evaluation.prompt')} (${t(
            'project.prompts.evaluation.sourceCustom',
          )})`}
          value={custom}
        />
      )
    }
    return (
      <p className="text-xs text-zinc-500 dark:text-zinc-400">
        {t('project.prompts.evaluation.builtAtGrading')}
      </p>
    )
  }

  return (
    <div className="space-y-6">
      <div>
        <p className="mb-3 text-xs text-zinc-500 dark:text-zinc-400">
          {t('project.prompts.evaluation.help')}
        </p>
        {methods.length === 0 ? (
          <p
            className="py-4 text-center text-sm text-zinc-500 dark:text-zinc-400"
            data-testid="evaluation-prompts-empty"
          >
            {t('project.prompts.evaluation.empty')}
          </p>
        ) : (
          <div className="space-y-2" data-testid="evaluation-prompts-methods">
            {methods.map(({ config, index }) => (
              <Disclosure
                key={`${config.id ?? ''}-${index}`}
                title={methodName(config)}
                badge={
                  config.enabled === false
                    ? t('project.prompts.evaluation.disabled')
                    : undefined
                }
              >
                {renderMethodPrompts(config, index)}
              </Disclosure>
            ))}
          </div>
        )}
      </div>

      <div>
        <h3 className="mb-1 text-sm font-semibold text-zinc-900 dark:text-white">
          {t('project.prompts.templates.title')}
        </h3>
        <p className="mb-3 text-xs text-zinc-500 dark:text-zinc-400">
          {t('project.prompts.templates.help')}
        </p>
        <div className="space-y-2" data-testid="evaluation-prompts-templates">
          {Object.entries(DEFAULT_PROMPT_TEMPLATES).map(([key, tpl]) => (
            <Disclosure key={key} title={answerTypeName(key)}>
              <PromptText
                label={t('generation.prompts.system')}
                value={JUDGE_SYSTEM_PROMPT}
              />
              <PromptText
                label={t('project.prompts.evaluation.prompt')}
                value={tpl.template}
              />
            </Disclosure>
          ))}
          <Disclosure title={t('project.prompts.evaluation.sourceFallback')}>
            <PromptText
              label={t('generation.prompts.system')}
              value={JUDGE_SYSTEM_PROMPT}
            />
            <PromptText
              label={t('project.prompts.evaluation.prompt')}
              value={JUDGE_FALLBACK_PROMPT_TEMPLATE}
            />
          </Disclosure>
        </div>
      </div>
    </div>
  )
}

/**
 * EvaluationPromptsOverview — the evaluation half of the project page's
 * Prompts card: one entry per LLM-judge method with the prompt the judge
 * resolves, overlay previews via registerPromptPreview, and the default
 * judge templates as a reference.
 */

import {
  DEFAULT_PROMPT_TEMPLATES,
  type EvaluationConfig,
  JUDGE_FALLBACK_PROMPT_TEMPLATE,
  JUDGE_SYSTEM_PROMPT,
  resolveJudgePrompt,
} from '@/lib/api/evaluation-types'
import { registerMetricEditor } from '@/lib/extensions/metricEditors'
import { registerPromptPreview } from '@/lib/extensions/promptPreviews'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { EvaluationPromptsOverview } from '../EvaluationPromptsOverview'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, vars?: Record<string, unknown>) => {
      const translations: Record<
        string,
        any
      > = require('../../../locales/en/common.json')
      let value: any = translations
      for (const part of key.split('.')) {
        if (value && typeof value === 'object' && part in value) {
          value = value[part]
        } else {
          return key
        }
      }
      if (typeof value !== 'string') return key
      for (const [k, v] of Object.entries(vars || {})) {
        value = value.replace(new RegExp(`\\{${k}\\}`, 'g'), String(v))
      }
      return value
    },
    locale: 'en',
  }),
}))

const config = (
  id: string,
  metric: string,
  metric_parameters: Record<string, unknown> = {},
  extra: Partial<EvaluationConfig> = {},
): EvaluationConfig => ({
  id,
  metric,
  metric_parameters,
  prediction_fields: [],
  reference_fields: [],
  enabled: true,
  ...extra,
})

const methods = () => screen.getByTestId('evaluation-prompts-methods')

describe('resolveJudgePrompt', () => {
  it('prefers a custom template', () => {
    expect(
      resolveJudgePrompt({
        custom_prompt_template: 'Mine {prediction}',
        answer_type: 'choices',
      }),
    ).toEqual({ source: 'custom', template: 'Mine {prediction}' })
  })

  it('ignores a blank custom template and uses the answer-type default', () => {
    expect(
      resolveJudgePrompt({
        custom_prompt_template: '  ',
        answer_type: 'binary',
      }),
    ).toEqual({
      source: 'answerType',
      answerType: 'binary',
      template: DEFAULT_PROMPT_TEMPLATES.choices.template,
    })
  })

  it('maps answer types onto their template like the worker', () => {
    expect(resolveJudgePrompt({ answer_type: 'long_text' }).template).toBe(
      DEFAULT_PROMPT_TEMPLATES.text.template,
    )
    expect(resolveJudgePrompt({ answer_type: 'rating' }).template).toBe(
      DEFAULT_PROMPT_TEMPLATES.numeric.template,
    )
    expect(resolveJudgePrompt({ answer_type: 'span_selection' }).template).toBe(
      DEFAULT_PROMPT_TEMPLATES.span_selection.template,
    )
    // Unknown types fall back to the text template (get_template_for_type)
    expect(resolveJudgePrompt({ answer_type: 'taxonomy' }).template).toBe(
      DEFAULT_PROMPT_TEMPLATES.text.template,
    )
  })

  it('falls back to the generic template without custom or answer type', () => {
    expect(resolveJudgePrompt({ answer_type: null })).toEqual({
      source: 'fallback',
      template: JUDGE_FALLBACK_PROMPT_TEMPLATE,
    })
    expect(resolveJudgePrompt(undefined).source).toBe('fallback')
  })
})

describe('EvaluationPromptsOverview', () => {
  it('shows the empty state when no judge method is configured', () => {
    render(
      <EvaluationPromptsOverview
        projectId="p1"
        evaluationConfigs={[config('e1', 'bleu')]}
      />,
    )
    expect(screen.getByTestId('evaluation-prompts-empty')).toBeInTheDocument()
    expect(
      screen.queryByTestId('evaluation-prompts-methods'),
    ).not.toBeInTheDocument()
  })

  it('lists only judge methods, not lexical metrics', () => {
    render(
      <EvaluationPromptsOverview
        projectId="p1"
        evaluationConfigs={[
          config('e1', 'bleu'),
          config('e2', 'llm_judge_classic', {}, { display_name: 'My judge' }),
        ]}
      />,
    )
    expect(within(methods()).getByText('My judge')).toBeInTheDocument()
    expect(within(methods()).getAllByRole('button')).toHaveLength(1)
  })

  it('shows system prompt and custom template of a custom judge', async () => {
    render(
      <EvaluationPromptsOverview
        projectId="p1"
        evaluationConfigs={[
          config(
            'e1',
            'llm_judge_custom',
            {
              custom_prompt_template:
                'Grade {prediction} against {ground_truth}',
            },
            { display_name: 'Custom judge' },
          ),
        ]}
      />,
    )
    await userEvent.click(within(methods()).getByText('Custom judge'))
    expect(within(methods()).getByText(JUDGE_SYSTEM_PROMPT)).toBeInTheDocument()
    expect(
      within(methods()).getByText('Evaluation prompt (Custom template)'),
    ).toBeInTheDocument()
    expect(
      within(methods()).getByText('Grade {prediction} against {ground_truth}'),
    ).toBeInTheDocument()
  })

  it('names the answer-type default a classic judge falls back to', async () => {
    render(
      <EvaluationPromptsOverview
        projectId="p1"
        evaluationConfigs={[
          config(
            'e1',
            'llm_judge_classic',
            { answer_type: 'choices' },
            { display_name: 'Classic', enabled: false },
          ),
        ]}
      />,
    )
    // Disabled methods are still listed, with a badge
    expect(within(methods()).getByText('Disabled')).toBeInTheDocument()
    await userEvent.click(within(methods()).getByText('Classic'))
    expect(
      within(methods()).getByText(
        /Evaluation prompt \(Default template for .+\)/,
      ),
    ).toBeInTheDocument()
  })

  it('renders an overlay prompt preview when one is registered', async () => {
    registerPromptPreview(
      'llm_judge_test_preview',
      ({ metric, parameters }) => (
        <div data-testid="overlay-preview">
          {metric}:{String(parameters.rubric)}
        </div>
      ),
    )
    render(
      <EvaluationPromptsOverview
        projectId="p1"
        evaluationConfigs={[
          config(
            'e1',
            'llm_judge_test_preview',
            { rubric: 'r1' },
            { display_name: 'Overlay judge' },
          ),
        ]}
      />,
    )
    await userEvent.click(within(methods()).getByText('Overlay judge'))
    expect(screen.getByTestId('overlay-preview')).toHaveTextContent(
      'llm_judge_test_preview:r1',
    )
    expect(
      within(methods()).queryByText(JUDGE_SYSTEM_PROMPT),
    ).not.toBeInTheDocument()
  })

  it('notes that a judge with its own editor builds its prompt at grading time', async () => {
    registerMetricEditor('llm_judge_test_own_editor', () => null)
    render(
      <EvaluationPromptsOverview
        projectId="p1"
        evaluationConfigs={[
          config(
            'e1',
            'llm_judge_test_own_editor',
            {},
            { display_name: 'Own editor judge' },
          ),
        ]}
      />,
    )
    await userEvent.click(within(methods()).getByText('Own editor judge'))
    expect(
      within(methods()).getByText(/assembles its prompt at grading time/),
    ).toBeInTheDocument()
  })

  it('lists the default judge templates as a reference', async () => {
    render(<EvaluationPromptsOverview projectId="p1" evaluationConfigs={[]} />)
    const templates = screen.getByTestId('evaluation-prompts-templates')
    // One entry per default template plus the general fallback
    expect(within(templates).getAllByRole('button')).toHaveLength(
      Object.keys(DEFAULT_PROMPT_TEMPLATES).length + 1,
    )
    await userEvent.click(
      within(templates).getByText('General default template'),
    )
    expect(
      within(templates).getByText(
        /assessing the quality of an AI-generated response/,
      ),
    ).toBeInTheDocument()
  })

  describe('editing', () => {
    const custom = config(
      'e1',
      'llm_judge_custom',
      { custom_prompt_template: 'Grade {prediction}' },
      { display_name: 'Custom judge' },
    )
    const classic = config(
      'e2',
      'llm_judge_classic',
      { answer_type: 'choices' },
      { display_name: 'Classic' },
    )

    it('is read-only without onConfigsChange', async () => {
      render(
        <EvaluationPromptsOverview
          projectId="p1"
          evaluationConfigs={[custom]}
        />,
      )
      await userEvent.click(within(methods()).getByText('Custom judge'))
      expect(screen.queryByText('Edit prompt')).not.toBeInTheDocument()
    })

    it('edits a custom template in place and hands back the changed configs', async () => {
      const onConfigsChange = jest.fn()
      render(
        <EvaluationPromptsOverview
          projectId="p1"
          evaluationConfigs={[custom, classic]}
          onConfigsChange={onConfigsChange}
        />,
      )
      await userEvent.click(within(methods()).getByText('Custom judge'))
      await userEvent.click(screen.getByText('Edit prompt'))
      const editor = screen.getByTestId('judge-prompt-editor-e1')
      const textarea = within(editor).getByRole('textbox')
      expect(textarea).toHaveValue('Grade {prediction}')
      await userEvent.clear(textarea)
      await userEvent.type(textarea, 'Strict grading')
      await userEvent.click(screen.getByText('Apply'))

      expect(onConfigsChange).toHaveBeenCalledTimes(1)
      const [next] = onConfigsChange.mock.calls[0]
      expect(next[0].metric_parameters.custom_prompt_template).toBe(
        'Strict grading',
      )
      // Other methods pass through untouched
      expect(next[1]).toBe(classic)
    })

    it('applying the unchanged default keeps the method on the default', async () => {
      const onConfigsChange = jest.fn()
      render(
        <EvaluationPromptsOverview
          projectId="p1"
          evaluationConfigs={[classic]}
          onConfigsChange={onConfigsChange}
        />,
      )
      await userEvent.click(within(methods()).getByText('Classic'))
      await userEvent.click(screen.getByText('Edit prompt'))
      expect(
        within(screen.getByTestId('judge-prompt-editor-e2')).getByRole(
          'textbox',
        ),
      ).toHaveValue(DEFAULT_PROMPT_TEMPLATES.choices.template)
      await userEvent.click(screen.getByText('Apply'))
      expect(onConfigsChange).not.toHaveBeenCalled()
    })

    it('drops a custom template back to the default', async () => {
      const onConfigsChange = jest.fn()
      render(
        <EvaluationPromptsOverview
          projectId="p1"
          evaluationConfigs={[custom]}
          onConfigsChange={onConfigsChange}
        />,
      )
      await userEvent.click(within(methods()).getByText('Custom judge'))
      await userEvent.click(screen.getByText('Use default template'))
      const [next] = onConfigsChange.mock.calls[0]
      expect(next[0].metric_parameters.custom_prompt_template).toBeUndefined()
    })

    it('edits only the chosen method when configs carry no id', async () => {
      const onConfigsChange = jest.fn()
      const noId = (name: string) =>
        ({
          ...config('x', 'llm_judge_custom', {
            custom_prompt_template: `${name} {prediction}`,
          }),
          id: null,
          display_name: name,
        }) as unknown as EvaluationConfig
      render(
        <EvaluationPromptsOverview
          projectId="p1"
          evaluationConfigs={[noId('First'), noId('Second')]}
          onConfigsChange={onConfigsChange}
        />,
      )
      await userEvent.click(within(methods()).getByText('Second'))
      await userEvent.click(screen.getByText('Use default template'))
      const [next] = onConfigsChange.mock.calls[0]
      expect(next[0].metric_parameters.custom_prompt_template).toBe(
        'First {prediction}',
      )
      expect(next[1].metric_parameters.custom_prompt_template).toBeUndefined()
    })

    it('cancel discards the draft', async () => {
      const onConfigsChange = jest.fn()
      render(
        <EvaluationPromptsOverview
          projectId="p1"
          evaluationConfigs={[custom]}
          onConfigsChange={onConfigsChange}
        />,
      )
      await userEvent.click(within(methods()).getByText('Custom judge'))
      await userEvent.click(screen.getByText('Edit prompt'))
      await userEvent.click(screen.getByText('Cancel'))
      expect(
        screen.queryByTestId('judge-prompt-editor-e1'),
      ).not.toBeInTheDocument()
      expect(onConfigsChange).not.toHaveBeenCalled()
    })
  })
})

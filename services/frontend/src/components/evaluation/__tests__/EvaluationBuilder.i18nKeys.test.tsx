/**
 * Every string the evaluation builder and its dialog show resolves in the
 * locale catalog.
 *
 * The other component tests mock `t` to return the key, so a mistyped key
 * passes them and shows the raw key on a real page. Here `t` resolves
 * against the real de/en catalogs, without the fallback to another language,
 * and the test walks a new method through every step of the dialog for each
 * built-in parameter editor, then opens the discard prompt. A key that the
 * catalog lacks comes back unchanged, so any visible text or label that
 * still reads like "evaluationBuilder.x.y" is a missing translation, however
 * the key was built.
 *
 * @jest-environment jsdom
 */

import { hasTranslation, translateKey } from '@/lib/i18n/catalog'
import type { Locale } from '@/lib/i18n/locales'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { EvaluationBuilder } from '../EvaluationBuilder'

let mockLocale: Locale = 'en'
const mockT = (key: string, vars?: Record<string, unknown>) =>
  hasTranslation(mockLocale, key)
    ? translateKey(mockLocale, key, vars as any)
    : key
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({ t: mockT, locale: mockLocale }),
}))

jest.mock('@/components/shared/Toast', () => ({
  useToast: () => ({ addToast: jest.fn() }),
}))

jest.mock('@/hooks/useModels', () => ({
  useModels: () => ({ models: [], loading: false }),
}))

jest.mock('@/lib/api', () => ({
  api: {
    get: jest.fn().mockResolvedValue({ data: {} }),
    post: jest.fn().mockResolvedValue({ data: {} }),
  },
}))

const availableFields = {
  model_response_fields: ['model_answer'],
  human_annotation_fields: [],
  all_fields: ['model_answer', 'reference'],
  reference_fields: ['reference'],
}

const RAW_KEY =
  /(?:^|[\s("'])((?:evaluationBuilder|evaluation|common)\.[A-Za-z_][\w.]*)/g

/** Raw catalog keys in the visible text and the labels of the page. */
function rawKeys(): string[] {
  const found: string[] = []
  const collect = (text: string | null) => {
    for (const match of (text || '').matchAll(RAW_KEY)) found.push(match[1])
  }
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT)
  while (walker.nextNode()) collect(walker.currentNode.textContent)
  document.body.querySelectorAll('*').forEach((element) => {
    for (const attr of ['aria-label', 'title', 'placeholder', 'alt']) {
      collect(element.getAttribute(attr))
    }
  })
  return found
}

const METRICS = [
  'bleu',
  'rouge',
  'meteor',
  'chrf',
  'factcc',
  'llm_judge_classic',
  'llm_judge_custom',
]
const STEPS = [
  'metric',
  'prediction_fields',
  'reference_fields',
  'parameters',
  'review',
]

describe.each<Locale>(['de', 'en'])(
  'EvaluationBuilder strings in %s',
  (lang) => {
    beforeEach(() => {
      mockLocale = lang
    })

    it.each(METRICS)(
      'shows no raw key on any step of a new %s method or the discard prompt',
      async (metric) => {
        const user = userEvent.setup()
        render(
          <EvaluationBuilder
            projectId="project-1"
            availableFields={availableFields}
            evaluations={[]}
            onEvaluationsChange={jest.fn()}
          />,
        )
        const seen = new Set<string>()
        const record = () => rawKeys().forEach((key) => seen.add(key))
        record()

        await user.click(screen.getByTestId('add-evaluation-button'))
        record()
        await user.click(screen.getByTestId(`metric-button-${metric}`))
        record()

        const visited: string[] = []
        for (const step of STEPS) {
          const nav = screen.queryByTestId(`wizard-step-nav-${step}`)
          if (!nav || (nav as HTMLButtonElement).disabled) continue
          await user.click(nav)
          visited.push(step)
          if (step === 'prediction_fields' || step === 'reference_fields') {
            const body = screen.getByTestId('evaluation-wizard-body')
            const boxes = within(body).getAllByRole('checkbox')
            if (!boxes.some((box) => (box as HTMLInputElement).checked)) {
              await user.click(boxes[0])
            }
          }
          record()
        }
        expect(visited).toEqual(
          expect.arrayContaining(['metric', 'prediction_fields', 'parameters']),
        )

        await user.keyboard('{Escape}')
        expect(
          await screen.findByText(
            translateKey(lang, 'evaluationBuilder.discard.keepEditing'),
          ),
        ).toBeInTheDocument()
        record()

        expect(Array.from(seen)).toEqual([])
      },
    )

    it('opens an edit and its review with no raw key', async () => {
      const user = userEvent.setup()
      render(
        <EvaluationBuilder
          projectId="project-1"
          availableFields={availableFields}
          evaluations={[
            {
              id: 'eval-bleu',
              metric: 'bleu',
              display_name: 'BLEU',
              prediction_fields: ['model_answer'],
              reference_fields: ['reference'],
              metric_parameters: { max_order: 4 },
              enabled: false,
              created_at: '2025-01-01',
            },
          ]}
          onEvaluationsChange={jest.fn()}
        />,
      )
      const seen = new Set(rawKeys())
      await user.click(screen.getByTestId('evaluation-method-edit'))
      rawKeys().forEach((key) => seen.add(key))
      await user.click(screen.getByTestId('wizard-step-nav-review'))
      rawKeys().forEach((key) => seen.add(key))

      expect(Array.from(seen)).toEqual([])
    })
  },
)

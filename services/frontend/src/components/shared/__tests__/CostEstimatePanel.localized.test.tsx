/**
 * @jest-environment jsdom
 *
 * The cost-estimate panel phrases the estimate's assumptions from the
 * structured response fields (accuracy band, input basis, output share,
 * tokenizer, counted cells) in the reader's language, and only falls back to
 * the API's English `note` when those fields are missing (older API).
 */
import '@testing-library/jest-dom'
import { render, screen, waitFor } from '@testing-library/react'

import de from '@/locales/de/common.json'
import en from '@/locales/en/common.json'

import { CostEstimatePanel } from '../CostEstimatePanel'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (_key: string, fallback?: any) =>
      typeof fallback === 'string' ? fallback : _key,
  }),
}))

jest.mock('@/components/shared/Toast', () => ({
  useToast: () => ({ addToast: jest.fn() }),
}))

const mockPost = jest.fn()
jest.mock('@/lib/api', () => ({
  __esModule: true,
  default: { post: (...args: any[]) => mockPost(...args) },
}))

const baseEstimate = {
  mode: 'evaluation' as const,
  runs_per_call: 1,
  sample_size: 3,
  tasks_total: 1,
  subject_count: 0,
  estimated_at: '2026-09-15T10:00:00Z',
  per_model: [
    {
      model_id: 'gpt-5-mini',
      per_call_usd: 0.01,
      per_run_usd: 0.03,
      total_usd: 0.03,
      pricing_known: true,
    },
  ],
  total_usd: 0.03,
  token_estimate: {
    input_mean: 18944,
    input_p95: 19575,
    output_estimate: 600,
    encoding: 'o200k_base',
  },
  note: 'Estimate accuracy ± ~20%. English note.',
}

function renderPanel() {
  return render(
    <CostEstimatePanel
      projectId="p1"
      mode="evaluation"
      judgeModels={['gpt-5-mini']}
      runsPerCall={1}
    />,
  )
}

beforeEach(() => {
  mockPost.mockReset()
})

describe('CostEstimatePanel localized note', () => {
  it('builds the note from the structured fields instead of the English note', async () => {
    mockPost.mockResolvedValue({
      ...baseEstimate,
      accuracy_percent: 20,
      encoding: 'o200k_base',
      input_basis: 'rendered_judge_prompt',
      output_utilization_percent: 15,
      missing_only: true,
      per_judge_cells: true,
    })
    renderPanel()

    const note = await screen.findByText(/Genauigkeit der Schätzung ± ~20 %\./)
    expect(note).toHaveTextContent('vollständige Judge-Prompt')
    expect(note).toHaveTextContent('15 % von max_tokens')
    expect(note).toHaveTextContent('Tokens gezählt mit o200k_base')
    expect(note).toHaveTextContent('tatsächlich ausgeführt')
    expect(note).toHaveTextContent('Zellen pro Judge')
    expect(screen.queryByText(/English note/)).not.toBeInTheDocument()
    expect(
      screen.getByText(
        'Input: 18944 (Mittel) / 19575 (p95) · Output: 600 · Kodierung: o200k_base · Stichprobe: 3',
      ),
    ).toBeInTheDocument()
  })

  it('names the generation basis and utilization for generation estimates', async () => {
    mockPost.mockResolvedValue({
      ...baseEstimate,
      mode: 'generation',
      accuracy_percent: 20,
      encoding: 'cl100k_base',
      input_basis: 'task_data',
      output_utilization_percent: null,
      missing_only: false,
      per_judge_cells: false,
    })
    render(
      <CostEstimatePanel
        projectId="p1"
        mode="generation"
        modelIds={['gpt-5-mini']}
        runsPerCall={1}
      />,
    )

    const note = await screen.findByText(/Genauigkeit der Schätzung/)
    expect(note).toHaveTextContent('an den Aufgabendaten gemessen')
    expect(note).toHaveTextContent('Reasoning-Modellen 90 %')
    expect(note).toHaveTextContent('jede Zelle (Task × Struktur)')
    expect(note).not.toHaveTextContent('Zellen pro Judge')
  })

  it('falls back to the API note when the structured fields are absent', async () => {
    mockPost.mockResolvedValue(baseEstimate)
    renderPanel()
    await waitFor(() =>
      expect(screen.getByText(/English note/)).toBeInTheDocument(),
    )
  })

  it('has every note key in both locales', () => {
    const keys = [
      'accuracy',
      'basisTaskData',
      'basisGenerationOutputs',
      'basisRenderedJudgePrompt',
      'outputJudge',
      'outputGeneration',
      'encoding',
      'countingMissing',
      'countingAll',
      'perJudgeCells',
    ]
    for (const locale of [de, en] as any[]) {
      expect(typeof locale.costEstimate.tokenLine).toBe('string')
      for (const key of keys) {
        expect(typeof locale.costEstimate.note[key]).toBe('string')
      }
    }
  })
})

import type { AvailableMetric } from '@/lib/api/evaluation-types'
import { registerTranslations, translateKey } from '@/lib/i18n/catalog'
import { computeDefaultEvalName, localizedEvalConfigName } from '../evalName'

const FALL = { display_name: 'Falllösung LLM Judge' } as any

describe('computeDefaultEvalName', () => {
  it('single judge, 1 run → bare model', () => {
    expect(
      computeDefaultEvalName(
        FALL,
        { judges: [{ runs: 1, judge_model_id: 'gpt-5-mini' }] },
        'llm_judge_falloesung',
      ),
    ).toBe('Falllösung LLM Judge (gpt-5-mini)')
  })

  it('single judge, 3 runs → model ×3', () => {
    expect(
      computeDefaultEvalName(
        FALL,
        { judges: [{ runs: 3, judge_model_id: 'gpt-5-mini' }] },
        'llm_judge_falloesung',
      ),
    ).toBe('Falllösung LLM Judge (gpt-5-mini ×3)')
  })

  it('same model appears twice → runs sum', () => {
    expect(
      computeDefaultEvalName(
        FALL,
        {
          judges: [
            { runs: 1, judge_model_id: 'gpt-5-mini' },
            { runs: 1, judge_model_id: 'gpt-5-mini' },
          ],
        },
        'llm_judge_falloesung',
      ),
    ).toBe('Falllösung LLM Judge (gpt-5-mini ×2)')
  })

  it('missing runs defaults to 1', () => {
    expect(
      computeDefaultEvalName(
        FALL,
        { judges: [{ judge_model_id: 'gpt-5-mini' }] },
        'llm_judge_falloesung',
      ),
    ).toBe('Falllösung LLM Judge (gpt-5-mini)')
  })

  it('ensemble of 3 distinct models preserves first-appearance order', () => {
    expect(
      computeDefaultEvalName(
        FALL,
        {
          judges: [
            { runs: 1, judge_model_id: 'gpt-5-mini' },
            { runs: 1, judge_model_id: 'claude-opus-4-7' },
            { runs: 1, judge_model_id: 'gemini-3.1-pro-preview' },
          ],
        },
        'llm_judge_falloesung',
      ),
    ).toBe(
      'Falllösung LLM Judge (gpt-5-mini + claude-opus-4-7 + gemini-3.1-pro-preview)',
    )
  })

  it('ensemble mixes run counts', () => {
    expect(
      computeDefaultEvalName(
        FALL,
        {
          judges: [
            { runs: 2, judge_model_id: 'gpt-5-mini' },
            { runs: 1, judge_model_id: 'claude-opus-4-7' },
          ],
        },
        'llm_judge_falloesung',
      ),
    ).toBe('Falllösung LLM Judge (gpt-5-mini ×2 + claude-opus-4-7)')
  })

  it('legacy judge_model (no judges) → single model, 1 run', () => {
    expect(
      computeDefaultEvalName(
        FALL,
        { judge_model: 'gpt-5-mini' },
        'llm_judge_falloesung',
      ),
    ).toBe('Falllösung LLM Judge (gpt-5-mini)')
  })

  it('prefers judges[] over legacy judge_model', () => {
    expect(
      computeDefaultEvalName(
        { display_name: 'Classic LLM Judge' } as any,
        { judges: [{ runs: 1, judge_model_id: 'x' }], judge_model: 'gpt-4o' },
        'llm_judge_classic',
      ),
    ).toBe('Classic LLM Judge (x)')
  })

  it('model ids with "/" pass through verbatim', () => {
    expect(
      computeDefaultEvalName(
        FALL,
        {
          judges: [
            { runs: 1, judge_model_id: 'deepseek-ai/DeepSeek-V4-Pro' },
            { runs: 3, judge_model_id: 'Qwen/Qwen3.5-397B-A17B' },
          ],
        },
        'llm_judge_falloesung',
      ),
    ).toBe(
      'Falllösung LLM Judge (deepseek-ai/DeepSeek-V4-Pro + Qwen/Qwen3.5-397B-A17B ×3)',
    )
  })

  it('non-llm metric unchanged', () => {
    expect(
      computeDefaultEvalName(
        { display_name: 'BLEU' } as any,
        { max_order: 4 },
        'bleu',
      ),
    ).toBe('BLEU')
  })

  it('korrektur (non-llm) metric unchanged, no parens', () => {
    expect(
      computeDefaultEvalName(
        { display_name: 'Korrektur Fallloesung' } as any,
        { judge_model: 'gpt-5-mini' },
        'korrektur_falloesung',
      ),
    ).toBe('Korrektur Fallloesung')
  })

  it('llm_judge metric with no resolvable model unchanged', () => {
    expect(
      computeDefaultEvalName(
        { display_name: 'Classic LLM Judge' } as any,
        {},
        'llm_judge_classic',
      ),
    ).toBe('Classic LLM Judge')
  })

  it('is idempotent when base already ends with the descriptor', () => {
    expect(
      computeDefaultEvalName(
        { display_name: 'Falllösung LLM Judge (gpt-5-mini ×3)' } as any,
        { judges: [{ runs: 3, judge_model_id: 'gpt-5-mini' }] },
        'llm_judge_falloesung',
      ),
    ).toBe('Falllösung LLM Judge (gpt-5-mini ×3)')
  })

  it('falls back to the metric key when metricDef is missing', () => {
    expect(
      computeDefaultEvalName(
        undefined,
        { judge_model: 'gpt-4o' },
        'llm_judge_classic',
      ),
    ).toBe('llm_judge_classic (gpt-4o)')
  })
})

describe('localizedEvalConfigName', () => {
  // A metric as an overlay registers it: its own name key plus the key of
  // the name its preset stores.
  const definitions = {
    human_grade: {
      name: 'human_grade',
      display_name: 'Human grade (registry)',
      displayNameKey: 'zzEvalName.metric',
      presetNameKeys: ['zzEvalName.preset'],
      description: '',
      category: 'Human Evaluation',
      status: 'stable',
      supports_parameters: false,
    },
    plain: {
      name: 'plain',
      display_name: 'Plain',
      description: '',
      category: 'Lexical',
      status: 'stable',
      supports_parameters: false,
    },
  } as Record<string, AvailableMetric>
  const fr = (key: string) => translateKey('fr', key)
  const de = (key: string) => translateKey('de', key)

  beforeAll(() => {
    registerTranslations('evalName-test', {
      de: {
        zzEvalName: {
          metric: 'Menschliche Note',
          preset: 'Korrektur (Raster /20)',
        },
      },
      en: {
        zzEvalName: { metric: 'Human grade', preset: 'Grading (grid /20)' },
      },
      fr: {
        zzEvalName: {
          metric: 'Note humaine',
          preset: 'Correction (grille /20)',
        },
      },
    })
  })
  afterAll(() => {
    registerTranslations('evalName-test', { de: {}, en: {}, fr: {} })
  })

  it('renders a stored preset name in the reader language', () => {
    expect(
      localizedEvalConfigName(
        { display_name: 'Korrektur (Raster /20)', metric: 'human_grade' },
        fr,
        definitions,
      ),
    ).toBe('Correction (grille /20)')
    expect(
      localizedEvalConfigName(
        { display_name: 'Correction (grille /20)', metric: 'human_grade' },
        de,
        definitions,
      ),
    ).toBe('Korrektur (Raster /20)')
  })

  it("recognizes the metric's own name, also as the registry literal", () => {
    expect(
      localizedEvalConfigName(
        { display_name: 'Human grade', metric: 'human_grade' },
        fr,
        definitions,
      ),
    ).toBe('Note humaine')
    expect(
      localizedEvalConfigName(
        { display_name: 'Human grade (registry)', metric: 'human_grade' },
        fr,
        definitions,
      ),
    ).toBe('Note humaine')
  })

  it("keeps the config's own judge-model suffix and translates the name", () => {
    expect(
      localizedEvalConfigName(
        {
          display_name: 'Korrektur (Raster /20) (gpt-5-mini)',
          metric: 'human_grade',
          metric_parameters: { judge_model: 'gpt-5-mini' },
        },
        fr,
        definitions,
      ),
    ).toBe('Correction (grille /20) (gpt-5-mini)')
    expect(
      localizedEvalConfigName(
        {
          display_name: 'Menschliche Note (gpt-5-mini ×3)',
          metric: 'human_grade',
          metric_parameters: {
            judges: [
              { judge_model_id: 'gpt-5-mini', runs: 2 },
              { judge_model_id: 'gpt-5-mini' },
            ],
          },
        },
        fr,
        definitions,
      ),
    ).toBe('Note humaine (gpt-5-mini ×3)')
  })

  it('leaves a known name with any other suffix as typed', () => {
    // A teacher's own names for two configs of one metric.
    for (const typed of [
      'Menschliche Note (Teil A)',
      'Menschliche Note (Teil B)',
    ]) {
      expect(
        localizedEvalConfigName(
          { display_name: typed, metric: 'human_grade' },
          fr,
          definitions,
        ),
      ).toBe(typed)
      expect(
        localizedEvalConfigName(
          {
            display_name: typed,
            metric: 'human_grade',
            metric_parameters: { judge_model: 'gpt-5-mini' },
          },
          fr,
          definitions,
        ),
      ).toBe(typed)
    }
    // The suffix names another judge model than the config runs.
    expect(
      localizedEvalConfigName(
        {
          display_name: 'Menschliche Note (gpt-4o)',
          metric: 'human_grade',
          metric_parameters: { judge_model: 'gpt-5-mini' },
        },
        fr,
        definitions,
      ),
    ).toBe('Menschliche Note (gpt-4o)')
    // A judge-model suffix without parameters naming it.
    expect(
      localizedEvalConfigName(
        {
          display_name: 'Menschliche Note (gpt-5-mini)',
          metric: 'human_grade',
        },
        fr,
        definitions,
      ),
    ).toBe('Menschliche Note (gpt-5-mini)')
  })

  it('leaves a typed name, an unknown metric and an empty name as stored', () => {
    expect(
      localizedEvalConfigName(
        { display_name: 'Meine Korrektur', metric: 'human_grade' },
        fr,
        definitions,
      ),
    ).toBe('Meine Korrektur')
    expect(
      localizedEvalConfigName(
        { display_name: 'Korrektur (Raster /20)', metric: 'unknown' },
        fr,
        definitions,
      ),
    ).toBe('Korrektur (Raster /20)')
    expect(
      localizedEvalConfigName(
        { display_name: 'Plain', metric: 'plain' },
        fr,
        definitions,
      ),
    ).toBe('Plain')
    expect(
      localizedEvalConfigName(
        { display_name: '', metric: 'human_grade' },
        fr,
        definitions,
      ),
    ).toBe('')
  })

  it('does not take a name of another metric', () => {
    expect(
      localizedEvalConfigName(
        { display_name: 'Korrektur (Raster /20)', metric: 'plain' },
        fr,
        definitions,
      ),
    ).toBe('Korrektur (Raster /20)')
  })
})

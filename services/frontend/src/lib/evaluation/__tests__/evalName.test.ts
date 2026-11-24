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
        'Korrektur (Raster /20)',
        'human_grade',
        fr,
        definitions,
      ),
    ).toBe('Correction (grille /20)')
    expect(
      localizedEvalConfigName(
        'Correction (grille /20)',
        'human_grade',
        de,
        definitions,
      ),
    ).toBe('Korrektur (Raster /20)')
  })

  it("recognizes the metric's own name, also as the registry literal", () => {
    expect(
      localizedEvalConfigName('Human grade', 'human_grade', fr, definitions),
    ).toBe('Note humaine')
    expect(
      localizedEvalConfigName(
        'Human grade (registry)',
        'human_grade',
        fr,
        definitions,
      ),
    ).toBe('Note humaine')
  })

  it('keeps a suffix such as the judge model', () => {
    expect(
      localizedEvalConfigName(
        'Korrektur (Raster /20) (gpt-5-mini)',
        'human_grade',
        fr,
        definitions,
      ),
    ).toBe('Correction (grille /20) (gpt-5-mini)')
    expect(
      localizedEvalConfigName(
        'Menschliche Note (Lauf 2)',
        'human_grade',
        fr,
        definitions,
      ),
    ).toBe('Note humaine (Lauf 2)')
  })

  it('leaves a typed name, an unknown metric and an empty name as stored', () => {
    expect(
      localizedEvalConfigName(
        'Meine Korrektur',
        'human_grade',
        fr,
        definitions,
      ),
    ).toBe('Meine Korrektur')
    expect(
      localizedEvalConfigName(
        'Korrektur (Raster /20)',
        'unknown',
        fr,
        definitions,
      ),
    ).toBe('Korrektur (Raster /20)')
    expect(localizedEvalConfigName('Plain', 'plain', fr, definitions)).toBe(
      'Plain',
    )
    expect(localizedEvalConfigName('', 'human_grade', fr, definitions)).toBe('')
  })

  it('does not take a name of another metric', () => {
    expect(
      localizedEvalConfigName(
        'Korrektur (Raster /20)',
        'plain',
        fr,
        definitions,
      ),
    ).toBe('Korrektur (Raster /20)')
  })
})

/**
 * Realistic report snapshot fixture (shape of a Klausur benchmark like
 * Benchathon: LLM judge on the Falllösung scheme, two judge configs, human
 * submissions graded by the same judge, a human Korrektur config). Used by
 * viewer/editor tests and as the reference for the API contract.
 */
import type { ReportSnapshot } from '@/types/report'

const bins18 = Array.from({ length: 19 }, (_, i) => i)
const bins01 = Array.from({ length: 10 }, (_, i) => i / 10)

const zeros = (n: number) => Array.from({ length: n }, () => 0)
const hist = (n: number, entries: Array<[number, number]>) => {
  const a = zeros(n)
  for (const [i, c] of entries) a[i] = c
  return a
}

export const REPORT_SNAPSHOT_FIXTURE: ReportSnapshot = {
  generated_at: '2026-09-02T12:00:00Z',
  statistics: {
    task_count: 15,
    annotation_count: 224,
    participant_count: 36,
    model_count: 4,
    evaluation_count: 3626,
  },
  methods: [
    {
      id: 'llm_judge_falloesung',
      name: 'Falllösung LLM Judge',
      category: 'llm_judge',
      scale: '0-100',
      higher_is_better: true,
    },
    {
      id: 'llm_judge_falloesung_grade_points',
      name: 'Notenpunkte (Falllösung)',
      category: 'llm_judge',
      scale: '0-18',
      higher_is_better: true,
      derived: true,
    },
    {
      id: 'llm_judge_falloesung_passed',
      name: 'Bestanden (Falllösung)',
      category: 'llm_judge',
      scale: '0-1',
      higher_is_better: true,
      derived: true,
    },
    {
      id: 'korrektur_falloesung',
      name: 'Korrektur (Standard Falllösung)',
      category: 'human',
      scale: '0-100',
      higher_is_better: true,
    },
    {
      id: 'bleu',
      name: 'BLEU',
      category: 'lexical',
      scale: '0-1',
      higher_is_better: true,
    },
  ],
  configs: [
    {
      id: 'cfg-judge-sonnet',
      metric: 'llm_judge_falloesung',
      judge_model: 'claude-sonnet-4-6',
      judge_label: 'Claude Sonnet 4.6',
      name: 'Notenpunkte (claude-sonnet-4-6)',
      n: 900,
    },
    {
      id: 'cfg-judge-mini',
      metric: 'llm_judge_falloesung',
      judge_model: 'gpt-5-mini',
      judge_label: 'GPT-5 mini',
      name: 'Notenpunkte (gpt-5-mini)',
      n: 420,
    },
    {
      id: 'cfg-korrektur',
      metric: 'korrektur_falloesung',
      judge_model: null,
      judge_label: null,
      name: 'Korrektur',
      n: 184,
    },
    {
      id: 'cfg-bleu',
      metric: 'bleu',
      judge_model: null,
      judge_label: null,
      name: null,
      n: 300,
    },
  ],
  primary_metric: 'llm_judge_falloesung',
  primary_config_id: 'cfg-judge-sonnet',
  grade_metric: 'llm_judge_falloesung_grade_points',
  models: [
    {
      id: 'gpt-5.4',
      kind: 'model',
      label: 'GPT-5.4',
      provider: 'openai',
      is_custom: false,
    },
    {
      id: 'claude-opus-4-7',
      kind: 'model',
      label: 'Claude Opus 4.7',
      provider: 'anthropic',
      is_custom: false,
    },
    {
      id: 'deepseek-ai/DeepSeek-V4-Flash',
      kind: 'model',
      label: 'DeepSeek V4 Flash',
      provider: 'deepinfra',
      is_custom: false,
    },
    {
      id: 'meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8',
      kind: 'model',
      label: 'Llama 4 Maverick',
      provider: 'deepinfra',
      is_custom: false,
    },
  ],
  participants: [
    { id: 'u1', label: 'KindAlly', annotation_count: 8 },
    { id: 'u2', label: 'BraveOtter', annotation_count: 7 },
    { id: 'u3', label: 'QuietRiver', annotation_count: 6 },
  ],
  series: [
    {
      subject: {
        id: 'gpt-5.4',
        kind: 'model',
        label: 'GPT-5.4',
        provider: 'openai',
      },
      config_id: 'cfg-judge-sonnet',
      metrics: {
        llm_judge_falloesung: {
          mean: 84.7,
          n: 15,
          std: 6.1,
          min: 70,
          max: 94,
          pass_rate: 1.0,
        },
        llm_judge_falloesung_grade_points: {
          mean: 13.9,
          n: 15,
          std: 1.8,
          min: 10,
          max: 17,
        },
        llm_judge_falloesung_passed: { mean: 1.0, n: 15 },
      },
    },
    {
      subject: {
        id: 'claude-opus-4-7',
        kind: 'model',
        label: 'Claude Opus 4.7',
        provider: 'anthropic',
      },
      config_id: 'cfg-judge-sonnet',
      metrics: {
        llm_judge_falloesung: {
          mean: 83.0,
          n: 15,
          std: 7.0,
          min: 66,
          max: 95,
          pass_rate: 1.0,
        },
        llm_judge_falloesung_grade_points: {
          mean: 13.6,
          n: 15,
          std: 2.0,
          min: 9,
          max: 17,
        },
        llm_judge_falloesung_passed: { mean: 1.0, n: 15 },
      },
    },
    {
      subject: {
        id: 'deepseek-ai/DeepSeek-V4-Flash',
        kind: 'model',
        label: 'DeepSeek V4 Flash',
        provider: 'deepinfra',
      },
      config_id: 'cfg-judge-sonnet',
      metrics: {
        llm_judge_falloesung: {
          mean: 70.2,
          n: 15,
          std: 9.4,
          min: 51,
          max: 88,
          pass_rate: 0.93,
        },
        llm_judge_falloesung_grade_points: {
          mean: 9.8,
          n: 15,
          std: 2.9,
          min: 4,
          max: 15,
        },
        llm_judge_falloesung_passed: { mean: 0.93, n: 15 },
      },
    },
    {
      subject: {
        id: 'meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8',
        kind: 'model',
        label: 'Llama 4 Maverick',
        provider: 'deepinfra',
      },
      config_id: 'cfg-judge-sonnet',
      metrics: {
        llm_judge_falloesung: {
          mean: 53.0,
          n: 15,
          std: 11.2,
          min: 30,
          max: 71,
          pass_rate: 0.58,
        },
        llm_judge_falloesung_grade_points: {
          mean: 5.0,
          n: 15,
          std: 3.1,
          min: 1,
          max: 10,
        },
        llm_judge_falloesung_passed: { mean: 0.58, n: 15 },
      },
    },
    {
      subject: {
        id: 'gpt-5.4',
        kind: 'model',
        label: 'GPT-5.4',
        provider: 'openai',
      },
      config_id: 'cfg-judge-mini',
      metrics: {
        llm_judge_falloesung: {
          mean: 79.1,
          n: 15,
          std: 8.0,
          min: 60,
          max: 92,
          pass_rate: 1.0,
        },
        llm_judge_falloesung_grade_points: { mean: 12.4, n: 15 },
        llm_judge_falloesung_passed: { mean: 1.0, n: 15 },
      },
    },
    {
      subject: { id: 'annotator:KindAlly', kind: 'human', label: 'KindAlly' },
      config_id: 'cfg-judge-sonnet',
      metrics: {
        llm_judge_falloesung: {
          mean: 72.3,
          n: 8,
          std: 10.0,
          min: 55,
          max: 88,
          pass_rate: 1.0,
        },
        llm_judge_falloesung_grade_points: { mean: 10.3, n: 8 },
        llm_judge_falloesung_passed: { mean: 1.0, n: 8 },
      },
    },
    {
      subject: {
        id: 'annotator:BraveOtter',
        kind: 'human',
        label: 'BraveOtter',
      },
      config_id: 'cfg-judge-sonnet',
      metrics: {
        llm_judge_falloesung: {
          mean: 58.1,
          n: 7,
          std: 12.5,
          min: 40,
          max: 80,
          pass_rate: 0.75,
        },
        llm_judge_falloesung_grade_points: { mean: 6.8, n: 7 },
        llm_judge_falloesung_passed: { mean: 0.75, n: 7 },
      },
    },
    {
      subject: { id: 'annotator:KindAlly', kind: 'human', label: 'KindAlly' },
      config_id: 'cfg-korrektur',
      metrics: { korrektur_falloesung: { mean: 80.5, n: 3, pass_rate: 1.0 } },
    },
    {
      subject: {
        id: 'gpt-5.4',
        kind: 'model',
        label: 'GPT-5.4',
        provider: 'openai',
      },
      config_id: 'cfg-bleu',
      metrics: { bleu: { mean: 0.21, n: 15, std: 0.05, min: 0.1, max: 0.3 } },
    },
  ],
  distributions: [
    {
      metric: 'llm_judge_falloesung_grade_points',
      config_id: 'cfg-judge-sonnet',
      scale: '0-18',
      bins: bins18,
      by_kind: {
        model: hist(19, [
          [4, 2],
          [5, 3],
          [8, 4],
          [9, 6],
          [10, 9],
          [12, 8],
          [13, 12],
          [14, 10],
          [15, 4],
          [17, 2],
        ]),
        human: hist(19, [
          [3, 2],
          [5, 4],
          [6, 6],
          [7, 9],
          [9, 12],
          [10, 11],
          [11, 8],
          [12, 6],
          [13, 3],
          [15, 1],
        ]),
      },
      by_subject: {
        'gpt-5.4': hist(19, [
          [10, 1],
          [12, 3],
          [13, 5],
          [14, 4],
          [15, 1],
          [17, 1],
        ]),
        'annotator:KindAlly': hist(19, [
          [7, 1],
          [9, 3],
          [10, 2],
          [12, 2],
        ]),
      },
    },
    {
      metric: 'llm_judge_falloesung',
      config_id: 'cfg-judge-sonnet',
      scale: '0-100',
      bins: bins01.map((b) => b * 100),
      by_kind: {
        model: hist(10, [
          [3, 2],
          [5, 6],
          [6, 9],
          [7, 14],
          [8, 22],
          [9, 7],
        ]),
        human: hist(10, [
          [3, 3],
          [4, 6],
          [5, 10],
          [6, 14],
          [7, 12],
          [8, 8],
          [9, 1],
        ]),
      },
      by_subject: {},
    },
  ],
}

const h = (c: string) => c.repeat(64)

/** The sections beyond the metric evaluation (synthetic values): a variant
 *  design with two imports, per-model generation outcomes, Likert ratings
 *  and preference comparisons, and the reproducibility appendix. */
export const REPORT_RECORDS_FIXTURE: Required<
  Pick<
    ReportSnapshot,
    'data' | 'generation' | 'human_evaluations' | 'reproducibility'
  >
> = {
  data: {
    task_count: 15,
    variant_designs: [
      {
        key: 'framing',
        version: 2,
        status: 'frozen',
        content_hash: h('c'),
        spec_sha256: h('s'),
        frozen_at: '2026-08-20T09:00:00Z',
        task_count: 8,
        unit_count: 2,
        cell_count: 4,
        title: 'Synthetic framing design',
        unit: 'case',
        factors: [
          {
            name: 'framing',
            type: 'nominal',
            role: 'manipulated',
            source: 'task',
            varies: 'within_unit',
            levels: ['neutral', 'loaded'],
            level_count: 2,
          },
          {
            name: 'order',
            type: 'ordinal',
            role: 'counterbalanced',
            source: 'task',
            varies: 'within_unit',
            levels: [1, 2],
            level_count: 60,
          },
        ],
        outcomes: ['correct'],
        declared_cells: null,
        provenance: { sha256: h('p'), content: { generator: 'synthetic' } },
      },
    ],
    imports: [
      {
        format: 'nested',
        mode: 'nested',
        completed_at: '2026-08-01T10:00:00Z',
        payload_sha256: h('b'),
        byte_size: 2048,
        task_count: 15,
        no_op: false,
        declared_manifest: {
          sha256: h('d'),
          content: { files: [{ name: 'cases.csv' }] },
        },
      },
      {
        format: 'nested',
        mode: 'nested',
        completed_at: '2026-08-02T10:00:00Z',
        payload_sha256: h('b'),
        byte_size: 2048,
        task_count: 0,
        no_op: true,
        declared_manifest: { sha256: h('e'), truncated: true },
      },
    ],
    import_count: 3,
    imports_truncated: true,
  },
  generation: {
    models: [
      {
        model_id: 'gpt-5.4',
        label: 'GPT-5.4',
        provider: 'openai',
        generations: 30,
        completed: 28,
        failed: 2,
        tasks: 15,
        runs_per_task: 2,
        max_runs_per_task: 2,
        refusal_rate: 0.25,
        truncation_rate: 0,
        retry_rate: 0.1,
        parse_attempted: 28,
        parse_failure_rate: 0.5,
        request_record_share: 1,
        structures: [{ key: 'plain', generations: 30 }],
      },
    ],
    structures: [{ key: 'plain', generations: 30 }],
    totals: {
      generations: 30,
      completed: 28,
      failed: 2,
      refusal_rate: 0.25,
      truncation_rate: 0,
      retry_rate: 0.1,
      parse_failure_rate: 0.5,
      request_record_share: 1,
    },
  },
  human_evaluations: {
    likert: {
      evaluator_count: 2,
      rating_count: 4,
      scale: [1, 2, 3, 4, 5],
      dimensions: [
        {
          dimension: 'accuracy',
          description: 'How accurate the answer is',
          n: 3,
          mean: 4,
          std: 1,
          distribution: [0, 0, 1, 1, 1],
          by_model: [
            { model_id: 'gpt-5.4', label: 'GPT-5.4', n: 3, mean: 4, std: 1 },
          ],
        },
        {
          dimension: 'clarity',
          description: null,
          n: 1,
          mean: 2,
          std: null,
          distribution: [0, 1, 0, 0, 0],
          by_model: [],
        },
      ],
    },
    preference: {
      evaluator_count: 1,
      comparisons: 3,
      ties: 1,
      models: [
        {
          model_id: 'gpt-5.4',
          label: 'GPT-5.4',
          comparisons: 3,
          wins: 2,
          losses: 0,
          ties: 1,
          win_rate: 2 / 3,
        },
        {
          model_id: 'claude-opus-4-7',
          label: 'Claude Opus 4.7',
          comparisons: 3,
          wins: 0,
          losses: 2,
          ties: 1,
          win_rate: 0,
        },
      ],
      pairs: [
        {
          model_a: 'claude-opus-4-7',
          label_a: 'Claude Opus 4.7',
          model_b: 'gpt-5.4',
          label_b: 'GPT-5.4',
          a_wins: 0,
          b_wins: 2,
          ties: 1,
        },
      ],
    },
  },
  reproducibility: {
    platform: { app_version: 'v20260901-aaaa-bbbb', core_api_version: '2.66' },
    label_config: { version: 'v3', sha256: h('l') },
    models: [{ id: 'gpt-5.4', provider: 'openai', label: 'GPT-5.4' }],
    prompt_structures: [
      { key: 'plain', generations: 30, definition_sha256: h('f') },
    ],
    evaluation_configs: [
      {
        id: 'cfg-judge',
        metric: 'llm_judge_falloesung',
        name: 'Judge config',
        judge_runs: [
          {
            judge_model: 'judge-model',
            samples: 30,
            parameters_sha256: h('a'),
            parameters: { temperature: 0 },
          },
        ],
      },
    ],
    variant_designs: [
      {
        key: 'framing',
        version: 2,
        status: 'frozen',
        content_hash: h('c'),
        spec_sha256: h('s'),
      },
    ],
    imports: [
      {
        payload_sha256: h('b'),
        completed_at: '2026-08-01T10:00:00Z',
        no_op: false,
      },
    ],
    analysis_runs: [
      {
        id: 'run-1',
        name: 'Framing effect',
        spec_hash: h('1'),
        spec_version: 1,
        engine_version: '1.1.0',
        frame_hash: h('2'),
        frame_sha256: h('3'),
        frame_rows: 16,
        estimates_count: 4,
        library_versions: { numpy: '2.0.0', scipy: '1.14.0' },
        lockfile_sha256: h('4'),
        seed: 7,
        completed_at: '2026-08-25T10:00:00Z',
      },
    ],
    snapshot_sha256: h('9'),
  },
}

/** An annotation-only project's snapshot: tasks and submissions, nothing else. */
export const ANNOTATION_ONLY_SNAPSHOT: ReportSnapshot = {
  generated_at: '2026-09-02T12:00:00Z',
  statistics: {
    task_count: 4,
    annotation_count: 6,
    participant_count: 2,
    model_count: 0,
    evaluation_count: 0,
  },
  methods: [],
  configs: [],
  primary_metric: null,
  primary_config_id: null,
  grade_metric: null,
  series: [],
  distributions: [],
  participants: [
    { id: 'u1', label: 'Heron', annotation_count: 4 },
    { id: 'u2', label: 'Wren', annotation_count: 2 },
  ],
  models: [],
  data: {
    task_count: 4,
    variant_designs: [],
    imports: [],
    import_count: 0,
    imports_truncated: false,
  },
  generation: {
    models: [],
    structures: [],
    totals: {
      generations: 0,
      completed: 0,
      failed: 0,
      refusal_rate: null,
      truncation_rate: null,
      retry_rate: null,
      parse_failure_rate: null,
      request_record_share: null,
    },
  },
  human_evaluations: {
    likert: {
      evaluator_count: 0,
      rating_count: 0,
      scale: [1, 2, 3, 4, 5],
      dimensions: [],
    },
    preference: {
      evaluator_count: 0,
      comparisons: 0,
      ties: 0,
      models: [],
      pairs: [],
    },
  },
  reproducibility: {
    platform: { app_version: null, core_api_version: '2.66' },
    label_config: { version: 'v1', sha256: h('l') },
    models: [],
    prompt_structures: [],
    evaluation_configs: [],
    variant_designs: [],
    imports: [],
    analysis_runs: [],
    snapshot_sha256: h('7'),
  },
}

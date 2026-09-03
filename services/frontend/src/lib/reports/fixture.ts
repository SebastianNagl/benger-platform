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
  statistics: { task_count: 15, annotation_count: 224, participant_count: 36, model_count: 4, evaluation_count: 3626 },
  methods: [
    { id: 'llm_judge_falloesung', name: 'Falllösung LLM Judge', category: 'llm_judge', scale: '0-100', higher_is_better: true },
    { id: 'llm_judge_falloesung_grade_points', name: 'Notenpunkte (Falllösung)', category: 'llm_judge', scale: '0-18', higher_is_better: true, derived: true },
    { id: 'llm_judge_falloesung_passed', name: 'Bestanden (Falllösung)', category: 'llm_judge', scale: '0-1', higher_is_better: true, derived: true },
    { id: 'korrektur_falloesung', name: 'Korrektur (Standard Falllösung)', category: 'human', scale: '0-100', higher_is_better: true },
    { id: 'bleu', name: 'BLEU', category: 'lexical', scale: '0-1', higher_is_better: true },
  ],
  configs: [
    { id: 'cfg-judge-sonnet', metric: 'llm_judge_falloesung', judge_model: 'claude-sonnet-4-6', judge_label: 'Claude Sonnet 4.6', name: 'Notenpunkte (Abo-Modell)', n: 900 },
    { id: 'cfg-judge-mini', metric: 'llm_judge_falloesung', judge_model: 'gpt-5-mini', judge_label: 'GPT-5 mini', name: 'Notenpunkte (Gratis-Modell)', n: 420 },
    { id: 'cfg-korrektur', metric: 'korrektur_falloesung', judge_model: null, judge_label: null, name: 'Korrektur', n: 184 },
    { id: 'cfg-bleu', metric: 'bleu', judge_model: null, judge_label: null, name: null, n: 300 },
  ],
  primary_metric: 'llm_judge_falloesung',
  primary_config_id: 'cfg-judge-sonnet',
  grade_metric: 'llm_judge_falloesung_grade_points',
  models: [
    { id: 'gpt-5.4', kind: 'model', label: 'GPT-5.4', provider: 'openai', is_custom: false },
    { id: 'claude-opus-4-7', kind: 'model', label: 'Claude Opus 4.7', provider: 'anthropic', is_custom: false },
    { id: 'deepseek-ai/DeepSeek-V4-Flash', kind: 'model', label: 'DeepSeek V4 Flash', provider: 'deepinfra', is_custom: false },
    { id: 'meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8', kind: 'model', label: 'Llama 4 Maverick', provider: 'deepinfra', is_custom: false },
  ],
  participants: [
    { id: 'u1', label: 'KindAlly', annotation_count: 8 },
    { id: 'u2', label: 'BraveOtter', annotation_count: 7 },
    { id: 'u3', label: 'QuietRiver', annotation_count: 6 },
  ],
  series: [
    { subject: { id: 'gpt-5.4', kind: 'model', label: 'GPT-5.4', provider: 'openai' }, config_id: 'cfg-judge-sonnet',
      metrics: { llm_judge_falloesung: { mean: 84.7, n: 15, std: 6.1, min: 70, max: 94, pass_rate: 1.0 }, llm_judge_falloesung_grade_points: { mean: 13.9, n: 15, std: 1.8, min: 10, max: 17 }, llm_judge_falloesung_passed: { mean: 1.0, n: 15 } } },
    { subject: { id: 'claude-opus-4-7', kind: 'model', label: 'Claude Opus 4.7', provider: 'anthropic' }, config_id: 'cfg-judge-sonnet',
      metrics: { llm_judge_falloesung: { mean: 83.0, n: 15, std: 7.0, min: 66, max: 95, pass_rate: 1.0 }, llm_judge_falloesung_grade_points: { mean: 13.6, n: 15, std: 2.0, min: 9, max: 17 }, llm_judge_falloesung_passed: { mean: 1.0, n: 15 } } },
    { subject: { id: 'deepseek-ai/DeepSeek-V4-Flash', kind: 'model', label: 'DeepSeek V4 Flash', provider: 'deepinfra' }, config_id: 'cfg-judge-sonnet',
      metrics: { llm_judge_falloesung: { mean: 70.2, n: 15, std: 9.4, min: 51, max: 88, pass_rate: 0.93 }, llm_judge_falloesung_grade_points: { mean: 9.8, n: 15, std: 2.9, min: 4, max: 15 }, llm_judge_falloesung_passed: { mean: 0.93, n: 15 } } },
    { subject: { id: 'meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8', kind: 'model', label: 'Llama 4 Maverick', provider: 'deepinfra' }, config_id: 'cfg-judge-sonnet',
      metrics: { llm_judge_falloesung: { mean: 53.0, n: 15, std: 11.2, min: 30, max: 71, pass_rate: 0.58 }, llm_judge_falloesung_grade_points: { mean: 5.0, n: 15, std: 3.1, min: 1, max: 10 }, llm_judge_falloesung_passed: { mean: 0.58, n: 15 } } },
    { subject: { id: 'gpt-5.4', kind: 'model', label: 'GPT-5.4', provider: 'openai' }, config_id: 'cfg-judge-mini',
      metrics: { llm_judge_falloesung: { mean: 79.1, n: 15, std: 8.0, min: 60, max: 92, pass_rate: 1.0 }, llm_judge_falloesung_grade_points: { mean: 12.4, n: 15 }, llm_judge_falloesung_passed: { mean: 1.0, n: 15 } } },
    { subject: { id: 'annotator:KindAlly', kind: 'human', label: 'KindAlly' }, config_id: 'cfg-judge-sonnet',
      metrics: { llm_judge_falloesung: { mean: 72.3, n: 8, std: 10.0, min: 55, max: 88, pass_rate: 1.0 }, llm_judge_falloesung_grade_points: { mean: 10.3, n: 8 }, llm_judge_falloesung_passed: { mean: 1.0, n: 8 } } },
    { subject: { id: 'annotator:BraveOtter', kind: 'human', label: 'BraveOtter' }, config_id: 'cfg-judge-sonnet',
      metrics: { llm_judge_falloesung: { mean: 58.1, n: 7, std: 12.5, min: 40, max: 80, pass_rate: 0.75 }, llm_judge_falloesung_grade_points: { mean: 6.8, n: 7 }, llm_judge_falloesung_passed: { mean: 0.75, n: 7 } } },
    { subject: { id: 'annotator:KindAlly', kind: 'human', label: 'KindAlly' }, config_id: 'cfg-korrektur',
      metrics: { korrektur_falloesung: { mean: 80.5, n: 3, pass_rate: 1.0 } } },
    { subject: { id: 'gpt-5.4', kind: 'model', label: 'GPT-5.4', provider: 'openai' }, config_id: 'cfg-bleu',
      metrics: { bleu: { mean: 0.21, n: 15, std: 0.05, min: 0.1, max: 0.3 } } },
  ],
  distributions: [
    { metric: 'llm_judge_falloesung_grade_points', config_id: 'cfg-judge-sonnet', scale: '0-18', bins: bins18,
      by_kind: { model: hist(19, [[4, 2], [5, 3], [8, 4], [9, 6], [10, 9], [12, 8], [13, 12], [14, 10], [15, 4], [17, 2]]), human: hist(19, [[3, 2], [5, 4], [6, 6], [7, 9], [9, 12], [10, 11], [11, 8], [12, 6], [13, 3], [15, 1]]) },
      by_subject: { 'gpt-5.4': hist(19, [[10, 1], [12, 3], [13, 5], [14, 4], [15, 1], [17, 1]]), 'annotator:KindAlly': hist(19, [[7, 1], [9, 3], [10, 2], [12, 2]]) } },
    { metric: 'llm_judge_falloesung', config_id: 'cfg-judge-sonnet', scale: '0-100', bins: bins01.map((b) => b * 100),
      by_kind: { model: hist(10, [[3, 2], [5, 6], [6, 9], [7, 14], [8, 22], [9, 7]]), human: hist(10, [[3, 3], [4, 6], [5, 10], [6, 14], [7, 12], [8, 8], [9, 1]]) },
      by_subject: {} },
  ],
}

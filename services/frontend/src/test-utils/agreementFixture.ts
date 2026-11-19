import type { AnnotatorAgreementSummary } from '@/lib/api/agreement'

/** Synthetic agreement: the three-annotator example of the API tests. */
export const AGREEMENT_FIXTURE: AnnotatorAgreementSummary = {
  overlap_task_count: 4,
  annotator_count: 3,
  controls: [
    {
      control: 'label',
      type: 'choices',
      score_type: 'categorical',
      multi_select: false,
      n_items: 4,
      n_annotators: 3,
      n_annotations: 12,
      categories: ['x', 'y'],
      fleiss_kappa: 0.3333,
      cohens_kappa_mean: 0.4,
      percent_agreement: 0.5,
      pearson_r_mean: null,
      mean_absolute_deviation: null,
      pairs: [
        {
          annotator_a: 'Ash',
          annotator_b: 'Birch',
          n_items: 4,
          cohens_kappa: 0.5,
        },
        {
          annotator_a: 'Ash',
          annotator_b: 'Cedar',
          n_items: 4,
          cohens_kappa: 0.2,
        },
        {
          annotator_a: 'Birch',
          annotator_b: 'Cedar',
          n_items: 4,
          cohens_kappa: 0.5,
        },
      ],
      pairs_total: 3,
    },
    {
      control: 'score',
      type: 'number',
      score_type: 'numeric',
      multi_select: false,
      n_items: 4,
      n_annotators: 2,
      n_annotations: 8,
      categories: [],
      fleiss_kappa: null,
      cohens_kappa_mean: null,
      percent_agreement: null,
      pearson_r_mean: 1,
      mean_absolute_deviation: 0.5,
      pairs: [
        { annotator_a: 'Ash', annotator_b: 'Birch', n_items: 4, pearson_r: 1 },
      ],
      pairs_total: 1,
    },
  ],
  unsupported_controls: [{ control: 'comment', type: 'textarea' }],
}

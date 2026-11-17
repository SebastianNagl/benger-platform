/**
 * The prediction/reference option contract.
 *
 * These exist because the project-creation wizard used to build its own
 * option lists and omitted the human prediction side entirely. A judge that
 * grades a submitted answer could therefore not be configured there at all:
 * the only choices were "all model outputs" and `model:<field>`. The config
 * that produced matched no subject in an exam project, so a batch evaluation
 * dispatched zero cells and reported success having graded nothing.
 *
 * Ordering is part of the contract, not an implementation detail: keeping
 * `__all_model__` first is what preserves the positional default for
 * benchmark metrics that legitimately compare model outputs.
 */
import {
  buildPredictionFieldOptions,
  buildReferenceFieldOptions,
  groupPredictionFieldOptions,
  matchFieldOption,
  resolveDefaultFieldSelection,
} from '../evaluation-types'

const FIELDS = {
  model_response_fields: ['loesung', 'gliederung'],
  human_annotation_fields: ['loesung', 'gliederung'],
  reference_fields: ['musterloesung'],
}

describe('buildPredictionFieldOptions', () => {
  it('offers both bulk selectors and both role-prefixed sides, in order', () => {
    expect(buildPredictionFieldOptions(FIELDS).map((o) => o.value)).toEqual([
      '__all_model__',
      '__all_human__',
      'model:loesung',
      'model:gliederung',
      'human:loesung',
      'human:gliederung',
    ])
  })

  it('keeps __all_model__ first so a benchmark metric still defaults to it', () => {
    expect(buildPredictionFieldOptions(FIELDS)[0].value).toBe('__all_model__')
  })

  it('offers the human side even when the project has no fields yet', () => {
    const opts = buildPredictionFieldOptions({
      model_response_fields: [],
      human_annotation_fields: [],
    })
    expect(opts.map((o) => o.value)).toEqual(['__all_model__', '__all_human__'])
  })

  it('tags each option so callers can group and label it', () => {
    const byValue = Object.fromEntries(
      buildPredictionFieldOptions(FIELDS).map((o) => [o.value, o]),
    )
    expect(byValue['__all_human__'].kind).toBe('special')
    expect(byValue['__all_human__'].labelKey).toBeDefined()
    expect(byValue['model:loesung'].kind).toBe('model')
    expect(byValue['human:loesung'].kind).toBe('human')
    expect(byValue['human:loesung'].labelKey).toBeUndefined()
  })
})

describe('buildReferenceFieldOptions', () => {
  it('lists human annotation fields before task-data columns', () => {
    expect(buildReferenceFieldOptions(FIELDS).map((o) => o.value)).toEqual([
      'human:loesung',
      'human:gliederung',
      'musterloesung',
    ])
  })

  it('marks task-data columns as data', () => {
    const opts = buildReferenceFieldOptions(FIELDS)
    expect(opts.find((o) => o.value === 'musterloesung')!.kind).toBe('data')
  })
})

describe('resolveDefaultFieldSelection', () => {
  const options = buildPredictionFieldOptions(FIELDS)

  it('falls back positionally when the metric declares nothing', () => {
    expect(
      resolveDefaultFieldSelection(undefined, options, '__all_model__'),
    ).toEqual(['__all_model__'])
  })

  it('selects only the first declared field that is on offer', () => {
    // The declaration is an ordered preference. Selecting every offered entry
    // made `__all_human__` grade the outline and the notes of a submission
    // against the rubric, each as if it were the answer.
    expect(
      resolveDefaultFieldSelection(
        ['human:loesung', '__all_human__'],
        options,
        '__all_model__',
      ),
    ).toEqual(['human:loesung'])
  })

  it('takes the next declared field when an earlier one is not offered', () => {
    // A judge whose first choice does not exist on this project must still
    // grade a declared field. Falling back here is what silently aimed it at
    // the model side.
    expect(
      resolveDefaultFieldSelection(
        ['human:nonexistent', 'human:loesung'],
        options,
        '__all_model__',
      ),
    ).toEqual(['human:loesung'])
  })

  it('uses a declared bulk selector only as the fallback it is', () => {
    expect(
      resolveDefaultFieldSelection(
        ['human:nonexistent', '__all_human__'],
        options,
        '__all_model__',
      ),
    ).toEqual(['__all_human__'])
  })

  it('falls back when nothing declared is on offer', () => {
    expect(
      resolveDefaultFieldSelection(
        ['human:nonexistent'],
        options,
        '__all_model__',
      ),
    ).toEqual(['__all_model__'])
  })

  it('returns nothing when there is nothing to fall back to', () => {
    expect(resolveDefaultFieldSelection(undefined, [], '')).toEqual([])
  })
})

describe('groupPredictionFieldOptions', () => {
  it('heads the bulk, model and human options, in option order', () => {
    const groups = groupPredictionFieldOptions(
      buildPredictionFieldOptions(FIELDS),
    )
    expect(groups.map((g) => g.labelKey)).toEqual([
      'evaluationBuilder.fields.bulkSelection',
      'evaluationBuilder.fields.modelResponseFields',
      'evaluationBuilder.fields.humanAnnotationFields',
    ])
    expect(groups.map((g) => g.options.map((o) => o.value))).toEqual([
      ['__all_model__', '__all_human__'],
      ['model:loesung', 'model:gliederung'],
      ['human:loesung', 'human:gliederung'],
    ])
  })

  it('keeps every option exactly once and in order', () => {
    const options = buildPredictionFieldOptions(FIELDS)
    expect(
      groupPredictionFieldOptions(options).flatMap((g) => g.options),
    ).toEqual(options)
  })

  it('drops a group that has no options', () => {
    const groups = groupPredictionFieldOptions(
      buildPredictionFieldOptions({
        model_response_fields: [],
        human_annotation_fields: ['loesung'],
      }),
    )
    expect(groups.map((g) => g.kind)).toEqual(['special', 'human'])
  })
})

describe('matchFieldOption', () => {
  const prediction = buildPredictionFieldOptions(FIELDS)
  const reference = buildReferenceFieldOptions(FIELDS)
  const HUMAN_JUDGE = ['human:loesung', '__all_human__']
  const value = (
    stored: string,
    role: 'prediction' | 'reference',
    declared?: string[],
  ) =>
    matchFieldOption(
      stored,
      role === 'prediction' ? prediction : reference,
      role,
      declared,
    )?.value

  it('returns an option the stored value names exactly', () => {
    expect(value('human:loesung', 'prediction', HUMAN_JUDGE)).toBe(
      'human:loesung',
    )
    expect(value('model:loesung', 'prediction', HUMAN_JUDGE)).toBe(
      'model:loesung',
    )
    expect(value('__all_human__', 'prediction')).toBe('__all_human__')
    expect(value('musterloesung', 'reference')).toBe('musterloesung')
  })

  it('reads a bare prediction field on the side the metric declares', () => {
    expect(value('loesung', 'prediction', HUMAN_JUDGE)).toBe('human:loesung')
    expect(value('loesung', 'prediction', ['model:loesung'])).toBe(
      'model:loesung',
    )
    expect(value('loesung', 'prediction', ['__all_model__'])).toBe(
      'model:loesung',
    )
  })

  it('reads a bare prediction field as the model side when nothing is declared, as the server does', () => {
    expect(value('loesung', 'prediction')).toBe('model:loesung')
    expect(value('loesung', 'prediction', [])).toBe('model:loesung')
  })

  it('takes the only side offered, whatever the metric declares', () => {
    const humanOnly = buildPredictionFieldOptions({
      model_response_fields: [],
      human_annotation_fields: ['loesung'],
    })
    expect(matchFieldOption('loesung', humanOnly, 'prediction')?.value).toBe(
      'human:loesung',
    )
    const modelOnly = buildPredictionFieldOptions({
      model_response_fields: ['loesung'],
      human_annotation_fields: [],
    })
    expect(
      matchFieldOption('loesung', modelOnly, 'prediction', HUMAN_JUDGE)?.value,
    ).toBe('model:loesung')
  })

  it('maps a task-data reference onto its data column', () => {
    expect(value('task.musterloesung', 'reference')).toBe('musterloesung')
  })

  it('leaves a bare reference alone: it names an annotation field or a task column', () => {
    expect(value('loesung', 'reference')).toBeUndefined()
  })

  it('matches nothing for a field no option carries', () => {
    expect(value('notes', 'prediction', HUMAN_JUDGE)).toBeUndefined()
    expect(value('human:notes', 'prediction')).toBeUndefined()
    expect(value('task.sachverhalt', 'reference')).toBeUndefined()
    expect(value('', 'prediction')).toBeUndefined()
    // A task-data prefix is a reference spelling only.
    expect(value('task.musterloesung', 'prediction')).toBeUndefined()
  })
})

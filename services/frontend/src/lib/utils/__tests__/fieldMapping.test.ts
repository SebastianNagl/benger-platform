import { applyFieldMappings, suggestFieldMappings } from '../fieldMapping'

describe('applyFieldMappings', () => {
  it('applies field mappings to data', () => {
    const data = [
      { oldField1: 'value1', oldField2: 'value2' },
      { oldField1: 'value3', oldField2: 'value4' },
    ]
    const mappings = [
      {
        source: 'oldField1',
        target: 'newField1',
        confidence: 1,
        type: 'exact' as const,
      },
      {
        source: 'oldField2',
        target: 'newField2',
        confidence: 1,
        type: 'exact' as const,
      },
    ]

    const result = applyFieldMappings(data, mappings)

    expect(result).toEqual([
      { newField1: 'value1', newField2: 'value2' },
      { newField1: 'value3', newField2: 'value4' },
    ])
  })

  it('handles missing fields gracefully', () => {
    const data = [{ field1: 'value1' }]
    const mappings = [
      {
        source: 'field1',
        target: 'mappedField',
        confidence: 1,
        type: 'exact' as const,
      },
      {
        source: 'nonexistent',
        target: 'missingField',
        confidence: 1,
        type: 'exact' as const,
      },
    ]

    const result = applyFieldMappings(data, mappings)

    expect(result).toEqual([
      {
        mappedField: 'value1',
      },
    ])
  })

  it('includes unmapped fields with prefix', () => {
    const data = [{ field1: 'value1', field2: 'value2', field3: 'value3' }]
    const mappings = [
      {
        source: 'field1',
        target: 'mappedField',
        confidence: 1,
        type: 'exact' as const,
      },
    ]

    const result = applyFieldMappings(data, mappings)

    expect(result).toEqual([
      {
        mappedField: 'value1',
        _unmapped_field2: 'value2',
        _unmapped_field3: 'value3',
      },
    ])
  })

  it('handles empty data', () => {
    const result = applyFieldMappings(
      [],
      [
        {
          source: 'field',
          target: 'target',
          confidence: 1,
          type: 'exact' as const,
        },
      ]
    )
    expect(result).toEqual([])
  })
})

describe('suggestFieldMappings', () => {
  it('suggests exact matches', () => {
    const sourceFields = ['question', 'answer', 'context']
    const targetFields = ['question', 'answer', 'context']

    const suggestions = suggestFieldMappings(sourceFields, targetFields)

    expect(suggestions.mappings).toHaveLength(3)
    expect(suggestions.mappings).toContainEqual({
      source: 'question',
      target: 'question',
      confidence: 1,
      type: 'exact',
    })
    expect(suggestions.mappings).toContainEqual({
      source: 'answer',
      target: 'answer',
      confidence: 1,
      type: 'exact',
    })
    expect(suggestions.mappings).toContainEqual({
      source: 'context',
      target: 'context',
      confidence: 1,
      type: 'exact',
    })
    expect(suggestions.quality).toBe('high')
  })

  it('suggests fuzzy matches for similar fields', () => {
    const sourceFields = ['quest', 'ans', 'ctx']
    const targetFields = ['question', 'answer', 'context']

    const suggestions = suggestFieldMappings(sourceFields, targetFields)

    expect(suggestions.mappings.length).toBeGreaterThan(0)
    const questionMapping = suggestions.mappings.find(
      (m) => m.source === 'quest'
    )
    expect(questionMapping).toBeTruthy()
    expect(questionMapping?.target).toBe('question')
    expect(questionMapping?.type).toBe('fuzzy')
  })

  it('suggests German to English mappings', () => {
    const sourceFields = ['frage', 'antwort', 'rechtsfrage']
    const targetFields = ['question', 'answer', 'legal_question']

    const suggestions = suggestFieldMappings(sourceFields, targetFields)

    const frageMapping = suggestions.mappings.find((m) => m.source === 'frage')
    expect(frageMapping).toBeTruthy()
    expect(frageMapping?.target).toBe('question')
    expect(frageMapping?.confidence).toBeGreaterThan(0.8)
  })

  it('handles empty source fields', () => {
    const suggestions = suggestFieldMappings([], ['question', 'answer'])
    expect(suggestions.mappings).toEqual([])
    expect(suggestions.unmappedSource).toEqual([])
    expect(suggestions.unmappedTarget).toEqual(['question', 'answer'])
    expect(suggestions.quality).toBe('low')
  })

  it('handles empty target fields', () => {
    const suggestions = suggestFieldMappings(['question', 'answer'], [])
    expect(suggestions.mappings).toEqual([])
    expect(suggestions.unmappedSource).toEqual(['question', 'answer'])
    expect(suggestions.unmappedTarget).toEqual([])
    expect(suggestions.quality).toBe('low')
  })

  it('prioritizes exact matches over fuzzy matches', () => {
    const sourceFields = ['question', 'quest']
    const targetFields = ['question', 'questionnaire']

    const suggestions = suggestFieldMappings(sourceFields, targetFields)

    const exactMatch = suggestions.mappings.find(
      (m) => m.source === 'question' && m.target === 'question'
    )
    expect(exactMatch).toBeTruthy()
    expect(exactMatch?.type).toBe('exact')
    expect(exactMatch?.confidence).toBe(1)
  })

  it('detects unmapped fields correctly', () => {
    const sourceFields = ['field1', 'field2', 'field3']
    const targetFields = ['field1', 'otherField']

    const suggestions = suggestFieldMappings(sourceFields, targetFields)

    expect(suggestions.unmappedSource).toContain('field2')
    expect(suggestions.unmappedSource).toContain('field3')
    expect(suggestions.unmappedTarget).toContain('otherField')
  })

  it('calculates mapping quality based on coverage and confidence', () => {
    // High quality: all fields mapped with high confidence
    const highQuality = suggestFieldMappings(
      ['question', 'answer'],
      ['question', 'answer']
    )
    expect(highQuality.quality).toBe('high')

    // Low quality: no fields mapped
    const lowQuality = suggestFieldMappings(
      ['foo', 'bar'],
      ['question', 'answer']
    )
    expect(lowQuality.quality).toBe('low')
  })

  it('uses content-based matching when sample data provided', () => {
    const sourceFields = ['date_field', 'number_field']
    const targetFields = ['creation_date', 'item_count']
    const sampleData = [
      { date_field: '2024-01-01', number_field: 42 },
      { date_field: '2024-01-02', number_field: 43 },
    ]

    const suggestions = suggestFieldMappings(
      sourceFields,
      targetFields,
      sampleData
    )

    const dateMapping = suggestions.mappings.find(
      (m) => m.source === 'date_field'
    )
    expect(dateMapping).toBeTruthy()
    expect(dateMapping?.target).toContain('date')
  })
})

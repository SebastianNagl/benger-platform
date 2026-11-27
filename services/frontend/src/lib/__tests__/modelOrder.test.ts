import { groupModelsByProvider } from '../modelOrder'

describe('groupModelsByProvider', () => {
  it('keeps the list order of the providers and of the models in each', () => {
    const models = [
      { id: 'gpt-6.2-astra', provider: 'OpenAI' },
      { id: 'gpt-6-astra', provider: 'OpenAI' },
      { id: 'claude-opus-5-5', provider: 'Anthropic' },
      { id: 'claude-haiku-5-5', provider: 'Anthropic' },
      { id: 'gemini-4-carbon', provider: 'Google' },
    ]
    expect(groupModelsByProvider(models)).toEqual([
      { provider: 'OpenAI', models: [models[0], models[1]] },
      { provider: 'Anthropic', models: [models[2], models[3]] },
      { provider: 'Google', models: [models[4]] },
    ])
  })

  it('collects a provider that appears again into its first group', () => {
    const models = [
      { id: 'a1', provider: 'OpenAI' },
      { id: 'b1', provider: 'Anthropic' },
      { id: 'a2', provider: 'OpenAI' },
    ]
    expect(
      groupModelsByProvider(models).map((group) => [
        group.provider,
        group.models.map((model) => model.id),
      ]),
    ).toEqual([
      ['OpenAI', ['a1', 'a2']],
      ['Anthropic', ['b1']],
    ])
  })

  it('returns no groups for no models', () => {
    expect(groupModelsByProvider([])).toEqual([])
  })
})

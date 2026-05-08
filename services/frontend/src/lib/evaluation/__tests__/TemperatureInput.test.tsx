/**
 * Tests for TemperatureInput — the eval-side judge temperature picker.
 * Locks the recommended-value badge state machine + reset link wired in
 * for migration 046.
 *
 * @jest-environment jsdom
 */

import { render, screen, fireEvent } from '@testing-library/react'
import React from 'react'
import { TemperatureInput } from '../TemperatureInput'

const baseModel = {
  id: 'gpt-4o',
  name: 'GPT-4o',
  provider: 'openai',
  model_type: 'chat',
  capabilities: ['text-generation'],
  is_active: true,
  created_at: null,
}

const modelWithEvalRec = {
  ...baseModel,
  recommended_parameters: {
    default: { max_tokens: 4000 },
    generation: { temperature: 0.7 },
    evaluation: { temperature: 0.0 },
    provenance: { source: 'docs', retrieved: '2026-05-07' },
  },
}

const modelWithoutRec = {
  ...baseModel,
  id: 'community-model',
  recommended_parameters: null,
}

const fixedTempModel = {
  ...baseModel,
  id: 'gpt-5',
  parameter_constraints: {
    temperature: { supported: false, required_value: 1.0 },
  },
  recommended_parameters: {
    default: { temperature: 1.0 },
    provenance: { source: 'docs', retrieved: '2026-05-07' },
  },
}

let mockModels: any[] = []

jest.mock('@/hooks/useModels', () => ({
  useModels: jest.fn(() => ({
    models: mockModels,
    loading: false,
    error: null,
    refetch: jest.fn(),
    hasApiKeys: true,
    apiKeyStatus: null,
  })),
}))

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (_k: string, fallback?: string) => fallback || _k,
    locale: 'de',
    setLocale: jest.fn(),
  }),
}))

describe('TemperatureInput', () => {
  beforeEach(() => {
    mockModels = []
  })

  it('renders the recommended value when the model has an evaluation-mode rec', () => {
    mockModels = [modelWithEvalRec]
    render(<TemperatureInput judgeModelId="gpt-4o" value={0.0} onChange={jest.fn()} />)
    // matches → no reset link, just the recommendation text
    expect(screen.getByText(/Empfehlung/i).textContent).toContain('0')
    expect(screen.queryByText(/Zurücksetzen/)).not.toBeInTheDocument()
  })

  it('shows the reset link when the user value diverges from the recommendation', () => {
    mockModels = [modelWithEvalRec]
    const onChange = jest.fn()
    render(<TemperatureInput judgeModelId="gpt-4o" value={0.5} onChange={onChange} />)
    const resetBtn = screen.getByText(/Zurücksetzen/)
    expect(resetBtn).toBeInTheDocument()
    fireEvent.click(resetBtn)
    // Reset clicks back to the eval-mode recommended value (0.0).
    expect(onChange).toHaveBeenCalledWith(0)
  })

  it('shows "Keine Empfehlung" when the model has no recommendations at all', () => {
    mockModels = [modelWithoutRec]
    render(<TemperatureInput judgeModelId="community-model" value={0.5} onChange={jest.fn()} />)
    expect(screen.getByText(/Keine Empfehlung$/)).toBeInTheDocument()
  })

  it('hides the recommendation badge entirely for fixed-temperature models', () => {
    // The constraint-fixed branch already locks the input visually; the
    // badge is suppressed so it doesn't double up with the "Fixed at X" pill.
    mockModels = [fixedTempModel]
    render(<TemperatureInput judgeModelId="gpt-5" value={1.0} onChange={jest.fn()} />)
    expect(screen.queryByText(/^Empfehlung/)).not.toBeInTheDocument()
  })
})

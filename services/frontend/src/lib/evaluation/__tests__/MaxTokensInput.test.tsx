/**
 * Tests for MaxTokensInput — the eval-side judge max-tokens picker.
 * Same badge/reset contract as TemperatureInput; locks the migration-046
 * recommended-value surface.
 *
 * @jest-environment jsdom
 */

import { render, screen, fireEvent } from '@testing-library/react'
import React from 'react'
import { MaxTokensInput } from '../MaxTokensInput'

const baseModel = {
  id: 'gpt-4o',
  name: 'GPT-4o',
  provider: 'openai',
  model_type: 'chat',
  capabilities: ['text-generation'],
  is_active: true,
  created_at: null,
}

const modelWithRec = {
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

describe('MaxTokensInput', () => {
  beforeEach(() => {
    mockModels = []
  })

  it('renders the recommended value (default-block fallback for both modes)', () => {
    mockModels = [modelWithRec]
    render(<MaxTokensInput judgeModelId="gpt-4o" value={4000} onChange={jest.fn()} />)
    expect(screen.getByText(/Empfehlung/i).textContent).toContain('4000')
    expect(screen.queryByText(/Zurücksetzen/)).not.toBeInTheDocument()
  })

  it('shows reset link when user value diverges from recommendation', () => {
    mockModels = [modelWithRec]
    const onChange = jest.fn()
    render(<MaxTokensInput judgeModelId="gpt-4o" value={500} onChange={onChange} />)
    const resetBtn = screen.getByText(/Zurücksetzen/)
    fireEvent.click(resetBtn)
    expect(onChange).toHaveBeenCalledWith(4000)
  })

  it('falls back to the fallback value when value is undefined', () => {
    mockModels = [modelWithRec]
    render(<MaxTokensInput judgeModelId="gpt-4o" value={undefined} onChange={jest.fn()} fallback={500} />)
    // Reset link should appear since fallback (500) ≠ recommendation (4000).
    expect(screen.getByText(/Zurücksetzen/)).toBeInTheDocument()
  })

  it('shows "Keine Empfehlung" when the model has no recommendations', () => {
    mockModels = [modelWithoutRec]
    render(<MaxTokensInput judgeModelId="community-model" value={500} onChange={jest.fn()} />)
    expect(screen.getByText(/Keine Empfehlung$/)).toBeInTheDocument()
  })

  it('emits the input value via onChange when user edits the field', () => {
    mockModels = [modelWithRec]
    const onChange = jest.fn()
    render(<MaxTokensInput judgeModelId="gpt-4o" value={4000} onChange={onChange} />)
    const input = screen.getByRole('spinbutton')
    fireEvent.change(input, { target: { value: '2000' } })
    expect(onChange).toHaveBeenCalledWith(2000)
  })
})

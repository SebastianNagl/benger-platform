/**
 * @jest-environment jsdom
 */

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { DimensionsEditor } from '../DimensionsEditor'
import type { CustomCriteriaDefinition } from '@/lib/api/evaluation-types'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (_key: string, fallback?: string) => fallback || _key,
  }),
}))

function Harness(props: {
  initial?: Record<string, CustomCriteriaDefinition>
}) {
  const [value, setValue] = useState(props.initial || {})
  return <DimensionsEditor value={value} onChange={setValue} />
}

const GRUNDPRINZIPIEN: Record<string, CustomCriteriaDefinition> = {
  result_correctness: { name: 'Ergebnisrichtigkeit', description: '', rubric: '', max_score: 40 },
  legal_knowledge: { name: 'Rechtskenntnis', description: '', rubric: '', max_score: 25 },
  subsumption: { name: 'Subsumtion', description: '', rubric: '', max_score: 25 },
  clarity: { name: 'Klarheit', description: '', rubric: '', max_score: 10 },
}

describe('DimensionsEditor', () => {
  it('shows empty state when no dimensions defined', () => {
    render(<Harness />)
    expect(
      screen.getByText(/No dimensions defined/i)
    ).toBeInTheDocument()
  })

  it('renders one row per dimension when value is provided', () => {
    render(<Harness initial={GRUNDPRINZIPIEN} />)
    expect(screen.getAllByPlaceholderText('result_correctness').length).toBeGreaterThanOrEqual(1)
    // 4 max_score number inputs (one per row)
    const maxInputs = screen.getAllByRole('spinbutton')
    expect(maxInputs).toHaveLength(4)
  })

  it('shows running total of max_score and colours green at 100', () => {
    render(<Harness initial={GRUNDPRINZIPIEN} />)
    expect(screen.getByText('100')).toBeInTheDocument()
  })

  it('adds a new empty row when "Add dimension" clicked', async () => {
    const user = userEvent.setup()
    render(<Harness initial={{}} />)
    await user.click(screen.getByRole('button', { name: /Add dimension/i }))
    // Now there should be one row with max=10 (default)
    const maxInputs = screen.getAllByRole('spinbutton') as HTMLInputElement[]
    expect(maxInputs).toHaveLength(1)
    expect(maxInputs[0].value).toBe('10')
  })

  it('removes a row when trash icon clicked', async () => {
    const user = userEvent.setup()
    render(<Harness initial={GRUNDPRINZIPIEN} />)
    expect(screen.getAllByRole('spinbutton')).toHaveLength(4)
    const removeButtons = screen.getAllByRole('button', { name: /Remove/i })
    await user.click(removeButtons[0])
    expect(screen.getAllByRole('spinbutton')).toHaveLength(3)
  })

  it('flags duplicate keys with an error message', async () => {
    const user = userEvent.setup()
    render(<Harness initial={{}} />)
    await user.click(screen.getByRole('button', { name: /Add dimension/i }))
    await user.click(screen.getByRole('button', { name: /Add dimension/i }))
    const keyInputs = screen.getAllByPlaceholderText('result_correctness') as HTMLInputElement[]
    await user.type(keyInputs[0], 'foo')
    await user.type(keyInputs[1], 'foo')
    expect(screen.getByText(/Duplicate keys/i)).toBeInTheDocument()
  })

  it('flags invalid keys (non snake_case) with an error message', async () => {
    const user = userEvent.setup()
    render(<Harness initial={{}} />)
    await user.click(screen.getByRole('button', { name: /Add dimension/i }))
    const keyInput = screen.getByPlaceholderText('result_correctness') as HTMLInputElement
    await user.type(keyInput, 'BadKey-1')
    expect(screen.getByText(/snake_case/i)).toBeInTheDocument()
  })
})

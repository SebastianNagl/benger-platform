/**
 * @jest-environment jsdom
 */

import { fireEvent, render, screen } from '@testing-library/react'
import { useState } from 'react'
import {
  patternSetCodes,
  TextPatternEditor,
  textPatternReady,
  type TextPatternParameters,
} from '../TextPatternEditor'

jest.mock('@/contexts/I18nContext', () =>
  require('@/test-utils/i18nMock').i18nMock('en'),
)

const SET = {
  name: 'signals',
  version: '1',
  codes: {
    cites: { mode: 'any', patterns: ['§\\s?\\d+'] },
    hedge: { mode: 'any', patterns: ['perhaps'] },
  },
}

function Harness({ initial }: { initial: TextPatternParameters }) {
  const [params, setParams] = useState<TextPatternParameters>(initial)
  return (
    <>
      <TextPatternEditor
        parameters={params}
        onChange={(patch) => setParams((p) => ({ ...p, ...patch }))}
      />
      <output data-testid="params">{JSON.stringify(params)}</output>
      <output data-testid="ready">{String(textPatternReady(params))}</output>
    </>
  )
}

const params = () => JSON.parse(screen.getByTestId('params').textContent!)

describe('TextPatternEditor', () => {
  it('lists the codes of a well-formed set only', () => {
    expect(patternSetCodes(SET)).toEqual(['cites', 'hedge'])
    expect(patternSetCodes({ name: 'x', codes: { a: {} } })).toEqual([])
    expect(patternSetCodes([])).toEqual([])
    expect(textPatternReady({ pattern_set: SET, code: 'hedge' })).toBe(true)
    expect(textPatternReady({ pattern_set: SET, code: 'nope' })).toBe(false)
  })

  it('takes a pasted set and offers its codes', () => {
    render(<Harness initial={{}} />)
    expect(screen.getByTestId('ready').textContent).toBe('false')
    fireEvent.change(screen.getByLabelText('Pattern set (JSON)'), {
      target: { value: JSON.stringify(SET) },
    })
    expect(params()).toEqual({ pattern_set: SET, code: 'cites' })
    expect(screen.getByTestId('ready').textContent).toBe('true')
    fireEvent.change(screen.getByLabelText('Code'), {
      target: { value: 'hedge' },
    })
    expect(params().code).toBe('hedge')
  })

  it('drops the set while the text is not one, keeping the chosen code', () => {
    render(<Harness initial={{ pattern_set: SET, code: 'hedge' }} />)
    const box = screen.getByLabelText('Pattern set (JSON)')
    expect((box as HTMLTextAreaElement).value).toContain('"signals"')
    expect(screen.getByTestId('ready').textContent).toBe('true')
    fireEvent.change(box, { target: { value: '{"name": ' } })
    expect(screen.getByRole('alert').textContent).toBe(
      'The pattern set is not valid JSON.',
    )
    expect(params()).toEqual({ code: 'hedge' })
    expect(screen.getByTestId('ready').textContent).toBe('false')
    fireEvent.change(box, { target: { value: JSON.stringify(SET) } })
    expect(screen.getByTestId('ready').textContent).toBe('true')
    fireEvent.change(box, { target: { value: '{"name": "x"}' } })
    expect(screen.getByRole('alert').textContent).toBe(
      'The pattern set needs a name, a version and at least one code.',
    )
    expect(params().pattern_set).toBeUndefined()
    expect(screen.getByTestId('ready').textContent).toBe('false')
    fireEvent.change(box, { target: { value: JSON.stringify(SET) } })
    expect(screen.queryByRole('alert')).toBeNull()
    expect(params()).toEqual({ pattern_set: SET, code: 'hedge' })
    expect(screen.getByTestId('ready').textContent).toBe('true')
  })
})

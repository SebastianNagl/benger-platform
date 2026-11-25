/**
 * Read-only mode for every editable annotation field.
 *
 * Review pages render an answer through DynamicAnnotationInterface with
 * readOnly; the interface swaps onChange for a no-op, so a field that keeps
 * its own state still let the reviewer type or click, showed the edit and
 * silently dropped it. A read-only field must not change at all.
 */

/**
 * @jest-environment jsdom
 */

import '@testing-library/jest-dom'
import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import ChoicesInput from '../ChoicesInput'
import LikertInput from '../LikertInput'
import NumberInput from '../NumberInput'
import RatingInput from '../RatingInput'
import SpanLabelsInput from '../SpanLabelsInput'
import TextAreaInput from '../TextAreaInput'

const base = (type: string, props: Record<string, string>, children = []) => ({
  config: { type, name: 'field', props: { name: 'field', ...props }, children },
  taskData: { text: 'The quick brown fox' },
  onChange: jest.fn(),
  onAnnotation: jest.fn(),
})

describe('annotation fields in read-only mode', () => {
  it('TextArea keeps the answer when the reviewer types', async () => {
    const props = base('TextArea', { toName: 'text' })
    render(<TextAreaInput {...props} value="Original answer" readOnly />)
    const box = screen.getByRole('textbox')
    expect(box).toHaveAttribute('readonly')
    await userEvent.type(box, ' edited')
    expect(box).toHaveValue('Original answer')
    expect(props.onChange).not.toHaveBeenCalled()
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('TextArea stays editable without readOnly', async () => {
    const props = base('TextArea', { toName: 'text' })
    render(<TextAreaInput {...props} value="Original answer" />)
    const box = screen.getByRole('textbox')
    expect(box).not.toHaveAttribute('readonly')
    await userEvent.type(box, '!')
    expect(box).toHaveValue('Original answer!')
    expect(props.onChange).toHaveBeenCalledWith('Original answer!')
  })

  it('Number keeps the value when the reviewer types', async () => {
    const props = base('Number', {})
    render(<NumberInput {...props} value={3} readOnly />)
    const box = screen.getByRole('spinbutton')
    expect(box).toHaveAttribute('readonly')
    await userEvent.type(box, '9')
    expect(box).toHaveValue(3)
    expect(props.onChange).not.toHaveBeenCalled()
  })

  it('Choices keeps the selection when the reviewer clicks', () => {
    const props = base('Choices', { toName: 'text' }, [
      { type: 'Choice', name: 'a', props: { value: 'A' }, children: [] },
      { type: 'Choice', name: 'b', props: { value: 'B' }, children: [] },
    ] as any)
    render(<ChoicesInput {...props} value="A" readOnly />)
    const [a, b] = screen.getAllByRole('radio')
    expect(b).toBeDisabled()
    fireEvent.click(b)
    expect(a).toBeChecked()
    expect(b).not.toBeChecked()
    expect(props.onChange).not.toHaveBeenCalled()
  })

  it('Rating keeps the rating when the reviewer clicks', () => {
    const props = base('Rating', { maxRating: '5' })
    render(<RatingInput {...props} value={2} readOnly />)
    const stars = screen.getAllByRole('button')
    stars.forEach((star) => expect(star).toBeDisabled())
    fireEvent.click(stars[4])
    expect(props.onChange).not.toHaveBeenCalled()
  })

  it('Likert keeps the value when the reviewer clicks', () => {
    const props = base('Likert', {})
    render(<LikertInput {...props} value={2} readOnly />)
    const radios = screen.getAllByRole('radio')
    radios.forEach((radio) => expect(radio).toBeDisabled())
    fireEvent.click(radios[5])
    expect(radios[1]).toBeChecked()
    expect(props.onChange).not.toHaveBeenCalled()
  })

  it('SpanLabels does not remove a span or offer label buttons', () => {
    const props = base('Labels', { toName: 'text' }, [
      { type: 'Label', name: 'l', props: { value: 'ANIMAL' }, children: [] },
    ] as any)
    const spans = [
      { id: 's1', start: 16, end: 19, text: 'fox', labels: ['ANIMAL'] },
    ]
    render(<SpanLabelsInput {...props} value={spans} readOnly />)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
    fireEvent.click(screen.getAllByText('fox')[0])
    fireEvent.keyDown(window, { key: '1' })
    expect(screen.getAllByText('fox').length).toBeGreaterThan(0)
    expect(props.onChange).not.toHaveBeenCalled()
  })
})

/**
 * @jest-environment jsdom
 *
 * A host that submits through its own controls (hostOwnsSubmit), such as a
 * review page's action bar, gets no submit from the real form and TextArea
 * field: no per-field submit button (it only rebuilds the field's result and
 * saves nothing), no keyboard shortcut tip, no Ctrl+Enter submit and no empty
 * action bar. A host that only hides the main button (the labeling page with
 * the project's submit button turned off) keeps Ctrl+Enter and the tip, as
 * the project setting promises.
 */
import '@testing-library/jest-dom'
import { fireEvent, render, screen } from '@testing-library/react'
import { DynamicAnnotationInterface } from '../DynamicAnnotationInterface'

jest.mock('@/contexts/I18nContext', () => {
  const t = (key: string) => key
  return { useI18n: () => ({ t, locale: 'de' }) }
})

const CONFIG =
  "<View><Text name='text' value='$text'/><TextArea name='answer' toName='text'/></View>"
const INITIAL = [
  {
    from_name: 'answer',
    to_name: 'text',
    type: 'textarea',
    value: { text: ['An answer.'] },
  },
]

function renderForm(
  props: Partial<Parameters<typeof DynamicAnnotationInterface>[0]>,
) {
  const onSubmit = jest.fn()
  render(
    <DynamicAnnotationInterface
      labelConfig={CONFIG}
      taskData={{ text: 'Facts' }}
      initialValues={INITIAL as any}
      onSubmit={onSubmit}
      taskId="task-1"
      enableAutoSave={false}
      {...props}
    />,
  )
  return onSubmit
}

describe('DynamicAnnotationInterface: host that owns the submit', () => {
  it('shows no per-field submit button', async () => {
    renderForm({ showSubmitButton: false, hostOwnsSubmit: true })
    await screen.findByRole('textbox')

    expect(screen.queryByText('common.submit')).not.toBeInTheDocument()
    expect(screen.queryAllByRole('button')).toEqual([])
  })

  it('shows no keyboard shortcut tip and ignores Ctrl+Enter', async () => {
    const onSubmit = renderForm({
      showSubmitButton: false,
      hostOwnsSubmit: true,
    })
    await screen.findByRole('textbox')

    expect(
      screen.queryByText('annotation.interface.tip'),
    ).not.toBeInTheDocument()

    fireEvent.keyDown(window, { key: 'Enter', ctrlKey: true })
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('renders no empty action bar', async () => {
    renderForm({ showSubmitButton: false, hostOwnsSubmit: true })
    await screen.findByRole('textbox')

    expect(
      screen.queryByTestId('annotation-action-bar'),
    ).not.toBeInTheDocument()
  })

  it('keeps the action bar and the tip while the skip shortcut works', async () => {
    renderForm({
      showSubmitButton: false,
      hostOwnsSubmit: true,
      onSkip: jest.fn(),
    })
    await screen.findByRole('textbox')

    expect(screen.getByTestId('annotation-action-bar')).toBeInTheDocument()
    expect(screen.getByText('annotation.interface.tip')).toBeInTheDocument()
  })
})

describe('DynamicAnnotationInterface: labeling page without the submit button', () => {
  it('still submits on Ctrl+Enter and shows the tip', async () => {
    const onSubmit = renderForm({ showSubmitButton: false })
    await screen.findByRole('textbox')

    expect(
      screen.queryByRole('button', { name: /annotation.interface.submit/ }),
    ).not.toBeInTheDocument()
    expect(screen.getByText('annotation.interface.tip')).toBeInTheDocument()

    fireEvent.keyDown(window, { key: 'Enter', ctrlKey: true })
    await screen.findByRole('textbox')
    expect(onSubmit).toHaveBeenCalledTimes(1)
  })
})

describe('DynamicAnnotationInterface: host with the submit button', () => {
  it('shows only the main submit button, the tip, and submits on Ctrl+Enter', async () => {
    const onSubmit = renderForm({ showSubmitButton: true })
    await screen.findByRole('textbox')

    expect(screen.queryByText('common.submit')).not.toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: /annotation.interface.submit/ }),
    ).toBeInTheDocument()
    expect(screen.getByText('annotation.interface.tip')).toBeInTheDocument()

    fireEvent.keyDown(window, { key: 'Enter', ctrlKey: true })
    await screen.findByRole('textbox')
    expect(onSubmit).toHaveBeenCalledTimes(1)
  })
})

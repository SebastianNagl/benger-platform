/**
 * @jest-environment jsdom
 *
 * The Ctrl/Cmd+Enter submit and Ctrl/Cmd+Escape skip shortcuts listen on the
 * window, so they must only act for the editor the key is meant for: never
 * for a read-only editor, never for the task editor while a questionnaire
 * (its own annotation interface) or a modal dialog has the key, and the
 * questionnaire's own form still submits from inside its dialog.
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

function TaskEditor(
  props: Partial<Parameters<typeof DynamicAnnotationInterface>[0]>,
) {
  return (
    <DynamicAnnotationInterface
      labelConfig={CONFIG}
      taskData={{ text: 'Facts' }}
      initialValues={INITIAL as any}
      onSubmit={jest.fn()}
      taskId="task-1"
      enableAutoSave={false}
      {...props}
    />
  )
}

describe('DynamicAnnotationInterface: keyboard shortcut scope', () => {
  it('submits on Ctrl+Enter when editable (control)', async () => {
    const onSubmit = jest.fn()
    render(<TaskEditor onSubmit={onSubmit} />)
    await screen.findByRole('textbox')

    fireEvent.keyDown(window, { key: 'Enter', ctrlKey: true })
    expect(onSubmit).toHaveBeenCalledTimes(1)
  })

  it('ignores Ctrl+Enter and hides the shortcut tip when read-only', async () => {
    const onSubmit = jest.fn()
    render(<TaskEditor onSubmit={onSubmit} readOnly showSubmitButton={false} />)
    await screen.findByRole('textbox')

    fireEvent.keyDown(window, { key: 'Enter', ctrlKey: true })
    fireEvent.keyDown(window, { key: 'Enter', metaKey: true })
    expect(onSubmit).not.toHaveBeenCalled()
    expect(
      screen.queryByText('annotation.interface.tip'),
    ).not.toBeInTheDocument()
  })

  it('leaves a Ctrl+Enter typed in a questionnaire form to that form', async () => {
    const onTaskSubmit = jest.fn()
    const onQuestionnaireSubmit = jest.fn()
    render(
      <>
        <TaskEditor onSubmit={onTaskSubmit} />
        <div data-testid="questionnaire">
          <TaskEditor
            onSubmit={onQuestionnaireSubmit}
            taskId={undefined}
            taskData={{ text: 'How hard was it?' }}
          />
        </div>
      </>,
    )
    const questionnaireBox = (await screen.findAllByRole('textbox'))[1]

    fireEvent.keyDown(questionnaireBox, { key: 'Enter', ctrlKey: true })
    expect(onQuestionnaireSubmit).toHaveBeenCalledTimes(1)
    expect(onTaskSubmit).not.toHaveBeenCalled()
  })

  it('ignores Ctrl+Enter and Ctrl+Escape while a modal dialog is open over it', async () => {
    const onTaskSubmit = jest.fn()
    const onSkip = jest.fn()
    const onDialogSubmit = jest.fn()
    render(
      <>
        <TaskEditor onSubmit={onTaskSubmit} onSkip={onSkip} />
        <div role="dialog" aria-modal="true">
          <button type="button">Other dialog</button>
          <TaskEditor
            onSubmit={onDialogSubmit}
            taskId={undefined}
            taskData={{ text: 'How hard was it?' }}
          />
        </div>
      </>,
    )
    await screen.findAllByRole('textbox')

    // Focus lost to the page body: still not the task editor's key.
    fireEvent.keyDown(window, { key: 'Enter', ctrlKey: true })
    fireEvent.keyDown(window, { key: 'Escape', ctrlKey: true })
    expect(onTaskSubmit).not.toHaveBeenCalled()
    expect(onSkip).not.toHaveBeenCalled()
    // The form inside the dialog is the one the key is for.
    expect(onDialogSubmit).toHaveBeenCalledTimes(1)

    // A key from a dialog control that is not an editor submits nothing
    // underneath it.
    fireEvent.keyDown(screen.getByText('Other dialog'), {
      key: 'Enter',
      ctrlKey: true,
    })
    expect(onTaskSubmit).not.toHaveBeenCalled()
  })

  it('still submits from a modal panel that the editor itself renders', async () => {
    const onSubmit = jest.fn()
    const { container } = render(<TaskEditor onSubmit={onSubmit} />)
    await screen.findByRole('textbox')
    // An exam layout may render its own modal panel inside the editor.
    const root = container.querySelector('[data-annotation-interface]')!
    const panel = document.createElement('div')
    panel.setAttribute('role', 'dialog')
    panel.setAttribute('aria-modal', 'true')
    const button = document.createElement('button')
    panel.appendChild(button)
    root.appendChild(panel)

    fireEvent.keyDown(button, { key: 'Enter', ctrlKey: true })
    expect(onSubmit).toHaveBeenCalledTimes(1)
    panel.remove()
  })
})

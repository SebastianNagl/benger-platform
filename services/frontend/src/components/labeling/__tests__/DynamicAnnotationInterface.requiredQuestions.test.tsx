/**
 * @jest-environment jsdom
 *
 * required="true" on a questionnaire question is enforced: with
 * enforceRequired (the post-annotation questionnaire modal) the form does
 * not submit while a required question is unanswered and names the missing
 * ones by their label. Annotation hosts do not opt in, so their behaviour is
 * unchanged. Runs against the templates the project settings ship.
 */
import { QUESTIONNAIRE_TEMPLATES } from '@/components/projects/AdvancedSettingsCard'
import '@testing-library/jest-dom'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { DynamicAnnotationInterface } from '../DynamicAnnotationInterface'
import { PostAnnotationQuestionnaireModal } from '../PostAnnotationQuestionnaireModal'

jest.mock('@/contexts/I18nContext', () => {
  const t = (key: string, params?: Record<string, string>) =>
    params?.fields ? `${key}: ${params.fields}` : key
  return { useI18n: () => ({ t, locale: 'en' }) }
})

const EXTENDED = QUESTIONNAIRE_TEMPLATES.extended

function renderForm(enforceRequired: boolean) {
  const onSubmit = jest.fn()
  render(
    <DynamicAnnotationInterface
      labelConfig={EXTENDED}
      taskData={{}}
      onSubmit={onSubmit}
      enableAutoSave={false}
      enforceRequired={enforceRequired}
    />,
  )
  return onSubmit
}

function ratingStars(label: string) {
  const block = screen.getByText(label).closest('.rating-input') as HTMLElement
  return Array.from(block.querySelectorAll('button'))
}

async function writeComment(user: ReturnType<typeof userEvent.setup>) {
  const box = await screen.findByRole('textbox')
  await user.type(box, 'An edge case')
  fireEvent.blur(box)
}

const SUBMIT = /annotation\.interface\.submit/

describe('DynamicAnnotationInterface: required questions', () => {
  it('shows each question by its label, not its name', async () => {
    renderForm(true)
    expect(
      await screen.findByText('How confident are you in your annotation?'),
    ).toBeInTheDocument()
    expect(screen.getByText('How difficult was this task?')).toBeInTheDocument()
    expect(
      screen.getByText('How clear were the annotation guidelines?'),
    ).toBeInTheDocument()
    expect(
      screen.getByText('Additional comments (optional)'),
    ).toBeInTheDocument()
    expect(screen.queryByText('confidence')).not.toBeInTheDocument()
    expect(screen.queryByText('guideline_clarity')).not.toBeInTheDocument()
  })

  it('does not submit while required questions are unanswered', async () => {
    const user = userEvent.setup()
    const onSubmit = renderForm(true)
    await writeComment(user)

    await user.click(screen.getByRole('button', { name: SUBMIT }))

    expect(onSubmit).not.toHaveBeenCalled()
    expect(
      screen.getByText(
        'annotation.interface.requiredMissing: How confident are you in your annotation?, How difficult was this task?, How clear were the annotation guidelines?',
      ),
    ).toBeInTheDocument()
  })

  it('treats a cleared star rating as unanswered', async () => {
    const user = userEvent.setup()
    const onSubmit = renderForm(true)
    await screen.findByText('How confident are you in your annotation?')

    const stars = ratingStars('How confident are you in your annotation?')
    await user.click(stars[2])
    await user.click(stars[2]) // clicking the chosen star again clears it
    await user.click(ratingStars('How difficult was this task?')[1])
    await user.click(screen.getByLabelText('Clear'))
    await user.click(screen.getByRole('button', { name: SUBMIT }))

    expect(onSubmit).not.toHaveBeenCalled()
    expect(
      screen.getByText(
        'annotation.interface.requiredMissing: How confident are you in your annotation?',
      ),
    ).toBeInTheDocument()
  })

  it('submits once every required question is answered', async () => {
    const user = userEvent.setup()
    const onSubmit = renderForm(true)
    await screen.findByText('How confident are you in your annotation?')

    await user.click(
      ratingStars('How confident are you in your annotation?')[3],
    )
    await user.click(ratingStars('How difficult was this task?')[1])
    await user.click(screen.getByLabelText('Clear'))
    await user.click(screen.getByRole('button', { name: SUBMIT }))

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1))
    const byName = Object.fromEntries(
      onSubmit.mock.calls[0][0].map((r: any) => [r.from_name, r.value]),
    )
    expect(byName).toEqual({
      confidence: 4,
      difficulty: 2,
      guideline_clarity: { choices: ['Clear'] },
    })
    expect(
      screen.queryByText(/annotation\.interface\.requiredMissing/),
    ).not.toBeInTheDocument()
  })

  it('leaves hosts that do not opt in unchanged', async () => {
    const user = userEvent.setup()
    const onSubmit = renderForm(false)
    await writeComment(user)

    await user.click(screen.getByRole('button', { name: SUBMIT }))

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1))
    expect(onSubmit.mock.calls[0][0].map((r: any) => r.from_name)).toEqual([
      'comments',
    ])
  })

  it('enforces the Likert questions of the UTAUT template', async () => {
    const user = userEvent.setup()
    const onSubmit = jest.fn()
    render(
      <DynamicAnnotationInterface
        labelConfig={QUESTIONNAIRE_TEMPLATES.utaut_study}
        taskData={{}}
        onSubmit={onSubmit}
        enableAutoSave={false}
        enforceRequired
      />,
    )
    const share = await screen.findByLabelText(
      'x Prozent der Fallbearbeitung gehen auf mich zurück.',
    )
    await user.type(share, '40')
    fireEvent.blur(share)

    await user.click(screen.getByRole('button', { name: SUBMIT }))

    expect(onSubmit).not.toHaveBeenCalled()
    expect(
      screen.getByText(
        'annotation.interface.requiredMissing: Es fiel mir leicht die Aufgabe zu lösen., Ich fühle mich verantwortlich für das von mir eingereichte Ergebnis.',
      ),
    ).toBeInTheDocument()
  })

  it('a rejected questionnaire submit shows only the modal message and keeps the answers', async () => {
    const user = userEvent.setup()
    const onSubmitResponse = jest
      .fn()
      .mockRejectedValue(
        new Error(
          'Questionnaire response already submitted for this annotation',
        ),
      )
    const onComplete = jest.fn()
    render(
      <PostAnnotationQuestionnaireModal
        isOpen
        questionnaireConfig={EXTENDED.replace(/ required="true"/g, '')}
        projectId="p"
        taskId="t"
        annotationId="a"
        onComplete={onComplete}
        onSubmitResponse={onSubmitResponse}
      />,
    )
    await writeComment(user)

    await user.click(screen.getByRole('button', { name: SUBMIT }))

    expect(
      await screen.findByText(
        'Questionnaire response already submitted for this annotation',
      ),
    ).toBeInTheDocument()
    expect(onSubmitResponse).toHaveBeenCalledTimes(1)
    expect(onComplete).not.toHaveBeenCalled()
    expect(
      screen.queryByText('annotation.interface.submissionError'),
    ).not.toBeInTheDocument()
    expect(screen.getByRole('textbox')).toHaveValue('An edge case')
  })
})

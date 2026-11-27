/**
 * @jest-environment jsdom
 *
 * The questionnaire settings card (three alike blocks) and the prompt that
 * asks a questionnaire after an action (after a submission, after a
 * Korrektur).
 */

import '@testing-library/jest-dom'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'

import { QuestionnairePrompt } from '../QuestionnairePrompt'
import { QuestionnairesSettings } from '../QuestionnairesSettings'
import { QUESTIONNAIRE_TEMPLATES } from '../templates'

jest.mock('@/contexts/I18nContext', () =>
  require('@/test-utils/i18nMock').i18nMock('en'),
)

// The annotation interface stub shows which config it renders and what
// task data it got (a questionnaire must get none).
const renderedTaskData: any[] = []
jest.mock('@/components/labeling/DynamicAnnotationInterface', () => ({
  DynamicAnnotationInterface: ({ labelConfig, taskData, onSubmit }: any) => {
    renderedTaskData.push(taskData)
    return (
      <div data-testid="rendered-config" data-config={labelConfig}>
        <button
          data-testid="answer-submit"
          onClick={() =>
            onSubmit([
              { from_name: 'q', to_name: 'q', type: 'rating', value: 4 },
            ])
          }
        >
          submit
        </button>
      </div>
    )
  },
}))

const mockAPI = {
  list: jest.fn(),
  save: jest.fn(),
  validate: jest.fn(),
  status: jest.fn(),
  answer: jest.fn(),
  skip: jest.fn(),
  csvUrl: (projectId: string, trigger = 'all') =>
    `/api/projects/${projectId}/questionnaire-responses/export.csv?trigger=${trigger}`,
}
jest.mock('@/lib/api/questionnaires', () => ({
  QUESTIONNAIRE_TRIGGERS: ['before_task', 'after_submit', 'korrektur'],
  questionnairesAPI: new Proxy(
    {},
    { get: (_t, key: string) => (mockAPI as any)[key] },
  ),
}))

function block(trigger: string, overrides: any = {}) {
  return {
    trigger,
    enabled: false,
    config: '',
    required: trigger !== 'korrektur',
    frequency:
      trigger === 'before_task' ? 'once_per_project' : 'once_per_submission',
    version: 0,
    active: false,
    allowed_frequencies:
      trigger === 'before_task'
        ? ['once_per_project', 'once_per_task']
        : trigger === 'after_submit'
          ? ['once_per_submission', 'once_per_task', 'once_per_project']
          : ['once_per_submission', 'once_per_project'],
    updated_at: null,
    ...overrides,
  }
}

const XML = '<View><Rating name="q" toName="q" required="true"/></View>'

beforeEach(() => {
  jest.useRealTimers()
  jest.clearAllMocks()
  renderedTaskData.length = 0
  mockAPI.list.mockResolvedValue({
    questionnaires: [
      block('before_task'),
      block('after_submit', {
        enabled: true,
        config: XML,
        version: 1,
        active: true,
      }),
      block('korrektur'),
    ],
    can_edit: true,
  })
  mockAPI.validate.mockResolvedValue({ valid: true, errors: [] })
})

describe('QuestionnairesSettings', () => {
  it('shows one block per moment, the switched-on one with its version', async () => {
    const onActiveCount = jest.fn()
    render(
      <QuestionnairesSettings
        projectId="p1"
        canEdit
        onActiveCount={onActiveCount}
      />,
    )
    await screen.findByTestId('questionnaires-settings')
    expect(
      screen.getByTestId('questionnaire-block-before_task'),
    ).toBeInTheDocument()
    expect(
      screen.getByTestId('questionnaire-block-after_submit'),
    ).toBeInTheDocument()
    expect(
      screen.getByTestId('questionnaire-block-korrektur'),
    ).toBeInTheDocument()
    expect(onActiveCount).toHaveBeenLastCalledWith(1)
    expect(screen.getByTestId('questionnaire-csv-all')).toHaveAttribute(
      'href',
      '/api/projects/p1/questionnaire-responses/export.csv?trigger=all',
    )
  })

  async function openBlock(trigger: string) {
    await screen.findByTestId('questionnaires-settings')
    const blockEl = screen.getByTestId(`questionnaire-block-${trigger}`)
    fireEvent.click(blockEl.querySelector('button[aria-expanded]')!)
  }

  it('saves a block with its settings and XML', async () => {
    mockAPI.save.mockResolvedValue(
      block('before_task', {
        enabled: true,
        config: XML,
        version: 1,
        active: true,
      }),
    )
    render(<QuestionnairesSettings projectId="p1" canEdit />)
    await openBlock('before_task')

    fireEvent.change(screen.getByTestId('questionnaire-before_task-xml'), {
      target: { value: XML },
    })
    fireEvent.click(screen.getByTestId('questionnaire-before_task-enabled'))
    fireEvent.click(screen.getByTestId('questionnaire-before_task-required'))
    await waitFor(() =>
      expect(mockAPI.validate).toHaveBeenCalledWith('p1', XML),
    )
    await waitFor(() =>
      expect(
        screen.getByTestId('questionnaire-before_task-save'),
      ).not.toBeDisabled(),
    )
    await act(async () => {
      fireEvent.click(screen.getByTestId('questionnaire-before_task-save'))
    })
    expect(mockAPI.save).toHaveBeenCalledWith('p1', 'before_task', {
      enabled: true,
      required: false,
      frequency: 'once_per_project',
      config: XML,
    })
  })

  it('names what is wrong with the XML and does not save it', async () => {
    mockAPI.validate.mockResolvedValue({
      valid: false,
      errors: ["Unsupported field type: 'Ratng'"],
    })
    render(<QuestionnairesSettings projectId="p1" canEdit />)
    await openBlock('korrektur')
    fireEvent.change(screen.getByTestId('questionnaire-korrektur-xml'), {
      target: { value: '<View><Ratng name="q"/></View>' },
    })
    expect(
      await screen.findByText("Unsupported field type: 'Ratng'"),
    ).toBeInTheDocument()
    expect(screen.getByTestId('questionnaire-korrektur-save')).toBeDisabled()
  })

  it('shows the server refusal on save', async () => {
    const err: any = new Error('refused')
    err.response = {
      status: 422,
      data: { detail: { errors: ['The questionnaire has no question'] } },
    }
    mockAPI.save.mockRejectedValue(err)
    render(<QuestionnairesSettings projectId="p1" canEdit />)
    await openBlock('after_submit')
    fireEvent.click(screen.getByTestId('questionnaire-after_submit-required'))
    await act(async () => {
      fireEvent.click(screen.getByTestId('questionnaire-after_submit-save'))
    })
    expect(
      await screen.findByText('The questionnaire has no question'),
    ).toBeInTheDocument()
  })

  it('loads an uploaded .xml file into the editor and previews it', async () => {
    render(<QuestionnairesSettings projectId="p1" canEdit />)
    await openBlock('before_task')
    const file = new File([XML], 'q.xml', { type: 'text/xml' })
    Object.defineProperty(file, 'text', { value: () => Promise.resolve(XML) })
    await act(async () => {
      fireEvent.change(screen.getByTestId('questionnaire-before_task-upload'), {
        target: { files: [file] },
      })
    })
    expect(screen.getByTestId('questionnaire-before_task-xml')).toHaveValue(XML)
    await waitFor(() =>
      expect(
        screen
          .getByTestId('questionnaire-before_task-preview')
          .querySelector('[data-config]'),
      ).toHaveAttribute('data-config', XML),
    )
  })

  it('offers the templates of the moment', () => {
    // Every moment has starting points; the Korrektur ones ask the grader.
    expect(QUESTIONNAIRE_TEMPLATES.before_task.length).toBeGreaterThan(0)
    expect(QUESTIONNAIRE_TEMPLATES.after_submit.map((t) => t.id)).toEqual([
      'confidence_difficulty',
      'extended',
      'utaut_study',
    ])
    expect(
      QUESTIONNAIRE_TEMPLATES.korrektur.every((t) => t.xml.includes('<View>')),
    ).toBe(true)
  })

  it('is read-only without edit rights', async () => {
    render(<QuestionnairesSettings projectId="p1" canEdit={false} />)
    await openBlock('after_submit')
    expect(screen.getByTestId('questionnaire-after_submit-xml')).toBeDisabled()
    expect(
      screen.getByTestId('questionnaire-after_submit-enabled'),
    ).toBeDisabled()
    expect(screen.queryByTestId('questionnaire-after_submit-save')).toBeNull()
  })
})

describe('QuestionnairePrompt (Korrektur)', () => {
  const grader = block('korrektur', {
    enabled: true,
    config: XML,
    version: 1,
    active: true,
  })

  it('asks after the grade is saved and records the grader answer', async () => {
    mockAPI.status.mockResolvedValue({ due: true, questionnaire: grader })
    mockAPI.answer.mockResolvedValue({})
    const onDone = jest.fn()
    render(
      <QuestionnairePrompt
        projectId="p1"
        trigger="korrektur"
        subject={{ task_evaluation_id: 'te-1' }}
        open
        onDone={onDone}
      />,
    )
    await screen.findByTestId('questionnaire-dialog-korrektur')
    expect(mockAPI.status).toHaveBeenCalledWith('p1', 'korrektur', {
      task_evaluation_id: 'te-1',
    })
    // Nothing of the submission or its author reaches the questionnaire.
    expect(renderedTaskData.every((d) => Object.keys(d).length === 0)).toBe(
      true,
    )
    await act(async () => {
      fireEvent.click(screen.getByTestId('answer-submit'))
    })
    expect(mockAPI.answer).toHaveBeenCalledWith(
      'p1',
      'korrektur',
      { task_evaluation_id: 'te-1' },
      expect.any(Array),
    )
    expect(onDone).toHaveBeenCalledWith('answered')
  })

  it('an optional one is skippable', async () => {
    mockAPI.status.mockResolvedValue({ due: true, questionnaire: grader })
    mockAPI.skip.mockResolvedValue({})
    const onDone = jest.fn()
    render(
      <QuestionnairePrompt
        projectId="p1"
        trigger="korrektur"
        subject={{ task_evaluation_id: 'te-1' }}
        open
        onDone={onDone}
      />,
    )
    await screen.findByTestId('questionnaire-dialog-korrektur')
    await act(async () => {
      fireEvent.click(screen.getByTestId('questionnaire-skip'))
    })
    expect(mockAPI.skip).toHaveBeenCalledWith('p1', 'korrektur', {
      task_evaluation_id: 'te-1',
    })
    expect(onDone).toHaveBeenCalledWith('skipped')
  })

  it('does nothing visible when none is due, and asks nothing while closed', async () => {
    mockAPI.status.mockResolvedValue({ due: false, questionnaire: null })
    const onDone = jest.fn()
    const { rerender } = render(
      <QuestionnairePrompt
        projectId="p1"
        trigger="korrektur"
        subject={{ task_evaluation_id: 'te-1' }}
        open={false}
        onDone={onDone}
      />,
    )
    expect(mockAPI.status).not.toHaveBeenCalled()
    rerender(
      <QuestionnairePrompt
        projectId="p1"
        trigger="korrektur"
        subject={{ task_evaluation_id: 'te-1' }}
        open
        onDone={onDone}
      />,
    )
    await waitFor(() => expect(onDone).toHaveBeenCalledWith('not_due'))
    expect(screen.queryByTestId('questionnaire-dialog-korrektur')).toBeNull()
  })

  it('an answer given meanwhile (409) counts as answered', async () => {
    mockAPI.status.mockResolvedValue({ due: true, questionnaire: grader })
    const conflict: any = new Error('already')
    conflict.response = { status: 409 }
    mockAPI.answer.mockRejectedValue(conflict)
    const onDone = jest.fn()
    render(
      <QuestionnairePrompt
        projectId="p1"
        trigger="after_submit"
        subject={{ annotation_id: 'a-1' }}
        open
        onDone={onDone}
      />,
    )
    await screen.findByTestId('questionnaire-dialog-after_submit')
    await act(async () => {
      fireEvent.click(screen.getByTestId('answer-submit'))
    })
    expect(onDone).toHaveBeenCalledWith('answered')
  })
})

/**
 * The reasoning a model returned beside its answer is shown in a collapsed
 * section next to the answer, and only when there is any.
 */

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { GenerationReasoning, reasoningEntries } from '../GenerationReasoning'
import { GenerationResultModal } from '../GenerationResultModal'

jest.mock('@/lib/api/client', () => ({
  apiClient: { get: jest.fn() },
}))

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, vars?: Record<string, unknown>) => {
      const translations: Record<string, string> = {
        'generation.resultModal.viewReasoning': 'View Model Reasoning',
        'generation.resultModal.reasoningHint': 'Reasoning hint',
        'generation.resultModal.reasoningRun': 'Run {index}',
        'generation.resultModal.generatedText': 'Generated Text',
      }
      let text = translations[key] || key
      Object.entries(vars || {}).forEach(([k, v]) => {
        text = text.replace(`{${k}}`, String(v))
      })
      return text
    },
    locale: 'en',
  }),
}))

describe('reasoningEntries', () => {
  const label = (index: number) => `Run ${index}`

  it('reads a single run', () => {
    expect(
      reasoningEntries(
        { generated_text: 'Antwort', reasoning: 'Erst § 433 BGB' },
        label,
      ),
    ).toEqual([{ label: null, text: 'Erst § 433 BGB' }])
  })

  it('labels each run of a multi-run result and skips runs without reasoning', () => {
    expect(
      reasoningEntries(
        {
          generations: [
            { generated_text: 'a', reasoning: 'r1' },
            { generated_text: 'b', reasoning: null },
            { generated_text: 'c', reasoning: 'r3' },
          ],
        },
        label,
      ),
    ).toEqual([
      { label: 'Run 1', text: 'r1' },
      { label: 'Run 3', text: 'r3' },
    ])
  })

  it('is empty without reasoning', () => {
    expect(reasoningEntries(undefined, label)).toEqual([])
    expect(reasoningEntries({ generated_text: 'a' }, label)).toEqual([])
    expect(
      reasoningEntries({ generated_text: 'a', reasoning: '' }, label),
    ).toEqual([])
  })
})

describe('GenerationReasoning', () => {
  it('renders nothing when the result has no reasoning', () => {
    const { container } = render(
      <GenerationReasoning result={{ generated_text: 'Antwort' }} />,
    )
    expect(container).toBeEmptyDOMElement()
  })

  it('is collapsed by default and opens on click', async () => {
    render(
      <GenerationReasoning
        result={{ generated_text: 'Antwort', reasoning: 'Erst § 433 BGB' }}
      />,
    )
    const section = screen.getByTestId('generation-reasoning')
    expect(section).not.toHaveAttribute('open')
    await userEvent.click(screen.getByText('View Model Reasoning'))
    expect(section).toHaveAttribute('open')
    expect(screen.getByText('Erst § 433 BGB')).toBeInTheDocument()
  })
})

describe('GenerationResultModal reasoning section', () => {
  it('shows the reasoning beside the answer without mixing it into the answer', () => {
    render(
      <GenerationResultModal
        isOpen
        taskId="task-1"
        modelId="qwen3"
        onClose={jest.fn()}
        result={{
          task_id: 'task-1',
          model_id: 'qwen3',
          generation_id: 'gen-1',
          status: 'completed',
          result: {
            generated_text: 'Der Anspruch besteht.',
            reasoning: 'Erst § 433 BGB prüfen.',
          },
        }}
      />,
    )
    expect(screen.getByText('Der Anspruch besteht.')).toBeInTheDocument()
    const section = screen.getByTestId('generation-reasoning')
    expect(section).toHaveTextContent('Erst § 433 BGB prüfen.')
    expect(screen.getByText('Der Anspruch besteht.')).not.toHaveTextContent(
      'Erst § 433 BGB',
    )
  })
})

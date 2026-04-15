import { QuestionData } from '@/components/tasks/QuestionCard'
import { questionsToJson } from '@/components/tasks/QuestionManager'

describe('Question Format Fix', () => {
  it('should generate correct JSON format for QA tasks', () => {
    const questions: QuestionData[] = [
      {
        id: '1',
        question: 'What is contract law?',
        reference_answer:
          'Contract law is the body of law that governs agreements.',
      },
      {
        id: '2',
        question: 'What is tort law?',
        reference_answer: 'Tort law deals with civil wrongs.',
      },
    ]

    const json = questionsToJson(questions, 'qa')
    const parsed = JSON.parse(json)

    // Should have id and question_data wrapper
    expect(parsed[0]).toHaveProperty('id')
    expect(parsed[0]).toHaveProperty('question_data')

    // Should have German field names for QA tasks
    expect(parsed[0].question_data).toHaveProperty('Frage')
    expect(parsed[0].question_data).toHaveProperty('Antwort')

    // Values should be correct
    expect(parsed[0].id).toBe('1')
    expect(parsed[0].question_data.Frage).toBe('What is contract law?')
    expect(parsed[0].question_data.Antwort).toBe(
      'Contract law is the body of law that governs agreements.'
    )
  })

  it('should generate correct JSON format for QA reasoning tasks', () => {
    const questions: QuestionData[] = [
      {
        id: '1',
        question: 'Explain the concept',
        reference_answer: 'The concept is...',
        reasoning: 'Because of legal precedent...',
      },
    ]

    const json = questionsToJson(questions, 'qa_reasoning')
    const parsed = JSON.parse(json)

    // Should have id and question_data wrapper
    expect(parsed[0]).toHaveProperty('id')
    expect(parsed[0]).toHaveProperty('question_data')

    // Should have English field names for QA reasoning tasks
    expect(parsed[0].question_data).toHaveProperty('question')
    expect(parsed[0].question_data).toHaveProperty('answer')
    expect(parsed[0].question_data).toHaveProperty('reasoning')

    // Values should be correct
    expect(parsed[0].id).toBe('1')
    expect(parsed[0].question_data.question).toBe('Explain the concept')
    expect(parsed[0].question_data.answer).toBe('The concept is...')
    expect(parsed[0].question_data.reasoning).toBe(
      'Because of legal precedent...'
    )
  })

  it('should generate correct JSON format for multiple choice tasks', () => {
    const questions: QuestionData[] = [
      {
        id: '1',
        question: 'Which is correct?',
        context: 'Given the following case...',
        choice_a: 'Option A',
        choice_b: 'Option B',
        choice_c: 'Option C',
        choice_d: 'Option D',
        correct_answer: 'a',
      },
    ]

    const json = questionsToJson(questions, 'multiple_choice')
    const parsed = JSON.parse(json)

    // Should have id and question_data wrapper
    expect(parsed[0]).toHaveProperty('id')
    expect(parsed[0]).toHaveProperty('question_data')

    // Should have multiple choice fields
    expect(parsed[0].question_data).toHaveProperty('question')
    expect(parsed[0].question_data).toHaveProperty('context')
    expect(parsed[0].question_data).toHaveProperty('choice_a')
    expect(parsed[0].question_data).toHaveProperty('choice_b')
    expect(parsed[0].question_data).toHaveProperty('choice_c')
    expect(parsed[0].question_data).toHaveProperty('choice_d')
    expect(parsed[0].question_data).toHaveProperty('correct_answer')

    // Values should be correct
    expect(parsed[0].id).toBe('1')
    expect(parsed[0].question_data.question).toBe('Which is correct?')
    expect(parsed[0].question_data.context).toBe('Given the following case...')
    expect(parsed[0].question_data.correct_answer).toBe('a')
  })
})

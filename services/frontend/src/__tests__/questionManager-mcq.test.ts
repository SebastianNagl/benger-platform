import { QuestionData } from '../components/tasks/QuestionCard'
import { questionsToJson } from '../components/tasks/QuestionManager'

describe('questionsToJson with MCQ support', () => {
  const mcqQuestions: QuestionData[] = [
    {
      id: '1',
      question: 'What is the capital of Germany?',
      context: 'Germany is a country in Central Europe.',
      choice_a: 'Berlin',
      choice_b: 'Munich',
      choice_c: 'Hamburg',
      choice_d: 'Frankfurt',
      correct_answer: 'a',
    },
    {
      id: '2',
      question: 'Which of the following is a programming language?',
      context: 'Programming languages are used to write software.',
      choice_a: 'HTML',
      choice_b: 'CSS',
      choice_c: 'JavaScript',
      choice_d: 'XML',
      correct_answer: 'c',
    },
  ]

  const qaQuestions: QuestionData[] = [
    {
      id: '1',
      question: 'What is JavaScript?',
      reference_answer: 'A programming language',
    },
  ]

  const qarQuestions: QuestionData[] = [
    {
      id: '1',
      question: 'Is fristlose Kündigung legal?',
      reference_answer: 'Yes, under specific circumstances',
      reasoning: 'According to German labor law...',
    },
  ]

  test('should handle multiple_choice task type correctly', () => {
    const result = questionsToJson(mcqQuestions, 'multiple_choice')
    const parsed = JSON.parse(result)

    expect(parsed).toHaveLength(2)

    // Check first question - structure with id and question_data wrapper
    expect(parsed[0]).toEqual({
      id: '1',
      question_data: {
        question: 'What is the capital of Germany?',
        context: 'Germany is a country in Central Europe.',
        choice_a: 'Berlin',
        choice_b: 'Munich',
        choice_c: 'Hamburg',
        choice_d: 'Frankfurt',
        correct_answer: 'a',
      },
    })

    // Check second question - structure with id and question_data wrapper
    expect(parsed[1]).toEqual({
      id: '2',
      question_data: {
        question: 'Which of the following is a programming language?',
        context: 'Programming languages are used to write software.',
        choice_a: 'HTML',
        choice_b: 'CSS',
        choice_c: 'JavaScript',
        choice_d: 'XML',
        correct_answer: 'c',
      },
    })
  })

  test('should handle qa task type correctly (regression test)', () => {
    const result = questionsToJson(qaQuestions, 'qa')
    const parsed = JSON.parse(result)

    expect(parsed).toHaveLength(1)
    expect(parsed[0]).toEqual({
      id: '1',
      question_data: {
        Frage: 'What is JavaScript?',
        Antwort: 'A programming language',
      },
    })
  })

  test('should handle qa_reasoning task type correctly (regression test)', () => {
    const result = questionsToJson(qarQuestions, 'qa_reasoning')
    const parsed = JSON.parse(result)

    expect(parsed).toHaveLength(1)
    expect(parsed[0]).toEqual({
      id: '1',
      question_data: {
        question: 'Is fristlose Kündigung legal?',
        answer: 'Yes, under specific circumstances',
        reasoning: 'According to German labor law...',
      },
    })
  })

  test('should handle empty questions array', () => {
    const result = questionsToJson([], 'multiple_choice')
    const parsed = JSON.parse(result)

    expect(parsed).toHaveLength(0)
    expect(parsed).toEqual([])
  })

  test('should handle MCQ questions with missing fields gracefully', () => {
    const incompleteQuestions: QuestionData[] = [
      {
        id: '1',
        question: 'Incomplete question',
        choice_a: 'Option A',
        // Missing context, choice_b, choice_c, choice_d, correct_answer
      },
    ]

    const result = questionsToJson(incompleteQuestions, 'multiple_choice')
    const parsed = JSON.parse(result)

    expect(parsed).toHaveLength(1)
    expect(parsed[0]).toEqual({
      id: '1',
      question_data: {
        question: 'Incomplete question',
        context: '', // Empty string when context is undefined
        choice_a: 'Option A',
        // undefined values are not included in JSON output
      },
    })
  })

  test('should produce valid JSON output', () => {
    const result = questionsToJson(mcqQuestions, 'multiple_choice')

    // Should not throw when parsing
    expect(() => JSON.parse(result)).not.toThrow()

    // Should be properly formatted with id and question_data structure
    expect(result).toContain('{\n')
    expect(result).toContain('  "id":')
    expect(result).toContain('  "question_data":')
  })

  test('should handle all correct_answer options', () => {
    const questionsWithAllAnswers: QuestionData[] = [
      {
        id: '1',
        question: 'Q1',
        context: 'Context1',
        choice_a: 'A1',
        choice_b: 'B1',
        choice_c: 'C1',
        choice_d: 'D1',
        correct_answer: 'a',
      },
      {
        id: '2',
        question: 'Q2',
        context: 'Context2',
        choice_a: 'A2',
        choice_b: 'B2',
        choice_c: 'C2',
        choice_d: 'D2',
        correct_answer: 'b',
      },
      {
        id: '3',
        question: 'Q3',
        context: 'Context3',
        choice_a: 'A3',
        choice_b: 'B3',
        choice_c: 'C3',
        choice_d: 'D3',
        correct_answer: 'c',
      },
      {
        id: '4',
        question: 'Q4',
        context: 'Context4',
        choice_a: 'A4',
        choice_b: 'B4',
        choice_c: 'C4',
        choice_d: 'D4',
        correct_answer: 'd',
      },
    ]

    const result = questionsToJson(questionsWithAllAnswers, 'multiple_choice')
    const parsed = JSON.parse(result)

    expect(parsed[0].question_data.correct_answer).toBe('a')
    expect(parsed[1].question_data.correct_answer).toBe('b')
    expect(parsed[2].question_data.correct_answer).toBe('c')
    expect(parsed[3].question_data.correct_answer).toBe('d')
  })
})

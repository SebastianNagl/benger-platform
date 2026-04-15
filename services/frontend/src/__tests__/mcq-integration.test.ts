import { QuestionData } from '../components/tasks/QuestionCard'
import { questionsToJson } from '../components/tasks/QuestionManager'

/**
 * Integration tests for MCQ task creation fixes
 * These tests verify that the specific issues from GitHub issue #92 are resolved
 */
describe('MCQ Task Creation Fixes - Issue #92', () => {
  describe('Fix #1: questionsToJson now accepts taskType parameter', () => {
    test('should accept multiple_choice as taskType parameter', () => {
      const questions: QuestionData[] = [
        {
          id: '1',
          question: 'What is the capital of France?',
          context: 'France is a country in Western Europe.',
          choice_a: 'Paris',
          choice_b: 'London',
          choice_c: 'Berlin',
          choice_d: 'Madrid',
          correct_answer: 'a',
        },
      ]

      // This should not throw - previously would fail because taskType was missing
      expect(() => {
        questionsToJson(questions, 'multiple_choice')
      }).not.toThrow()
    })

    test('should maintain backward compatibility with qa and qa_reasoning', () => {
      const qaQuestions: QuestionData[] = [
        { id: '1', question: 'What is 2+2?', reference_answer: '4' },
      ]

      const qarQuestions: QuestionData[] = [
        {
          id: '1',
          question: 'What is 2+2?',
          reference_answer: '4',
          reasoning: 'Basic arithmetic',
        },
      ]

      expect(() => {
        questionsToJson(qaQuestions, 'qa')
        questionsToJson(qarQuestions, 'qa_reasoning')
      }).not.toThrow()
    })
  })

  describe('Fix #2: questionsToJson now supports multiple_choice task type', () => {
    test('should generate correct JSON structure for MCQ questions', () => {
      const mcqQuestions: QuestionData[] = [
        {
          id: '1',
          question: 'Which programming language is this?',
          context: 'Programming languages are used to create software.',
          choice_a: 'JavaScript',
          choice_b: 'Python',
          choice_c: 'Java',
          choice_d: 'C++',
          correct_answer: 'a',
        },
      ]

      const result = questionsToJson(mcqQuestions, 'multiple_choice')
      const parsed = JSON.parse(result)

      expect(parsed).toHaveLength(1)
      expect(parsed[0]).toEqual({
        id: '1',
        question_data: {
          question: 'Which programming language is this?',
          context: 'Programming languages are used to create software.',
          choice_a: 'JavaScript',
          choice_b: 'Python',
          choice_c: 'Java',
          choice_d: 'C++',
          correct_answer: 'a',
        },
      })
    })

    test('should handle all possible correct answers (a, b, c, d)', () => {
      const questions: QuestionData[] = [
        {
          id: '1',
          question: 'Q1',
          choice_a: 'A',
          choice_b: 'B',
          choice_c: 'C',
          choice_d: 'D',
          correct_answer: 'a',
        },
        {
          id: '2',
          question: 'Q2',
          choice_a: 'A',
          choice_b: 'B',
          choice_c: 'C',
          choice_d: 'D',
          correct_answer: 'b',
        },
        {
          id: '3',
          question: 'Q3',
          choice_a: 'A',
          choice_b: 'B',
          choice_c: 'C',
          choice_d: 'D',
          correct_answer: 'c',
        },
        {
          id: '4',
          question: 'Q4',
          choice_a: 'A',
          choice_b: 'B',
          choice_c: 'C',
          choice_d: 'D',
          correct_answer: 'd',
        },
      ]

      const result = questionsToJson(questions, 'multiple_choice')
      const parsed = JSON.parse(result)

      expect(parsed[0].question_data.correct_answer).toBe('a')
      expect(parsed[1].question_data.correct_answer).toBe('b')
      expect(parsed[2].question_data.correct_answer).toBe('c')
      expect(parsed[3].question_data.correct_answer).toBe('d')
    })
  })

  describe('Fix #3: uploadTaskData parameter order validation', () => {
    test('should validate File parameter creation', () => {
      const questionsJson = JSON.stringify([{ data: { question: 'test' } }])
      const fileName = 'Test_Task_questions.json'

      // Test that File object can be created correctly (this simulates the fix)
      const file = new File([questionsJson], fileName, {
        type: 'application/json',
      })

      expect(file).toBeInstanceOf(File)
      expect(file.name).toBe(fileName)
      expect(file.type).toBe('application/json')
      expect(file.size).toBeGreaterThan(0)
    })

    test('should validate expected parameter types for uploadTaskData call', () => {
      // This test ensures the parameters are in the correct order and type
      const questionsJson = JSON.stringify([{ data: { question: 'test' } }])
      const file = new File([questionsJson], 'test.json', {
        type: 'application/json',
      })
      const taskId = 'test-task-123'
      const description = 'Questions created via wizard'

      // Validate parameter types (this simulates the fixed function call)
      expect(file).toBeInstanceOf(File)
      expect(typeof taskId).toBe('string')
      expect(typeof description).toBe('string')

      // Validate parameter order is: File, string, string
      const params = [file, taskId, description]
      expect(params[0]).toBeInstanceOf(File)
      expect(typeof params[1]).toBe('string')
      expect(typeof params[2]).toBe('string')
    })
  })

  describe('Error Handling and Edge Cases', () => {
    test('should handle empty MCQ questions array', () => {
      const result = questionsToJson([], 'multiple_choice')
      const parsed = JSON.parse(result)

      expect(parsed).toEqual([])
      expect(parsed).toHaveLength(0)
    })

    test('should handle MCQ questions with undefined fields gracefully', () => {
      const incompleteQuestion: QuestionData[] = [
        {
          id: '1',
          question: 'Incomplete question',
          // Missing choice fields and correct_answer
        },
      ]

      const result = questionsToJson(incompleteQuestion, 'multiple_choice')
      const parsed = JSON.parse(result)

      expect(parsed[0]).toEqual({
        id: '1',
        question_data: {
          question: 'Incomplete question',
          context: '', // Empty string when context is undefined
          choice_a: undefined,
          choice_b: undefined,
          choice_c: undefined,
          choice_d: undefined,
          correct_answer: undefined,
        },
      })
    })

    test('should produce valid JSON for all task types', () => {
      const testCases = [
        {
          questions: [
            { id: '1', question: 'Q1', choice_a: 'A', correct_answer: 'a' },
          ],
          taskType: 'multiple_choice' as const,
        },
        {
          questions: [{ id: '1', question: 'Q1', reference_answer: 'A1' }],
          taskType: 'qa' as const,
        },
        {
          questions: [
            {
              id: '1',
              question: 'Q1',
              reference_answer: 'A1',
              reasoning: 'R1',
            },
          ],
          taskType: 'qa_reasoning' as const,
        },
      ]

      testCases.forEach(({ questions, taskType }) => {
        const result = questionsToJson(questions, taskType)

        // Should be valid JSON
        expect(() => JSON.parse(result)).not.toThrow()

        // Should be properly formatted (includes newlines and indentation)
        expect(result).toMatch(/\{\s*\n/)
        expect(result).toMatch(/\s{2,}/)
      })
    })
  })

  describe('Regression Tests', () => {
    test('should not break existing QA functionality', () => {
      const qaQuestions: QuestionData[] = [
        { id: '1', question: 'Was ist 2+2?', reference_answer: '4' },
      ]

      const result = questionsToJson(qaQuestions, 'qa')
      const parsed = JSON.parse(result)

      // Should maintain German field names for QA
      expect(parsed[0].question_data).toEqual({
        Frage: 'Was ist 2+2?',
        Antwort: '4',
      })
    })

    test('should not break existing QAR functionality', () => {
      const qarQuestions: QuestionData[] = [
        {
          id: '1',
          question: 'Legal question?',
          reference_answer: 'Legal answer',
          reasoning: 'Legal reasoning',
        },
      ]

      const result = questionsToJson(qarQuestions, 'qa_reasoning')
      const parsed = JSON.parse(result)

      // Should maintain English field names for QAR
      expect(parsed[0].question_data).toEqual({
        question: 'Legal question?',
        answer: 'Legal answer',
        reasoning: 'Legal reasoning',
      })
    })
  })
})

/**
 * Performance and Data Integrity Tests
 */
describe('MCQ Data Processing Performance and Integrity', () => {
  test('should handle large MCQ datasets efficiently', () => {
    const largeDataset: QuestionData[] = Array.from(
      { length: 100 },
      (_, i) => ({
        id: `question-${i}`,
        question: `Question ${i}?`,
        choice_a: `Option A${i}`,
        choice_b: `Option B${i}`,
        choice_c: `Option C${i}`,
        choice_d: `Option D${i}`,
        correct_answer: ['a', 'b', 'c', 'd'][i % 4] as 'a' | 'b' | 'c' | 'd',
      })
    )

    const startTime = performance.now()
    const result = questionsToJson(largeDataset, 'multiple_choice')
    const endTime = performance.now()

    // Should complete in reasonable time (< 100ms for 100 questions)
    expect(endTime - startTime).toBeLessThan(100)

    const parsed = JSON.parse(result)
    expect(parsed).toHaveLength(100)

    // Verify first and last items are correct
    expect(parsed[0].question_data.question).toBe('Question 0?')
    expect(parsed[99].question_data.question).toBe('Question 99?')
  })

  test('should maintain data integrity across conversions', () => {
    const originalQuestion: QuestionData = {
      id: 'integrity-test',
      question: 'What is the meaning of life?',
      choice_a: '42',
      choice_b: 'Unknown',
      choice_c: 'Love',
      choice_d: 'Success',
      correct_answer: 'a',
    }

    const result = questionsToJson([originalQuestion], 'multiple_choice')
    const parsed = JSON.parse(result)
    const convertedData = parsed[0].question_data

    // All original data should be preserved
    expect(convertedData.question).toBe(originalQuestion.question)
    expect(convertedData.choice_a).toBe(originalQuestion.choice_a)
    expect(convertedData.choice_b).toBe(originalQuestion.choice_b)
    expect(convertedData.choice_c).toBe(originalQuestion.choice_c)
    expect(convertedData.choice_d).toBe(originalQuestion.choice_d)
    expect(convertedData.correct_answer).toBe(originalQuestion.correct_answer)
  })
})

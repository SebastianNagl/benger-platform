/**
 * Integration test for the nested data structure validation issue
 *
 * This test directly replicates the issue described where validation fails
 * for nested data structures like:
 * {
 *   "data": {
 *     "context": "Das Bürgerliche Gesetzbuch (BGB) ist die zentrale Kodifikation...",
 *     "question": "Wann trat das BGB in Kraft?"
 *   }
 * }
 */

import { validateTaskDataFields } from '../dataBinding'
import { extractDataFields, parseLabelConfig } from '../parser'

describe('Issue: Nested data structure validation', () => {
  it('should handle the exact issue case: nested data structure with context and question', () => {
    // This is the exact task data structure from the issue
    const taskData = {
      data: {
        context:
          'Das Bürgerliche Gesetzbuch (BGB) ist die zentrale Kodifikation...',
        question: 'Wann trat das BGB in Kraft?',
      },
    }

    // This is the typical label configuration that expects context and question
    const labelConfig = `
      <View>
        <Text name="context" value="$context"/>
        <Text name="question" value="$question"/>
        <TextArea name="answer" toName="context" placeholder="Enter your answer..." />
      </View>
    `

    // Parse the label config and extract required fields
    const parsed = parseLabelConfig(labelConfig)
    expect('message' in parsed).toBe(false) // Should parse successfully

    if ('message' in parsed) {
      throw new Error('Label config failed to parse')
    }

    const requiredFields = extractDataFields(parsed)
    expect(requiredFields).toEqual(['context', 'question'])

    // The validation should now pass with our fix
    const validation = validateTaskDataFields(requiredFields, taskData)

    expect(validation.valid).toBe(true)
    expect(validation.missingFields).toEqual([])
  })

  it('should show the error message that was occurring before the fix', () => {
    // Create a task data with missing fields to show what the error would look like
    const taskDataWithMissingFields = {
      data: {
        context:
          'Das Bürgerliche Gesetzbuch (BGB) ist die zentrale Kodifikation...',
        // Missing question field
      },
    }

    const requiredFields = ['context', 'question']
    const validation = validateTaskDataFields(
      requiredFields,
      taskDataWithMissingFields
    )

    expect(validation.valid).toBe(false)
    expect(validation.missingFields).toEqual(['question'])

    // This would generate the error message:
    // "Configuration Error: Missing required data fields: question"
    const errorMessage = `Configuration Error: Missing required data fields: ${validation.missingFields.join(', ')}`
    expect(errorMessage).toBe(
      'Configuration Error: Missing required data fields: question'
    )
  })

  it('should handle both formats: the old flat format and new nested format', () => {
    // Old flat format (still should work)
    const flatTaskData = {
      context:
        'Das Bürgerliche Gesetzbuch (BGB) ist die zentrale Kodifikation...',
      question: 'Wann trat das BGB in Kraft?',
    }

    // New nested format (the issue case)
    const nestedTaskData = {
      data: {
        context:
          'Das Bürgerliche Gesetzbuch (BGB) ist die zentrale Kodifikation...',
        question: 'Wann trat das BGB in Kraft?',
      },
    }

    const requiredFields = ['context', 'question']

    // Both should pass validation
    const flatValidation = validateTaskDataFields(requiredFields, flatTaskData)
    const nestedValidation = validateTaskDataFields(
      requiredFields,
      nestedTaskData
    )

    expect(flatValidation.valid).toBe(true)
    expect(nestedValidation.valid).toBe(true)
    expect(flatValidation.missingFields).toEqual([])
    expect(nestedValidation.missingFields).toEqual([])
  })

  it('should handle complex nested data with multiple levels', () => {
    // Task data with deeper nesting
    const complexTaskData = {
      data: {
        legal: {
          context: 'Complex legal case context',
          question: 'What is the legal question?',
        },
        metadata: {
          source: 'BGH',
          date: '2023-01-01',
        },
      },
    }

    const requiredFields = [
      'legal.context',
      'legal.question',
      'metadata.source',
    ]
    const validation = validateTaskDataFields(requiredFields, complexTaskData)

    expect(validation.valid).toBe(true)
    expect(validation.missingFields).toEqual([])
  })
})

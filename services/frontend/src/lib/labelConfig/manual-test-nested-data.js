#!/usr/bin/env node

/**
 * Manual test script to verify the nested data structure fix
 *
 * This can be run independently to test the data binding functionality
 * outside of the Jest environment.
 */

// Import the functions (Note: this would need to be adapted for Node.js execution)
const { validateTaskDataFields, resolveDataBinding } = require('../dataBinding')

console.log('=== Testing Nested Data Structure Fix ===\n')

// Test case 1: The exact issue case
console.log('Test 1: Exact issue case with nested data structure')
const nestedTaskData = {
  data: {
    context:
      'Das Bürgerliche Gesetzbuch (BGB) ist die zentrale Kodifikation...',
    question: 'Wann trat das BGB in Kraft?',
  },
}

const requiredFields = ['context', 'question']
const result1 = validateTaskDataFields(requiredFields, nestedTaskData)

console.log('Result:', result1)
console.log('Expected: { valid: true, missingFields: [] }')
console.log(
  '✓ Test 1 PASSED:',
  result1.valid === true && result1.missingFields.length === 0
)
console.log('')

// Test case 2: Data binding resolution
console.log('Test 2: Data binding resolution with nested data')
const contextValue = resolveDataBinding('$context', nestedTaskData)
const questionValue = resolveDataBinding('$question', nestedTaskData)

console.log('Context value:', contextValue)
console.log('Question value:', questionValue)
console.log(
  '✓ Test 2 PASSED:',
  contextValue ===
    'Das Bürgerliche Gesetzbuch (BGB) ist die zentrale Kodifikation...' &&
    questionValue === 'Wann trat das BGB in Kraft?'
)
console.log('')

// Test case 3: Backwards compatibility with flat structure
console.log('Test 3: Backwards compatibility with flat structure')
const flatTaskData = {
  context: 'Flat context',
  question: 'Flat question',
}

const result3 = validateTaskDataFields(requiredFields, flatTaskData)
const flatContextValue = resolveDataBinding('$context', flatTaskData)

console.log('Validation result:', result3)
console.log('Context value:', flatContextValue)
console.log(
  '✓ Test 3 PASSED:',
  result3.valid === true &&
    result3.missingFields.length === 0 &&
    flatContextValue === 'Flat context'
)
console.log('')

console.log('=== All tests completed ===')

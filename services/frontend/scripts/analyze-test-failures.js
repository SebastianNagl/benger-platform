#!/usr/bin/env node

const { execSync } = require('child_process')
const fs = require('fs')

// Run tests and capture output
console.log('🔍 Analyzing test failures...\n')

try {
  const output = execSync(
    'npm test -- --passWithNoTests --coverage=false --verbose',
    {
      encoding: 'utf8',
      maxBuffer: 1024 * 1024 * 10, // 10MB buffer
    }
  )
} catch (error) {
  const output = error.stdout + error.stderr

  // Parse failure patterns
  const failurePatterns = {
    apiMocking: [],
    componentInterface: [],
    hookErrors: [],
    translationKeys: [],
    clipboardErrors: [],
    timeoutErrors: [],
  }

  const lines = output.split('\n')
  let currentTest = ''

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]

    // Track current test file
    if (line.includes('FAIL ')) {
      currentTest = line.replace('FAIL ', '').trim()
    }

    // Categorize errors
    if (line.includes('Unable to find an element with the text:')) {
      failurePatterns.componentInterface.push({
        test: currentTest,
        error: line.trim(),
        type: 'missing_element',
      })
    }

    if (
      line.includes('Invalid hook call') ||
      line.includes('Hooks can only be called')
    ) {
      failurePatterns.hookErrors.push({
        test: currentTest,
        error: line.trim(),
        type: 'hook_error',
      })
    }

    if (line.includes('clipboardtimeout') || line.includes('writeText')) {
      failurePatterns.clipboardErrors.push({
        test: currentTest,
        error: line.trim(),
        type: 'clipboard_error',
      })
    }

    if (line.includes('waitFor') && line.includes('timeout')) {
      failurePatterns.timeoutErrors.push({
        test: currentTest,
        error: line.trim(),
        type: 'timeout_error',
      })
    }

    if (
      line.includes('projects.') ||
      line.includes('tasks.') ||
      line.includes('common.')
    ) {
      failurePatterns.translationKeys.push({
        test: currentTest,
        error: line.trim(),
        type: 'translation_key',
      })
    }

    if (
      line.includes('mockResolvedValue') ||
      line.includes('getTask') ||
      line.includes('API')
    ) {
      failurePatterns.apiMocking.push({
        test: currentTest,
        error: line.trim(),
        type: 'api_mock',
      })
    }
  }

  // Print analysis
  console.log('📊 Test Failure Analysis:\n')

  console.log(
    `🔧 Component Interface Issues: ${failurePatterns.componentInterface.length}`
  )
  failurePatterns.componentInterface.slice(0, 5).forEach((f) => {
    console.log(`  • ${f.test}: ${f.error.substring(0, 80)}...`)
  })

  console.log(`\n⚠️  Hook Errors: ${failurePatterns.hookErrors.length}`)
  failurePatterns.hookErrors.slice(0, 3).forEach((f) => {
    console.log(`  • ${f.test}: ${f.error.substring(0, 80)}...`)
  })

  console.log(
    `\n📋 Clipboard Errors: ${failurePatterns.clipboardErrors.length}`
  )
  failurePatterns.clipboardErrors.slice(0, 3).forEach((f) => {
    console.log(`  • ${f.test}: ${f.error.substring(0, 80)}...`)
  })

  console.log(`\n⏱️  Timeout Errors: ${failurePatterns.timeoutErrors.length}`)
  failurePatterns.timeoutErrors.slice(0, 3).forEach((f) => {
    console.log(`  • ${f.test}: ${f.error.substring(0, 80)}...`)
  })

  console.log(
    `\n🌐 Translation Key Errors: ${failurePatterns.translationKeys.length}`
  )
  failurePatterns.translationKeys.slice(0, 3).forEach((f) => {
    console.log(`  • ${f.test}: ${f.error.substring(0, 80)}...`)
  })

  console.log(`\n🔗 API Mocking Issues: ${failurePatterns.apiMocking.length}`)
  failurePatterns.apiMocking.slice(0, 3).forEach((f) => {
    console.log(`  • ${f.test}: ${f.error.substring(0, 80)}...`)
  })

  // Get test summary
  const summaryMatch = output.match(
    /Test Suites: (\d+) failed, (\d+) passed, (\d+) total/
  )
  if (summaryMatch) {
    const [, failed, passed, total] = summaryMatch
    console.log(
      `\n📈 Current Status: ${passed}/${total} test suites passing (${Math.round((passed / total) * 100)}%)`
    )
  }

  // Prioritized recommendations
  console.log('\n🎯 Priority Fix Recommendations:')
  if (failurePatterns.hookErrors.length > 0) {
    console.log(
      '1. ⚠️  Fix Hook Errors - These prevent tests from running at all'
    )
  }
  if (failurePatterns.componentInterface.length > 5) {
    console.log(
      '2. 🔧 Fix Component Interface Mismatches - Update tests to match current component API'
    )
  }
  if (failurePatterns.timeoutErrors.length > 3) {
    console.log('3. ⏱️  Fix Timeout Errors - Improve async test handling')
  }
  if (failurePatterns.clipboardErrors.length > 0) {
    console.log('4. 📋 Fix Clipboard Mocking - Standardize clipboard API mocks')
  }
}

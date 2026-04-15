#!/usr/bin/env node

const fs = require('fs')
const path = require('path')
const glob = require('glob')

// Fix functions
function fixGhostVariant(content, filePath) {
  const count = (content.match(/variant="ghost"/g) || []).length
  if (count > 0) {
    console.log(
      `  Fixing ${count} 'ghost' variant(s) in ${path.basename(filePath)}`
    )
    content = content.replace(/variant="ghost"/g, 'variant="text"')
  }
  return content
}

function fixSelectItemDefaultValue(content, filePath) {
  const pattern = /<SelectItem([^>]*)\sdefaultValue="([^"]*)"([^>]*)>/g
  const matches = content.match(pattern)
  if (matches && matches.length > 0) {
    console.log(
      `  Fixing ${matches.length} SelectItem defaultValue(s) in ${path.basename(filePath)}`
    )
    content = content.replace(pattern, '<SelectItem$1 value="$2"$3>')
  }
  return content
}

function fixImplicitAnyInCallbacks(content, filePath) {
  // Fix onValueChange callbacks with implicit any
  const pattern = /onValueChange=\{(\(value\))\s*=>/g
  const matches = content.match(pattern)
  if (matches && matches.length > 0) {
    console.log(
      `  Fixing ${matches.length} implicit any in onValueChange callbacks in ${path.basename(filePath)}`
    )
    content = content.replace(pattern, 'onValueChange={(value: string) =>')
  }

  // Fix setAdvancedSettings callbacks
  const setStatePattern = /\(prev\)\s*=>\s*\(\{/g
  const setStateMatches = content.match(setStatePattern)
  if (setStateMatches && setStateMatches.length > 0) {
    console.log(
      `  Fixing ${setStateMatches.length} implicit any in setState callbacks in ${path.basename(filePath)}`
    )
    content = content.replace(setStatePattern, '(prev: any) => ({')
  }

  return content
}

function addMissingApiExports(content, filePath) {
  if (filePath.includes('lib/api/index.ts')) {
    console.log(`  Adding missing type exports to API index`)

    // Check if exports are missing and add them
    if (!content.includes('EvaluationResult,')) {
      content = content.replace(
        /export type \{/,
        `export type {
  EvaluationResult,`
      )
    }

    if (!content.includes('LLMModelResponse,')) {
      content = content.replace(
        /export type \{/,
        `export type {
  LLMModelResponse,`
      )
    }

    if (!content.includes('EvaluationType,')) {
      content = content.replace(
        /export type \{/,
        `export type {
  EvaluationType,`
      )
    }

    if (!content.includes('PromptResponse,')) {
      // PromptResponse is already in the list, no need to add
    }
  }
  return content
}

function fixTaskDataProperty(content, filePath) {
  // For files that use task.data, cast task to any
  if (
    content.includes('task.data') &&
    !content.includes('(task as any).data')
  ) {
    const count = (content.match(/(?<!as any\))\.data/g) || []).length
    if (count > 0) {
      console.log(
        `  Fixing ${count} task.data references in ${path.basename(filePath)}`
      )
      // Be careful not to replace all .data, only task.data
      content = content.replace(/task\.data/g, '(task as any).data')
    }
  }
  return content
}

function fixTabsTriggerDefaultValue(content, filePath) {
  const pattern = /<TabsTrigger([^>]*)\sdefaultValue="([^"]*)"([^>]*)>/g
  const matches = content.match(pattern)
  if (matches && matches.length > 0) {
    console.log(
      `  Fixing ${matches.length} TabsTrigger defaultValue(s) in ${path.basename(filePath)}`
    )
    content = content.replace(pattern, '<TabsTrigger$1 value="$2"$3>')
  }
  return content
}

// Main function
async function fixTypeScriptErrors() {
  console.log('🔧 Fixing remaining TypeScript errors...\n')

  // Files to process
  const patterns = ['src/**/*.tsx', 'src/**/*.ts']

  let totalFixed = 0

  for (const pattern of patterns) {
    const files = glob.sync(pattern, {
      cwd: process.cwd(),
      ignore: ['node_modules/**', '**/*.test.*', '**/*.spec.*'],
    })

    for (const file of files) {
      const filePath = path.join(process.cwd(), file)
      let content = fs.readFileSync(filePath, 'utf-8')
      const originalContent = content

      // Apply fixes
      content = fixGhostVariant(content, filePath)
      content = fixSelectItemDefaultValue(content, filePath)
      content = fixTabsTriggerDefaultValue(content, filePath)
      content = fixImplicitAnyInCallbacks(content, filePath)
      content = addMissingApiExports(content, filePath)
      content = fixTaskDataProperty(content, filePath)

      // Write back if changed
      if (content !== originalContent) {
        fs.writeFileSync(filePath, content)
        totalFixed++
      }
    }
  }

  console.log(`\n✅ Fixed issues in ${totalFixed} files`)

  // Special fix for API types
  const apiTypesPath = path.join(process.cwd(), 'src/lib/api/types.ts')
  if (fs.existsSync(apiTypesPath)) {
    let apiTypesContent = fs.readFileSync(apiTypesPath, 'utf-8')

    // Ensure EvaluationResult is exported
    if (
      !apiTypesContent.includes('export interface EvaluationResult') &&
      !apiTypesContent.includes('export type EvaluationResult')
    ) {
      console.log(
        '\n⚠️  Note: EvaluationResult type may need to be defined in src/lib/api/types.ts'
      )
    }
  }

  console.log('\n📝 Next steps:')
  console.log('1. Run npm run type-check to verify fixes')
  console.log('2. Some errors may require manual intervention')
  console.log('3. Check for any remaining Task.data property issues')
}

// Run the script
fixTypeScriptErrors().catch(console.error)

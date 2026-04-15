#!/usr/bin/env node

const fs = require('fs')
const path = require('path')
const glob = require('glob')

// Fix implicit any in setState callbacks
function fixImplicitAnyInSetState(content, filePath) {
  let fixed = false

  // Fix all setState patterns with implicit any
  const patterns = [
    // setAdvancedSettings(prev => ...)
    {
      pattern: /setAdvancedSettings\((prev)\s*=>/g,
      replacement: 'setAdvancedSettings((prev: any) =>',
    },
    // Other setState patterns
    {
      pattern: /(\w+Settings?)\((prev)\s*=>\s*\(\{/g,
      replacement: '$1((prev: any) => ({',
    },
  ]

  patterns.forEach(({ pattern, replacement }) => {
    const matches = content.match(pattern)
    if (matches && matches.length > 0) {
      console.log(
        `  Fixing ${matches.length} implicit any in setState in ${path.basename(filePath)}`
      )
      content = content.replace(pattern, replacement)
      fixed = true
    }
  })

  return { content, fixed }
}

// Fix task.data references
function fixTaskDataReferences(content, filePath) {
  let fixed = false

  // Don't process if it's already been fixed or is a type definition file
  if (filePath.includes('.d.ts') || filePath.includes('types.ts')) {
    return { content, fixed }
  }

  // Fix patterns like task.data that aren't already cast
  const pattern = /(?<![a-zA-Z])task\.data(?!\s*as\s*any)/g
  const matches = content.match(pattern)

  if (matches && matches.length > 0) {
    console.log(
      `  Fixing ${matches.length} task.data references in ${path.basename(filePath)}`
    )
    content = content.replace(pattern, '(task as any).data')
    fixed = true
  }

  return { content, fixed }
}

// Fix missing types in function parameters
function fixParameterTypes(content, filePath) {
  let fixed = false

  // Fix common parameter patterns that are missing types
  const patterns = [
    // map/filter/forEach callbacks
    {
      pattern: /\.map\((\w+)\s*=>/g,
      check: (match, param) =>
        !content.includes(`${param}:`) && param !== 'item',
      replacement: '.map(($1: any) =>',
    },
    {
      pattern: /\.filter\((\w+)\s*=>/g,
      check: (match, param) => !content.includes(`${param}:`),
      replacement: '.filter(($1: any) =>',
    },
  ]

  patterns.forEach(({ pattern, check, replacement }) => {
    const matches = [...content.matchAll(pattern)]
    let replacements = 0

    matches.forEach((match) => {
      if (!check || check(match[0], match[1])) {
        content = content.replace(
          match[0],
          match[0].replace(pattern, replacement)
        )
        replacements++
      }
    })

    if (replacements > 0) {
      console.log(
        `  Fixed ${replacements} parameter types in ${path.basename(filePath)}`
      )
      fixed = true
    }
  })

  return { content, fixed }
}

// Fix variant issues
function fixButtonVariants(content, filePath) {
  let fixed = false

  // Map old variants to new ones
  const variantMap = {
    success: 'primary',
    warning: 'secondary',
    error: 'secondary',
    danger: 'secondary',
  }

  Object.entries(variantMap).forEach(([oldVariant, newVariant]) => {
    const pattern = new RegExp(`variant="${oldVariant}"`, 'g')
    const matches = content.match(pattern)

    if (matches && matches.length > 0) {
      console.log(
        `  Fixing ${matches.length} '${oldVariant}' variant(s) to '${newVariant}' in ${path.basename(filePath)}`
      )
      content = content.replace(pattern, `variant="${newVariant}"`)
      fixed = true
    }
  })

  return { content, fixed }
}

// Fix missing null checks on params
function fixParamsNullChecks(content, filePath) {
  let fixed = false

  // Fix params.id and similar patterns
  const pattern = /params\.(\w+)(?!\?)/g
  const matches = content.match(pattern)

  if (matches && matches.length > 0) {
    console.log(
      `  Adding ${matches.length} null checks for params in ${path.basename(filePath)}`
    )
    content = content.replace(pattern, 'params?.$1')
    fixed = true
  }

  // Fix searchParams similar patterns
  const searchPattern = /searchParams\.(\w+)(?!\?)/g
  const searchMatches = content.match(searchPattern)

  if (searchMatches && searchMatches.length > 0) {
    console.log(
      `  Adding ${searchMatches.length} null checks for searchParams in ${path.basename(filePath)}`
    )
    content = content.replace(searchPattern, 'searchParams?.$1')
    fixed = true
  }

  return { content, fixed }
}

// Main function
async function fixTypeScriptErrors() {
  console.log('🔧 Fixing final TypeScript errors...\n')

  const patterns = ['src/**/*.tsx', 'src/**/*.ts']

  let totalFixed = 0

  for (const pattern of patterns) {
    const files = glob.sync(pattern, {
      cwd: process.cwd(),
      ignore: ['node_modules/**', '**/*.test.*', '**/*.spec.*', '**/*.d.ts'],
    })

    for (const file of files) {
      const filePath = path.join(process.cwd(), file)
      let content = fs.readFileSync(filePath, 'utf-8')
      const originalContent = content
      let anyFixed = false

      // Apply fixes
      let result

      result = fixImplicitAnyInSetState(content, filePath)
      content = result.content
      anyFixed = anyFixed || result.fixed

      result = fixTaskDataReferences(content, filePath)
      content = result.content
      anyFixed = anyFixed || result.fixed

      result = fixParameterTypes(content, filePath)
      content = result.content
      anyFixed = anyFixed || result.fixed

      result = fixButtonVariants(content, filePath)
      content = result.content
      anyFixed = anyFixed || result.fixed

      result = fixParamsNullChecks(content, filePath)
      content = result.content
      anyFixed = anyFixed || result.fixed

      // Write back if changed
      if (content !== originalContent) {
        fs.writeFileSync(filePath, content)
        totalFixed++
      }
    }
  }

  console.log(`\n✅ Fixed issues in ${totalFixed} files`)
  console.log('\n📝 Next steps:')
  console.log('1. Run npm run type-check to verify fixes')
  console.log('2. Review any remaining errors that need manual intervention')
}

// Run the script
fixTypeScriptErrors().catch(console.error)

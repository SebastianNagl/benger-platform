#!/usr/bin/env node

/**
 * Script to enforce Jest-only testing in the codebase
 * Detects and optionally fixes Vitest syntax
 */

const fs = require('fs')
const path = require('path')
const glob = require('glob')

// Colors for console output
const colors = {
  red: '\x1b[31m',
  green: '\x1b[32m',
  yellow: '\x1b[33m',
  blue: '\x1b[34m',
  reset: '\x1b[0m',
}

// Patterns to detect Vitest usage
const vitestPatterns = [
  {
    name: 'Vitest imports',
    pattern: /from ['"]vitest['"]/g,
    fix: (match) => `from '@jest/globals'`,
    severity: 'error',
  },
  {
    name: 'vi.fn() usage',
    pattern: /\bvi\.fn\(/g,
    fix: (match) => 'jest.fn(',
    severity: 'error',
  },
  {
    name: 'vi.mock() usage',
    pattern: /\bvi\.mock\(/g,
    fix: (match) => 'jest.mock(',
    severity: 'error',
  },
  {
    name: 'vi.spyOn() usage',
    pattern: /\bvi\.spyOn\(/g,
    fix: (match) => 'jest.spyOn(',
    severity: 'error',
  },
  {
    name: 'vi.clearAllMocks() usage',
    pattern: /\bvi\.clearAllMocks\(/g,
    fix: (match) => 'jest.clearAllMocks(',
    severity: 'error',
  },
  {
    name: 'vi.resetAllMocks() usage',
    pattern: /\bvi\.resetAllMocks\(/g,
    fix: (match) => 'jest.resetAllMocks(',
    severity: 'error',
  },
  {
    name: 'vi.mocked() usage',
    pattern: /\bvi\.mocked\(/g,
    fix: (match) => 'jest.mocked(',
    severity: 'error',
  },
  {
    name: 'import vi',
    pattern: /import\s*{\s*[^}]*\bvi\b[^}]*}\s*from/g,
    fix: (match) => {
      // Replace vi with jest in import statements
      return match.replace(/\bvi\b/g, 'jest')
    },
    severity: 'error',
  },
]

function findTestFiles() {
  const patterns = [
    'src/**/*.test.ts',
    'src/**/*.test.tsx',
    'src/**/*.test.js',
    'src/**/*.test.jsx',
    'src/**/*.spec.ts',
    'src/**/*.spec.tsx',
    'src/**/*.spec.js',
    'src/**/*.spec.jsx',
  ]

  let files = []
  patterns.forEach((pattern) => {
    files = files.concat(glob.sync(pattern))
  })

  return files
}

function checkFile(filePath, fix = false) {
  let content = fs.readFileSync(filePath, 'utf8')
  const originalContent = content
  const issues = []

  vitestPatterns.forEach(({ name, pattern, fix: fixFn, severity }) => {
    const matches = content.match(pattern)
    if (matches) {
      issues.push({
        name,
        count: matches.length,
        severity,
        examples: matches.slice(0, 3),
      })

      if (fix && fixFn) {
        content = content.replace(pattern, fixFn)
      }
    }
  })

  if (fix && content !== originalContent) {
    // Additional cleanup: ensure jest is imported if we're using it
    if (
      content.includes('jest.') &&
      !content.includes("from '@jest/globals'") &&
      !content.includes("from 'jest'")
    ) {
      // Add jest import at the top of the file if not present
      const importStatement = "import { jest } from '@jest/globals'\n"

      // Find the right place to insert (after other imports)
      const firstImportMatch = content.match(/^import .* from/m)
      if (firstImportMatch) {
        const lines = content.split('\n')
        let lastImportIndex = 0
        for (let i = 0; i < lines.length; i++) {
          if (lines[i].startsWith('import ')) {
            lastImportIndex = i
          }
        }
        lines.splice(lastImportIndex + 1, 0, importStatement)
        content = lines.join('\n')
      } else {
        content = importStatement + content
      }
    }

    fs.writeFileSync(filePath, content, 'utf8')
  }

  return {
    filePath,
    issues,
    fixed: fix && content !== originalContent,
  }
}

function main() {
  const args = process.argv.slice(2)
  const shouldFix = args.includes('--fix')
  const quiet = args.includes('--quiet')

  console.log(
    `${colors.blue}🔍 Checking for Vitest usage in test files...${colors.reset}\n`
  )

  const testFiles = findTestFiles()
  console.log(`Found ${testFiles.length} test files to check.\n`)

  let totalIssues = 0
  let filesWithIssues = 0
  let filesFixed = 0
  const allIssues = []

  testFiles.forEach((file) => {
    const result = checkFile(file, shouldFix)

    if (result.issues.length > 0) {
      filesWithIssues++
      totalIssues += result.issues.reduce((sum, issue) => sum + issue.count, 0)

      if (!quiet) {
        console.log(
          `${colors.yellow}📄 ${path.relative(process.cwd(), file)}${colors.reset}`
        )
        result.issues.forEach((issue) => {
          const color = issue.severity === 'error' ? colors.red : colors.yellow
          console.log(
            `  ${color}✗ ${issue.name}: ${issue.count} occurrence(s)${colors.reset}`
          )
          if (!shouldFix) {
            issue.examples.forEach((example) => {
              console.log(
                `    Example: ${colors.blue}${example}${colors.reset}`
              )
            })
          }
        })

        if (result.fixed) {
          filesFixed++
          console.log(`  ${colors.green}✓ Fixed!${colors.reset}`)
        }
        console.log()
      }

      allIssues.push(result)
    }
  })

  // Summary
  console.log(`${colors.blue}${'='.repeat(60)}${colors.reset}`)
  console.log(`${colors.blue}Summary:${colors.reset}`)
  console.log(`  Total test files checked: ${testFiles.length}`)
  console.log(`  Files with Vitest usage: ${filesWithIssues}`)
  console.log(`  Total Vitest instances: ${totalIssues}`)

  if (shouldFix) {
    console.log(`  ${colors.green}Files fixed: ${filesFixed}${colors.reset}`)
  }

  if (filesWithIssues > 0 && !shouldFix) {
    console.log(
      `\n${colors.yellow}💡 Run with --fix flag to automatically fix these issues:${colors.reset}`
    )
    console.log(`  ${colors.blue}npm run enforce-jest -- --fix${colors.reset}`)
    process.exit(1)
  } else if (filesWithIssues === 0) {
    console.log(
      `\n${colors.green}✅ No Vitest usage found! The codebase is Jest-only.${colors.reset}`
    )
  } else if (shouldFix) {
    console.log(
      `\n${colors.green}✅ All Vitest usage has been replaced with Jest!${colors.reset}`
    )
  }
}

// Run the script
main()

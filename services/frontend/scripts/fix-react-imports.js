#!/usr/bin/env node

const fs = require('fs')
const path = require('path')
const glob = require('glob')

function fixReactImports(filePath) {
  try {
    let content = fs.readFileSync(filePath, 'utf8')
    const originalContent = content
    let hasChanges = false

    // Check if the file has React components but no React import
    const hasReactComponents =
      content.includes('<') &&
      (content.includes('render(') ||
        content.includes('createElement') ||
        content.includes('JSX') ||
        content.includes('React.') ||
        content.includes('useState') ||
        content.includes('useEffect') ||
        content.includes('<div') ||
        content.includes('<button') ||
        content.includes('<span'))

    const hasReactImport =
      content.includes("import React from 'react'") ||
      content.includes("import * as React from 'react'") ||
      content.includes("const React = require('react')")

    if (hasReactComponents && !hasReactImport) {
      // Add React import at the top after jest mocks but before other imports
      const lines = content.split('\n')
      let insertIndex = 0

      // Find where to insert React import (after jest mocks, before other imports)
      for (let i = 0; i < lines.length; i++) {
        const line = lines[i]
        if (
          line.startsWith('import') &&
          !line.includes('jest') &&
          !line.includes('@testing-library')
        ) {
          insertIndex = i
          break
        }
      }

      if (insertIndex === 0) {
        // No imports found, add after last jest.mock
        for (let i = lines.length - 1; i >= 0; i--) {
          if (lines[i].includes('jest.mock') || lines[i].includes('}))')) {
            insertIndex = i + 1
            break
          }
        }
      }

      // Insert React import
      lines.splice(insertIndex, 0, "import React from 'react'")
      content = lines.join('\n')
      hasChanges = true
    }

    // Fix navigator.clipboard mocking issues
    if (
      content.includes('navigator.clipboard.writeText') &&
      !content.includes("Object.defineProperty(navigator, 'clipboard'")
    ) {
      // Add clipboard mock setup
      const mockSetup = `
// Mock navigator.clipboard
Object.defineProperty(navigator, 'clipboard', {
  value: {
    writeText: jest.fn()
  },
  writable: true
});
`

      // Find a good place to insert it (after imports, before describe blocks)
      const lines = content.split('\n')
      let insertIndex = 0

      for (let i = 0; i < lines.length; i++) {
        const line = lines[i]
        if (line.includes('describe(')) {
          insertIndex = i
          break
        }
      }

      if (insertIndex > 0) {
        lines.splice(insertIndex, 0, mockSetup)
        content = lines.join('\n')
        hasChanges = true
      }
    }

    // Fix missing @jest-environment jsdom declarations
    if (
      (content.includes('render(') || content.includes('screen.')) &&
      !content.includes('@jest-environment jsdom')
    ) {
      // Add @jest-environment jsdom at the top
      const lines = content.split('\n')

      // Find first non-comment line
      let insertIndex = 0
      for (let i = 0; i < lines.length; i++) {
        const line = lines[i].trim()
        if (
          line &&
          !line.startsWith('/**') &&
          !line.startsWith('*') &&
          !line.startsWith('//')
        ) {
          insertIndex = i
          break
        }
      }

      lines.splice(insertIndex, 0, '/**\n * @jest-environment jsdom\n */\n')
      content = lines.join('\n')
      hasChanges = true
    }

    if (hasChanges) {
      fs.writeFileSync(filePath, content, 'utf8')
      return true
    }
    return false
  } catch (error) {
    console.error(`Error processing ${filePath}:`, error.message)
    return false
  }
}

// Main execution
console.log('🔧 Fixing React imports and environment issues...\n')

const testFiles = glob.sync('src/**/*.test.{ts,tsx}', {
  cwd: path.join(__dirname, '..'),
  absolute: true,
})

let fixedCount = 0

for (const file of testFiles) {
  const relativePath = path.relative(path.join(__dirname, '..'), file)
  if (fixReactImports(file)) {
    console.log(`  ✅ Fixed: ${relativePath}`)
    fixedCount++
  }
}

console.log(
  `\n✨ Fixed ${fixedCount} files with React import and environment issues`
)

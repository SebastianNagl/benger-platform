#!/usr/bin/env node

const fs = require('fs')
const path = require('path')
const glob = require('glob')

function fixI18nMocks(filePath) {
  try {
    let content = fs.readFileSync(filePath, 'utf8')
    const originalContent = content
    let hasChanges = false

    // Check if file uses translation keys (likely patterns)
    const hasTranslationKeys =
      content.includes('searchPlaceholder') ||
      content.includes('noProjects') ||
      content.includes('loading') ||
      content.includes('.t(') ||
      content.includes('useI18n') ||
      content.includes('expect(').includes('Search projects') ||
      content.includes('expect(').includes('Loading') ||
      content.includes('expect(').includes('No projects')

    const hasI18nMock =
      content.includes('@/contexts/I18nContext') &&
      content.includes('jest.mock')

    if (hasTranslationKeys && !hasI18nMock) {
      // Add i18n mock after other mocks
      const mockToAdd = `
// Mock i18n context
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string) => {
      const translations: Record<string, string> = {
        'projects.searchPlaceholder': 'Search projects...',
        'projects.noProjects': 'No projects found',
        'projects.loading': 'Loading projects...',
        'tasks.searchPlaceholder': 'Search tasks...',
        'tasks.noTasks': 'No tasks found',
        'tasks.loading': 'Loading tasks...',
        'common.search': 'Search',
        'common.loading': 'Loading...',
        'common.save': 'Save',
        'common.cancel': 'Cancel',
        'common.delete': 'Delete',
        'common.edit': 'Edit',
        'common.create': 'Create',
        'common.update': 'Update',
        'common.close': 'Close',
        'annotations.loading': 'Loading annotations...',
        'annotations.noAnnotations': 'No annotations found',
        'quality.title': 'Quality Control',
        'quality.loading': 'Loading quality metrics...',
        'analytics.title': 'Analytics',
        'analytics.loading': 'Loading analytics...',
      }
      return translations[key] || key
    },
    currentLanguage: 'en'
  })
}))
`

      // Find a good place to insert it (after existing jest.mock statements)
      const lines = content.split('\n')
      let insertIndex = 0

      // Look for the last jest.mock line
      for (let i = lines.length - 1; i >= 0; i--) {
        if (lines[i].includes('jest.mock(') || lines[i].includes('}))')) {
          // Find the end of this mock block
          for (let j = i; j < lines.length; j++) {
            if (
              lines[j].includes('}))') ||
              (lines[j].includes('}') && lines[j].includes(')'))
            ) {
              insertIndex = j + 1
              break
            }
          }
          break
        }
      }

      if (insertIndex === 0) {
        // No mocks found, add before imports
        for (let i = 0; i < lines.length; i++) {
          if (lines[i].startsWith('import') && !lines[i].includes('jest')) {
            insertIndex = i
            break
          }
        }
      }

      if (insertIndex > 0) {
        lines.splice(insertIndex, 0, mockToAdd)
        content = lines.join('\n')
        hasChanges = true
      }
    }

    if (originalContent !== content) {
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
console.log('🔧 Fixing i18n mocks in test files...\n')

const testFiles = glob.sync('src/**/*.test.{ts,tsx}', {
  cwd: path.join(__dirname, '..'),
  absolute: true,
})

let fixedCount = 0

for (const file of testFiles) {
  const relativePath = path.relative(path.join(__dirname, '..'), file)
  if (fixI18nMocks(file)) {
    console.log(`  ✅ Fixed: ${relativePath}`)
    fixedCount++
  }
}

console.log(`\n✨ Fixed ${fixedCount} files with i18n mocking issues`)

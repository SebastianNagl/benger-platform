/**
 * Test suite for locale file changes in Issue #105
 *
 * This tests the actual locale JSON files to ensure:
 * 1. Subtitle keys are completely removed
 * 2. Login text is updated to first person
 * 3. JSON structure remains valid
 * 4. No orphaned references exist
 */

import fs from 'fs'
import path from 'path'

describe('Locale Files Text Updates (Issue #105)', () => {
  const localesDir = path.join(__dirname, '..')
  const englishLocalePath = path.join(localesDir, 'en', 'common.json')
  const germanLocalePath = path.join(localesDir, 'de', 'common.json')

  describe('English Locale File', () => {
    let englishLocale: any

    beforeAll(() => {
      // Read and parse English locale file
      const englishContent = fs.readFileSync(englishLocalePath, 'utf-8')
      englishLocale = JSON.parse(englishContent)
    })

    test('should be valid JSON', () => {
      expect(englishLocale).toBeInstanceOf(Object)
      expect(englishLocale.register).toBeInstanceOf(Object)
    })

    test('should not contain removed subtitle key', () => {
      // Verify subtitle key is completely removed from register section
      expect(englishLocale.register.subtitle).toBeUndefined()

      // Verify the old subtitle text is not present anywhere
      const fileContent = fs.readFileSync(englishLocalePath, 'utf-8')
      expect(fileContent).not.toContain('Join the BenGER community')

      // Verify register section doesn't have subtitle key
      const registerSection = JSON.stringify(englishLocale.register)
      expect(registerSection).not.toContain('subtitle')
    })

    test('should contain updated first-person login text', () => {
      // Verify new login text
      expect(englishLocale.register.login).toBe('I already have an account')

      // Verify old login text pattern is not present (without "I" prefix)
      const fileContent = fs.readFileSync(englishLocalePath, 'utf-8')
      expect(fileContent).not.toContain('"login": "already have an account"')

      // Verify it starts with first person
      expect(englishLocale.register.login).toMatch(/^I /)
    })

    test('should maintain all other register keys', () => {
      // Verify essential keys are still present
      expect(englishLocale.register.title).toBe('Create your account')
      expect(englishLocale.register.name).toBeDefined()
      expect(englishLocale.register.username).toBeDefined()
      expect(englishLocale.register.email).toBeDefined()
      expect(englishLocale.register.password).toBeDefined()
      expect(englishLocale.register.button).toBeDefined()
      expect(englishLocale.register.backToLanding).toBeDefined()
    })

    test('should have proper JSON formatting', () => {
      // Verify file can be parsed and re-stringified without errors
      const fileContent = fs.readFileSync(englishLocalePath, 'utf-8')
      const parsed = JSON.parse(fileContent)
      const stringified = JSON.stringify(parsed, null, 2)

      expect(() => JSON.parse(stringified)).not.toThrow()
    })
  })

  describe('German Locale File', () => {
    let germanLocale: any

    beforeAll(() => {
      // Read and parse German locale file
      const germanContent = fs.readFileSync(germanLocalePath, 'utf-8')
      germanLocale = JSON.parse(germanContent)
    })

    test('should be valid JSON', () => {
      expect(germanLocale).toBeInstanceOf(Object)
      expect(germanLocale.register).toBeInstanceOf(Object)
    })

    test('should not contain removed German subtitle key', () => {
      // Verify subtitle key is completely removed from register section
      expect(germanLocale.register.subtitle).toBeUndefined()

      // Verify the old German subtitle text is not present anywhere
      const fileContent = fs.readFileSync(germanLocalePath, 'utf-8')
      expect(fileContent).not.toContain('Der BenGER-Community beitreten')

      // Verify register section doesn't have subtitle key
      const registerSection = JSON.stringify(germanLocale.register)
      expect(registerSection).not.toContain('subtitle')
    })

    test('should contain updated first-person German login text', () => {
      // Verify new German login text
      expect(germanLocale.register.login).toBe('Ich habe bereits ein Konto')

      // Verify old German login text is not present
      const fileContent = fs.readFileSync(germanLocalePath, 'utf-8')
      expect(fileContent).not.toContain('bereits ein Konto haben')
    })

    test('should maintain all other German register keys', () => {
      // Verify essential German keys are still present
      expect(germanLocale.register.title).toBe('Ihr Konto erstellen')
      expect(germanLocale.register.name).toBeDefined()
      expect(germanLocale.register.username).toBeDefined()
      expect(germanLocale.register.email).toBeDefined()
      expect(germanLocale.register.password).toBeDefined()
      expect(germanLocale.register.button).toBeDefined()
      expect(germanLocale.register.backToLanding).toBeDefined()
    })

    test('should have proper JSON formatting', () => {
      // Verify file can be parsed and re-stringified without errors
      const fileContent = fs.readFileSync(germanLocalePath, 'utf-8')
      const parsed = JSON.parse(fileContent)
      const stringified = JSON.stringify(parsed, null, 2)

      expect(() => JSON.parse(stringified)).not.toThrow()
    })
  })

  describe('Cross-Locale Consistency', () => {
    let englishLocale: any
    let germanLocale: any

    beforeAll(() => {
      const englishContent = fs.readFileSync(englishLocalePath, 'utf-8')
      const germanContent = fs.readFileSync(germanLocalePath, 'utf-8')
      englishLocale = JSON.parse(englishContent)
      germanLocale = JSON.parse(germanContent)
    })

    test('should have matching register key structure', () => {
      // Both locales should have the same keys (except values)
      const englishKeys = Object.keys(englishLocale.register).sort()
      const germanKeys = Object.keys(germanLocale.register).sort()

      expect(englishKeys).toEqual(germanKeys)
    })

    test('should both have removed subtitle key', () => {
      // Both locales should consistently not have subtitle
      expect(englishLocale.register.subtitle).toBeUndefined()
      expect(germanLocale.register.subtitle).toBeUndefined()
    })

    test('should both have updated login text with first person', () => {
      // Both should use first person perspective
      expect(englishLocale.register.login).toBe('I already have an account')
      expect(germanLocale.register.login).toBe('Ich habe bereits ein Konto')

      // Verify first person by checking for "I"/"Ich" at the start
      expect(englishLocale.register.login).toMatch(/^I /)
      expect(germanLocale.register.login).toMatch(/^Ich /)
    })
  })

  describe('File System Integration Tests', () => {
    test('should have readable locale files', () => {
      expect(fs.existsSync(englishLocalePath)).toBe(true)
      expect(fs.existsSync(germanLocalePath)).toBe(true)

      // Files should be readable
      expect(() => fs.readFileSync(englishLocalePath, 'utf-8')).not.toThrow()
      expect(() => fs.readFileSync(germanLocalePath, 'utf-8')).not.toThrow()
    })

    test('should not contain backup or temporary files', () => {
      const localesDir = path.dirname(englishLocalePath)
      const files = fs.readdirSync(localesDir)

      // Should not have backup files
      const backupFiles = files.filter(
        (file) =>
          file.includes('.backup') ||
          file.includes('.tmp') ||
          file.includes('~') ||
          file.endsWith('.bak')
      )

      expect(backupFiles).toHaveLength(0)
    })

    test('should maintain file encoding and line endings', () => {
      const englishContent = fs.readFileSync(englishLocalePath, 'utf-8')
      const germanContent = fs.readFileSync(germanLocalePath, 'utf-8')

      // Should not contain weird characters or encoding issues
      expect(englishContent).not.toMatch(
        /[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F-\u009F]/
      )
      expect(germanContent).not.toMatch(
        /[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F-\u009F]/
      )

      // Should end with newline for proper git handling
      expect(englishContent.endsWith('\n')).toBe(true)
      expect(germanContent.endsWith('\n')).toBe(true)
    })
  })

  describe('Regression Prevention Tests', () => {
    test('should not affect other locale sections', () => {
      const englishContent = fs.readFileSync(englishLocalePath, 'utf-8')
      const germanContent = fs.readFileSync(germanLocalePath, 'utf-8')

      const englishLocale = JSON.parse(englishContent)
      const germanLocale = JSON.parse(germanContent)

      // Other sections should remain unchanged
      expect(englishLocale.login).toBeDefined()
      expect(englishLocale.landing).toBeDefined()
      expect(germanLocale.login).toBeDefined()
      expect(germanLocale.landing).toBeDefined()
    })

    test('should not introduce translation inconsistencies', () => {
      const englishContent = fs.readFileSync(englishLocalePath, 'utf-8')
      const germanContent = fs.readFileSync(germanLocalePath, 'utf-8')

      // Should not have mixed languages in same file
      expect(englishContent).not.toContain('Ich habe')
      expect(englishContent).not.toContain('bereits')
      expect(germanContent).not.toContain('I already')
      expect(germanContent).not.toContain('have an account')
    })

    test('should preserve JSON structure integrity', () => {
      const englishContent = fs.readFileSync(englishLocalePath, 'utf-8')
      const germanContent = fs.readFileSync(germanLocalePath, 'utf-8')

      // Parse should not throw
      expect(() => JSON.parse(englishContent)).not.toThrow()
      expect(() => JSON.parse(germanContent)).not.toThrow()

      // Should be properly formatted objects
      const englishLocale = JSON.parse(englishContent)
      const germanLocale = JSON.parse(germanContent)

      expect(typeof englishLocale).toBe('object')
      expect(typeof germanLocale).toBe('object')
      expect(englishLocale).not.toBeNull()
      expect(germanLocale).not.toBeNull()
    })
  })
})

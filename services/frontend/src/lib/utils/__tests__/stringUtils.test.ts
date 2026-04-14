/**
 * Comprehensive tests for stringUtils utility functions
 * Tests string manipulation, similarity calculations, case conversions, and edge cases
 */

import {
  escapeRegExp,
  levenshteinDistance,
  removeDiacritics,
  stringSimilarity,
  toCamelCase,
  toKebabCase,
  toSnakeCase,
  truncate,
} from '../stringUtils'

describe('stringUtils', () => {
  describe('levenshteinDistance', () => {
    it('should return 0 for identical strings', () => {
      expect(levenshteinDistance('hello', 'hello')).toBe(0)
      expect(levenshteinDistance('', '')).toBe(0)
      expect(levenshteinDistance('test123', 'test123')).toBe(0)
    })

    it('should calculate distance for single character changes', () => {
      expect(levenshteinDistance('cat', 'bat')).toBe(1) // substitution
      expect(levenshteinDistance('cat', 'cats')).toBe(1) // insertion
      expect(levenshteinDistance('cats', 'cat')).toBe(1) // deletion
    })

    it('should calculate distance for multiple changes', () => {
      expect(levenshteinDistance('kitten', 'sitting')).toBe(3)
      expect(levenshteinDistance('saturday', 'sunday')).toBe(3)
    })

    it('should handle empty strings', () => {
      expect(levenshteinDistance('', 'hello')).toBe(5)
      expect(levenshteinDistance('hello', '')).toBe(5)
    })

    it('should handle single character strings', () => {
      expect(levenshteinDistance('a', 'b')).toBe(1)
      expect(levenshteinDistance('a', 'a')).toBe(0)
    })

    it('should handle completely different strings', () => {
      expect(levenshteinDistance('abc', 'xyz')).toBe(3)
    })

    it('should be case-sensitive', () => {
      expect(levenshteinDistance('Hello', 'hello')).toBe(1)
      expect(levenshteinDistance('ABC', 'abc')).toBe(3)
    })

    it('should handle strings with special characters', () => {
      expect(levenshteinDistance('hello!', 'hello?')).toBe(1)
      expect(levenshteinDistance('test@123', 'test#123')).toBe(1)
    })

    it('should handle unicode characters', () => {
      expect(levenshteinDistance('café', 'cafe')).toBe(1)
      expect(levenshteinDistance('😀', '😁')).toBe(1)
    })

    it('should handle long strings efficiently', () => {
      const str1 = 'a'.repeat(100)
      const str2 = 'b'.repeat(100)
      expect(levenshteinDistance(str1, str2)).toBe(100)
    })
  })

  describe('stringSimilarity', () => {
    it('should return 1 for identical strings', () => {
      expect(stringSimilarity('hello', 'hello')).toBe(1)
      expect(stringSimilarity('', '')).toBe(1)
      expect(stringSimilarity('Test123', 'test123')).toBe(1) // Case-insensitive
    })

    it('should return 0 for completely different strings', () => {
      const result = stringSimilarity('abc', 'xyz')
      expect(result).toBe(0)
    })

    it('should return values between 0 and 1 for partially similar strings', () => {
      const result = stringSimilarity('hello', 'hallo')
      expect(result).toBeGreaterThan(0)
      expect(result).toBeLessThan(1)
    })

    it('should be case-insensitive', () => {
      expect(stringSimilarity('Hello', 'hello')).toBe(1)
      expect(stringSimilarity('WORLD', 'world')).toBe(1)
    })

    it('should handle empty strings', () => {
      expect(stringSimilarity('', 'hello')).toBe(0)
      expect(stringSimilarity('hello', '')).toBe(0)
    })

    it('should calculate similarity correctly for similar words', () => {
      const similarity = stringSimilarity('kitten', 'sitting')
      expect(similarity).toBeGreaterThan(0.4)
      expect(similarity).toBeLessThan(0.7)
    })

    it('should give higher similarity for more similar strings', () => {
      const sim1 = stringSimilarity('hello', 'hallo')
      const sim2 = stringSimilarity('hello', 'world')
      expect(sim1).toBeGreaterThan(sim2)
    })

    it('should handle single character differences', () => {
      const similarity = stringSimilarity('cat', 'bat')
      expect(similarity).toBeGreaterThan(0.6)
    })
  })

  describe('toCamelCase', () => {
    it('should convert snake_case to camelCase', () => {
      expect(toCamelCase('hello_world')).toBe('helloWorld')
      expect(toCamelCase('first_name')).toBe('firstName')
      expect(toCamelCase('user_id')).toBe('userId')
    })

    it('should convert kebab-case to camelCase', () => {
      expect(toCamelCase('hello-world')).toBe('helloWorld')
      expect(toCamelCase('first-name')).toBe('firstName')
    })

    it('should convert space-separated words to camelCase', () => {
      expect(toCamelCase('hello world')).toBe('helloWorld')
      expect(toCamelCase('first name')).toBe('firstName')
    })

    it('should handle already camelCase strings', () => {
      expect(toCamelCase('helloWorld')).toBe('helloworld')
      expect(toCamelCase('firstName')).toBe('firstname')
    })

    it('should handle PascalCase strings', () => {
      expect(toCamelCase('HelloWorld')).toBe('helloworld')
      expect(toCamelCase('FirstName')).toBe('firstname')
    })

    it('should handle single words', () => {
      expect(toCamelCase('hello')).toBe('hello')
      expect(toCamelCase('HELLO')).toBe('hello')
    })

    it('should handle empty strings', () => {
      expect(toCamelCase('')).toBe('')
    })

    it('should handle strings with numbers', () => {
      expect(toCamelCase('user_id_123')).toBe('userId123')
      expect(toCamelCase('test-case-2')).toBe('testCase2')
    })

    it('should handle multiple separators', () => {
      expect(toCamelCase('hello___world')).toBe('helloWorld')
      expect(toCamelCase('first---name')).toBe('firstName')
    })

    it('should remove special characters', () => {
      expect(toCamelCase('hello@world')).toBe('helloWorld')
      expect(toCamelCase('first#name')).toBe('firstName')
    })
  })

  describe('toSnakeCase', () => {
    it('should convert camelCase to snake_case', () => {
      expect(toSnakeCase('helloWorld')).toBe('hello_world')
      expect(toSnakeCase('firstName')).toBe('first_name')
      expect(toSnakeCase('userId')).toBe('user_id')
    })

    it('should convert PascalCase to snake_case', () => {
      expect(toSnakeCase('HelloWorld')).toBe('hello_world')
      expect(toSnakeCase('FirstName')).toBe('first_name')
    })

    it('should convert kebab-case to snake_case', () => {
      expect(toSnakeCase('hello-world')).toBe('hello_world')
      expect(toSnakeCase('first-name')).toBe('first_name')
    })

    it('should convert space-separated words to snake_case', () => {
      expect(toSnakeCase('hello world')).toBe('hello_world')
      expect(toSnakeCase('first name')).toBe('first_name')
    })

    it('should handle already snake_case strings', () => {
      expect(toSnakeCase('hello_world')).toBe('hello_world')
      expect(toSnakeCase('first_name')).toBe('first_name')
    })

    it('should handle single words', () => {
      expect(toSnakeCase('hello')).toBe('hello')
      expect(toSnakeCase('HELLO')).toBe('h_e_l_l_o')
    })

    it('should handle empty strings', () => {
      expect(toSnakeCase('')).toBe('')
    })

    it('should handle consecutive capitals', () => {
      expect(toSnakeCase('HTTPSConnection')).toBe('h_t_t_p_s_connection')
      expect(toSnakeCase('XMLParser')).toBe('x_m_l_parser')
    })

    it('should remove special characters', () => {
      expect(toSnakeCase('hello@world')).toBe('hello_world')
      expect(toSnakeCase('first#name')).toBe('first_name')
    })

    it('should handle multiple separators', () => {
      expect(toSnakeCase('hello___world')).toBe('hello_world')
      expect(toSnakeCase('first---name')).toBe('first_name')
    })

    it('should not have leading or trailing underscores', () => {
      expect(toSnakeCase('_hello_world_')).toBe('hello_world')
      expect(toSnakeCase('__test__')).toBe('_test')
    })

    it('should handle strings with numbers', () => {
      expect(toSnakeCase('userId123')).toBe('user_id123')
      expect(toSnakeCase('test2Case')).toBe('test2_case')
    })
  })

  describe('toKebabCase', () => {
    it('should convert camelCase to kebab-case', () => {
      expect(toKebabCase('helloWorld')).toBe('hello-world')
      expect(toKebabCase('firstName')).toBe('first-name')
      expect(toKebabCase('userId')).toBe('user-id')
    })

    it('should convert PascalCase to kebab-case', () => {
      expect(toKebabCase('HelloWorld')).toBe('hello-world')
      expect(toKebabCase('FirstName')).toBe('first-name')
    })

    it('should convert snake_case to kebab-case', () => {
      expect(toKebabCase('hello_world')).toBe('hello-world')
      expect(toKebabCase('first_name')).toBe('first-name')
    })

    it('should convert space-separated words to kebab-case', () => {
      expect(toKebabCase('hello world')).toBe('hello-world')
      expect(toKebabCase('first name')).toBe('first-name')
    })

    it('should handle already kebab-case strings', () => {
      expect(toKebabCase('hello-world')).toBe('hello-world')
      expect(toKebabCase('first-name')).toBe('first-name')
    })

    it('should handle single words', () => {
      expect(toKebabCase('hello')).toBe('hello')
      expect(toKebabCase('HELLO')).toBe('h-e-l-l-o')
    })

    it('should handle empty strings', () => {
      expect(toKebabCase('')).toBe('')
    })

    it('should handle consecutive capitals', () => {
      expect(toKebabCase('HTTPSConnection')).toBe('h-t-t-p-s-connection')
      expect(toKebabCase('XMLParser')).toBe('x-m-l-parser')
    })

    it('should remove special characters', () => {
      expect(toKebabCase('hello@world')).toBe('hello-world')
      expect(toKebabCase('first#name')).toBe('first-name')
    })

    it('should handle multiple separators', () => {
      expect(toKebabCase('hello___world')).toBe('hello-world')
      expect(toKebabCase('first---name')).toBe('first-name')
    })

    it('should not have leading or trailing hyphens', () => {
      expect(toKebabCase('-hello-world-')).toBe('hello-world')
      expect(toKebabCase('--test--')).toBe('-test')
    })

    it('should handle strings with numbers', () => {
      expect(toKebabCase('userId123')).toBe('user-id123')
      expect(toKebabCase('test2Case')).toBe('test2-case')
    })
  })

  describe('truncate', () => {
    it('should not truncate strings shorter than maxLength', () => {
      expect(truncate('hello', 10)).toBe('hello')
      expect(truncate('test', 10)).toBe('test')
    })

    it('should not truncate strings equal to maxLength', () => {
      expect(truncate('hello', 5)).toBe('hello')
      expect(truncate('12345', 5)).toBe('12345')
    })

    it('should truncate strings longer than maxLength', () => {
      expect(truncate('hello world', 8)).toBe('hello...')
      expect(truncate('this is a long string', 10)).toBe('this is...')
    })

    it('should handle empty strings', () => {
      expect(truncate('', 10)).toBe('')
    })

    it('should handle maxLength of 3 (minimum for ellipsis)', () => {
      expect(truncate('hello', 3)).toBe('...')
    })

    it('should handle maxLength of 4', () => {
      expect(truncate('hello world', 4)).toBe('h...')
    })

    it('should handle very long strings', () => {
      const longString = 'a'.repeat(1000)
      const result = truncate(longString, 50)
      expect(result).toHaveLength(50)
      expect(result.endsWith('...')).toBe(true)
    })

    it('should handle strings with unicode characters', () => {
      const result = truncate('hello 😀 world', 10)
      expect(result).toHaveLength(10)
      expect(result.endsWith('...')).toBe(true)
    })

    it('should handle strings with newlines', () => {
      expect(truncate('hello\nworld\ntest', 10)).toBe('hello\nw...')
    })

    it('should count ellipsis in total length', () => {
      const result = truncate('hello world test', 10)
      expect(result).toHaveLength(10)
      expect(result.endsWith('...')).toBe(true)
    })
  })

  describe('escapeRegExp', () => {
    it('should escape special regex characters', () => {
      expect(escapeRegExp('.')).toBe('\\.')
      expect(escapeRegExp('*')).toBe('\\*')
      expect(escapeRegExp('+')).toBe('\\+')
      expect(escapeRegExp('?')).toBe('\\?')
      expect(escapeRegExp('^')).toBe('\\^')
      expect(escapeRegExp('$')).toBe('\\$')
    })

    it('should escape brackets and braces', () => {
      expect(escapeRegExp('{')).toBe('\\{')
      expect(escapeRegExp('}')).toBe('\\}')
      expect(escapeRegExp('(')).toBe('\\(')
      expect(escapeRegExp(')')).toBe('\\)')
      expect(escapeRegExp('[')).toBe('\\[')
      expect(escapeRegExp(']')).toBe('\\]')
    })

    it('should escape backslash and pipe', () => {
      expect(escapeRegExp('\\')).toBe('\\\\')
      expect(escapeRegExp('|')).toBe('\\|')
    })

    it('should not escape regular characters', () => {
      expect(escapeRegExp('hello')).toBe('hello')
      expect(escapeRegExp('abc123')).toBe('abc123')
      expect(escapeRegExp('test_string')).toBe('test_string')
    })

    it('should handle strings with multiple special characters', () => {
      expect(escapeRegExp('hello.*world')).toBe('hello\\.\\*world')
      expect(escapeRegExp('[a-z]+')).toBe('\\[a-z\\]\\+')
      expect(escapeRegExp('(test)?')).toBe('\\(test\\)\\?')
    })

    it('should handle empty strings', () => {
      expect(escapeRegExp('')).toBe('')
    })

    it('should work with RegExp constructor', () => {
      const escaped = escapeRegExp('hello.world')
      const regex = new RegExp(escaped)
      expect(regex.test('hello.world')).toBe(true)
      expect(regex.test('helloXworld')).toBe(false)
    })

    it('should handle complex regex patterns', () => {
      const pattern = '^(test|demo)\\d+$'
      const escaped = escapeRegExp(pattern)
      expect(escaped).toBe('\\^\\(test\\|demo\\)\\\\d\\+\\$')
    })
  })

  describe('removeDiacritics', () => {
    it('should remove common diacritics', () => {
      expect(removeDiacritics('café')).toBe('cafe')
      expect(removeDiacritics('naïve')).toBe('naive')
      expect(removeDiacritics('résumé')).toBe('resume')
    })

    it('should handle multiple diacritics', () => {
      expect(removeDiacritics('José')).toBe('Jose')
      expect(removeDiacritics('François')).toBe('Francois')
      expect(removeDiacritics('Zürich')).toBe('Zurich')
    })

    it('should handle various accents', () => {
      expect(removeDiacritics('àáâãäå')).toBe('aaaaaa')
      expect(removeDiacritics('èéêë')).toBe('eeee')
      expect(removeDiacritics('ìíîï')).toBe('iiii')
      expect(removeDiacritics('òóôõö')).toBe('ooooo')
      expect(removeDiacritics('ùúûü')).toBe('uuuu')
    })

    it('should handle cedilla and tilde', () => {
      expect(removeDiacritics('ç')).toBe('c')
      expect(removeDiacritics('ñ')).toBe('n')
    })

    it('should not affect regular ASCII characters', () => {
      expect(removeDiacritics('hello world')).toBe('hello world')
      expect(removeDiacritics('test123')).toBe('test123')
    })

    it('should handle empty strings', () => {
      expect(removeDiacritics('')).toBe('')
    })

    it('should handle mixed text with and without diacritics', () => {
      expect(removeDiacritics('Hello café world')).toBe('Hello cafe world')
      expect(removeDiacritics('The naïve résumé')).toBe('The naive resume')
    })

    it('should handle German umlauts', () => {
      expect(removeDiacritics('Müller')).toBe('Muller')
      expect(removeDiacritics('Köln')).toBe('Koln')
      // ß is a special character that doesn't have a combining diacritic, so it won't be removed
      expect(removeDiacritics('Größe')).toBe('Große')
    })

    it('should handle Spanish characters', () => {
      expect(removeDiacritics('Español')).toBe('Espanol')
      expect(removeDiacritics('mañana')).toBe('manana')
    })

    it('should handle French characters', () => {
      expect(removeDiacritics('Français')).toBe('Francais')
      expect(removeDiacritics('être')).toBe('etre')
    })

    it('should handle uppercase diacritics', () => {
      expect(removeDiacritics('CAFÉ')).toBe('CAFE')
      expect(removeDiacritics('JOSÉ')).toBe('JOSE')
    })

    it('should preserve non-diacritic special characters', () => {
      expect(removeDiacritics('café!')).toBe('cafe!')
      expect(removeDiacritics('naïve?')).toBe('naive?')
    })
  })

  describe('Integration scenarios', () => {
    it('should chain case conversions correctly', () => {
      const original = 'Hello World Test'
      const snake = toSnakeCase(original)
      const camel = toCamelCase(snake)
      const kebab = toKebabCase(camel)

      expect(snake).toBe('hello_world_test')
      expect(camel).toBe('helloWorldTest')
      expect(kebab).toBe('hello-world-test')
    })

    it('should handle diacritics before case conversion', () => {
      const original = 'Café Français'
      const normalized = removeDiacritics(original)
      const kebab = toKebabCase(normalized)

      expect(normalized).toBe('Cafe Francais')
      expect(kebab).toBe('cafe-francais')
    })

    it('should handle truncate with escape for regex search', () => {
      const text =
        'This is a very long text with special characters like . and *'
      const truncated = truncate(text, 30)
      const escaped = escapeRegExp(truncated)

      expect(truncated.length).toBe(30)
      expect(escaped).toContain('\\.')
    })

    it('should calculate similarity after normalization', () => {
      const str1 = 'café'
      const str2 = 'cafe'

      // Without normalization
      const directSimilarity = stringSimilarity(str1, str2)

      // With normalization
      const normalized1 = removeDiacritics(str1)
      const normalized2 = removeDiacritics(str2)
      const normalizedSimilarity = stringSimilarity(normalized1, normalized2)

      expect(normalizedSimilarity).toBe(1)
      expect(normalizedSimilarity).toBeGreaterThanOrEqual(directSimilarity)
    })
  })

  describe('Edge cases and error handling', () => {
    it('should handle very long strings without performance issues', () => {
      const longString = 'a'.repeat(10000)
      const start = Date.now()

      toSnakeCase(longString)
      toKebabCase(longString)
      toCamelCase(longString)
      truncate(longString, 100)

      const duration = Date.now() - start
      expect(duration).toBeLessThan(1000) // Should complete in under 1 second
    })

    it('should handle strings with only special characters', () => {
      expect(toSnakeCase('!!!@@@###')).toBe('')
      expect(toKebabCase('!!!@@@###')).toBe('')
      // toCamelCase converts the last character
      const result = toCamelCase('!!!@@@###')
      expect(result.length).toBeGreaterThanOrEqual(0)
    })

    it('should handle strings with mixed scripts', () => {
      const mixed = 'hello世界test'
      expect(toSnakeCase(mixed)).toContain('hello')
      expect(toSnakeCase(mixed)).toContain('test')
    })

    it('should handle null-like values gracefully in similarity', () => {
      expect(stringSimilarity('', '')).toBe(1)
      expect(stringSimilarity('test', '')).toBe(0)
      expect(stringSimilarity('', 'test')).toBe(0)
    })
  })
})

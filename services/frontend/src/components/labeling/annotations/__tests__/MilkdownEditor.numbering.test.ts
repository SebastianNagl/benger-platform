/**
 * Unit tests for MilkdownEditor heading auto-numbering logic
 *
 * Issue #1082: Tests position-aware heading numbering and proper reset of
 * sub-levels under new parent headings (German alphanumeric outline system).
 *
 * @jest-environment node
 */

import {
  extractHeadingsFromMarkdown,
  getNextPrefix,
  LEGAL_LEVELS,
} from '@/lib/utils/legalHeadingUtils'

describe('extractHeadingsFromMarkdown', () => {
  it('should extract no headings from empty markdown', () => {
    const result = extractHeadingsFromMarkdown('')
    expect(result).toEqual([])
  })

  it('should extract no headings from markdown without legal prefixes', () => {
    const markdown = `# Regular Heading
## Another Heading
Some text`
    const result = extractHeadingsFromMarkdown(markdown)
    expect(result).toEqual([])
  })

  it('should extract Level 1 heading with A. prefix', () => {
    const markdown = '# A. Anspruchsgrundlage'
    const result = extractHeadingsFromMarkdown(markdown)
    expect(result).toHaveLength(1)
    expect(result[0]).toEqual({
      level: 1,
      prefix: 'A.',
      text: 'Anspruchsgrundlage',
      line: 0,
    })
  })

  it('should extract Level 2 heading with Roman numeral prefix', () => {
    const markdown = '## I. Tatbestand'
    const result = extractHeadingsFromMarkdown(markdown)
    expect(result).toHaveLength(1)
    expect(result[0]).toEqual({
      level: 2,
      prefix: 'I.',
      text: 'Tatbestand',
      line: 0,
    })
  })

  it('should extract Level 3 heading with numeric prefix', () => {
    const markdown = '### 1. Erste Voraussetzung'
    const result = extractHeadingsFromMarkdown(markdown)
    expect(result).toHaveLength(1)
    expect(result[0]).toEqual({
      level: 3,
      prefix: '1.',
      text: 'Erste Voraussetzung',
      line: 0,
    })
  })

  it('should extract Level 4 heading with lowercase letter prefix', () => {
    const markdown = '#### a) Unterabschnitt'
    const result = extractHeadingsFromMarkdown(markdown)
    expect(result).toHaveLength(1)
    expect(result[0]).toEqual({
      level: 4,
      prefix: 'a)',
      text: 'Unterabschnitt',
      line: 0,
    })
  })

  it('should extract Level 5 heading with double letter prefix', () => {
    const markdown = '##### aa) Detail'
    const result = extractHeadingsFromMarkdown(markdown)
    expect(result).toHaveLength(1)
    expect(result[0]).toEqual({
      level: 5,
      prefix: 'aa)',
      text: 'Detail',
      line: 0,
    })
  })

  it('should extract Level 6 heading with parenthesized number prefix', () => {
    const markdown = '###### (1) Punkt'
    const result = extractHeadingsFromMarkdown(markdown)
    expect(result).toHaveLength(1)
    expect(result[0]).toEqual({
      level: 6,
      prefix: '(1)',
      text: 'Punkt',
      line: 0,
    })
  })

  it('should extract multiple headings with correct line numbers', () => {
    const markdown = `# A. First
Some text
## I. Sub first
More text
# B. Second`
    const result = extractHeadingsFromMarkdown(markdown)
    expect(result).toHaveLength(3)
    expect(result[0]).toMatchObject({ level: 1, prefix: 'A.', line: 0 })
    expect(result[1]).toMatchObject({ level: 2, prefix: 'I.', line: 2 })
    expect(result[2]).toMatchObject({ level: 1, prefix: 'B.', line: 4 })
  })

  it('should handle complex hierarchical structure', () => {
    const markdown = `# A. Anspruch entstanden
## I. Vertrag
### 1. Angebot
### 2. Annahme
## II. Wirksamkeit
# B. Nicht Erloschen`
    const result = extractHeadingsFromMarkdown(markdown)
    expect(result).toHaveLength(6)
    expect(result.map(h => ({ level: h.level, prefix: h.prefix }))).toEqual([
      { level: 1, prefix: 'A.' },
      { level: 2, prefix: 'I.' },
      { level: 3, prefix: '1.' },
      { level: 3, prefix: '2.' },
      { level: 2, prefix: 'II.' },
      { level: 1, prefix: 'B.' },
    ])
  })
})

describe('getNextPrefix', () => {
  describe('Level 1 (A., B., C...)', () => {
    it('should return A. when inserting at document start with no existing headings', () => {
      const markdown = ''
      const result = getNextPrefix(1, markdown, 0)
      expect(result).toBe('A.')
    })

    it('should return A. when inserting at document start even with existing headings below', () => {
      const markdown = `# B. Existing
## I. Sub`
      // Inserting at line 0 (before everything)
      const result = getNextPrefix(1, markdown, 0)
      expect(result).toBe('A.')
    })

    it('should return B. when inserting after one Level 1 heading', () => {
      const markdown = `# A. First`
      // Inserting after line 0
      const result = getNextPrefix(1, markdown, 1)
      expect(result).toBe('B.')
    })

    it('should return C. when inserting after two Level 1 headings', () => {
      const markdown = `# A. First
# B. Second`
      // Inserting after line 1
      const result = getNextPrefix(1, markdown, 2)
      expect(result).toBe('C.')
    })

    it('should return B. when inserting between A. and C.', () => {
      const markdown = `# A. First
# C. Third`
      // Inserting at line 1 (after A., before C.)
      const result = getNextPrefix(1, markdown, 1)
      expect(result).toBe('B.')
    })
  })

  describe('Level 2 (I., II., III...) - Reset under new Level 1 parent', () => {
    it('should return I. when no parent exists', () => {
      const markdown = ''
      const result = getNextPrefix(2, markdown, 0)
      expect(result).toBe('I.')
    })

    it('should return I. when inserting under a Level 1 parent with no Level 2 siblings', () => {
      const markdown = `# A. First`
      // Inserting after line 0 (under A.)
      const result = getNextPrefix(2, markdown, 1)
      expect(result).toBe('I.')
    })

    it('should return II. when inserting after one Level 2 heading under same parent', () => {
      const markdown = `# A. First
## I. Sub`
      // Inserting after line 1
      const result = getNextPrefix(2, markdown, 2)
      expect(result).toBe('II.')
    })

    it('should RESET to I. when inserting under a NEW Level 1 parent', () => {
      // This is the key bug fix test!
      const markdown = `# A. First
## I. Under A
## II. Also under A
# B. Second`
      // Inserting after B. (line 3), which is a new Level 1 parent
      const result = getNextPrefix(2, markdown, 4)
      expect(result).toBe('I.')
    })

    it('should return I. when inserting under B. even if A. has multiple Level 2 children', () => {
      const markdown = `# A. First
## I. Under A
## II. Under A
## III. Under A
# B. Second`
      // Inserting after B. (line 4)
      const result = getNextPrefix(2, markdown, 5)
      expect(result).toBe('I.')
    })

    it('should return II. when inserting under B. that already has I.', () => {
      const markdown = `# A. First
## I. Under A
## II. Under A
# B. Second
## I. Under B`
      // Inserting after "I. Under B" (line 4)
      const result = getNextPrefix(2, markdown, 5)
      expect(result).toBe('II.')
    })
  })

  describe('Level 3 (1., 2., 3...) - Reset under new Level 2 parent', () => {
    it('should return 1. when inserting under a Level 2 parent with no Level 3 siblings', () => {
      const markdown = `# A. First
## I. Sub`
      const result = getNextPrefix(3, markdown, 2)
      expect(result).toBe('1.')
    })

    it('should return 2. when inserting after one Level 3 heading', () => {
      const markdown = `# A. First
## I. Sub
### 1. Detail`
      const result = getNextPrefix(3, markdown, 3)
      expect(result).toBe('2.')
    })

    it('should RESET to 1. when inserting under a NEW Level 2 parent', () => {
      const markdown = `# A. First
## I. Sub
### 1. Under I
### 2. Under I
## II. Another`
      // Inserting after II. (line 4)
      const result = getNextPrefix(3, markdown, 5)
      expect(result).toBe('1.')
    })
  })

  describe('Level 4 (a), b), c)...) - Reset under new Level 3 parent', () => {
    it('should return a) when inserting under a Level 3 parent with no siblings', () => {
      const markdown = `# A. First
## I. Sub
### 1. Detail`
      const result = getNextPrefix(4, markdown, 3)
      expect(result).toBe('a)')
    })

    it('should RESET to a) when inserting under a NEW Level 3 parent', () => {
      const markdown = `# A. First
## I. Sub
### 1. Detail
#### a) Under 1
#### b) Under 1
### 2. Another`
      // Inserting after "2. Another" (line 5)
      const result = getNextPrefix(4, markdown, 6)
      expect(result).toBe('a)')
    })
  })

  describe('Level 5 (aa), bb)...) - Reset under new Level 4 parent', () => {
    it('should return aa) when inserting under a Level 4 parent with no siblings', () => {
      const markdown = `# A. First
## I. Sub
### 1. Detail
#### a) Sub-detail`
      const result = getNextPrefix(5, markdown, 4)
      expect(result).toBe('aa)')
    })

    it('should RESET to aa) when inserting under a NEW Level 4 parent', () => {
      const markdown = `# A. First
## I. Sub
### 1. Detail
#### a) First
##### aa) Deep
##### bb) Deep
#### b) Second`
      // Inserting after "b) Second" (line 6)
      const result = getNextPrefix(5, markdown, 7)
      expect(result).toBe('aa)')
    })
  })

  describe('Level 6 ((1), (2)...) - Reset under new Level 5 parent', () => {
    it('should return (1) when inserting under a Level 5 parent with no siblings', () => {
      const markdown = `# A. First
## I. Sub
### 1. Detail
#### a) Sub-detail
##### aa) Deepest`
      const result = getNextPrefix(6, markdown, 5)
      expect(result).toBe('(1)')
    })

    it('should RESET to (1) when inserting under a NEW Level 5 parent', () => {
      const markdown = `# A. First
## I. Sub
### 1. Detail
#### a) First
##### aa) Deep
###### (1) Deepest
###### (2) Deepest
##### bb) Another`
      // Inserting after "bb) Another" (line 7)
      const result = getNextPrefix(6, markdown, 8)
      expect(result).toBe('(1)')
    })
  })

  describe('Edge cases', () => {
    it('should handle insertion at exact line 0', () => {
      const markdown = `# A. Existing`
      const result = getNextPrefix(1, markdown, 0)
      expect(result).toBe('A.')
    })

    it('should handle deeply nested structure with multiple resets', () => {
      const markdown = `# A. First
## I. Under A
### 1. Level 3
#### a) Level 4
## II. Under A second
# B. Second
## I. Under B`
      // Insert Level 3 under "I. Under B" (line 6)
      const result = getNextPrefix(3, markdown, 7)
      expect(result).toBe('1.')
    })

    it('should handle empty lines in markdown', () => {
      const markdown = `# A. First

## I. Sub

### 1. Detail`
      const headings = extractHeadingsFromMarkdown(markdown)
      expect(headings).toHaveLength(3)
      // Lines should account for empty lines
      expect(headings[0].line).toBe(0)
      expect(headings[1].line).toBe(2)
      expect(headings[2].line).toBe(4)
    })

    it('should handle Level 2 insertion at very high line number', () => {
      const markdown = `# A. First
## I. Under A
# B. Second`
      // Insert at a line far after the document
      const result = getNextPrefix(2, markdown, 100)
      expect(result).toBe('I.')
    })

    it('should return last sequence value when sequence is exhausted', () => {
      // Level 2 sequence only has 10 items (I-X)
      // Create markdown with 10 Level 2 headings under same parent
      const markdown = `# A. First
## I. One
## II. Two
## III. Three
## IV. Four
## V. Five
## VI. Six
## VII. Seven
## VIII. Eight
## IX. Nine
## X. Ten`
      // Inserting 11th Level 2 should return X (last in sequence)
      const result = getNextPrefix(2, markdown, 11)
      expect(result).toBe('X.')
    })
  })
})

describe('LEGAL_LEVELS configuration', () => {
  it('should have 6 levels defined', () => {
    expect(LEGAL_LEVELS).toHaveLength(6)
  })

  it('should have correct Level 1 configuration', () => {
    const level1 = LEGAL_LEVELS[0]
    expect(level1.level).toBe(1)
    expect(level1.prefix).toBe('A.')
    expect(level1.sequence).toContain('A')
    expect(level1.sequence).toContain('B')
    expect(level1.format('A')).toBe('A.')
  })

  it('should have correct Level 2 configuration with Roman numerals', () => {
    const level2 = LEGAL_LEVELS[1]
    expect(level2.level).toBe(2)
    expect(level2.prefix).toBe('I.')
    expect(level2.sequence).toEqual(['I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X'])
    expect(level2.format('I')).toBe('I.')
    expect(level2.format('IV')).toBe('IV.')
  })

  it('should have correct Level 3 configuration with numbers', () => {
    const level3 = LEGAL_LEVELS[2]
    expect(level3.level).toBe(3)
    expect(level3.prefix).toBe('1.')
    expect(level3.sequence).toHaveLength(99)
    expect(level3.sequence[0]).toBe('1')
    expect(level3.format('1')).toBe('1.')
  })

  it('should have correct Level 4 configuration with lowercase letters', () => {
    const level4 = LEGAL_LEVELS[3]
    expect(level4.level).toBe(4)
    expect(level4.prefix).toBe('a)')
    expect(level4.sequence).toContain('a')
    expect(level4.sequence).toContain('z')
    expect(level4.format('a')).toBe('a)')
  })

  it('should have correct Level 5 configuration with double letters', () => {
    const level5 = LEGAL_LEVELS[4]
    expect(level5.level).toBe(5)
    expect(level5.prefix).toBe('aa)')
    expect(level5.sequence).toContain('aa')
    expect(level5.sequence).toContain('zz')
    expect(level5.format('aa')).toBe('aa)')
  })

  it('should have correct Level 6 configuration with parenthesized numbers', () => {
    const level6 = LEGAL_LEVELS[5]
    expect(level6.level).toBe(6)
    expect(level6.prefix).toBe('(1)')
    expect(level6.sequence).toHaveLength(99)
    expect(level6.format('1')).toBe('(1)')
    expect(level6.format('99')).toBe('(99)')
  })
})

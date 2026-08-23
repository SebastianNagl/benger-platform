import { defaultIconForKind, projectIcon, projectKindLabelKey } from '../projectKind'

describe('projectKind helpers', () => {
  it('falls back to the kind icon and resolves label keys', () => {
    expect(defaultIconForKind('exam')).toBe('⚖️')
    expect(defaultIconForKind('flashcard_collection')).toBe('🗃️')
    expect(defaultIconForKind(null)).toBe('🗂️')
    expect(projectIcon({ icon: ' ', kind: 'exam' })).toBe('⚖️')
    expect(projectIcon({ icon: '📚', kind: 'exam' })).toBe('📚')
    expect(projectKindLabelKey('exam')).toContain('kind.exam')
    expect(projectKindLabelKey('flashcard_collection')).toContain('kind.deck')
    expect(projectKindLabelKey(undefined)).toContain('kind.generic')
  })
})

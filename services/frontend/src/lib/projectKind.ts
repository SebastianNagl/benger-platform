/**
 * Project type helpers. `kind` is write-once (set in the creation wizard):
 * 'exam' | 'flashcard_collection' | null (generic). The icon falls back to a
 * kind-derived emoji when the user chose none.
 */
export type ProjectKind = 'exam' | 'flashcard_collection' | null | undefined

export function defaultIconForKind(kind: ProjectKind | string | null | undefined): string {
  if (kind === 'exam') return '⚖️'
  if (kind === 'flashcard_collection') return '🗃️'
  return '🗂️'
}

export function projectIcon(project: { icon?: string | null; kind?: string | null }): string {
  return (project.icon && project.icon.trim()) || defaultIconForKind(project.kind)
}

export function projectKindLabelKey(kind: string | null | undefined): string {
  if (kind === 'exam') return 'projects.creation.wizard.step1.kind.exam'
  if (kind === 'flashcard_collection') return 'projects.creation.wizard.step1.kind.deck'
  return 'projects.creation.wizard.step1.kind.generic'
}

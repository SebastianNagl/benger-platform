/**
 * @jest-environment jsdom
 *
 * ProjectMetadataCard — the project-details block. The kind row is a pure
 * read-only display (the editable picker lives in the settings card's
 * ProjectKindSection); student-origin projects additionally show the lock.
 */
import '@testing-library/jest-dom'
import { render, screen } from '@testing-library/react'

import { ProjectMetadataCard } from '../ProjectMetadataCard'

const t = (key: string, fallback?: any) =>
  typeof fallback === 'string' ? fallback : key

const project = (overrides: Record<string, any> = {}) =>
  ({
    id: 'p-1',
    title: 'P',
    kind: null,
    origin: null,
    icon: null,
    created_at: '2026-08-25T00:00:00Z',
    updated_at: null,
    organizations: [],
    ...overrides,
  }) as any

describe('ProjectMetadataCard — kind display', () => {
  it('shows the kind read-only, with no picker buttons', () => {
    render(<ProjectMetadataCard project={project({ kind: 'exam' })} t={t} />)
    expect(screen.getByTestId('project-kind')).toBeInTheDocument()
    expect(screen.queryByTestId('project-kind-exam')).not.toBeInTheDocument()
    expect(screen.queryByRole('radiogroup')).not.toBeInTheDocument()
  })

  it('marks student-origin projects with the locked tooltip', () => {
    render(
      <ProjectMetadataCard project={project({ kind: 'exam', origin: 'student' })} t={t} />,
    )
    expect(
      screen.getByTitle('Der Typ studentischer Projekte kann nicht geändert werden.'),
    ).toBeInTheDocument()
  })

  it('shows no lock on expert projects (editable elsewhere)', () => {
    render(<ProjectMetadataCard project={project({ kind: 'flashcard_collection' })} t={t} />)
    expect(
      screen.queryByTitle('Der Typ studentischer Projekte kann nicht geändert werden.'),
    ).not.toBeInTheDocument()
  })
})

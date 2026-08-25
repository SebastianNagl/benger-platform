/**
 * @jest-environment jsdom
 *
 * ProjectKindSection — the settings card's editable project-type radio
 * (generic maps to null) plus the extended ProjectKindHints slot.
 */
import '@testing-library/jest-dom'
import { fireEvent, render, screen } from '@testing-library/react'

import { registerSlot } from '@/lib/extensions/slots'
import { ProjectKindSection } from '../ProjectKindSection'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, fallback?: any) => (typeof fallback === 'string' ? fallback : key),
  }),
}))

const project = (overrides: Record<string, any> = {}) =>
  ({ id: 'p-1', title: 'P', kind: null, origin: null, ...overrides }) as any

// The section is a collapsed-by-default SubSection with the current type as
// its badge; expand it by clicking the title toggle.
const expand = () => fireEvent.click(screen.getByRole('button', { name: /Projekttyp/ }))

describe('ProjectKindSection', () => {
  it('shows the picked type as the collapsed badge and the radio when expanded', () => {
    const onKindChange = jest.fn()
    render(<ProjectKindSection project={project({ kind: 'exam' })} onKindChange={onKindChange} />)
    expect(screen.getByText('Klausur')).toBeInTheDocument() // badge
    expect(screen.queryByTestId('project-kind-exam')).not.toBeInTheDocument()
    expand()
    expect(screen.getByTestId('project-kind-exam')).toHaveAttribute('aria-checked', 'true')
    fireEvent.click(screen.getByTestId('project-kind-flashcard_collection'))
    expect(onKindChange).toHaveBeenCalledWith('flashcard_collection')
    fireEvent.click(screen.getByTestId('project-kind-generic'))
    expect(onKindChange).toHaveBeenCalledWith(null)
    // Re-clicking the selected option is a no-op.
    onKindChange.mockClear()
    fireEvent.click(screen.getByTestId('project-kind-exam'))
    expect(onKindChange).not.toHaveBeenCalled()
  })

  it('renders the ProjectKindHints slot with the project (extended warnings)', () => {
    registerSlot('ProjectKindHints', ({ project: p }: any) => (
      <div data-testid="kind-hints">{p.id}</div>
    ))
    render(<ProjectKindSection project={project({ id: 'p-77' })} onKindChange={jest.fn()} />)
    expand()
    expect(screen.getByTestId('kind-hints')).toHaveTextContent('p-77')
  })
})

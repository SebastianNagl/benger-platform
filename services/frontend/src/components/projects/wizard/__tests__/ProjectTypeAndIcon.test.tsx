/**
 * @jest-environment jsdom
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { IconPickerModal, ProjectTypeSelector } from '../ProjectTypeAndIcon'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({ t: (k: string, d?: any) => (typeof d === 'string' ? d : k) }),
}))
jest.mock('@/components/shared/Dialog', () => ({
  Dialog: ({ isOpen, title, children }: any) =>
    isOpen ? (
      <div role="dialog">
        <h3>{title}</h3>
        {children}
      </div>
    ) : null,
}))

describe('ProjectTypeSelector', () => {
  it('renders the three options in one row and selects a type', () => {
    const onChange = jest.fn()
    const { container } = render(
      <ProjectTypeSelector projectKind="generic" onChange={onChange} />
    )
    expect(container.querySelector('[role="radiogroup"]')).toHaveClass('grid-cols-3')
    expect(screen.getByTestId('project-kind-generic')).toHaveAttribute('aria-checked', 'true')
    fireEvent.click(screen.getByTestId('project-kind-exam'))
    expect(onChange).toHaveBeenCalledWith({ projectKind: 'exam' })
    expect(screen.getByText(/unter „Einstellungen“ geändert/)).toBeInTheDocument()
  })
})

describe('IconPickerModal', () => {
  it('picks a curated emoji and saves; free text works; empty falls back to the kind default', () => {
    const onPick = jest.fn()
    const onClose = jest.fn()
    const { rerender } = render(
      <IconPickerModal isOpen icon="" projectKind="exam" onPick={onPick} onClose={onClose} />
    )
    fireEvent.click(screen.getByTestId('project-icon-📚'))
    fireEvent.click(screen.getByTestId('project-icon-save'))
    expect(onPick).toHaveBeenCalledWith('📚')
    expect(onClose).toHaveBeenCalled()

    rerender(
      <IconPickerModal isOpen icon="" projectKind="flashcard_collection" onPick={onPick} onClose={onClose} />
    )
    fireEvent.change(screen.getByTestId('project-icon-input'), { target: { value: ' ' } })
    fireEvent.click(screen.getByTestId('project-icon-save'))
    expect(onPick).toHaveBeenLastCalledWith('🗃️')
  })
})

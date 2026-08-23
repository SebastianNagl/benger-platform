/**
 * @jest-environment jsdom
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { ProjectTypeAndIcon } from '../ProjectTypeAndIcon'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({ t: (k: string, d?: any) => (typeof d === 'string' ? d : k) }),
}))

describe('ProjectTypeAndIcon', () => {
  it('selects a project type and toggles an icon choice', () => {
    const onChange = jest.fn()
    render(<ProjectTypeAndIcon projectKind="generic" icon="" onChange={onChange} />)
    expect(screen.getByTestId('project-kind-generic')).toHaveAttribute('aria-checked', 'true')
    fireEvent.click(screen.getByTestId('project-kind-exam'))
    expect(onChange).toHaveBeenCalledWith({ projectKind: 'exam' })
    fireEvent.click(screen.getByTestId('project-icon-📚'))
    expect(onChange).toHaveBeenCalledWith({ icon: '📚' })
    fireEvent.change(screen.getByTestId('project-icon-input'), { target: { value: '🦉' } })
    expect(onChange).toHaveBeenCalledWith({ icon: '🦉' })
    expect(screen.getByText(/kann danach nicht geändert/)).toBeInTheDocument()
  })

  it('clicking the selected icon clears it; placeholder shows the kind default', () => {
    const onChange = jest.fn()
    render(<ProjectTypeAndIcon projectKind="flashcard_collection" icon="📚" onChange={onChange} />)
    fireEvent.click(screen.getByTestId('project-icon-📚'))
    expect(onChange).toHaveBeenCalledWith({ icon: '' })
    expect(screen.getByTestId('project-icon-input')).toHaveAttribute('placeholder', '🗃️')
  })
})

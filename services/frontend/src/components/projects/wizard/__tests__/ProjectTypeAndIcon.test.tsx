/**
 * @jest-environment jsdom
 */
import {
  _resetWizardProjectTypes,
  registerWizardProjectType,
} from '@/lib/extensions/wizardTemplates'
import { fireEvent, render, screen } from '@testing-library/react'
import { IconPickerModal, ProjectTypeSelector } from '../ProjectTypeAndIcon'

jest.mock('@/contexts/I18nContext', () =>
  require('@/test-utils/i18nMock').i18nMock('de'),
)
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
      <ProjectTypeSelector projectKind="generic" onChange={onChange} />,
    )
    expect(container.querySelector('[role="radiogroup"]')).toHaveClass(
      'grid-cols-3',
    )
    expect(screen.getByTestId('project-kind-generic')).toHaveAttribute(
      'aria-checked',
      'true',
    )
    fireEvent.click(screen.getByTestId('project-kind-exam'))
    expect(onChange).toHaveBeenCalledWith({
      projectKind: 'exam',
      projectTypeId: 'exam',
    })
    expect(
      screen.getByText(/unter „Einstellungen“ geändert/),
    ).toBeInTheDocument()
  })

  describe('registered project types', () => {
    beforeEach(() => {
      _resetWizardProjectTypes()
      registerWizardProjectType({
        id: 'fr-dissertation',
        kind: 'exam',
        icon: '📝',
        nameKey: 'x.dissertation',
        descriptionKey: 'x.dissertationDescription',
        templateId: 'fr-dissertation',
        jurisdictions: ['FR'],
      })
      registerWizardProjectType({
        id: 'everywhere',
        kind: 'generic',
        icon: '🧪',
        nameKey: 'x.everywhere',
        descriptionKey: 'x.everywhereDescription',
      })
    })
    afterEach(() => _resetWizardProjectTypes())

    it('keeps the three base kinds and adds only the types offered here', () => {
      render(<ProjectTypeSelector projectKind="generic" onChange={jest.fn()} />)
      for (const id of [
        'generic',
        'exam',
        'flashcard_collection',
        'everywhere',
      ]) {
        expect(screen.getByTestId(`project-kind-${id}`)).toBeInTheDocument()
      }
      // German by default: the French type is not offered.
      expect(screen.queryByTestId('project-kind-fr-dissertation')).toBeNull()
    })

    it('shows the types of other jurisdictions behind a toggle', () => {
      const onChange = jest.fn()
      render(<ProjectTypeSelector projectKind="generic" onChange={onChange} />)
      const toggle = screen.getByTestId('project-kind-show-all')
      expect(toggle).toHaveAttribute('aria-expanded', 'false')
      expect(toggle).toHaveTextContent('Alle Projekttypen anzeigen (+1)')

      fireEvent.click(toggle)
      expect(toggle).toHaveAttribute('aria-expanded', 'true')
      expect(toggle).toHaveTextContent('Weniger Projekttypen anzeigen')
      fireEvent.click(screen.getByTestId('project-kind-fr-dissertation'))
      expect(onChange).toHaveBeenCalledWith({
        projectKind: 'exam',
        projectTypeId: 'fr-dissertation',
      })

      fireEvent.click(toggle)
      expect(screen.queryByTestId('project-kind-fr-dissertation')).toBeNull()
    })

    it('opens expanded when the selected type is of another jurisdiction', () => {
      render(
        <ProjectTypeSelector
          projectKind="exam"
          projectTypeId="fr-dissertation"
          onChange={jest.fn()}
        />,
      )
      expect(screen.getByTestId('project-kind-show-all')).toHaveAttribute(
        'aria-expanded',
        'true',
      )
      expect(
        screen.getByTestId('project-kind-fr-dissertation'),
      ).toHaveAttribute('aria-checked', 'true')
    })

    it('keeps a selected type of another jurisdiction visible when collapsed', () => {
      const { rerender } = render(
        <ProjectTypeSelector
          projectKind="exam"
          projectTypeId="fr-dissertation"
          jurisdictions={['FR']}
          onChange={jest.fn()}
        />,
      )
      // Offered for FR: no toggle; switching the target org to DE keeps
      // the selection on screen.
      expect(screen.queryByTestId('project-kind-show-all')).toBeNull()
      rerender(
        <ProjectTypeSelector
          projectKind="exam"
          projectTypeId="fr-dissertation"
          jurisdictions={['DE']}
          onChange={jest.fn()}
        />,
      )
      expect(screen.getByTestId('project-kind-show-all')).toHaveAttribute(
        'aria-expanded',
        'false',
      )
      expect(
        screen.getByTestId('project-kind-fr-dissertation'),
      ).toHaveAttribute('aria-checked', 'true')
    })

    it('offers a jurisdiction type and picks it as its base kind', () => {
      const onChange = jest.fn()
      render(
        <ProjectTypeSelector
          projectKind="exam"
          projectTypeId="fr-dissertation"
          jurisdictions={['FR']}
          onChange={onChange}
        />,
      )
      const option = screen.getByTestId('project-kind-fr-dissertation')
      expect(option).toHaveAttribute('aria-checked', 'true')
      // The base exam option is not the selected one.
      expect(screen.getByTestId('project-kind-exam')).toHaveAttribute(
        'aria-checked',
        'false',
      )
      fireEvent.click(screen.getByTestId('project-kind-everywhere'))
      expect(onChange).toHaveBeenCalledWith({
        projectKind: 'generic',
        projectTypeId: 'everywhere',
      })
    })
  })
})

describe('IconPickerModal', () => {
  it('picks a curated emoji and saves; free text works; empty falls back to the kind default', () => {
    const onPick = jest.fn()
    const onClose = jest.fn()
    const { rerender } = render(
      <IconPickerModal
        isOpen
        icon=""
        projectKind="exam"
        onPick={onPick}
        onClose={onClose}
      />,
    )
    fireEvent.click(screen.getByTestId('project-icon-📚'))
    fireEvent.click(screen.getByTestId('project-icon-save'))
    expect(onPick).toHaveBeenCalledWith('📚')
    expect(onClose).toHaveBeenCalled()

    rerender(
      <IconPickerModal
        isOpen
        icon=""
        projectKind="flashcard_collection"
        onPick={onPick}
        onClose={onClose}
      />,
    )
    fireEvent.change(screen.getByTestId('project-icon-input'), {
      target: { value: ' ' },
    })
    fireEvent.click(screen.getByTestId('project-icon-save'))
    expect(onPick).toHaveBeenLastCalledWith('🗃️')
  })
})

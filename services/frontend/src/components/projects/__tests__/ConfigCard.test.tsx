/**
 * Tests for ConfigCard — the top-level collapsible card on project detail.
 *
 * Tests the contract, not the markup: edit/save/cancel lifecycle, the
 * "single Speichern flushes everything" model, button visibility rules,
 * disabled-while-saving, and canEdit gating. The actual layout is incidental.
 *
 * @jest-environment jsdom
 */

import { ConfigCard } from '@/components/projects/ConfigCard'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

jest.mock('@/components/shared/Button', () => ({
  Button: ({ children, onClick, disabled, ...props }: any) => (
    <button onClick={onClick} disabled={disabled} {...props}>
      {children}
    </button>
  ),
}))

describe('ConfigCard', () => {
  describe('expand / collapse', () => {
    it('renders expanded by default', () => {
      render(
        <ConfigCard title="Annotation">
          <div data-testid="child">inner</div>
        </ConfigCard>
      )
      expect(screen.getByTestId('child')).toBeInTheDocument()
    })

    it('respects defaultExpanded={false}', () => {
      render(
        <ConfigCard title="Annotation" defaultExpanded={false}>
          <div data-testid="child">inner</div>
        </ConfigCard>
      )
      expect(screen.queryByTestId('child')).not.toBeInTheDocument()
    })

    it('toggles via header click', async () => {
      const user = userEvent.setup()
      render(
        <ConfigCard title="Annotation" defaultExpanded={false}>
          <div data-testid="child">inner</div>
        </ConfigCard>
      )
      await user.click(screen.getByRole('button', { name: /Annotation/i }))
      expect(screen.getByTestId('child')).toBeInTheDocument()
      await user.click(screen.getByRole('button', { name: /Annotation/i }))
      expect(screen.queryByTestId('child')).not.toBeInTheDocument()
    })

    it('renders the badge next to the title', () => {
      render(
        <ConfigCard title="Evaluation" badge="3 methods">
          <div>inner</div>
        </ConfigCard>
      )
      expect(screen.getByText('3 methods')).toBeInTheDocument()
    })
  })

  describe('edit / save / cancel lifecycle', () => {
    it('shows Bearbeiten when not editing and lifecycle is wired', () => {
      const onEdit = jest.fn()
      render(
        <ConfigCard
          title="Annotation"
          editing={false}
          onEdit={onEdit}
          onSave={jest.fn()}
          onCancel={jest.fn()}
          canEdit
        >
          <div>inner</div>
        </ConfigCard>
      )
      expect(screen.getByRole('button', { name: 'Bearbeiten' })).toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Speichern' })).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Abbrechen' })).not.toBeInTheDocument()
    })

    it('shows Speichern + Abbrechen when editing', () => {
      render(
        <ConfigCard
          title="Annotation"
          editing
          onEdit={jest.fn()}
          onSave={jest.fn()}
          onCancel={jest.fn()}
          canEdit
        >
          <div>inner</div>
        </ConfigCard>
      )
      expect(screen.getByRole('button', { name: 'Speichern' })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Abbrechen' })).toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Bearbeiten' })).not.toBeInTheDocument()
    })

    it('Bearbeiten click triggers onEdit', async () => {
      const onEdit = jest.fn()
      const user = userEvent.setup()
      render(
        <ConfigCard
          title="Annotation"
          editing={false}
          onEdit={onEdit}
          onSave={jest.fn()}
          onCancel={jest.fn()}
          canEdit
        >
          <div>inner</div>
        </ConfigCard>
      )
      await user.click(screen.getByRole('button', { name: 'Bearbeiten' }))
      expect(onEdit).toHaveBeenCalledTimes(1)
    })

    it('Speichern click triggers onSave', async () => {
      const onSave = jest.fn().mockResolvedValue(undefined)
      const user = userEvent.setup()
      render(
        <ConfigCard
          title="Annotation"
          editing
          onEdit={jest.fn()}
          onSave={onSave}
          onCancel={jest.fn()}
          canEdit
        >
          <div>inner</div>
        </ConfigCard>
      )
      await user.click(screen.getByRole('button', { name: 'Speichern' }))
      expect(onSave).toHaveBeenCalledTimes(1)
    })

    it('Abbrechen click triggers onCancel', async () => {
      const onCancel = jest.fn()
      const user = userEvent.setup()
      render(
        <ConfigCard
          title="Annotation"
          editing
          onEdit={jest.fn()}
          onSave={jest.fn()}
          onCancel={onCancel}
          canEdit
        >
          <div>inner</div>
        </ConfigCard>
      )
      await user.click(screen.getByRole('button', { name: 'Abbrechen' }))
      expect(onCancel).toHaveBeenCalledTimes(1)
    })

    it('shows "Speichert…" and disables both buttons when saving', () => {
      render(
        <ConfigCard
          title="Annotation"
          editing
          onEdit={jest.fn()}
          onSave={jest.fn()}
          onCancel={jest.fn()}
          saving
          canEdit
        >
          <div>inner</div>
        </ConfigCard>
      )
      expect(screen.getByRole('button', { name: 'Speichert…' })).toBeDisabled()
      expect(screen.getByRole('button', { name: 'Abbrechen' })).toBeDisabled()
    })
  })

  describe('canEdit gating', () => {
    it('hides edit controls when canEdit is false', () => {
      render(
        <ConfigCard
          title="Annotation"
          editing={false}
          onEdit={jest.fn()}
          onSave={jest.fn()}
          onCancel={jest.fn()}
          canEdit={false}
        >
          <div>inner</div>
        </ConfigCard>
      )
      expect(screen.queryByRole('button', { name: 'Bearbeiten' })).not.toBeInTheDocument()
    })

    it('hides edit controls when no onEdit/onSave is wired (read-only mode)', () => {
      render(
        <ConfigCard title="Annotation">
          <div>inner</div>
        </ConfigCard>
      )
      expect(screen.queryByRole('button', { name: 'Bearbeiten' })).not.toBeInTheDocument()
    })

    it('hides edit controls while collapsed even if lifecycle is wired', async () => {
      const user = userEvent.setup()
      render(
        <ConfigCard
          title="Annotation"
          defaultExpanded={false}
          editing={false}
          onEdit={jest.fn()}
          onSave={jest.fn()}
          onCancel={jest.fn()}
          canEdit
        >
          <div>inner</div>
        </ConfigCard>
      )
      // Collapsed: no Bearbeiten visible
      expect(screen.queryByRole('button', { name: 'Bearbeiten' })).not.toBeInTheDocument()
      // Expand → it appears
      await user.click(screen.getByRole('button', { name: /Annotation/i }))
      expect(screen.getByRole('button', { name: 'Bearbeiten' })).toBeInTheDocument()
    })
  })
})

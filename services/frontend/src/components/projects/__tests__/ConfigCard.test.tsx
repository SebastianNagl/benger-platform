/**
 * Tests for ConfigCard — the top-level collapsible card on project detail.
 *
 * Tests the contract, not the markup: expand/collapse, badge, and the
 * dirty/saving status chip of the auto-save model (there is no edit mode
 * and no manual save button). The actual layout is incidental.
 *
 * @jest-environment jsdom
 */

import { ConfigCard } from '@/components/projects/ConfigCard'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

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

  describe('auto-save status chip', () => {
    it('shows no status chip when neither dirty nor saving', () => {
      render(
        <ConfigCard title="Annotation">
          <div>inner</div>
        </ConfigCard>
      )
      expect(screen.queryByRole('status')).not.toBeInTheDocument()
    })

    it('shows the unsaved-changes chip while dirty', () => {
      render(
        <ConfigCard title="Annotation" dirty>
          <div>inner</div>
        </ConfigCard>
      )
      expect(screen.getByRole('status')).toHaveTextContent(
        'Ungespeicherte Änderungen'
      )
    })

    it('shows "Speichert…" while a flush is in flight', () => {
      render(
        <ConfigCard title="Annotation" dirty saving>
          <div>inner</div>
        </ConfigCard>
      )
      expect(screen.getByRole('status')).toHaveTextContent('Speichert…')
    })

    it('shows the status chip even while collapsed', () => {
      render(
        <ConfigCard title="Annotation" defaultExpanded={false} dirty>
          <div>inner</div>
        </ConfigCard>
      )
      expect(screen.getByRole('status')).toHaveTextContent(
        'Ungespeicherte Änderungen'
      )
    })

    it('renders no edit or save buttons (auto-save has no manual controls)', () => {
      render(
        <ConfigCard title="Annotation" dirty saving>
          <div>inner</div>
        </ConfigCard>
      )
      expect(
        screen.queryByRole('button', { name: 'Bearbeiten' })
      ).not.toBeInTheDocument()
      expect(
        screen.queryByRole('button', { name: /Speicher/ })
      ).not.toBeInTheDocument()
      expect(
        screen.queryByRole('button', { name: 'Abbrechen' })
      ).not.toBeInTheDocument()
    })
  })
})

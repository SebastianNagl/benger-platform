/**
 * Tests for SubSection — collapsible section nested inside a ConfigCard.
 *
 * @jest-environment jsdom
 */

import { SubSection } from '@/components/projects/SubSection'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

describe('SubSection', () => {
  it('renders collapsed by default — children are not in the DOM', () => {
    render(
      <SubSection title="Settings">
        <div data-testid="inner">x</div>
      </SubSection>
    )
    expect(screen.queryByTestId('inner')).not.toBeInTheDocument()
    expect(screen.getByText('Settings')).toBeInTheDocument()
  })

  it('respects defaultExpanded={true}', () => {
    render(
      <SubSection title="Settings" defaultExpanded>
        <div data-testid="inner">x</div>
      </SubSection>
    )
    expect(screen.getByTestId('inner')).toBeInTheDocument()
  })

  it('toggles via header click', async () => {
    const user = userEvent.setup()
    render(
      <SubSection title="Settings">
        <div data-testid="inner">x</div>
      </SubSection>
    )
    await user.click(screen.getByRole('button', { name: /Settings/i }))
    expect(screen.getByTestId('inner')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Settings/i }))
    expect(screen.queryByTestId('inner')).not.toBeInTheDocument()
  })

  it('renders the badge next to the title', () => {
    render(
      <SubSection title="Methods" badge="3 configured">
        <div>x</div>
      </SubSection>
    )
    expect(screen.getByText('3 configured')).toBeInTheDocument()
  })

  it('hides actions slot when collapsed and shows it when expanded', async () => {
    const user = userEvent.setup()
    render(
      <SubSection
        title="Methods"
        actions={<span data-testid="action-slot">edit</span>}
      >
        <div>x</div>
      </SubSection>
    )
    expect(screen.queryByTestId('action-slot')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Methods/i }))
    expect(screen.getByTestId('action-slot')).toBeInTheDocument()
  })
})

/**
 * @jest-environment jsdom
 */

import { registerSlot } from '@/lib/extensions/slots'
import '@testing-library/jest-dom'
import { render, screen } from '@testing-library/react'
import ProjectLivePage from '../page'

jest.mock('next/navigation', () => ({
  useParams: () => ({ id: 'p1' }),
}))

describe('ProjectLivePage (slot stub)', () => {
  it('says the page is unavailable without the extended slot', () => {
    render(<ProjectLivePage />)
    expect(
      screen.getByText(/not available in the community edition/),
    ).toBeInTheDocument()
  })

  it('renders the registered slot with the project id', () => {
    registerSlot('ProjectLivePage', ({ projectId }: { projectId: string }) => (
      <div data-testid="live-slot">{projectId}</div>
    ))
    render(<ProjectLivePage />)
    expect(screen.getByTestId('live-slot')).toHaveTextContent('p1')
  })
})

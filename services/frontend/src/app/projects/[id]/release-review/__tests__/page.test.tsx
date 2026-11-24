/**
 * @jest-environment jsdom
 */

import { registerSlot } from '@/lib/extensions/slots'
import '@testing-library/jest-dom'
import { render, screen } from '@testing-library/react'
import ProjectReleaseReviewPage from '../page'

jest.mock('next/navigation', () => ({
  useParams: () => ({ id: 'p1' }),
}))

describe('ProjectReleaseReviewPage (slot stub)', () => {
  it('says the review needs the extended edition without the extended slot', () => {
    render(<ProjectReleaseReviewPage />)
    expect(
      screen.getByText('project.releaseReview.extendedRequired'),
    ).toBeInTheDocument()
  })

  it('renders the registered slot with the project id', () => {
    registerSlot(
      'ProjectReleaseReviewPage',
      ({ projectId }: { projectId: string }) => (
        <div data-testid="release-review-slot">{projectId}</div>
      ),
    )
    render(<ProjectReleaseReviewPage />)
    expect(screen.getByTestId('release-review-slot')).toHaveTextContent('p1')
  })
})

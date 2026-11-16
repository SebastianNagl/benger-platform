/**
 * @jest-environment jsdom
 */

import { registerSlot } from '@/lib/extensions/slots'
import '@testing-library/jest-dom'
import { render, screen } from '@testing-library/react'
import ProjectRubricReviewPage from '../page'

jest.mock('next/navigation', () => ({
  useParams: () => ({ id: 'p1' }),
}))

describe('ProjectRubricReviewPage (slot stub)', () => {
  it('says the check step needs the extended edition without the extended slot', () => {
    render(<ProjectRubricReviewPage />)
    expect(
      screen.getByText('project.rubricReview.extendedRequired'),
    ).toBeInTheDocument()
  })

  it('renders the registered slot with the project id', () => {
    registerSlot(
      'ProjectRubricReviewPage',
      ({ projectId }: { projectId: string }) => (
        <div data-testid="rubric-review-slot">{projectId}</div>
      ),
    )
    render(<ProjectRubricReviewPage />)
    expect(screen.getByTestId('rubric-review-slot')).toHaveTextContent('p1')
  })
})

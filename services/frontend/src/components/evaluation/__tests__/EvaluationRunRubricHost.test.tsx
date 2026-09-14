/**
 * The run page's extension slot: children render unchanged until an edition
 * registers a host, which then wraps them and receives the project id.
 */
import { registerSlot } from '@/lib/extensions/slots'
import { act, render, screen } from '@testing-library/react'
import {
  EVALUATION_RUN_RUBRIC_HOST_SLOT,
  EvaluationRunRubricHost,
} from '../EvaluationRunRubricHost'

function Host({
  projectId,
  children,
}: {
  projectId: string
  children: React.ReactNode
}) {
  return (
    <section data-testid="host" data-project-id={projectId}>
      {children}
    </section>
  )
}

describe('EvaluationRunRubricHost', () => {
  it('uses the contract slot name', () => {
    expect(EVALUATION_RUN_RUBRIC_HOST_SLOT).toBe('EvaluationRunRubricHost')
  })

  it('renders its children unchanged without a registration', () => {
    const { container } = render(
      <EvaluationRunRubricHost projectId="p1">
        <p>Inhalt</p>
      </EvaluationRunRubricHost>,
    )
    expect(container.innerHTML).toBe('<p>Inhalt</p>')
  })

  // Registration is module-global: from here on a host is registered.
  it('picks up a host registered after mount', () => {
    render(
      <EvaluationRunRubricHost projectId="p1">
        <p>Inhalt</p>
      </EvaluationRunRubricHost>,
    )
    expect(screen.queryByTestId('host')).not.toBeInTheDocument()
    act(() => registerSlot(EVALUATION_RUN_RUBRIC_HOST_SLOT, Host))
    expect(screen.getByTestId('host')).toHaveAttribute('data-project-id', 'p1')
  })

  it('wraps its children in the registered host with the project id', () => {
    render(
      <EvaluationRunRubricHost projectId="project-42">
        <p>Inhalt</p>
      </EvaluationRunRubricHost>,
    )
    const host = screen.getByTestId('host')
    expect(host).toHaveAttribute('data-project-id', 'project-42')
    expect(host).toHaveTextContent('Inhalt')
  })
})

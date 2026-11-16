/**
 * WizardStepIndicator: one dot per step, connectors between neighbours, and
 * a dot click selects its step. The phone-width layout (rubric e2e D02) is
 * measured in a browser by e2e/mobile/phone-width-layout.spec.ts.
 *
 * @jest-environment jsdom
 */

import '@testing-library/jest-dom'
import { render, screen } from '@testing-library/react'
import { WizardStepIndicator } from '../WizardStepIndicator'

const steps = Array.from({ length: 10 }, (_, i) => ({
  id: `step-${i + 1}`,
  name: `Step ${i + 1}`,
  description: `About step ${i + 1}`,
})) as any

describe('WizardStepIndicator', () => {
  it('renders one dot per step and a connector between neighbours', () => {
    render(
      <WizardStepIndicator
        steps={steps}
        currentStepIndex={2}
        onStepClick={jest.fn()}
      />,
    )
    expect(screen.getAllByTestId(/^wizard-step-dot-/)).toHaveLength(10)
    expect(screen.getAllByTestId(/^wizard-step-connector-/)).toHaveLength(9)
    expect(screen.getByText('Step 3')).toBeInTheDocument()
  })

  it('goes to a step when its dot is clicked', () => {
    const onStepClick = jest.fn()
    render(
      <WizardStepIndicator
        steps={steps}
        currentStepIndex={0}
        onStepClick={onStepClick}
      />,
    )
    screen.getByTestId('wizard-step-dot-4').click()
    expect(onStepClick).toHaveBeenCalledWith(3)
  })
})

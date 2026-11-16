/**
 * WizardStepIndicator at phone width (rubric e2e D02).
 *
 * Fixed 32 px connectors between up to ten 32 px dots made the wizard 427-535
 * px wide on a 390 px phone, with dot 1 off screen. The dots keep their size
 * and the connectors are what shrinks. jsdom has no layout, so this pins the
 * classes that give that behaviour; the width itself was checked in Chromium
 * at 390 px.
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

  it('lets the connectors shrink while the dots keep their size', () => {
    render(
      <WizardStepIndicator
        steps={steps}
        currentStepIndex={0}
        onStepClick={jest.fn()}
      />,
    )
    for (const dot of screen.getAllByTestId(/^wizard-step-dot-/)) {
      expect(dot).toHaveClass('shrink-0', 'h-7', 'w-7', 'sm:h-8', 'sm:w-8')
    }
    for (const connector of screen.getAllByTestId(/^wizard-step-connector-/)) {
      expect(connector).toHaveClass('flex-1', 'min-w-0.5', 'max-w-12')
      expect(connector).not.toHaveClass('w-8')
    }
    // Dots and connectors share one flex row, so the row can shrink them.
    const row = screen.getByTestId('wizard-step-dot-1').parentElement!
    expect(row).toHaveClass('flex', 'w-full')
    expect(row).toContainElement(screen.getByTestId('wizard-step-connector-1'))
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

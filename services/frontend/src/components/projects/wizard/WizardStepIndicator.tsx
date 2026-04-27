'use client'

import { cn } from '@/lib/utils'
import { CheckIcon } from '@heroicons/react/24/outline'
import { WizardStepDef } from './types'

interface WizardStepIndicatorProps {
  steps: WizardStepDef[]
  currentStepIndex: number
  onStepClick: (index: number) => void
}

export function WizardStepIndicator({
  steps,
  currentStepIndex,
  onStepClick,
}: WizardStepIndicatorProps) {
  const currentStep = steps[currentStepIndex]

  return (
    <div className="mb-8">
      {/* Dots row */}
      <div className="flex items-center justify-center gap-0">
        {steps.map((step, index) => {
          const isActive = index === currentStepIndex
          const isCompleted = index < currentStepIndex
          const isClickable = true

          return (
            <div key={step.id} className="flex items-center">
              <button
                type="button"
                onClick={() => isClickable && onStepClick(index)}
                disabled={!isClickable}
                title={step.name}
                className={cn(
                  'flex h-8 w-8 items-center justify-center rounded-full border-2 text-sm font-medium transition-colors cursor-pointer',
                  isActive && 'border-emerald-600 bg-emerald-600 text-white',
                  isCompleted &&
                    'border-emerald-600 bg-emerald-600 text-white hover:bg-emerald-700 hover:border-emerald-700',
                  !isActive &&
                    !isCompleted &&
                    'border-zinc-300 text-zinc-500 hover:border-zinc-400 hover:text-zinc-700 dark:border-zinc-600 dark:text-zinc-400 dark:hover:border-zinc-500'
                )}
                data-testid={`wizard-step-dot-${index + 1}`}
              >
                {isCompleted ? (
                  <CheckIcon className="h-4 w-4" />
                ) : (
                  index + 1
                )}
              </button>
              {index < steps.length - 1 && (
                <div
                  className={cn(
                    'mx-1 h-0.5 w-8 sm:w-12',
                    isCompleted
                      ? 'bg-emerald-600'
                      : 'bg-zinc-300 dark:bg-zinc-700'
                  )}
                />
              )}
            </div>
          )
        })}
      </div>

      {/* Current step label */}
      {currentStep && (
        <div className="mt-4 text-center">
          <p className="text-lg font-semibold text-zinc-900 dark:text-white">
            {currentStep.name}
          </p>
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            {currentStep.description}
          </p>
        </div>
      )}
    </div>
  )
}

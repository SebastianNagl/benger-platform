/**
 * fn3 function coverage for EvaluationControlModal.tsx
 * Targets: handleSubmit with onRunWithMode callback, handleSubmit direct API mode error paths
 */

import React from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    locale: 'en',
    t: (key: string) => key,
    changeLocale: jest.fn(),
    isReady: true,
  }),
}))

const mockAddToast = jest.fn()
jest.mock('@/components/shared/Toast', () => ({
  useToast: () => ({ addToast: mockAddToast }),
}))

jest.mock('@/lib/api/client', () => ({
  apiClient: {
    evaluations: {
      runEvaluation: jest.fn(),
    },
  },
}))

// Mock HeadlessUI
jest.mock('@headlessui/react', () => ({
  Dialog: ({ children, ...props }: any) =>
    props.open !== false ? (
      <div data-testid="dialog" role="dialog">{typeof children === 'function' ? children({}) : children}</div>
    ) : null,
  Transition: {
    Root: ({ children, show }: any) => (show ? <div>{children}</div> : null),
    Child: ({ children }: any) => <div>{children}</div>,
  },
}))

// Need to add Dialog.Panel, Dialog.Title
const HeadlessUI = require('@headlessui/react')
HeadlessUI.Dialog.Panel = ({ children }: any) => <div>{children}</div>
HeadlessUI.Dialog.Title = ({ children, ...props }: any) => <h3 {...props}>{children}</h3>

import { EvaluationControlModal } from '../EvaluationControlModal'

describe('EvaluationControlModal fn3', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('calls onRunWithMode with false for missing mode', async () => {
    const onRunWithMode = jest.fn().mockResolvedValue(undefined)
    const onClose = jest.fn()
    const onSuccess = jest.fn()

    render(
      <EvaluationControlModal
        isOpen={true}
        onClose={onClose}
        onSuccess={onSuccess}
        onRunWithMode={onRunWithMode}
        configCount={3}
      />
    )

    // Default mode is 'missing', so forceRerun should be false
    const startBtn = screen.getByText('evaluation.controlModal.startEvaluation')
    fireEvent.click(startBtn)

    await waitFor(() => {
      expect(onRunWithMode).toHaveBeenCalledWith(false)
    })
    expect(onSuccess).toHaveBeenCalled()
    expect(onClose).toHaveBeenCalled()
  })

  it('calls onRunWithMode with true when all mode selected', async () => {
    const onRunWithMode = jest.fn().mockResolvedValue(undefined)
    const onClose = jest.fn()

    render(
      <EvaluationControlModal
        isOpen={true}
        onClose={onClose}
        onRunWithMode={onRunWithMode}
        configCount={2}
      />
    )

    // Select 'all' mode
    const allRadio = screen.getByLabelText('evaluation.controlModal.evaluateAll')
    fireEvent.click(allRadio)

    const startBtn = screen.getByText('evaluation.controlModal.startEvaluation')
    fireEvent.click(startBtn)

    await waitFor(() => {
      expect(onRunWithMode).toHaveBeenCalledWith(true)
    })
  })

  it('shows error toast when onRunWithMode fails', async () => {
    const onRunWithMode = jest.fn().mockRejectedValue(new Error('Eval failed'))

    render(
      <EvaluationControlModal
        isOpen={true}
        onClose={jest.fn()}
        onRunWithMode={onRunWithMode}
        configCount={1}
      />
    )

    fireEvent.click(screen.getByText('evaluation.controlModal.startEvaluation'))

    await waitFor(() => {
      expect(mockAddToast).toHaveBeenCalledWith('Eval failed', 'error')
    })
  })

  it('shows error when no configs in direct API mode', async () => {
    render(
      <EvaluationControlModal
        isOpen={true}
        onClose={jest.fn()}
        projectId="proj-1"
        evaluationConfigs={[]}
      />
    )

    // Button should be disabled because displayConfigCount is 0
    const startBtn = screen.getByText('evaluation.controlModal.startEvaluation')
    expect(startBtn).toBeDisabled()
  })
})

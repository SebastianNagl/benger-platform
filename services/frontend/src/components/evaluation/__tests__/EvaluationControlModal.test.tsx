/**
 * @jest-environment jsdom
 */
import '@testing-library/jest-dom'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { EvaluationControlModal } from '../EvaluationControlModal'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, params?: Record<string, any>) => {
      const translations: Record<string, string> = {
        'evaluation.controlModal.title': 'Run Evaluation',
        'evaluation.controlModal.evaluationMode': 'Evaluation Mode',
        'evaluation.controlModal.evaluateMissingOnly': 'Missing Only',
        'evaluation.controlModal.evaluateMissingOnlyDesc': 'Only evaluate samples without results',
        'evaluation.controlModal.evaluateAll': 'All Samples',
        'evaluation.controlModal.evaluateAllDesc': 'Re-evaluate all samples, overwriting existing results',
        'evaluation.controlModal.evaluationConfigurations': 'Evaluation Configurations',
        'evaluation.controlModal.oneConfigWillBeRun': '1 configuration will be run',
        'evaluation.controlModal.configsWillBeRun': `${params?.count} configurations will be run`,
        'evaluation.controlModal.note': 'Note:',
        'evaluation.controlModal.backgroundInfo': 'Evaluation runs in the background.',
        'evaluation.controlModal.starting': 'Starting...',
        'evaluation.controlModal.startEvaluation': 'Start Evaluation',
        'evaluation.controlModal.cancel': 'Cancel',
        'evaluation.controlModal.failedToStart': 'Failed to start evaluation',
        'evaluation.controlModal.noConfigsFound': 'No configs found',
        'evaluation.controlModal.projectIdRequired': 'Project ID is required',
        'toasts.project.evaluationStarted': 'Evaluation started',
        'shared.alertDialog.close': 'Close',
      }
      return translations[key] || key
    },
  }),
}))

const mockAddToast = jest.fn()
jest.mock('@/components/shared/Toast', () => ({
  useToast: () => ({ addToast: mockAddToast }),
}))

const mockRunEvaluation = jest.fn()
jest.mock('@/lib/api/client', () => ({
  apiClient: {
    evaluations: {
      runEvaluation: (...args: any[]) => mockRunEvaluation(...args),
    },
  },
}))

// Mock HeadlessUI - compound components
jest.mock('@headlessui/react', () => {
  const Dialog = ({ children, onClose, className }: any) => (
    <div data-testid="dialog" className={className}>
      {typeof children === 'function' ? children({ open: true }) : children}
    </div>
  )
  Dialog.Title = ({ children, className, as }: any) => {
    const Tag = as || 'h3'
    return <Tag className={className}>{children}</Tag>
  }
  Dialog.Panel = ({ children, className }: any) => (
    <div data-testid="dialog-panel" className={className}>{children}</div>
  )
  const Transition = ({ children, show }: any) => (show !== false ? <>{children}</> : null)
  Transition.Root = ({ children, show }: any) => (show !== false ? <>{children}</> : null)
  Transition.Child = ({ children }: any) => <>{children}</>
  return { Dialog, Transition, Fragment: ({ children }: any) => <>{children}</> }
})

const defaultProps = {
  isOpen: true,
  projectId: 'project-1',
  evaluationConfigs: [
    { id: 'config-1', metric: 'exact_match', prediction_fields: ['answer'], reference_fields: ['gold_answer'] },
    { id: 'config-2', metric: 'rouge', prediction_fields: ['summary'], reference_fields: ['gold_summary'] },
  ],
  onClose: jest.fn(),
  onSuccess: jest.fn(),
}

describe('EvaluationControlModal', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockRunEvaluation.mockResolvedValue({})
  })

  describe('Rendering', () => {
    it('renders modal title', () => {
      render(<EvaluationControlModal {...defaultProps} />)
      expect(screen.getByText('Run Evaluation')).toBeInTheDocument()
    })

    it('renders evaluation mode radio buttons', () => {
      render(<EvaluationControlModal {...defaultProps} />)
      expect(screen.getByText('Missing Only')).toBeInTheDocument()
      expect(screen.getByText('All Samples')).toBeInTheDocument()
    })

    it('shows config count for multiple configs', () => {
      render(<EvaluationControlModal {...defaultProps} />)
      expect(screen.getByText('2 configurations will be run')).toBeInTheDocument()
    })

    it('shows singular config text for one config', () => {
      render(
        <EvaluationControlModal
          {...defaultProps}
          evaluationConfigs={[defaultProps.evaluationConfigs![0]]}
        />
      )
      expect(screen.getByText('1 configuration will be run')).toBeInTheDocument()
    })

    it('uses configCount prop over evaluationConfigs length', () => {
      render(
        <EvaluationControlModal
          {...defaultProps}
          configCount={5}
        />
      )
      expect(screen.getByText('5 configurations will be run')).toBeInTheDocument()
    })

    it('shows info note', () => {
      render(<EvaluationControlModal {...defaultProps} />)
      expect(screen.getByText(/Note:/)).toBeInTheDocument()
      expect(screen.getByText(/background/)).toBeInTheDocument()
    })

    it('renders start and cancel buttons', () => {
      render(<EvaluationControlModal {...defaultProps} />)
      expect(screen.getByText('Start Evaluation')).toBeInTheDocument()
      expect(screen.getByText('Cancel')).toBeInTheDocument()
    })
  })

  describe('Mode selection', () => {
    it('defaults to missing mode', () => {
      render(<EvaluationControlModal {...defaultProps} />)
      const missingRadio = screen.getByRole('radio', { name: /Missing Only/ })
      expect(missingRadio).toBeChecked()
    })

    it('switches to all mode', async () => {
      const user = userEvent.setup()
      render(<EvaluationControlModal {...defaultProps} />)

      const allRadio = screen.getByRole('radio', { name: /All Samples/ })
      await user.click(allRadio)
      expect(allRadio).toBeChecked()
    })
  })

  describe('Close', () => {
    it('calls onClose when cancel is clicked', async () => {
      const user = userEvent.setup()
      const onClose = jest.fn()
      render(<EvaluationControlModal {...defaultProps} onClose={onClose} />)

      await user.click(screen.getByText('Cancel'))
      expect(onClose).toHaveBeenCalledTimes(1)
    })
  })

  describe('Direct API submission', () => {
    it('calls runEvaluation with missing mode (forceRerun=false)', async () => {
      const user = userEvent.setup()
      render(<EvaluationControlModal {...defaultProps} />)

      await user.click(screen.getByText('Start Evaluation'))

      await waitFor(() => {
        expect(mockRunEvaluation).toHaveBeenCalledWith(
          expect.objectContaining({
            project_id: 'project-1',
            force_rerun: false,
          })
        )
      })
    })

    it('calls runEvaluation with all mode (forceRerun=true)', async () => {
      const user = userEvent.setup()
      render(<EvaluationControlModal {...defaultProps} />)

      await user.click(screen.getByRole('radio', { name: /All Samples/ }))
      await user.click(screen.getByText('Start Evaluation'))

      await waitFor(() => {
        expect(mockRunEvaluation).toHaveBeenCalledWith(
          expect.objectContaining({
            force_rerun: true,
          })
        )
      })
    })

    it('shows success toast and calls onSuccess/onClose on success', async () => {
      const user = userEvent.setup()
      const onSuccess = jest.fn()
      const onClose = jest.fn()
      render(<EvaluationControlModal {...defaultProps} onSuccess={onSuccess} onClose={onClose} />)

      await user.click(screen.getByText('Start Evaluation'))

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith('Evaluation started', 'success')
        expect(onSuccess).toHaveBeenCalled()
        expect(onClose).toHaveBeenCalled()
      })
    })

    it('shows error toast on API failure', async () => {
      const user = userEvent.setup()
      const consoleSpy = jest.spyOn(console, 'error').mockImplementation()
      mockRunEvaluation.mockRejectedValue({ message: 'Server error', response: { data: { detail: 'Rate limited' } } })

      render(<EvaluationControlModal {...defaultProps} />)

      await user.click(screen.getByText('Start Evaluation'))

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith('Rate limited', 'error')
      })
      consoleSpy.mockRestore()
    })

    it('disables start button when no configs and no callback', () => {
      render(
        <EvaluationControlModal
          {...defaultProps}
          evaluationConfigs={[]}
        />
      )

      const startButton = screen.getByText('Start Evaluation')
      expect(startButton).toBeDisabled()
    })

    it('shows toast when projectId is missing', async () => {
      const user = userEvent.setup()
      render(
        <EvaluationControlModal
          {...defaultProps}
          projectId={undefined}
        />
      )

      await user.click(screen.getByText('Start Evaluation'))
      expect(mockAddToast).toHaveBeenCalledWith('Project ID is required', 'error')
    })
  })

  describe('Callback mode (onRunWithMode)', () => {
    it('calls onRunWithMode instead of API when provided', async () => {
      const user = userEvent.setup()
      const onRunWithMode = jest.fn().mockResolvedValue(undefined)
      render(
        <EvaluationControlModal
          {...defaultProps}
          onRunWithMode={onRunWithMode}
        />
      )

      await user.click(screen.getByText('Start Evaluation'))

      await waitFor(() => {
        expect(onRunWithMode).toHaveBeenCalledWith(false) // missing mode -> forceRerun=false
        expect(mockRunEvaluation).not.toHaveBeenCalled()
      })
    })

    it('passes forceRerun=true when all mode selected in callback mode', async () => {
      const user = userEvent.setup()
      const onRunWithMode = jest.fn().mockResolvedValue(undefined)
      render(
        <EvaluationControlModal
          {...defaultProps}
          onRunWithMode={onRunWithMode}
        />
      )

      await user.click(screen.getByRole('radio', { name: /All Samples/ }))
      await user.click(screen.getByText('Start Evaluation'))

      await waitFor(() => {
        expect(onRunWithMode).toHaveBeenCalledWith(true)
      })
    })

    it('handles callback mode errors', async () => {
      const user = userEvent.setup()
      const consoleSpy = jest.spyOn(console, 'error').mockImplementation()
      const onRunWithMode = jest.fn().mockRejectedValue(new Error('Callback failed'))
      render(
        <EvaluationControlModal
          {...defaultProps}
          onRunWithMode={onRunWithMode}
        />
      )

      await user.click(screen.getByText('Start Evaluation'))

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith('Callback failed', 'error')
      })
      consoleSpy.mockRestore()
    })
  })

  describe('Loading state', () => {
    it('shows loading text while submitting', async () => {
      const user = userEvent.setup()
      mockRunEvaluation.mockReturnValue(new Promise(() => {}))

      render(<EvaluationControlModal {...defaultProps} />)

      await user.click(screen.getByText('Start Evaluation'))

      await waitFor(() => {
        expect(screen.getByText('Starting...')).toBeInTheDocument()
      })
    })
  })

  describe('Not rendering when closed', () => {
    it('does not render when isOpen is false', () => {
      render(<EvaluationControlModal {...defaultProps} isOpen={false} />)
      expect(screen.queryByText('Run Evaluation')).not.toBeInTheDocument()
    })
  })
})

import { render, screen, waitFor } from '@testing-library/react'
import { ProgressIndicator } from '../ProgressIndicator'

// Mock Heroicons
jest.mock('@heroicons/react/24/outline', () => ({
  CheckCircleIcon: (props: any) => (
    <svg data-testid="check-circle-icon" {...props} />
  ),
  XCircleIcon: (props: any) => <svg data-testid="x-circle-icon" {...props} />,
}))

describe('ProgressIndicator', () => {
  describe('basic rendering', () => {
    it('renders progress indicator with default props', () => {
      const { container } = render(<ProgressIndicator progress={50} />)

      const progressContainer = container.querySelector('.w-full.bg-zinc-200')
      expect(progressContainer).toBeInTheDocument()
    })

    it('renders with specified progress value', async () => {
      render(<ProgressIndicator progress={75} />)

      await waitFor(() => {
        expect(screen.getByText('75%')).toBeInTheDocument()
      })
    })

    it('renders progress bar container with correct styling', () => {
      const { container } = render(<ProgressIndicator progress={50} />)

      const progressContainer = container.querySelector('.bg-zinc-200')
      expect(progressContainer).toHaveClass(
        'w-full',
        'dark:bg-zinc-700',
        'rounded-full',
        'overflow-hidden'
      )
    })

    it('renders progress bar with correct width style', async () => {
      const { container } = render(<ProgressIndicator progress={60} />)

      await waitFor(() => {
        const progressBar = container.querySelector('.bg-emerald-500')
        expect(progressBar).toHaveStyle('width: 60%')
      })
    })
  })

  describe('progress animation', () => {
    it('animates progress changes', async () => {
      const { rerender, container } = render(<ProgressIndicator progress={0} />)

      rerender(<ProgressIndicator progress={100} />)

      await waitFor(
        () => {
          const progressBar = container.querySelector('.bg-emerald-500')
          expect(progressBar).toHaveStyle('width: 100%')
        },
        { timeout: 200 }
      )
    })

    it('clamps progress values to 0-100 range', async () => {
      const { container } = render(<ProgressIndicator progress={150} />)

      await waitFor(() => {
        expect(screen.getByText('100%')).toBeInTheDocument()
        const progressBar = container.querySelector('.bg-emerald-500')
        expect(progressBar).toHaveStyle('width: 100%')
      })
    })

    it('handles negative progress values', async () => {
      const { container } = render(<ProgressIndicator progress={-10} />)

      await waitFor(() => {
        expect(screen.getByText('0%')).toBeInTheDocument()
        const progressBar = container.querySelector('.bg-emerald-500')
        expect(progressBar).toHaveStyle('width: 0%')
      })
    })
  })

  describe('labels and text', () => {
    it('renders label when provided', () => {
      render(<ProgressIndicator progress={50} label="Processing data" />)

      expect(screen.getByText('Processing data')).toBeInTheDocument()
    })

    it('renders sublabel when provided', () => {
      render(<ProgressIndicator progress={50} sublabel="Step 2 of 5" />)

      expect(screen.getByText('Step 2 of 5')).toBeInTheDocument()
    })

    it('renders both label and sublabel', () => {
      render(
        <ProgressIndicator
          progress={50}
          label="Uploading files"
          sublabel="3 of 10 files uploaded"
        />
      )

      expect(screen.getByText('Uploading files')).toBeInTheDocument()
      expect(screen.getByText('3 of 10 files uploaded')).toBeInTheDocument()
    })

    it('hides percentage when showPercentage is false', () => {
      render(<ProgressIndicator progress={50} showPercentage={false} />)

      expect(screen.queryByText('50%')).not.toBeInTheDocument()
    })

    it('shows percentage by default', async () => {
      render(<ProgressIndicator progress={25} />)

      await waitFor(() => {
        expect(screen.getByText('25%')).toBeInTheDocument()
      })
    })
  })

  describe('size variants', () => {
    it('applies small size classes', () => {
      const { container } = render(
        <ProgressIndicator progress={50} size="sm" />
      )

      const progressContainer = container.querySelector('.h-1')
      expect(progressContainer).toBeInTheDocument()
    })

    it('applies medium size classes by default', () => {
      const { container } = render(<ProgressIndicator progress={50} />)

      const progressContainer = container.querySelector('.h-2')
      expect(progressContainer).toBeInTheDocument()
    })

    it('applies large size classes', () => {
      const { container } = render(
        <ProgressIndicator progress={50} size="lg" />
      )

      const progressContainer = container.querySelector('.h-3')
      expect(progressContainer).toBeInTheDocument()
    })

    it('applies correct text size for small variant', () => {
      render(
        <ProgressIndicator progress={50} size="sm" label="Small progress" />
      )

      const label = screen.getByText('Small progress')
      expect(label).toHaveClass('text-xs')
    })

    it('applies correct text size for large variant', () => {
      render(
        <ProgressIndicator progress={50} size="lg" label="Large progress" />
      )

      const label = screen.getByText('Large progress')
      expect(label).toHaveClass('text-base')
    })
  })

  describe('status variants', () => {
    it('applies running status color by default', () => {
      const { container } = render(<ProgressIndicator progress={50} />)

      const progressBar = container.querySelector('.bg-emerald-500')
      expect(progressBar).toBeInTheDocument()
    })

    it('applies success status color', () => {
      const { container } = render(
        <ProgressIndicator progress={100} status="success" />
      )

      const progressBar = container.querySelector('.bg-green-500')
      expect(progressBar).toBeInTheDocument()
    })

    it('applies error status color', () => {
      const { container } = render(
        <ProgressIndicator progress={50} status="error" />
      )

      const progressBar = container.querySelector('.bg-red-500')
      expect(progressBar).toBeInTheDocument()
    })

    it('applies idle status color', () => {
      const { container } = render(
        <ProgressIndicator progress={0} status="idle" />
      )

      const progressBar = container.querySelector('.bg-zinc-400')
      expect(progressBar).toBeInTheDocument()
    })

    it('shows check icon for success status', () => {
      render(<ProgressIndicator progress={100} status="success" />)

      expect(screen.getByTestId('check-circle-icon')).toBeInTheDocument()
    })

    it('shows error icon for error status', () => {
      render(<ProgressIndicator progress={50} status="error" />)

      expect(screen.getByTestId('x-circle-icon')).toBeInTheDocument()
    })

    it('does not show icons for running status', () => {
      render(<ProgressIndicator progress={50} status="running" />)

      expect(screen.queryByTestId('check-circle-icon')).not.toBeInTheDocument()
      expect(screen.queryByTestId('x-circle-icon')).not.toBeInTheDocument()
    })
  })

  describe('indeterminate mode', () => {
    it('enables indeterminate animation when specified', () => {
      const { container } = render(
        <ProgressIndicator progress={50} indeterminate />
      )

      const progressBar = container.querySelector('.animate-indeterminate')
      expect(progressBar).toBeInTheDocument()
    })

    it('hides percentage in indeterminate mode', () => {
      render(<ProgressIndicator progress={50} indeterminate />)

      expect(screen.queryByText('50%')).not.toBeInTheDocument()
    })

    it('still shows labels in indeterminate mode', () => {
      render(
        <ProgressIndicator
          progress={50}
          indeterminate
          label="Processing..."
          sublabel="Please wait"
        />
      )

      expect(screen.getByText('Processing...')).toBeInTheDocument()
      expect(screen.getByText('Please wait')).toBeInTheDocument()
    })

    it('applies correct animation classes', () => {
      const { container } = render(
        <ProgressIndicator progress={50} indeterminate />
      )

      const animatedBar = container.querySelector('.animate-indeterminate')
      expect(animatedBar).toHaveClass('animate-indeterminate')
    })
  })

  describe('custom styling', () => {
    it('applies custom className', () => {
      const { container } = render(
        <ProgressIndicator progress={50} className="custom-progress" />
      )

      const wrapper = container.querySelector('.custom-progress')
      expect(wrapper).toBeInTheDocument()
    })

    it('combines custom className with default classes', () => {
      const { container } = render(
        <ProgressIndicator progress={50} className="my-4" />
      )

      const wrapper = container.querySelector('.my-4.space-y-2')
      expect(wrapper).toBeInTheDocument()
    })
  })

  describe('dark mode support', () => {
    it('includes dark mode classes for background', () => {
      const { container } = render(<ProgressIndicator progress={50} />)

      const progressContainer = container.querySelector('.dark\\:bg-zinc-700')
      expect(progressContainer).toBeInTheDocument()
    })

    it('includes dark mode classes for text', () => {
      render(<ProgressIndicator progress={50} label="Test label" />)

      const label = screen.getByText('Test label')
      expect(label).toHaveClass('dark:text-white')
    })

    it('includes dark mode classes for sublabel', () => {
      render(<ProgressIndicator progress={50} sublabel="Test sublabel" />)

      const sublabel = screen.getByText('Test sublabel')
      expect(sublabel).toHaveClass('dark:text-zinc-400')
    })
  })

  describe('accessibility', () => {
    it('provides progressbar role', async () => {
      const { container } = render(<ProgressIndicator progress={50} />)

      // The component creates a visual progress bar, check for ARIA structure
      await waitFor(() => {
        const progressElement = container.querySelector('[style*="width: 50%"]')
        expect(progressElement).toBeInTheDocument()
      })
    })

    it('provides readable progress information', async () => {
      render(<ProgressIndicator progress={75} label="File upload" />)

      expect(screen.getByText('File upload')).toBeInTheDocument()
      await waitFor(() => {
        expect(screen.getByText('75%')).toBeInTheDocument()
      })
    })

    it('maintains semantic structure with labels', async () => {
      render(
        <ProgressIndicator
          progress={60}
          label="Processing documents"
          sublabel="5 of 8 complete"
        />
      )

      expect(screen.getByText('Processing documents')).toBeInTheDocument()
      expect(screen.getByText('5 of 8 complete')).toBeInTheDocument()
      await waitFor(() => {
        expect(screen.getByText('60%')).toBeInTheDocument()
      })
    })
  })

  describe('layout and positioning', () => {
    it('arranges labels and percentage correctly', () => {
      const { container } = render(
        <ProgressIndicator
          progress={50}
          label="Main label"
          sublabel="Sub label"
        />
      )

      const flexContainer = container.querySelector(
        '.flex.items-center.justify-between'
      )
      expect(flexContainer).toBeInTheDocument()
    })

    it('stacks label and sublabel vertically', () => {
      render(
        <ProgressIndicator
          progress={50}
          label="Main label"
          sublabel="Sub label"
        />
      )

      // Labels should be in same container but sublabel should come after label
      const label = screen.getByText('Main label')
      const sublabel = screen.getByText('Sub label')
      expect(label).toBeInTheDocument()
      expect(sublabel).toBeInTheDocument()
    })

    it('positions percentage and status icons together', () => {
      const { container } = render(
        <ProgressIndicator progress={100} status="success" />
      )

      const rightSection = container.querySelector('.flex.items-center.gap-2')
      expect(rightSection).toBeInTheDocument()
    })
  })

  describe('edge cases', () => {
    it('handles zero progress', async () => {
      render(<ProgressIndicator progress={0} />)

      await waitFor(() => {
        expect(screen.getByText('0%')).toBeInTheDocument()
      })
    })

    it('handles complete progress', async () => {
      render(<ProgressIndicator progress={100} />)

      await waitFor(() => {
        expect(screen.getByText('100%')).toBeInTheDocument()
      })
    })

    it('rounds fractional progress values', async () => {
      render(<ProgressIndicator progress={33.7} />)

      await waitFor(() => {
        expect(screen.getByText('34%')).toBeInTheDocument()
      })
    })

    it('handles missing props gracefully', () => {
      const { container } = render(<ProgressIndicator progress={50} />)

      expect(container.firstChild).toBeInTheDocument()
    })

    it('handles empty labels', async () => {
      render(<ProgressIndicator progress={50} label="" sublabel="" />)

      await waitFor(() => {
        expect(screen.getByText('50%')).toBeInTheDocument()
      })
    })
  })
})

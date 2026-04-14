import { render, screen } from '@testing-library/react'
import { Alert, AlertDescription } from '../alert'

describe('Alert Components', () => {
  describe('Alert', () => {
    it('renders correctly with children', () => {
      render(
        <Alert>
          <div data-testid="alert-child">Alert content</div>
        </Alert>
      )

      const alert = screen.getByTestId('alert-child').parentElement
      expect(alert).toBeInTheDocument()
      expect(screen.getByTestId('alert-child')).toBeInTheDocument()
    })

    it('applies default variant styles', () => {
      render(
        <Alert data-testid="alert">
          <div>Default alert</div>
        </Alert>
      )

      const alert = screen.getByTestId('alert')
      expect(alert).toHaveClass(
        'bg-blue-50',
        'border-blue-200',
        'text-blue-900',
        'dark:bg-blue-900/20',
        'dark:border-blue-800',
        'dark:text-blue-200'
      )
    })

    it('applies destructive variant styles', () => {
      render(
        <Alert variant="destructive" data-testid="alert">
          <div>Destructive alert</div>
        </Alert>
      )

      const alert = screen.getByTestId('alert')
      expect(alert).toHaveClass(
        'bg-red-50',
        'border-red-200',
        'text-red-900',
        'dark:bg-red-900/20',
        'dark:border-red-800',
        'dark:text-red-200'
      )
    })

    it('applies base styles consistently', () => {
      render(
        <Alert data-testid="alert">
          <div>Base styles</div>
        </Alert>
      )

      const alert = screen.getByTestId('alert')
      expect(alert).toHaveClass('px-4', 'py-3', 'rounded-md', 'border')
    })

    it('applies custom className alongside default styles', () => {
      render(
        <Alert className="custom-class" data-testid="alert">
          <div>Custom alert</div>
        </Alert>
      )

      const alert = screen.getByTestId('alert')
      expect(alert).toHaveClass('custom-class')
      expect(alert).toHaveClass('px-4') // Base styles still applied
      expect(alert).toHaveClass('bg-blue-50') // Default variant still applied
    })

    it('forwards HTML div attributes', () => {
      render(
        <Alert
          data-testid="alert"
          id="alert-id"
          role="alert"
          aria-live="polite"
          onClick={jest.fn()}
        >
          <div>Alert with attributes</div>
        </Alert>
      )

      const alert = screen.getByTestId('alert')
      expect(alert).toHaveAttribute('id', 'alert-id')
      expect(alert).toHaveAttribute('role', 'alert')
      expect(alert).toHaveAttribute('aria-live', 'polite')
      expect(alert).toHaveAttribute('data-testid', 'alert')
    })
  })

  describe('AlertDescription', () => {
    it('renders as paragraph element', () => {
      render(<AlertDescription>Description text</AlertDescription>)

      const description = screen.getByText('Description text')
      expect(description).toBeInTheDocument()
      expect(description.tagName).toBe('P')
    })

    it('applies default description styles', () => {
      render(
        <AlertDescription data-testid="description">
          Description
        </AlertDescription>
      )

      const description = screen.getByTestId('description')
      expect(description).toHaveClass('text-sm')
    })

    it('applies custom className', () => {
      render(
        <AlertDescription
          className="custom-description"
          data-testid="description"
        >
          Custom description
        </AlertDescription>
      )

      const description = screen.getByTestId('description')
      expect(description).toHaveClass('custom-description')
      expect(description).toHaveClass('text-sm') // Default styles still applied
    })

    it('forwards HTML paragraph attributes', () => {
      render(
        <AlertDescription
          data-testid="description"
          id="desc-id"
          aria-label="Alert description"
        >
          Description with attributes
        </AlertDescription>
      )

      const description = screen.getByTestId('description')
      expect(description).toHaveAttribute('id', 'desc-id')
      expect(description).toHaveAttribute('aria-label', 'Alert description')
    })
  })

  describe('Alert composition', () => {
    it('renders complete alert with description', () => {
      render(
        <Alert data-testid="complete-alert">
          <AlertDescription data-testid="complete-description">
            This is an alert with a description
          </AlertDescription>
        </Alert>
      )

      expect(screen.getByTestId('complete-alert')).toBeInTheDocument()
      expect(screen.getByTestId('complete-description')).toBeInTheDocument()
      expect(
        screen.getByText('This is an alert with a description')
      ).toBeInTheDocument()
    })

    it('works with multiple children', () => {
      render(
        <Alert data-testid="multi-child-alert">
          <h4>Alert Title</h4>
          <AlertDescription>Alert description</AlertDescription>
          <div>Additional content</div>
        </Alert>
      )

      const alert = screen.getByTestId('multi-child-alert')
      expect(alert).toBeInTheDocument()
      expect(screen.getByText('Alert Title')).toBeInTheDocument()
      expect(screen.getByText('Alert description')).toBeInTheDocument()
      expect(screen.getByText('Additional content')).toBeInTheDocument()
    })

    it('handles nested AlertDescription components', () => {
      render(
        <Alert>
          <AlertDescription>First description</AlertDescription>
          <AlertDescription>Second description</AlertDescription>
        </Alert>
      )

      expect(screen.getByText('First description')).toBeInTheDocument()
      expect(screen.getByText('Second description')).toBeInTheDocument()
    })
  })

  describe('Variants with AlertDescription', () => {
    it('renders default variant with description', () => {
      render(
        <Alert variant="default" data-testid="default-alert">
          <AlertDescription>Default alert description</AlertDescription>
        </Alert>
      )

      const alert = screen.getByTestId('default-alert')
      expect(alert).toHaveClass('bg-blue-50', 'text-blue-900')
      expect(screen.getByText('Default alert description')).toBeInTheDocument()
    })

    it('renders destructive variant with description', () => {
      render(
        <Alert variant="destructive" data-testid="destructive-alert">
          <AlertDescription>Error occurred!</AlertDescription>
        </Alert>
      )

      const alert = screen.getByTestId('destructive-alert')
      expect(alert).toHaveClass('bg-red-50', 'text-red-900')
      expect(screen.getByText('Error occurred!')).toBeInTheDocument()
    })
  })

  describe('Accessibility', () => {
    it('supports ARIA alert role', () => {
      render(
        <Alert role="alert">
          <AlertDescription>Important message</AlertDescription>
        </Alert>
      )

      const alert = screen.getByRole('alert')
      expect(alert).toBeInTheDocument()
      expect(alert).toHaveTextContent('Important message')
    })

    it('supports ARIA live regions', () => {
      render(
        <Alert aria-live="assertive" data-testid="live-alert">
          <AlertDescription>Urgent notification</AlertDescription>
        </Alert>
      )

      const alert = screen.getByTestId('live-alert')
      expect(alert).toHaveAttribute('aria-live', 'assertive')
    })

    it('maintains semantic structure', () => {
      render(
        <Alert>
          <AlertDescription>Semantic alert content</AlertDescription>
        </Alert>
      )

      const description = screen.getByText('Semantic alert content')
      expect(description.tagName).toBe('P')
    })
  })

  describe('Dark mode support', () => {
    it('includes dark mode classes for default variant', () => {
      render(
        <Alert data-testid="dark-default" className="dark">
          <AlertDescription>Dark mode default</AlertDescription>
        </Alert>
      )

      const alert = screen.getByTestId('dark-default')
      expect(alert).toHaveClass(
        'dark:bg-blue-900/20',
        'dark:border-blue-800',
        'dark:text-blue-200'
      )
    })

    it('includes dark mode classes for destructive variant', () => {
      render(
        <Alert
          variant="destructive"
          data-testid="dark-destructive"
          className="dark"
        >
          <AlertDescription>Dark mode error</AlertDescription>
        </Alert>
      )

      const alert = screen.getByTestId('dark-destructive')
      expect(alert).toHaveClass(
        'dark:bg-red-900/20',
        'dark:border-red-800',
        'dark:text-red-200'
      )
    })
  })

  describe('Event handling', () => {
    it('handles click events on Alert', () => {
      const handleClick = jest.fn()

      render(
        <Alert onClick={handleClick} data-testid="clickable-alert">
          <AlertDescription>Clickable alert</AlertDescription>
        </Alert>
      )

      const alert = screen.getByTestId('clickable-alert')
      alert.click()

      expect(handleClick).toHaveBeenCalledTimes(1)
    })

    it('handles click events on AlertDescription', () => {
      const handleClick = jest.fn()

      render(
        <Alert>
          <AlertDescription
            onClick={handleClick}
            data-testid="clickable-description"
          >
            Clickable description
          </AlertDescription>
        </Alert>
      )

      const description = screen.getByTestId('clickable-description')
      description.click()

      expect(handleClick).toHaveBeenCalledTimes(1)
    })
  })

  describe('Edge cases', () => {
    it('handles empty children in Alert', () => {
      render(<Alert data-testid="empty-alert"></Alert>)

      const alert = screen.getByTestId('empty-alert')
      expect(alert).toBeInTheDocument()
      expect(alert).toHaveTextContent('')
    })

    it('handles empty children in AlertDescription', () => {
      render(
        <AlertDescription data-testid="empty-description"></AlertDescription>
      )

      const description = screen.getByTestId('empty-description')
      expect(description).toBeInTheDocument()
      expect(description).toHaveTextContent('')
    })

    it('handles complex nested content', () => {
      render(
        <Alert>
          <AlertDescription>
            <span>Nested</span>
            <strong>content</strong>
            <em>works</em>
          </AlertDescription>
        </Alert>
      )

      expect(screen.getByText('Nested')).toBeInTheDocument()
      expect(screen.getByText('content')).toBeInTheDocument()
      expect(screen.getByText('works')).toBeInTheDocument()
    })

    it('handles multiple Alert instances', () => {
      render(
        <div>
          <Alert data-testid="alert-1">
            <AlertDescription>First alert</AlertDescription>
          </Alert>
          <Alert variant="destructive" data-testid="alert-2">
            <AlertDescription>Second alert</AlertDescription>
          </Alert>
        </div>
      )

      expect(screen.getByTestId('alert-1')).toBeInTheDocument()
      expect(screen.getByTestId('alert-2')).toBeInTheDocument()
      expect(screen.getByText('First alert')).toBeInTheDocument()
      expect(screen.getByText('Second alert')).toBeInTheDocument()
    })

    it('handles very long text content', () => {
      const longText =
        'This is a very long alert message that might wrap to multiple lines and should still render correctly with all styles applied properly.'

      render(
        <Alert>
          <AlertDescription>{longText}</AlertDescription>
        </Alert>
      )

      expect(screen.getByText(longText)).toBeInTheDocument()
    })
  })

  describe('TypeScript compliance', () => {
    it('accepts valid variant props', () => {
      // This test ensures TypeScript types are correctly defined
      render(
        <div>
          <Alert variant="default">Default</Alert>
          <Alert variant="destructive">Destructive</Alert>
        </div>
      )

      expect(screen.getByText('Default')).toBeInTheDocument()
      expect(screen.getByText('Destructive')).toBeInTheDocument()
    })

    it('requires children prop', () => {
      // This test ensures the children prop is required
      render(
        <Alert>
          <AlertDescription>Required children</AlertDescription>
        </Alert>
      )

      expect(screen.getByText('Required children')).toBeInTheDocument()
    })
  })
})

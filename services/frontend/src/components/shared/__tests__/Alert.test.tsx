import { render, screen } from '@testing-library/react'
import { Alert } from '../Alert'

describe('Alert', () => {
  const defaultText = 'Test alert message'

  it('renders correctly with default props', () => {
    render(<Alert>{defaultText}</Alert>)
    expect(screen.getByText(defaultText)).toBeInTheDocument()
  })

  it('renders with info variant by default', () => {
    const { container } = render(<Alert>{defaultText}</Alert>)
    const alertElement = container.firstChild as HTMLElement
    expect(alertElement).toHaveClass('bg-blue-50')
  })

  it('renders with success variant', () => {
    const { container } = render(<Alert variant="success">{defaultText}</Alert>)
    const alertElement = container.firstChild as HTMLElement
    expect(alertElement).toHaveClass('bg-green-50')
    expect(screen.getByText(defaultText)).toBeInTheDocument()
  })

  it('renders with warning variant', () => {
    const { container } = render(<Alert variant="warning">{defaultText}</Alert>)
    const alertElement = container.firstChild as HTMLElement
    expect(alertElement).toHaveClass('bg-amber-50')
    expect(screen.getByText(defaultText)).toBeInTheDocument()
  })

  it('renders with error variant', () => {
    const { container } = render(<Alert variant="error">{defaultText}</Alert>)
    const alertElement = container.firstChild as HTMLElement
    expect(alertElement).toHaveClass('bg-red-50')
    expect(screen.getByText(defaultText)).toBeInTheDocument()
  })

  it('applies custom className', () => {
    const customClass = 'custom-alert-class'
    const { container } = render(
      <Alert className={customClass}>{defaultText}</Alert>
    )
    const alertElement = container.firstChild as HTMLElement
    expect(alertElement).toHaveClass(customClass)
  })

  it('renders complex children content', () => {
    render(
      <Alert>
        <h3>Alert Title</h3>
        <p>Alert description</p>
      </Alert>
    )
    expect(screen.getByText('Alert Title')).toBeInTheDocument()
    expect(screen.getByText('Alert description')).toBeInTheDocument()
  })

  it('maintains proper structure with icon and content', () => {
    const { container } = render(<Alert>{defaultText}</Alert>)
    const iconContainer = container.querySelector('svg')
    expect(iconContainer).toBeInTheDocument()
    const flexContainer = container.querySelector('.flex.items-start.gap-3')
    expect(flexContainer).toBeInTheDocument()
  })

  it('renders different icons for different variants', () => {
    const { container: infoContainer } = render(
      <Alert variant="info">Info</Alert>
    )
    const { container: successContainer } = render(
      <Alert variant="success">Success</Alert>
    )
    const { container: warningContainer } = render(
      <Alert variant="warning">Warning</Alert>
    )
    const { container: errorContainer } = render(
      <Alert variant="error">Error</Alert>
    )

    // Each variant should have an icon
    expect(infoContainer.querySelector('svg')).toBeInTheDocument()
    expect(successContainer.querySelector('svg')).toBeInTheDocument()
    expect(warningContainer.querySelector('svg')).toBeInTheDocument()
    expect(errorContainer.querySelector('svg')).toBeInTheDocument()
  })

  it('applies correct icon colors for each variant', () => {
    const { container: infoContainer } = render(
      <Alert variant="info">Info</Alert>
    )
    const infoIcon = infoContainer.querySelector('svg')
    expect(infoIcon).toHaveClass('text-blue-600')

    const { container: successContainer } = render(
      <Alert variant="success">Success</Alert>
    )
    const successIcon = successContainer.querySelector('svg')
    expect(successIcon).toHaveClass('text-green-600')

    const { container: warningContainer } = render(
      <Alert variant="warning">Warning</Alert>
    )
    const warningIcon = warningContainer.querySelector('svg')
    expect(warningIcon).toHaveClass('text-amber-600')

    const { container: errorContainer } = render(
      <Alert variant="error">Error</Alert>
    )
    const errorIcon = errorContainer.querySelector('svg')
    expect(errorIcon).toHaveClass('text-red-600')
  })
})

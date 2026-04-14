/**
 * Tests for StyleContainer component
 * Tests that it passes through children
 */

/**
 * @jest-environment jsdom
 */

import '@testing-library/jest-dom'
import { render, screen } from '@testing-library/react'

import StyleContainer from '../StyleContainer'

describe('StyleContainer', () => {
  const defaultProps = {
    config: {
      type: 'Style',
      name: 'style',
      props: {},
      children: [],
    },
    taskData: {},
    value: undefined,
    onChange: jest.fn(),
    onAnnotation: jest.fn(),
  }

  it('renders children', () => {
    render(
      <StyleContainer {...defaultProps}>
        <div data-testid="child">Child Content</div>
      </StyleContainer>
    )
    expect(screen.getByTestId('child')).toBeInTheDocument()
    expect(screen.getByText('Child Content')).toBeInTheDocument()
  })

  it('renders multiple children', () => {
    render(
      <StyleContainer {...defaultProps}>
        <div data-testid="child-1">First</div>
        <div data-testid="child-2">Second</div>
      </StyleContainer>
    )
    expect(screen.getByTestId('child-1')).toBeInTheDocument()
    expect(screen.getByTestId('child-2')).toBeInTheDocument()
  })

  it('renders without children', () => {
    const { container } = render(<StyleContainer {...defaultProps} />)
    // Should render empty without errors
    expect(container).toBeInTheDocument()
  })
})

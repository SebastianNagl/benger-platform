/**
 * Tests for HeaderDisplay component
 * Tests heading rendering, level selection, and prop handling
 */

/**
 * @jest-environment jsdom
 */

import '@testing-library/jest-dom'
import { render, screen } from '@testing-library/react'

import HeaderDisplay from '../HeaderDisplay'

describe('HeaderDisplay', () => {
  const defaultProps = {
    config: {
      type: 'Header',
      name: 'header',
      props: {
        value: 'Test Header',
      },
      children: [],
    },
    taskData: {},
    value: undefined,
    onChange: jest.fn(),
    onAnnotation: jest.fn(),
  }

  it('renders header text from value prop', () => {
    render(<HeaderDisplay {...defaultProps} />)
    expect(screen.getByText('Test Header')).toBeInTheDocument()
  })

  it('renders header text from content prop when value is not set', () => {
    const props = {
      ...defaultProps,
      config: {
        ...defaultProps.config,
        props: { content: 'Content Header' },
      },
    }
    render(<HeaderDisplay {...props} />)
    expect(screen.getByText('Content Header')).toBeInTheDocument()
  })

  it('renders "Header" as fallback when no value or content is set', () => {
    const props = {
      ...defaultProps,
      config: {
        ...defaultProps.config,
        props: {},
      },
    }
    render(<HeaderDisplay {...props} />)
    expect(screen.getByText('Header')).toBeInTheDocument()
  })

  it('renders as h3 by default', () => {
    const { container } = render(<HeaderDisplay {...defaultProps} />)
    const heading = container.querySelector('h3')
    expect(heading).not.toBeNull()
    expect(heading).toHaveTextContent('Test Header')
  })

  it('renders as h1 when level is 1', () => {
    const props = {
      ...defaultProps,
      config: {
        ...defaultProps.config,
        props: { value: 'H1 Header', level: '1' },
      },
    }
    const { container } = render(<HeaderDisplay {...props} />)
    const heading = container.querySelector('h1')
    expect(heading).not.toBeNull()
    expect(heading).toHaveTextContent('H1 Header')
  })

  it('renders as h2 when level is 2', () => {
    const props = {
      ...defaultProps,
      config: {
        ...defaultProps.config,
        props: { value: 'H2 Header', level: '2' },
      },
    }
    const { container } = render(<HeaderDisplay {...props} />)
    expect(container.querySelector('h2')).not.toBeNull()
  })

  it('renders as h4 when level is 4', () => {
    const props = {
      ...defaultProps,
      config: {
        ...defaultProps.config,
        props: { value: 'H4 Header', level: '4' },
      },
    }
    const { container } = render(<HeaderDisplay {...props} />)
    expect(container.querySelector('h4')).not.toBeNull()
  })

  it('applies custom className', () => {
    const props = {
      ...defaultProps,
      config: {
        ...defaultProps.config,
        props: { value: 'Styled Header', className: 'text-red-500' },
      },
    }
    const { container } = render(<HeaderDisplay {...props} />)
    const heading = container.querySelector('h3')
    expect(heading).toHaveClass('text-red-500')
  })

  it('has font-semibold styling by default', () => {
    const { container } = render(<HeaderDisplay {...defaultProps} />)
    const heading = container.querySelector('h3')
    expect(heading).toHaveClass('font-semibold')
  })
})

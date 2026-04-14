/**
 * Coverage-focused tests for RatingInput
 *
 * Targets uncovered branches:
 * - Click same rating to toggle off (rating === newRating -> 0)
 * - No toName (annotation not created)
 * - hint text rendering
 * - required asterisk
 * - Custom maxRating
 * - Hover state (active icon rendering)
 * - config.name fallback
 */

/**
 * @jest-environment jsdom
 */

import '@testing-library/jest-dom'
import { fireEvent, render, screen } from '@testing-library/react'
import RatingInput from '../RatingInput'

jest.mock('@/lib/labelConfig/dataBinding', () => ({
  buildAnnotationResult: jest.fn((name, type, value, toName) => ({
    id: `${name}-result`,
    from_name: name,
    to_name: toName,
    type: type.toLowerCase(),
    value: { rating: value },
  })),
}))

jest.mock('@heroicons/react/24/outline', () => ({
  StarIcon: (props: any) => <svg data-testid="star-outline" {...props} />,
}))

jest.mock('@heroicons/react/24/solid', () => ({
  StarIcon: (props: any) => <svg data-testid="star-solid" {...props} />,
}))

const baseConfig = {
  name: 'rating',
  type: 'Rating',
  props: {
    name: 'myRating',
    toName: 'text',
    maxRating: '5',
    required: 'false',
  },
  children: [],
}

describe('RatingInput - branch coverage', () => {
  const mockOnChange = jest.fn()
  const mockOnAnnotation = jest.fn()

  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('renders 5 star buttons by default', () => {
    render(
      <RatingInput
        config={baseConfig}
        taskData={{}}
        value={0}
        onChange={mockOnChange}
        onAnnotation={mockOnAnnotation}
      />
    )

    const buttons = screen.getAllByRole('button')
    expect(buttons).toHaveLength(5)
  })

  it('renders custom maxRating', () => {
    const config = {
      ...baseConfig,
      props: { ...baseConfig.props, maxRating: '10' },
    }

    render(
      <RatingInput
        config={config}
        taskData={{}}
        value={0}
        onChange={mockOnChange}
        onAnnotation={mockOnAnnotation}
      />
    )

    const buttons = screen.getAllByRole('button')
    expect(buttons).toHaveLength(10)
  })

  it('selects a rating and creates annotation', () => {
    render(
      <RatingInput
        config={baseConfig}
        taskData={{}}
        value={0}
        onChange={mockOnChange}
        onAnnotation={mockOnAnnotation}
      />
    )

    const buttons = screen.getAllByRole('button')
    fireEvent.click(buttons[2]) // Click 3rd star

    expect(mockOnChange).toHaveBeenCalledWith(3)
    expect(mockOnAnnotation).toHaveBeenCalled()
  })

  it('toggles rating off when clicking same star', () => {
    render(
      <RatingInput
        config={baseConfig}
        taskData={{}}
        value={3}
        onChange={mockOnChange}
        onAnnotation={mockOnAnnotation}
      />
    )

    const buttons = screen.getAllByRole('button')
    fireEvent.click(buttons[2]) // Click 3rd star again (same as current rating)

    expect(mockOnChange).toHaveBeenCalledWith(0) // Should toggle to 0
  })

  it('does not create annotation when toName is missing', () => {
    const config = {
      ...baseConfig,
      props: { ...baseConfig.props, toName: undefined },
    }

    render(
      <RatingInput
        config={config}
        taskData={{}}
        value={0}
        onChange={mockOnChange}
        onAnnotation={mockOnAnnotation}
      />
    )

    const buttons = screen.getAllByRole('button')
    fireEvent.click(buttons[0])

    expect(mockOnChange).toHaveBeenCalledWith(1)
    expect(mockOnAnnotation).not.toHaveBeenCalled()
  })

  it('shows required asterisk when required', () => {
    const config = {
      ...baseConfig,
      props: { ...baseConfig.props, required: 'true' },
    }

    render(
      <RatingInput
        config={config}
        taskData={{}}
        value={0}
        onChange={mockOnChange}
        onAnnotation={mockOnAnnotation}
      />
    )

    expect(screen.getByText('*')).toBeInTheDocument()
  })

  it('shows hint text', () => {
    const config = {
      ...baseConfig,
      props: { ...baseConfig.props, hint: 'Rate from 1 to 5' },
    }

    render(
      <RatingInput
        config={config}
        taskData={{}}
        value={0}
        onChange={mockOnChange}
        onAnnotation={mockOnAnnotation}
      />
    )

    expect(screen.getByText('Rate from 1 to 5')).toBeInTheDocument()
  })

  it('shows active stars based on hover state', () => {
    render(
      <RatingInput
        config={baseConfig}
        taskData={{}}
        value={0}
        onChange={mockOnChange}
        onAnnotation={mockOnAnnotation}
      />
    )

    const buttons = screen.getAllByRole('button')

    // Hover over 3rd star
    fireEvent.mouseEnter(buttons[2])

    // First 3 stars should be solid (active)
    const solidStars = screen.getAllByTestId('star-solid')
    expect(solidStars).toHaveLength(3)

    // Mouse leave resets hover
    fireEvent.mouseLeave(buttons[2])

    // All stars should be outline (no hover, no selection)
    const outlineStars = screen.getAllByTestId('star-outline')
    expect(outlineStars).toHaveLength(5)
  })

  it('uses label from config.props.label', () => {
    const config = {
      ...baseConfig,
      props: { ...baseConfig.props, label: 'Quality Rating' },
    }

    render(
      <RatingInput
        config={config}
        taskData={{}}
        value={0}
        onChange={mockOnChange}
        onAnnotation={mockOnAnnotation}
      />
    )

    expect(screen.getByText('Quality Rating')).toBeInTheDocument()
  })

  it('uses config.name as fallback label', () => {
    const config = {
      ...baseConfig,
      props: { ...baseConfig.props, name: undefined },
    }

    render(
      <RatingInput
        config={config}
        taskData={{}}
        value={0}
        onChange={mockOnChange}
        onAnnotation={mockOnAnnotation}
      />
    )

    expect(screen.getByText('rating')).toBeInTheDocument()
  })

  it('initializes with external value', () => {
    render(
      <RatingInput
        config={baseConfig}
        taskData={{}}
        value={4}
        onChange={mockOnChange}
        onAnnotation={mockOnAnnotation}
      />
    )

    // 4 solid stars should be shown
    const solidStars = screen.getAllByTestId('star-solid')
    expect(solidStars).toHaveLength(4)
  })
})

/**
 * Comprehensive tests for RatingInput component
 * Tests star rating selection, hover effects, value management, and annotation creation
 */

/**
 * @jest-environment jsdom
 */

import '@testing-library/jest-dom'
import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

// Mock Label component
jest.mock('@/components/shared/Label', () => ({
  Label: ({ children }: any) => <label data-testid="label">{children}</label>,
}))

// Mock data binding utilities
const mockBuildAnnotationResult = jest.fn((name, type, value, toName) => ({
  from_name: name,
  to_name: toName,
  type,
  value,
}))

jest.mock('@/lib/labelConfig/dataBinding', () => ({
  buildAnnotationResult: (...args: any[]) => mockBuildAnnotationResult(...args),
}))

// Mock Heroicons
jest.mock('@heroicons/react/24/outline', () => ({
  StarIcon: ({ className }: any) => (
    <svg data-testid="star-outline" className={className} />
  ),
}))

jest.mock('@heroicons/react/24/solid', () => ({
  StarIcon: ({ className }: any) => (
    <svg data-testid="star-solid" className={className} />
  ),
}))

// Import the component after mocks
import RatingInput from '../RatingInput'

describe('RatingInput', () => {
  const mockOnChange = jest.fn()
  const mockOnAnnotation = jest.fn()

  const defaultConfig = {
    type: 'Rating',
    name: 'quality',
    props: {
      name: 'quality',
      toName: 'text',
      label: 'Rate Quality',
      maxRating: '5',
      required: 'false',
    },
    children: [],
  }

  const defaultProps = {
    config: defaultConfig,
    taskData: { text: 'Sample text' },
    value: 0,
    onChange: mockOnChange,
    onAnnotation: mockOnAnnotation,
  }

  beforeEach(() => {
    jest.clearAllMocks()
  })

  describe('Basic Rendering', () => {
    it('renders with label', () => {
      render(<RatingInput {...defaultProps} />)

      expect(screen.getByText('Rate Quality')).toBeInTheDocument()
    })

    it('renders 5 stars by default', () => {
      render(<RatingInput {...defaultProps} />)

      const stars = screen.getAllByRole('button')
      expect(stars).toHaveLength(5)
    })

    it('renders custom max rating', () => {
      const customConfig = {
        ...defaultConfig,
        props: { ...defaultConfig.props, maxRating: '10' },
      }

      render(<RatingInput {...defaultProps} config={customConfig} />)

      const stars = screen.getAllByRole('button')
      expect(stars).toHaveLength(10)
    })

    it('renders required asterisk when required', () => {
      const requiredConfig = {
        ...defaultConfig,
        props: { ...defaultConfig.props, required: 'true' },
      }

      render(<RatingInput {...defaultProps} config={requiredConfig} />)

      expect(screen.getByText('*')).toBeInTheDocument()
    })

    it('renders hint when provided', () => {
      const configWithHint = {
        ...defaultConfig,
        props: {
          ...defaultConfig.props,
          hint: 'Click to rate from 1 to 5',
        },
      }

      render(<RatingInput {...defaultProps} config={configWithHint} />)

      expect(screen.getByText('Click to rate from 1 to 5')).toBeInTheDocument()
    })

    it('uses fallback label when label not provided', () => {
      const configWithoutLabel = {
        ...defaultConfig,
        props: {
          ...defaultConfig.props,
          label: undefined,
        },
      }

      render(<RatingInput {...defaultProps} config={configWithoutLabel} />)

      expect(screen.getByText('quality')).toBeInTheDocument()
    })

    it('uses name as fallback when both label and name not in props', () => {
      const configWithOnlyTypeName = {
        ...defaultConfig,
        name: 'fallback-name',
        props: {
          toName: 'text',
        },
      }

      render(<RatingInput {...defaultProps} config={configWithOnlyTypeName} />)

      expect(screen.getByText('fallback-name')).toBeInTheDocument()
    })
  })

  describe('Rating Selection', () => {
    it('selects rating when star is clicked', async () => {
      const user = userEvent.setup()
      render(<RatingInput {...defaultProps} />)

      const stars = screen.getAllByRole('button')
      await user.click(stars[2]) // Click third star

      expect(mockOnChange).toHaveBeenCalledWith(3)
    })

    it('calls onAnnotation when rating is selected', async () => {
      const user = userEvent.setup()
      render(<RatingInput {...defaultProps} />)

      const stars = screen.getAllByRole('button')
      await user.click(stars[3]) // Click fourth star

      expect(mockOnAnnotation).toHaveBeenCalledWith({
        from_name: 'quality',
        to_name: 'text',
        type: 'Rating',
        value: 4,
      })
    })

    it('deselects rating when clicking same star twice', async () => {
      const user = userEvent.setup()
      render(<RatingInput {...defaultProps} value={3} />)

      const stars = screen.getAllByRole('button')
      await user.click(stars[2]) // Click third star (currently selected)

      expect(mockOnChange).toHaveBeenCalledWith(0)
    })

    it('changes rating when different star is clicked', async () => {
      const user = userEvent.setup()
      render(<RatingInput {...defaultProps} value={2} />)

      const stars = screen.getAllByRole('button')
      await user.click(stars[4]) // Click fifth star

      expect(mockOnChange).toHaveBeenCalledWith(5)
    })

    it('selects minimum rating (1 star)', async () => {
      const user = userEvent.setup()
      render(<RatingInput {...defaultProps} />)

      const stars = screen.getAllByRole('button')
      await user.click(stars[0]) // Click first star

      expect(mockOnChange).toHaveBeenCalledWith(1)
    })

    it('selects maximum rating', async () => {
      const user = userEvent.setup()
      render(<RatingInput {...defaultProps} />)

      const stars = screen.getAllByRole('button')
      await user.click(stars[4]) // Click last star

      expect(mockOnChange).toHaveBeenCalledWith(5)
    })
  })

  describe('Hover Effects', () => {
    it('shows hover state when mouse enters star', () => {
      render(<RatingInput {...defaultProps} />)

      const stars = screen.getAllByRole('button')
      fireEvent.mouseEnter(stars[2]) // Hover third star

      // Third star and all before should show solid icon
      const solidIcons = screen.getAllByTestId('star-solid')
      expect(solidIcons.length).toBeGreaterThanOrEqual(3)
    })

    it('clears hover state when mouse leaves star', () => {
      render(<RatingInput {...defaultProps} value={0} />)

      const stars = screen.getAllByRole('button')
      fireEvent.mouseEnter(stars[2])
      fireEvent.mouseLeave(stars[2])

      // All stars should be outline when no rating and no hover
      const outlineIcons = screen.getAllByTestId('star-outline')
      expect(outlineIcons.length).toBe(5)
    })

    it('shows hover state over current rating', () => {
      render(<RatingInput {...defaultProps} value={2} />)

      const stars = screen.getAllByRole('button')
      fireEvent.mouseEnter(stars[4]) // Hover fifth star (over 2-star rating)

      // All 5 stars should be solid during hover
      const solidIcons = screen.getAllByTestId('star-solid')
      expect(solidIcons.length).toBe(5)
    })

    it('returns to selected rating after hover', () => {
      render(<RatingInput {...defaultProps} value={3} />)

      const stars = screen.getAllByRole('button')

      // Hover over different star
      fireEvent.mouseEnter(stars[4])
      fireEvent.mouseLeave(stars[4])

      // Should show 3 solid stars again
      const solidIcons = screen.getAllByTestId('star-solid')
      expect(solidIcons.length).toBe(3)
    })
  })

  describe('Visual States', () => {
    it('displays solid stars up to selected rating', () => {
      render(<RatingInput {...defaultProps} value={3} />)

      const solidIcons = screen.getAllByTestId('star-solid')
      expect(solidIcons.length).toBe(3)
    })

    it('displays outline stars for unselected ratings', () => {
      render(<RatingInput {...defaultProps} value={2} />)

      const outlineIcons = screen.getAllByTestId('star-outline')
      expect(outlineIcons.length).toBe(3) // Stars 3, 4, 5 are outline
    })

    it('displays all outline stars when rating is 0', () => {
      render(<RatingInput {...defaultProps} value={0} />)

      const outlineIcons = screen.getAllByTestId('star-outline')
      expect(outlineIcons.length).toBe(5)
    })

    it('displays all solid stars when max rating is selected', () => {
      render(<RatingInput {...defaultProps} value={5} />)

      const solidIcons = screen.getAllByTestId('star-solid')
      expect(solidIcons.length).toBe(5)
    })
  })

  describe('External Value Control', () => {
    it('displays initial external value when provided', () => {
      render(<RatingInput {...defaultProps} value={4} />)

      const solidIcons = screen.getAllByTestId('star-solid')
      expect(solidIcons.length).toBe(4)
    })

    it('maintains internal state after initialization', () => {
      const { rerender } = render(<RatingInput {...defaultProps} value={2} />)

      let solidIcons = screen.getAllByTestId('star-solid')
      expect(solidIcons.length).toBe(2)

      // Note: Component uses useState and doesn't sync with external value changes
      // This is the current behavior - internal state is independent after mount
      rerender(<RatingInput {...defaultProps} value={4} />)

      solidIcons = screen.getAllByTestId('star-solid')
      expect(solidIcons.length).toBe(2) // Still shows initial rating
    })

    it('handles undefined external value as 0', () => {
      render(<RatingInput {...defaultProps} value={undefined} />)

      const outlineIcons = screen.getAllByTestId('star-outline')
      expect(outlineIcons.length).toBe(5)
    })

    it('handles null external value as 0', () => {
      render(<RatingInput {...defaultProps} value={null} />)

      const outlineIcons = screen.getAllByTestId('star-outline')
      expect(outlineIcons.length).toBe(5)
    })
  })

  describe('Annotation Creation', () => {
    it('does not call onAnnotation when toName is not provided', async () => {
      const user = userEvent.setup()
      const configWithoutToName = {
        ...defaultConfig,
        props: {
          ...defaultConfig.props,
          toName: undefined,
        },
      }

      render(<RatingInput {...defaultProps} config={configWithoutToName} />)

      const stars = screen.getAllByRole('button')
      await user.click(stars[2])

      expect(mockOnAnnotation).not.toHaveBeenCalled()
    })

    it('creates annotation with correct structure', async () => {
      const user = userEvent.setup()
      render(<RatingInput {...defaultProps} />)

      const stars = screen.getAllByRole('button')
      await user.click(stars[3])

      expect(mockBuildAnnotationResult).toHaveBeenCalledWith(
        'quality',
        'Rating',
        4,
        'text'
      )
    })

    it('creates annotation with 0 when deselecting', async () => {
      const user = userEvent.setup()
      render(<RatingInput {...defaultProps} value={3} />)

      const stars = screen.getAllByRole('button')
      await user.click(stars[2]) // Click same rating to deselect

      expect(mockOnAnnotation).toHaveBeenCalledWith({
        from_name: 'quality',
        to_name: 'text',
        type: 'Rating',
        value: 0,
      })
    })
  })

  describe('Configuration Props', () => {
    it('handles maxRating as string', () => {
      const config = {
        ...defaultConfig,
        props: { ...defaultConfig.props, maxRating: '7' },
      }

      render(<RatingInput {...defaultProps} config={config} />)

      const stars = screen.getAllByRole('button')
      expect(stars).toHaveLength(7)
    })

    it('defaults to 5 stars when maxRating not provided', () => {
      const config = {
        ...defaultConfig,
        props: {
          name: 'quality',
          toName: 'text',
        },
      }

      render(<RatingInput {...defaultProps} config={config} />)

      const stars = screen.getAllByRole('button')
      expect(stars).toHaveLength(5)
    })

    it('handles very low maxRating', () => {
      const config = {
        ...defaultConfig,
        props: { ...defaultConfig.props, maxRating: '1' },
      }

      render(<RatingInput {...defaultProps} config={config} />)

      const stars = screen.getAllByRole('button')
      expect(stars).toHaveLength(1)
    })

    it('handles very high maxRating', () => {
      const config = {
        ...defaultConfig,
        props: { ...defaultConfig.props, maxRating: '10' },
      }

      render(<RatingInput {...defaultProps} config={config} />)

      const stars = screen.getAllByRole('button')
      expect(stars).toHaveLength(10)
    })
  })

  describe('Edge Cases', () => {
    it('handles rapid clicks', async () => {
      const user = userEvent.setup()
      render(<RatingInput {...defaultProps} />)

      const stars = screen.getAllByRole('button')

      await user.click(stars[0])
      await user.click(stars[2])
      await user.click(stars[4])

      expect(mockOnChange).toHaveBeenCalledTimes(3)
      expect(mockOnChange).toHaveBeenLastCalledWith(5)
    })

    it('handles rapid hover changes', () => {
      render(<RatingInput {...defaultProps} />)

      const stars = screen.getAllByRole('button')

      fireEvent.mouseEnter(stars[0])
      fireEvent.mouseEnter(stars[2])
      fireEvent.mouseEnter(stars[4])

      // Should show last hover (5 stars)
      const solidIcons = screen.getAllByTestId('star-solid')
      expect(solidIcons.length).toBe(5)
    })

    it('handles missing name in config', () => {
      const config = {
        type: 'Rating',
        props: {
          toName: 'text',
          label: 'Rate',
        },
        children: [],
      }

      render(<RatingInput {...defaultProps} config={config as any} />)

      expect(screen.getByText('Rate')).toBeInTheDocument()
    })

    it('uses rating as default name when all name sources missing', () => {
      const config = {
        type: 'Rating',
        props: {
          toName: 'text',
        },
        children: [],
      }

      render(<RatingInput {...defaultProps} config={config as any} />)

      expect(screen.getByText('rating')).toBeInTheDocument()
    })
  })

  describe('Accessibility', () => {
    it('renders buttons for star selection', () => {
      render(<RatingInput {...defaultProps} />)

      const stars = screen.getAllByRole('button')
      stars.forEach((star) => {
        expect(star).toHaveAttribute('type', 'button')
      })
    })

    it('stars are keyboard accessible', async () => {
      const user = userEvent.setup()
      render(<RatingInput {...defaultProps} />)

      const stars = screen.getAllByRole('button')

      // Tab to first star
      await user.tab()
      expect(stars[0]).toHaveFocus()
    })

    it('star buttons have proper structure for screen readers', () => {
      render(<RatingInput {...defaultProps} />)

      const stars = screen.getAllByRole('button')
      expect(stars.length).toBe(5)

      stars.forEach((star) => {
        expect(star).toBeInTheDocument()
      })
    })
  })

  describe('Multiple Instances', () => {
    it('handles multiple RatingInput components independently', async () => {
      const user = userEvent.setup()
      const mockOnChange1 = jest.fn()
      const mockOnChange2 = jest.fn()

      const props1 = {
        ...defaultProps,
        config: {
          ...defaultConfig,
          props: { ...defaultConfig.props, name: 'rating1' },
        },
        onChange: mockOnChange1,
      }

      const props2 = {
        ...defaultProps,
        config: {
          ...defaultConfig,
          props: { ...defaultConfig.props, name: 'rating2' },
        },
        onChange: mockOnChange2,
      }

      const { container } = render(
        <div>
          <RatingInput {...props1} />
          <RatingInput {...props2} />
        </div>
      )

      const allStars = screen.getAllByRole('button')

      // Click third star of first rating
      await user.click(allStars[2])
      expect(mockOnChange1).toHaveBeenCalledWith(3)

      // Click second star of second rating
      await user.click(allStars[6]) // 5 stars in first + 2nd star
      expect(mockOnChange2).toHaveBeenCalledWith(2)
    })
  })

  describe('State Management', () => {
    it('maintains internal state when external value not provided', async () => {
      const user = userEvent.setup()
      const { rerender } = render(
        <RatingInput {...defaultProps} value={undefined} />
      )

      const stars = screen.getAllByRole('button')
      await user.click(stars[2])

      expect(mockOnChange).toHaveBeenCalledWith(3)

      // Re-render without changing value
      rerender(<RatingInput {...defaultProps} value={undefined} />)

      // Internal state should show 3 stars
      let solidIcons = screen.getAllByTestId('star-solid')
      expect(solidIcons.length).toBe(3)
    })

    it('initializes with external value', () => {
      render(<RatingInput {...defaultProps} value={2} />)

      const solidIcons = screen.getAllByTestId('star-solid')
      expect(solidIcons.length).toBe(2)
    })

    it('maintains internal state independent of external value changes', () => {
      const { rerender } = render(<RatingInput {...defaultProps} value={2} />)

      let solidIcons = screen.getAllByTestId('star-solid')
      expect(solidIcons.length).toBe(2)

      // External value doesn't sync after mount - this is current behavior
      rerender(<RatingInput {...defaultProps} value={4} />)

      solidIcons = screen.getAllByTestId('star-solid')
      expect(solidIcons.length).toBe(2) // Still shows initial rating
    })

    it('allows user selection to override initial value', async () => {
      const user = userEvent.setup()
      render(<RatingInput {...defaultProps} value={2} />)

      let solidIcons = screen.getAllByTestId('star-solid')
      expect(solidIcons.length).toBe(2)

      const stars = screen.getAllByRole('button')
      await user.click(stars[4]) // Click 5th star

      solidIcons = screen.getAllByTestId('star-solid')
      expect(solidIcons.length).toBe(5)
    })
  })

  describe('Click Behavior', () => {
    it('prevents default button behavior', async () => {
      const user = userEvent.setup()
      render(<RatingInput {...defaultProps} />)

      const stars = screen.getAllByRole('button')

      stars.forEach((star) => {
        expect(star).toHaveAttribute('type', 'button')
      })
    })

    it('handles sequential selections correctly', async () => {
      const user = userEvent.setup()
      render(<RatingInput {...defaultProps} />)

      const stars = screen.getAllByRole('button')

      await user.click(stars[0]) // Select 1
      expect(mockOnChange).toHaveBeenCalledWith(1)

      await user.click(stars[1]) // Select 2
      expect(mockOnChange).toHaveBeenCalledWith(2)

      await user.click(stars[2]) // Select 3
      expect(mockOnChange).toHaveBeenCalledWith(3)
    })
  })
})

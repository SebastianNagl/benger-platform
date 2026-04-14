/**
 * @jest-environment jsdom
 */

import { DisplayContext, TaskTemplateField } from '@/types/taskTemplate'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { RatingField } from '../RatingField'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, varsOrDefault?: any) => {
      const translations: Record<string, any> = require('../../../locales/en/common.json')
      const parts = key.split('.')
      let value: any = translations
      for (const part of parts) {
        if (value && typeof value === 'object' && part in value) {
          value = value[part]
        } else {
          return key
        }
      }
      if (typeof value !== 'string') return key
      if (varsOrDefault && typeof varsOrDefault === 'object') {
        for (const [k, v] of Object.entries(varsOrDefault)) {
          value = value.replace(new RegExp(`\\{${k}\\}`, 'g'), String(v))
        }
      }
      return value
    },
    locale: 'en',
  }),
}))

// Mock Heroicons
jest.mock('@heroicons/react/24/solid', () => ({
  StarIcon: ({ className }: { className?: string }) => (
    <svg className={className} data-testid="star-filled">
      <path />
    </svg>
  ),
}))

jest.mock('@heroicons/react/24/outline', () => ({
  StarIcon: ({ className }: { className?: string }) => (
    <svg className={className} data-testid="star-outline">
      <path />
    </svg>
  ),
  ExclamationCircleIcon: ({ className }: { className?: string }) => (
    <svg className={className} data-testid="exclamation-icon">
      <path />
    </svg>
  ),
}))

describe('RatingField Component', () => {
  const mockOnChange = jest.fn()

  const defaultField: TaskTemplateField = {
    name: 'rating_field',
    type: 'rating',
    source: 'task_data',
    display: {
      annotation: 'editable',
      table: 'column',
      creation: 'editable',
    },
    label: 'Quality Rating',
    description: 'Rate the quality',
    required: false,
    validation: [
      { type: 'min', value: 1 },
      { type: 'max', value: 5 },
    ],
  }

  const defaultProps = {
    field: defaultField,
    value: 0,
    onChange: mockOnChange,
    context: 'annotation' as DisplayContext,
    readonly: false,
    errors: [],
  }

  beforeEach(() => {
    jest.clearAllMocks()
  })

  describe('Basic Rendering', () => {
    it('renders rating field with correct number of stars', () => {
      render(<RatingField {...defaultProps} />)

      const stars = screen.getAllByRole('button')
      expect(stars).toHaveLength(5) // 1 to 5
    })

    it('renders field label', () => {
      render(<RatingField {...defaultProps} />)

      expect(screen.getByText('Quality Rating (Optional)')).toBeInTheDocument()
    })

    it('renders field description', () => {
      render(<RatingField {...defaultProps} />)

      expect(screen.getByText('Rate the quality')).toBeInTheDocument()
    })

    it('renders default 5-star rating', () => {
      const fieldWithoutValidation: TaskTemplateField = {
        ...defaultField,
        validation: undefined,
      }
      render(<RatingField {...defaultProps} field={fieldWithoutValidation} />)

      const stars = screen.getAllByRole('button')
      expect(stars).toHaveLength(5)
    })
  })

  describe('Custom Star Range', () => {
    it('renders custom min and max range', () => {
      const customField = {
        ...defaultField,
        validation: [
          { type: 'min', value: 2 },
          { type: 'max', value: 10 },
        ],
      }
      render(<RatingField {...defaultProps} field={customField} />)

      const stars = screen.getAllByRole('button')
      expect(stars).toHaveLength(9) // 2 to 10 = 9 stars
    })

    it('renders 3-star rating system', () => {
      const customField = {
        ...defaultField,
        validation: [
          { type: 'min', value: 1 },
          { type: 'max', value: 3 },
        ],
      }
      render(<RatingField {...defaultProps} field={customField} />)

      const stars = screen.getAllByRole('button')
      expect(stars).toHaveLength(3)
    })

    it('renders 10-star rating system', () => {
      const customField = {
        ...defaultField,
        validation: [
          { type: 'min', value: 1 },
          { type: 'max', value: 10 },
        ],
      }
      render(<RatingField {...defaultProps} field={customField} />)

      const stars = screen.getAllByRole('button')
      expect(stars).toHaveLength(10)
    })
  })

  describe('Value Display', () => {
    it('displays no filled stars when value is 0', () => {
      render(<RatingField {...defaultProps} value={0} />)

      const filledStars = screen.queryAllByTestId('star-filled')
      expect(filledStars).toHaveLength(0)

      const outlineStars = screen.getAllByTestId('star-outline')
      expect(outlineStars).toHaveLength(5)
    })

    it('displays correct number of filled stars for value', () => {
      render(<RatingField {...defaultProps} value={3} />)

      const filledStars = screen.getAllByTestId('star-filled')
      expect(filledStars).toHaveLength(3)

      const outlineStars = screen.getAllByTestId('star-outline')
      expect(outlineStars).toHaveLength(2)
    })

    it('fills all stars when value is max', () => {
      render(<RatingField {...defaultProps} value={5} />)

      const filledStars = screen.getAllByTestId('star-filled')
      expect(filledStars).toHaveLength(5)

      const outlineStars = screen.queryAllByTestId('star-outline')
      expect(outlineStars).toHaveLength(0)
    })

    it('shows selected rating text', () => {
      render(<RatingField {...defaultProps} value={4} />)

      expect(screen.getByText('Selected: 4 stars')).toBeInTheDocument()
    })

    it('shows singular star text for rating of 1', () => {
      render(<RatingField {...defaultProps} value={1} />)

      expect(screen.getByText('Selected: 1 stars')).toBeInTheDocument()
    })

    it('does not show selected text when value is 0', () => {
      render(<RatingField {...defaultProps} value={0} />)

      expect(screen.queryByText(/Selected:/)).not.toBeInTheDocument()
    })
  })

  describe('User Interaction', () => {
    it('calls onChange when star is clicked', async () => {
      const user = userEvent.setup()
      render(<RatingField {...defaultProps} />)

      const stars = screen.getAllByRole('button')
      await user.click(stars[2]) // Click 3rd star

      expect(mockOnChange).toHaveBeenCalledWith(3)
    })

    it('allows changing rating', async () => {
      const user = userEvent.setup()
      const { rerender } = render(<RatingField {...defaultProps} value={3} />)

      const stars = screen.getAllByRole('button')
      await user.click(stars[4]) // Click 5th star

      expect(mockOnChange).toHaveBeenCalledWith(5)

      rerender(<RatingField {...defaultProps} value={5} />)
      expect(screen.getByText('Selected: 5 stars')).toBeInTheDocument()
    })

    it('allows decreasing rating', async () => {
      const user = userEvent.setup()
      render(<RatingField {...defaultProps} value={5} />)

      const stars = screen.getAllByRole('button')
      await user.click(stars[1]) // Click 2nd star

      expect(mockOnChange).toHaveBeenCalledWith(2)
    })

    it('can set rating to minimum value', async () => {
      const user = userEvent.setup()
      render(<RatingField {...defaultProps} />)

      const stars = screen.getAllByRole('button')
      await user.click(stars[0]) // Click 1st star

      expect(mockOnChange).toHaveBeenCalledWith(1)
    })
  })

  describe('Labels and Tooltips', () => {
    it('shows default tooltip for each star', () => {
      render(<RatingField {...defaultProps} />)

      const stars = screen.getAllByRole('button')
      expect(stars[0]).toHaveAttribute('title', '1 stars')
      expect(stars[1]).toHaveAttribute('title', '2 stars')
      expect(stars[4]).toHaveAttribute('title', '5 stars')
    })

    it('shows custom labels when provided', () => {
      const fieldWithLabels = {
        ...defaultField,
        metadata: {
          labels: ['Poor', 'Fair', 'Good', 'Very Good', 'Excellent'],
        },
      }
      render(<RatingField {...defaultProps} field={fieldWithLabels} />)

      const stars = screen.getAllByRole('button')
      expect(stars[0]).toHaveAttribute('title', 'Poor')
      expect(stars[2]).toHaveAttribute('title', 'Good')
      expect(stars[4]).toHaveAttribute('title', 'Excellent')
    })

    it('displays custom label text when show_labels is enabled', () => {
      const fieldWithLabels = {
        ...defaultField,
        metadata: {
          labels: ['Poor', 'Fair', 'Good', 'Very Good', 'Excellent'],
          show_labels: true,
        },
      }
      render(
        <RatingField {...defaultProps} field={fieldWithLabels} value={3} />
      )

      expect(screen.getByText('Good')).toBeInTheDocument()
    })

    it('falls back to default text when label missing', () => {
      const fieldWithLabels = {
        ...defaultField,
        metadata: {
          labels: ['Poor', 'Fair'], // Only 2 labels for 5 stars
          show_labels: true,
        },
      }
      render(
        <RatingField {...defaultProps} field={fieldWithLabels} value={4} />
      )

      expect(screen.getByText('Selected: 4 stars')).toBeInTheDocument()
    })

    it('shows default text when show_labels is false', () => {
      const fieldWithLabels = {
        ...defaultField,
        metadata: {
          labels: ['Poor', 'Fair', 'Good', 'Very Good', 'Excellent'],
          show_labels: false,
        },
      }
      render(
        <RatingField {...defaultProps} field={fieldWithLabels} value={3} />
      )

      expect(screen.getByText('Selected: 3 stars')).toBeInTheDocument()
      expect(screen.queryByText('Good')).not.toBeInTheDocument()
    })
  })

  describe('Readonly State', () => {
    it('disables all star buttons when readonly', () => {
      render(<RatingField {...defaultProps} readonly={true} value={3} />)

      const stars = screen.getAllByRole('button')
      stars.forEach((star) => {
        expect(star).toBeDisabled()
      })
    })

    it('does not call onChange when readonly', async () => {
      const user = userEvent.setup()
      render(<RatingField {...defaultProps} readonly={true} value={3} />)

      const stars = screen.getAllByRole('button')
      await user.click(stars[4])

      expect(mockOnChange).not.toHaveBeenCalled()
    })

    it('applies cursor-not-allowed class when readonly', () => {
      render(<RatingField {...defaultProps} readonly={true} />)

      const stars = screen.getAllByRole('button')
      stars.forEach((star) => {
        expect(star).toHaveClass('cursor-not-allowed')
      })
    })
  })

  describe('Required Field Handling', () => {
    it('shows required asterisk for required fields', () => {
      const requiredField = { ...defaultField, required: true }
      render(<RatingField {...defaultProps} field={requiredField} />)

      const asterisk = screen.getByText('*')
      expect(asterisk).toBeInTheDocument()
      expect(asterisk).toHaveClass('text-red-500')
    })

    it('shows optional label for non-required fields', () => {
      render(<RatingField {...defaultProps} />)

      expect(screen.getByText('Quality Rating (Optional)')).toBeInTheDocument()
    })
  })

  describe('Error Handling', () => {
    it('displays error message', () => {
      const errors = ['Rating is required']
      render(<RatingField {...defaultProps} errors={errors} />)

      expect(screen.getByText('Rating is required')).toBeInTheDocument()
    })

    it('displays multiple errors', () => {
      const errors = ['Required field', 'Invalid rating']
      render(<RatingField {...defaultProps} errors={errors} />)

      expect(screen.getByText('Required field')).toBeInTheDocument()
      expect(screen.getByText('Invalid rating')).toBeInTheDocument()
    })
  })

  describe('Styling and Visual Feedback', () => {
    it('applies hover scale effect to stars when not readonly', () => {
      render(<RatingField {...defaultProps} />)

      const stars = screen.getAllByRole('button')
      stars.forEach((star) => {
        expect(star).toHaveClass('hover:scale-110')
      })
    })

    it('does not apply hover effects when readonly', () => {
      render(<RatingField {...defaultProps} readonly={true} />)

      const stars = screen.getAllByRole('button')
      stars.forEach((star) => {
        expect(star).not.toHaveClass('hover:scale-110')
      })
    })

    it('applies background to filled stars', () => {
      render(<RatingField {...defaultProps} value={3} />)

      const stars = screen.getAllByRole('button')
      // First 3 stars should have background
      expect(stars[0]).toHaveClass('bg-yellow-100')
      expect(stars[1]).toHaveClass('bg-yellow-100')
      expect(stars[2]).toHaveClass('bg-yellow-100')
      // Last 2 should not
      expect(stars[3]).not.toHaveClass('bg-yellow-100')
      expect(stars[4]).not.toHaveClass('bg-yellow-100')
    })

    it('applies custom className to wrapper', () => {
      render(<RatingField {...defaultProps} className="custom-class" />)

      const wrapper = screen.getAllByRole('button')[0].closest('.field-wrapper')
      expect(wrapper).toHaveClass('custom-class')
    })
  })

  describe('Accessibility', () => {
    it('all stars are keyboard accessible', async () => {
      const user = userEvent.setup()
      render(<RatingField {...defaultProps} />)

      const stars = screen.getAllByRole('button')

      stars[0].focus()
      expect(stars[0]).toHaveFocus()

      await user.tab()
      expect(stars[1]).toHaveFocus()
    })

    it('stars have descriptive titles', () => {
      render(<RatingField {...defaultProps} />)

      const stars = screen.getAllByRole('button')
      stars.forEach((star) => {
        expect(star).toHaveAttribute('title')
      })
    })

    it('button type is set to prevent form submission', () => {
      render(<RatingField {...defaultProps} />)

      const stars = screen.getAllByRole('button')
      stars.forEach((star) => {
        expect(star).toHaveAttribute('type', 'button')
      })
    })
  })

  describe('Edge Cases', () => {
    it('handles null value gracefully', () => {
      render(<RatingField {...defaultProps} value={null} />)

      const filledStars = screen.queryAllByTestId('star-filled')
      expect(filledStars).toHaveLength(0)

      expect(screen.queryByText(/Selected:/)).not.toBeInTheDocument()
    })

    it('handles undefined value gracefully', () => {
      render(<RatingField {...defaultProps} value={undefined} />)

      const filledStars = screen.queryAllByTestId('star-filled')
      expect(filledStars).toHaveLength(0)
    })

    it('handles missing validation gracefully', () => {
      const fieldWithoutValidation: TaskTemplateField = {
        ...defaultField,
        validation: undefined,
      }
      render(<RatingField {...defaultProps} field={fieldWithoutValidation} />)

      const stars = screen.getAllByRole('button')
      expect(stars).toHaveLength(5) // Default 1-5
    })

    it('handles partial validation (only max)', () => {
      const fieldWithPartialValidation = {
        ...defaultField,
        validation: [{ type: 'max', value: 7 }],
      }
      render(
        <RatingField {...defaultProps} field={fieldWithPartialValidation} />
      )

      const stars = screen.getAllByRole('button')
      expect(stars).toHaveLength(7) // min defaults to 1
    })

    it('handles partial validation (only min)', () => {
      const fieldWithPartialValidation = {
        ...defaultField,
        validation: [{ type: 'min', value: 2 }],
      }
      render(
        <RatingField {...defaultProps} field={fieldWithPartialValidation} />
      )

      const stars = screen.getAllByRole('button')
      expect(stars).toHaveLength(4) // max defaults to 5, so 2-5 = 4 stars
    })

    it('handles missing metadata gracefully', () => {
      const fieldWithoutMetadata: TaskTemplateField = {
        ...defaultField,
        metadata: undefined,
      }
      render(
        <RatingField {...defaultProps} field={fieldWithoutMetadata} value={3} />
      )

      expect(screen.getByText('Selected: 3 stars')).toBeInTheDocument()
    })
  })
})

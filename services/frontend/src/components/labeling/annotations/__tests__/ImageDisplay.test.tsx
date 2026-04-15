/**
 * Tests for ImageDisplay component
 * Tests image rendering, data binding, and missing data handling
 */

/**
 * @jest-environment jsdom
 */

import '@testing-library/jest-dom'
import { render, screen } from '@testing-library/react'

// Mock data binding
jest.mock('@/lib/labelConfig/dataBinding', () => ({
  resolveDataBinding: (expression: string, taskData: any) => {
    if (typeof expression !== 'string' || !expression.startsWith('$')) return expression
    const key = expression.substring(1)
    return taskData?.[key]
  },
}))

import ImageDisplay from '../ImageDisplay'

describe('ImageDisplay', () => {
  const defaultProps = {
    config: {
      type: 'Image',
      name: 'image',
      props: {
        name: 'photo',
        value: '$imageUrl',
      },
      children: [],
    },
    taskData: { imageUrl: 'https://example.com/image.png' },
    value: undefined,
    onChange: jest.fn(),
    onAnnotation: jest.fn(),
  }

  describe('Basic Rendering', () => {
    it('renders image with resolved src', () => {
      render(<ImageDisplay {...defaultProps} />)
      const img = screen.getByRole('img')
      expect(img).toHaveAttribute('src', 'https://example.com/image.png')
    })

    it('renders image with alt text from name', () => {
      render(<ImageDisplay {...defaultProps} />)
      const img = screen.getByRole('img')
      expect(img).toHaveAttribute('alt', 'photo')
    })

    it('uses config.name as fallback alt text when props.name is not set', () => {
      const props = {
        ...defaultProps,
        config: {
          ...defaultProps.config,
          props: {
            value: '$imageUrl',
          },
        },
      }
      render(<ImageDisplay {...props} />)
      const img = screen.getByRole('img')
      // Falls back to config.name ('image') when props.name not set
      expect(img).toHaveAttribute('alt', 'image')
    })

    it('uses "Annotation image" as fallback alt when no name at all', () => {
      const props = {
        ...defaultProps,
        config: {
          ...defaultProps.config,
          name: undefined as any,
          props: {
            value: '$imageUrl',
          },
        },
      }
      render(<ImageDisplay {...props} />)
      const img = screen.getByRole('img')
      expect(img).toHaveAttribute('alt', 'Annotation image')
    })

    it('renders label when name is provided', () => {
      render(<ImageDisplay {...defaultProps} />)
      expect(screen.getByText('photo')).toBeInTheDocument()
    })
  })

  describe('Missing Image', () => {
    it('shows fallback message when image URL is undefined', () => {
      const props = {
        ...defaultProps,
        taskData: {},
      }
      render(<ImageDisplay {...props} />)
      expect(screen.getByText(/No image data for field/)).toBeInTheDocument()
    })

    it('shows fallback message when image URL is empty string', () => {
      const props = {
        ...defaultProps,
        taskData: { imageUrl: '' },
      }
      render(<ImageDisplay {...props} />)
      expect(screen.getByText(/No image data for field/)).toBeInTheDocument()
    })
  })

  describe('Dimensions', () => {
    it('applies width and height when provided', () => {
      const props = {
        ...defaultProps,
        config: {
          ...defaultProps.config,
          props: {
            ...defaultProps.config.props,
            width: '400',
            height: '300',
          },
        },
      }
      render(<ImageDisplay {...props} />)
      const img = screen.getByRole('img')
      expect(img).toHaveAttribute('width', '400')
      expect(img).toHaveAttribute('height', '300')
    })

    it('renders without explicit width and height', () => {
      render(<ImageDisplay {...defaultProps} />)
      const img = screen.getByRole('img')
      // Should not have width/height attributes when not provided
      expect(img).not.toHaveAttribute('width')
      expect(img).not.toHaveAttribute('height')
    })
  })

  describe('Container Styling', () => {
    it('has image-display container class', () => {
      const { container } = render(<ImageDisplay {...defaultProps} />)
      expect(container.querySelector('.image-display')).not.toBeNull()
    })

    it('image has styling classes', () => {
      render(<ImageDisplay {...defaultProps} />)
      const img = screen.getByRole('img')
      expect(img).toHaveClass('max-w-full')
      expect(img).toHaveClass('rounded-lg')
    })
  })
})

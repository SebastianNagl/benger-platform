/**
 * Unit tests for ImageDisplay component
 */

/**
 * @jest-environment jsdom
 */

import '@testing-library/jest-dom'
import { render, screen } from '@testing-library/react'
import ImageDisplay from '../../../components/labeling/annotations/ImageDisplay'

jest.mock('../../../lib/labelConfig/dataBinding', () => ({
  resolveDataBinding: jest.fn((value, taskData) => {
    if (typeof value !== 'string' || !value.startsWith('$')) {
      return value
    }
    const path = value.substring(1)
    const parts = path.split('.')
    let current = taskData
    for (const part of parts) {
      if (current == null || typeof current !== 'object') {
        return undefined
      }
      current = current[part]
    }
    if (current === undefined && taskData.data) {
      current = taskData.data
      for (const part of parts) {
        if (current == null || typeof current !== 'object') {
          return undefined
        }
        current = current[part]
      }
    }
    return current
  }),
}))

describe('ImageDisplay', () => {
  const mockConfig = {
    type: 'ImageDisplay',
    name: 'image-display',
    props: {
      value: '$image',
      name: 'Image Field',
      width: '800',
      height: '600',
    },
  }

  const mockTaskData = {
    image: 'https://example.com/image.jpg',
  }

  describe('Content Rendering', () => {
    it('should render image with src', () => {
      render(<ImageDisplay config={mockConfig} taskData={mockTaskData} />)

      const img = screen.getByRole('img')
      expect(img).toHaveAttribute('src', 'https://example.com/image.jpg')
    })

    it('should render label when name is provided', () => {
      render(<ImageDisplay config={mockConfig} taskData={mockTaskData} />)

      expect(screen.getByText('Image Field')).toBeInTheDocument()
    })

    it('should render with default name when name prop is not provided', () => {
      const config = {
        ...mockConfig,
        props: { ...mockConfig.props, name: undefined },
      }
      render(<ImageDisplay config={config} taskData={mockTaskData} />)

      expect(screen.getByText('image-display')).toBeInTheDocument()
    })

    it('should not render label when name is empty', () => {
      const config = {
        type: 'ImageDisplay',
        name: undefined,
        props: { ...mockConfig.props, name: undefined },
      }
      const { container } = render(
        <ImageDisplay config={config} taskData={mockTaskData} />
      )

      const label = container.querySelector('label')
      expect(label).not.toBeInTheDocument()
    })

    it('should render image with alt text from name', () => {
      render(<ImageDisplay config={mockConfig} taskData={mockTaskData} />)

      const img = screen.getByAltText('Image Field')
      expect(img).toBeInTheDocument()
    })

    it('should render image with default alt text when name is not provided', () => {
      const config = {
        type: 'ImageDisplay',
        name: undefined,
        props: { value: '$image' },
      }
      render(<ImageDisplay config={config} taskData={mockTaskData} />)

      const img = screen.getByAltText('Annotation image')
      expect(img).toBeInTheDocument()
    })
  })

  describe('Image Dimensions', () => {
    it('should apply width attribute', () => {
      render(<ImageDisplay config={mockConfig} taskData={mockTaskData} />)

      const img = screen.getByRole('img')
      expect(img).toHaveAttribute('width', '800')
    })

    it('should apply height attribute', () => {
      render(<ImageDisplay config={mockConfig} taskData={mockTaskData} />)

      const img = screen.getByRole('img')
      expect(img).toHaveAttribute('height', '600')
    })

    it('should render without width when not provided', () => {
      const config = {
        ...mockConfig,
        props: { ...mockConfig.props, width: undefined },
      }
      render(<ImageDisplay config={config} taskData={mockTaskData} />)

      const img = screen.getByRole('img')
      expect(img).not.toHaveAttribute('width')
    })

    it('should render without height when not provided', () => {
      const config = {
        ...mockConfig,
        props: { ...mockConfig.props, height: undefined },
      }
      render(<ImageDisplay config={config} taskData={mockTaskData} />)

      const img = screen.getByRole('img')
      expect(img).not.toHaveAttribute('height')
    })

    it('should handle numeric dimensions', () => {
      const config = {
        ...mockConfig,
        props: { ...mockConfig.props, width: 1024, height: 768 },
      }
      render(<ImageDisplay config={config} taskData={mockTaskData} />)

      const img = screen.getByRole('img')
      expect(img).toHaveAttribute('width', '1024')
      expect(img).toHaveAttribute('height', '768')
    })
  })

  describe('Error Handling', () => {
    it('should display error message when image src is undefined', () => {
      const taskData = {}
      render(<ImageDisplay config={mockConfig} taskData={taskData} />)

      expect(
        screen.getByText(/No image data for field: \$image/)
      ).toBeInTheDocument()
    })

    it('should display error message when image src is null', () => {
      const taskData = { image: null }
      render(<ImageDisplay config={mockConfig} taskData={taskData} />)

      expect(
        screen.getByText(/No image data for field: \$image/)
      ).toBeInTheDocument()
    })

    it('should display error message when image src is empty string', () => {
      const taskData = { image: '' }
      render(<ImageDisplay config={mockConfig} taskData={taskData} />)

      expect(
        screen.getByText(/No image data for field: \$image/)
      ).toBeInTheDocument()
    })

    it('should display error with field name from valueExpression', () => {
      const config = {
        ...mockConfig,
        props: { ...mockConfig.props, value: '$customImage' },
      }
      const taskData = {}
      render(<ImageDisplay config={config} taskData={taskData} />)

      expect(
        screen.getByText('No image data for field: $customImage')
      ).toBeInTheDocument()
    })

    it('should apply error styling when data is missing', () => {
      const taskData = {}
      const { container } = render(
        <ImageDisplay config={mockConfig} taskData={taskData} />
      )

      const errorElement = container.querySelector('.italic.text-zinc-500')
      expect(errorElement).toBeInTheDocument()
    })
  })

  describe('Data Binding', () => {
    it('should resolve nested data paths', () => {
      const config = {
        ...mockConfig,
        props: { ...mockConfig.props, value: '$data.imageUrl' },
      }
      const taskData = {
        data: { imageUrl: 'https://example.com/nested.jpg' },
      }
      render(<ImageDisplay config={config} taskData={taskData} />)

      const img = screen.getByRole('img')
      expect(img).toHaveAttribute('src', 'https://example.com/nested.jpg')
    })

    it('should resolve data from taskData.data object', () => {
      const config = {
        ...mockConfig,
        props: { ...mockConfig.props, value: '$image' },
      }
      const taskData = {
        data: { image: 'https://example.com/data-image.jpg' },
      }
      render(<ImageDisplay config={config} taskData={taskData} />)

      const img = screen.getByRole('img')
      expect(img).toHaveAttribute('src', 'https://example.com/data-image.jpg')
    })

    it('should handle deeply nested paths', () => {
      const config = {
        ...mockConfig,
        props: { ...mockConfig.props, value: '$media.images.primary' },
      }
      const taskData = {
        media: { images: { primary: 'https://example.com/deep.jpg' } },
      }
      render(<ImageDisplay config={config} taskData={taskData} />)

      const img = screen.getByRole('img')
      expect(img).toHaveAttribute('src', 'https://example.com/deep.jpg')
    })
  })

  describe('Image Sources', () => {
    it('should render with HTTP URL', () => {
      const taskData = { image: 'http://example.com/image.jpg' }
      render(<ImageDisplay config={mockConfig} taskData={taskData} />)

      const img = screen.getByRole('img')
      expect(img).toHaveAttribute('src', 'http://example.com/image.jpg')
    })

    it('should render with HTTPS URL', () => {
      const taskData = { image: 'https://example.com/image.jpg' }
      render(<ImageDisplay config={mockConfig} taskData={taskData} />)

      const img = screen.getByRole('img')
      expect(img).toHaveAttribute('src', 'https://example.com/image.jpg')
    })

    it('should render with data URI', () => {
      const taskData = {
        image:
          'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==',
      }
      render(<ImageDisplay config={mockConfig} taskData={taskData} />)

      const img = screen.getByRole('img')
      expect(img).toHaveAttribute(
        'src',
        expect.stringContaining('data:image/png;base64')
      )
    })

    it('should render with relative path', () => {
      const taskData = { image: '/images/local.jpg' }
      render(<ImageDisplay config={mockConfig} taskData={taskData} />)

      const img = screen.getByRole('img')
      expect(img).toHaveAttribute('src', '/images/local.jpg')
    })

    it('should render with blob URL', () => {
      const taskData = { image: 'blob:https://example.com/uuid' }
      render(<ImageDisplay config={mockConfig} taskData={taskData} />)

      const img = screen.getByRole('img')
      expect(img).toHaveAttribute('src', 'blob:https://example.com/uuid')
    })
  })

  describe('Styling and Layout', () => {
    it('should apply wrapper class', () => {
      const { container } = render(
        <ImageDisplay config={mockConfig} taskData={mockTaskData} />
      )

      const wrapper = container.querySelector('.image-display')
      expect(wrapper).toBeInTheDocument()
    })

    it('should apply label styling', () => {
      const { container } = render(
        <ImageDisplay config={mockConfig} taskData={mockTaskData} />
      )

      const label = container.querySelector('label')
      expect(label).toHaveClass('mb-2', 'block', 'text-sm', 'font-medium')
    })

    it('should apply image styling classes', () => {
      render(<ImageDisplay config={mockConfig} taskData={mockTaskData} />)

      const img = screen.getByRole('img')
      expect(img).toHaveClass('h-auto', 'max-w-full', 'rounded-lg', 'border')
    })

    it('should apply dark mode border class', () => {
      render(<ImageDisplay config={mockConfig} taskData={mockTaskData} />)

      const img = screen.getByRole('img')
      expect(img).toHaveClass('dark:border-zinc-700')
    })

    it('should apply light mode border class', () => {
      render(<ImageDisplay config={mockConfig} taskData={mockTaskData} />)

      const img = screen.getByRole('img')
      expect(img).toHaveClass('border-zinc-200')
    })
  })

  describe('Responsive Behavior', () => {
    it('should have max-w-full for responsive width', () => {
      render(<ImageDisplay config={mockConfig} taskData={mockTaskData} />)

      const img = screen.getByRole('img')
      expect(img).toHaveClass('max-w-full')
    })

    it('should have h-auto for maintaining aspect ratio', () => {
      render(<ImageDisplay config={mockConfig} taskData={mockTaskData} />)

      const img = screen.getByRole('img')
      expect(img).toHaveClass('h-auto')
    })

    it('should maintain aspect ratio with width only', () => {
      const config = {
        ...mockConfig,
        props: { ...mockConfig.props, width: 800, height: undefined },
      }
      render(<ImageDisplay config={config} taskData={mockTaskData} />)

      const img = screen.getByRole('img')
      expect(img).toHaveAttribute('width', '800')
      expect(img).toHaveClass('h-auto')
    })

    it('should maintain aspect ratio with height only', () => {
      const config = {
        ...mockConfig,
        props: { ...mockConfig.props, width: undefined, height: 600 },
      }
      render(<ImageDisplay config={config} taskData={mockTaskData} />)

      const img = screen.getByRole('img')
      expect(img).toHaveAttribute('height', '600')
      expect(img).toHaveClass('h-auto')
    })
  })

  describe('Edge Cases', () => {
    it('should handle minimal config', () => {
      const config = {
        type: 'ImageDisplay',
        name: 'img',
        props: { value: '$image' },
      }
      render(<ImageDisplay config={config} taskData={mockTaskData} />)

      expect(screen.getByRole('img')).toBeInTheDocument()
    })

    it('should handle special characters in image URL', () => {
      const taskData = {
        image:
          'https://example.com/image%20with%20spaces.jpg?param=value&other=test',
      }
      render(<ImageDisplay config={mockConfig} taskData={taskData} />)

      const img = screen.getByRole('img')
      expect(img).toHaveAttribute(
        'src',
        'https://example.com/image%20with%20spaces.jpg?param=value&other=test'
      )
    })

    it('should handle very long URLs', () => {
      const longUrl = 'https://example.com/' + 'a'.repeat(1000) + '.jpg'
      const taskData = { image: longUrl }
      render(<ImageDisplay config={mockConfig} taskData={taskData} />)

      const img = screen.getByRole('img')
      expect(img).toHaveAttribute('src', longUrl)
    })

    it('should handle different image formats in URL', () => {
      const formats = ['jpg', 'png', 'gif', 'webp', 'svg', 'bmp']
      formats.forEach((format) => {
        const taskData = { image: `https://example.com/image.${format}` }
        const { unmount } = render(
          <ImageDisplay config={mockConfig} taskData={taskData} />
        )

        const img = screen.getByRole('img')
        expect(img).toHaveAttribute(
          'src',
          `https://example.com/image.${format}`
        )
        unmount()
      })
    })

    it('should handle zero dimensions', () => {
      const config = {
        ...mockConfig,
        props: { ...mockConfig.props, width: 0, height: 0 },
      }
      render(<ImageDisplay config={config} taskData={mockTaskData} />)

      const img = screen.getByRole('img')
      expect(img).toHaveAttribute('width', '0')
      expect(img).toHaveAttribute('height', '0')
    })

    it('should handle very large dimensions', () => {
      const config = {
        ...mockConfig,
        props: { ...mockConfig.props, width: 10000, height: 10000 },
      }
      render(<ImageDisplay config={config} taskData={mockTaskData} />)

      const img = screen.getByRole('img')
      expect(img).toHaveAttribute('width', '10000')
      expect(img).toHaveAttribute('height', '10000')
    })
  })

  describe('Accessibility', () => {
    it('should have proper image role', () => {
      render(<ImageDisplay config={mockConfig} taskData={mockTaskData} />)

      expect(screen.getByRole('img')).toBeInTheDocument()
    })

    it('should have alt text for screen readers', () => {
      render(<ImageDisplay config={mockConfig} taskData={mockTaskData} />)

      const img = screen.getByAltText('Image Field')
      expect(img).toBeInTheDocument()
    })

    it('should associate label with image semantically', () => {
      const { container } = render(
        <ImageDisplay config={mockConfig} taskData={mockTaskData} />
      )

      const label = container.querySelector('label')
      expect(label).toBeInTheDocument()
      const img = screen.getByRole('img')
      expect(img).toBeInTheDocument()
    })
  })
})

/**
 * Unit tests for TextDisplay component
 */

/**
 * @jest-environment jsdom
 */

import '@testing-library/jest-dom'
import { render, screen } from '@testing-library/react'
import TextDisplay from '../../../components/labeling/annotations/TextDisplay'

// Mock I18n context
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

describe('TextDisplay', () => {
  const mockConfig = {
    type: 'TextDisplay',
    name: 'text-display',
    props: {
      value: '$text',
      name: 'Text Field',
      showLabel: 'true',
      className: '',
      style: {},
    },
  }

  const mockTaskData = {
    text: 'Sample text content',
  }

  describe('Content Rendering', () => {
    it('should render text content', () => {
      render(<TextDisplay config={mockConfig} taskData={mockTaskData} />)

      expect(screen.getByText('Sample text content')).toBeInTheDocument()
    })

    it('should render label when showLabel is true', () => {
      render(<TextDisplay config={mockConfig} taskData={mockTaskData} />)

      expect(screen.getByText('Text Field')).toBeInTheDocument()
    })

    it('should not render label when showLabel is false', () => {
      const config = {
        ...mockConfig,
        props: { ...mockConfig.props, showLabel: 'false' },
      }
      render(<TextDisplay config={config} taskData={mockTaskData} />)

      expect(screen.queryByText('Text Field')).not.toBeInTheDocument()
    })

    it('should render with default name when name is not provided', () => {
      const config = {
        ...mockConfig,
        props: { ...mockConfig.props, name: undefined },
      }
      render(<TextDisplay config={config} taskData={mockTaskData} />)

      expect(screen.getByText('text-display')).toBeInTheDocument()
    })

    it('should render without label when both name and config.name are missing', () => {
      const config = {
        type: 'TextDisplay',
        name: undefined,
        props: { ...mockConfig.props, name: undefined },
      }
      const { container } = render(
        <TextDisplay config={config} taskData={mockTaskData} />
      )

      const label = container.querySelector('label')
      expect(label).not.toBeInTheDocument()
    })

    it('should render multiline text with whitespace preserved', () => {
      const taskData = {
        text: 'Line 1\nLine 2\nLine 3',
      }
      const { container } = render(
        <TextDisplay config={mockConfig} taskData={taskData} />
      )

      const textElement = container.querySelector('.whitespace-pre-wrap')
      expect(textElement).toBeInTheDocument()
      expect(textElement?.textContent).toContain('Line 1')
      expect(textElement?.textContent).toContain('Line 2')
      expect(textElement?.textContent).toContain('Line 3')
    })

    it('should render long text without truncation', () => {
      const longText = 'a'.repeat(1000)
      const taskData = { text: longText }
      render(<TextDisplay config={mockConfig} taskData={taskData} />)

      expect(screen.getByText(longText)).toBeInTheDocument()
    })
  })

  describe('Data Types', () => {
    it('should render string values', () => {
      const taskData = { text: 'Simple string' }
      render(<TextDisplay config={mockConfig} taskData={taskData} />)

      expect(screen.getByText('Simple string')).toBeInTheDocument()
    })

    it('should render number values as string', () => {
      const taskData = { text: 42 }
      render(<TextDisplay config={mockConfig} taskData={taskData} />)

      expect(screen.getByText('42')).toBeInTheDocument()
    })

    it('should render boolean values as string', () => {
      const taskData = { text: true }
      render(<TextDisplay config={mockConfig} taskData={taskData} />)

      expect(screen.getByText('true')).toBeInTheDocument()
    })

    it('should render object values as formatted JSON', () => {
      const taskData = {
        text: { key: 'value', nested: { data: 'test' } },
      }
      const { container } = render(
        <TextDisplay config={mockConfig} taskData={taskData} />
      )

      const pre = container.querySelector('pre')
      expect(pre).toBeInTheDocument()
      expect(pre).toHaveTextContent('"key": "value"')
      expect(pre).toHaveTextContent('"nested"')
    })

    it('should render array values as formatted JSON', () => {
      const taskData = {
        text: ['item1', 'item2', 'item3'],
      }
      const { container } = render(
        <TextDisplay config={mockConfig} taskData={taskData} />
      )

      const pre = container.querySelector('pre')
      expect(pre).toBeInTheDocument()
      expect(pre).toHaveTextContent('item1')
      expect(pre).toHaveTextContent('item2')
    })

    it('should handle empty string', () => {
      const taskData = { text: '' }
      const { container } = render(
        <TextDisplay config={mockConfig} taskData={taskData} />
      )

      const textElement = container.querySelector('.whitespace-pre-wrap')
      expect(textElement).toHaveTextContent('')
    })
  })

  describe('Error Handling', () => {
    it('should display error message when value is undefined', () => {
      const taskData = {}
      render(<TextDisplay config={mockConfig} taskData={taskData} />)

      expect(screen.getByText(/No data for field: \$text/)).toBeInTheDocument()
    })

    it('should display error message when value is null', () => {
      const taskData = { text: null }
      render(<TextDisplay config={mockConfig} taskData={taskData} />)

      expect(screen.getByText(/No data for field: \$text/)).toBeInTheDocument()
    })

    it('should display error with field name from valueExpression', () => {
      const config = {
        ...mockConfig,
        props: { ...mockConfig.props, value: '$customField' },
      }
      const taskData = {}
      render(<TextDisplay config={config} taskData={taskData} />)

      expect(
        screen.getByText('No data for field: $customField')
      ).toBeInTheDocument()
    })

    it('should apply error styling when data is missing', () => {
      const taskData = {}
      const { container } = render(
        <TextDisplay config={mockConfig} taskData={taskData} />
      )

      const errorElement = container.querySelector('.italic.text-zinc-500')
      expect(errorElement).toBeInTheDocument()
    })
  })

  describe('Data Binding', () => {
    it('should resolve nested data paths', () => {
      const config = {
        ...mockConfig,
        props: { ...mockConfig.props, value: '$user.name' },
      }
      const taskData = {
        user: { name: 'John Doe' },
      }
      render(<TextDisplay config={config} taskData={taskData} />)

      expect(screen.getByText('John Doe')).toBeInTheDocument()
    })

    it('should resolve data from taskData.data object', () => {
      const config = {
        ...mockConfig,
        props: { ...mockConfig.props, value: '$text' },
      }
      const taskData = {
        data: { text: 'Nested data content' },
      }
      render(<TextDisplay config={config} taskData={taskData} />)

      expect(screen.getByText('Nested data content')).toBeInTheDocument()
    })

    it('should handle deeply nested paths', () => {
      const config = {
        ...mockConfig,
        props: { ...mockConfig.props, value: '$level1.level2.level3' },
      }
      const taskData = {
        level1: { level2: { level3: 'Deep value' } },
      }
      render(<TextDisplay config={config} taskData={taskData} />)

      expect(screen.getByText('Deep value')).toBeInTheDocument()
    })

    it('should return undefined for invalid nested paths', () => {
      const config = {
        ...mockConfig,
        props: { ...mockConfig.props, value: '$invalid.path.here' },
      }
      const taskData = { invalid: 'string' }
      render(<TextDisplay config={config} taskData={taskData} />)

      expect(screen.getByText(/No data for field:/)).toBeInTheDocument()
    })
  })

  describe('Styling and Layout', () => {
    it('should apply custom className', () => {
      const config = {
        ...mockConfig,
        props: { ...mockConfig.props, className: 'custom-class' },
      }
      const { container } = render(
        <TextDisplay config={config} taskData={mockTaskData} />
      )

      const wrapper = container.querySelector('.text-display.custom-class')
      expect(wrapper).toBeInTheDocument()
    })

    it('should apply custom styles', () => {
      const config = {
        ...mockConfig,
        props: {
          ...mockConfig.props,
          style: { color: 'red', fontSize: '20px' },
        },
      }
      const { container } = render(
        <TextDisplay config={config} taskData={mockTaskData} />
      )

      const wrapper = container.querySelector('.text-display') as HTMLElement
      expect(wrapper).toBeInTheDocument()
      expect(wrapper.style.color).toBe('red')
      expect(wrapper.style.fontSize).toBe('20px')
    })

    it('should apply prose styling to content', () => {
      const { container } = render(
        <TextDisplay config={mockConfig} taskData={mockTaskData} />
      )

      const prose = container.querySelector(
        '.prose.prose-sm.max-w-none.dark\\:prose-invert'
      )
      expect(prose).toBeInTheDocument()
    })

    it('should apply label styling', () => {
      const { container } = render(
        <TextDisplay config={mockConfig} taskData={mockTaskData} />
      )

      const label = container.querySelector('label')
      expect(label).toHaveClass('mb-1', 'block', 'text-sm', 'font-medium')
    })

    it('should apply object rendering styles', () => {
      const taskData = { text: { key: 'value' } }
      const { container } = render(
        <TextDisplay config={mockConfig} taskData={taskData} />
      )

      const pre = container.querySelector('pre')
      expect(pre).toHaveClass('overflow-x-auto', 'rounded-md', 'bg-zinc-100')
    })
  })

  describe('Responsive Behavior', () => {
    it('should have max-w-none for full width prose', () => {
      const { container } = render(
        <TextDisplay config={mockConfig} taskData={mockTaskData} />
      )

      const prose = container.querySelector('.max-w-none')
      expect(prose).toBeInTheDocument()
    })

    it('should handle overflow with overflow-x-auto for JSON', () => {
      const taskData = {
        text: { very: 'long', object: 'data', with: 'many', keys: 'here' },
      }
      const { container } = render(
        <TextDisplay config={mockConfig} taskData={taskData} />
      )

      const pre = container.querySelector('.overflow-x-auto')
      expect(pre).toBeInTheDocument()
    })

    it('should preserve whitespace for multiline content', () => {
      const taskData = { text: 'Line 1\n\nLine 2\n\n\nLine 3' }
      const { container } = render(
        <TextDisplay config={mockConfig} taskData={taskData} />
      )

      const p = container.querySelector('.whitespace-pre-wrap')
      expect(p).toBeInTheDocument()
    })
  })

  describe('Edge Cases', () => {
    it('should handle empty config props', () => {
      const config = {
        type: 'TextDisplay',
        name: 'display',
        props: { value: '$text' },
      }
      const { container } = render(
        <TextDisplay config={config} taskData={mockTaskData} />
      )

      expect(container.querySelector('.text-display')).toBeInTheDocument()
    })

    it('should handle zero as valid value', () => {
      const taskData = { text: 0 }
      render(<TextDisplay config={mockConfig} taskData={taskData} />)

      expect(screen.getByText('0')).toBeInTheDocument()
    })

    it('should handle false as valid value', () => {
      const taskData = { text: false }
      render(<TextDisplay config={mockConfig} taskData={taskData} />)

      expect(screen.getByText('false')).toBeInTheDocument()
    })

    it('should handle special characters in text', () => {
      const taskData = { text: '<>&"\'`' }
      render(<TextDisplay config={mockConfig} taskData={taskData} />)

      expect(screen.getByText('<>&"\'`')).toBeInTheDocument()
    })

    it('should handle unicode characters', () => {
      const taskData = { text: '你好世界 🌍 Привет мир' }
      render(<TextDisplay config={mockConfig} taskData={taskData} />)

      expect(screen.getByText('你好世界 🌍 Привет мир')).toBeInTheDocument()
    })

    it('should handle very deeply nested objects', () => {
      const deepObject = {
        level1: { level2: { level3: { level4: { level5: 'deep' } } } },
      }
      const taskData = { text: deepObject }
      const { container } = render(
        <TextDisplay config={mockConfig} taskData={taskData} />
      )

      const pre = container.querySelector('pre')
      expect(pre).toHaveTextContent('level5')
      expect(pre).toHaveTextContent('deep')
    })

    it('should handle circular references by throwing error', () => {
      const circular: any = { a: 'test' }
      circular.self = circular
      const taskData = { text: circular }

      // Suppress console.error for this test
      const consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation()

      expect(() => {
        render(<TextDisplay config={mockConfig} taskData={taskData} />)
      }).toThrow()

      consoleErrorSpy.mockRestore()
    })
  })
})

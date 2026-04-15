/**
 * @jest-environment jsdom
 */

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { JsonViewer } from '../JsonViewer'

// Mock Heroicons
jest.mock('@heroicons/react/24/outline', () => ({
  ChevronDownIcon: (props: any) => (
    <svg {...props} data-testid="chevron-down">
      <path />
    </svg>
  ),
  ChevronRightIcon: (props: any) => (
    <svg {...props} data-testid="chevron-right">
      <path />
    </svg>
  ),
}))

describe('JsonViewer Component', () => {
  describe('Basic Rendering', () => {
    it('renders container with correct styling', () => {
      const { container } = render(<JsonViewer data={{}} />)

      const viewer = container.querySelector('.font-mono')
      expect(viewer).toBeInTheDocument()
      expect(viewer).toHaveClass(
        'max-h-[600px]',
        'overflow-auto',
        'rounded-lg',
        'bg-gray-50',
        'dark:bg-gray-900'
      )
    })

    it('renders with scrollable container', () => {
      const { container } = render(<JsonViewer data={{}} />)

      const viewer = container.querySelector('.overflow-auto')
      expect(viewer).toBeInTheDocument()
    })
  })

  describe('Primitive Values - Null and Undefined', () => {
    it('renders null value', () => {
      render(<JsonViewer data={null} />)

      const nullValue = screen.getByText('null')
      expect(nullValue).toBeInTheDocument()
      expect(nullValue).toHaveClass('text-orange-600')
    })

    it('renders undefined value', () => {
      render(<JsonViewer data={undefined} />)

      const undefinedValue = screen.getByText('undefined')
      expect(undefinedValue).toBeInTheDocument()
      expect(undefinedValue).toHaveClass('text-gray-500')
    })
  })

  describe('Primitive Values - String', () => {
    it('renders string value with quotes', () => {
      render(<JsonViewer data="hello world" />)

      expect(screen.getByText('"hello world"')).toBeInTheDocument()
    })

    it('applies green color to strings', () => {
      render(<JsonViewer data="test" />)

      const stringValue = screen.getByText('"test"')
      expect(stringValue).toHaveClass('text-green-600')
    })

    it('handles empty string', () => {
      render(<JsonViewer data="" />)

      expect(screen.getByText('""')).toBeInTheDocument()
    })

    it('handles special characters in strings', () => {
      const specialChars = '<>&"\''
      render(<JsonViewer data={specialChars} />)

      expect(screen.getByText(`"${specialChars}"`)).toBeInTheDocument()
    })
  })

  describe('Primitive Values - Number', () => {
    it('renders integer', () => {
      render(<JsonViewer data={42} />)

      const numberValue = screen.getByText('42')
      expect(numberValue).toBeInTheDocument()
      expect(numberValue).toHaveClass('text-blue-600')
    })

    it('renders float', () => {
      render(<JsonViewer data={3.14} />)

      expect(screen.getByText('3.14')).toBeInTheDocument()
    })

    it('renders zero', () => {
      render(<JsonViewer data={0} />)

      expect(screen.getByText('0')).toBeInTheDocument()
    })

    it('renders negative number', () => {
      render(<JsonViewer data={-100} />)

      expect(screen.getByText('-100')).toBeInTheDocument()
    })
  })

  describe('Primitive Values - Boolean', () => {
    it('renders true', () => {
      render(<JsonViewer data={true} />)

      const boolValue = screen.getByText('true')
      expect(boolValue).toBeInTheDocument()
      expect(boolValue).toHaveClass('text-purple-600')
    })

    it('renders false', () => {
      render(<JsonViewer data={false} />)

      const boolValue = screen.getByText('false')
      expect(boolValue).toBeInTheDocument()
      expect(boolValue).toHaveClass('text-purple-600')
    })
  })

  describe('Empty Structures', () => {
    it('renders empty object', () => {
      render(<JsonViewer data={{}} />)

      expect(screen.getByText('{}')).toBeInTheDocument()
    })

    it('renders empty array', () => {
      render(<JsonViewer data={[]} />)

      expect(screen.getByText('[]')).toBeInTheDocument()
    })
  })

  describe('Simple Arrays', () => {
    it('renders simple array inline', () => {
      render(<JsonViewer data={[1, 2, 3]} />)

      expect(screen.getByText('1')).toBeInTheDocument()
      expect(screen.getByText('2')).toBeInTheDocument()
      expect(screen.getByText('3')).toBeInTheDocument()
    })

    it('renders array of strings', () => {
      render(<JsonViewer data={['a', 'b', 'c']} />)

      expect(screen.getByText('"a"')).toBeInTheDocument()
      expect(screen.getByText('"b"')).toBeInTheDocument()
      expect(screen.getByText('"c"')).toBeInTheDocument()
    })

    it('renders mixed primitive array', () => {
      render(<JsonViewer data={[1, 'text', true, null]} />)

      expect(screen.getByText('1')).toBeInTheDocument()
      expect(screen.getByText('"text"')).toBeInTheDocument()
      expect(screen.getByText('true')).toBeInTheDocument()
      expect(screen.getByText('null')).toBeInTheDocument()
    })
  })

  describe('Complex Arrays', () => {
    it('renders complex array with expand button', () => {
      render(<JsonViewer data={[{ a: 1 }, { b: 2 }]} />)

      expect(screen.getByText('Array[2]')).toBeInTheDocument()
      expect(screen.getByTestId('chevron-right')).toBeInTheDocument()
    })

    it('expands complex array on click', async () => {
      const user = userEvent.setup()
      render(<JsonViewer data={[{ name: 'John' }, { name: 'Jane' }]} />)

      const expandButton = screen.getByText('Array[2]')
      await user.click(expandButton)

      // After expanding array, objects inside are collapsed
      expect(screen.getByText('0:')).toBeInTheDocument()
      expect(screen.getByText('1:')).toBeInTheDocument()
      const objects = screen.getAllByText('Object{1}')
      expect(objects).toHaveLength(2) // Two objects in array
    })

    it('can toggle array expansion', async () => {
      const user = userEvent.setup()
      render(<JsonViewer data={[{ test: 'value' }]} />)

      const expandButton = screen.getByText('Array[1]')

      // Initially collapsed - no indices shown
      expect(screen.queryByText('0:')).not.toBeInTheDocument()

      // Expand
      await user.click(expandButton)
      expect(screen.getByText('0:')).toBeInTheDocument()

      // Collapse again
      await user.click(expandButton)
      expect(screen.queryByText('0:')).not.toBeInTheDocument()
    })

    it('shows array indices', async () => {
      const user = userEvent.setup()
      render(<JsonViewer data={[{ a: 1 }, { b: 2 }]} />)

      const expandButton = screen.getByText('Array[2]')
      await user.click(expandButton)

      expect(screen.getByText('0:')).toBeInTheDocument()
      expect(screen.getByText('1:')).toBeInTheDocument()
    })
  })

  describe('Objects', () => {
    it('renders simple object with expand button', () => {
      render(<JsonViewer data={{ name: 'Test' }} />)

      expect(screen.getByText('Object{1}')).toBeInTheDocument()
      expect(screen.getByTestId('chevron-right')).toBeInTheDocument()
    })

    it('expands object on click', async () => {
      const user = userEvent.setup()
      render(<JsonViewer data={{ name: 'John', age: 30 }} />)

      const expandButton = screen.getByText('Object{2}')
      await user.click(expandButton)

      expect(screen.getByText('name:')).toBeInTheDocument()
      expect(screen.getByText('"John"')).toBeInTheDocument()
      expect(screen.getByText('age:')).toBeInTheDocument()
      expect(screen.getByText('30')).toBeInTheDocument()
    })

    it('can toggle object expansion', async () => {
      const user = userEvent.setup()
      const { container } = render(<JsonViewer data={{ test: 'value' }} />)

      const expandButton = container.querySelector('button')!

      // Initially collapsed - no keys shown
      expect(screen.queryByText('test:')).not.toBeInTheDocument()

      // Expand
      await user.click(expandButton)
      expect(screen.getByText('test:')).toBeInTheDocument()
      expect(screen.getByText('"value"')).toBeInTheDocument()

      // Collapse again
      await user.click(expandButton)
      expect(screen.queryByText('test:')).not.toBeInTheDocument()
    })
  })

  describe('Nested Structures', () => {
    it('renders nested objects', async () => {
      const user = userEvent.setup()
      const data = {
        user: {
          name: 'John',
          address: {
            city: 'NYC',
          },
        },
      }
      render(<JsonViewer data={data} />)

      const expandButton = screen.getByText('Object{1}')
      await user.click(expandButton)

      expect(screen.getByText('user:')).toBeInTheDocument()
    })

    it('renders nested arrays', async () => {
      const user = userEvent.setup()
      const data = [
        [1, 2],
        [3, 4],
      ]
      render(<JsonViewer data={data} />)

      const expandButton = screen.getByText('Array[2]')
      await user.click(expandButton)

      expect(screen.getByText('0:')).toBeInTheDocument()
      expect(screen.getByText('1:')).toBeInTheDocument()
    })
  })

  describe('Expanded Prop', () => {
    it('expands root when expanded is true', () => {
      render(<JsonViewer data={{ key: 'value' }} expanded={true} />)

      expect(screen.getByText('key:')).toBeInTheDocument()
      expect(screen.getByText('"value"')).toBeInTheDocument()
    })

    it('collapses root when expanded is false', () => {
      render(<JsonViewer data={{ key: 'value' }} expanded={false} />)

      expect(screen.queryByText('key:')).not.toBeInTheDocument()
      expect(screen.queryByText('"value"')).not.toBeInTheDocument()
    })
  })

  describe('Max Depth Control', () => {
    it('respects maxDepth limit', async () => {
      const user = userEvent.setup()
      const deepData = {
        level1: {
          level2: {
            level3: {
              value: 'deep',
            },
          },
        },
      }
      render(<JsonViewer data={deepData} maxDepth={2} />)

      // Expand to depth 1
      await user.click(screen.getByText('Object{1}'))
      expect(screen.getByText('level1:')).toBeInTheDocument()

      // Expand to depth 2
      const level1Objects = screen.getAllByText(/Object\{/)
      if (level1Objects.length > 1) {
        await user.click(level1Objects[1])
      }

      // Should not render beyond maxDepth
      const level3Text = screen.queryByText('level3:')
      expect(level3Text).not.toBeInTheDocument()
    })
  })

  describe('Icons and Expand/Collapse', () => {
    it('shows right chevron when collapsed', () => {
      render(<JsonViewer data={{ key: 'value' }} />)

      expect(screen.getByTestId('chevron-right')).toBeInTheDocument()
      expect(screen.queryByTestId('chevron-down')).not.toBeInTheDocument()
    })

    it('shows down chevron when expanded', async () => {
      const user = userEvent.setup()
      render(<JsonViewer data={{ key: 'value' }} />)

      await user.click(screen.getByText('Object{1}'))

      expect(screen.getByTestId('chevron-down')).toBeInTheDocument()
    })
  })

  describe('Edge Cases', () => {
    it('handles large numbers', () => {
      render(<JsonViewer data={999999999} />)

      expect(screen.getByText('999999999')).toBeInTheDocument()
    })

    it('handles unicode strings', () => {
      render(<JsonViewer data="你好🌍" />)

      expect(screen.getByText('"你好🌍"')).toBeInTheDocument()
    })

    it('handles long strings', () => {
      const longString = 'A'.repeat(1000)
      render(<JsonViewer data={longString} />)

      const displayed = screen.getByText(new RegExp(`"${longString}"`))
      expect(displayed).toBeInTheDocument()
    })

    it('handles objects with many keys', async () => {
      const user = userEvent.setup()
      const data = Object.fromEntries(
        Array.from({ length: 50 }, (_, i) => [`key${i}`, i])
      )
      render(<JsonViewer data={data} />)

      expect(screen.getByText('Object{50}')).toBeInTheDocument()

      await user.click(screen.getByText('Object{50}'))
      expect(screen.getByText('key0:')).toBeInTheDocument()
      expect(screen.getByText('key49:')).toBeInTheDocument()
    })

    it('handles arrays with many items', async () => {
      const user = userEvent.setup()
      const data = Array.from({ length: 100 }, (_, i) => ({ id: i }))
      render(<JsonViewer data={data} />)

      expect(screen.getByText('Array[100]')).toBeInTheDocument()

      await user.click(screen.getByText('Array[100]'))
      expect(screen.getByText('0:')).toBeInTheDocument()
      expect(screen.getByText('99:')).toBeInTheDocument()
    })
  })

  describe('Accessibility', () => {
    it('expand buttons are clickable', async () => {
      const user = userEvent.setup()
      const { container } = render(<JsonViewer data={{ key: 'value' }} />)

      const button = container.querySelector('button')!
      await user.click(button)

      expect(screen.getByText('key:')).toBeInTheDocument()
    })

    it('buttons can receive focus', () => {
      const { container } = render(<JsonViewer data={{ key: 'value' }} />)

      const button = container.querySelector('button')!
      button.focus()
      expect(button).toHaveFocus()
    })

    it('buttons have focus outline removed', () => {
      const { container } = render(<JsonViewer data={{ key: 'value' }} />)

      const button = container.querySelector('button')!
      expect(button).toHaveClass('focus:outline-none')
    })
  })
})

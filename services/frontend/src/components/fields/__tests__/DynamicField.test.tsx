import { render, screen } from '@testing-library/react'
import { DynamicField, DynamicFieldGroup, FieldConfig } from '../DynamicField'

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

describe('DynamicField', () => {
  describe('Basic Rendering', () => {
    it('renders text field with label and value', () => {
      const field: FieldConfig = {
        name: 'name',
        label: 'Name',
        type: 'text',
      }
      render(<DynamicField field={field} value="John Doe" />)
      expect(screen.getByText('Name:')).toBeInTheDocument()
      expect(screen.getByText('John Doe')).toBeInTheDocument()
    })

    it('renders field without label when not provided', () => {
      const field: FieldConfig = {
        name: 'value',
        type: 'text',
      }
      render(<DynamicField field={field} value="Test Value" />)
      expect(screen.getByText('Test Value')).toBeInTheDocument()
      expect(screen.queryByText(':')).not.toBeInTheDocument()
    })

    it('applies custom className to field wrapper', () => {
      const field: FieldConfig = {
        name: 'test',
        type: 'text',
      }
      const { container } = render(
        <DynamicField field={field} value="test" className="custom-class" />
      )
      expect(container.firstChild).toHaveClass('custom-class')
    })

    it('applies field-specific className from config', () => {
      const field: FieldConfig = {
        name: 'test',
        type: 'badge',
        className: 'field-custom-class',
      }
      render(<DynamicField field={field} value="test" />)
      const badge = screen.getByText('test').closest('.field-custom-class')
      expect(badge).toBeInTheDocument()
    })
  })

  describe('Badge Type', () => {
    it('renders badge with label and value', () => {
      const field: FieldConfig = {
        name: 'status',
        label: 'Status',
        type: 'badge',
      }
      render(<DynamicField field={field} value="active" />)
      expect(screen.getByText('Status:')).toBeInTheDocument()
      expect(screen.getByText('active')).toBeInTheDocument()
    })

    it('renders badge without label', () => {
      const field: FieldConfig = {
        name: 'status',
        type: 'badge',
      }
      render(<DynamicField field={field} value="active" />)
      expect(screen.getByText('active')).toBeInTheDocument()
      expect(screen.queryByText('Status:')).not.toBeInTheDocument()
    })

    it('applies badge variant styles', () => {
      const field: FieldConfig = {
        name: 'status',
        type: 'badge',
      }
      const { container } = render(<DynamicField field={field} value="test" />)
      const badge = container.querySelector('.inline-flex')
      expect(badge).toBeInTheDocument()
    })
  })

  describe('Code Type', () => {
    it('renders code block with label', () => {
      const field: FieldConfig = {
        name: 'snippet',
        label: 'Code',
        type: 'code',
      }
      render(<DynamicField field={field} value="const x = 1;" />)
      expect(screen.getByText('Code')).toBeInTheDocument()
      expect(screen.getByText('const x = 1;')).toBeInTheDocument()
    })

    it('renders code block without label', () => {
      const field: FieldConfig = {
        name: 'snippet',
        type: 'code',
      }
      render(<DynamicField field={field} value="const x = 1;" />)
      expect(screen.getByText('const x = 1;')).toBeInTheDocument()
    })

    it('applies code formatting styles', () => {
      const field: FieldConfig = {
        name: 'code',
        type: 'code',
      }
      const { container } = render(<DynamicField field={field} value="test" />)
      const pre = container.querySelector('pre')
      expect(pre).toBeInTheDocument()
      expect(pre).toHaveClass('bg-muted')
      const code = container.querySelector('code')
      expect(code).toBeInTheDocument()
    })
  })

  describe('Boolean Type', () => {
    it('renders true boolean as "Yes"', () => {
      const field: FieldConfig = {
        name: 'active',
        label: 'Active',
        type: 'boolean',
      }
      render(<DynamicField field={field} value={true} />)
      expect(screen.getByText('Active:')).toBeInTheDocument()
      expect(screen.getByText('Yes')).toBeInTheDocument()
    })

    it('renders false boolean as "No"', () => {
      const field: FieldConfig = {
        name: 'active',
        label: 'Active',
        type: 'boolean',
      }
      render(<DynamicField field={field} value={false} />)
      expect(screen.getByText('Active:')).toBeInTheDocument()
      expect(screen.getByText('No')).toBeInTheDocument()
    })

    it('applies default variant for true', () => {
      const field: FieldConfig = {
        name: 'active',
        type: 'boolean',
      }
      render(<DynamicField field={field} value={true} />)
      const badge = screen.getByText('Yes')
      expect(badge).toBeInTheDocument()
    })

    it('applies secondary variant for false', () => {
      const field: FieldConfig = {
        name: 'active',
        type: 'boolean',
      }
      render(<DynamicField field={field} value={false} />)
      const badge = screen.getByText('No')
      expect(badge).toBeInTheDocument()
    })
  })

  describe('List Type', () => {
    it('renders list with items', () => {
      const field: FieldConfig = {
        name: 'items',
        label: 'Items',
        type: 'list',
      }
      render(
        <DynamicField field={field} value={['Item 1', 'Item 2', 'Item 3']} />
      )
      expect(screen.getByText('Items')).toBeInTheDocument()
      expect(screen.getByText('Item 1')).toBeInTheDocument()
      expect(screen.getByText('Item 2')).toBeInTheDocument()
      expect(screen.getByText('Item 3')).toBeInTheDocument()
    })

    it('renders empty list', () => {
      const field: FieldConfig = {
        name: 'items',
        label: 'Items',
        type: 'list',
      }
      render(<DynamicField field={field} value={[]} />)
      expect(screen.getByText('Items')).toBeInTheDocument()
      const list = screen.getByText('Items').nextElementSibling
      expect(list?.children.length).toBe(0)
    })

    it('returns null for non-array value', () => {
      const field: FieldConfig = {
        name: 'items',
        type: 'list',
      }
      const { container } = render(
        <DynamicField field={field} value="not an array" />
      )
      expect(container.firstChild).toBeNull()
    })

    it('renders list without label', () => {
      const field: FieldConfig = {
        name: 'items',
        type: 'list',
      }
      render(<DynamicField field={field} value={['Item 1', 'Item 2']} />)
      expect(screen.getByText('Item 1')).toBeInTheDocument()
      expect(screen.getByText('Item 2')).toBeInTheDocument()
    })

    it('applies list styling', () => {
      const field: FieldConfig = {
        name: 'items',
        type: 'list',
      }
      const { container } = render(
        <DynamicField field={field} value={['Item 1']} />
      )
      const list = container.querySelector('ul')
      expect(list).toBeInTheDocument()
      expect(list).toHaveClass('list-disc')
      expect(list).toHaveClass('list-inside')
    })
  })

  describe('Object/JSON Type', () => {
    it('renders object as JSON', () => {
      const field: FieldConfig = {
        name: 'data',
        label: 'Data',
        type: 'object',
      }
      const obj = { key: 'value', count: 42 }
      render(<DynamicField field={field} value={obj} />)
      expect(screen.getByText('Data')).toBeInTheDocument()
      expect(screen.getByText(/"key": "value"/)).toBeInTheDocument()
    })

    it('renders JSON type', () => {
      const field: FieldConfig = {
        name: 'data',
        label: 'JSON Data',
        type: 'json',
      }
      const obj = { test: true }
      render(<DynamicField field={field} value={obj} />)
      expect(screen.getByText('JSON Data')).toBeInTheDocument()
      expect(screen.getByText(/"test": true/)).toBeInTheDocument()
    })

    it('formats object with proper indentation', () => {
      const field: FieldConfig = {
        name: 'data',
        type: 'object',
      }
      const obj = { a: 1, b: 2 }
      const { container } = render(<DynamicField field={field} value={obj} />)
      const pre = container.querySelector('pre')
      expect(pre?.textContent).toContain(JSON.stringify(obj, null, 2))
    })

    it('renders nested objects', () => {
      const field: FieldConfig = {
        name: 'data',
        type: 'object',
      }
      const obj = { outer: { inner: 'value' } }
      render(<DynamicField field={field} value={obj} />)
      expect(screen.getByText(/"inner": "value"/)).toBeInTheDocument()
    })
  })

  describe('Text/Number/Date Types', () => {
    it('renders short text inline', () => {
      const field: FieldConfig = {
        name: 'name',
        label: 'Name',
        type: 'text',
      }
      render(<DynamicField field={field} value="Short text" />)
      expect(screen.getByText('Name:')).toBeInTheDocument()
      expect(screen.getByText('Short text')).toBeInTheDocument()
    })

    it('renders long text in block layout', () => {
      const field: FieldConfig = {
        name: 'description',
        label: 'Description',
        type: 'text',
      }
      const longText = 'a'.repeat(250)
      render(<DynamicField field={field} value={longText} />)
      expect(screen.getByText('Description')).toBeInTheDocument()
      expect(screen.getByText(longText)).toBeInTheDocument()
    })

    it('renders number type', () => {
      const field: FieldConfig = {
        name: 'count',
        label: 'Count',
        type: 'number',
      }
      render(<DynamicField field={field} value={42} />)
      expect(screen.getByText('Count:')).toBeInTheDocument()
      expect(screen.getByText('42')).toBeInTheDocument()
    })

    it('renders date type', () => {
      const field: FieldConfig = {
        name: 'created',
        label: 'Created',
        type: 'date',
      }
      render(<DynamicField field={field} value="2025-01-01" />)
      expect(screen.getByText('Created:')).toBeInTheDocument()
      expect(screen.getByText('2025-01-01')).toBeInTheDocument()
    })

    it('renders default type for undefined type', () => {
      const field: FieldConfig = {
        name: 'value',
        label: 'Value',
      }
      render(<DynamicField field={field} value="default" />)
      expect(screen.getByText('Value:')).toBeInTheDocument()
      expect(screen.getByText('default')).toBeInTheDocument()
    })

    it('preserves whitespace in long text', () => {
      const field: FieldConfig = {
        name: 'text',
        type: 'text',
      }
      const textWithSpaces = 'a'.repeat(250)
      const { container } = render(
        <DynamicField field={field} value={textWithSpaces} />
      )
      const textElement = container.querySelector('.whitespace-pre-wrap')
      expect(textElement).toBeInTheDocument()
    })
  })

  describe('Custom Render Function', () => {
    it('uses custom render function when provided', () => {
      const field: FieldConfig = {
        name: 'custom',
        render: (value) => <div>Custom: {value}</div>,
      }
      render(<DynamicField field={field} value="test" />)
      expect(screen.getByText('Custom: test')).toBeInTheDocument()
    })

    it('custom render overrides type rendering', () => {
      const field: FieldConfig = {
        name: 'custom',
        type: 'badge',
        render: (value) => <span>Rendered: {value}</span>,
      }
      render(<DynamicField field={field} value="test" />)
      expect(screen.getByText('Rendered: test')).toBeInTheDocument()
      expect(screen.queryByRole('status')).not.toBeInTheDocument()
    })

    it('custom render receives correct value', () => {
      const field: FieldConfig = {
        name: 'custom',
        render: (value) => <div>{JSON.stringify(value)}</div>,
      }
      const complexValue = { key: 'value', num: 123 }
      render(<DynamicField field={field} value={complexValue} />)
      expect(screen.getByText(JSON.stringify(complexValue))).toBeInTheDocument()
    })
  })

  describe('Custom Format Function', () => {
    it('uses custom format function', () => {
      const field: FieldConfig = {
        name: 'date',
        label: 'Date',
        format: (value) => `Formatted: ${value}`,
      }
      render(<DynamicField field={field} value="2025-01-01" />)
      expect(screen.getByText('Formatted: 2025-01-01')).toBeInTheDocument()
    })

    it('format function works with type rendering', () => {
      const field: FieldConfig = {
        name: 'status',
        type: 'badge',
        format: (value) => value.toUpperCase(),
      }
      render(<DynamicField field={field} value="active" />)
      expect(screen.getByText('ACTIVE')).toBeInTheDocument()
    })

    it('format function receives correct value', () => {
      const formatFn = jest.fn((value) => `${value}`)
      const field: FieldConfig = {
        name: 'test',
        format: formatFn,
      }
      render(<DynamicField field={field} value="test-value" />)
      expect(formatFn).toHaveBeenCalledWith('test-value')
    })
  })
})

describe('DynamicFieldGroup', () => {
  describe('Basic Rendering', () => {
    it('renders multiple fields', () => {
      const fields: FieldConfig[] = [
        { name: 'name', label: 'Name', type: 'text' },
        { name: 'age', label: 'Age', type: 'number' },
      ]
      const data = { name: 'John', age: 30 }
      render(<DynamicFieldGroup fields={fields} data={data} />)
      expect(screen.getByText('Name:')).toBeInTheDocument()
      expect(screen.getByText('John')).toBeInTheDocument()
      expect(screen.getByText('Age:')).toBeInTheDocument()
      expect(screen.getByText('30')).toBeInTheDocument()
    })

    it('renders with title', () => {
      const fields: FieldConfig[] = [
        { name: 'name', label: 'Name', type: 'text' },
      ]
      const data = { name: 'John' }
      render(
        <DynamicFieldGroup fields={fields} data={data} title="User Info" />
      )
      expect(screen.getByText('User Info')).toBeInTheDocument()
    })

    it('renders without title', () => {
      const fields: FieldConfig[] = [
        { name: 'name', label: 'Name', type: 'text' },
      ]
      const data = { name: 'John' }
      render(<DynamicFieldGroup fields={fields} data={data} />)
      expect(screen.getByText('Name:')).toBeInTheDocument()
    })

    it('applies custom className', () => {
      const fields: FieldConfig[] = [
        { name: 'name', label: 'Name', type: 'text' },
      ]
      const data = { name: 'John' }
      const { container } = render(
        <DynamicFieldGroup
          fields={fields}
          data={data}
          className="custom-group"
        />
      )
      expect(container.firstChild).toHaveClass('custom-group')
    })
  })

  describe('Path Resolution', () => {
    it('resolves nested path with dot notation', () => {
      const fields: FieldConfig[] = [
        { name: 'nested', label: 'Nested', path: 'user.name' },
      ]
      const data = { user: { name: 'John' } }
      render(<DynamicFieldGroup fields={fields} data={data} />)
      expect(screen.getByText('John')).toBeInTheDocument()
    })

    it('resolves deep nested paths', () => {
      const fields: FieldConfig[] = [
        { name: 'deep', label: 'Deep', path: 'a.b.c.d' },
      ]
      const data = { a: { b: { c: { d: 'value' } } } }
      render(<DynamicFieldGroup fields={fields} data={data} />)
      expect(screen.getByText('value')).toBeInTheDocument()
    })

    it('uses name when path is not provided', () => {
      const fields: FieldConfig[] = [{ name: 'name', label: 'Name' }]
      const data = { name: 'Direct' }
      render(<DynamicFieldGroup fields={fields} data={data} />)
      expect(screen.getByText('Direct')).toBeInTheDocument()
    })

    it('skips field when value is undefined', () => {
      const fields: FieldConfig[] = [
        { name: 'missing', label: 'Missing', path: 'not.exists' },
      ]
      const data = { other: 'value' }
      const { container } = render(
        <DynamicFieldGroup fields={fields} data={data} />
      )
      expect(screen.queryByText('Missing')).not.toBeInTheDocument()
    })

    it('skips field when value is null', () => {
      const fields: FieldConfig[] = [{ name: 'nullValue', label: 'Null' }]
      const data = { nullValue: null }
      const { container } = render(
        <DynamicFieldGroup fields={fields} data={data} />
      )
      expect(screen.queryByText('Null')).not.toBeInTheDocument()
    })
  })

  describe('Multiple Fields', () => {
    it('renders empty group when no fields', () => {
      const { container } = render(<DynamicFieldGroup fields={[]} data={{}} />)
      expect(container.firstChild).toBeInTheDocument()
      expect(container.querySelector('.space-y-3')).toBeInTheDocument()
    })

    it('renders mixed field types', () => {
      const fields: FieldConfig[] = [
        { name: 'text', label: 'Text', type: 'text' },
        { name: 'bool', label: 'Bool', type: 'boolean' },
        { name: 'badge', label: 'Badge', type: 'badge' },
      ]
      const data = { text: 'value', bool: true, badge: 'active' }
      render(<DynamicFieldGroup fields={fields} data={data} />)
      expect(screen.getByText('value')).toBeInTheDocument()
      expect(screen.getByText('Yes')).toBeInTheDocument()
      expect(screen.getByText('active')).toBeInTheDocument()
    })

    it('renders fields in correct order', () => {
      const fields: FieldConfig[] = [
        { name: 'first', label: 'First' },
        { name: 'second', label: 'Second' },
        { name: 'third', label: 'Third' },
      ]
      const data = { first: '1', second: '2', third: '3' }
      const { container } = render(
        <DynamicFieldGroup fields={fields} data={data} />
      )
      const labels = Array.from(container.querySelectorAll('.font-medium')).map(
        (el) => el.textContent
      )
      expect(labels).toEqual(['First:', 'Second:', 'Third:'])
    })
  })
})

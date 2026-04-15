/**
 * @jest-environment jsdom
 */

import { TaskTemplateField } from '@/types/taskTemplate'
import { render, screen } from '@testing-library/react'
import { FieldWrapper, getInputClasses } from '../BaseField'

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
jest.mock('@heroicons/react/24/outline', () => ({
  ExclamationCircleIcon: ({ className }: { className?: string }) => (
    <svg className={className} data-testid="exclamation-icon">
      <path />
    </svg>
  ),
}))

describe('BaseField Utilities', () => {
  describe('FieldWrapper Component', () => {
    const defaultField: TaskTemplateField = {
      name: 'test_field',
      type: 'text',
      source: 'task_data',
      display: {
        annotation: 'editable',
        table: 'column',
        creation: 'editable',
      },
      label: 'Test Field',
      description: 'Test field description',
      required: false,
    }

    it('renders children content', () => {
      render(
        <FieldWrapper field={defaultField}>
          <input data-testid="test-input" />
        </FieldWrapper>
      )

      expect(screen.getByTestId('test-input')).toBeInTheDocument()
    })

    it('renders field label', () => {
      render(
        <FieldWrapper field={defaultField}>
          <div>Content</div>
        </FieldWrapper>
      )

      expect(screen.getByText('Test Field (Optional)')).toBeInTheDocument()
    })

    it('renders field description', () => {
      render(
        <FieldWrapper field={defaultField}>
          <div>Content</div>
        </FieldWrapper>
      )

      expect(screen.getByText('Test field description')).toBeInTheDocument()
    })

    it('shows required asterisk for required fields', () => {
      const requiredField = { ...defaultField, required: true }
      render(
        <FieldWrapper field={requiredField}>
          <div>Content</div>
        </FieldWrapper>
      )

      const asterisk = screen.getByText('*')
      expect(asterisk).toBeInTheDocument()
      expect(asterisk).toHaveClass('text-red-500')
    })

    it('does not show asterisk for optional fields', () => {
      render(
        <FieldWrapper field={defaultField}>
          <div>Content</div>
        </FieldWrapper>
      )

      expect(screen.queryByText('*')).not.toBeInTheDocument()
    })

    it('adds (Optional) suffix to non-required fields', () => {
      render(
        <FieldWrapper field={defaultField}>
          <div>Content</div>
        </FieldWrapper>
      )

      expect(screen.getByText('Test Field (Optional)')).toBeInTheDocument()
    })

    it('does not duplicate (Optional) if already in label', () => {
      const fieldWithOptional = {
        ...defaultField,
        label: 'Test Field (Optional)',
      }
      render(
        <FieldWrapper field={fieldWithOptional}>
          <div>Content</div>
        </FieldWrapper>
      )

      const label = screen.getByText('Test Field (Optional)')
      expect(label).toBeInTheDocument()
      // Should not have double (Optional)
      expect(
        screen.queryByText('Test Field (Optional) (Optional)')
      ).not.toBeInTheDocument()
    })

    it('displays single error message', () => {
      const errors = ['This field is required']
      render(
        <FieldWrapper field={defaultField} errors={errors}>
          <div>Content</div>
        </FieldWrapper>
      )

      expect(screen.getByText('This field is required')).toBeInTheDocument()
      expect(screen.getByTestId('exclamation-icon')).toBeInTheDocument()
    })

    it('displays multiple error messages', () => {
      const errors = ['Error 1', 'Error 2', 'Error 3']
      render(
        <FieldWrapper field={defaultField} errors={errors}>
          <div>Content</div>
        </FieldWrapper>
      )

      expect(screen.getByText('Error 1')).toBeInTheDocument()
      expect(screen.getByText('Error 2')).toBeInTheDocument()
      expect(screen.getByText('Error 3')).toBeInTheDocument()

      const icons = screen.getAllByTestId('exclamation-icon')
      expect(icons).toHaveLength(3)
    })

    it('does not display errors when array is empty', () => {
      render(
        <FieldWrapper field={defaultField} errors={[]}>
          <div>Content</div>
        </FieldWrapper>
      )

      expect(screen.queryByTestId('exclamation-icon')).not.toBeInTheDocument()
    })

    it('does not display errors when not provided', () => {
      render(
        <FieldWrapper field={defaultField}>
          <div>Content</div>
        </FieldWrapper>
      )

      expect(screen.queryByTestId('exclamation-icon')).not.toBeInTheDocument()
    })

    it('applies error styling to error messages', () => {
      const errors = ['Test error']
      const { container } = render(
        <FieldWrapper field={defaultField} errors={errors}>
          <div>Content</div>
        </FieldWrapper>
      )

      const errorDiv = container.querySelector('.text-red-600')
      expect(errorDiv).toBeInTheDocument()
      expect(errorDiv).toHaveClass('dark:text-red-400')
    })

    it('applies custom className to wrapper', () => {
      const { container } = render(
        <FieldWrapper field={defaultField} className="custom-wrapper-class">
          <div>Content</div>
        </FieldWrapper>
      )

      const wrapper = container.querySelector('.field-wrapper')
      expect(wrapper).toHaveClass('custom-wrapper-class')
    })

    it('renders label as a label element', () => {
      const { container } = render(
        <FieldWrapper field={defaultField}>
          <div>Content</div>
        </FieldWrapper>
      )

      const label = container.querySelector('label')
      expect(label).toBeInTheDocument()
      expect(label).toHaveTextContent('Test Field (Optional)')
    })

    it('handles field without label', () => {
      const fieldWithoutLabel = { ...defaultField, label: undefined }
      render(
        <FieldWrapper field={fieldWithoutLabel}>
          <div>Content</div>
        </FieldWrapper>
      )

      const label = screen.queryByRole('label')
      expect(label).not.toBeInTheDocument()
    })

    it('handles field without description', () => {
      const fieldWithoutDescription = {
        ...defaultField,
        description: undefined,
      }
      render(
        <FieldWrapper field={fieldWithoutDescription}>
          <div>Content</div>
        </FieldWrapper>
      )

      expect(
        screen.queryByText('Test field description')
      ).not.toBeInTheDocument()
    })

    it('applies label styling classes', () => {
      const { container } = render(
        <FieldWrapper field={defaultField}>
          <div>Content</div>
        </FieldWrapper>
      )

      const label = container.querySelector('label')
      expect(label).toHaveClass(
        'mb-1',
        'block',
        'text-sm',
        'font-medium',
        'text-gray-700',
        'dark:text-gray-300'
      )
    })

    it('applies description styling classes', () => {
      const { container } = render(
        <FieldWrapper field={defaultField}>
          <div>Content</div>
        </FieldWrapper>
      )

      const description = screen.getByText('Test field description')
      expect(description).toHaveClass(
        'mb-2',
        'text-sm',
        'text-gray-500',
        'dark:text-gray-400'
      )
    })
  })

  describe('getInputClasses Function', () => {
    it('returns base classes for normal state', () => {
      const classes = getInputClasses(false, false)

      expect(classes).toContain('block')
      expect(classes).toContain('w-full')
      expect(classes).toContain('rounded-md')
      expect(classes).toContain('shadow-sm')
      expect(classes).toContain('sm:text-sm')
      expect(classes).toContain('transition-colors')
    })

    it('returns error classes when hasError is true', () => {
      const classes = getInputClasses(true, false)

      expect(classes).toContain('border-red-300')
      expect(classes).toContain('dark:border-red-600')
      expect(classes).toContain('focus:border-red-500')
      expect(classes).toContain('focus:ring-red-500')
    })

    it('returns normal classes when hasError is false', () => {
      const classes = getInputClasses(false, false)

      expect(classes).toContain('border-gray-300')
      expect(classes).toContain('dark:border-gray-600')
      expect(classes).toContain('focus:border-blue-500')
      expect(classes).toContain('focus:ring-blue-500')
    })

    it('returns readonly classes when readonly is true', () => {
      const classes = getInputClasses(false, true)

      expect(classes).toContain('bg-gray-50')
      expect(classes).toContain('dark:bg-gray-800')
      expect(classes).toContain('cursor-not-allowed')
    })

    it('returns normal background classes when readonly is false', () => {
      const classes = getInputClasses(false, false)

      expect(classes).toContain('bg-white')
      expect(classes).toContain('dark:bg-gray-700')
    })

    it('combines error and readonly classes', () => {
      const classes = getInputClasses(true, true)

      // Should have error classes
      expect(classes).toContain('border-red-300')
      expect(classes).toContain('dark:border-red-600')

      // Should have readonly classes
      expect(classes).toContain('bg-gray-50')
      expect(classes).toContain('dark:bg-gray-800')
      expect(classes).toContain('cursor-not-allowed')
    })

    it('always includes base classes regardless of state', () => {
      const normalClasses = getInputClasses(false, false)
      const errorClasses = getInputClasses(true, false)
      const readonlyClasses = getInputClasses(false, true)
      const bothClasses = getInputClasses(true, true)

      const baseClassesList = [
        'block',
        'w-full',
        'rounded-md',
        'shadow-sm',
        'sm:text-sm',
        'transition-colors',
      ]

      for (const baseClass of baseClassesList) {
        expect(normalClasses).toContain(baseClass)
        expect(errorClasses).toContain(baseClass)
        expect(readonlyClasses).toContain(baseClass)
        expect(bothClasses).toContain(baseClass)
      }
    })

    it('does not include error classes in normal state', () => {
      const classes = getInputClasses(false, false)

      expect(classes).not.toContain('border-red-300')
      expect(classes).not.toContain('dark:border-red-600')
    })

    it('does not include readonly classes in editable state', () => {
      const classes = getInputClasses(false, false)

      expect(classes).not.toContain('bg-gray-50')
      expect(classes).not.toContain('cursor-not-allowed')
    })

    it('returns a string type', () => {
      const classes = getInputClasses(false, false)

      expect(typeof classes).toBe('string')
    })

    it('returns non-empty string', () => {
      const classes = getInputClasses(false, false)

      expect(classes.length).toBeGreaterThan(0)
    })
  })
})

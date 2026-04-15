/**
 * @jest-environment jsdom
 */

// Mock i18n context
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string) => {
      const translations: Record<string, string> = {
        'projects.searchPlaceholder': 'Search projects...',
        'projects.noProjects': 'No projects found',
        'projects.loading': 'Loading projects...',
        'tasks.searchPlaceholder': 'Search tasks...',
        'tasks.noTasks': 'No tasks found',
        'tasks.loading': 'Loading tasks...',
        'common.search': 'Search...',
        'common.loading': 'Loading...',
        'common.save': 'Save',
        'common.cancel': 'Cancel',
        'common.delete': 'Delete',
        'common.edit': 'Edit',
        'common.create': 'Create',
        'common.update': 'Update',
        'common.close': 'Close',
        'annotations.loading': 'Loading annotations...',
        'annotations.noAnnotations': 'No annotations found',
        'quality.title': 'Quality Control',
        'quality.loading': 'Loading quality metrics...',
        'analytics.title': 'Analytics',
        'analytics.loading': 'Loading analytics...',
      }
      return translations[key] || key
    },
    currentLanguage: 'en',
  }),
}))

import { fireEvent, render, screen } from '@testing-library/react'
import React from 'react'
import { SearchInput } from '../SearchInput'

describe('SearchInput', () => {
  describe('rendering', () => {
    it('should render with default props', () => {
      render(<SearchInput value="" onChange={() => {}} />)
      const input = screen.getByPlaceholderText('Search...')
      expect(input).toBeInTheDocument()
      expect(input).toHaveClass('rounded-full')
    })

    it('should render with custom placeholder', () => {
      render(
        <SearchInput
          value=""
          onChange={() => {}}
          placeholder="Find projects..."
        />
      )
      expect(
        screen.getByPlaceholderText('Find projects...')
      ).toBeInTheDocument()
    })

    it('should show search icon by default', () => {
      const { container } = render(<SearchInput value="" onChange={() => {}} />)
      const icon = container.querySelector('svg')
      expect(icon).toBeInTheDocument()
    })

    it('should hide icon when showIcon is false', () => {
      const { container } = render(
        <SearchInput value="" onChange={() => {}} showIcon={false} />
      )
      const icon = container.querySelector('svg')
      expect(icon).not.toBeInTheDocument()
    })

    it('should position icon on the left by default', () => {
      const { container } = render(<SearchInput value="" onChange={() => {}} />)
      const leftIcon = container.querySelector('.left-0')
      expect(leftIcon).toBeInTheDocument()
    })

    it('should position icon on the right when specified', () => {
      const { container } = render(
        <SearchInput value="" onChange={() => {}} iconPosition="right" />
      )
      const rightIcon = container.querySelector('.right-0')
      expect(rightIcon).toBeInTheDocument()
    })

    it('should show loading spinner when loading is true', () => {
      const { container } = render(
        <SearchInput value="" onChange={() => {}} loading={true} />
      )
      const spinner = container.querySelector('.animate-spin')
      expect(spinner).toBeInTheDocument()
    })

    it('should apply custom className', () => {
      const { container } = render(
        <SearchInput value="" onChange={() => {}} className="custom-class" />
      )
      expect(container.firstChild).toHaveClass('custom-class')
    })

    it('should have proper navigation-like styling', () => {
      render(<SearchInput value="" onChange={() => {}} />)
      const input = screen.getByPlaceholderText('Search...')

      // Check for rounded-full (matching navigation)
      expect(input).toHaveClass('rounded-full')

      // Check for proper ring styling
      expect(input).toHaveClass('ring-1')
      expect(input).toHaveClass('ring-zinc-900/10')
      expect(input).toHaveClass('dark:ring-white/10')

      // Check for hover states
      expect(input).toHaveClass('hover:ring-zinc-900/20')
      expect(input).toHaveClass('dark:hover:ring-white/20')

      // Check for focus states
      expect(input).toHaveClass('focus:ring-2')
      expect(input).toHaveClass('focus:ring-emerald-500')
    })
  })

  describe('functionality', () => {
    it('should display the provided value', () => {
      render(<SearchInput value="test query" onChange={() => {}} />)
      const input = screen.getByDisplayValue('test query')
      expect(input).toBeInTheDocument()
    })

    it('should call onChange when input value changes', () => {
      const handleChange = jest.fn()
      render(<SearchInput value="" onChange={handleChange} />)

      const input = screen.getByPlaceholderText('Search...')
      fireEvent.change(input, { target: { value: 'new value' } })

      expect(handleChange).toHaveBeenCalledWith('new value')
    })

    it('should call onChange immediately', () => {
      const handleChange = jest.fn()

      render(<SearchInput value="" onChange={handleChange} />)

      const input = screen.getByPlaceholderText('Search...')
      fireEvent.change(input, { target: { value: 'quick' } })

      // Should be called immediately
      expect(handleChange).toHaveBeenCalledWith('quick')
    })

    it('should handle multiple rapid changes', () => {
      const handleChange = jest.fn()

      render(<SearchInput value="" onChange={handleChange} />)

      const input = screen.getByPlaceholderText('Search...')

      // Type rapidly
      fireEvent.change(input, { target: { value: 'a' } })
      fireEvent.change(input, { target: { value: 'ab' } })
      fireEvent.change(input, { target: { value: 'abc' } })

      // Should be called for each change
      expect(handleChange).toHaveBeenCalledTimes(3)
      expect(handleChange).toHaveBeenNthCalledWith(1, 'a')
      expect(handleChange).toHaveBeenNthCalledWith(2, 'ab')
      expect(handleChange).toHaveBeenNthCalledWith(3, 'abc')
    })

    it('should sync with external value changes', () => {
      const { rerender } = render(
        <SearchInput value="initial" onChange={() => {}} />
      )
      expect(screen.getByDisplayValue('initial')).toBeInTheDocument()

      rerender(<SearchInput value="updated" onChange={() => {}} />)
      expect(screen.getByDisplayValue('updated')).toBeInTheDocument()
    })
  })

  describe('accessibility', () => {
    it('should have type="search" attribute', () => {
      render(<SearchInput value="" onChange={() => {}} />)
      const input = screen.getByPlaceholderText('Search...')
      expect(input).toHaveAttribute('type', 'search')
    })

    it('should support disabled state', () => {
      render(<SearchInput value="" onChange={() => {}} disabled />)
      const input = screen.getByPlaceholderText('Search...')
      expect(input).toBeDisabled()
      expect(input).toHaveClass('disabled:cursor-not-allowed')
    })

    it('should forward additional props to input element', () => {
      render(
        <SearchInput
          value=""
          onChange={() => {}}
          aria-label="Search projects"
          data-testid="custom-search"
          autoComplete="off"
        />
      )
      const input = screen.getByPlaceholderText('Search...')
      expect(input).toHaveAttribute('aria-label', 'Search projects')
      expect(input).toHaveAttribute('data-testid', 'custom-search')
      expect(input).toHaveAttribute('autoComplete', 'off')
    })

    it('should forward ref to input element', () => {
      const ref = React.createRef<HTMLInputElement>()
      render(<SearchInput value="" onChange={() => {}} ref={ref} />)

      expect(ref.current).toBeInstanceOf(HTMLInputElement)
      expect(ref.current?.type).toBe('search')
    })
  })

  describe('dark mode', () => {
    it('should have proper dark mode classes', () => {
      render(<SearchInput value="" onChange={() => {}} />)
      const input = screen.getByPlaceholderText('Search...')

      // Dark mode background
      expect(input).toHaveClass('dark:bg-white/5')

      // Dark mode text
      expect(input).toHaveClass('dark:text-zinc-100')

      // Dark mode placeholder
      expect(input).toHaveClass('dark:placeholder-zinc-400')

      // Dark mode ring
      expect(input).toHaveClass('dark:ring-white/10')
      expect(input).toHaveClass('dark:hover:ring-white/20')
      expect(input).toHaveClass('dark:focus:ring-emerald-400')
    })
  })
})

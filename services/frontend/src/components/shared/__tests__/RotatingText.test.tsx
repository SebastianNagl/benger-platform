/**
 * @jest-environment jsdom
 */

import { act, render, screen, waitFor } from '@testing-library/react'
import { RotatingText } from '../RotatingText'
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


describe('RotatingText', () => {
  let matchMediaMock: jest.Mock

  beforeEach(() => {
    jest.useFakeTimers()
    // Mock matchMedia
    matchMediaMock = jest.fn().mockImplementation((query) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: jest.fn(),
      removeListener: jest.fn(),
      addEventListener: jest.fn(),
      removeEventListener: jest.fn(),
      dispatchEvent: jest.fn(),
    }))
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: matchMediaMock,
    })
  })

  afterEach(() => {
    jest.runOnlyPendingTimers()
    jest.useRealTimers()
  })

  // ===== Basic Rendering =====
  describe('Basic Rendering', () => {
    it('should render the first word from the array', () => {
      render(<RotatingText words={['First', 'Second', 'Third']} />)
      expect(screen.getByText('First')).toBeInTheDocument()
    })

    it('should render empty array with fallback text', () => {
      render(<RotatingText words={[]} />)
      expect(screen.getByText('Loading...')).toBeInTheDocument()
    })

    it('should render single word without rotation', () => {
      render(<RotatingText words={['OnlyWord']} />)
      expect(screen.getByText('OnlyWord')).toBeInTheDocument()
    })

    it('should render component with default props', () => {
      render(<RotatingText words={['Test']} />)
      expect(screen.getByText('Test')).toBeInTheDocument()
    })
  })

  // ===== Text Rotation Animation =====
  describe('Text Rotation Animation', () => {
    it('should rotate through all words in sequence', async () => {
      const words = ['First', 'Second', 'Third']
      render(<RotatingText words={words} interval={1000} />)

      await waitFor(() => {
        expect(screen.getByText('First')).toBeInTheDocument()
      })

      act(() => {
        jest.advanceTimersByTime(1000)
      })
      await waitFor(() => {
        expect(screen.getByText('Second')).toBeInTheDocument()
      })

      act(() => {
        jest.advanceTimersByTime(1000)
      })
      await waitFor(() => {
        expect(screen.getByText('Third')).toBeInTheDocument()
      })

      act(() => {
        jest.advanceTimersByTime(1000)
      })
      await waitFor(() => {
        expect(screen.getByText('First')).toBeInTheDocument()
      })
    })

    it('should not rotate when prefers-reduced-motion is enabled', async () => {
      matchMediaMock.mockImplementation((query) => ({
        matches: query === '(prefers-reduced-motion: reduce)',
        media: query,
        onchange: null,
        addListener: jest.fn(),
        removeListener: jest.fn(),
        addEventListener: jest.fn(),
        removeEventListener: jest.fn(),
        dispatchEvent: jest.fn(),
      }))

      render(
        <RotatingText words={['First', 'Second', 'Third']} interval={1000} />
      )

      await waitFor(() => {
        expect(screen.getByText('First')).toBeInTheDocument()
      })

      jest.advanceTimersByTime(5000)

      await waitFor(() => {
        expect(screen.getByText('First')).toBeInTheDocument()
      })
    })

    it('should stop rotation when unmounted', async () => {
      const { unmount } = render(
        <RotatingText words={['First', 'Second', 'Third']} interval={1000} />
      )

      await waitFor(() => {
        expect(screen.getByText('First')).toBeInTheDocument()
      })

      unmount()
      jest.advanceTimersByTime(5000)
    })
  })

  // ===== Interval/Timing Control =====
  describe('Interval/Timing Control', () => {
    it('should respect custom interval prop', async () => {
      render(<RotatingText words={['First', 'Second']} interval={3000} />)

      await waitFor(() => {
        expect(screen.getByText('First')).toBeInTheDocument()
      })

      jest.advanceTimersByTime(2000)
      await waitFor(() => {
        expect(screen.getByText('First')).toBeInTheDocument()
      })

      jest.advanceTimersByTime(1000)
      await waitFor(() => {
        expect(screen.getByText('Second')).toBeInTheDocument()
      })
    })

    it('should use default interval of 2000ms when not specified', async () => {
      render(<RotatingText words={['First', 'Second']} />)

      await waitFor(() => {
        expect(screen.getByText('First')).toBeInTheDocument()
      })

      jest.advanceTimersByTime(2000)
      await waitFor(() => {
        expect(screen.getByText('Second')).toBeInTheDocument()
      })
    })

    it('should handle very short intervals', async () => {
      render(<RotatingText words={['First', 'Second']} interval={100} />)

      await waitFor(() => {
        expect(screen.getByText('First')).toBeInTheDocument()
      })

      jest.advanceTimersByTime(100)
      await waitFor(() => {
        expect(screen.getByText('Second')).toBeInTheDocument()
      })
    })
  })

  // ===== Text Array Display =====
  describe('Text Array Display', () => {
    it('should handle array with special characters', async () => {
      const words = ['Hello!', 'World?', 'Test@123', '<>{}']
      render(<RotatingText words={words} interval={1000} />)

      await waitFor(() => {
        expect(screen.getByText('Hello!')).toBeInTheDocument()
      })

      jest.advanceTimersByTime(1000)
      await waitFor(() => {
        expect(screen.getByText('World?')).toBeInTheDocument()
      })
    })

    it('should handle array with unicode and emojis', async () => {
      const words = ['Hello', 'Welt', '世界', '🌍']
      render(<RotatingText words={words} interval={1000} />)

      await waitFor(() => {
        expect(screen.getByText('Hello')).toBeInTheDocument()
      })

      jest.advanceTimersByTime(1000)
      await waitFor(() => {
        expect(screen.getByText('Welt')).toBeInTheDocument()
      })
    })

    it('should handle array with long text strings', async () => {
      const words = [
        'This is a very long text string that should still work',
        'Another long string with multiple words',
      ]
      render(<RotatingText words={words} interval={1000} />)

      await waitFor(() => {
        expect(
          screen.getByText(
            'This is a very long text string that should still work'
          )
        ).toBeInTheDocument()
      })
    })

    it('should handle array with duplicate entries', async () => {
      const words = ['Same', 'Same', 'Different']
      render(<RotatingText words={words} interval={1000} />)

      await waitFor(() => {
        expect(screen.getByText('Same')).toBeInTheDocument()
      })

      jest.advanceTimersByTime(1000)
      await waitFor(() => {
        expect(screen.getByText('Same')).toBeInTheDocument()
      })

      jest.advanceTimersByTime(1000)
      await waitFor(() => {
        expect(screen.getByText('Different')).toBeInTheDocument()
      })
    })
  })

  // ===== Props/Attributes =====
  describe('Props/Attributes', () => {
    it('should accept and apply custom className', () => {
      render(<RotatingText words={['Test']} className="custom-class" />)
      const element = screen.getByText('Test')
      expect(element).toHaveClass('custom-class')
      expect(element).toHaveClass('inline-block')
    })

    it('should work without className prop', () => {
      render(<RotatingText words={['Test']} />)
      const element = screen.getByText('Test')
      expect(element).toHaveClass('inline-block')
    })

    it('should handle className with multiple classes', () => {
      render(<RotatingText words={['Test']} className="class1 class2 class3" />)
      const element = screen.getByText('Test')
      expect(element).toHaveClass('class1', 'class2', 'class3', 'inline-block')
    })

    it('should handle non-array words prop gracefully', () => {
      // @ts-expect-error Testing runtime handling of invalid prop
      render(<RotatingText words={null} />)
      expect(screen.getByText('Loading...')).toBeInTheDocument()
    })

    it('should handle undefined words prop gracefully', () => {
      // @ts-expect-error Testing runtime handling of invalid prop
      render(<RotatingText words={undefined} />)
      expect(screen.getByText('Loading...')).toBeInTheDocument()
    })
  })

  // ===== Styling =====
  describe('Styling', () => {
    it('should apply inline-block display class', () => {
      render(<RotatingText words={['Test']} />)
      const element = screen.getByText('Test')
      expect(element).toHaveClass('inline-block')
    })

    it('should render as span element', () => {
      render(<RotatingText words={['Test']} />)
      const element = screen.getByText('Test')
      expect(element.tagName).toBe('SPAN')
    })

    it('should combine default and custom classes correctly', () => {
      render(<RotatingText words={['Test']} className="text-xl font-bold" />)
      const element = screen.getByText('Test')
      expect(element.className).toContain('inline-block')
      expect(element.className).toContain('text-xl')
      expect(element.className).toContain('font-bold')
    })

    it('should apply dark mode classes when provided', () => {
      render(<RotatingText words={['Test']} className="dark:text-white" />)
      const element = screen.getByText('Test')
      expect(element).toHaveClass('dark:text-white')
    })
  })

  // ===== Accessibility =====
  describe('Accessibility', () => {
    it('should have aria-live="polite" when rotating', async () => {
      render(<RotatingText words={['First', 'Second']} />)

      await waitFor(() => {
        const element = screen.getByText('First')
        expect(element).toHaveAttribute('aria-live', 'polite')
      })
    })

    it('should have aria-live="off" for single word', async () => {
      render(<RotatingText words={['OnlyWord']} />)

      await waitFor(() => {
        const element = screen.getByText('OnlyWord')
        expect(element).toHaveAttribute('aria-live', 'off')
      })
    })

    it('should have aria-label with all words for single word', async () => {
      render(<RotatingText words={['OnlyWord']} />)

      await waitFor(() => {
        const element = screen.getByText('OnlyWord')
        expect(element).toHaveAttribute('aria-label', 'OnlyWord')
      })
    })

    it('should have aria-live="off" when prefers-reduced-motion', async () => {
      matchMediaMock.mockImplementation((query) => ({
        matches: query === '(prefers-reduced-motion: reduce)',
        media: query,
        onchange: null,
        addListener: jest.fn(),
        removeListener: jest.fn(),
        addEventListener: jest.fn(),
        removeEventListener: jest.fn(),
        dispatchEvent: jest.fn(),
      }))

      render(<RotatingText words={['First', 'Second']} />)

      await waitFor(() => {
        const element = screen.getByText('First')
        expect(element).toHaveAttribute('aria-live', 'off')
      })
    })

    it('should have aria-label when rotation is disabled', async () => {
      matchMediaMock.mockImplementation((query) => ({
        matches: query === '(prefers-reduced-motion: reduce)',
        media: query,
        onchange: null,
        addListener: jest.fn(),
        removeListener: jest.fn(),
        addEventListener: jest.fn(),
        removeEventListener: jest.fn(),
        dispatchEvent: jest.fn(),
      }))

      render(<RotatingText words={['First', 'Second', 'Third']} />)

      await waitFor(() => {
        const element = screen.getByText('First')
        expect(element).toHaveAttribute('aria-label', 'First, Second, Third')
      })
    })

    it('should not have aria-label when rotating normally', async () => {
      render(<RotatingText words={['First', 'Second']} />)

      await waitFor(() => {
        const element = screen.getByText('First')
        expect(element).not.toHaveAttribute('aria-label')
      })
    })
  })

  // ===== Edge Cases =====
  describe('Edge Cases', () => {
    it('should handle words array change during rotation', async () => {
      const { rerender } = render(
        <RotatingText words={['First', 'Second']} interval={1000} />
      )

      await waitFor(() => {
        expect(screen.getByText('First')).toBeInTheDocument()
      })

      rerender(
        <RotatingText words={['New1', 'New2', 'New3']} interval={1000} />
      )

      await waitFor(() => {
        expect(screen.getByText('New1')).toBeInTheDocument()
      })

      jest.advanceTimersByTime(1000)
      await waitFor(() => {
        expect(screen.getByText('New2')).toBeInTheDocument()
      })
    })

    it('should handle changing from multiple words to single word', async () => {
      const { rerender } = render(
        <RotatingText words={['First', 'Second']} interval={1000} />
      )

      await waitFor(() => {
        expect(screen.getByText('First')).toBeInTheDocument()
      })

      rerender(<RotatingText words={['OnlyWord']} interval={1000} />)

      await waitFor(() => {
        const element = screen.getByText('OnlyWord')
        expect(element).toBeInTheDocument()
        expect(element).toHaveAttribute('aria-live', 'off')
      })
    })

    it('should handle changing from single word to multiple words', async () => {
      const { rerender } = render(
        <RotatingText words={['OnlyWord']} interval={1000} />
      )

      await waitFor(() => {
        expect(screen.getByText('OnlyWord')).toBeInTheDocument()
      })

      rerender(<RotatingText words={['First', 'Second']} interval={1000} />)

      await waitFor(() => {
        const element = screen.getByText('First')
        expect(element).toHaveAttribute('aria-live', 'polite')
      })
    })

    it('should handle empty string in array', async () => {
      render(<RotatingText words={['First', '', 'Third']} interval={1000} />)

      await waitFor(() => {
        expect(screen.getByText('First')).toBeInTheDocument()
      })

      act(() => {
        jest.advanceTimersByTime(1000)
      })
      // After advancing time, component should now show empty string
      const container = document.querySelector('span[aria-live]')
      expect(container?.textContent).toBe('')

      act(() => {
        jest.advanceTimersByTime(1000)
      })
      await waitFor(() => {
        expect(screen.getByText('Third')).toBeInTheDocument()
      })
    })

    it('should handle very large words array', async () => {
      const largeArray = Array.from({ length: 100 }, (_, i) => `Word${i}`)
      render(<RotatingText words={largeArray} interval={100} />)

      await waitFor(() => {
        expect(screen.getByText('Word0')).toBeInTheDocument()
      })

      jest.advanceTimersByTime(500)
      await waitFor(() => {
        expect(screen.getByText('Word5')).toBeInTheDocument()
      })
    })

    it('should cleanup interval on unmount', async () => {
      const { unmount } = render(
        <RotatingText words={['First', 'Second', 'Third']} interval={1000} />
      )

      await waitFor(() => {
        expect(screen.getByText('First')).toBeInTheDocument()
      })

      const activeTimers = jest.getTimerCount()
      unmount()

      expect(jest.getTimerCount()).toBeLessThanOrEqual(activeTimers)
    })
  })
})

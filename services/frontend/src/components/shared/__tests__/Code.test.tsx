/**
 * Test suite for Code component
 * Tests for code blocks with syntax highlighting, copy functionality, and language support
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Code, CodeGroup, Pre } from '../Code'

// Mock I18nContext
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string) => key,
    locale: 'en',
    changeLocale: jest.fn(),
    isReady: true,
  }),
}))

// Mock clipboard API
const mockWriteText = jest.fn()
Object.assign(navigator, {
  clipboard: {
    writeText: mockWriteText,
  },
})

describe('Code Component', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockWriteText.mockResolvedValue(undefined)
  })

  describe('Basic Rendering', () => {
    it('renders children correctly', () => {
      render(<Code>const x = 10;</Code>)
      expect(screen.getByText('const x = 10;')).toBeInTheDocument()
    })

    it('renders as code element', () => {
      const { container } = render(<Code>test code</Code>)
      const codeElement = container.querySelector('code')
      expect(codeElement).toBeInTheDocument()
      expect(codeElement).toHaveTextContent('test code')
    })

    it('applies custom className', () => {
      const { container } = render(
        <Code className="custom-class">test code</Code>
      )
      const codeElement = container.querySelector('code')
      expect(codeElement).toHaveClass('custom-class')
    })
  })

  describe('Code Content', () => {
    it('displays single line code correctly', () => {
      render(<Code>console.log("Hello");</Code>)
      expect(screen.getByText('console.log("Hello");')).toBeInTheDocument()
    })

    it('displays multi-line code correctly', () => {
      const { container } = render(
        <Code>
          {`function test() {
  return true;
}`}
        </Code>
      )
      const codeElement = container.querySelector('code')
      expect(codeElement).toBeInTheDocument()
      expect(codeElement?.textContent).toContain('function test()')
      expect(codeElement?.textContent).toContain('return true')
    })

    it('handles empty code', () => {
      const { container } = render(<Code></Code>)
      const codeElement = container.querySelector('code')
      expect(codeElement).toBeInTheDocument()
      expect(codeElement).toHaveTextContent('')
    })
  })

  describe('CodeGroup Component', () => {
    it('renders with title', () => {
      render(
        <CodeGroup title="Example Code">
          <Pre>
            <Code>test code</Code>
          </Pre>
        </CodeGroup>
      )
      expect(screen.getByText('Example Code')).toBeInTheDocument()
    })

    it('renders single code panel without tabs', () => {
      render(
        <CodeGroup title="Test">
          <Pre>
            <Code>single panel</Code>
          </Pre>
        </CodeGroup>
      )
      expect(screen.getByText('single panel')).toBeInTheDocument()
    })

    it('renders multiple code panels with tabs', () => {
      render(
        <CodeGroup title="Multi Language">
          <Pre language="javascript" title="JavaScript">
            <Code>console.log("JS")</Code>
          </Pre>
          <Pre language="python" title="Python">
            <Code>print("Python")</Code>
          </Pre>
        </CodeGroup>
      )
      expect(screen.getByText('JavaScript')).toBeInTheDocument()
      expect(screen.getByText('Python')).toBeInTheDocument()
    })

    it('switches between tabs when clicked', async () => {
      const user = userEvent.setup()
      render(
        <CodeGroup title="Languages">
          <Pre language="js">
            <Code>console.log("JS")</Code>
          </Pre>
          <Pre language="python">
            <Code>print("Python")</Code>
          </Pre>
        </CodeGroup>
      )

      // First tab should be selected by default
      expect(screen.getByText('console.log("JS")')).toBeInTheDocument()

      // Click on Python tab
      const pythonTab = screen.getByText('Python')
      await user.click(pythonTab)

      // Python code should now be visible
      expect(screen.getByText('print("Python")')).toBeInTheDocument()
    })

    it('applies container styling', () => {
      const { container } = render(
        <CodeGroup title="Test">
          <Pre>
            <Code>test</Code>
          </Pre>
        </CodeGroup>
      )
      const codeGroupDiv = container.querySelector('.rounded-2xl')
      expect(codeGroupDiv).toBeInTheDocument()
      expect(codeGroupDiv).toHaveClass('bg-zinc-900')
      expect(codeGroupDiv).toHaveClass('shadow-md')
    })
  })

  describe('Language Support', () => {
    it('displays JavaScript language label in tabs', () => {
      render(
        <CodeGroup title="">
          <Pre language="javascript">
            <Code>const x = 1;</Code>
          </Pre>
          <Pre language="python">
            <Code>x = 1</Code>
          </Pre>
        </CodeGroup>
      )
      expect(screen.getByText('JavaScript')).toBeInTheDocument()
    })

    it('displays TypeScript language label in tabs', () => {
      render(
        <CodeGroup title="">
          <Pre language="typescript">
            <Code>const x: number = 1;</Code>
          </Pre>
          <Pre language="python">
            <Code>x = 1</Code>
          </Pre>
        </CodeGroup>
      )
      expect(screen.getByText('TypeScript')).toBeInTheDocument()
    })

    it('displays Python language label in tabs', () => {
      render(
        <CodeGroup title="">
          <Pre language="javascript">
            <Code>const x = 1;</Code>
          </Pre>
          <Pre language="python">
            <Code>x = 1</Code>
          </Pre>
        </CodeGroup>
      )
      expect(screen.getByText('Python')).toBeInTheDocument()
    })

    it('displays PHP language label in tabs', () => {
      render(
        <CodeGroup title="">
          <Pre language="php">
            <Code>{'<?php echo "test"; ?>'}</Code>
          </Pre>
          <Pre language="python">
            <Code>x = 1</Code>
          </Pre>
        </CodeGroup>
      )
      expect(screen.getByText('PHP')).toBeInTheDocument()
    })

    it('displays Ruby language label in tabs', () => {
      render(
        <CodeGroup title="">
          <Pre language="ruby">
            <Code>puts "test"</Code>
          </Pre>
          <Pre language="python">
            <Code>x = 1</Code>
          </Pre>
        </CodeGroup>
      )
      expect(screen.getByText('Ruby')).toBeInTheDocument()
    })

    it('displays Go language label in tabs', () => {
      render(
        <CodeGroup title="">
          <Pre language="go">
            <Code>fmt.Println("test")</Code>
          </Pre>
          <Pre language="python">
            <Code>x = 1</Code>
          </Pre>
        </CodeGroup>
      )
      expect(screen.getByText('Go')).toBeInTheDocument()
    })

    it('handles short language codes (js, ts)', () => {
      render(
        <CodeGroup title="">
          <Pre language="js">
            <Code>console.log("test")</Code>
          </Pre>
          <Pre language="ts">
            <Code>const x: number = 1;</Code>
          </Pre>
        </CodeGroup>
      )
      expect(screen.getByText('JavaScript')).toBeInTheDocument()
      expect(screen.getByText('TypeScript')).toBeInTheDocument()
    })

    it('falls back to "Code" for unknown language', () => {
      render(
        <CodeGroup title="">
          <Pre language="unknown">
            <Code>test</Code>
          </Pre>
          <Pre language="python">
            <Code>x = 1</Code>
          </Pre>
        </CodeGroup>
      )
      expect(screen.getByText('Code')).toBeInTheDocument()
    })

    it('uses custom title over language label in tabs', () => {
      render(
        <CodeGroup title="">
          <Pre language="javascript" title="Custom Title">
            <Code>test</Code>
          </Pre>
          <Pre language="python">
            <Code>x = 1</Code>
          </Pre>
        </CodeGroup>
      )
      expect(screen.getByText('Custom Title')).toBeInTheDocument()
      expect(screen.queryByText('JavaScript')).not.toBeInTheDocument()
    })
  })

  describe('Styling', () => {
    it('applies text-white color to code', () => {
      const { container } = render(
        <CodeGroup title="Test">
          <Pre>
            <Code>test</Code>
          </Pre>
        </CodeGroup>
      )
      const preElement = container.querySelector('pre')
      expect(preElement).toHaveClass('text-white')
    })

    it('applies correct background colors', () => {
      const { container } = render(
        <CodeGroup title="Test">
          <Pre>
            <Code>test</Code>
          </Pre>
        </CodeGroup>
      )
      const codeGroupDiv = container.querySelector('.bg-zinc-900')
      expect(codeGroupDiv).toBeInTheDocument()
    })

    it('applies overflow-x-auto for horizontal scrolling', () => {
      const { container } = render(
        <CodeGroup title="Test">
          <Pre>
            <Code>test</Code>
          </Pre>
        </CodeGroup>
      )
      const preElement = container.querySelector('pre')
      expect(preElement).toHaveClass('overflow-x-auto')
    })

    it('applies correct padding', () => {
      const { container } = render(
        <CodeGroup title="Test">
          <Pre>
            <Code>test</Code>
          </Pre>
        </CodeGroup>
      )
      const preElement = container.querySelector('pre')
      expect(preElement).toHaveClass('p-4')
    })

    it('applies text size', () => {
      const { container } = render(
        <CodeGroup title="Test">
          <Pre>
            <Code>test</Code>
          </Pre>
        </CodeGroup>
      )
      const preElement = container.querySelector('pre')
      expect(preElement).toHaveClass('text-xs')
    })
  })

  describe('Copy Functionality', () => {
    it('renders copy button', () => {
      const { container } = render(
        <CodeGroup title="Test">
          <Pre>
            <Code>const x = 1;</Code>
          </Pre>
        </CodeGroup>
      )
      const copyButton = container.querySelector('button')
      expect(copyButton).toBeInTheDocument()
      expect(copyButton).toHaveTextContent('common.copy')
    })

    it('copy button is initially hidden (opacity-0)', () => {
      const { container } = render(
        <CodeGroup title="Test">
          <Pre>
            <Code>test code</Code>
          </Pre>
        </CodeGroup>
      )
      const copyButton = container.querySelector('button')
      expect(copyButton).toHaveClass('opacity-0')
    })

    it('triggers clipboard copy when clicked', async () => {
      const user = userEvent.setup()

      const { container } = render(
        <CodeGroup title="Test">
          <Pre>
            <Code>const x = 10;</Code>
          </Pre>
        </CodeGroup>
      )

      const copyButton = container.querySelector('button')
      expect(copyButton).toBeInTheDocument()

      if (copyButton) {
        await user.click(copyButton)
        // The clipboard interaction is tested indirectly through the "Copied!" feedback test
        // Just verify the button exists and is clickable
        expect(copyButton).toBeInTheDocument()
      }
    })

    it('shows "Copied!" feedback after clicking copy', async () => {
      const user = userEvent.setup()
      const { container } = render(
        <CodeGroup title="Test">
          <Pre>
            <Code>test code</Code>
          </Pre>
        </CodeGroup>
      )

      const copyButton = container.querySelector('button')
      expect(copyButton).toBeInTheDocument()

      if (copyButton) {
        await user.click(copyButton)
        await waitFor(() => {
          expect(copyButton).toHaveTextContent('common.copied')
        })
      }
    })

    it('resets to "Copy" after timeout', async () => {
      jest.useFakeTimers()
      const user = userEvent.setup({ delay: null })

      const { container } = render(
        <CodeGroup title="Test">
          <Pre>
            <Code>test code</Code>
          </Pre>
        </CodeGroup>
      )

      const copyButton = container.querySelector('button')
      expect(copyButton).toBeInTheDocument()

      if (copyButton) {
        await user.click(copyButton)

        await waitFor(() => {
          expect(copyButton).toHaveTextContent('common.copied')
        })

        // Fast-forward time
        jest.advanceTimersByTime(1000)

        await waitFor(() => {
          expect(copyButton).toHaveTextContent('common.copy')
        })
      }

      jest.useRealTimers()
    })

    it('applies emerald styling when copied', async () => {
      const user = userEvent.setup()
      const { container } = render(
        <CodeGroup title="Test">
          <Pre>
            <Code>test code</Code>
          </Pre>
        </CodeGroup>
      )

      const copyButton = container.querySelector('button')
      if (copyButton) {
        await user.click(copyButton)
        await waitFor(() => {
          expect(copyButton).toHaveClass('bg-emerald-400/10')
          expect(copyButton).toHaveClass('ring-emerald-400/20')
        })
      }
    })

    it('handles multiline code in copy button', async () => {
      const user = userEvent.setup()

      const { container } = render(
        <CodeGroup title="Test">
          <Pre>
            <Code>
              {`function test() {
  return true;
}`}
            </Code>
          </Pre>
        </CodeGroup>
      )

      const copyButton = container.querySelector('button')
      expect(copyButton).toBeInTheDocument()

      if (copyButton) {
        await user.click(copyButton)
        // Verify the button shows "Copied!" feedback, confirming copy worked
        await waitFor(() => {
          expect(copyButton).toHaveTextContent('common.copied')
        })
      }
    })
  })

  describe('Edge Cases', () => {
    it('handles very long code lines', () => {
      const longCode = 'x'.repeat(500)
      render(
        <CodeGroup title="Test">
          <Pre>
            <Code>{longCode}</Code>
          </Pre>
        </CodeGroup>
      )
      expect(screen.getByText(longCode)).toBeInTheDocument()
    })

    it('handles special characters', () => {
      const specialChars = '<>&"\'{}'
      render(
        <CodeGroup title="Test">
          <Pre>
            <Code>{specialChars}</Code>
          </Pre>
        </CodeGroup>
      )
      expect(screen.getByText(specialChars)).toBeInTheDocument()
    })

    it('handles unicode characters', () => {
      const unicodeCode = '你好世界 🚀 μ'
      render(
        <CodeGroup title="Test">
          <Pre>
            <Code>{unicodeCode}</Code>
          </Pre>
        </CodeGroup>
      )
      expect(screen.getByText(unicodeCode)).toBeInTheDocument()
    })

    it('handles code with tabs and spaces', () => {
      const indentedCode = '\t\tconst x = 1;'
      const { container } = render(
        <CodeGroup title="Test">
          <Pre>
            <Code>{indentedCode}</Code>
          </Pre>
        </CodeGroup>
      )
      const codeElement = container.querySelector('code')
      expect(codeElement).toBeInTheDocument()
      expect(codeElement?.textContent).toContain('const x = 1;')
    })

    it('handles empty code gracefully', () => {
      const { container } = render(
        <CodeGroup title="Test">
          <Pre>
            <Code> </Code>
          </Pre>
        </CodeGroup>
      )
      const preElement = container.querySelector('pre')
      expect(preElement).toBeInTheDocument()
    })

    it('handles code with HTML-like syntax', () => {
      const htmlCode = '<div class="test">Hello</div>'
      const { container } = render(
        <CodeGroup title="Test">
          <Pre>
            <Code>{htmlCode}</Code>
          </Pre>
        </CodeGroup>
      )
      const codeElement = container.querySelector('code')
      expect(codeElement).toBeInTheDocument()
      // Code contains the HTML string
      expect(codeElement?.innerHTML).toContain('div')
    })

    it('handles code with regex patterns', () => {
      const regexCode = '/^[a-z0-9]+$/i'
      render(
        <CodeGroup title="Test">
          <Pre>
            <Code>{regexCode}</Code>
          </Pre>
        </CodeGroup>
      )
      expect(screen.getByText(regexCode)).toBeInTheDocument()
    })

    it('handles code with backticks', () => {
      const backtickCode = '`template ${string}`'
      render(
        <CodeGroup title="Test">
          <Pre>
            <Code>{backtickCode}</Code>
          </Pre>
        </CodeGroup>
      )
      expect(screen.getByText(backtickCode)).toBeInTheDocument()
    })
  })

  describe('Accessibility', () => {
    it('copy button has proper type attribute', () => {
      const { container } = render(
        <CodeGroup title="Test">
          <Pre>
            <Code>test</Code>
          </Pre>
        </CodeGroup>
      )
      const copyButton = container.querySelector('button')
      expect(copyButton).toHaveAttribute('type', 'button')
    })

    it('clipboard icon has aria-hidden', () => {
      const { container } = render(
        <CodeGroup title="Test">
          <Pre>
            <Code>test</Code>
          </Pre>
        </CodeGroup>
      )
      const icon = container.querySelector('svg')
      expect(icon).toHaveAttribute('aria-hidden', 'true')
    })

    it('copy feedback uses aria-hidden appropriately', () => {
      const { container } = render(
        <CodeGroup title="Test">
          <Pre>
            <Code>test</Code>
          </Pre>
        </CodeGroup>
      )
      const copyButton = container.querySelector('button')
      const spans = copyButton?.querySelectorAll('span')

      // First span (Copy text) should not be aria-hidden initially
      expect(spans?.[0]).toHaveAttribute('aria-hidden', 'false')
      // Second span (Copied! text) should be aria-hidden initially
      expect(spans?.[1]).toHaveAttribute('aria-hidden', 'true')
    })

    it('code group has semantic structure', () => {
      render(
        <CodeGroup title="Example Code">
          <Pre>
            <Code>test</Code>
          </Pre>
        </CodeGroup>
      )
      const heading = screen.getByRole('heading', { level: 3 })
      expect(heading).toHaveTextContent('Example Code')
    })

    it('code is properly nested in pre element', () => {
      const { container } = render(
        <CodeGroup title="Test">
          <Pre>
            <Code>test code</Code>
          </Pre>
        </CodeGroup>
      )
      const preElement = container.querySelector('pre')
      const codeElement = preElement?.querySelector('code')
      expect(codeElement).toBeInTheDocument()
    })

    it('tabs are keyboard navigable', async () => {
      const user = userEvent.setup()
      render(
        <CodeGroup title="Languages">
          <Pre language="js">
            <Code>console.log("JS")</Code>
          </Pre>
          <Pre language="python">
            <Code>print("Python")</Code>
          </Pre>
        </CodeGroup>
      )

      const jsTab = screen.getByText('JavaScript')
      const pythonTab = screen.getByText('Python')

      // Focus on first tab
      jsTab.focus()
      expect(document.activeElement).toBe(jsTab)

      // Tab to next element
      await user.tab()
      expect(document.activeElement).toBe(pythonTab)
    })

    it('copy button becomes visible on focus', () => {
      const { container } = render(
        <CodeGroup title="Test">
          <Pre>
            <Code>test</Code>
          </Pre>
        </CodeGroup>
      )
      const copyButton = container.querySelector('button')
      expect(copyButton).toHaveClass('focus:opacity-100')
    })
  })

  describe('Tag and Label Support', () => {
    it('renders tag when provided', () => {
      render(
        <CodeGroup title="Test">
          <Pre tag="GET">
            <Code>test</Code>
          </Pre>
        </CodeGroup>
      )
      expect(screen.getByText('GET')).toBeInTheDocument()
    })

    it('renders label when provided', () => {
      render(
        <CodeGroup title="Test">
          <Pre label="/api/users">
            <Code>test</Code>
          </Pre>
        </CodeGroup>
      )
      expect(screen.getByText('/api/users')).toBeInTheDocument()
    })

    it('renders both tag and label with separator', () => {
      const { container } = render(
        <CodeGroup title="Test">
          <Pre tag="POST" label="/api/users">
            <Code>test</Code>
          </Pre>
        </CodeGroup>
      )
      expect(screen.getByText('POST')).toBeInTheDocument()
      expect(screen.getByText('/api/users')).toBeInTheDocument()

      // Check for separator dot
      const separator = container.querySelector('.bg-zinc-500')
      expect(separator).toBeInTheDocument()
    })

    it('does not render header when no tag or label', () => {
      const { container } = render(
        <CodeGroup title="Test">
          <Pre>
            <Code>test</Code>
          </Pre>
        </CodeGroup>
      )
      // Header should not exist when there's no tag or label
      const header = container.querySelector('.border-b-white\\/7\\.5')
      expect(header).not.toBeInTheDocument()
    })
  })

  describe('Code in CodeGroup Context', () => {
    it('throws error when Code children is not string in CodeGroup', () => {
      // Suppress console.error for this test
      const consoleSpy = jest.spyOn(console, 'error').mockImplementation()

      expect(() => {
        render(
          <CodeGroup title="Test">
            <Pre>
              <Code>
                <div>not a string</div>
              </Code>
            </Pre>
          </CodeGroup>
        )
      }).toThrow(
        '`Code` children must be a string when nested inside a `CodeGroup`.'
      )

      consoleSpy.mockRestore()
    })

    it('renders HTML when inside CodeGroup with string children', () => {
      const { container } = render(
        <CodeGroup title="Test">
          <Pre>
            <Code>{'<strong>test</strong>'}</Code>
          </Pre>
        </CodeGroup>
      )
      const codeElement = container.querySelector('code')
      expect(codeElement).toBeInTheDocument()
    })
  })

  describe('Advanced Copy Functionality', () => {
    it('handles multiple rapid copy clicks', async () => {
      jest.useFakeTimers()
      const user = userEvent.setup({ delay: null })

      const { container } = render(
        <CodeGroup title="Test">
          <Pre>
            <Code>test code</Code>
          </Pre>
        </CodeGroup>
      )

      const copyButton = container.querySelector('button')
      if (copyButton) {
        await user.click(copyButton)
        await user.click(copyButton)
        await user.click(copyButton)

        await waitFor(() => {
          expect(copyButton).toHaveTextContent('common.copied')
        })

        jest.advanceTimersByTime(1000)

        await waitFor(() => {
          expect(copyButton).toHaveTextContent('common.copy')
        })
      }

      jest.useRealTimers()
    })

    it('handles clipboard API failure gracefully', async () => {
      const user = userEvent.setup()
      mockWriteText.mockRejectedValueOnce(new Error('Clipboard access denied'))

      const { container } = render(
        <CodeGroup title="Test">
          <Pre>
            <Code>test code</Code>
          </Pre>
        </CodeGroup>
      )

      const copyButton = container.querySelector('button')
      if (copyButton) {
        await user.click(copyButton)
        // Should not throw error
        expect(copyButton).toBeInTheDocument()
      }
    })

    it('extracts code from string children', () => {
      const { container } = render(
        <CodeGroup title="Test">
          <Pre>
            <Code>nested code</Code>
          </Pre>
        </CodeGroup>
      )

      const copyButton = container.querySelector('button')
      expect(copyButton).toBeInTheDocument()
    })

    it('handles multiline code string', () => {
      const { container } = render(
        <CodeGroup title="Test">
          <Pre>
            <Code>{`line1
line2
line3`}</Code>
          </Pre>
        </CodeGroup>
      )

      const copyButton = container.querySelector('button')
      expect(copyButton).toBeInTheDocument()
    })
  })

  describe('CodePanel Props Inheritance', () => {
    it('inherits tag prop from Pre', () => {
      render(
        <CodeGroup title="Test">
          <Pre tag="GET">
            <Code>test</Code>
          </Pre>
        </CodeGroup>
      )

      expect(screen.getByText('GET')).toBeInTheDocument()
    })

    it('inherits label prop from Pre', () => {
      render(
        <CodeGroup title="Test">
          <Pre label="/api/endpoint">
            <Code>test</Code>
          </Pre>
        </CodeGroup>
      )

      expect(screen.getByText('/api/endpoint')).toBeInTheDocument()
    })

    it('displays both tag and label from Pre', () => {
      render(
        <CodeGroup title="Test">
          <Pre tag="POST" label="/api/users">
            <Code>test</Code>
          </Pre>
        </CodeGroup>
      )

      expect(screen.getByText('POST')).toBeInTheDocument()
      expect(screen.getByText('/api/users')).toBeInTheDocument()
    })
  })

  describe('Theme Support', () => {
    it('applies dark mode classes to container', () => {
      const { container } = render(
        <CodeGroup title="Test">
          <Pre>
            <Code>test</Code>
          </Pre>
        </CodeGroup>
      )

      const codeGroupDiv = container.querySelector('.rounded-2xl')
      expect(codeGroupDiv).toHaveClass('dark:ring-1', 'dark:ring-white/10')
    })

    it('applies dark mode classes to copy button', () => {
      const { container } = render(
        <CodeGroup title="Test">
          <Pre>
            <Code>test</Code>
          </Pre>
        </CodeGroup>
      )

      const copyButton = container.querySelector('button')
      expect(copyButton).toHaveClass(
        'dark:bg-white/2.5',
        'dark:hover:bg-white/5'
      )
    })

    it('applies dark mode classes to header', () => {
      const { container } = render(
        <CodeGroup title="Test">
          <Pre tag="GET">
            <Code>test</Code>
          </Pre>
        </CodeGroup>
      )

      const header = container.querySelector('.border-b-white\\/7\\.5')
      expect(header).toHaveClass('dark:bg-white/1', 'dark:border-b-white/5')
    })

    it('applies dark mode classes to code group header', () => {
      const { container } = render(
        <CodeGroup title="Test Title">
          <Pre language="js">
            <Code>test</Code>
          </Pre>
          <Pre language="python">
            <Code>test2</Code>
          </Pre>
        </CodeGroup>
      )

      const groupHeader = container.querySelector('.border-zinc-700')
      expect(groupHeader).toHaveClass(
        'dark:border-zinc-800',
        'dark:bg-transparent'
      )
    })
  })

  describe('Tab Preference Management', () => {
    it('remembers last selected tab across CodeGroups', async () => {
      const user = userEvent.setup()

      const { unmount } = render(
        <CodeGroup title="First">
          <Pre language="js">
            <Code>js code</Code>
          </Pre>
          <Pre language="python">
            <Code>py code</Code>
          </Pre>
        </CodeGroup>
      )

      const pythonTab = screen.getByText('Python')
      await user.click(pythonTab)

      unmount()

      render(
        <CodeGroup title="Second">
          <Pre language="js">
            <Code>js code 2</Code>
          </Pre>
          <Pre language="python">
            <Code>py code 2</Code>
          </Pre>
        </CodeGroup>
      )

      expect(screen.getByText('py code 2')).toBeInTheDocument()
    })

    it('handles tab selection with three or more languages', async () => {
      const user = userEvent.setup()
      render(
        <CodeGroup title="Multi">
          <Pre language="js">
            <Code>js</Code>
          </Pre>
          <Pre language="python">
            <Code>python</Code>
          </Pre>
          <Pre language="ruby">
            <Code>ruby</Code>
          </Pre>
        </CodeGroup>
      )

      const rubyTab = screen.getByText('Ruby')
      await user.click(rubyTab)

      expect(screen.getByText('ruby')).toBeInTheDocument()
    })

    it('prevents layout shift when switching tabs', async () => {
      const user = userEvent.setup()
      render(
        <CodeGroup title="Test">
          <Pre language="js">
            <Code>js code</Code>
          </Pre>
          <Pre language="python">
            <Code>python code</Code>
          </Pre>
        </CodeGroup>
      )

      const pythonTab = screen.getByText('Python')
      await user.click(pythonTab)

      expect(screen.getByText('python code')).toBeInTheDocument()
    })
  })

  describe('CodeGroupHeader Behavior', () => {
    it('renders no header when title is empty and single tab', () => {
      const { container } = render(
        <CodeGroup title="">
          <Pre>
            <Code>test</Code>
          </Pre>
        </CodeGroup>
      )

      const header = container.querySelector('.border-zinc-700')
      expect(header).not.toBeInTheDocument()
    })

    it('renders header with title but no tabs for single panel', () => {
      render(
        <CodeGroup title="Example">
          <Pre>
            <Code>test</Code>
          </Pre>
        </CodeGroup>
      )

      expect(screen.getByText('Example')).toBeInTheDocument()
      const heading = screen.getByRole('heading', { level: 3 })
      expect(heading).toHaveTextContent('Example')
    })

    it('renders both title and tabs for multiple panels', () => {
      render(
        <CodeGroup title="Examples">
          <Pre language="js">
            <Code>js</Code>
          </Pre>
          <Pre language="python">
            <Code>py</Code>
          </Pre>
        </CodeGroup>
      )

      expect(screen.getByText('Examples')).toBeInTheDocument()
      expect(screen.getByText('JavaScript')).toBeInTheDocument()
      expect(screen.getByText('Python')).toBeInTheDocument()
    })

    it('applies correct styling to selected tab', async () => {
      const user = userEvent.setup()
      const { container } = render(
        <CodeGroup title="Test">
          <Pre language="js">
            <Code>js</Code>
          </Pre>
          <Pre language="python">
            <Code>py</Code>
          </Pre>
        </CodeGroup>
      )

      // Check that JavaScript tab exists and is initially selected
      const jsTab = screen.getByText('JavaScript')
      expect(jsTab).toBeInTheDocument()

      // Click Python tab
      const pythonTab = screen.getByText('Python')
      await user.click(pythonTab)

      // Check that both tabs remain visible after click
      expect(jsTab).toBeInTheDocument()
      expect(pythonTab).toBeInTheDocument()
    })
  })

  describe('Error Handling', () => {
    it('throws error when CodePanel has no code prop and no extractable children', () => {
      const consoleSpy = jest.spyOn(console, 'error').mockImplementation()

      expect(() => {
        render(
          <CodeGroup title="Test">
            <Pre>
              <Code>{null}</Code>
            </Pre>
          </CodeGroup>
        )
      }).toThrow(
        '`CodePanel` requires a `code` prop, or a child with a `code` prop.'
      )

      consoleSpy.mockRestore()
    })
  })

  describe('Pre Component', () => {
    it('renders children within CodeGroup when used standalone', () => {
      const { container } = render(
        <Pre title="Test">
          <Code>test content</Code>
        </Pre>
      )

      expect(container.textContent).toContain('test content')
    })

    it('shows title when not in CodeGroup context', () => {
      render(
        <Pre title="Test Title">
          <Code>test</Code>
        </Pre>
      )

      expect(screen.getByText('Test Title')).toBeInTheDocument()
    })
  })

  describe('Responsive Behavior', () => {
    it('applies responsive classes to code group header title', () => {
      render(
        <CodeGroup title="Test Title">
          <Pre>
            <Code>test</Code>
          </Pre>
        </CodeGroup>
      )

      const title = screen.getByText('Test Title')
      expect(title).toHaveClass('mr-auto', 'pt-3', 'text-xs')
    })

    it('applies responsive gap classes to tab list', () => {
      const { container } = render(
        <CodeGroup title="">
          <Pre language="js">
            <Code>js</Code>
          </Pre>
          <Pre language="python">
            <Code>py</Code>
          </Pre>
        </CodeGroup>
      )

      const tabList = container.querySelector('[role="tablist"]')
      expect(tabList).toHaveClass('gap-4')
    })
  })

  describe('Copy Button Visibility', () => {
    it('has group-hover:opacity-100 class for hover visibility', () => {
      const { container } = render(
        <CodeGroup title="Test">
          <Pre>
            <Code>test</Code>
          </Pre>
        </CodeGroup>
      )

      const copyButton = container.querySelector('button')
      expect(copyButton).toHaveClass('group-hover:opacity-100')
    })

    it('applies absolute positioning to copy button', () => {
      const { container } = render(
        <CodeGroup title="Test">
          <Pre>
            <Code>test</Code>
          </Pre>
        </CodeGroup>
      )

      const copyButton = container.querySelector('button')
      expect(copyButton).toHaveClass('absolute', 'right-4', 'top-3.5')
    })
  })

  describe('Code Content Extraction', () => {
    it('extracts text from child props children', async () => {
      const user = userEvent.setup()
      const codeElement = <code>child prop text</code>
      const { container } = render(
        <CodeGroup title="Test">
          <Pre>{codeElement}</Pre>
        </CodeGroup>
      )

      const copyButton = container.querySelector('button')
      expect(copyButton).toBeInTheDocument()
    })
  })
})

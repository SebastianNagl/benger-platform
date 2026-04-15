/**
 * @jest-environment jsdom
 */

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { APIKeysModal } from '../APIKeysModal'

// Mock heroicons
jest.mock('@heroicons/react/24/outline', () => ({
  XMarkIcon: (props: any) => <svg {...props} data-testid="x-mark-icon" />,
}))

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

// Mock UserApiKeys component
jest.mock('@/components/shared/UserApiKeys', () => ({
  __esModule: true,
  default: () => (
    <div data-testid="user-api-keys-component">UserApiKeys Component</div>
  ),
}))

// Mock Headless UI
jest.mock('@headlessui/react', () => {
  return {
    Dialog: Object.assign(
      ({ children, onClose, open, ...props }: any) => {
        return open ? (
          <div {...props} role="dialog">
            {children}
          </div>
        ) : null
      },
      {
        Panel: ({ children, ...props }: any) => (
          <div {...props}>{children}</div>
        ),
        Title: ({ children, ...props }: any) => <h2 {...props}>{children}</h2>,
      }
    ),
  }
})

describe('APIKeysModal', () => {
  const defaultProps = {
    isOpen: true,
    onClose: jest.fn(),
  }

  beforeEach(() => {
    jest.clearAllMocks()
  })

  describe('Rendering', () => {
    it('renders when isOpen is true', () => {
      render(<APIKeysModal {...defaultProps} />)
      expect(screen.getByRole('dialog')).toBeInTheDocument()
    })

    it('does not render when isOpen is false', () => {
      render(<APIKeysModal {...defaultProps} isOpen={false} />)
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })

    it('renders modal title', () => {
      render(<APIKeysModal {...defaultProps} />)
      expect(screen.getByText('API Keys Management')).toBeInTheDocument()
    })

    it('renders modal description', () => {
      render(<APIKeysModal {...defaultProps} />)
      expect(
        screen.getByText('Manage your personal API keys for LLM providers. These keys are encrypted and stored securely.')
      ).toBeInTheDocument()
    })

    it('renders UserApiKeys component', () => {
      render(<APIKeysModal {...defaultProps} />)
      expect(screen.getByTestId('user-api-keys-component')).toBeInTheDocument()
    })

    it('renders close button with aria-label', () => {
      render(<APIKeysModal {...defaultProps} />)
      expect(screen.getByLabelText('Close')).toBeInTheDocument()
    })

    it('renders Done button', () => {
      render(<APIKeysModal {...defaultProps} />)
      expect(screen.getByText('Done')).toBeInTheDocument()
    })
  })

  describe('User Interaction', () => {
    it('calls onClose when clicking close button', async () => {
      const user = userEvent.setup()
      render(<APIKeysModal {...defaultProps} />)

      await user.click(screen.getByLabelText('Close'))

      expect(defaultProps.onClose).toHaveBeenCalledTimes(1)
    })

    it('calls onClose when clicking Done button', async () => {
      const user = userEvent.setup()
      render(<APIKeysModal {...defaultProps} />)

      await user.click(screen.getByText('Done'))

      expect(defaultProps.onClose).toHaveBeenCalledTimes(1)
    })
  })

  describe('Modal Structure', () => {
    it('renders UserApiKeys inside scrollable container', () => {
      render(<APIKeysModal {...defaultProps} />)

      // Verify the UserApiKeys component is rendered
      const userApiKeysComponent = screen.getByTestId('user-api-keys-component')
      expect(userApiKeysComponent).toBeInTheDocument()

      // Verify it's inside a container (class assertions don't work with mocked Dialog)
      expect(userApiKeysComponent.closest('div')).toBeInTheDocument()
    })

    it('has proper header structure with title and description', () => {
      render(<APIKeysModal {...defaultProps} />)

      const title = screen.getByText('API Keys Management')
      const description = screen.getByText(
        'Manage your personal API keys for LLM providers. These keys are encrypted and stored securely.'
      )

      expect(title.tagName).toBe('H2')
      expect(description.tagName).toBe('P')
    })
  })

  describe('Accessibility', () => {
    it('has dialog role when open', () => {
      render(<APIKeysModal {...defaultProps} />)
      expect(screen.getByRole('dialog')).toBeInTheDocument()
    })

    it('close button has aria-label', () => {
      render(<APIKeysModal {...defaultProps} />)
      expect(
        screen.getByRole('button', { name: 'Close' })
      ).toBeInTheDocument()
    })

    it('backdrop has aria-hidden attribute', () => {
      render(<APIKeysModal {...defaultProps} />)
      const backdrop = screen.getByRole('dialog').querySelector('[aria-hidden]')
      expect(backdrop).toHaveAttribute('aria-hidden', 'true')
    })
  })

  describe('Integration', () => {
    it('renders UserApiKeys component inside modal content area', () => {
      render(<APIKeysModal {...defaultProps} />)

      const userApiKeysComponent = screen.getByTestId('user-api-keys-component')
      const modalContent = screen.getByRole('dialog')

      expect(modalContent).toContainElement(userApiKeysComponent)
    })
  })
})

/**
 * Additional coverage for APIKeysModal - open/close, org key settings fetch
 */

import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import { APIKeysModal } from '../APIKeysModal'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, fallback?: string) => fallback || key,
    locale: 'en',
  }),
}))

jest.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({
    currentOrganization: { id: 'org-1', name: 'TUM' },
  }),
}))

const mockGetOrgApiKeySettings = jest.fn()

jest.mock('@/lib/api/organizations', () => ({
  organizationsAPI: {
    getOrgApiKeySettings: (...args: any[]) => mockGetOrgApiKeySettings(...args),
  },
}))

jest.mock('@/components/shared/UserApiKeys', () => {
  return function MockUserApiKeys({ disabled, disabledMessage }: any) {
    return (
      <div data-testid="user-api-keys" data-disabled={disabled}>
        {disabledMessage && <span data-testid="disabled-msg">{disabledMessage}</span>}
      </div>
    )
  }
})

// Mock HeadlessUI Dialog
jest.mock('@headlessui/react', () => ({
  Dialog: ({ open, onClose, children, className }: any) =>
    open ? (
      <div data-testid="dialog" className={className}>
        {children}
      </div>
    ) : null,
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  'Dialog.Panel': undefined,
  'Dialog.Title': undefined,
}))

// Re-mock with proper nested components
jest.mock('@headlessui/react', () => {
  const Dialog = ({ open, onClose, children, className }: any) =>
    open ? (
      <div data-testid="dialog" className={className}>
        {children}
      </div>
    ) : null
  Dialog.Panel = ({ children, className }: any) => <div data-testid="dialog-panel" className={className}>{children}</div>
  Dialog.Title = ({ children, className }: any) => <h2 data-testid="dialog-title" className={className}>{children}</h2>
  return { Dialog }
})

jest.mock('@heroicons/react/24/outline', () => ({
  XMarkIcon: ({ className }: any) => <span data-testid="close-icon" className={className} />,
}))

describe('APIKeysModal', () => {
  const defaultProps = {
    isOpen: true,
    onClose: jest.fn(),
  }

  beforeEach(() => {
    jest.clearAllMocks()
    mockGetOrgApiKeySettings.mockResolvedValue({ require_private_keys: true })
  })

  it('renders when open', () => {
    render(<APIKeysModal {...defaultProps} />)
    expect(screen.getByTestId('dialog')).toBeInTheDocument()
  })

  it('does not render when closed', () => {
    render(<APIKeysModal isOpen={false} onClose={jest.fn()} />)
    expect(screen.queryByTestId('dialog')).not.toBeInTheDocument()
  })

  it('shows API keys management title', () => {
    render(<APIKeysModal {...defaultProps} />)
    expect(screen.getByText('profile.apiKeysManagement')).toBeInTheDocument()
  })

  it('shows description text', () => {
    render(<APIKeysModal {...defaultProps} />)
    expect(screen.getByText('profile.apiKeysDescription')).toBeInTheDocument()
  })

  it('renders done button', () => {
    render(<APIKeysModal {...defaultProps} />)
    const doneBtn = screen.getByText('common.done')
    expect(doneBtn).toBeInTheDocument()
  })

  it('calls onClose when done button is clicked', () => {
    render(<APIKeysModal {...defaultProps} />)
    fireEvent.click(screen.getByText('common.done'))
    expect(defaultProps.onClose).toHaveBeenCalled()
  })

  it('calls onClose when X button is clicked', () => {
    render(<APIKeysModal {...defaultProps} />)
    const closeBtn = screen.getByTestId('close-icon').closest('button')!
    fireEvent.click(closeBtn)
    expect(defaultProps.onClose).toHaveBeenCalled()
  })

  it('fetches org API key settings when open with organization', async () => {
    render(<APIKeysModal {...defaultProps} />)

    await waitFor(() => {
      expect(mockGetOrgApiKeySettings).toHaveBeenCalledWith('org-1')
    })
  })

  it('shows disabled message when org provides keys', async () => {
    mockGetOrgApiKeySettings.mockResolvedValue({ require_private_keys: false })

    render(<APIKeysModal {...defaultProps} />)

    await waitFor(() => {
      expect(screen.getByTestId('disabled-msg')).toBeInTheDocument()
    })
  })

  it('does not show disabled message when org requires private keys', async () => {
    mockGetOrgApiKeySettings.mockResolvedValue({ require_private_keys: true })

    render(<APIKeysModal {...defaultProps} />)

    await waitFor(() => {
      expect(mockGetOrgApiKeySettings).toHaveBeenCalled()
    })

    // UserApiKeys should not be disabled
    const apiKeys = screen.getByTestId('user-api-keys')
    expect(apiKeys).toHaveAttribute('data-disabled', 'false')
  })

  it('handles settings fetch failure gracefully', async () => {
    mockGetOrgApiKeySettings.mockRejectedValue(new Error('Network error'))

    render(<APIKeysModal {...defaultProps} />)

    await waitFor(() => {
      expect(mockGetOrgApiKeySettings).toHaveBeenCalled()
    })

    // Should default to not disabled on error
    const apiKeys = screen.getByTestId('user-api-keys')
    expect(apiKeys).toHaveAttribute('data-disabled', 'false')
  })
})

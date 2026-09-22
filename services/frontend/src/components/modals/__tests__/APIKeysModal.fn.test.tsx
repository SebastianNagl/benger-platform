/**
 * Additional coverage for APIKeysModal - open/close, the per-organization
 * key settings fetch and the "organization provides the keys" note.
 */

import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { APIKeysModal } from '../APIKeysModal'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    // A string second argument is an inline fallback; an object carries
    // interpolation values (the note's {{names}}), rendered here as the key
    // plus the names so the text stays assertable.
    t: (key: string, arg?: unknown) =>
      typeof arg === 'string'
        ? arg
        : arg && typeof arg === 'object' && 'names' in arg
          ? `${key}: ${String((arg as { names: unknown }).names)}`
          : key,
    locale: 'en',
  }),
}))

let mockOrganizations: Array<{ id: string; name: string }> = [
  { id: 'org-1', name: 'TUM' },
  { id: 'org-2', name: 'LMU' },
]
jest.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({
    organizations: mockOrganizations,
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
        {disabledMessage && (
          <span data-testid="disabled-msg">{disabledMessage}</span>
        )}
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
  // eslint-disable-next-line react/display-name
  Dialog.Panel = ({ children, className }: any) => (
    <div data-testid="dialog-panel" className={className}>
      {children}
    </div>
  )
  // eslint-disable-next-line react/display-name
  Dialog.Title = ({ children, className }: any) => (
    <h2 data-testid="dialog-title" className={className}>
      {children}
    </h2>
  )
  return { Dialog }
})

jest.mock('@heroicons/react/24/outline', () => ({
  XMarkIcon: ({ className }: any) => (
    <span data-testid="close-icon" className={className} />
  ),
}))

describe('APIKeysModal', () => {
  const defaultProps = {
    isOpen: true,
    onClose: jest.fn(),
  }

  beforeEach(() => {
    jest.clearAllMocks()
    mockOrganizations = [
      { id: 'org-1', name: 'TUM' },
      { id: 'org-2', name: 'LMU' },
    ]
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

  it('fetches the key settings of every organization the user belongs to', async () => {
    render(<APIKeysModal {...defaultProps} />)

    await waitFor(() => {
      expect(mockGetOrgApiKeySettings).toHaveBeenCalledWith('org-1')
      expect(mockGetOrgApiKeySettings).toHaveBeenCalledWith('org-2')
    })
  })

  it('names the organizations that provide their own keys, keys stay editable', async () => {
    mockGetOrgApiKeySettings.mockImplementation(async (orgId: string) => ({
      require_private_keys: orgId !== 'org-2',
    }))

    render(<APIKeysModal {...defaultProps} />)

    const note = await screen.findByTestId('api-keys-org-provided-note')
    expect(note).toHaveTextContent('LMU')
    expect(note).not.toHaveTextContent('TUM')
    // The personal keys apply to private projects regardless.
    const apiKeys = screen.getByTestId('user-api-keys')
    expect(apiKeys).not.toHaveAttribute('data-disabled', 'true')
    expect(screen.queryByTestId('disabled-msg')).not.toBeInTheDocument()
  })

  it('shows no note when every organization requires private keys', async () => {
    render(<APIKeysModal {...defaultProps} />)

    await waitFor(() => {
      expect(mockGetOrgApiKeySettings).toHaveBeenCalledTimes(2)
    })
    expect(
      screen.queryByTestId('api-keys-org-provided-note'),
    ).not.toBeInTheDocument()
  })

  it('shows no note and fetches nothing without memberships', () => {
    mockOrganizations = []
    render(<APIKeysModal {...defaultProps} />)
    expect(mockGetOrgApiKeySettings).not.toHaveBeenCalled()
    expect(
      screen.queryByTestId('api-keys-org-provided-note'),
    ).not.toBeInTheDocument()
  })

  it('handles a settings fetch failure gracefully', async () => {
    mockGetOrgApiKeySettings.mockRejectedValue(new Error('Network error'))

    render(<APIKeysModal {...defaultProps} />)

    await waitFor(() => {
      expect(mockGetOrgApiKeySettings).toHaveBeenCalled()
    })
    await act(async () => {})
    expect(
      screen.queryByTestId('api-keys-org-provided-note'),
    ).not.toBeInTheDocument()
    expect(screen.getByTestId('user-api-keys')).toBeInTheDocument()
  })
})

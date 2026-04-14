/**
 * @jest-environment jsdom
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { OrgApiKeys } from '../OrgApiKeys'

// Mock HeadlessUI Dialog
jest.mock('@headlessui/react', () => {
  const Dialog = ({ children, open, onClose, className }: any) => {
    if (!open) return null
    return <div className={className} data-testid="dialog">{children}</div>
  }
  Dialog.Panel = ({ children, className }: any) => <div className={className}>{children}</div>
  Dialog.Title = ({ children, className }: any) => <h2 className={className}>{children}</h2>
  return { Dialog }
})

// Mock heroicons
jest.mock('@heroicons/react/24/outline', () => ({
  KeyIcon: (props: any) => <svg {...props} data-testid="key-icon" />,
  EyeIcon: (props: any) => <svg {...props} data-testid="eye-icon" />,
  EyeSlashIcon: (props: any) => <svg {...props} data-testid="eye-slash-icon" />,
  TrashIcon: (props: any) => <svg {...props} data-testid="trash-icon" />,
  XMarkIcon: (props: any) => <svg {...props} data-testid="x-mark-icon" />,
  CheckCircleIcon: (props: any) => <svg {...props} data-testid="check-circle-icon" />,
  ExclamationTriangleIcon: (props: any) => <svg {...props} data-testid="exclamation-icon" />,
  ArrowPathIcon: (props: any) => <svg {...props} data-testid="arrow-path-icon" />,
}))

// Mock I18n context
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, vars?: Record<string, any>) => {
      const translations: Record<string, string> = {
        'organization.apiKeys.dialogTitle': 'Organization API Keys',
        'organization.apiKeys.dialogDescription': 'Configure how API keys are managed for this organization.',
        'organization.apiKeys.orgProvidesToggle': 'Organization provides API keys',
        'organization.apiKeys.sharedKeysActive': 'Shared API keys are active. Members do not need personal keys.',
        'organization.apiKeys.enableSharedKeys': 'Enable to share organization API keys with all members.',
        'organization.apiKeys.membersConfigureOwn': 'Members must configure their own API keys in their profile settings.',
        'organization.apiKeys.orgProvidesSharedKeys': 'This organization provides shared API keys. You do not need to configure personal keys for organization projects.',
        'organization.apiKeys.configuredCount': 'Configure organization API keys for LLM providers ({configured}/{total} configured). These keys are shared across all members and encrypted securely.',
        'organization.apiKeys.membersPersonalNote': 'Note: Members currently use personal keys. Toggle above to share these keys with all members.',
        'organization.apiKeys.membersUseOwnKeys': 'Members now use their own API keys',
        'organization.apiKeys.orgProvidesKeys': 'Organization now provides API keys for all members',
        'organization.apiKeys.updateFailed': 'Failed to update settings',
        'organization.apiKeys.invalidKeyFormat': 'Invalid {provider} API key format',
        'organization.apiKeys.keySaved': '{provider} API key saved',
        'organization.apiKeys.saveFailed': 'Failed to save API key',
        'organization.apiKeys.keyRemoved': '{provider} API key removed',
        'organization.apiKeys.removeFailed': 'Failed to remove API key',
        'organization.apiKeys.testFailed': 'Connection test failed',
        'organization.apiKeys.configured': 'Configured',
        'organization.apiKeys.notConfigured': 'Not configured',
        'organization.apiKeys.testing': 'Testing...',
        'organization.apiKeys.testConnection': 'Test Connection',
        'organization.apiKeys.removing': 'Removing...',
        'organization.apiKeys.removeKey': 'Remove API Key',
        'organization.apiKeys.saving': 'Saving...',
        'organization.apiKeys.saveKey': 'Save API Key',
        'organization.apiKeys.encryptedInfo': 'API keys are encrypted and stored securely.',
        'organization.apiKeys.sharedInfo': 'These keys are shared across all organization members.',
        'organization.apiKeys.adminOnlyInfo': 'Only organization admins can view and manage these keys.',
        'common.done': 'Done',
      }
      let result = translations[key] || key
      if (vars) {
        Object.entries(vars).forEach(([k, v]) => {
          result = result.replace(`{${k}}`, String(v))
        })
      }
      return result
    },
    locale: 'en',
  }),
}))

// Mock shared Button
jest.mock('@/components/shared/Button', () => ({
  Button: ({
    children,
    onClick,
    disabled,
    variant,
    ...props
  }: any) => (
    <button
      onClick={onClick}
      disabled={disabled}
      data-variant={variant}
      {...props}
    >
      {children}
    </button>
  ),
}))

// Default mock for org API
const mockGetOrgApiKeySettings = jest.fn()
const mockGetOrgApiKeyStatus = jest.fn()
const mockUpdateOrgApiKeySettings = jest.fn()
const mockSetOrgApiKey = jest.fn()
const mockRemoveOrgApiKey = jest.fn()
const mockTestOrgApiKey = jest.fn()
const mockTestSavedOrgApiKey = jest.fn()

jest.mock('@/lib/api/organizations', () => ({
  organizationsAPI: {
    getOrgApiKeySettings: (...args: any[]) => mockGetOrgApiKeySettings(...args),
    getOrgApiKeyStatus: (...args: any[]) => mockGetOrgApiKeyStatus(...args),
    updateOrgApiKeySettings: (...args: any[]) =>
      mockUpdateOrgApiKeySettings(...args),
    setOrgApiKey: (...args: any[]) => mockSetOrgApiKey(...args),
    removeOrgApiKey: (...args: any[]) => mockRemoveOrgApiKey(...args),
    testOrgApiKey: (...args: any[]) => mockTestOrgApiKey(...args),
    testSavedOrgApiKey: (...args: any[]) => mockTestSavedOrgApiKey(...args),
  },
}))

describe('OrgApiKeys', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockGetOrgApiKeySettings.mockResolvedValue({ require_private_keys: true })
    mockGetOrgApiKeyStatus.mockResolvedValue({
      api_key_status: {
        openai: false,
        anthropic: false,
        google: false,
        deepinfra: false,
        grok: false,
        mistral: false,
        cohere: false,
      },
      available_providers: [],
    })
  })

  describe('Members-pay mode (default)', () => {
    it('renders heading and description', async () => {
      render(<OrgApiKeys organizationId="org-1" isAdmin={true} open={true} onOpenChange={jest.fn()} />)

      await waitFor(() => {
        expect(screen.getByText('Organization API Keys')).toBeInTheDocument()
      })
      expect(
        screen.getByText(
          'Configure how API keys are managed for this organization.'
        )
      ).toBeInTheDocument()
    })

    it('shows toggle label for admin in members-pay mode', async () => {
      render(<OrgApiKeys organizationId="org-1" isAdmin={true} open={true} onOpenChange={jest.fn()} />)

      await waitFor(() => {
        expect(
          screen.getByText('Organization provides API keys')
        ).toBeInTheDocument()
      })
      // In members-pay mode, toggle is OFF
      const toggleSwitch = screen.getByRole('switch')
      expect(toggleSwitch).toHaveAttribute('aria-checked', 'false')
    })

    it('shows provider cards with warning when members-pay', async () => {
      render(<OrgApiKeys organizationId="org-1" isAdmin={true} open={true} onOpenChange={jest.fn()} />)

      await waitFor(() => {
        expect(
          screen.getByText('Organization provides API keys')
        ).toBeInTheDocument()
      })

      // Provider cards are always shown for admin, but with warning when members-pay
      await waitFor(() => {
        expect(screen.getByText('OpenAI')).toBeInTheDocument()
      })
    })

    it('shows info message for non-admin in members-pay mode', async () => {
      render(<OrgApiKeys organizationId="org-1" isAdmin={false} open={true} onOpenChange={jest.fn()} />)

      await waitFor(() => {
        expect(
          screen.getByText(
            'Members must configure their own API keys in their profile settings.'
          )
        ).toBeInTheDocument()
      })
    })

    it('does not show toggle for non-admin', async () => {
      render(<OrgApiKeys organizationId="org-1" isAdmin={false} open={true} onOpenChange={jest.fn()} />)

      await waitFor(() => {
        expect(
          screen.getByText(
            'Members must configure their own API keys in their profile settings.'
          )
        ).toBeInTheDocument()
      })

      expect(screen.queryByRole('switch')).not.toBeInTheDocument()
    })
  })

  describe('Org-pays mode', () => {
    beforeEach(() => {
      mockGetOrgApiKeySettings.mockResolvedValue({
        require_private_keys: false,
      })
    })

    it('shows org-pays label for admin', async () => {
      render(<OrgApiKeys organizationId="org-1" isAdmin={true} open={true} onOpenChange={jest.fn()} />)

      await waitFor(() => {
        expect(
          screen.getByText('Organization provides API keys')
        ).toBeInTheDocument()
      })
    })

    it('shows provider cards in org-pays mode', async () => {
      render(<OrgApiKeys organizationId="org-1" isAdmin={true} open={true} onOpenChange={jest.fn()} />)

      await waitFor(() => {
        expect(screen.getByText('OpenAI')).toBeInTheDocument()
      })
      expect(screen.getByText('Anthropic')).toBeInTheDocument()
      expect(screen.getByText('Google')).toBeInTheDocument()
      expect(screen.getByText('DeepInfra')).toBeInTheDocument()
    })

    it('shows "Not configured" badge for unconfigured providers', async () => {
      render(<OrgApiKeys organizationId="org-1" isAdmin={true} open={true} onOpenChange={jest.fn()} />)

      await waitFor(() => {
        const badges = screen.getAllByText('Not configured')
        expect(badges.length).toBe(7) // all 7 providers
      })
    })

    it('shows "Configured" badge for set providers', async () => {
      mockGetOrgApiKeyStatus.mockResolvedValue({
        api_key_status: {
          openai: true,
          anthropic: false,
          google: false,
          deepinfra: false,
          grok: false,
          mistral: false,
          cohere: false,
        },
        available_providers: ['OpenAI'],
      })

      render(<OrgApiKeys organizationId="org-1" isAdmin={true} open={true} onOpenChange={jest.fn()} />)

      await waitFor(() => {
        expect(screen.getByText('Configured')).toBeInTheDocument()
      })
      const notConfiguredBadges = screen.getAllByText('Not configured')
      expect(notConfiguredBadges.length).toBe(6) // 6 unconfigured
    })

    it('shows info message for non-admin in org-pays mode', async () => {
      render(<OrgApiKeys organizationId="org-1" isAdmin={false} open={true} onOpenChange={jest.fn()} />)

      await waitFor(() => {
        expect(
          screen.getByText(
            /This organization provides shared API keys/
          )
        ).toBeInTheDocument()
      })
    })

    it('does not show provider cards for non-admin', async () => {
      render(<OrgApiKeys organizationId="org-1" isAdmin={false} open={true} onOpenChange={jest.fn()} />)

      await waitFor(() => {
        expect(
          screen.getByText(/This organization provides shared API keys/)
        ).toBeInTheDocument()
      })

      expect(screen.queryByText('OpenAI')).not.toBeInTheDocument()
    })
  })

  describe('Toggle interaction', () => {
    it('admin can toggle to org-pays mode', async () => {
      mockUpdateOrgApiKeySettings.mockResolvedValue({
        message: 'Settings updated',
        require_private_keys: false,
      })

      render(<OrgApiKeys organizationId="org-1" isAdmin={true} open={true} onOpenChange={jest.fn()} />)

      await waitFor(() => {
        expect(screen.getByRole('switch')).toBeInTheDocument()
      })

      fireEvent.click(screen.getByRole('switch'))

      await waitFor(() => {
        expect(mockUpdateOrgApiKeySettings).toHaveBeenCalledWith(
          'org-1',
          false
        )
      })

      await waitFor(() => {
        expect(
          screen.getByText(
            'Organization now provides API keys for all members'
          )
        ).toBeInTheDocument()
      })
    })

    it('shows error on toggle failure', async () => {
      mockUpdateOrgApiKeySettings.mockRejectedValue({
        response: { data: { detail: 'Permission denied' } },
      })

      render(<OrgApiKeys organizationId="org-1" isAdmin={true} open={true} onOpenChange={jest.fn()} />)

      await waitFor(() => {
        expect(screen.getByRole('switch')).toBeInTheDocument()
      })

      fireEvent.click(screen.getByRole('switch'))

      await waitFor(() => {
        expect(screen.getByText('Permission denied')).toBeInTheDocument()
      })
    })
  })

  describe('Loading state', () => {
    it('renders dialog immediately while data loads', () => {
      // Make the API calls hang (never resolve)
      mockGetOrgApiKeySettings.mockReturnValue(new Promise(() => {}))
      mockGetOrgApiKeyStatus.mockReturnValue(new Promise(() => {}))

      render(<OrgApiKeys organizationId="org-1" isAdmin={true} open={true} onOpenChange={jest.fn()} />)

      // Component renders dialog structure immediately
      expect(
        screen.getByText('Organization API Keys')
      ).toBeInTheDocument()
    })
  })

  describe('Dialog open/close', () => {
    it('does not render when open is false', () => {
      render(<OrgApiKeys organizationId="org-1" isAdmin={true} open={false} onOpenChange={jest.fn()} />)

      expect(screen.queryByText('Organization API Keys')).not.toBeInTheDocument()
    })

    it('calls onOpenChange(false) when close button is clicked', async () => {
      const onOpenChange = jest.fn()
      render(<OrgApiKeys organizationId="org-1" isAdmin={true} open={true} onOpenChange={onOpenChange} />)

      await waitFor(() => {
        expect(screen.getByText('Organization API Keys')).toBeInTheDocument()
      })

      fireEvent.click(screen.getByLabelText('Close modal'))

      expect(onOpenChange).toHaveBeenCalledWith(false)
    })

    it('calls onOpenChange(false) when Done button is clicked', async () => {
      const onOpenChange = jest.fn()
      render(<OrgApiKeys organizationId="org-1" isAdmin={true} open={true} onOpenChange={onOpenChange} />)

      await waitFor(() => {
        expect(screen.getByText('Done')).toBeInTheDocument()
      })

      fireEvent.click(screen.getByText('Done'))

      expect(onOpenChange).toHaveBeenCalledWith(false)
    })
  })

  describe('API key input', () => {
    it('shows password input for unconfigured provider', async () => {
      render(<OrgApiKeys organizationId="org-1" isAdmin={true} open={true} onOpenChange={jest.fn()} />)

      await waitFor(() => {
        expect(screen.getByText('OpenAI')).toBeInTheDocument()
      })

      const inputs = screen.getAllByPlaceholderText('sk-...')
      expect(inputs.length).toBe(1)
      expect(inputs[0]).toHaveAttribute('type', 'password')
    })

    it('toggles API key visibility when eye icon is clicked', async () => {
      render(<OrgApiKeys organizationId="org-1" isAdmin={true} open={true} onOpenChange={jest.fn()} />)

      await waitFor(() => {
        expect(screen.getByText('OpenAI')).toBeInTheDocument()
      })

      const input = screen.getAllByPlaceholderText('sk-...')[0]
      expect(input).toHaveAttribute('type', 'password')

      // Find the eye toggle button (sibling of input)
      const toggleButtons = input.parentElement?.querySelectorAll('button')
      expect(toggleButtons?.length).toBeGreaterThan(0)
      fireEvent.click(toggleButtons![0])

      expect(input).toHaveAttribute('type', 'text')
    })

    it('disables Save button when input is empty', async () => {
      render(<OrgApiKeys organizationId="org-1" isAdmin={true} open={true} onOpenChange={jest.fn()} />)

      await waitFor(() => {
        expect(screen.getByText('OpenAI')).toBeInTheDocument()
      })

      const saveButtons = screen.getAllByText('Save API Key')
      expect(saveButtons[0]).toBeDisabled()
    })

    it('enables Save button when input has a value', async () => {
      render(<OrgApiKeys organizationId="org-1" isAdmin={true} open={true} onOpenChange={jest.fn()} />)

      await waitFor(() => {
        expect(screen.getByText('OpenAI')).toBeInTheDocument()
      })

      const input = screen.getAllByPlaceholderText('sk-...')[0]
      fireEvent.change(input, { target: { value: 'sk-abc123456789012345678901' } })

      const saveButtons = screen.getAllByText('Save API Key')
      expect(saveButtons[0]).not.toBeDisabled()
    })
  })

  describe('Setting API keys', () => {
    it('calls setOrgApiKey with correct params on save', async () => {
      mockSetOrgApiKey.mockResolvedValue({ message: 'Saved' })

      render(<OrgApiKeys organizationId="org-1" isAdmin={true} open={true} onOpenChange={jest.fn()} />)

      await waitFor(() => {
        expect(screen.getByText('OpenAI')).toBeInTheDocument()
      })

      const input = screen.getAllByPlaceholderText('sk-...')[0]
      fireEvent.change(input, { target: { value: 'sk-abc123456789012345678901' } })

      const saveButtons = screen.getAllByText('Save API Key')
      fireEvent.click(saveButtons[0])

      await waitFor(() => {
        expect(mockSetOrgApiKey).toHaveBeenCalledWith(
          'org-1',
          'openai',
          'sk-abc123456789012345678901'
        )
      })
    })

    it('shows validation error for invalid key format', async () => {
      render(<OrgApiKeys organizationId="org-1" isAdmin={true} open={true} onOpenChange={jest.fn()} />)

      await waitFor(() => {
        expect(screen.getByText('OpenAI')).toBeInTheDocument()
      })

      const input = screen.getAllByPlaceholderText('sk-...')[0]
      fireEvent.change(input, { target: { value: 'invalid-key' } })

      const saveButtons = screen.getAllByText('Save API Key')
      fireEvent.click(saveButtons[0])

      await waitFor(() => {
        expect(screen.getByText(/Invalid.*API key format/)).toBeInTheDocument()
      })
    })

    it('shows success message after saving key', async () => {
      mockSetOrgApiKey.mockResolvedValue({ message: 'Saved' })

      render(<OrgApiKeys organizationId="org-1" isAdmin={true} open={true} onOpenChange={jest.fn()} />)

      await waitFor(() => {
        expect(screen.getByText('OpenAI')).toBeInTheDocument()
      })

      const input = screen.getAllByPlaceholderText('sk-...')[0]
      fireEvent.change(input, { target: { value: 'sk-abc123456789012345678901' } })

      const saveButtons = screen.getAllByText('Save API Key')
      fireEvent.click(saveButtons[0])

      await waitFor(() => {
        expect(screen.getByText(/OpenAI API key saved/)).toBeInTheDocument()
      })
    })
  })

  describe('Removing API keys', () => {
    beforeEach(() => {
      mockGetOrgApiKeyStatus.mockResolvedValue({
        api_key_status: {
          openai: true,
          anthropic: false,
          google: false,
          deepinfra: false,
          grok: false,
          mistral: false,
          cohere: false,
        },
        available_providers: ['OpenAI'],
      })
    })

    it('shows remove button for configured provider', async () => {
      render(<OrgApiKeys organizationId="org-1" isAdmin={true} open={true} onOpenChange={jest.fn()} />)

      await waitFor(() => {
        expect(screen.getByText('Configured')).toBeInTheDocument()
      })

      expect(screen.getByText('Remove API Key')).toBeInTheDocument()
    })

    it('calls removeOrgApiKey when remove is clicked', async () => {
      mockRemoveOrgApiKey.mockResolvedValue({ message: 'Removed' })

      render(<OrgApiKeys organizationId="org-1" isAdmin={true} open={true} onOpenChange={jest.fn()} />)

      await waitFor(() => {
        expect(screen.getByText('Remove API Key')).toBeInTheDocument()
      })

      fireEvent.click(screen.getByText('Remove API Key'))

      await waitFor(() => {
        expect(mockRemoveOrgApiKey).toHaveBeenCalledWith('org-1', 'openai')
      })
    })

    it('shows success message after removing key', async () => {
      mockRemoveOrgApiKey.mockResolvedValue({ message: 'Removed' })

      render(<OrgApiKeys organizationId="org-1" isAdmin={true} open={true} onOpenChange={jest.fn()} />)

      await waitFor(() => {
        expect(screen.getByText('Remove API Key')).toBeInTheDocument()
      })

      fireEvent.click(screen.getByText('Remove API Key'))

      await waitFor(() => {
        expect(screen.getByText(/OpenAI API key removed/)).toBeInTheDocument()
      })
    })
  })

  describe('Testing API keys', () => {
    it('disables Test button when input is empty for unconfigured provider', async () => {
      render(<OrgApiKeys organizationId="org-1" isAdmin={true} open={true} onOpenChange={jest.fn()} />)

      await waitFor(() => {
        expect(screen.getByText('OpenAI')).toBeInTheDocument()
      })

      const testButtons = screen.getAllByText('Test Connection')
      expect(testButtons[0]).toBeDisabled()
    })

    it('shows Test Connection for configured provider', async () => {
      mockGetOrgApiKeyStatus.mockResolvedValue({
        api_key_status: {
          openai: true,
          anthropic: false,
          google: false,
          deepinfra: false,
          grok: false,
          mistral: false,
          cohere: false,
        },
        available_providers: ['OpenAI'],
      })

      render(<OrgApiKeys organizationId="org-1" isAdmin={true} open={true} onOpenChange={jest.fn()} />)

      await waitFor(() => {
        expect(screen.getByText('Configured')).toBeInTheDocument()
      })

      // Test Connection buttons exist for all providers (configured and unconfigured)
      const testButtons = screen.getAllByText('Test Connection')
      expect(testButtons.length).toBeGreaterThan(0)
    })

    it('calls testSavedOrgApiKey for configured provider', async () => {
      mockGetOrgApiKeyStatus.mockResolvedValue({
        api_key_status: {
          openai: true,
          anthropic: false,
          google: false,
          deepinfra: false,
          grok: false,
          mistral: false,
          cohere: false,
        },
        available_providers: ['OpenAI'],
      })
      mockTestSavedOrgApiKey.mockResolvedValue({ status: 'success', message: 'Connection OK' })

      render(<OrgApiKeys organizationId="org-1" isAdmin={true} open={true} onOpenChange={jest.fn()} />)

      await waitFor(() => {
        expect(screen.getByText('Configured')).toBeInTheDocument()
      })

      // The first Test Connection button is for OpenAI (configured)
      const testButtons = screen.getAllByText('Test Connection')
      // Find the enabled one (configured provider's test button is not disabled)
      const enabledTestBtn = testButtons.find((btn) => !btn.closest('button')?.hasAttribute('disabled'))
      expect(enabledTestBtn).toBeTruthy()
      fireEvent.click(enabledTestBtn!)

      await waitFor(() => {
        expect(mockTestSavedOrgApiKey).toHaveBeenCalledWith('org-1', 'openai')
      })

      await waitFor(() => {
        expect(screen.getByText('Connection OK')).toBeInTheDocument()
      })
    })

    it('calls testOrgApiKey for unconfigured provider with input', async () => {
      mockTestOrgApiKey.mockResolvedValue({ status: 'success', message: 'Key valid' })

      render(<OrgApiKeys organizationId="org-1" isAdmin={true} open={true} onOpenChange={jest.fn()} />)

      await waitFor(() => {
        expect(screen.getByText('OpenAI')).toBeInTheDocument()
      })

      const input = screen.getAllByPlaceholderText('sk-...')[0]
      fireEvent.change(input, { target: { value: 'sk-testapikey1234567890abc' } })

      const testButtons = screen.getAllByText('Test Connection')
      fireEvent.click(testButtons[0])

      await waitFor(() => {
        expect(mockTestOrgApiKey).toHaveBeenCalledWith(
          'org-1',
          'openai',
          'sk-testapikey1234567890abc'
        )
      })

      await waitFor(() => {
        expect(screen.getByText('Key valid')).toBeInTheDocument()
      })
    })

    it('shows error test result', async () => {
      mockTestOrgApiKey.mockResolvedValue({ status: 'error', message: 'Invalid API key' })

      render(<OrgApiKeys organizationId="org-1" isAdmin={true} open={true} onOpenChange={jest.fn()} />)

      await waitFor(() => {
        expect(screen.getByText('OpenAI')).toBeInTheDocument()
      })

      const input = screen.getAllByPlaceholderText('sk-...')[0]
      fireEvent.change(input, { target: { value: 'sk-testapikey1234567890abc' } })

      const testButtons = screen.getAllByText('Test Connection')
      fireEvent.click(testButtons[0])

      await waitFor(() => {
        expect(screen.getByText('Invalid API key')).toBeInTheDocument()
      })
    })
  })

  describe('Provider list', () => {
    it('renders all 7 providers for admin', async () => {
      render(<OrgApiKeys organizationId="org-1" isAdmin={true} open={true} onOpenChange={jest.fn()} />)

      await waitFor(() => {
        expect(screen.getByText('OpenAI')).toBeInTheDocument()
      })

      expect(screen.getByText('Anthropic')).toBeInTheDocument()
      expect(screen.getByText('Google')).toBeInTheDocument()
      expect(screen.getByText('DeepInfra')).toBeInTheDocument()
      expect(screen.getByText('Grok (xAI)')).toBeInTheDocument()
      expect(screen.getByText('Mistral AI')).toBeInTheDocument()
      expect(screen.getByText('Cohere')).toBeInTheDocument()
    })

    it('shows encrypted info text for admin', async () => {
      render(<OrgApiKeys organizationId="org-1" isAdmin={true} open={true} onOpenChange={jest.fn()} />)

      await waitFor(() => {
        expect(screen.getByText('API keys are encrypted and stored securely.')).toBeInTheDocument()
      })
      expect(screen.getByText('These keys are shared across all organization members.')).toBeInTheDocument()
      expect(screen.getByText('Only organization admins can view and manage these keys.')).toBeInTheDocument()
    })

    it('shows configured count summary', async () => {
      mockGetOrgApiKeyStatus.mockResolvedValue({
        api_key_status: {
          openai: true,
          anthropic: true,
          google: false,
          deepinfra: false,
          grok: false,
          mistral: false,
          cohere: false,
        },
        available_providers: ['OpenAI', 'Anthropic'],
      })

      render(<OrgApiKeys organizationId="org-1" isAdmin={true} open={true} onOpenChange={jest.fn()} />)

      await waitFor(() => {
        expect(screen.getByText(/2\/7 configured/)).toBeInTheDocument()
      })
    })
  })

  describe('Error handling', () => {
    it('shows fallback error on save failure without detail', async () => {
      mockSetOrgApiKey.mockRejectedValue(new Error('Network error'))

      render(<OrgApiKeys organizationId="org-1" isAdmin={true} open={true} onOpenChange={jest.fn()} />)

      await waitFor(() => {
        expect(screen.getByText('OpenAI')).toBeInTheDocument()
      })

      const input = screen.getAllByPlaceholderText('sk-...')[0]
      fireEvent.change(input, { target: { value: 'sk-validkey12345678901234567' } })

      const saveButtons = screen.getAllByText('Save API Key')
      fireEvent.click(saveButtons[0])

      await waitFor(() => {
        expect(screen.getByText('Failed to save API key')).toBeInTheDocument()
      })
    })

    it('shows fallback error on remove failure without detail', async () => {
      mockGetOrgApiKeyStatus.mockResolvedValue({
        api_key_status: {
          openai: true, anthropic: false, google: false,
          deepinfra: false, grok: false, mistral: false, cohere: false,
        },
        available_providers: ['OpenAI'],
      })
      mockRemoveOrgApiKey.mockRejectedValue(new Error('Server error'))

      render(<OrgApiKeys organizationId="org-1" isAdmin={true} open={true} onOpenChange={jest.fn()} />)

      await waitFor(() => {
        expect(screen.getByText('Remove API Key')).toBeInTheDocument()
      })

      fireEvent.click(screen.getByText('Remove API Key'))

      await waitFor(() => {
        expect(screen.getByText('Failed to remove API key')).toBeInTheDocument()
      })
    })

    it('falls back to default on settings fetch failure', async () => {
      mockGetOrgApiKeySettings.mockRejectedValue(new Error('Fetch failed'))

      render(<OrgApiKeys organizationId="org-1" isAdmin={true} open={true} onOpenChange={jest.fn()} />)

      // Should default to requirePrivateKeys=true, so toggle is off
      await waitFor(() => {
        const toggleSwitch = screen.getByRole('switch')
        expect(toggleSwitch).toHaveAttribute('aria-checked', 'false')
      })
    })

    it('shows fallback error on test failure', async () => {
      mockTestOrgApiKey.mockRejectedValue(new Error('timeout'))

      render(<OrgApiKeys organizationId="org-1" isAdmin={true} open={true} onOpenChange={jest.fn()} />)

      await waitFor(() => {
        expect(screen.getByText('OpenAI')).toBeInTheDocument()
      })

      const input = screen.getAllByPlaceholderText('sk-...')[0]
      fireEvent.change(input, { target: { value: 'sk-testkey1234567890abcdefg' } })

      const testButtons = screen.getAllByText('Test Connection')
      fireEvent.click(testButtons[0])

      await waitFor(() => {
        expect(screen.getByText('Connection test failed')).toBeInTheDocument()
      })
    })
  })
})

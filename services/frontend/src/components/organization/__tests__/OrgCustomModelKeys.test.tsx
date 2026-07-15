/**
 * @jest-environment jsdom
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { OrgCustomModelKeys } from '../OrgCustomModelKeys'

// Mock HeadlessUI Dialog
jest.mock('@headlessui/react', () => {
  const Dialog = ({ children, open, className }: any) => {
    if (!open) return null
    return (
      <div className={className} data-testid="dialog">
        {children}
      </div>
    )
  }
  // eslint-disable-next-line react/display-name
  Dialog.Panel = ({ children, className }: any) => (
    <div className={className}>{children}</div>
  )
  // eslint-disable-next-line react/display-name
  Dialog.Title = ({ children, className }: any) => (
    <h2 className={className}>{children}</h2>
  )
  return { Dialog }
})

// Mock heroicons
jest.mock('@heroicons/react/24/outline', () => ({
  EyeIcon: (props: any) => <svg {...props} data-testid="eye-icon" />,
  EyeSlashIcon: (props: any) => <svg {...props} data-testid="eye-slash-icon" />,
  XMarkIcon: (props: any) => <svg {...props} data-testid="x-mark-icon" />,
}))

// Mock I18n context
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, vars?: Record<string, any>) => {
      const translations: Record<string, string> = {
        'organization.customModelKeys.dialogTitle': 'Shared Custom Model Keys',
        'organization.customModelKeys.dialogDescription':
          'Provision one shared API key per custom model.',
        'organization.customModelKeys.adminOnly':
          'Only organization admins can view and manage shared custom model keys.',
        'organization.customModelKeys.sharedModeActive': 'Shared billing is active.',
        'organization.customModelKeys.sharedModeInactive': 'Shared billing is off.',
        'organization.customModelKeys.configuredCount':
          '{configured} of {total} shared custom models have a key configured.',
        'organization.customModelKeys.loading': 'Loading custom models...',
        'organization.customModelKeys.noModels':
          'No custom models are shared with this organization yet.',
        'organization.customModelKeys.configured': 'Configured',
        'organization.customModelKeys.notConfigured': 'Not configured',
        'organization.customModelKeys.keyPlaceholder': 'Enter the shared API key',
        'organization.customModelKeys.saveKey': 'Save Key',
        'organization.customModelKeys.saving': 'Saving...',
        'organization.customModelKeys.removeKey': 'Remove Key',
        'organization.customModelKeys.removing': 'Removing...',
        'organization.customModelKeys.keySaved': 'Shared key saved for {model}',
        'organization.customModelKeys.saveFailed': 'Failed to save the shared key',
        'organization.customModelKeys.keyRemoved': 'Shared key removed for {model}',
        'organization.customModelKeys.removeFailed':
          'Failed to remove the shared key',
        'organization.customModelKeys.encryptedInfo':
          'Shared keys are encrypted and stored securely.',
        'organization.customModelKeys.sharedInfo':
          'A shared key is used only when the organization provides API keys.',
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
  Button: ({ children, onClick, disabled, variant, ...props }: any) => (
    <button onClick={onClick} disabled={disabled} data-variant={variant} {...props}>
      {children}
    </button>
  ),
}))

const mockGetOrgApiKeySettings = jest.fn()
const mockListOrgCustomModels = jest.fn()
const mockSetOrgCustomModelCredential = jest.fn()
const mockRemoveOrgCustomModelCredential = jest.fn()

jest.mock('@/lib/api/organizations', () => ({
  organizationsAPI: {
    getOrgApiKeySettings: (...args: any[]) => mockGetOrgApiKeySettings(...args),
    listOrgCustomModels: (...args: any[]) => mockListOrgCustomModels(...args),
    setOrgCustomModelCredential: (...args: any[]) =>
      mockSetOrgCustomModelCredential(...args),
    removeOrgCustomModelCredential: (...args: any[]) =>
      mockRemoveOrgCustomModelCredential(...args),
  },
}))

const MODEL_UNCONFIGURED = {
  id: 'custom-abc',
  name: 'My vLLM',
  provider: 'Custom',
  base_url: 'http://10.0.0.5:8000/v1',
  endpoint_model_name: 'llama-3-8b',
  requires_api_key: true,
  has_org_credential: false,
}

const MODEL_CONFIGURED = {
  id: 'custom-def',
  name: 'Shared GPU Model',
  provider: 'Custom',
  base_url: 'http://10.0.0.6:8000/v1',
  endpoint_model_name: 'qwen-72b',
  requires_api_key: true,
  has_org_credential: true,
}

describe('OrgCustomModelKeys', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockGetOrgApiKeySettings.mockResolvedValue({ require_private_keys: false })
    mockListOrgCustomModels.mockResolvedValue([MODEL_UNCONFIGURED])
  })

  describe('Rendering', () => {
    it('renders heading and description', async () => {
      render(
        <OrgCustomModelKeys
          organizationId="org-1"
          isAdmin={true}
          open={true}
          onOpenChange={jest.fn()}
        />
      )
      await waitFor(() => {
        expect(screen.getByText('Shared Custom Model Keys')).toBeInTheDocument()
      })
      expect(
        screen.getByText('Provision one shared API key per custom model.')
      ).toBeInTheDocument()
    })

    it('shows shared-mode-active banner when org provides keys', async () => {
      render(
        <OrgCustomModelKeys
          organizationId="org-1"
          isAdmin={true}
          open={true}
          onOpenChange={jest.fn()}
        />
      )
      await waitFor(() => {
        expect(screen.getByText('Shared billing is active.')).toBeInTheDocument()
      })
    })

    it('shows shared-mode-inactive banner when members pay', async () => {
      mockGetOrgApiKeySettings.mockResolvedValue({ require_private_keys: true })
      render(
        <OrgCustomModelKeys
          organizationId="org-1"
          isAdmin={true}
          open={true}
          onOpenChange={jest.fn()}
        />
      )
      await waitFor(() => {
        expect(screen.getByText('Shared billing is off.')).toBeInTheDocument()
      })
    })

    it('shows admin-only message for non-admin', async () => {
      render(
        <OrgCustomModelKeys
          organizationId="org-1"
          isAdmin={false}
          open={true}
          onOpenChange={jest.fn()}
        />
      )
      await waitFor(() => {
        expect(
          screen.getByText(
            'Only organization admins can view and manage shared custom model keys.'
          )
        ).toBeInTheDocument()
      })
      // Non-admin never sees model cards.
      expect(screen.queryByText('My vLLM')).not.toBeInTheDocument()
    })

    it('lists the shared custom models', async () => {
      render(
        <OrgCustomModelKeys
          organizationId="org-1"
          isAdmin={true}
          open={true}
          onOpenChange={jest.fn()}
        />
      )
      await waitFor(() => {
        expect(screen.getByText('My vLLM')).toBeInTheDocument()
      })
      expect(screen.getByText('http://10.0.0.5:8000/v1')).toBeInTheDocument()
      expect(mockListOrgCustomModels).toHaveBeenCalledWith('org-1')
    })

    it('shows the empty state when no models are shared', async () => {
      mockListOrgCustomModels.mockResolvedValue([])
      render(
        <OrgCustomModelKeys
          organizationId="org-1"
          isAdmin={true}
          open={true}
          onOpenChange={jest.fn()}
        />
      )
      await waitFor(() => {
        expect(
          screen.getByText(
            'No custom models are shared with this organization yet.'
          )
        ).toBeInTheDocument()
      })
    })

    it('shows configured count summary', async () => {
      mockListOrgCustomModels.mockResolvedValue([
        MODEL_UNCONFIGURED,
        MODEL_CONFIGURED,
      ])
      render(
        <OrgCustomModelKeys
          organizationId="org-1"
          isAdmin={true}
          open={true}
          onOpenChange={jest.fn()}
        />
      )
      await waitFor(() => {
        expect(
          screen.getByText(/1 of 2 shared custom models have a key configured/)
        ).toBeInTheDocument()
      })
    })
  })

  describe('Setting a shared key', () => {
    it('shows password input and disabled Save when empty', async () => {
      render(
        <OrgCustomModelKeys
          organizationId="org-1"
          isAdmin={true}
          open={true}
          onOpenChange={jest.fn()}
        />
      )
      await waitFor(() => {
        expect(screen.getByText('My vLLM')).toBeInTheDocument()
      })
      const input = screen.getByPlaceholderText('Enter the shared API key')
      expect(input).toHaveAttribute('type', 'password')
      expect(screen.getByText('Save Key')).toBeDisabled()
    })

    it('calls setOrgCustomModelCredential with correct params', async () => {
      mockSetOrgCustomModelCredential.mockResolvedValue({ has_credential: true })
      mockListOrgCustomModels
        .mockResolvedValueOnce([MODEL_UNCONFIGURED])
        .mockResolvedValueOnce([{ ...MODEL_UNCONFIGURED, has_org_credential: true }])

      render(
        <OrgCustomModelKeys
          organizationId="org-1"
          isAdmin={true}
          open={true}
          onOpenChange={jest.fn()}
        />
      )
      await waitFor(() => {
        expect(screen.getByText('My vLLM')).toBeInTheDocument()
      })

      const input = screen.getByPlaceholderText('Enter the shared API key')
      fireEvent.change(input, { target: { value: 'sk-shared-key-123' } })
      fireEvent.click(screen.getByText('Save Key'))

      await waitFor(() => {
        expect(mockSetOrgCustomModelCredential).toHaveBeenCalledWith(
          'org-1',
          'custom-abc',
          'sk-shared-key-123'
        )
      })
      await waitFor(() => {
        expect(screen.getByText('Shared key saved for My vLLM')).toBeInTheDocument()
      })
    })

    it('toggles key visibility with the eye icon', async () => {
      render(
        <OrgCustomModelKeys
          organizationId="org-1"
          isAdmin={true}
          open={true}
          onOpenChange={jest.fn()}
        />
      )
      await waitFor(() => {
        expect(screen.getByText('My vLLM')).toBeInTheDocument()
      })
      const input = screen.getByPlaceholderText('Enter the shared API key')
      expect(input).toHaveAttribute('type', 'password')
      const toggle = input.parentElement?.querySelector('button')
      fireEvent.click(toggle!)
      expect(input).toHaveAttribute('type', 'text')
    })

    it('shows error message on save failure', async () => {
      mockSetOrgCustomModelCredential.mockRejectedValue(new Error('boom'))
      render(
        <OrgCustomModelKeys
          organizationId="org-1"
          isAdmin={true}
          open={true}
          onOpenChange={jest.fn()}
        />
      )
      await waitFor(() => {
        expect(screen.getByText('My vLLM')).toBeInTheDocument()
      })
      const input = screen.getByPlaceholderText('Enter the shared API key')
      fireEvent.change(input, { target: { value: 'sk-x' } })
      fireEvent.click(screen.getByText('Save Key'))
      await waitFor(() => {
        expect(screen.getByText('Failed to save the shared key')).toBeInTheDocument()
      })
    })
  })

  describe('Removing a shared key', () => {
    beforeEach(() => {
      mockListOrgCustomModels.mockResolvedValue([MODEL_CONFIGURED])
    })

    it('shows Configured badge and Remove Key for a configured model', async () => {
      render(
        <OrgCustomModelKeys
          organizationId="org-1"
          isAdmin={true}
          open={true}
          onOpenChange={jest.fn()}
        />
      )
      await waitFor(() => {
        expect(screen.getByText('Configured')).toBeInTheDocument()
      })
      expect(screen.getByText('Remove Key')).toBeInTheDocument()
    })

    it('calls removeOrgCustomModelCredential when Remove is clicked', async () => {
      mockRemoveOrgCustomModelCredential.mockResolvedValue({ has_credential: false })
      render(
        <OrgCustomModelKeys
          organizationId="org-1"
          isAdmin={true}
          open={true}
          onOpenChange={jest.fn()}
        />
      )
      await waitFor(() => {
        expect(screen.getByText('Remove Key')).toBeInTheDocument()
      })
      fireEvent.click(screen.getByText('Remove Key'))
      await waitFor(() => {
        expect(mockRemoveOrgCustomModelCredential).toHaveBeenCalledWith(
          'org-1',
          'custom-def'
        )
      })
      await waitFor(() => {
        expect(
          screen.getByText('Shared key removed for Shared GPU Model')
        ).toBeInTheDocument()
      })
    })
  })

  describe('Dialog open/close', () => {
    it('does not render when open is false', () => {
      render(
        <OrgCustomModelKeys
          organizationId="org-1"
          isAdmin={true}
          open={false}
          onOpenChange={jest.fn()}
        />
      )
      expect(screen.queryByText('Shared Custom Model Keys')).not.toBeInTheDocument()
    })

    it('calls onOpenChange(false) on Done', async () => {
      const onOpenChange = jest.fn()
      render(
        <OrgCustomModelKeys
          organizationId="org-1"
          isAdmin={true}
          open={true}
          onOpenChange={onOpenChange}
        />
      )
      await waitFor(() => {
        expect(screen.getByText('Done')).toBeInTheDocument()
      })
      fireEvent.click(screen.getByText('Done'))
      expect(onOpenChange).toHaveBeenCalledWith(false)
    })

    it('calls onOpenChange(false) when close button is clicked', async () => {
      const onOpenChange = jest.fn()
      render(
        <OrgCustomModelKeys
          organizationId="org-1"
          isAdmin={true}
          open={true}
          onOpenChange={onOpenChange}
        />
      )
      await waitFor(() => {
        expect(screen.getByText('Shared Custom Model Keys')).toBeInTheDocument()
      })
      fireEvent.click(screen.getByLabelText('Close modal'))
      expect(onOpenChange).toHaveBeenCalledWith(false)
    })
  })
})

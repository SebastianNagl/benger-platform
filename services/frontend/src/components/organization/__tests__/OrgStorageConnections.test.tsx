/**
 * @jest-environment jsdom
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { OrgStorageConnections } from '../OrgStorageConnections'

// Mock HeadlessUI Dialog (same shape as the OrgApiKeys suite)
jest.mock('@headlessui/react', () => {
  const Dialog = ({ children, open, onClose, className }: any) => {
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
        'organizations.storageConnections.dialogTitle':
          'Cloud storage connections',
        'organizations.storageConnections.dialogDescription':
          'Connect S3-compatible storage so members can import files straight from the bucket.',
        'organizations.storageConnections.adminOnly':
          'Only organization admins can manage storage connections.',
        'organizations.storageConnections.loading': 'Loading connections...',
        'organizations.storageConnections.empty':
          'No storage connections configured yet.',
        'organizations.storageConnections.awsDefaultEndpoint':
          'AWS default endpoint',
        'organizations.storageConnections.accessKeyHint': 'Key ...{hint}',
        'organizations.storageConnections.addConnection': 'Add connection',
        'organizations.storageConnections.addTitle': 'New storage connection',
        'organizations.storageConnections.editTitle': 'Edit storage connection',
        'organizations.storageConnections.name': 'Name',
        'organizations.storageConnections.namePlaceholder': 'Name',
        'organizations.storageConnections.endpoint': 'Endpoint URL',
        'organizations.storageConnections.endpointPlaceholder':
          'Endpoint URL (empty = AWS S3)',
        'organizations.storageConnections.bucket': 'Bucket',
        'organizations.storageConnections.bucketPlaceholder': 'Bucket',
        'organizations.storageConnections.prefix': 'Prefix',
        'organizations.storageConnections.prefixPlaceholder':
          'Prefix (optional)',
        'organizations.storageConnections.region': 'Region',
        'organizations.storageConnections.regionPlaceholder':
          'Region (optional)',
        'organizations.storageConnections.useSsl': 'Use SSL',
        'organizations.storageConnections.accessKey': 'Access key',
        'organizations.storageConnections.accessKeyPlaceholder':
          'Access key ID',
        'organizations.storageConnections.accessKeyKeepPlaceholder':
          'Access key ID (leave empty to keep the stored one)',
        'organizations.storageConnections.secretKey': 'Secret key',
        'organizations.storageConnections.secretKeyPlaceholder':
          'Secret access key',
        'organizations.storageConnections.secretKeyKeepPlaceholder':
          'Secret access key (leave empty to keep the stored one)',
        'organizations.storageConnections.toggleAccessKey':
          'Show/hide access key',
        'organizations.storageConnections.toggleSecretKey':
          'Show/hide secret key',
        'organizations.storageConnections.testConnection': 'Test connection',
        'organizations.storageConnections.testing': 'Testing...',
        'organizations.storageConnections.testFailed': 'Connection test failed',
        'organizations.storageConnections.save': 'Save',
        'organizations.storageConnections.saving': 'Saving...',
        'organizations.storageConnections.saved':
          'Storage connection "{name}" saved',
        'organizations.storageConnections.updated':
          'Storage connection "{name}" updated',
        'organizations.storageConnections.saveFailed':
          'Failed to save the storage connection',
        'organizations.storageConnections.edit': 'Edit',
        'organizations.storageConnections.delete': 'Delete',
        'organizations.storageConnections.deleteConfirm': 'Really delete?',
        'organizations.storageConnections.deleteConfirmYes': 'Yes, delete',
        'organizations.storageConnections.deleting': 'Deleting...',
        'organizations.storageConnections.deleted':
          'Storage connection "{name}" deleted',
        'organizations.storageConnections.deleteFailed':
          'Failed to delete the storage connection',
        'organizations.storageConnections.encryptedInfo':
          'Credentials are stored encrypted and never returned to the browser.',
        'organizations.storageConnections.membersInfo':
          'All members of the organization can import files into their projects via these connections.',
        'common.cancel': 'Cancel',
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

const mockListStorageConnections = jest.fn()
const mockCreateStorageConnection = jest.fn()
const mockUpdateStorageConnection = jest.fn()
const mockDeleteStorageConnection = jest.fn()
const mockTestStorageConnection = jest.fn()
const mockTestSavedStorageConnection = jest.fn()

jest.mock('@/lib/api/organizations', () => ({
  organizationsAPI: {
    listStorageConnections: (...args: any[]) =>
      mockListStorageConnections(...args),
    createStorageConnection: (...args: any[]) =>
      mockCreateStorageConnection(...args),
    updateStorageConnection: (...args: any[]) =>
      mockUpdateStorageConnection(...args),
    deleteStorageConnection: (...args: any[]) =>
      mockDeleteStorageConnection(...args),
    testStorageConnection: (...args: any[]) =>
      mockTestStorageConnection(...args),
    testSavedStorageConnection: (...args: any[]) =>
      mockTestSavedStorageConnection(...args),
  },
}))

const CONN = {
  id: 'conn-1',
  organization_id: 'org-1',
  name: 'Chair bucket',
  endpoint_url: 'https://minio.example.org',
  bucket: 'law-exams',
  prefix: 'imports/',
  region: null,
  use_ssl: true,
  access_key_hint: 'A1B2',
  created_by: 'user-1',
  created_at: '2026-08-30T10:00:00Z',
  updated_at: '2026-08-30T10:00:00Z',
}

function renderModal(props: Partial<any> = {}) {
  return render(
    <OrgStorageConnections
      organizationId="org-1"
      isAdmin={true}
      open={true}
      onOpenChange={jest.fn()}
      {...props}
    />
  )
}

describe('OrgStorageConnections', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockListStorageConnections.mockResolvedValue([])
  })

  describe('Rendering', () => {
    it('renders title and description', async () => {
      renderModal()
      expect(
        screen.getByText('Cloud storage connections')
      ).toBeInTheDocument()
      expect(
        screen.getByText(
          'Connect S3-compatible storage so members can import files straight from the bucket.'
        )
      ).toBeInTheDocument()
      await waitFor(() =>
        expect(mockListStorageConnections).toHaveBeenCalledWith('org-1')
      )
    })

    it('does not render when open is false', () => {
      renderModal({ open: false })
      expect(
        screen.queryByText('Cloud storage connections')
      ).not.toBeInTheDocument()
      expect(mockListStorageConnections).not.toHaveBeenCalled()
    })

    it('shows the empty state when no connections exist', async () => {
      renderModal()
      expect(
        await screen.findByText('No storage connections configured yet.')
      ).toBeInTheDocument()
    })

    it('lists a connection with name, endpoint, bucket/prefix and key hint', async () => {
      mockListStorageConnections.mockResolvedValue([CONN])
      renderModal()
      expect(await screen.findByText('Chair bucket')).toBeInTheDocument()
      expect(
        screen.getByText('https://minio.example.org')
      ).toBeInTheDocument()
      expect(screen.getByText('law-exams/imports/')).toBeInTheDocument()
      expect(screen.getByText('Key ...A1B2')).toBeInTheDocument()
    })

    it('falls back to the AWS default endpoint label', async () => {
      mockListStorageConnections.mockResolvedValue([
        { ...CONN, endpoint_url: null },
      ])
      renderModal()
      expect(
        await screen.findByText('AWS default endpoint')
      ).toBeInTheDocument()
    })

    it('hides manage actions for non-admins and shows the admin-only note', async () => {
      mockListStorageConnections.mockResolvedValue([CONN])
      renderModal({ isAdmin: false })
      expect(await screen.findByText('Chair bucket')).toBeInTheDocument()
      expect(
        screen.getByText(
          'Only organization admins can manage storage connections.'
        )
      ).toBeInTheDocument()
      expect(screen.queryByText('Add connection')).not.toBeInTheDocument()
      expect(screen.queryByText('Edit')).not.toBeInTheDocument()
      expect(screen.queryByText('Delete')).not.toBeInTheDocument()
    })
  })

  describe('Creating a connection', () => {
    async function openCreateForm() {
      renderModal()
      fireEvent.click(await screen.findByText('Add connection'))
      return screen.getByTestId('storage-connection-form')
    }

    it('opens the add form and disables Save until required fields are set', async () => {
      await openCreateForm()
      expect(screen.getByText('New storage connection')).toBeInTheDocument()
      expect(screen.getByText('Save')).toBeDisabled()

      fireEvent.change(screen.getByLabelText('Name'), {
        target: { value: 'My bucket' },
      })
      fireEvent.change(screen.getByLabelText('Bucket'), {
        target: { value: 'bucket-a' },
      })
      expect(screen.getByText('Save')).toBeDisabled()

      fireEvent.change(screen.getByLabelText('Access key'), {
        target: { value: 'AKIA123' },
      })
      fireEvent.change(screen.getByLabelText('Secret key'), {
        target: { value: 'secret456' },
      })
      expect(screen.getByText('Save')).not.toBeDisabled()
    })

    it('creates the connection with the entered values', async () => {
      mockCreateStorageConnection.mockResolvedValue({ ...CONN, id: 'conn-new' })
      await openCreateForm()

      fireEvent.change(screen.getByLabelText('Name'), {
        target: { value: 'My bucket' },
      })
      fireEvent.change(screen.getByLabelText('Bucket'), {
        target: { value: 'bucket-a' },
      })
      fireEvent.change(screen.getByLabelText('Prefix'), {
        target: { value: 'data/' },
      })
      fireEvent.change(screen.getByLabelText('Access key'), {
        target: { value: 'AKIA123' },
      })
      fireEvent.change(screen.getByLabelText('Secret key'), {
        target: { value: 'secret456' },
      })
      fireEvent.click(screen.getByText('Save'))

      await waitFor(() =>
        expect(mockCreateStorageConnection).toHaveBeenCalledWith('org-1', {
          name: 'My bucket',
          endpoint_url: null,
          bucket: 'bucket-a',
          prefix: 'data/',
          region: null,
          use_ssl: true,
          access_key: 'AKIA123',
          secret_key: 'secret456',
        })
      )
      expect(
        await screen.findByText('Storage connection "My bucket" saved')
      ).toBeInTheDocument()
      // List refetched after save.
      expect(mockListStorageConnections).toHaveBeenCalledTimes(2)
    })

    it('shows the API error detail on create failure', async () => {
      mockCreateStorageConnection.mockRejectedValue({
        response: {
          data: {
            detail: 'A storage connection with this name already exists',
          },
        },
      })
      await openCreateForm()
      fireEvent.change(screen.getByLabelText('Name'), {
        target: { value: 'Dup' },
      })
      fireEvent.change(screen.getByLabelText('Bucket'), {
        target: { value: 'b' },
      })
      fireEvent.change(screen.getByLabelText('Access key'), {
        target: { value: 'a' },
      })
      fireEvent.change(screen.getByLabelText('Secret key'), {
        target: { value: 's' },
      })
      fireEvent.click(screen.getByText('Save'))
      expect(
        await screen.findByText(
          'A storage connection with this name already exists'
        )
      ).toBeInTheDocument()
    })

    it('toggles secret key visibility', async () => {
      await openCreateForm()
      const secretInput = screen.getByLabelText('Secret key')
      expect(secretInput).toHaveAttribute('type', 'password')
      fireEvent.click(screen.getByLabelText('Show/hide secret key'))
      expect(secretInput).toHaveAttribute('type', 'text')
    })

    it('tests unsaved params via the test endpoint and shows the result', async () => {
      mockTestStorageConnection.mockResolvedValue({
        status: 'success',
        message: 'Bucket reachable, 12 objects visible',
      })
      await openCreateForm()

      // Test is disabled until bucket + credentials are present.
      const testButton = screen.getByText('Test connection')
      expect(testButton).toBeDisabled()

      fireEvent.change(screen.getByLabelText('Bucket'), {
        target: { value: 'bucket-a' },
      })
      fireEvent.change(screen.getByLabelText('Access key'), {
        target: { value: 'AKIA123' },
      })
      fireEvent.change(screen.getByLabelText('Secret key'), {
        target: { value: 'secret456' },
      })
      expect(testButton).not.toBeDisabled()
      fireEvent.click(testButton)

      await waitFor(() =>
        expect(mockTestStorageConnection).toHaveBeenCalledWith(
          'org-1',
          expect.objectContaining({
            bucket: 'bucket-a',
            access_key: 'AKIA123',
            secret_key: 'secret456',
          })
        )
      )
      expect(
        await screen.findByText('Bucket reachable, 12 objects visible')
      ).toBeInTheDocument()
    })
  })

  describe('Editing a connection', () => {
    it('prefills metadata, leaves credentials empty and omits them on save', async () => {
      mockListStorageConnections.mockResolvedValue([CONN])
      mockUpdateStorageConnection.mockResolvedValue(CONN)
      renderModal()
      fireEvent.click(await screen.findByText('Edit'))

      expect(screen.getByText('Edit storage connection')).toBeInTheDocument()
      expect(screen.getByLabelText('Name')).toHaveValue('Chair bucket')
      expect(screen.getByLabelText('Bucket')).toHaveValue('law-exams')
      expect(screen.getByLabelText('Prefix')).toHaveValue('imports/')
      expect(screen.getByLabelText('Access key')).toHaveValue('')
      expect(screen.getByLabelText('Secret key')).toHaveValue('')

      fireEvent.change(screen.getByLabelText('Name'), {
        target: { value: 'Renamed' },
      })
      fireEvent.click(screen.getByText('Save'))

      await waitFor(() =>
        expect(mockUpdateStorageConnection).toHaveBeenCalledWith(
          'org-1',
          'conn-1',
          {
            name: 'Renamed',
            endpoint_url: 'https://minio.example.org',
            bucket: 'law-exams',
            prefix: 'imports/',
            region: null,
            use_ssl: true,
          }
        )
      )
      // Credentials NOT included when left empty.
      const body = mockUpdateStorageConnection.mock.calls[0][2]
      expect(body).not.toHaveProperty('access_key')
      expect(body).not.toHaveProperty('secret_key')
      expect(
        await screen.findByText('Storage connection "Renamed" updated')
      ).toBeInTheDocument()
    })

    it('includes re-entered credentials on save', async () => {
      mockListStorageConnections.mockResolvedValue([CONN])
      mockUpdateStorageConnection.mockResolvedValue(CONN)
      renderModal()
      fireEvent.click(await screen.findByText('Edit'))

      fireEvent.change(screen.getByLabelText('Secret key'), {
        target: { value: 'new-secret' },
      })
      fireEvent.click(screen.getByText('Save'))

      await waitFor(() =>
        expect(mockUpdateStorageConnection).toHaveBeenCalledWith(
          'org-1',
          'conn-1',
          expect.objectContaining({ secret_key: 'new-secret' })
        )
      )
      expect(mockUpdateStorageConnection.mock.calls[0][2]).not.toHaveProperty(
        'access_key'
      )
    })
  })

  describe('Testing a saved connection', () => {
    it('calls the saved-test endpoint and shows the result', async () => {
      mockListStorageConnections.mockResolvedValue([CONN])
      mockTestSavedStorageConnection.mockResolvedValue({
        status: 'error',
        message: 'Access denied on bucket',
      })
      renderModal()
      fireEvent.click(await screen.findByText('Test connection'))

      await waitFor(() =>
        expect(mockTestSavedStorageConnection).toHaveBeenCalledWith(
          'org-1',
          'conn-1'
        )
      )
      expect(
        await screen.findByText('Access denied on bucket')
      ).toBeInTheDocument()
    })

    it('shows the fallback error when the test request itself fails', async () => {
      mockListStorageConnections.mockResolvedValue([CONN])
      mockTestSavedStorageConnection.mockRejectedValue(new Error('timeout'))
      renderModal()
      fireEvent.click(await screen.findByText('Test connection'))
      expect(
        await screen.findByText('Connection test failed')
      ).toBeInTheDocument()
    })
  })

  describe('Deleting a connection', () => {
    it('requires an inline confirm before deleting', async () => {
      mockListStorageConnections.mockResolvedValue([CONN])
      mockDeleteStorageConnection.mockResolvedValue({ message: 'deleted' })
      renderModal()
      fireEvent.click(await screen.findByText('Delete'))

      // Nothing deleted yet — the confirm step appears.
      expect(mockDeleteStorageConnection).not.toHaveBeenCalled()
      expect(screen.getByText('Really delete?')).toBeInTheDocument()

      fireEvent.click(screen.getByText('Yes, delete'))
      await waitFor(() =>
        expect(mockDeleteStorageConnection).toHaveBeenCalledWith(
          'org-1',
          'conn-1'
        )
      )
      expect(
        await screen.findByText('Storage connection "Chair bucket" deleted')
      ).toBeInTheDocument()
    })

    it('cancel aborts the delete', async () => {
      mockListStorageConnections.mockResolvedValue([CONN])
      renderModal()
      fireEvent.click(await screen.findByText('Delete'))
      fireEvent.click(screen.getByText('Cancel'))
      expect(mockDeleteStorageConnection).not.toHaveBeenCalled()
      expect(screen.queryByText('Really delete?')).not.toBeInTheDocument()
    })

    it('shows the API error detail on delete failure', async () => {
      mockListStorageConnections.mockResolvedValue([CONN])
      mockDeleteStorageConnection.mockRejectedValue({
        response: { data: { detail: 'Nope' } },
      })
      renderModal()
      fireEvent.click(await screen.findByText('Delete'))
      fireEvent.click(screen.getByText('Yes, delete'))
      expect(await screen.findByText('Nope')).toBeInTheDocument()
    })
  })

  describe('Dialog close', () => {
    it('calls onOpenChange(false) via the close button and Done', async () => {
      const onOpenChange = jest.fn()
      renderModal({ onOpenChange })
      fireEvent.click(screen.getByLabelText('Close modal'))
      expect(onOpenChange).toHaveBeenCalledWith(false)
      fireEvent.click(screen.getByText('Done'))
      expect(onOpenChange).toHaveBeenCalledTimes(2)
    })
  })
})

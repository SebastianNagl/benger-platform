/**
 * CustomModelCredentialRow — per-user API key management for one custom
 * model (BYOM), backed by the /custom-models/{id}/credential endpoints.
 */

import { customModelsAPI } from '@/lib/api/customModels'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { CustomModelCredentialRow } from '../CustomModelCredentialRow'

jest.mock('@/lib/api/customModels', () => ({
  customModelsAPI: {
    getCredentialStatus: jest.fn(),
    setCredential: jest.fn(),
    deleteCredential: jest.fn(),
    testConnection: jest.fn(),
  },
}))

const defaultProps = {
  modelId: 'custom-1',
  baseUrl: 'https://api.example.com/v1',
  requiresApiKey: true,
}

describe('CustomModelCredentialRow', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    ;(customModelsAPI.getCredentialStatus as jest.Mock).mockResolvedValue({
      has_credential: false,
    })
    ;(customModelsAPI.setCredential as jest.Mock).mockResolvedValue({
      has_credential: true,
    })
    ;(customModelsAPI.deleteCredential as jest.Mock).mockResolvedValue(
      undefined
    )
    ;(customModelsAPI.testConnection as jest.Mock).mockResolvedValue({
      status: 'success',
      message: 'Connection ok',
    })
  })

  it('shows the endpoint the key will be sent to', async () => {
    render(<CustomModelCredentialRow {...defaultProps} />)

    expect(
      screen.getByText('https://api.example.com/v1')
    ).toBeInTheDocument()
  })

  it('derives the status pill from the credential GET', async () => {
    ;(customModelsAPI.getCredentialStatus as jest.Mock).mockResolvedValue({
      has_credential: true,
    })

    render(<CustomModelCredentialRow {...defaultProps} />)

    await waitFor(() => {
      expect(customModelsAPI.getCredentialStatus).toHaveBeenCalledWith(
        'custom-1'
      )
    })
    await waitFor(() => {
      expect(screen.getByTestId('credential-status-pill')).toHaveTextContent(
        'customModels.credential.configured'
      )
    })
    // Configured state: remove button instead of the key input.
    expect(
      screen.getByTestId('credential-remove-button')
    ).toBeInTheDocument()
    expect(
      screen.queryByTestId('credential-key-input')
    ).not.toBeInTheDocument()
  })

  it('saves a key via PUT and dispatches apiKeysChanged', async () => {
    const user = userEvent.setup()
    const keysChangedListener = jest.fn()
    window.addEventListener('apiKeysChanged', keysChangedListener)

    const onChanged = jest.fn()
    render(
      <CustomModelCredentialRow {...defaultProps} onChanged={onChanged} />
    )

    await waitFor(() => {
      expect(screen.getByTestId('credential-key-input')).toBeInTheDocument()
    })

    await user.type(screen.getByTestId('credential-key-input'), 'sk-test')
    await user.click(screen.getByTestId('credential-save-button'))

    await waitFor(() => {
      expect(customModelsAPI.setCredential).toHaveBeenCalledWith(
        'custom-1',
        'sk-test'
      )
    })
    expect(keysChangedListener).toHaveBeenCalled()
    expect(onChanged).toHaveBeenCalled()

    // Pill flips to configured without a refetch round-trip.
    expect(screen.getByTestId('credential-status-pill')).toHaveTextContent(
      'customModels.credential.configured'
    )

    window.removeEventListener('apiKeysChanged', keysChangedListener)
  })

  it('shows a success box after a successful test with an unsaved key', async () => {
    const user = userEvent.setup()
    render(<CustomModelCredentialRow {...defaultProps} />)

    await waitFor(() => {
      expect(screen.getByTestId('credential-key-input')).toBeInTheDocument()
    })

    await user.type(screen.getByTestId('credential-key-input'), 'sk-test')
    await user.click(screen.getByTestId('credential-test-button'))

    await waitFor(() => {
      expect(customModelsAPI.testConnection).toHaveBeenCalledWith(
        'custom-1',
        { api_key: 'sk-test' }
      )
    })
    expect(
      screen.getByTestId('credential-test-result')
    ).toHaveTextContent('Connection ok')
  })

  it('shows an error box when the test fails', async () => {
    const user = userEvent.setup()
    ;(customModelsAPI.testConnection as jest.Mock).mockResolvedValue({
      status: 'error',
      message: 'Invalid key',
      error_type: 'auth',
    })

    render(<CustomModelCredentialRow {...defaultProps} />)

    await waitFor(() => {
      expect(screen.getByTestId('credential-key-input')).toBeInTheDocument()
    })

    await user.type(screen.getByTestId('credential-key-input'), 'sk-bad')
    await user.click(screen.getByTestId('credential-test-button'))

    await waitFor(() => {
      expect(
        screen.getByTestId('credential-test-result')
      ).toHaveTextContent('Invalid key')
    })
  })

  it('removes the stored key and dispatches apiKeysChanged', async () => {
    const user = userEvent.setup()
    const keysChangedListener = jest.fn()
    window.addEventListener('apiKeysChanged', keysChangedListener)
    ;(customModelsAPI.getCredentialStatus as jest.Mock).mockResolvedValue({
      has_credential: true,
    })

    render(<CustomModelCredentialRow {...defaultProps} />)

    await waitFor(() => {
      expect(
        screen.getByTestId('credential-remove-button')
      ).toBeInTheDocument()
    })

    await user.click(screen.getByTestId('credential-remove-button'))

    await waitFor(() => {
      expect(customModelsAPI.deleteCredential).toHaveBeenCalledWith(
        'custom-1'
      )
    })
    expect(keysChangedListener).toHaveBeenCalled()
    expect(screen.getByTestId('credential-status-pill')).toHaveTextContent(
      'customModels.credential.notConfigured'
    )

    window.removeEventListener('apiKeysChanged', keysChangedListener)
  })

  describe('keyless models (requires_api_key: false)', () => {
    it('renders the informational state with only a Test button', async () => {
      const user = userEvent.setup()
      render(
        <CustomModelCredentialRow {...defaultProps} requiresApiKey={false} />
      )

      expect(
        screen.getByTestId('credential-no-key-required')
      ).toBeInTheDocument()
      expect(
        screen.queryByTestId('credential-key-input')
      ).not.toBeInTheDocument()
      expect(
        screen.queryByTestId('credential-save-button')
      ).not.toBeInTheDocument()
      expect(
        screen.queryByTestId('credential-status-pill')
      ).not.toBeInTheDocument()
      // No credential status fetch for keyless models.
      expect(customModelsAPI.getCredentialStatus).not.toHaveBeenCalled()

      await user.click(screen.getByTestId('credential-test-button'))

      await waitFor(() => {
        expect(customModelsAPI.testConnection).toHaveBeenCalledWith(
          'custom-1',
          {}
        )
      })
      expect(
        screen.getByTestId('credential-test-result')
      ).toHaveTextContent('Connection ok')
    })
  })
})

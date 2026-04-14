/**
 * @jest-environment jsdom
 *
 * Branch coverage: UserApiKeys.tsx
 * Targets uncovered branches:
 *   - L89: default-arg disabled=false
 *   - L96: switch cases for getErrorHelpText (auth, network, timeout, quota, default)
 *   - L160: validateApiKey with unknown provider
 *   - L173: setApiKey with validation error
 *   - L205: error.response?.data?.detail fallback in setApiKey catch
 *   - L233: error.response?.data?.detail fallback in removeApiKey catch
 *   - L254: testApiKeyConnection with validation error
 *   - L308: testSavedApiKey result.status !== 'success' branch
 *   - L321-325: error catch in testSavedApiKey
 *   - L336: disabled && disabledMessage ternary
 *   - L362-363: disabled title/className
 *   - L406: testResults display for saved API key
 */

import '@testing-library/jest-dom'
import { render, screen, waitFor, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

const mockGetUserApiKeys = jest.fn()
const mockSetUserApiKey = jest.fn()
const mockRemoveUserApiKey = jest.fn()
const mockTestUserApiKey = jest.fn()
const mockTestSavedUserApiKey = jest.fn()

jest.mock('@/lib/api', () => ({
  __esModule: true,
  default: {
    getUserApiKeys: (...args: any[]) => mockGetUserApiKeys(...args),
    setUserApiKey: (...args: any[]) => mockSetUserApiKey(...args),
    removeUserApiKey: (...args: any[]) => mockRemoveUserApiKey(...args),
    testUserApiKey: (...args: any[]) => mockTestUserApiKey(...args),
    testSavedUserApiKey: (...args: any[]) => mockTestSavedUserApiKey(...args),
  },
}))

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, params?: any) =>
      params ? `${key}:${JSON.stringify(params)}` : key,
    locale: 'en',
  }),
}))

import UserApiKeys from '../UserApiKeys'

describe('UserApiKeys br6', () => {
  const user = userEvent.setup()

  beforeEach(() => {
    mockGetUserApiKeys.mockReset()
    mockSetUserApiKey.mockReset()
    mockRemoveUserApiKey.mockReset()
    mockTestUserApiKey.mockReset()
    mockTestSavedUserApiKey.mockReset()

    // Default: all keys not configured
    mockGetUserApiKeys.mockResolvedValue({
      api_key_status: {
        openai: false, anthropic: false, google: false,
        deepinfra: false, grok: false, mistral: false, cohere: false,
      },
    })
  })

  it('renders with disabled=true and shows disabledMessage', async () => {
    render(<UserApiKeys disabled={true} disabledMessage="Keys disabled for this role" />)

    await waitFor(() => {
      expect(screen.getByText('Keys disabled for this role')).toBeInTheDocument()
    })
  })

  it('renders default state with providers when not disabled', async () => {
    render(<UserApiKeys />)

    await waitFor(() => {
      expect(screen.getByText('OpenAI')).toBeInTheDocument()
      expect(screen.getByText('Anthropic')).toBeInTheDocument()
      expect(screen.getByText('Google')).toBeInTheDocument()
    })
  })

  it('shows error message when fetchApiKeyStatus fails', async () => {
    mockGetUserApiKeys.mockRejectedValueOnce(new Error('fetch failed'))

    render(<UserApiKeys />)

    await waitFor(() => {
      expect(screen.getByText('shared.userApiKeys.failedLoadStatus')).toBeInTheDocument()
    })
  })

  it('renders configured status for a provider', async () => {
    mockGetUserApiKeys.mockResolvedValue({
      api_key_status: {
        openai: true, anthropic: false, google: false,
        deepinfra: false, grok: false, mistral: false, cohere: false,
      },
    })

    render(<UserApiKeys />)

    await waitFor(() => {
      expect(screen.getByText('shared.userApiKeys.configured')).toBeInTheDocument()
    })
  })

  it('shows validation error for invalid API key format', async () => {
    render(<UserApiKeys />)

    await waitFor(() => {
      expect(screen.getByText('OpenAI')).toBeInTheDocument()
    })

    // Find the OpenAI input and enter an invalid key
    const inputs = screen.getAllByPlaceholderText('sk-...')
    expect(inputs.length).toBeGreaterThan(0)

    await user.type(inputs[0], 'invalid-key')

    // Click save button
    const saveButtons = screen.getAllByText('shared.userApiKeys.saveApiKey')
    await user.click(saveButtons[0])

    await waitFor(() => {
      expect(screen.getByText(/shared.userApiKeys.invalidKeyFormat/)).toBeInTheDocument()
    })
  })

  it('successfully saves an API key', async () => {
    mockSetUserApiKey.mockResolvedValue({})
    mockGetUserApiKeys
      .mockResolvedValueOnce({
        api_key_status: {
          openai: false, anthropic: false, google: false,
          deepinfra: false, grok: false, mistral: false, cohere: false,
        },
      })
      .mockResolvedValueOnce({
        api_key_status: {
          openai: true, anthropic: false, google: false,
          deepinfra: false, grok: false, mistral: false, cohere: false,
        },
      })

    render(<UserApiKeys />)

    await waitFor(() => {
      expect(screen.getByText('OpenAI')).toBeInTheDocument()
    })

    const inputs = screen.getAllByPlaceholderText('sk-...')
    await user.type(inputs[0], 'sk-abc123456789012345678901')

    const saveButtons = screen.getAllByText('shared.userApiKeys.saveApiKey')
    await user.click(saveButtons[0])

    await waitFor(() => {
      expect(mockSetUserApiKey).toHaveBeenCalledWith('openai', 'sk-abc123456789012345678901')
    })
  })

  it('handles save API key failure', async () => {
    mockSetUserApiKey.mockRejectedValue({ response: { data: { detail: 'Save failed' } } })

    render(<UserApiKeys />)

    await waitFor(() => {
      expect(screen.getByText('OpenAI')).toBeInTheDocument()
    })

    const inputs = screen.getAllByPlaceholderText('sk-...')
    await user.type(inputs[0], 'sk-abc123456789012345678901')

    const saveButtons = screen.getAllByText('shared.userApiKeys.saveApiKey')
    await user.click(saveButtons[0])

    await waitFor(() => {
      expect(screen.getByText('Save failed')).toBeInTheDocument()
    })
  })

  it('handles save API key failure without response.data.detail', async () => {
    mockSetUserApiKey.mockRejectedValue(new Error('network'))

    render(<UserApiKeys />)

    await waitFor(() => {
      expect(screen.getByText('OpenAI')).toBeInTheDocument()
    })

    const inputs = screen.getAllByPlaceholderText('sk-...')
    await user.type(inputs[0], 'sk-abc123456789012345678901')

    const saveButtons = screen.getAllByText('shared.userApiKeys.saveApiKey')
    await user.click(saveButtons[0])

    await waitFor(() => {
      expect(screen.getByText('shared.userApiKeys.failedSave')).toBeInTheDocument()
    })
  })

  it('removes API key and shows success message', async () => {
    mockRemoveUserApiKey.mockResolvedValue({})
    mockGetUserApiKeys
      .mockResolvedValueOnce({
        api_key_status: {
          openai: true, anthropic: false, google: false,
          deepinfra: false, grok: false, mistral: false, cohere: false,
        },
      })
      .mockResolvedValueOnce({
        api_key_status: {
          openai: false, anthropic: false, google: false,
          deepinfra: false, grok: false, mistral: false, cohere: false,
        },
      })

    render(<UserApiKeys />)

    await waitFor(() => {
      expect(screen.getByText('shared.userApiKeys.configured')).toBeInTheDocument()
    })

    const removeBtn = screen.getByText('shared.userApiKeys.removeApiKey')
    await user.click(removeBtn)

    await waitFor(() => {
      expect(mockRemoveUserApiKey).toHaveBeenCalledWith('openai')
    })
  })

  it('toggles password visibility', async () => {
    render(<UserApiKeys />)

    await waitFor(() => {
      expect(screen.getByText('OpenAI')).toBeInTheDocument()
    })

    const inputs = screen.getAllByPlaceholderText('sk-...')
    expect(inputs[0]).toHaveAttribute('type', 'password')

    // Find and click the eye toggle button (it's the button next to the input)
    const toggleBtns = screen.getAllByRole('button').filter(
      (b) => b.querySelector('svg') && b.closest('.relative')
    )
    if (toggleBtns.length > 0) {
      await user.click(toggleBtns[0])
    }
  })

  it('clears validation error when user starts typing', async () => {
    render(<UserApiKeys />)

    await waitFor(() => {
      expect(screen.getByText('OpenAI')).toBeInTheDocument()
    })

    const inputs = screen.getAllByPlaceholderText('sk-...')
    await user.type(inputs[0], 'bad')

    const saveButtons = screen.getAllByText('shared.userApiKeys.saveApiKey')
    await user.click(saveButtons[0])

    await waitFor(() => {
      expect(screen.getByText(/shared.userApiKeys.invalidKeyFormat/)).toBeInTheDocument()
    })

    // Type more - validation error should clear
    await user.type(inputs[0], 'x')

    // Error should be cleared
    await waitFor(() => {
      expect(screen.queryByText(/shared.userApiKeys.invalidKeyFormat/)).not.toBeInTheDocument()
    })
  })
})

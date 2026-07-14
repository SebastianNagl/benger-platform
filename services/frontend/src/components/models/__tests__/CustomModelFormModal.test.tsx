/**
 * CustomModelFormModal — register/edit form for custom models (BYOM).
 */

import { customModelsAPI } from '@/lib/api/customModels'
import type { CustomModel } from '@/lib/api/types'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { CustomModelFormModal } from '../CustomModelFormModal'

jest.mock('@/lib/api/customModels', () => ({
  customModelsAPI: {
    create: jest.fn(),
    update: jest.fn(),
    testConnection: jest.fn(),
  },
}))

const createdModel: CustomModel = {
  id: 'custom-new',
  name: 'My Model',
  description: 'Desc',
  provider: 'Custom',
  model_type: 'chat',
  capabilities: ['text-generation'],
  base_url: 'https://api.example.com/v1',
  endpoint_model_name: 'llama-x',
  requires_api_key: true,
  input_cost_per_million: 1.5,
  output_cost_per_million: 2,
  parameter_constraints: null,
  is_active: true,
  is_official: false,
  created_by: 'user-1',
  created_by_username: 'me',
  is_private: true,
  is_public: false,
  organization_ids: [],
  has_credential: true,
  can_edit: true,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: null,
}

const existingModel: CustomModel = {
  ...createdModel,
  id: 'custom-42',
  name: 'Old Name',
  description: '',
  input_cost_per_million: null,
  output_cost_per_million: null,
}

describe('CustomModelFormModal', () => {
  const mockOnClose = jest.fn()
  const mockOnSaved = jest.fn()

  beforeEach(() => {
    jest.clearAllMocks()
    ;(customModelsAPI.create as jest.Mock).mockResolvedValue(createdModel)
    ;(customModelsAPI.update as jest.Mock).mockResolvedValue(existingModel)
    ;(customModelsAPI.testConnection as jest.Mock).mockResolvedValue({
      status: 'success',
      message: 'Connection ok',
    })
  })

  const fillRequired = async (
    user: ReturnType<typeof userEvent.setup>,
    baseUrl = 'https://api.example.com/v1'
  ) => {
    await user.type(
      screen.getByTestId('custom-model-name-input'),
      'My Model'
    )
    await user.type(
      screen.getByTestId('custom-model-base-url-input'),
      baseUrl
    )
    await user.type(
      screen.getByTestId('custom-model-endpoint-name-input'),
      'llama-x'
    )
  }

  describe('Validation', () => {
    it('rejects an empty form and does not call create', async () => {
      const user = userEvent.setup()
      render(<CustomModelFormModal isOpen onClose={mockOnClose} />)

      await user.click(screen.getByTestId('custom-model-form-submit'))

      expect(
        screen.getByTestId('custom-model-error-name')
      ).toBeInTheDocument()
      expect(
        screen.getByTestId('custom-model-error-base_url')
      ).toBeInTheDocument()
      expect(
        screen.getByTestId('custom-model-error-endpoint_model_name')
      ).toBeInTheDocument()
      expect(customModelsAPI.create).not.toHaveBeenCalled()
    })

    it('rejects a non-URL base_url', async () => {
      const user = userEvent.setup()
      render(<CustomModelFormModal isOpen onClose={mockOnClose} />)

      await fillRequired(user, 'not-a-url')
      await user.click(screen.getByTestId('custom-model-form-submit'))

      expect(
        screen.getByTestId('custom-model-error-base_url')
      ).toBeInTheDocument()
      expect(customModelsAPI.create).not.toHaveBeenCalled()
    })

    it('rejects a non-http(s) scheme', async () => {
      const user = userEvent.setup()
      render(<CustomModelFormModal isOpen onClose={mockOnClose} />)

      await fillRequired(user, 'ftp://x')
      await user.click(screen.getByTestId('custom-model-form-submit'))

      expect(
        screen.getByTestId('custom-model-error-base_url')
      ).toBeInTheDocument()
      expect(customModelsAPI.create).not.toHaveBeenCalled()
    })

    it('accepts http://localhost URLs', async () => {
      const user = userEvent.setup()
      render(<CustomModelFormModal isOpen onClose={mockOnClose} />)

      await fillRequired(user, 'http://localhost:8000/v1')

      expect(
        screen.queryByTestId('custom-model-http-warning')
      ).not.toBeInTheDocument()

      await user.click(screen.getByTestId('custom-model-form-submit'))

      await waitFor(() => {
        expect(customModelsAPI.create).toHaveBeenCalled()
      })
      expect(
        screen.queryByTestId('custom-model-error-base_url')
      ).not.toBeInTheDocument()
    })

    it('warns about plain http to a non-localhost host', async () => {
      const user = userEvent.setup()
      render(<CustomModelFormModal isOpen onClose={mockOnClose} />)

      await user.type(
        screen.getByTestId('custom-model-base-url-input'),
        'http://myserver.example.com/v1'
      )

      expect(
        screen.getByTestId('custom-model-http-warning')
      ).toBeInTheDocument()
    })

    it('enforces both-or-neither pricing', async () => {
      const user = userEvent.setup()
      render(<CustomModelFormModal isOpen onClose={mockOnClose} />)

      await fillRequired(user)
      await user.type(
        screen.getByTestId('custom-model-input-cost-input'),
        '1.5'
      )
      await user.click(screen.getByTestId('custom-model-form-submit'))

      expect(
        screen.getByTestId('custom-model-error-input_cost')
      ).toBeInTheDocument()
      expect(customModelsAPI.create).not.toHaveBeenCalled()
    })
  })

  describe('Create', () => {
    it('POSTs the full payload and shows the success step', async () => {
      const user = userEvent.setup()
      render(
        <CustomModelFormModal
          isOpen
          onClose={mockOnClose}
          onSaved={mockOnSaved}
        />
      )

      await fillRequired(user)
      await user.type(
        screen.getByTestId('custom-model-description-input'),
        'Desc'
      )
      await user.type(
        screen.getByTestId('custom-model-input-cost-input'),
        '1.5'
      )
      await user.type(
        screen.getByTestId('custom-model-output-cost-input'),
        '2'
      )
      await user.type(
        screen.getByTestId('custom-model-api-key-input'),
        'sk-abc'
      )
      await user.click(screen.getByTestId('custom-model-form-submit'))

      await waitFor(() => {
        expect(customModelsAPI.create).toHaveBeenCalledWith({
          name: 'My Model',
          description: 'Desc',
          base_url: 'https://api.example.com/v1',
          endpoint_model_name: 'llama-x',
          requires_api_key: true,
          input_cost_per_million: 1.5,
          output_cost_per_million: 2,
          api_key: 'sk-abc',
        })
      })

      // Success step with test-connection offer; modal stays open.
      expect(
        screen.getByTestId('custom-model-form-success')
      ).toBeInTheDocument()
      expect(mockOnSaved).toHaveBeenCalledWith(createdModel)
      expect(mockOnClose).not.toHaveBeenCalled()

      await user.click(screen.getByTestId('custom-model-form-test-button'))

      await waitFor(() => {
        expect(customModelsAPI.testConnection).toHaveBeenCalledWith(
          'custom-new'
        )
      })
      expect(
        screen.getByTestId('custom-model-form-test-result')
      ).toHaveTextContent('Connection ok')

      await user.click(screen.getByTestId('custom-model-form-close-button'))
      expect(mockOnClose).toHaveBeenCalled()
    })
  })

  describe('Edit', () => {
    it('prefills the form and PATCHes only the changed fields', async () => {
      const user = userEvent.setup()
      render(
        <CustomModelFormModal
          isOpen
          onClose={mockOnClose}
          model={existingModel}
          onSaved={mockOnSaved}
        />
      )

      const nameInput = screen.getByTestId(
        'custom-model-name-input'
      ) as HTMLInputElement
      expect(nameInput.value).toBe('Old Name')
      expect(
        (screen.getByTestId('custom-model-base-url-input') as HTMLInputElement)
          .value
      ).toBe('https://api.example.com/v1')

      // No api_key field in edit mode - credentials live in the row.
      expect(
        screen.queryByTestId('custom-model-api-key-input')
      ).not.toBeInTheDocument()

      await user.clear(nameInput)
      await user.type(nameInput, 'New Name')
      await user.click(screen.getByTestId('custom-model-form-submit'))

      await waitFor(() => {
        expect(customModelsAPI.update).toHaveBeenCalledWith('custom-42', {
          name: 'New Name',
        })
      })
      expect(mockOnClose).toHaveBeenCalled()
    })
  })
})

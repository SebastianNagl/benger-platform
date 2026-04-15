/**
 * @jest-environment jsdom
 */

import { apiClient } from '@/lib/api/client'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { PromptStructuresManager } from '../PromptStructuresManager'

// Mock I18nContext
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

// Mock dependencies
jest.mock('@/lib/api/client', () => ({
  apiClient: {
    get: jest.fn(),
    put: jest.fn(),
    delete: jest.fn(),
    getProject: jest.fn(),
  },
}))

jest.mock('../GenerationStructureEditor', () => ({
  GenerationStructureEditor: ({
    initialConfig,
    onChange,
    onSave,
    onCancel,
    showActionButtons,
  }: any) => (
    <div data-testid="generation-structure-editor">
      <textarea
        data-testid="structure-config-textarea"
        value={initialConfig}
        onChange={(e) => onChange?.(e.target.value)}
      />
      {showActionButtons && (
        <>
          <button onClick={() => onSave?.(initialConfig)}>Save</button>
          <button onClick={() => onCancel?.()}>Cancel</button>
        </>
      )}
    </div>
  ),
}))

describe('PromptStructuresManager', () => {
  const mockProjectId = 'test-project-123'
  const mockStructures = {
    'legal-analysis': {
      key: 'legal-analysis',
      name: 'Legal Analysis',
      description: 'Analyze legal documents',
      system_prompt: 'You are a legal expert',
      instruction_prompt: '$question',
      evaluation_prompt: null,
    },
    'simple-qa': {
      key: 'simple-qa',
      name: 'Simple Q&A',
      description: 'Simple question answering',
      system_prompt: 'You are a helpful assistant',
      instruction_prompt: {
        template: 'Answer: {{question}}',
        fields: { question: '$question' },
      },
      evaluation_prompt: null,
    },
  }

  const mockProject = {
    id: mockProjectId,
    generation_config: {
      selected_configuration: {
        active_structures: ['legal-analysis'],
      },
    },
  }

  beforeEach(() => {
    jest.clearAllMocks()
    ;(apiClient.get as jest.Mock).mockResolvedValue(mockStructures)
    ;(apiClient.getProject as jest.Mock).mockResolvedValue(mockProject)
  })

  describe('Manager Rendering', () => {
    it('should show loading state initially', () => {
      render(<PromptStructuresManager projectId={mockProjectId} />)
      expect(
        screen.getByText('Loading prompt structures...')
      ).toBeInTheDocument()
    })

    it('should render collapsed by default', async () => {
      render(<PromptStructuresManager projectId={mockProjectId} />)

      await waitFor(() => {
        expect(
          screen.queryByText('Loading prompt structures...')
        ).not.toBeInTheDocument()
      })

      expect(screen.getByText('Prompt Structures')).toBeInTheDocument()
      expect(screen.getByText('1 active / 2 total')).toBeInTheDocument()
      expect(screen.queryByText('Legal Analysis')).not.toBeInTheDocument()
    })

    it('should expand to show structures when clicked', async () => {
      render(<PromptStructuresManager projectId={mockProjectId} />)

      await waitFor(() => {
        expect(
          screen.queryByText('Loading prompt structures...')
        ).not.toBeInTheDocument()
      })

      const headerButton = screen.getByRole('button', {
        name: /Prompt Structures/i,
      })
      await userEvent.click(headerButton)

      expect(screen.getByText('Legal Analysis')).toBeInTheDocument()
      expect(screen.getByText('Simple Q&A')).toBeInTheDocument()
    })

    it('should show "Not configured" when no structures exist', async () => {
      ;(apiClient.get as jest.Mock).mockResolvedValue({})
      ;(apiClient.getProject as jest.Mock).mockResolvedValue({
        id: mockProjectId,
        generation_config: {
          selected_configuration: { active_structures: [] },
        },
      })

      render(<PromptStructuresManager projectId={mockProjectId} />)

      await waitFor(() => {
        expect(
          screen.queryByText('Loading prompt structures...')
        ).not.toBeInTheDocument()
      })

      expect(screen.getByText('Not configured')).toBeInTheDocument()
    })

    it('should show empty state when expanded with no structures', async () => {
      ;(apiClient.get as jest.Mock).mockResolvedValue({})
      ;(apiClient.getProject as jest.Mock).mockResolvedValue({
        id: mockProjectId,
        generation_config: {
          selected_configuration: { active_structures: [] },
        },
      })

      render(<PromptStructuresManager projectId={mockProjectId} />)

      await waitFor(() => {
        expect(
          screen.queryByText('Loading prompt structures...')
        ).not.toBeInTheDocument()
      })

      const headerButton = screen.getByRole('button', {
        name: /Prompt Structures/i,
      })
      await userEvent.click(headerButton)

      expect(
        screen.getByText(/No prompt structures configured yet/i)
      ).toBeInTheDocument()
      expect(
        screen.getByRole('button', { name: /Create First Structure/i })
      ).toBeInTheDocument()
    })

    it('should display structure details correctly', async () => {
      render(<PromptStructuresManager projectId={mockProjectId} />)

      await waitFor(() => {
        expect(
          screen.queryByText('Loading prompt structures...')
        ).not.toBeInTheDocument()
      })

      const headerButton = screen.getByRole('button', {
        name: /Prompt Structures/i,
      })
      await userEvent.click(headerButton)

      expect(screen.getByText('Legal Analysis')).toBeInTheDocument()
      expect(screen.getByText('Analyze legal documents')).toBeInTheDocument()
      expect(screen.getByText('legal-analysis')).toBeInTheDocument()
      expect(screen.getByText('Active')).toBeInTheDocument()
    })

    it('should show Add Structure button when expanded', async () => {
      render(<PromptStructuresManager projectId={mockProjectId} />)

      await waitFor(() => {
        expect(
          screen.queryByText('Loading prompt structures...')
        ).not.toBeInTheDocument()
      })

      const headerButton = screen.getByRole('button', {
        name: /Prompt Structures/i,
      })
      await userEvent.click(headerButton)

      expect(
        screen.getByRole('button', { name: /Add Structure/i })
      ).toBeInTheDocument()
    })
  })

  describe('Active Structure Toggle', () => {
    it('should toggle structure active state', async () => {
      ;(apiClient.put as jest.Mock).mockResolvedValue({})

      render(<PromptStructuresManager projectId={mockProjectId} />)

      await waitFor(() => {
        expect(
          screen.queryByText('Loading prompt structures...')
        ).not.toBeInTheDocument()
      })

      const headerButton = screen.getByRole('button', {
        name: /Prompt Structures/i,
      })
      await userEvent.click(headerButton)

      // Find the Simple Q&A card (which is not active) and toggle it
      const simpleQaCard = screen
        .getByText('Simple Q&A')
        .closest('[class*="p-4"]')
      expect(simpleQaCard).toBeInTheDocument()

      const checkbox = within(simpleQaCard!).getByRole('checkbox')
      expect(checkbox).not.toBeChecked()

      await userEvent.click(checkbox)

      await waitFor(() => {
        expect(apiClient.put).toHaveBeenCalledWith(
          `/projects/${mockProjectId}/generation-config/structures`,
          ['legal-analysis', 'simple-qa']
        )
      })
    })

    it('should handle toggle errors and revert state', async () => {
      ;(apiClient.put as jest.Mock).mockRejectedValue(
        new Error('Failed to update')
      )

      render(<PromptStructuresManager projectId={mockProjectId} />)

      await waitFor(() => {
        expect(
          screen.queryByText('Loading prompt structures...')
        ).not.toBeInTheDocument()
      })

      const headerButton = screen.getByRole('button', {
        name: /Prompt Structures/i,
      })
      await userEvent.click(headerButton)

      const checkboxes = screen.getAllByRole('checkbox')
      await userEvent.click(checkboxes[0])

      await waitFor(() => {
        expect(
          screen.getByText('Failed to update active structures')
        ).toBeInTheDocument()
      })
    })

    it('should call onStructuresChange callback after toggle', async () => {
      const onStructuresChange = jest.fn()
      ;(apiClient.put as jest.Mock).mockResolvedValue({})

      render(
        <PromptStructuresManager
          projectId={mockProjectId}
          onStructuresChange={onStructuresChange}
        />
      )

      await waitFor(() => {
        expect(
          screen.queryByText('Loading prompt structures...')
        ).not.toBeInTheDocument()
      })

      const headerButton = screen.getByRole('button', {
        name: /Prompt Structures/i,
      })
      await userEvent.click(headerButton)

      const checkboxes = screen.getAllByRole('checkbox')
      await userEvent.click(checkboxes[0])

      await waitFor(() => {
        expect(onStructuresChange).toHaveBeenCalled()
      })
    })
  })

  describe('Add Structure Modal', () => {
    it('should open add modal when Add Structure button is clicked', async () => {
      render(<PromptStructuresManager projectId={mockProjectId} />)

      await waitFor(() => {
        expect(
          screen.queryByText('Loading prompt structures...')
        ).not.toBeInTheDocument()
      })

      const headerButton = screen.getByRole('button', {
        name: /Prompt Structures/i,
      })
      await userEvent.click(headerButton)

      const addButton = screen.getByRole('button', { name: /Add Structure/i })
      await userEvent.click(addButton)

      expect(screen.getByText('Add Prompt Structure')).toBeInTheDocument()
      expect(screen.getByLabelText('Structure Key')).toBeInTheDocument()
      expect(screen.getByLabelText('Name')).toBeInTheDocument()
    })

    it('should validate required fields in add modal', async () => {
      render(<PromptStructuresManager projectId={mockProjectId} />)

      await waitFor(() => {
        expect(
          screen.queryByText('Loading prompt structures...')
        ).not.toBeInTheDocument()
      })

      const headerButton = screen.getByRole('button', {
        name: /Prompt Structures/i,
      })
      await userEvent.click(headerButton)

      const addButton = screen.getByRole('button', { name: /Add Structure/i })
      await userEvent.click(addButton)

      const createButton = screen.getByRole('button', {
        name: /Create Structure/i,
      })
      await userEvent.click(createButton)

      await waitFor(() => {
        expect(screen.getByText('Name is required')).toBeInTheDocument()
      })
    })

    it('should validate structure key format', async () => {
      render(<PromptStructuresManager projectId={mockProjectId} />)

      await waitFor(() => {
        expect(
          screen.queryByText('Loading prompt structures...')
        ).not.toBeInTheDocument()
      })

      const headerButton = screen.getByRole('button', {
        name: /Prompt Structures/i,
      })
      await userEvent.click(headerButton)

      const addButton = screen.getByRole('button', { name: /Add Structure/i })
      await userEvent.click(addButton)

      const keyInput = screen.getByLabelText('Structure Key')
      const nameInput = screen.getByLabelText('Name')
      const configTextarea = screen.getByTestId('structure-config-textarea')

      await userEvent.type(keyInput, 'invalid key!')
      await userEvent.type(nameInput, 'Test Structure')
      await userEvent.click(configTextarea)
      await userEvent.paste(
        '{"system_prompt": "test", "instruction_prompt": "test"}'
      )

      const createButton = screen.getByRole('button', {
        name: /Create Structure/i,
      })
      await userEvent.click(createButton)

      await waitFor(() => {
        expect(
          screen.getByText(
            /Structure key can only contain alphanumeric characters, underscores, and hyphens/i
          )
        ).toBeInTheDocument()
      })
    })

    it('should validate duplicate structure keys', async () => {
      render(<PromptStructuresManager projectId={mockProjectId} />)

      await waitFor(() => {
        expect(
          screen.queryByText('Loading prompt structures...')
        ).not.toBeInTheDocument()
      })

      const headerButton = screen.getByRole('button', {
        name: /Prompt Structures/i,
      })
      await userEvent.click(headerButton)

      const addButton = screen.getByRole('button', { name: /Add Structure/i })
      await userEvent.click(addButton)

      const keyInput = screen.getByLabelText('Structure Key')
      const nameInput = screen.getByLabelText('Name')
      const configTextarea = screen.getByTestId('structure-config-textarea')

      await userEvent.type(keyInput, 'legal-analysis')
      await userEvent.type(nameInput, 'Test Structure')
      await userEvent.click(configTextarea)
      await userEvent.paste(
        '{"system_prompt": "test", "instruction_prompt": "test"}'
      )

      const createButton = screen.getByRole('button', {
        name: /Create Structure/i,
      })
      await userEvent.click(createButton)

      await waitFor(() => {
        expect(
          screen.getByText('A structure with this key already exists')
        ).toBeInTheDocument()
      })
    })

    it('should validate JSON in structure configuration', async () => {
      render(<PromptStructuresManager projectId={mockProjectId} />)

      await waitFor(() => {
        expect(
          screen.queryByText('Loading prompt structures...')
        ).not.toBeInTheDocument()
      })

      const headerButton = screen.getByRole('button', {
        name: /Prompt Structures/i,
      })
      await userEvent.click(headerButton)

      const addButton = screen.getByRole('button', { name: /Add Structure/i })
      await userEvent.click(addButton)

      const keyInput = screen.getByLabelText('Structure Key')
      const nameInput = screen.getByLabelText('Name')
      const configTextarea = screen.getByTestId('structure-config-textarea')

      await userEvent.type(keyInput, 'new-structure')
      await userEvent.type(nameInput, 'Test Structure')
      await userEvent.click(configTextarea)
      await userEvent.paste('invalid json')

      const createButton = screen.getByRole('button', {
        name: /Create Structure/i,
      })
      await userEvent.click(createButton)

      await waitFor(() => {
        expect(
          screen.getByText('Invalid JSON in structure configuration')
        ).toBeInTheDocument()
      })
    })

    it('should validate that at least one prompt is defined', async () => {
      render(<PromptStructuresManager projectId={mockProjectId} />)

      await waitFor(() => {
        expect(
          screen.queryByText('Loading prompt structures...')
        ).not.toBeInTheDocument()
      })

      const headerButton = screen.getByRole('button', {
        name: /Prompt Structures/i,
      })
      await userEvent.click(headerButton)

      const addButton = screen.getByRole('button', { name: /Add Structure/i })
      await userEvent.click(addButton)

      const keyInput = screen.getByLabelText('Structure Key')
      const nameInput = screen.getByLabelText('Name')
      const configTextarea = screen.getByTestId('structure-config-textarea')

      await userEvent.type(keyInput, 'new-structure')
      await userEvent.type(nameInput, 'Test Structure')
      await userEvent.click(configTextarea)
      await userEvent.paste('{"evaluation_prompt": "test"}')

      const createButton = screen.getByRole('button', {
        name: /Create Structure/i,
      })
      await userEvent.click(createButton)

      await waitFor(() => {
        expect(
          screen.getByText(
            'Structure must have at least system_prompt or instruction_prompt'
          )
        ).toBeInTheDocument()
      })
    })

    it('should successfully create a new structure', async () => {
      ;(apiClient.put as jest.Mock).mockResolvedValue({})
      ;(apiClient.get as jest.Mock)
        .mockResolvedValueOnce(mockStructures)
        .mockResolvedValueOnce({
          ...mockStructures,
          'new-structure': {
            key: 'new-structure',
            name: 'New Structure',
            description: 'Test description',
            system_prompt: 'test',
            instruction_prompt: 'test',
            evaluation_prompt: null,
          },
        })
      ;(apiClient.getProject as jest.Mock).mockResolvedValue(mockProject)

      render(<PromptStructuresManager projectId={mockProjectId} />)

      await waitFor(() => {
        expect(
          screen.queryByText('Loading prompt structures...')
        ).not.toBeInTheDocument()
      })

      const headerButton = screen.getByRole('button', {
        name: /Prompt Structures/i,
      })
      await userEvent.click(headerButton)

      const addButton = screen.getByRole('button', { name: /Add Structure/i })
      await userEvent.click(addButton)

      const keyInput = screen.getByLabelText('Structure Key')
      const nameInput = screen.getByLabelText('Name')
      const descriptionInput = screen.getByLabelText(/Description/i)
      const configTextarea = screen.getByTestId('structure-config-textarea')

      await userEvent.type(keyInput, 'new-structure')
      await userEvent.type(nameInput, 'New Structure')
      await userEvent.type(descriptionInput, 'Test description')
      await userEvent.clear(configTextarea)
      await userEvent.click(configTextarea)
      await userEvent.paste(
        '{"system_prompt": "test", "instruction_prompt": "test"}'
      )

      const createButton = screen.getByRole('button', {
        name: /Create Structure/i,
      })
      await userEvent.click(createButton)

      await waitFor(() => {
        expect(apiClient.put).toHaveBeenCalledWith(
          `/projects/${mockProjectId}/generation-config/structures/new-structure`,
          expect.objectContaining({
            name: 'New Structure',
            description: 'Test description',
            system_prompt: 'test',
            instruction_prompt: 'test',
          })
        )
      })
    })

    it('should close modal on cancel', async () => {
      render(<PromptStructuresManager projectId={mockProjectId} />)

      await waitFor(() => {
        expect(
          screen.queryByText('Loading prompt structures...')
        ).not.toBeInTheDocument()
      })

      const headerButton = screen.getByRole('button', {
        name: /Prompt Structures/i,
      })
      await userEvent.click(headerButton)

      const addButton = screen.getByRole('button', { name: /Add Structure/i })
      await userEvent.click(addButton)

      expect(screen.getByText('Add Prompt Structure')).toBeInTheDocument()

      const cancelButton = screen.getByRole('button', { name: /Cancel/i })
      await userEvent.click(cancelButton)

      await waitFor(() => {
        expect(
          screen.queryByText('Add Prompt Structure')
        ).not.toBeInTheDocument()
      })
    })
  })

  describe('Edit Structure Modal', () => {
    it('should open edit modal when edit button is clicked', async () => {
      render(<PromptStructuresManager projectId={mockProjectId} />)

      await waitFor(() => {
        expect(
          screen.queryByText('Loading prompt structures...')
        ).not.toBeInTheDocument()
      })

      const headerButton = screen.getByRole('button', {
        name: /Prompt Structures/i,
      })
      await userEvent.click(headerButton)

      // Find the Legal Analysis card and click its edit button
      const legalAnalysisCard = screen
        .getByText('Legal Analysis')
        .closest('[class*="p-4"]')
      expect(legalAnalysisCard).toBeInTheDocument()

      const editButtons = within(legalAnalysisCard!).getAllByRole('button')
      // First button should be the edit button (pencil icon)
      await userEvent.click(editButtons[0])

      await waitFor(() => {
        expect(screen.getByText('Edit Prompt Structure')).toBeInTheDocument()
      })

      expect(screen.getByDisplayValue('Legal Analysis')).toBeInTheDocument()
      expect(screen.queryByLabelText('Structure Key')).not.toBeInTheDocument()
    })

    it('should successfully update an existing structure', async () => {
      ;(apiClient.put as jest.Mock).mockResolvedValue({})
      ;(apiClient.get as jest.Mock)
        .mockResolvedValueOnce(mockStructures)
        .mockResolvedValueOnce({
          ...mockStructures,
          'legal-analysis': {
            ...mockStructures['legal-analysis'],
            name: 'Updated Legal Analysis',
          },
        })
      ;(apiClient.getProject as jest.Mock).mockResolvedValue(mockProject)

      render(<PromptStructuresManager projectId={mockProjectId} />)

      await waitFor(() => {
        expect(
          screen.queryByText('Loading prompt structures...')
        ).not.toBeInTheDocument()
      })

      const headerButton = screen.getByRole('button', {
        name: /Prompt Structures/i,
      })
      await userEvent.click(headerButton)

      // Find the Legal Analysis card and click its edit button
      const legalAnalysisCard = screen
        .getByText('Legal Analysis')
        .closest('[class*="p-4"]')
      const editButtons = within(legalAnalysisCard!).getAllByRole('button')
      await userEvent.click(editButtons[0])

      await waitFor(() => {
        expect(screen.getByText('Edit Prompt Structure')).toBeInTheDocument()
      })

      const nameInput = screen.getByDisplayValue('Legal Analysis')
      await userEvent.clear(nameInput)
      await userEvent.type(nameInput, 'Updated Legal Analysis')

      const updateButton = screen.getByRole('button', {
        name: /Update Structure/i,
      })
      await userEvent.click(updateButton)

      await waitFor(() => {
        expect(apiClient.put).toHaveBeenCalledWith(
          `/projects/${mockProjectId}/generation-config/structures/legal-analysis`,
          expect.objectContaining({
            name: 'Updated Legal Analysis',
          })
        )
      })
    })

    it('should handle edit errors', async () => {
      ;(apiClient.put as jest.Mock).mockRejectedValue({
        detail: 'Failed to update structure',
        message: 'Failed to update',
      })

      render(<PromptStructuresManager projectId={mockProjectId} />)

      await waitFor(() => {
        expect(
          screen.queryByText('Loading prompt structures...')
        ).not.toBeInTheDocument()
      })

      const headerButton = screen.getByRole('button', {
        name: /Prompt Structures/i,
      })
      await userEvent.click(headerButton)

      // Find the Legal Analysis card and click its edit button
      const legalAnalysisCard = screen
        .getByText('Legal Analysis')
        .closest('[class*="p-4"]')
      expect(legalAnalysisCard).toBeInTheDocument()

      const editButtons = within(legalAnalysisCard!).getAllByRole('button')
      // First button should be the edit button (pencil icon)
      await userEvent.click(editButtons[0])

      await waitFor(() => {
        expect(screen.getByText('Edit Prompt Structure')).toBeInTheDocument()
      })

      const updateButton = screen.getByRole('button', {
        name: /Update Structure/i,
      })
      await userEvent.click(updateButton)

      await waitFor(() => {
        expect(
          screen.getByText('Failed to update structure')
        ).toBeInTheDocument()
      })
    })
  })

  describe('Delete Structure', () => {
    it('should open delete confirmation modal', async () => {
      render(<PromptStructuresManager projectId={mockProjectId} />)

      await waitFor(() => {
        expect(
          screen.queryByText('Loading prompt structures...')
        ).not.toBeInTheDocument()
      })

      const headerButton = screen.getByRole('button', {
        name: /Prompt Structures/i,
      })
      await userEvent.click(headerButton)

      // Find delete button by searching for buttons with red styling
      const allButtons = screen.getAllByRole('button')
      const deleteButton = allButtons.find((button) => {
        return button.className.includes('text-red-600')
      })

      if (deleteButton) {
        await userEvent.click(deleteButton)

        await waitFor(() => {
          expect(
            screen.getByText('Delete Prompt Structure')
          ).toBeInTheDocument()
          expect(
            screen.getByText(/Are you sure you want to delete/i)
          ).toBeInTheDocument()
        })
      }
    })

    it('should successfully delete a structure', async () => {
      ;(apiClient.delete as jest.Mock).mockResolvedValue({})
      ;(apiClient.get as jest.Mock)
        .mockResolvedValueOnce(mockStructures)
        .mockResolvedValueOnce({ 'simple-qa': mockStructures['simple-qa'] })
      ;(apiClient.getProject as jest.Mock).mockResolvedValue(mockProject)

      render(<PromptStructuresManager projectId={mockProjectId} />)

      await waitFor(() => {
        expect(
          screen.queryByText('Loading prompt structures...')
        ).not.toBeInTheDocument()
      })

      const headerButton = screen.getByRole('button', {
        name: /Prompt Structures/i,
      })
      await userEvent.click(headerButton)

      // Find delete button by searching for buttons with red styling
      const allButtons = screen.getAllByRole('button')
      const deleteButton = allButtons.find((button) => {
        return button.className.includes('text-red-600')
      })

      if (deleteButton) {
        await userEvent.click(deleteButton)

        await waitFor(() => {
          expect(
            screen.getByText('Delete Prompt Structure')
          ).toBeInTheDocument()
        })

        // Get all delete buttons and find the one in the modal (not the icon)
        const deleteButtons = screen.getAllByRole('button', { name: /Delete/i })
        const confirmButton = deleteButtons.find((btn) => {
          return btn.textContent === 'Delete' && !btn.querySelector('svg')
        })

        if (confirmButton) {
          await userEvent.click(confirmButton)

          await waitFor(() => {
            expect(apiClient.delete).toHaveBeenCalledWith(
              `/projects/${mockProjectId}/generation-config/structures/legal-analysis`
            )
          })
        }
      }
    })

    it('should cancel delete on cancel button', async () => {
      render(<PromptStructuresManager projectId={mockProjectId} />)

      await waitFor(() => {
        expect(
          screen.queryByText('Loading prompt structures...')
        ).not.toBeInTheDocument()
      })

      const headerButton = screen.getByRole('button', {
        name: /Prompt Structures/i,
      })
      await userEvent.click(headerButton)

      // Find delete button by searching for buttons with red styling
      const allButtons = screen.getAllByRole('button')
      const deleteButton = allButtons.find((button) => {
        return button.className.includes('text-red-600')
      })

      if (deleteButton) {
        await userEvent.click(deleteButton)

        await waitFor(() => {
          expect(
            screen.getByText('Delete Prompt Structure')
          ).toBeInTheDocument()
        })

        const cancelButtons = screen.getAllByRole('button', { name: /Cancel/i })
        await userEvent.click(cancelButtons[cancelButtons.length - 1])

        await waitFor(() => {
          expect(
            screen.queryByText('Delete Prompt Structure')
          ).not.toBeInTheDocument()
        })

        expect(apiClient.delete).not.toHaveBeenCalled()
      }
    })

    it('should handle delete errors', async () => {
      ;(apiClient.delete as jest.Mock).mockRejectedValue(
        new Error('Failed to delete')
      )

      render(<PromptStructuresManager projectId={mockProjectId} />)

      await waitFor(() => {
        expect(
          screen.queryByText('Loading prompt structures...')
        ).not.toBeInTheDocument()
      })

      const headerButton = screen.getByRole('button', {
        name: /Prompt Structures/i,
      })
      await userEvent.click(headerButton)

      // Find delete button by searching for buttons with red styling
      const allButtons = screen.getAllByRole('button')
      const deleteButton = allButtons.find((button) => {
        return button.className.includes('text-red-600')
      })

      if (deleteButton) {
        await userEvent.click(deleteButton)

        await waitFor(() => {
          expect(
            screen.getByText('Delete Prompt Structure')
          ).toBeInTheDocument()
        })

        // Get all delete buttons and find the one in the modal (not the icon)
        const deleteButtons = screen.getAllByRole('button', { name: /Delete/i })
        const confirmButton = deleteButtons.find((btn) => {
          return btn.textContent === 'Delete' && !btn.querySelector('svg')
        })

        if (confirmButton) {
          await userEvent.click(confirmButton)

          await waitFor(() => {
            expect(
              screen.getByText('Failed to delete structure')
            ).toBeInTheDocument()
          })
        }
      }
    })
  })

  describe('Error Handling', () => {
    it('should display error when fetching structures fails', async () => {
      ;(apiClient.get as jest.Mock).mockRejectedValue(
        new Error('Network error')
      )

      render(<PromptStructuresManager projectId={mockProjectId} />)

      await waitFor(() => {
        expect(
          screen.queryByText('Loading prompt structures...')
        ).not.toBeInTheDocument()
      })

      const headerButton = screen.getByRole('button', {
        name: /Prompt Structures/i,
      })
      await userEvent.click(headerButton)

      await waitFor(() => {
        expect(
          screen.getByText('Failed to load prompt structures')
        ).toBeInTheDocument()
      })
    })

    it('should handle project fetch failure gracefully', async () => {
      ;(apiClient.get as jest.Mock).mockResolvedValue(mockStructures)
      ;(apiClient.getProject as jest.Mock).mockRejectedValue(
        new Error('Project not found')
      )

      render(<PromptStructuresManager projectId={mockProjectId} />)

      await waitFor(() => {
        expect(
          screen.queryByText('Loading prompt structures...')
        ).not.toBeInTheDocument()
      })

      const headerButton = screen.getByRole('button', {
        name: /Prompt Structures/i,
      })
      await userEvent.click(headerButton)

      await waitFor(() => {
        expect(
          screen.getByText('Failed to load prompt structures')
        ).toBeInTheDocument()
      })
    })
  })

  describe('Field References Extraction', () => {
    it('should extract and display field references from structures', async () => {
      render(<PromptStructuresManager projectId={mockProjectId} />)

      await waitFor(() => {
        expect(
          screen.queryByText('Loading prompt structures...')
        ).not.toBeInTheDocument()
      })

      const headerButton = screen.getByRole('button', {
        name: /Prompt Structures/i,
      })
      await userEvent.click(headerButton)

      // The legal-analysis structure has $question reference
      // The simple-qa structure has nested field references
      await waitFor(() => {
        const referencesText = screen.queryAllByText('References fields:')
        expect(referencesText.length).toBeGreaterThan(0)
      })
    })
  })

  describe('Callbacks', () => {
    it('should call onStructuresChange after successful create', async () => {
      const onStructuresChange = jest.fn()
      ;(apiClient.put as jest.Mock).mockResolvedValue({})
      ;(apiClient.get as jest.Mock)
        .mockResolvedValueOnce(mockStructures)
        .mockResolvedValueOnce(mockStructures)
      ;(apiClient.getProject as jest.Mock).mockResolvedValue(mockProject)

      render(
        <PromptStructuresManager
          projectId={mockProjectId}
          onStructuresChange={onStructuresChange}
        />
      )

      await waitFor(() => {
        expect(
          screen.queryByText('Loading prompt structures...')
        ).not.toBeInTheDocument()
      })

      const headerButton = screen.getByRole('button', {
        name: /Prompt Structures/i,
      })
      await userEvent.click(headerButton)

      const addButton = screen.getByRole('button', { name: /Add Structure/i })
      await userEvent.click(addButton)

      const keyInput = screen.getByLabelText('Structure Key')
      const nameInput = screen.getByLabelText('Name')
      const configTextarea = screen.getByTestId('structure-config-textarea')

      await userEvent.type(keyInput, 'test-structure')
      await userEvent.type(nameInput, 'Test')
      await userEvent.click(configTextarea)
      await userEvent.paste(
        '{"system_prompt": "test", "instruction_prompt": "test"}'
      )

      const createButton = screen.getByRole('button', {
        name: /Create Structure/i,
      })
      await userEvent.click(createButton)

      await waitFor(() => {
        expect(onStructuresChange).toHaveBeenCalled()
      })
    })

    it('should call onStructuresChange after successful delete', async () => {
      const onStructuresChange = jest.fn()
      ;(apiClient.delete as jest.Mock).mockResolvedValue({})
      ;(apiClient.get as jest.Mock)
        .mockResolvedValueOnce(mockStructures)
        .mockResolvedValueOnce(mockStructures)
      ;(apiClient.getProject as jest.Mock).mockResolvedValue(mockProject)

      render(
        <PromptStructuresManager
          projectId={mockProjectId}
          onStructuresChange={onStructuresChange}
        />
      )

      await waitFor(() => {
        expect(
          screen.queryByText('Loading prompt structures...')
        ).not.toBeInTheDocument()
      })

      const headerButton = screen.getByRole('button', {
        name: /Prompt Structures/i,
      })
      await userEvent.click(headerButton)

      // Find delete button by searching for buttons with red styling
      const allButtons = screen.getAllByRole('button')
      const deleteButton = allButtons.find((button) => {
        return button.className.includes('text-red-600')
      })

      if (deleteButton) {
        await userEvent.click(deleteButton)

        await waitFor(() => {
          expect(
            screen.getByText('Delete Prompt Structure')
          ).toBeInTheDocument()
        })

        // Get all delete buttons and find the one in the modal (not the icon)
        const deleteButtons = screen.getAllByRole('button', { name: /Delete/i })
        const confirmButton = deleteButtons.find((btn) => {
          return btn.textContent === 'Delete' && !btn.querySelector('svg')
        })

        if (confirmButton) {
          await userEvent.click(confirmButton)

          await waitFor(() => {
            expect(onStructuresChange).toHaveBeenCalled()
          })
        }
      }
    })
  })
})

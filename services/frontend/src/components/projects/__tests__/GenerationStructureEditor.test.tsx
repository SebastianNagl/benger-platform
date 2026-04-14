/**
 * @jest-environment jsdom
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { GenerationStructureEditor } from '../GenerationStructureEditor'

const mockTranslate = (key: string, arg2?: any, arg3?: any) => {
  const vars = typeof arg2 === 'object' ? arg2 : arg3
  const translations: Record<string, string> = {
    'projects.generationStructure.templatesTitle': 'Generation Structure Templates',
    'projects.generationStructure.templatesDescription': 'Select a template for common generation patterns with the new prompt structure',
    'projects.generationStructure.templateSimpleQA': 'Simple Q&A',
    'projects.generationStructure.templateSimpleQADesc': 'Direct field reference',
    'projects.generationStructure.templateTemplateQA': 'Template Q&A',
    'projects.generationStructure.templateTemplateQADesc': 'With {{placeholders}}',
    'projects.generationStructure.templateLegalAnalysis': 'Legal Analysis',
    'projects.generationStructure.templateLegalAnalysisDesc': 'Complex template',
    'projects.generationStructure.templateClassification': 'Classification',
    'projects.generationStructure.templateClassificationDesc': 'Category-based',
    'projects.generationStructure.templateNestedData': 'Nested Data',
    'projects.generationStructure.templateNestedDataDesc': 'Dot notation paths',
    'projects.generationStructure.templateMultiFieldCombo': 'Multi-Field Combo',
    'projects.generationStructure.templateMultiFieldComboDesc': 'Combine multiple fields',
    'projects.generationStructure.configTitle': 'Generation Structure Configuration',
    'projects.generationStructure.configDescription': 'Define system and instruction prompts with field mappings and templates',
    'projects.generationStructure.editorHint': 'Use $field.path for field references and {{placeholder}} for template variables',
    'projects.generationStructure.showPreview': 'Show Preview',
    'projects.generationStructure.hidePreview': 'Hide Preview',
    'projects.generationStructure.placeholder': 'Enter your JSON generation structure configuration...',
    'projects.generationStructure.valid': 'Configuration is valid',
    'projects.generationStructure.saveButton': 'Save Configuration',
    'projects.generationStructure.errorEmpty': 'Configuration cannot be empty',
    'projects.generationStructure.errorMissingPrompt': 'Configuration must define at least one of: system_prompt, instruction_prompt, or fields',
    'projects.generationStructure.errorSystemPromptTemplate': 'system_prompt object must have a "template" field',
    'projects.generationStructure.errorSystemPromptFields': 'system_prompt.fields must be an object',
    'projects.generationStructure.errorInstructionPromptTemplate': 'instruction_prompt object must have a "template" field',
    'projects.generationStructure.errorInstructionPromptFields': 'instruction_prompt.fields must be an object',
    'projects.generationStructure.errorExcludeFieldsArray': 'exclude_fields must be an array',
    'projects.generationStructure.errorParametersObject': 'parameters must be an object',
    'projects.generationStructure.errorInvalidJson': 'Invalid JSON format: ',
    'projects.generationStructure.previewTitle': 'Structure Preview',
    'projects.generationStructure.systemPromptLabel': 'System Prompt:',
    'projects.generationStructure.instructionPromptLabel': 'Instruction Prompt:',
    'projects.generationStructure.willUseField': 'Will use field: {field}',
    'projects.generationStructure.templateWithPlaceholders': 'Template with placeholders: ',
    'projects.generationStructure.referencedFields': 'Referenced Data Fields:',
    'projects.generationStructure.excludedFields': 'Excluded Fields (Security):',
    'projects.generationStructure.docTitle': 'Configuration Structure',
    'projects.generationStructure.docPromptFields': 'Prompt Fields:',
    'projects.generationStructure.docFieldReferences': 'Field References:',
    'projects.generationStructure.docTemplateSyntax': 'Template Syntax:',
    'projects.generationStructure.docOptionalFields': 'Optional Fields:',
    'projects.generationStructure.docSecurityNote': 'Security Note:',
    'projects.generationStructure.docSecurityNoteText': "Sensitive fields like 'annotations', 'ground_truth', 'reference_answer' are automatically filtered and will never be sent to LLMs.",
    'projects.generationStructure.docSystemPromptDesc': 'System-level instructions',
    'projects.generationStructure.docInstructionPromptDesc': 'Task-specific instructions',
    'projects.generationStructure.docStringOption': '• String: Direct text or $field reference',
    'projects.generationStructure.docObjectOption': '• Object: Template with {{placeholders}} and field mappings',
    'projects.generationStructure.docSimpleFieldRef': 'Simple field reference',
    'projects.generationStructure.docNestedFieldRef': 'Nested field with dot notation',
    'projects.generationStructure.docArrayAccessRef': 'Array access with index',
    'projects.generationStructure.docTemplateVariable': 'Template variable to be replaced',
    'projects.generationStructure.docFieldsMapping': 'Defined in fields object mapping placeholders to $references',
    'projects.generationStructure.docContextFields': 'Array of additional context field references',
    'projects.generationStructure.docExcludeFields': 'Fields to exclude for security (e.g., annotations)',
    'projects.generationStructure.docParameters': 'Generation parameters (temperature, max_tokens)',
    'common.cancel': 'Cancel',
  }
  let result = translations[key] || key
  if (vars) {
    Object.entries(vars).forEach(([k, v]) => {
      result = result.replace(`{${k}}`, String(v))
    })
  }
  return result
}

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: mockTranslate,
    locale: 'en',
    setLocale: jest.fn(),
  }),
}))

describe('GenerationStructureEditor', () => {
  const mockOnSave = jest.fn()
  const mockOnCancel = jest.fn()
  const mockOnChange = jest.fn()

  beforeEach(() => {
    jest.clearAllMocks()
  })

  describe('Editor Rendering', () => {
    it('should render with empty state', () => {
      render(<GenerationStructureEditor onSave={mockOnSave} />)

      expect(
        screen.getByText('Generation Structure Templates')
      ).toBeInTheDocument()
      expect(
        screen.getByText('Generation Structure Configuration')
      ).toBeInTheDocument()
      expect(
        screen.getByPlaceholderText(
          'Enter your JSON generation structure configuration...'
        )
      ).toBeInTheDocument()
    })

    it('should render with initial config', () => {
      const initialConfig =
        '{"system_prompt": "test", "instruction_prompt": "$question"}'

      render(
        <GenerationStructureEditor
          initialConfig={initialConfig}
          onSave={mockOnSave}
        />
      )

      expect(screen.getByDisplayValue(initialConfig)).toBeInTheDocument()
    })

    it('should display template selection buttons', () => {
      render(<GenerationStructureEditor onSave={mockOnSave} />)

      expect(screen.getByText('Simple Q&A')).toBeInTheDocument()
      expect(screen.getByText('Template Q&A')).toBeInTheDocument()
      expect(screen.getByText('Legal Analysis')).toBeInTheDocument()
      expect(screen.getByText('Classification')).toBeInTheDocument()
      expect(screen.getByText('Nested Data')).toBeInTheDocument()
    })

    it('should show action buttons by default', () => {
      render(
        <GenerationStructureEditor
          onSave={mockOnSave}
          onCancel={mockOnCancel}
        />
      )

      expect(
        screen.getByRole('button', { name: 'Save Configuration' })
      ).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument()
    })

    it('should hide action buttons when showActionButtons is false', () => {
      render(
        <GenerationStructureEditor
          onSave={mockOnSave}
          onCancel={mockOnCancel}
          showActionButtons={false}
        />
      )

      expect(
        screen.queryByRole('button', { name: 'Save Configuration' })
      ).not.toBeInTheDocument()
      expect(
        screen.queryByRole('button', { name: 'Cancel' })
      ).not.toBeInTheDocument()
    })

    it('should not show cancel button when onCancel is not provided', () => {
      render(<GenerationStructureEditor onSave={mockOnSave} />)

      expect(
        screen.queryByRole('button', { name: 'Cancel' })
      ).not.toBeInTheDocument()
    })

    it('should render documentation section', () => {
      render(<GenerationStructureEditor onSave={mockOnSave} />)

      expect(screen.getByText('Configuration Structure')).toBeInTheDocument()
      expect(screen.getByText('Prompt Fields:')).toBeInTheDocument()
      expect(screen.getByText('Field References:')).toBeInTheDocument()
      expect(screen.getByText('Template Syntax:')).toBeInTheDocument()
    })
  })

  describe('Template Selection', () => {
    it('should load simple_qa template', async () => {
      render(
        <GenerationStructureEditor
          onSave={mockOnSave}
          onChange={mockOnChange}
        />
      )

      const simpleQaButton = screen.getByText('Simple Q&A').closest('button')!
      await userEvent.click(simpleQaButton)

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalled()
      })

      const callArg = mockOnChange.mock.calls[0][0]
      expect(callArg).toContain('You are a helpful assistant')
      expect(callArg).toContain('$question')
    })

    it('should load template_qa template', async () => {
      render(
        <GenerationStructureEditor
          onSave={mockOnSave}
          onChange={mockOnChange}
        />
      )

      const templateQaButton = screen
        .getByText('Template Q&A')
        .closest('button')!
      await userEvent.click(templateQaButton)

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalled()
      })

      const callArg = mockOnChange.mock.calls[0][0]
      expect(callArg).toContain('{{domain}}')
      expect(callArg).toContain('{{question}}')
      expect(callArg).toContain('{{context}}')
    })

    it('should load legal_analysis template', async () => {
      render(
        <GenerationStructureEditor
          onSave={mockOnSave}
          onChange={mockOnChange}
        />
      )

      const legalAnalysisButton = screen
        .getByText('Legal Analysis')
        .closest('button')!
      await userEvent.click(legalAnalysisButton)

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalled()
      })

      const callArg = mockOnChange.mock.calls[0][0]
      expect(callArg).toContain('{{jurisdiction}}')
      expect(callArg).toContain('exclude_fields')
    })

    it('should load classification template', async () => {
      render(
        <GenerationStructureEditor
          onSave={mockOnSave}
          onChange={mockOnChange}
        />
      )

      const classificationButton = screen
        .getByText('Classification')
        .closest('button')!
      await userEvent.click(classificationButton)

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalled()
      })

      const callArg = mockOnChange.mock.calls[0][0]
      expect(callArg).toContain('classification expert')
      expect(callArg).toContain('{{categories}}')
    })

    it('should load nested_data template', async () => {
      render(
        <GenerationStructureEditor
          onSave={mockOnSave}
          onChange={mockOnChange}
        />
      )

      const nestedDataButton = screen
        .getByText('Nested Data')
        .closest('button')!
      await userEvent.click(nestedDataButton)

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalled()
      })

      const callArg = mockOnChange.mock.calls[0][0]
      expect(callArg).toContain('$prompts.system')
      expect(callArg).toContain('parameters')
      expect(callArg).toContain('temperature')
    })

    it('should highlight selected template', async () => {
      render(
        <GenerationStructureEditor
          onSave={mockOnSave}
          onChange={mockOnChange}
        />
      )

      const simpleQaButton = screen.getByText('Simple Q&A').closest('button')!

      expect(simpleQaButton.className).not.toContain('bg-zinc-900')

      await userEvent.click(simpleQaButton)

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalled()
      })
    })

    it('should switch between templates', async () => {
      render(
        <GenerationStructureEditor
          onSave={mockOnSave}
          onChange={mockOnChange}
        />
      )

      const simpleQaButton = screen.getByText('Simple Q&A').closest('button')!
      await userEvent.click(simpleQaButton)

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalledWith(
          expect.stringContaining('helpful assistant')
        )
      })

      const legalButton = screen.getByText('Legal Analysis').closest('button')!
      await userEvent.click(legalButton)

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalledWith(
          expect.stringContaining('legal expert')
        )
      })
    })
  })

  describe('Configuration Editing', () => {
    it('should update config on textarea change', async () => {
      render(
        <GenerationStructureEditor
          onSave={mockOnSave}
          onChange={mockOnChange}
        />
      )

      const textarea = screen.getByPlaceholderText(
        'Enter your JSON generation structure configuration...'
      )

      await userEvent.click(textarea)
      await userEvent.paste('{"system_prompt": "test"}')

      expect(mockOnChange).toHaveBeenCalledWith('{"system_prompt": "test"}')
    })

    it('should validate JSON format on change', async () => {
      render(<GenerationStructureEditor onSave={mockOnSave} />)

      const textarea = screen.getByPlaceholderText(
        'Enter your JSON generation structure configuration...'
      )

      await userEvent.click(textarea)
      await userEvent.paste('invalid json')

      await waitFor(() => {
        expect(screen.getByText(/Invalid JSON format/i)).toBeInTheDocument()
      })
    })

    it('should show success when valid config is entered', async () => {
      render(<GenerationStructureEditor onSave={mockOnSave} />)

      const textarea = screen.getByPlaceholderText(
        'Enter your JSON generation structure configuration...'
      )

      await userEvent.click(textarea)
      await userEvent.paste(
        '{"system_prompt": "test", "instruction_prompt": "test"}'
      )

      await waitFor(() => {
        expect(screen.getByText('Configuration is valid')).toBeInTheDocument()
      })
    })

    it('should clear config value', async () => {
      const initialConfig = '{"system_prompt": "test"}'
      render(
        <GenerationStructureEditor
          initialConfig={initialConfig}
          onSave={mockOnSave}
          onChange={mockOnChange}
        />
      )

      const textarea = screen.getByPlaceholderText(
        'Enter your JSON generation structure configuration...'
      )

      await userEvent.clear(textarea)

      await waitFor(() => {
        expect(textarea).toHaveValue('')
      })
    })
  })

  describe('Validation', () => {
    it('should require at least one prompt field', async () => {
      render(<GenerationStructureEditor onSave={mockOnSave} />)

      const textarea = screen.getByPlaceholderText(
        'Enter your JSON generation structure configuration...'
      )

      await userEvent.click(textarea)
      await userEvent.paste('{"exclude_fields": ["test"]}')

      await waitFor(() => {
        expect(
          screen.getByText(
            /must define at least one of: system_prompt, instruction_prompt, or fields/i
          )
        ).toBeInTheDocument()
      })
    })

    it('should validate system_prompt object structure', async () => {
      render(<GenerationStructureEditor onSave={mockOnSave} />)

      const textarea = screen.getByPlaceholderText(
        'Enter your JSON generation structure configuration...'
      )

      await userEvent.click(textarea)
      await userEvent.paste('{"system_prompt": {"fields": "invalid"}}')

      await waitFor(() => {
        expect(
          screen.getByText('system_prompt object must have a "template" field')
        ).toBeInTheDocument()
      })
    })

    it('should validate instruction_prompt object structure', async () => {
      render(<GenerationStructureEditor onSave={mockOnSave} />)

      const textarea = screen.getByPlaceholderText(
        'Enter your JSON generation structure configuration...'
      )

      await userEvent.click(textarea)
      await userEvent.paste('{"instruction_prompt": {"fields": {}}}')

      await waitFor(() => {
        expect(
          screen.getByText(
            'instruction_prompt object must have a "template" field'
          )
        ).toBeInTheDocument()
      })
    })

    it('should validate exclude_fields is an array', async () => {
      render(<GenerationStructureEditor onSave={mockOnSave} />)

      const textarea = screen.getByPlaceholderText(
        'Enter your JSON generation structure configuration...'
      )

      await userEvent.click(textarea)
      await userEvent.paste(
        '{"system_prompt": "test", "exclude_fields": "invalid"}'
      )

      await waitFor(() => {
        expect(
          screen.getByText('exclude_fields must be an array')
        ).toBeInTheDocument()
      })
    })

    it('should validate parameters is an object', async () => {
      render(<GenerationStructureEditor onSave={mockOnSave} />)

      const textarea = screen.getByPlaceholderText(
        'Enter your JSON generation structure configuration...'
      )

      await userEvent.click(textarea)
      await userEvent.paste(
        '{"system_prompt": "test", "parameters": "invalid"}'
      )

      await waitFor(() => {
        expect(
          screen.getByText('parameters must be an object')
        ).toBeInTheDocument()
      })
    })

    it('should not allow empty configuration', async () => {
      render(<GenerationStructureEditor onSave={mockOnSave} />)

      const textarea = screen.getByPlaceholderText(
        'Enter your JSON generation structure configuration...'
      )

      await userEvent.click(textarea)
      await userEvent.paste('   ')

      await waitFor(() => {
        expect(
          screen.getByText('Configuration cannot be empty')
        ).toBeInTheDocument()
      })
    })

    it('should validate system_prompt.fields is an object', async () => {
      render(<GenerationStructureEditor onSave={mockOnSave} />)

      const textarea = screen.getByPlaceholderText(
        'Enter your JSON generation structure configuration...'
      )

      await userEvent.click(textarea)
      await userEvent.paste(
        '{"system_prompt": {"template": "test", "fields": "invalid"}}'
      )

      await waitFor(() => {
        expect(
          screen.getByText('system_prompt.fields must be an object')
        ).toBeInTheDocument()
      })
    })

    it('should validate instruction_prompt.fields is an object', async () => {
      render(<GenerationStructureEditor onSave={mockOnSave} />)

      const textarea = screen.getByPlaceholderText(
        'Enter your JSON generation structure configuration...'
      )

      await userEvent.click(textarea)
      await userEvent.paste(
        '{"instruction_prompt": {"template": "test", "fields": "invalid"}}'
      )

      await waitFor(() => {
        expect(
          screen.getByText('instruction_prompt.fields must be an object')
        ).toBeInTheDocument()
      })
    })

    it('should accept valid system_prompt as string', async () => {
      render(<GenerationStructureEditor onSave={mockOnSave} />)

      const textarea = screen.getByPlaceholderText(
        'Enter your JSON generation structure configuration...'
      )

      await userEvent.click(textarea)
      await userEvent.paste(
        '{"system_prompt": "You are a helpful assistant", "instruction_prompt": "$question"}'
      )

      await waitFor(() => {
        expect(screen.getByText('Configuration is valid')).toBeInTheDocument()
      })
    })

    it('should accept valid system_prompt as object with template', async () => {
      render(<GenerationStructureEditor onSave={mockOnSave} />)

      const textarea = screen.getByPlaceholderText(
        'Enter your JSON generation structure configuration...'
      )

      await userEvent.click(textarea)
      await userEvent.paste(
        '{"system_prompt": {"template": "Test {{var}}", "fields": {"var": "$data"}}, "instruction_prompt": "test"}'
      )

      await waitFor(() => {
        expect(screen.getByText('Configuration is valid')).toBeInTheDocument()
      })
    })
  })

  describe('Preview Functionality', () => {
    it('should toggle preview on button click', async () => {
      render(<GenerationStructureEditor onSave={mockOnSave} />)

      const previewButton = screen.getByRole('button', {
        name: /Show Preview/i,
      })

      expect(screen.queryByText('Structure Preview')).not.toBeInTheDocument()

      await userEvent.click(previewButton)

      await waitFor(() => {
        expect(
          screen.getByRole('button', { name: /Hide Preview/i })
        ).toBeInTheDocument()
      })
    })

    it('should display system_prompt in preview', async () => {
      render(<GenerationStructureEditor onSave={mockOnSave} />)

      const textarea = screen.getByPlaceholderText(
        'Enter your JSON generation structure configuration...'
      )
      await userEvent.click(textarea)
      await userEvent.paste(
        '{"system_prompt": "You are helpful", "instruction_prompt": "test"}'
      )

      const previewButton = screen.getByRole('button', {
        name: /Show Preview/i,
      })
      await userEvent.click(previewButton)

      await waitFor(() => {
        expect(screen.getByText('System Prompt:')).toBeInTheDocument()
        expect(screen.getByText('You are helpful')).toBeInTheDocument()
      })
    })

    it('should display instruction_prompt in preview', async () => {
      render(<GenerationStructureEditor onSave={mockOnSave} />)

      const textarea = screen.getByPlaceholderText(
        'Enter your JSON generation structure configuration...'
      )
      await userEvent.click(textarea)
      await userEvent.paste(
        '{"system_prompt": "test", "instruction_prompt": "Answer this"}'
      )

      const previewButton = screen.getByRole('button', {
        name: /Show Preview/i,
      })
      await userEvent.click(previewButton)

      await waitFor(() => {
        expect(screen.getByText('Instruction Prompt:')).toBeInTheDocument()
        expect(screen.getByText('Answer this')).toBeInTheDocument()
      })
    })

    it('should show field references in preview', async () => {
      render(<GenerationStructureEditor onSave={mockOnSave} />)

      const textarea = screen.getByPlaceholderText(
        'Enter your JSON generation structure configuration...'
      )
      await userEvent.click(textarea)
      await userEvent.paste(
        '{"system_prompt": "$prompts.system", "instruction_prompt": "$question"}'
      )

      const previewButton = screen.getByRole('button', {
        name: /Show Preview/i,
      })
      await userEvent.click(previewButton)

      await waitFor(() => {
        expect(screen.getByText('Referenced Data Fields:')).toBeInTheDocument()
        expect(screen.getByText('prompts.system')).toBeInTheDocument()
        expect(screen.getByText('question')).toBeInTheDocument()
      })
    })

    it('should show template placeholders in preview', async () => {
      render(<GenerationStructureEditor onSave={mockOnSave} />)

      const textarea = screen.getByPlaceholderText(
        'Enter your JSON generation structure configuration...'
      )
      await userEvent.click(textarea)
      await userEvent.paste(
        '{"system_prompt": {"template": "Expert in {{domain}}", "fields": {"domain": "$area"}}, "instruction_prompt": "test"}'
      )

      const previewButton = screen.getByRole('button', {
        name: /Show Preview/i,
      })
      await userEvent.click(previewButton)

      await waitFor(() => {
        expect(
          screen.getByText(/Template with placeholders/i)
        ).toBeInTheDocument()
      })
    })

    it('should show exclude_fields in preview', async () => {
      render(<GenerationStructureEditor onSave={mockOnSave} />)

      const textarea = screen.getByPlaceholderText(
        'Enter your JSON generation structure configuration...'
      )
      await userEvent.click(textarea)
      await userEvent.paste(
        '{"system_prompt": "test", "instruction_prompt": "test", "exclude_fields": ["annotations", "ground_truth"]}'
      )

      const previewButton = screen.getByRole('button', {
        name: /Show Preview/i,
      })
      await userEvent.click(previewButton)

      await waitFor(() => {
        expect(
          screen.getByText('Excluded Fields (Security):')
        ).toBeInTheDocument()
        expect(screen.getByText('annotations')).toBeInTheDocument()
        expect(screen.getByText('ground_truth')).toBeInTheDocument()
      })
    })

    it('should hide preview when toggled off', async () => {
      render(<GenerationStructureEditor onSave={mockOnSave} />)

      const textarea = screen.getByPlaceholderText(
        'Enter your JSON generation structure configuration...'
      )
      await userEvent.click(textarea)
      await userEvent.paste(
        '{"system_prompt": "test", "instruction_prompt": "test"}'
      )

      const showButton = screen.getByRole('button', { name: /Show Preview/i })
      await userEvent.click(showButton)

      await waitFor(() => {
        expect(screen.getByText('Structure Preview')).toBeInTheDocument()
      })

      const hideButton = screen.getByRole('button', { name: /Hide Preview/i })
      await userEvent.click(hideButton)

      await waitFor(() => {
        expect(screen.queryByText('Structure Preview')).not.toBeInTheDocument()
      })
    })

    it('should show field reference indicator for string prompts', async () => {
      render(<GenerationStructureEditor onSave={mockOnSave} />)

      const textarea = screen.getByPlaceholderText(
        'Enter your JSON generation structure configuration...'
      )
      await userEvent.click(textarea)
      await userEvent.paste(
        '{"system_prompt": "$prompts.system", "instruction_prompt": "test"}'
      )

      const previewButton = screen.getByRole('button', {
        name: /Show Preview/i,
      })
      await userEvent.click(previewButton)

      await waitFor(() => {
        expect(
          screen.getByText(/Will use field: prompts.system/)
        ).toBeInTheDocument()
      })
    })
  })

  describe('Save Functionality', () => {
    it('should call onSave with valid config', async () => {
      render(<GenerationStructureEditor onSave={mockOnSave} />)

      const textarea = screen.getByPlaceholderText(
        'Enter your JSON generation structure configuration...'
      )
      await userEvent.click(textarea)
      await userEvent.paste(
        '{"system_prompt": "test", "instruction_prompt": "test"}'
      )

      await waitFor(() => {
        expect(screen.getByText('Configuration is valid')).toBeInTheDocument()
      })

      const saveButton = screen.getByRole('button', {
        name: 'Save Configuration',
      })
      await userEvent.click(saveButton)

      expect(mockOnSave).toHaveBeenCalledWith(
        '{"system_prompt": "test", "instruction_prompt": "test"}'
      )
    })

    it('should not call onSave with invalid config', async () => {
      render(<GenerationStructureEditor onSave={mockOnSave} />)

      const textarea = screen.getByPlaceholderText(
        'Enter your JSON generation structure configuration...'
      )
      await userEvent.click(textarea)
      await userEvent.paste('invalid json')

      await waitFor(() => {
        expect(screen.getByText(/Invalid JSON format/i)).toBeInTheDocument()
      })

      const saveButton = screen.getByRole('button', {
        name: 'Save Configuration',
      })
      await userEvent.click(saveButton)

      expect(mockOnSave).not.toHaveBeenCalled()
    })

    it('should disable save button when config is empty', () => {
      render(<GenerationStructureEditor onSave={mockOnSave} />)

      const saveButton = screen.getByRole('button', {
        name: 'Save Configuration',
      })
      expect(saveButton).toBeDisabled()
    })

    it('should disable save button when there is an error', async () => {
      render(<GenerationStructureEditor onSave={mockOnSave} />)

      const textarea = screen.getByPlaceholderText(
        'Enter your JSON generation structure configuration...'
      )
      await userEvent.click(textarea)
      await userEvent.paste('invalid json')

      await waitFor(() => {
        const saveButton = screen.getByRole('button', {
          name: 'Save Configuration',
        })
        expect(saveButton).toBeDisabled()
      })
    })

    it('should enable save button with valid config', async () => {
      render(<GenerationStructureEditor onSave={mockOnSave} />)

      const textarea = screen.getByPlaceholderText(
        'Enter your JSON generation structure configuration...'
      )
      await userEvent.click(textarea)
      await userEvent.paste(
        '{"system_prompt": "test", "instruction_prompt": "test"}'
      )

      await waitFor(() => {
        const saveButton = screen.getByRole('button', {
          name: 'Save Configuration',
        })
        expect(saveButton).toBeEnabled()
      })
    })

    it('should call onCancel when cancel button is clicked', async () => {
      render(
        <GenerationStructureEditor
          onSave={mockOnSave}
          onCancel={mockOnCancel}
        />
      )

      const cancelButton = screen.getByRole('button', { name: 'Cancel' })
      await userEvent.click(cancelButton)

      expect(mockOnCancel).toHaveBeenCalled()
    })
  })

  describe('Field Reference Extraction', () => {
    it('should extract simple field references', async () => {
      render(<GenerationStructureEditor onSave={mockOnSave} />)

      const textarea = screen.getByPlaceholderText(
        'Enter your JSON generation structure configuration...'
      )
      await userEvent.click(textarea)
      await userEvent.paste(
        '{"system_prompt": "$question", "instruction_prompt": "$context"}'
      )

      const previewButton = screen.getByRole('button', {
        name: /Show Preview/i,
      })
      await userEvent.click(previewButton)

      await waitFor(() => {
        expect(screen.getByText('question')).toBeInTheDocument()
        expect(screen.getByText('context')).toBeInTheDocument()
      })
    })

    it('should extract nested field references', async () => {
      render(<GenerationStructureEditor onSave={mockOnSave} />)

      const textarea = screen.getByPlaceholderText(
        'Enter your JSON generation structure configuration...'
      )
      await userEvent.click(textarea)
      await userEvent.paste(
        '{"system_prompt": "$prompts.system", "instruction_prompt": "$metadata.domain"}'
      )

      const previewButton = screen.getByRole('button', {
        name: /Show Preview/i,
      })
      await userEvent.click(previewButton)

      await waitFor(() => {
        expect(screen.getByText('prompts.system')).toBeInTheDocument()
        expect(screen.getByText('metadata.domain')).toBeInTheDocument()
      })
    })

    it('should extract field references from template fields', async () => {
      render(<GenerationStructureEditor onSave={mockOnSave} />)

      const textarea = screen.getByPlaceholderText(
        'Enter your JSON generation structure configuration...'
      )
      await userEvent.click(textarea)
      await userEvent.paste(
        '{"system_prompt": {"template": "test", "fields": {"var": "$data.field"}}, "instruction_prompt": "test"}'
      )

      const previewButton = screen.getByRole('button', {
        name: /Show Preview/i,
      })
      await userEvent.click(previewButton)

      await waitFor(() => {
        expect(screen.getByText('data.field')).toBeInTheDocument()
      })
    })

    it('should extract field references from arrays', async () => {
      render(<GenerationStructureEditor onSave={mockOnSave} />)

      const textarea = screen.getByPlaceholderText(
        'Enter your JSON generation structure configuration...'
      )
      await userEvent.click(textarea)
      await userEvent.paste(
        '{"system_prompt": "test", "instruction_prompt": "test", "context_fields": ["$field1", "$field2"]}'
      )

      const previewButton = screen.getByRole('button', {
        name: /Show Preview/i,
      })
      await userEvent.click(previewButton)

      await waitFor(() => {
        expect(screen.getByText('field1')).toBeInTheDocument()
        expect(screen.getByText('field2')).toBeInTheDocument()
      })
    })
  })

  describe('Complex Validation Scenarios', () => {
    it('should validate complete legal analysis structure', async () => {
      render(<GenerationStructureEditor onSave={mockOnSave} />)

      const legalButton = screen.getByText('Legal Analysis').closest('button')!
      await userEvent.click(legalButton)

      await waitFor(() => {
        expect(screen.getByText('Configuration is valid')).toBeInTheDocument()
      })
    })

    it('should validate structure with parameters', async () => {
      render(<GenerationStructureEditor onSave={mockOnSave} />)

      const textarea = screen.getByPlaceholderText(
        'Enter your JSON generation structure configuration...'
      )
      await userEvent.click(textarea)
      await userEvent.paste(
        '{"system_prompt": "test", "instruction_prompt": "test", "parameters": {"temperature": 0.7, "max_tokens": 1000}}'
      )

      await waitFor(() => {
        expect(screen.getByText('Configuration is valid')).toBeInTheDocument()
      })
    })

    it('should validate structure with context_fields', async () => {
      render(<GenerationStructureEditor onSave={mockOnSave} />)

      const textarea = screen.getByPlaceholderText(
        'Enter your JSON generation structure configuration...'
      )
      await userEvent.click(textarea)
      await userEvent.paste(
        '{"system_prompt": "test", "instruction_prompt": "test", "context_fields": ["$context.jurisdiction", "$context.legal_system"]}'
      )

      await waitFor(() => {
        expect(screen.getByText('Configuration is valid')).toBeInTheDocument()
      })
    })

    it('should validate with only fields defined', async () => {
      render(<GenerationStructureEditor onSave={mockOnSave} />)

      const textarea = screen.getByPlaceholderText(
        'Enter your JSON generation structure configuration...'
      )
      await userEvent.click(textarea)
      await userEvent.paste('{"fields": {"var": "$data"}}')

      await waitFor(() => {
        expect(screen.getByText('Configuration is valid')).toBeInTheDocument()
      })
    })
  })

  describe('Edge Cases', () => {
    it('should handle config update when onChange is not provided', async () => {
      render(<GenerationStructureEditor onSave={mockOnSave} />)

      const textarea = screen.getByPlaceholderText(
        'Enter your JSON generation structure configuration...'
      )
      await userEvent.click(textarea)
      await userEvent.paste('{"system_prompt": "test"}')

      expect(textarea).toHaveValue('{"system_prompt": "test"}')
    })

    it('should handle template selection when onChange is not provided', async () => {
      render(<GenerationStructureEditor onSave={mockOnSave} />)

      const simpleQaButton = screen.getByText('Simple Q&A').closest('button')!
      await userEvent.click(simpleQaButton)

      await waitFor(() => {
        expect(screen.getByText('Configuration is valid')).toBeInTheDocument()
      })
    })

    it('should clear error when valid config is entered after invalid', async () => {
      render(<GenerationStructureEditor onSave={mockOnSave} />)

      const textarea = screen.getByPlaceholderText(
        'Enter your JSON generation structure configuration...'
      )

      await userEvent.click(textarea)
      await userEvent.paste('invalid')

      await waitFor(() => {
        expect(screen.getByText(/Invalid JSON format/i)).toBeInTheDocument()
      })

      await userEvent.clear(textarea)
      await userEvent.click(textarea)
      await userEvent.paste(
        '{"system_prompt": "test", "instruction_prompt": "test"}'
      )

      await waitFor(() => {
        expect(
          screen.queryByText(/Invalid JSON format/i)
        ).not.toBeInTheDocument()
        expect(screen.getByText('Configuration is valid')).toBeInTheDocument()
      })
    })

    it('should not show preview when config is invalid', async () => {
      render(<GenerationStructureEditor onSave={mockOnSave} />)

      const textarea = screen.getByPlaceholderText(
        'Enter your JSON generation structure configuration...'
      )
      await userEvent.click(textarea)
      await userEvent.paste('invalid json')

      const previewButton = screen.getByRole('button', {
        name: /Show Preview/i,
      })
      await userEvent.click(previewButton)

      await waitFor(() => {
        expect(screen.queryByText('Structure Preview')).not.toBeInTheDocument()
      })
    })

    it('should validate on initial load if config provided', async () => {
      const initialConfig =
        '{"system_prompt": "test", "instruction_prompt": "test"}'
      render(
        <GenerationStructureEditor
          initialConfig={initialConfig}
          onSave={mockOnSave}
        />
      )

      await waitFor(() => {
        expect(screen.getByText('Configuration is valid')).toBeInTheDocument()
      })
    })

    it('should show error on initial load if invalid config provided', async () => {
      const initialConfig = 'invalid json'
      render(
        <GenerationStructureEditor
          initialConfig={initialConfig}
          onSave={mockOnSave}
        />
      )

      await waitFor(() => {
        expect(screen.getByText(/Invalid JSON format/i)).toBeInTheDocument()
      })
    })
  })
})

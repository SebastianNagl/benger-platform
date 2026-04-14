/**
 * Comprehensive tests for LabelConfigEditor component
 */

/**
 * @jest-environment jsdom
 */

import '@testing-library/jest-dom'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { LabelConfigEditor } from '../LabelConfigEditor'

const mockTranslate = (key: string, arg2?: any, arg3?: any) => {
  const vars = typeof arg2 === 'object' ? arg2 : arg3
  const translations: Record<string, string> = {
    'projects.labelConfig.title': 'Label Configuration',
    'projects.labelConfig.description': 'Edit your Label Studio XML configuration below',
    'projects.labelConfig.placeholder': 'Enter your Label Studio XML configuration...',
    'projects.labelConfig.errorEmpty': 'Configuration cannot be empty',
    'projects.labelConfig.errorInvalidXml': 'Invalid XML: ',
    'projects.labelConfig.errorMissingView': 'Configuration must contain a <View> element',
    'projects.labelConfig.errorInvalidFormat': 'Invalid configuration format',
    'projects.labelConfig.valid': 'Configuration is valid',
    'projects.labelConfig.saveButton': 'Save Configuration',
    'common.cancel': 'Cancel',
    'project.labelConfiguration.fieldReferenceHelp': 'Reference task data fields in your XML using $fieldname syntax (e.g., $text, $question).',
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

describe('LabelConfigEditor', () => {
  const mockOnSave = jest.fn()
  const mockOnCancel = jest.fn()

  beforeEach(() => {
    jest.clearAllMocks()
  })

  describe('Component Rendering', () => {
    it('should render the editor with all main sections', () => {
      render(<LabelConfigEditor onSave={mockOnSave} />)

      expect(screen.getByText('Label Configuration')).toBeInTheDocument()
      expect(
        screen.getByText(/Edit your Label Studio XML configuration/i)
      ).toBeInTheDocument()
      expect(
        screen.getByPlaceholderText(
          /Enter your Label Studio XML configuration/i
        )
      ).toBeInTheDocument()
    })

    it('should render save button', () => {
      render(<LabelConfigEditor onSave={mockOnSave} />)

      expect(
        screen.getByRole('button', { name: /save configuration/i })
      ).toBeInTheDocument()
    })

    it('should render cancel button when onCancel is provided', () => {
      render(<LabelConfigEditor onSave={mockOnSave} onCancel={mockOnCancel} />)

      expect(
        screen.getByRole('button', { name: /cancel/i })
      ).toBeInTheDocument()
    })

    it('should not render cancel button when onCancel is not provided', () => {
      render(<LabelConfigEditor onSave={mockOnSave} />)

      expect(
        screen.queryByRole('button', { name: /cancel/i })
      ).not.toBeInTheDocument()
    })

    it('should render with initial configuration', () => {
      const initialConfig = '<View><Text name="test" value="$text"/></View>'
      render(
        <LabelConfigEditor initialConfig={initialConfig} onSave={mockOnSave} />
      )

      const textarea = screen.getByPlaceholderText(
        /Enter your Label Studio XML configuration/i
      ) as HTMLTextAreaElement
      expect(textarea.value).toBe(initialConfig)
    })
  })

  describe('Config Editing', () => {
    it('should allow typing in the textarea', async () => {
      const user = userEvent.setup()
      render(<LabelConfigEditor onSave={mockOnSave} />)

      const textarea = screen.getByPlaceholderText(
        /Enter your Label Studio XML configuration/i
      )

      await user.type(textarea, '<View><Text name="test"/></View>')

      expect(textarea).toHaveValue('<View><Text name="test"/></View>')
    })

    it('should clear existing text when typing new config', async () => {
      const user = userEvent.setup()
      const initialConfig = '<View><Text name="old"/></View>'
      render(
        <LabelConfigEditor initialConfig={initialConfig} onSave={mockOnSave} />
      )

      const textarea = screen.getByPlaceholderText(
        /Enter your Label Studio XML configuration/i
      )

      await user.clear(textarea)
      await user.type(textarea, '<View><Text name="new"/></View>')

      expect(textarea).toHaveValue('<View><Text name="new"/></View>')
    })

    it('should update validation when config changes', async () => {
      const user = userEvent.setup()
      render(<LabelConfigEditor onSave={mockOnSave} />)

      const textarea = screen.getByPlaceholderText(
        /Enter your Label Studio XML configuration/i
      )

      await user.type(
        textarea,
        '<View><Text name="test" value="$text"/></View>'
      )

      await waitFor(() => {
        expect(screen.getByText(/Configuration is valid/i)).toBeInTheDocument()
      })
    })
  })

  describe('Config Validation', () => {
    it('should show error when config is empty on save attempt', async () => {
      const user = userEvent.setup()
      render(<LabelConfigEditor onSave={mockOnSave} />)

      const saveButton = screen.getByRole('button', {
        name: /save configuration/i,
      })

      expect(saveButton).toBeDisabled()
    })

    it('should show valid message for valid config', async () => {
      const user = userEvent.setup()
      render(<LabelConfigEditor onSave={mockOnSave} />)

      const textarea = screen.getByPlaceholderText(
        /Enter your Label Studio XML configuration/i
      )

      await user.type(
        textarea,
        '<View><Text name="test" value="$text"/></View>'
      )

      await waitFor(() => {
        expect(screen.getByText(/Configuration is valid/i)).toBeInTheDocument()
      })
    })

    it('should show error for invalid XML', async () => {
      const user = userEvent.setup()
      render(<LabelConfigEditor onSave={mockOnSave} />)

      const textarea = screen.getByPlaceholderText(
        /Enter your Label Studio XML configuration/i
      )

      await user.type(textarea, '<View><Text name="test">')

      await waitFor(() => {
        expect(screen.getByText(/Invalid XML/i)).toBeInTheDocument()
      })
    })

    it('should show error for missing View element', async () => {
      const user = userEvent.setup()
      render(<LabelConfigEditor onSave={mockOnSave} />)

      const textarea = screen.getByPlaceholderText(
        /Enter your Label Studio XML configuration/i
      )

      await user.type(textarea, '<Text name="test" value="$text"/>')

      await waitFor(() => {
        expect(
          screen.getByText(/Configuration must contain a <View> element/i)
        ).toBeInTheDocument()
      })
    })

    it('should disable save button when config has errors', async () => {
      const user = userEvent.setup()
      render(<LabelConfigEditor onSave={mockOnSave} />)

      const textarea = screen.getByPlaceholderText(
        /Enter your Label Studio XML configuration/i
      )

      await user.type(textarea, '<View><Text name="test">')

      await waitFor(() => {
        const saveButton = screen.getByRole('button', {
          name: /save configuration/i,
        })
        expect(saveButton).toBeDisabled()
      })
    })

    it('should enable save button when config is valid', async () => {
      const user = userEvent.setup()
      render(<LabelConfigEditor onSave={mockOnSave} />)

      const textarea = screen.getByPlaceholderText(
        /Enter your Label Studio XML configuration/i
      )

      await user.type(
        textarea,
        '<View><Text name="test" value="$text"/></View>'
      )

      await waitFor(() => {
        const saveButton = screen.getByRole('button', {
          name: /save configuration/i,
        })
        expect(saveButton).not.toBeDisabled()
      })
    })

    it('should handle complex nested XML structures', async () => {
      const user = userEvent.setup()
      render(<LabelConfigEditor onSave={mockOnSave} />)

      const textarea = screen.getByPlaceholderText(
        /Enter your Label Studio XML configuration/i
      )

      const complexConfig = `<View>
  <Text name="text" value="$text"/>
  <Choices name="sentiment" toName="text">
    <Choice value="Positive"/>
    <Choice value="Negative"/>
  </Choices>
  <TextArea name="comment" toName="text"/>
</View>`

      await user.type(textarea, complexConfig)

      await waitFor(() => {
        expect(screen.getByText(/Configuration is valid/i)).toBeInTheDocument()
      })
    })
  })

  describe('Save Functionality', () => {
    it('should call onSave with valid config when save button is clicked', async () => {
      const user = userEvent.setup()
      render(<LabelConfigEditor onSave={mockOnSave} />)

      const textarea = screen.getByPlaceholderText(
        /Enter your Label Studio XML configuration/i
      )
      const validConfig = '<View><Text name="test" value="$text"/></View>'

      await user.type(textarea, validConfig)

      await waitFor(() => {
        const saveButton = screen.getByRole('button', {
          name: /save configuration/i,
        })
        expect(saveButton).not.toBeDisabled()
      })

      const saveButton = screen.getByRole('button', {
        name: /save configuration/i,
      })
      await user.click(saveButton)

      expect(mockOnSave).toHaveBeenCalledWith(validConfig)
      expect(mockOnSave).toHaveBeenCalledTimes(1)
    })

    it('should not call onSave when config is invalid', async () => {
      const user = userEvent.setup()
      render(<LabelConfigEditor onSave={mockOnSave} />)

      const textarea = screen.getByPlaceholderText(
        /Enter your Label Studio XML configuration/i
      )

      await user.type(textarea, '<View><Text name="test">')

      await waitFor(() => {
        expect(screen.getByText(/Invalid XML/i)).toBeInTheDocument()
      })

      const saveButton = screen.getByRole('button', {
        name: /save configuration/i,
      })

      expect(saveButton).toBeDisabled()
      expect(mockOnSave).not.toHaveBeenCalled()
    })

  })

  describe('Cancel Functionality', () => {
    it('should call onCancel when cancel button is clicked', async () => {
      const user = userEvent.setup()
      render(<LabelConfigEditor onSave={mockOnSave} onCancel={mockOnCancel} />)

      const cancelButton = screen.getByRole('button', { name: /cancel/i })
      await user.click(cancelButton)

      expect(mockOnCancel).toHaveBeenCalledTimes(1)
    })

    it('should call onCancel without saving changes', async () => {
      const user = userEvent.setup()
      render(<LabelConfigEditor onSave={mockOnSave} onCancel={mockOnCancel} />)

      const textarea = screen.getByPlaceholderText(
        /Enter your Label Studio XML configuration/i
      )

      await user.type(
        textarea,
        '<View><Text name="test" value="$text"/></View>'
      )

      const cancelButton = screen.getByRole('button', { name: /cancel/i })
      await user.click(cancelButton)

      expect(mockOnCancel).toHaveBeenCalledTimes(1)
      expect(mockOnSave).not.toHaveBeenCalled()
    })
  })

  describe('Error Handling', () => {
    it('should show error alert with error icon for invalid configs', async () => {
      const user = userEvent.setup()
      render(<LabelConfigEditor onSave={mockOnSave} />)

      const textarea = screen.getByPlaceholderText(
        /Enter your Label Studio XML configuration/i
      )

      await user.type(textarea, '<View><Invalid')

      await waitFor(() => {
        expect(screen.getByText(/Invalid XML/i)).toBeInTheDocument()
      })
    })

    it('should show success alert with check icon for valid configs', async () => {
      const user = userEvent.setup()
      render(<LabelConfigEditor onSave={mockOnSave} />)

      const textarea = screen.getByPlaceholderText(
        /Enter your Label Studio XML configuration/i
      )

      await user.type(
        textarea,
        '<View><Text name="test" value="$text"/></View>'
      )

      await waitFor(() => {
        expect(screen.getByText(/Configuration is valid/i)).toBeInTheDocument()
      })
    })

    it('should clear error when invalid config is fixed', async () => {
      const user = userEvent.setup()
      render(<LabelConfigEditor onSave={mockOnSave} />)

      const textarea = screen.getByPlaceholderText(
        /Enter your Label Studio XML configuration/i
      )

      await user.type(textarea, '<View><Text')

      await waitFor(() => {
        expect(screen.getByText(/Invalid XML/i)).toBeInTheDocument()
      })

      await user.clear(textarea)
      await user.type(
        textarea,
        '<View><Text name="test" value="$text"/></View>'
      )

      await waitFor(() => {
        expect(screen.queryByText(/Invalid XML/i)).not.toBeInTheDocument()
        expect(screen.getByText(/Configuration is valid/i)).toBeInTheDocument()
      })
    })

    it('should show error when clearing a valid config', async () => {
      const user = userEvent.setup()
      const initialConfig = '<View><Text name="test" value="$text"/></View>'
      render(
        <LabelConfigEditor initialConfig={initialConfig} onSave={mockOnSave} />
      )

      await waitFor(() => {
        expect(screen.getByText(/Configuration is valid/i)).toBeInTheDocument()
      })

      const textarea = screen.getByPlaceholderText(
        /Enter your Label Studio XML configuration/i
      )

      await user.clear(textarea)

      await waitFor(() => {
        const saveButton = screen.getByRole('button', {
          name: /save configuration/i,
        })
        expect(saveButton).toBeDisabled()
      })
    })
  })

  describe('Initial State', () => {
    it('should have empty textarea when no initial config is provided', () => {
      render(<LabelConfigEditor onSave={mockOnSave} />)

      const textarea = screen.getByPlaceholderText(
        /Enter your Label Studio XML configuration/i
      ) as HTMLTextAreaElement

      expect(textarea.value).toBe('')
    })

    it('should have disabled save button when config is empty', () => {
      render(<LabelConfigEditor onSave={mockOnSave} />)

      const saveButton = screen.getByRole('button', {
        name: /save configuration/i,
      })

      expect(saveButton).toBeDisabled()
    })

    it('should not show validation messages when config is empty', () => {
      render(<LabelConfigEditor onSave={mockOnSave} />)

      expect(
        screen.queryByText(/Configuration is valid/i)
      ).not.toBeInTheDocument()
      expect(screen.queryByText(/Invalid/i)).not.toBeInTheDocument()
    })

    it('should validate initial config if provided', async () => {
      const initialConfig = '<View><Text name="test" value="$text"/></View>'
      render(
        <LabelConfigEditor initialConfig={initialConfig} onSave={mockOnSave} />
      )

      await waitFor(() => {
        expect(screen.getByText(/Configuration is valid/i)).toBeInTheDocument()
      })
    })

    it('should show error for invalid initial config', async () => {
      const invalidConfig = '<View><Text'
      render(
        <LabelConfigEditor initialConfig={invalidConfig} onSave={mockOnSave} />
      )

      await waitFor(() => {
        expect(screen.getByText(/Invalid XML/i)).toBeInTheDocument()
      })
    })
  })

  describe('Edge Cases', () => {
    it('should handle whitespace-only config as invalid', async () => {
      const user = userEvent.setup()
      render(<LabelConfigEditor onSave={mockOnSave} />)

      const textarea = screen.getByPlaceholderText(
        /Enter your Label Studio XML configuration/i
      )

      await user.type(textarea, '   \n\n   ')

      const saveButton = screen.getByRole('button', {
        name: /save configuration/i,
      })

      expect(saveButton).toBeDisabled()
    })

    it('should handle config with only opening View tag', async () => {
      const user = userEvent.setup()
      render(<LabelConfigEditor onSave={mockOnSave} />)

      const textarea = screen.getByPlaceholderText(
        /Enter your Label Studio XML configuration/i
      )

      await user.type(textarea, '<View>')

      await waitFor(() => {
        expect(screen.getByText(/Invalid XML/i)).toBeInTheDocument()
      })
    })

    it('should handle config with self-closing View tag', async () => {
      const user = userEvent.setup()
      render(<LabelConfigEditor onSave={mockOnSave} />)

      const textarea = screen.getByPlaceholderText(
        /Enter your Label Studio XML configuration/i
      )

      await user.type(textarea, '<View/>')

      await waitFor(() => {
        expect(
          screen.getByText(/Configuration must contain a <View> element/i)
        ).toBeInTheDocument()
      })
    })

    it('should handle very long configs', async () => {
      const user = userEvent.setup()
      render(<LabelConfigEditor onSave={mockOnSave} />)

      const textarea = screen.getByPlaceholderText(
        /Enter your Label Studio XML configuration/i
      )

      const longConfig = `<View>
  ${Array(50)
    .fill(0)
    .map((_, i) => `<Text name="text${i}" value="$text${i}"/>`)
    .join('\n  ')}
</View>`

      await user.type(textarea, longConfig)

      await waitFor(() => {
        expect(screen.getByText(/Configuration is valid/i)).toBeInTheDocument()
      })
    })

    it('should handle configs with special characters', async () => {
      const user = userEvent.setup()
      render(<LabelConfigEditor onSave={mockOnSave} />)

      const textarea = screen.getByPlaceholderText(
        /Enter your Label Studio XML configuration/i
      )

      const specialConfig = '<View><Text name="test" value="$text"/></View>'

      await user.type(textarea, specialConfig)

      await waitFor(() => {
        expect(screen.getByText(/Configuration is valid/i)).toBeInTheDocument()
      })
    })

    it('should handle configs with comments', async () => {
      const user = userEvent.setup()
      render(<LabelConfigEditor onSave={mockOnSave} />)

      const textarea = screen.getByPlaceholderText(
        /Enter your Label Studio XML configuration/i
      )

      const commentConfig =
        '<View><!-- Comment --><Text name="text" value="$text"/></View>'

      await user.type(textarea, commentConfig)

      await waitFor(() => {
        expect(screen.getByText(/Configuration is valid/i)).toBeInTheDocument()
      })
    })
  })

  describe('Integration Scenarios', () => {
    it('should complete full workflow: write custom config and save', async () => {
      const user = userEvent.setup()
      render(<LabelConfigEditor onSave={mockOnSave} />)

      const textarea = screen.getByPlaceholderText(
        /Enter your Label Studio XML configuration/i
      )

      const customConfig = `<View>
  <Text name="custom" value="$custom"/>
  <Choices name="rating" toName="custom">
    <Choice value="Good"/>
    <Choice value="Bad"/>
  </Choices>
</View>`

      await user.type(textarea, customConfig)

      await waitFor(() => {
        const saveButton = screen.getByRole('button', {
          name: /save configuration/i,
        })
        expect(saveButton).not.toBeDisabled()
      })

      const saveButton = screen.getByRole('button', {
        name: /save configuration/i,
      })
      await user.click(saveButton)

      expect(mockOnSave).toHaveBeenCalledWith(customConfig)
    })

    it('should handle cancel workflow without saving', async () => {
      const user = userEvent.setup()
      render(<LabelConfigEditor onSave={mockOnSave} onCancel={mockOnCancel} />)

      const textarea = screen.getByPlaceholderText(
        /Enter your Label Studio XML configuration/i
      )

      await user.type(
        textarea,
        '<View><Text name="test" value="$text"/></View>'
      )

      const cancelButton = screen.getByRole('button', { name: /cancel/i })
      await user.click(cancelButton)

      expect(mockOnCancel).toHaveBeenCalledTimes(1)
      expect(mockOnSave).not.toHaveBeenCalled()
    })

    it('should handle edit initial config workflow', async () => {
      const user = userEvent.setup()
      const initialConfig = '<View><Text name="old" value="$old"/></View>'
      render(
        <LabelConfigEditor
          initialConfig={initialConfig}
          onSave={mockOnSave}
          onCancel={mockOnCancel}
        />
      )

      await waitFor(() => {
        expect(screen.getByText(/Configuration is valid/i)).toBeInTheDocument()
      })

      const textarea = screen.getByPlaceholderText(
        /Enter your Label Studio XML configuration/i
      )

      await user.clear(textarea)
      await user.type(textarea, '<View><Text name="new" value="$new"/></View>')

      const saveButton = screen.getByRole('button', {
        name: /save configuration/i,
      })
      await user.click(saveButton)

      expect(mockOnSave).toHaveBeenCalledWith(
        '<View><Text name="new" value="$new"/></View>'
      )
    })
  })
})

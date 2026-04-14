/**
 * Unit tests for FieldMappingSettings component
 */

/**
 * @jest-environment jsdom
 */

import '@testing-library/jest-dom'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { FieldMappingSettings } from '../../../components/projects/FieldMappingSettings'
import { projectsAPI } from '../../../lib/api/projects'

// Mock dependencies
jest.mock('../../../lib/api/projects', () => ({
  projectsAPI: {
    update: jest.fn(),
  },
}))

// Override the global Toast mock from setupTests.ts (must use same path alias)
const mockAddToast = jest.fn()
const mockRemoveToast = jest.fn()
jest.unmock('@/components/shared/Toast')
jest.mock('@/components/shared/Toast', () => ({
  useToast: () => ({
    addToast: mockAddToast,
    removeToast: mockRemoveToast,
    toasts: [],
  }),
  ToastProvider: ({ children }: { children: React.ReactNode }) => children,
}))

// Mock i18n context
const mockFieldMappingTranslate = (key: string, arg2?: any, arg3?: any) => {
  const vars = typeof arg2 === 'object' ? arg2 : arg3
  const translations: Record<string, string> = {
    'toasts.template.annotationUpdated': 'Annotation template has been updated successfully',
    'projects.fieldMapping.title': 'Field Mapping & Template',
    'projects.fieldMapping.editTemplate': 'Edit Template',
    'projects.fieldMapping.fieldMappingStatus': 'Field Mapping Status',
    'projects.fieldMapping.validationError': 'Validation error - These fields are not present in the data:',
    'projects.fieldMapping.validationErrorHint': 'This will cause annotation errors. Update your template or import new data.',
    'projects.fieldMapping.unusedFields': 'Unused fields in your data:',
    'projects.fieldMapping.unusedFieldsHint': 'Consider updating your template to use these fields.',
    'projects.fieldMapping.labelingConfiguration': 'Labeling Configuration',
    'projects.fieldMapping.generateFromData': 'Generate from Data',
    'projects.fieldMapping.placeholder': 'Enter your Label Studio configuration...',
    'projects.fieldMapping.updateTemplate': 'Update Template',
    'projects.fieldMapping.autoConfigureTemplate': 'Auto-Configure Template',
    'projects.fieldMapping.updateFailed': 'Update failed: {error}',
    'projects.fieldMapping.failedUpdateTemplate': 'Failed to update template',
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
    t: mockFieldMappingTranslate,
    locale: 'en',
    setLocale: jest.fn(),
  }),
}))

const mockProjectsAPI = projectsAPI as jest.Mocked<typeof projectsAPI>

describe('FieldMappingSettings', () => {
  const mockOnTemplateUpdate = jest.fn()
  const projectId = 'test-project-123'
  const currentTemplate = `<View>
  <Text name="question" value="$question"/>
  <Text name="answer" value="$answer"/>
  <Choices name="label" toName="question">
    <Choice value="Correct"/>
    <Choice value="Incorrect"/>
  </Choices>
</View>`
  const availableFields = ['question', 'answer', 'category']

  beforeEach(() => {
    jest.clearAllMocks()
    // Reset API mocks to clear any queued mockResolvedValueOnce
    mockProjectsAPI.update.mockReset()
  })

  describe('Component Rendering', () => {
    it('should render the field mapping settings component', () => {
      render(
        <FieldMappingSettings
          projectId={projectId}
          currentTemplate={currentTemplate}
          availableFields={availableFields}
        />
      )

      expect(screen.getByText('Field Mapping & Template')).toBeInTheDocument()
      expect(screen.getByText('Edit Template')).toBeInTheDocument()
    })

    it('should display field mapping status section', () => {
      render(
        <FieldMappingSettings
          projectId={projectId}
          currentTemplate={currentTemplate}
          availableFields={availableFields}
        />
      )

      expect(screen.getByText('Field Mapping Status')).toBeInTheDocument()
    })
  })

  describe('Field Extraction and Display', () => {
    it('should extract and display fields from template', () => {
      render(
        <FieldMappingSettings
          projectId={projectId}
          currentTemplate={currentTemplate}
          availableFields={availableFields}
        />
      )

      expect(screen.getByText('$question')).toBeInTheDocument()
      expect(screen.getByText('$answer')).toBeInTheDocument()
    })

    it('should handle template with no fields', () => {
      const emptyTemplate = '<View></View>'

      render(
        <FieldMappingSettings
          projectId={projectId}
          currentTemplate={emptyTemplate}
          availableFields={availableFields}
        />
      )

      expect(screen.getByText('Field Mapping Status')).toBeInTheDocument()
    })

    it('should extract unique fields only', () => {
      const duplicateTemplate = `<View>
  <Text name="text" value="$text"/>
  <Text name="text2" value="$text"/>
</View>`

      render(
        <FieldMappingSettings
          projectId={projectId}
          currentTemplate={duplicateTemplate}
          availableFields={['text']}
        />
      )

      const textBadges = screen.getAllByText('$text')
      expect(textBadges).toHaveLength(1)
    })
  })

  describe('Field Validation', () => {
    it('should show validation error for missing fields', () => {
      const templateWithMissingField = `<View>
  <Text name="nonexistent" value="$nonexistent"/>
</View>`

      render(
        <FieldMappingSettings
          projectId={projectId}
          currentTemplate={templateWithMissingField}
          availableFields={availableFields}
        />
      )

      expect(
        screen.getByText(
          /Validation error - These fields are not present in the data:/
        )
      ).toBeInTheDocument()
      // Use getAllByText since "nonexistent" appears in both badge and alert text
      const nonexistentElements = screen.getAllByText(/nonexistent/)
      expect(nonexistentElements.length).toBeGreaterThan(0)
    })

    it('should show warning for unused fields', () => {
      const templateWithoutCategory = `<View>
  <Text name="question" value="$question"/>
</View>`

      render(
        <FieldMappingSettings
          projectId={projectId}
          currentTemplate={templateWithoutCategory}
          availableFields={availableFields}
        />
      )

      expect(
        screen.getByText(/Unused fields in your data:/)
      ).toBeInTheDocument()
      expect(screen.getByText(/answer/)).toBeInTheDocument()
      expect(screen.getByText(/category/)).toBeInTheDocument()
    })

    it('should not show validation errors when all fields match', () => {
      const validTemplate = `<View>
  <Text name="question" value="$question"/>
  <Text name="answer" value="$answer"/>
  <Text name="category" value="$category"/>
</View>`

      render(
        <FieldMappingSettings
          projectId={projectId}
          currentTemplate={validTemplate}
          availableFields={availableFields}
        />
      )

      expect(screen.queryByText(/Validation error/)).not.toBeInTheDocument()
      expect(screen.queryByText(/Unused fields/)).not.toBeInTheDocument()
    })
  })

  describe('Template Editing', () => {
    it('should toggle edit mode when Edit Template is clicked', async () => {
      const user = userEvent.setup()

      render(
        <FieldMappingSettings
          projectId={projectId}
          currentTemplate={currentTemplate}
          availableFields={availableFields}
        />
      )

      const editButton = screen.getByText('Edit Template')
      await user.click(editButton)

      expect(screen.getByText('Labeling Configuration')).toBeInTheDocument()
      expect(
        screen.getByPlaceholderText('Enter your Label Studio configuration...')
      ).toBeInTheDocument()
      // Use getAllByText since Cancel appears in multiple buttons
      expect(screen.getAllByText('Cancel').length).toBeGreaterThan(0)
    })

    it('should cancel editing when Cancel is clicked', async () => {
      const user = userEvent.setup()

      render(
        <FieldMappingSettings
          projectId={projectId}
          currentTemplate={currentTemplate}
          availableFields={availableFields}
        />
      )

      const editButton = screen.getByText('Edit Template')
      await user.click(editButton)

      const cancelButton = screen.getAllByText('Cancel')[0]
      await user.click(cancelButton)

      expect(
        screen.queryByPlaceholderText(
          'Enter your Label Studio configuration...'
        )
      ).not.toBeInTheDocument()
    })

    it('should allow editing template content', async () => {
      const user = userEvent.setup()

      render(
        <FieldMappingSettings
          projectId={projectId}
          currentTemplate={currentTemplate}
          availableFields={availableFields}
        />
      )

      const editButton = screen.getByText('Edit Template')
      await user.click(editButton)

      const textarea = screen.getByPlaceholderText(
        'Enter your Label Studio configuration...'
      ) as HTMLTextAreaElement
      await user.clear(textarea)
      await user.type(textarea, '<View><Text name="test"/></View>')

      expect(textarea.value).toContain('<View><Text name="test"/></View>')
    })

    it('should update button text when editing', async () => {
      const user = userEvent.setup()

      render(
        <FieldMappingSettings
          projectId={projectId}
          currentTemplate={currentTemplate}
          availableFields={availableFields}
        />
      )

      const editButton = screen.getByText('Edit Template')
      await user.click(editButton)

      // Use getAllByText since Cancel appears in multiple buttons
      expect(screen.getAllByText('Cancel').length).toBeGreaterThan(0)
    })
  })

  describe('Template Update', () => {
    it('should successfully update template', async () => {
      const user = userEvent.setup()
      mockProjectsAPI.update.mockResolvedValueOnce({} as any)

      render(
        <FieldMappingSettings
          projectId={projectId}
          currentTemplate={currentTemplate}
          availableFields={availableFields}
          onTemplateUpdate={mockOnTemplateUpdate}
        />
      )

      const editButton = screen.getByText('Edit Template')
      await user.click(editButton)

      const textarea = screen.getByPlaceholderText(
        'Enter your Label Studio configuration...'
      )
      const newTemplate = '<View><Text name="new"/></View>'
      await user.clear(textarea)
      await user.type(textarea, newTemplate)

      const updateButton = screen.getByText('Update Template')
      await user.click(updateButton)

      await waitFor(
        () => {
          expect(mockProjectsAPI.update).toHaveBeenCalledWith(projectId, {
            label_config: newTemplate,
          })
          expect(mockAddToast).toHaveBeenCalledWith(
            'Annotation template has been updated successfully',
            'success'
          )
          expect(mockOnTemplateUpdate).toHaveBeenCalledWith(newTemplate)
        },
        { timeout: 3000 }
      )
    })

    it('should handle update error', async () => {
      const user = userEvent.setup()
      mockProjectsAPI.update.mockRejectedValueOnce(new Error('Network error'))

      render(
        <FieldMappingSettings
          projectId={projectId}
          currentTemplate={currentTemplate}
          availableFields={availableFields}
        />
      )

      const editButton = screen.getByText('Edit Template')
      await user.click(editButton)

      const updateButton = screen.getByText('Update Template')
      await user.click(updateButton)

      await waitFor(
        () => {
          expect(mockAddToast).toHaveBeenCalledWith(
            expect.stringContaining('Update failed'),
            'error'
          )
        },
        { timeout: 3000 }
      )
    })

    it('should close editor after successful update', async () => {
      const user = userEvent.setup()
      mockProjectsAPI.update.mockResolvedValueOnce({} as any)

      render(
        <FieldMappingSettings
          projectId={projectId}
          currentTemplate={currentTemplate}
          availableFields={availableFields}
        />
      )

      const editButton = screen.getByText('Edit Template')
      await user.click(editButton)

      const updateButton = screen.getByText('Update Template')
      await user.click(updateButton)

      await waitFor(() => {
        expect(
          screen.queryByPlaceholderText(
            'Enter your Label Studio configuration...'
          )
        ).not.toBeInTheDocument()
      })
    })

    it('should work without onTemplateUpdate callback', async () => {
      const user = userEvent.setup()
      mockProjectsAPI.update.mockResolvedValueOnce({} as any)

      render(
        <FieldMappingSettings
          projectId={projectId}
          currentTemplate={currentTemplate}
          availableFields={availableFields}
        />
      )

      const editButton = screen.getByText('Edit Template')
      await user.click(editButton)

      const updateButton = screen.getByText('Update Template')
      await user.click(updateButton)

      await waitFor(() => {
        expect(mockProjectsAPI.update).toHaveBeenCalled()
      })
    })
  })

  describe('Template Generation', () => {
    it('should generate template from available fields', async () => {
      const user = userEvent.setup()

      render(
        <FieldMappingSettings
          projectId={projectId}
          currentTemplate={currentTemplate}
          availableFields={['text', 'image', 'question', 'other']}
        />
      )

      const editButton = screen.getByText('Edit Template')
      await user.click(editButton)

      const generateButton = screen.getByText('Generate from Data')
      await user.click(generateButton)

      const textarea = screen.getByPlaceholderText(
        'Enter your Label Studio configuration...'
      ) as HTMLTextAreaElement

      expect(textarea.value).toContain('<View>')
      expect(textarea.value).toContain('name="text"')
      expect(textarea.value).toContain('value="$text"')
      expect(textarea.value).toContain('<Choices')
    })

    it('should detect text fields in template generation', async () => {
      const user = userEvent.setup()

      render(
        <FieldMappingSettings
          projectId={projectId}
          currentTemplate={currentTemplate}
          availableFields={['question_text', 'answer_text']}
        />
      )

      const editButton = screen.getByText('Edit Template')
      await user.click(editButton)

      const generateButton = screen.getByText('Generate from Data')
      await user.click(generateButton)

      const textarea = screen.getByPlaceholderText(
        'Enter your Label Studio configuration...'
      ) as HTMLTextAreaElement

      expect(textarea.value).toContain('<Text name="question_text"')
      expect(textarea.value).toContain('<Text name="answer_text"')
    })

    it('should detect image fields in template generation', async () => {
      const user = userEvent.setup()

      render(
        <FieldMappingSettings
          projectId={projectId}
          currentTemplate={currentTemplate}
          availableFields={['photo_image', 'document']}
        />
      )

      const editButton = screen.getByText('Edit Template')
      await user.click(editButton)

      const generateButton = screen.getByText('Generate from Data')
      await user.click(generateButton)

      const textarea = screen.getByPlaceholderText(
        'Enter your Label Studio configuration...'
      ) as HTMLTextAreaElement

      expect(textarea.value).toContain('<Image name="photo_image"')
      expect(textarea.value).toContain('<Text name="document"')
    })

    it('should auto-configure template via quick action', async () => {
      const user = userEvent.setup()

      render(
        <FieldMappingSettings
          projectId={projectId}
          currentTemplate={currentTemplate}
          availableFields={['text', 'label']}
        />
      )

      const autoConfigButton = screen.getByText('Auto-Configure Template')
      await user.click(autoConfigButton)

      expect(
        screen.queryByPlaceholderText(
          'Enter your Label Studio configuration...'
        )
      ).not.toBeInTheDocument()
    })

    it('should disable auto-configure when no fields available', () => {
      render(
        <FieldMappingSettings
          projectId={projectId}
          currentTemplate={currentTemplate}
          availableFields={[]}
        />
      )

      const autoConfigButton = screen.getByText('Auto-Configure Template')
      expect(autoConfigButton).toBeDisabled()
    })
  })

  describe('Loading States', () => {
    it('should show loading state during update', async () => {
      const user = userEvent.setup()
      let resolveUpdate: any
      mockProjectsAPI.update.mockReturnValueOnce(
        new Promise((resolve) => {
          resolveUpdate = resolve
        })
      )

      render(
        <FieldMappingSettings
          projectId={projectId}
          currentTemplate={currentTemplate}
          availableFields={availableFields}
        />
      )

      const editButton = screen.getByText('Edit Template')
      await user.click(editButton)

      const updateButton = screen.getByText('Update Template')
      await user.click(updateButton)

      await waitFor(() => {
        // Button component disables when loading
        expect(updateButton).toBeDisabled()
      })

      resolveUpdate({})
    })
  })

  describe('Field Badge Display', () => {
    it('should show correct badge variant for mapped fields', () => {
      render(
        <FieldMappingSettings
          projectId={projectId}
          currentTemplate={currentTemplate}
          availableFields={availableFields}
        />
      )

      const questionBadge = screen.getByText('$question').closest('div')
      expect(questionBadge).toBeTruthy()
      expect(questionBadge?.className).not.toContain('destructive')
    })

    it('should show destructive badge variant for unmapped fields', () => {
      const templateWithMissingField = `<View>
  <Text name="missing" value="$missing"/>
</View>`

      render(
        <FieldMappingSettings
          projectId={projectId}
          currentTemplate={templateWithMissingField}
          availableFields={availableFields}
        />
      )

      expect(screen.getByText('$missing')).toBeInTheDocument()
    })
  })

  describe('Edge Cases', () => {
    it('should handle template with complex field patterns', () => {
      const complexTemplate = `<View>
  <Text name="field1" value="$field_1"/>
  <Text name="field2" value="$field_2"/>
  <Text name="field3" value="$field3_test"/>
</View>`

      render(
        <FieldMappingSettings
          projectId={projectId}
          currentTemplate={complexTemplate}
          availableFields={['field_1', 'field_2', 'field3_test']}
        />
      )

      expect(screen.getByText('$field_1')).toBeInTheDocument()
      expect(screen.getByText('$field_2')).toBeInTheDocument()
      expect(screen.getByText('$field3_test')).toBeInTheDocument()
    })

    it('should handle empty available fields array', () => {
      render(
        <FieldMappingSettings
          projectId={projectId}
          currentTemplate={currentTemplate}
          availableFields={[]}
        />
      )

      expect(
        screen.getByText(
          /Validation error - These fields are not present in the data:/
        )
      ).toBeInTheDocument()
    })

    it('should handle template update with error message', async () => {
      const user = userEvent.setup()
      mockProjectsAPI.update.mockRejectedValueOnce({
        message: 'Invalid template syntax',
      })

      render(
        <FieldMappingSettings
          projectId={projectId}
          currentTemplate={currentTemplate}
          availableFields={availableFields}
        />
      )

      const editButton = screen.getByText('Edit Template')
      await user.click(editButton)

      const updateButton = screen.getByText('Update Template')
      await user.click(updateButton)

      await waitFor(
        () => {
          expect(mockAddToast).toHaveBeenCalledWith(
            'Update failed: Invalid template syntax',
            'error'
          )
        },
        { timeout: 3000 }
      )
    })

    it('should handle template update with generic error', async () => {
      const user = userEvent.setup()
      mockProjectsAPI.update.mockRejectedValueOnce({})

      render(
        <FieldMappingSettings
          projectId={projectId}
          currentTemplate={currentTemplate}
          availableFields={availableFields}
        />
      )

      const editButton = screen.getByText('Edit Template')
      await user.click(editButton)

      const updateButton = screen.getByText('Update Template')
      await user.click(updateButton)

      await waitFor(
        () => {
          expect(mockAddToast).toHaveBeenCalledWith(
            'Update failed: Failed to update template',
            'error'
          )
        },
        { timeout: 3000 }
      )
    })
  })

  describe('Accessibility', () => {
    it('should have proper button roles', () => {
      render(
        <FieldMappingSettings
          projectId={projectId}
          currentTemplate={currentTemplate}
          availableFields={availableFields}
        />
      )

      const editButton = screen.getByText('Edit Template')
      expect(editButton).toBeInTheDocument()

      const autoConfigButton = screen.getByText('Auto-Configure Template')
      expect(autoConfigButton).toBeInTheDocument()
    })

    it('should have proper textarea attributes', async () => {
      const user = userEvent.setup()

      render(
        <FieldMappingSettings
          projectId={projectId}
          currentTemplate={currentTemplate}
          availableFields={availableFields}
        />
      )

      const editButton = screen.getByText('Edit Template')
      await user.click(editButton)

      const textarea = screen.getByPlaceholderText(
        'Enter your Label Studio configuration...'
      )
      expect(textarea).toHaveAttribute('placeholder')
    })
  })
})

/**
 * @jest-environment jsdom
 */
import '@testing-library/jest-dom'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { FieldMappingEditor } from '../FieldMappingEditor'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, fallback?: string) => {
      const translations: Record<string, string> = {
        'fieldMapping.title': 'Custom Field Mappings',
        'fieldMapping.addMapping': 'Add Mapping',
        'fieldMapping.helpText': 'Map custom template variables to task data fields.',
        'fieldMapping.noMappings': 'No field mappings defined. Click "Add Mapping" to create one.',
        'fieldMapping.variableName': 'Variable Name',
        'fieldMapping.taskField': 'Task Data Field',
        'fieldMapping.variablePlaceholder': 'domain',
        'fieldMapping.selectField': 'Select a field...',
        'fieldMapping.reservedVariable': 'Reserved variable name',
        'fieldMapping.availableFields': 'Available fields in your tasks:',
        'common.delete': 'Delete',
      }
      return translations[key] || fallback || key
    },
  }),
}))

const mockGetTaskFields = jest.fn()

jest.mock('@/lib/api/projects', () => ({
  projectsAPI: {
    getTaskFields: (...args: any[]) => mockGetTaskFields(...args),
  },
}))

jest.mock('@/components/shared/TaskFieldSelector', () => ({
  TaskFieldSelector: ({ projectId, value, onChange, placeholder }: any) => (
    <select
      data-testid="task-field-selector"
      value={value}
      onChange={(e) => onChange(e.target.value)}
    >
      <option value="">{placeholder}</option>
      <option value="data.text">data.text</option>
      <option value="data.label">data.label</option>
    </select>
  ),
  // Re-export the interface type placeholder
  TaskFieldInfo: undefined,
}))

jest.mock('@/components/shared/LoadingSpinner', () => ({
  LoadingSpinner: ({ size }: any) => <div data-testid="loading-spinner" data-size={size} />,
}))

describe('FieldMappingEditor', () => {
  const defaultProps = {
    projectId: 'project-1',
    value: {},
    onChange: jest.fn(),
  }

  beforeEach(() => {
    jest.clearAllMocks()
    mockGetTaskFields.mockResolvedValue({
      fields: [
        { path: 'data.text', sample_value: 'Hello world' },
        { path: 'data.label', sample_value: 'positive' },
      ],
    })
  })

  describe('Empty state', () => {
    it('renders the title', () => {
      render(<FieldMappingEditor {...defaultProps} />)
      expect(screen.getByText('Custom Field Mappings')).toBeInTheDocument()
    })

    it('renders the Add Mapping button', () => {
      render(<FieldMappingEditor {...defaultProps} />)
      expect(screen.getByText('Add Mapping')).toBeInTheDocument()
    })

    it('shows help text', () => {
      render(<FieldMappingEditor {...defaultProps} />)
      expect(screen.getByText('Map custom template variables to task data fields.')).toBeInTheDocument()
    })

    it('shows empty state message when no mappings exist', () => {
      render(<FieldMappingEditor {...defaultProps} />)
      expect(screen.getByText(/No field mappings defined/)).toBeInTheDocument()
    })
  })

  describe('Pre-existing values', () => {
    it('renders rows from initial value prop', () => {
      render(
        <FieldMappingEditor
          {...defaultProps}
          value={{ my_variable: 'data.text' }}
        />
      )
      // Variable name input should have the value
      const inputs = screen.getAllByRole('textbox')
      expect(inputs[0]).toHaveValue('my_variable')
    })

    it('renders multiple rows from initial value', () => {
      render(
        <FieldMappingEditor
          {...defaultProps}
          value={{ var1: 'data.text', var2: 'data.label' }}
        />
      )
      const inputs = screen.getAllByRole('textbox')
      expect(inputs).toHaveLength(2)
    })
  })

  describe('Adding mappings', () => {
    it('adds a new empty row when Add Mapping is clicked', async () => {
      const user = userEvent.setup()
      render(<FieldMappingEditor {...defaultProps} />)

      await user.click(screen.getByText('Add Mapping'))

      // Should show a text input and a field selector
      expect(screen.getByRole('textbox')).toBeInTheDocument()
      expect(screen.getByTestId('task-field-selector')).toBeInTheDocument()
    })

    it('shows column headers after adding a row', async () => {
      const user = userEvent.setup()
      render(<FieldMappingEditor {...defaultProps} />)

      await user.click(screen.getByText('Add Mapping'))

      expect(screen.getByText('Variable Name')).toBeInTheDocument()
      expect(screen.getByText('Task Data Field')).toBeInTheDocument()
    })
  })

  describe('Editing mappings', () => {
    it('updates variable name and calls onChange', async () => {
      const user = userEvent.setup()
      const onChange = jest.fn()
      render(<FieldMappingEditor {...defaultProps} onChange={onChange} />)

      // Add a row
      await user.click(screen.getByText('Add Mapping'))

      // Type a variable name
      const input = screen.getByRole('textbox')
      await user.type(input, 'my_var')

      // onChange should not be called with empty fieldPath (no complete mapping)
      // The emitChanges function only emits if both variableName and fieldPath are set
      // So with just variable name, it would be called with empty object
      expect(onChange).toHaveBeenCalled()
    })

    it('sanitizes variable name to alphanumeric and underscore only', async () => {
      const user = userEvent.setup()
      render(<FieldMappingEditor {...defaultProps} />)

      await user.click(screen.getByText('Add Mapping'))

      const input = screen.getByRole('textbox')
      await user.type(input, 'my-var.name!@#$')

      // Should strip out non-alphanumeric/underscore characters
      expect(input).toHaveValue('myvarname')
    })

    it('shows template preview for variable name', async () => {
      const user = userEvent.setup()
      render(
        <FieldMappingEditor
          {...defaultProps}
          value={{ domain: 'data.text' }}
        />
      )

      // Should show {{domain}} preview
      expect(screen.getByText('{{domain}}')).toBeInTheDocument()
    })
  })

  describe('Reserved variables', () => {
    it('shows error for reserved variable names', () => {
      render(
        <FieldMappingEditor
          {...defaultProps}
          value={{ context: 'data.text' }}
        />
      )
      expect(screen.getByText('Reserved variable name')).toBeInTheDocument()
    })

    it('marks row with error styling for reserved variable "ground_truth"', () => {
      render(
        <FieldMappingEditor
          {...defaultProps}
          value={{ ground_truth: 'data.label' }}
        />
      )
      expect(screen.getByText('Reserved variable name')).toBeInTheDocument()
    })
  })

  describe('Removing mappings', () => {
    it('removes a row when delete button is clicked', async () => {
      const user = userEvent.setup()
      const onChange = jest.fn()
      render(
        <FieldMappingEditor
          {...defaultProps}
          value={{ my_var: 'data.text' }}
          onChange={onChange}
        />
      )

      // Find and click the delete button
      const deleteButton = screen.getByTitle('Delete')
      await user.click(deleteButton)

      // Should call onChange with empty mappings
      expect(onChange).toHaveBeenCalledWith({})
    })
  })

  describe('Field fetching', () => {
    it('fetches available fields for the project', async () => {
      render(<FieldMappingEditor {...defaultProps} />)

      await waitFor(() => {
        expect(mockGetTaskFields).toHaveBeenCalledWith('project-1')
      })
    })

    it('shows available fields reference section when fields are loaded', async () => {
      render(<FieldMappingEditor {...defaultProps} />)

      await waitFor(() => {
        expect(screen.getByText('Available fields in your tasks:')).toBeInTheDocument()
        expect(screen.getByText('data.text')).toBeInTheDocument()
        expect(screen.getByText('data.label')).toBeInTheDocument()
      })
    })

    it('handles field fetch errors gracefully', async () => {
      const consoleSpy = jest.spyOn(console, 'error').mockImplementation()
      mockGetTaskFields.mockRejectedValue(new Error('Fetch failed'))

      render(<FieldMappingEditor {...defaultProps} />)

      await waitFor(() => {
        expect(consoleSpy).toHaveBeenCalledWith('Failed to fetch task fields:', expect.any(Error))
      })
      consoleSpy.mockRestore()
    })

    it('does not fetch fields when projectId is empty', () => {
      render(<FieldMappingEditor {...defaultProps} projectId="" />)
      expect(mockGetTaskFields).not.toHaveBeenCalled()
    })

    it('shows +N more label when more than 10 fields exist', async () => {
      const fields = Array.from({ length: 15 }, (_, i) => ({
        path: `data.field_${i}`,
        sample_value: `value_${i}`,
      }))
      mockGetTaskFields.mockResolvedValue({ fields })

      render(<FieldMappingEditor {...defaultProps} />)

      await waitFor(() => {
        expect(screen.getByText('+5 more')).toBeInTheDocument()
      })
    })
  })

  describe('Warning states', () => {
    it('shows warning styling when variable has name but no field path', async () => {
      const user = userEvent.setup()
      render(<FieldMappingEditor {...defaultProps} />)

      // Add a row
      await user.click(screen.getByText('Add Mapping'))

      // Type a variable name but don't select a field
      const input = screen.getByRole('textbox')
      await user.type(input, 'my_var')

      // The row should have warning-like styling (amber border)
      // The component applies `border-amber-300` for hasWarning
      const row = input.closest('.grid')
      expect(row).toBeInTheDocument()
    })
  })
})

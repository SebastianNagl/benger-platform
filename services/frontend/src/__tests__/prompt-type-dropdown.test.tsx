/**
 * @jest-environment jsdom
 */

import '@testing-library/jest-dom'
import { fireEvent, render, screen } from '@testing-library/react'

// Mock component to test the prompt type dropdown behavior
const PromptTypeDropdown = ({
  value,
  onChange,
}: {
  value: string
  onChange: (value: string) => void
}) => {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      data-testid="prompt-type-select"
    >
      <option value="evaluation">Evaluation</option>
      <option value="instruction">Instruction</option>
      <option value="system">System</option>
    </select>
  )
}

describe('Prompt Type Dropdown', () => {
  test('should render all three prompt type options', () => {
    const mockOnChange = jest.fn()
    render(<PromptTypeDropdown value="instruction" onChange={mockOnChange} />)

    const select = screen.getByTestId('prompt-type-select')
    const options = select.querySelectorAll('option')

    expect(options).toHaveLength(3)
    expect(options[0]).toHaveValue('evaluation')
    expect(options[1]).toHaveValue('instruction')
    expect(options[2]).toHaveValue('system')
  })

  test('should display the current value correctly', () => {
    const mockOnChange = jest.fn()
    render(<PromptTypeDropdown value="system" onChange={mockOnChange} />)

    const select = screen.getByTestId('prompt-type-select') as HTMLSelectElement
    expect(select.value).toBe('system')
  })

  test('should call onChange when selection changes', () => {
    const mockOnChange = jest.fn()
    render(<PromptTypeDropdown value="instruction" onChange={mockOnChange} />)

    const select = screen.getByTestId('prompt-type-select')
    fireEvent.change(select, { target: { value: 'system' } })

    expect(mockOnChange).toHaveBeenCalledWith('system')
  })

  test('should handle all prompt type transitions', () => {
    const mockOnChange = jest.fn()
    const { rerender } = render(
      <PromptTypeDropdown value="evaluation" onChange={mockOnChange} />
    )

    const select = screen.getByTestId('prompt-type-select') as HTMLSelectElement

    // Change from evaluation to instruction
    fireEvent.change(select, { target: { value: 'instruction' } })
    expect(mockOnChange).toHaveBeenCalledWith('instruction')

    // Update props to reflect new value
    rerender(<PromptTypeDropdown value="instruction" onChange={mockOnChange} />)
    expect(select.value).toBe('instruction')

    // Change from instruction to system
    fireEvent.change(select, { target: { value: 'system' } })
    expect(mockOnChange).toHaveBeenCalledWith('system')

    // Update props to reflect new value
    rerender(<PromptTypeDropdown value="system" onChange={mockOnChange} />)
    expect(select.value).toBe('system')

    // Change from system to evaluation
    fireEvent.change(select, { target: { value: 'evaluation' } })
    expect(mockOnChange).toHaveBeenCalledWith('evaluation')
  })
})

// Test the actual implementation pattern used in the task page
describe('Prompt Type Update Pattern', () => {
  test('should correctly update editingPromptData state', () => {
    // Simulate the state update pattern used in the actual code
    let editingPromptData: any = {
      prompt_name: 'Test Prompt',
      prompt_text: 'Test text',
      prompt_type: 'instruction',
      language: 'en',
      is_default: false,
    }

    const setEditingPromptData = (updater: any) => {
      if (typeof updater === 'function') {
        editingPromptData = updater(editingPromptData)
      } else {
        editingPromptData = updater
      }
    }

    // Simulate the onChange handler
    const handlePromptTypeChange = (value: string) => {
      setEditingPromptData((prev: any) => ({ ...prev, prompt_type: value }))
    }

    // Initial state
    expect(editingPromptData.prompt_type).toBe('instruction')

    // Change to system
    handlePromptTypeChange('system')
    expect(editingPromptData.prompt_type).toBe('system')

    // Verify other fields are preserved
    expect(editingPromptData.prompt_name).toBe('Test Prompt')
    expect(editingPromptData.prompt_text).toBe('Test text')
    expect(editingPromptData.language).toBe('en')
    expect(editingPromptData.is_default).toBe(false)
  })

  test('should handle type casting correctly', () => {
    // Test the type casting pattern used in the actual code
    const validTypes = ['evaluation', 'instruction', 'system'] as const
    type PromptType = (typeof validTypes)[number]

    const isValidPromptType = (value: string): value is PromptType => {
      return validTypes.includes(value as PromptType)
    }

    // Test valid types
    expect(isValidPromptType('evaluation')).toBe(true)
    expect(isValidPromptType('instruction')).toBe(true)
    expect(isValidPromptType('system')).toBe(true)

    // Test invalid types
    expect(isValidPromptType('invalid')).toBe(false)
    expect(isValidPromptType('')).toBe(false)
  })
})

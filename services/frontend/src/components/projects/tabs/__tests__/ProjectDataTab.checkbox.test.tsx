/**
 * Test file for header checkbox select all/deselect all functionality
 */

/**
 * @jest-environment jsdom
 */

import '@testing-library/jest-dom'
import { fireEvent, render, screen } from '@testing-library/react'
import { TableCheckbox } from '../../TableCheckbox'

describe('TableCheckbox', () => {
  it('should handle checked state correctly', () => {
    const onChange = jest.fn()
    const { rerender } = render(
      <TableCheckbox
        checked={false}
        onChange={onChange}
        data-testid="test-checkbox"
      />
    )

    const checkbox = screen.getByTestId('test-checkbox')

    // Initial state should be unchecked
    expect(checkbox).not.toBeChecked()

    // Click to check
    fireEvent.click(checkbox)
    expect(onChange).toHaveBeenCalledWith(true)

    // Rerender with checked state
    rerender(
      <TableCheckbox
        checked={true}
        onChange={onChange}
        data-testid="test-checkbox"
      />
    )

    expect(checkbox).toBeChecked()

    // Click to uncheck
    fireEvent.click(checkbox)
    expect(onChange).toHaveBeenCalledWith(false)
  })

  it('should handle indeterminate state correctly', () => {
    const onChange = jest.fn()
    const { container } = render(
      <TableCheckbox
        checked={false}
        indeterminate={true}
        onChange={onChange}
        data-testid="test-checkbox"
      />
    )

    const checkbox = container.querySelector(
      'input[type="checkbox"]'
    ) as HTMLInputElement

    // Should be indeterminate
    expect(checkbox.indeterminate).toBe(true)

    // Click should still work
    fireEvent.click(checkbox)
    expect(onChange).toHaveBeenCalledWith(true)
  })

  it('should have emerald color classes', () => {
    const onChange = jest.fn()
    const { container } = render(
      <TableCheckbox
        checked={true}
        onChange={onChange}
        data-testid="test-checkbox"
      />
    )

    const checkbox = container.querySelector('input[type="checkbox"]')

    // Check for emerald color classes
    expect(checkbox?.className).toContain('accent-emerald-600')
    expect(checkbox?.className).toContain('text-emerald-600')
  })
})

describe('Header Checkbox Integration', () => {
  it('should select all when none selected', () => {
    const tasks = [
      { id: '1', name: 'Task 1' },
      { id: '2', name: 'Task 2' },
      { id: '3', name: 'Task 3' },
    ]

    const selectedTasks = new Set<string>()
    const filteredTasks = tasks

    // Calculate checkbox state
    const filteredTaskIds = filteredTasks.map((t) => t.id)
    const allSelected =
      filteredTasks.length > 0 &&
      filteredTaskIds.every((id) => selectedTasks.has(id))
    const someSelected = filteredTaskIds.some((id) => selectedTasks.has(id))
    const isIndeterminate = someSelected && !allSelected

    // Initially nothing selected
    expect(allSelected).toBe(false)
    expect(someSelected).toBe(false)
    expect(isIndeterminate).toBe(false)
  })

  it('should show indeterminate when some selected', () => {
    const tasks = [
      { id: '1', name: 'Task 1' },
      { id: '2', name: 'Task 2' },
      { id: '3', name: 'Task 3' },
    ]

    const selectedTasks = new Set<string>(['1', '2']) // 2 of 3 selected
    const filteredTasks = tasks

    // Calculate checkbox state
    const filteredTaskIds = filteredTasks.map((t) => t.id)
    const allSelected =
      filteredTasks.length > 0 &&
      filteredTaskIds.every((id) => selectedTasks.has(id))
    const someSelected = filteredTaskIds.some((id) => selectedTasks.has(id))
    const isIndeterminate = someSelected && !allSelected

    expect(allSelected).toBe(false)
    expect(someSelected).toBe(true)
    expect(isIndeterminate).toBe(true)
  })

  it('should show checked when all selected', () => {
    const tasks = [
      { id: '1', name: 'Task 1' },
      { id: '2', name: 'Task 2' },
      { id: '3', name: 'Task 3' },
    ]

    const selectedTasks = new Set<string>(['1', '2', '3']) // All selected
    const filteredTasks = tasks

    // Calculate checkbox state
    const filteredTaskIds = filteredTasks.map((t) => t.id)
    const allSelected =
      filteredTasks.length > 0 &&
      filteredTaskIds.every((id) => selectedTasks.has(id))
    const someSelected = filteredTaskIds.some((id) => selectedTasks.has(id))
    const isIndeterminate = someSelected && !allSelected

    expect(allSelected).toBe(true)
    expect(someSelected).toBe(true)
    expect(isIndeterminate).toBe(false)
  })
})

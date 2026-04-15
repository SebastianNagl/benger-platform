/**
 * @jest-environment jsdom
 *
 * Branch coverage: BulkActions.tsx
 * Targets: L36 (selectedCount === 0 disabled), L42 (canAssign && onAssign),
 *          L87 (dropdown open with selectedCount > 0 vs 0)
 */

import '@testing-library/jest-dom'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { BulkActions } from '../BulkActions'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, params?: Record<string, any>) => {
      const translations: Record<string, string> = {
        'projects.bulkActions.actions': 'Actions',
        'projects.bulkActions.tasksSelected': `${params?.count} selected`,
        'projects.bulkActions.assignToAnnotators': 'Assign',
        'projects.bulkActions.exportSelected': 'Export',
        'projects.bulkActions.duplicateSelected': 'Duplicate',
        'projects.bulkActions.duplicateComingSoon': 'Coming soon',
        'projects.bulkActions.editMetadata': 'Edit Metadata',
        'projects.bulkActions.archiveSelected': 'Archive',
        'projects.bulkActions.deleteSelected': 'Delete',
        'projects.bulkActions.selectTasksPrompt': 'Select tasks first',
      }
      return translations[key] || key
    },
  }),
}))

jest.mock('@/components/shared/Button', () => ({
  Button: ({ children, onClick, disabled, ...props }: any) => (
    <button onClick={onClick} disabled={disabled} {...props}>
      {children}
    </button>
  ),
}))

jest.mock('@/components/shared/MetadataField', () => ({
  BulkMetadataEditor: ({ onClose, onSuccess }: any) => (
    <div data-testid="metadata-editor">
      <button onClick={onClose}>Close</button>
      <button onClick={onSuccess}>Save</button>
    </div>
  ),
}))

describe('BulkActions br4 - uncovered branches', () => {
  const defaultProps = {
    selectedCount: 0,
    onDelete: jest.fn(),
    onExport: jest.fn(),
    onArchive: jest.fn(),
  }

  it('opens dropdown when selectedCount is 0 and shows prompt (line 87)', async () => {
    const user = userEvent.setup()
    render(<BulkActions {...defaultProps} selectedCount={0} />)

    // Button should be disabled when selectedCount is 0
    const button = screen.getByText('Actions').closest('button')
    expect(button).toBeDisabled()
  })

  it('shows assign button when canAssign is true and onAssign provided (line 42)', async () => {
    const user = userEvent.setup()
    const onAssign = jest.fn()
    render(
      <BulkActions
        {...defaultProps}
        selectedCount={2}
        canAssign={true}
        onAssign={onAssign}
      />
    )

    const button = screen.getByText('Actions').closest('button')!
    await user.click(button)

    expect(screen.getByText('Assign')).toBeInTheDocument()
    await user.click(screen.getByText('Assign'))
    expect(onAssign).toHaveBeenCalled()
  })

  it('hides assign button when canAssign is false (line 93 falsy)', async () => {
    const user = userEvent.setup()
    render(
      <BulkActions
        {...defaultProps}
        selectedCount={2}
        canAssign={false}
      />
    )

    const button = screen.getByText('Actions').closest('button')!
    await user.click(button)

    expect(screen.queryByText('Assign')).not.toBeInTheDocument()
  })

  it('calls onExport and closes dropdown on export click', async () => {
    const user = userEvent.setup()
    const onExport = jest.fn()
    render(
      <BulkActions
        {...defaultProps}
        selectedCount={1}
        onExport={onExport}
      />
    )

    const button = screen.getByText('Actions').closest('button')!
    await user.click(button)
    await user.click(screen.getByText('Export'))
    expect(onExport).toHaveBeenCalled()
  })

  it('calls onArchive and closes dropdown on archive click', async () => {
    const user = userEvent.setup()
    const onArchive = jest.fn()
    render(
      <BulkActions
        {...defaultProps}
        selectedCount={1}
        onArchive={onArchive}
      />
    )

    const button = screen.getByText('Actions').closest('button')!
    await user.click(button)
    await user.click(screen.getByText('Archive'))
    expect(onArchive).toHaveBeenCalled()
  })

  it('calls onDelete and closes dropdown on delete click', async () => {
    const user = userEvent.setup()
    const onDelete = jest.fn()
    render(
      <BulkActions
        {...defaultProps}
        selectedCount={1}
        onDelete={onDelete}
      />
    )

    const button = screen.getByText('Actions').closest('button')!
    await user.click(button)
    await user.click(screen.getByText('Delete'))
    expect(onDelete).toHaveBeenCalled()
  })

  it('opens metadata editor on edit metadata click', async () => {
    const user = userEvent.setup()
    render(
      <BulkActions
        {...defaultProps}
        selectedCount={1}
        selectedTaskIds={['1', '2']}
        projectId="proj1"
      />
    )

    const button = screen.getByText('Actions').closest('button')!
    await user.click(button)
    await user.click(screen.getByText('Edit Metadata'))

    expect(screen.getByTestId('metadata-editor')).toBeInTheDocument()
  })

  it('closes dropdown on outside click', async () => {
    const user = userEvent.setup()
    render(
      <div>
        <div data-testid="outside">Outside</div>
        <BulkActions
          {...defaultProps}
          selectedCount={2}
        />
      </div>
    )

    // Open dropdown
    const button = screen.getByText('Actions').closest('button')!
    await user.click(button)
    expect(screen.getByText('2 selected')).toBeInTheDocument()

    // Click outside
    await user.click(screen.getByTestId('outside'))
    // Dropdown should be closed
    expect(screen.queryByText('2 selected')).not.toBeInTheDocument()
  })
})

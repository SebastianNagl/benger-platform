/**
 * @jest-environment jsdom
 *
 * The projects list offers the async full-export formats (defect 11): the
 * docs recommend NDJSON gzip for moving a project, and before this the UI
 * only had the synchronous ZIP.
 */
import { ProjectBulkActions } from '@/components/projects/ProjectBulkActions'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

jest.mock('@/contexts/I18nContext', () =>
  require('@/test-utils/i18nMock').i18nMock('en'),
)

describe('ProjectBulkActions async export', () => {
  it('offers NDJSON gzip and JSON and reports the chosen format', async () => {
    const user = userEvent.setup()
    const onAsyncExport = jest.fn()
    render(
      <ProjectBulkActions
        selectedCount={2}
        onDelete={jest.fn()}
        onFullExport={jest.fn()}
        onAsyncExport={onAsyncExport}
      />,
    )
    await user.click(screen.getByTestId('projects-bulk-actions-button'))
    expect(
      screen.getByTestId('projects-bulk-export-comprehensive-option'),
    ).toHaveTextContent('Export as JSON (one file per project)')
    await user.click(
      screen.getByTestId('projects-bulk-export-ndjson_gz-option'),
    )
    expect(onAsyncExport).toHaveBeenCalledWith('ndjson_gz')
  })

  it('hides the async formats without a handler', async () => {
    const user = userEvent.setup()
    render(<ProjectBulkActions selectedCount={1} onDelete={jest.fn()} />)
    await user.click(screen.getByTestId('projects-bulk-actions-button'))
    expect(
      screen.queryByTestId('projects-bulk-export-ndjson_gz-option'),
    ).not.toBeInTheDocument()
  })
})

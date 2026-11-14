import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { TaskFieldSelector } from '../TaskFieldSelector'

jest.mock('@/contexts/I18nContext', () =>
  require('@/test-utils/i18nMock').i18nMock('en'),
)

// jest.config maps the alias to the native-select mock; these tests drive
// the real searchable list.
jest.mock('@/components/shared/Select', () => jest.requireActual('../Select'))

jest.mock('@/lib/api/projects', () => ({
  projectsAPI: {
    getTaskFields: jest.fn().mockResolvedValue({ fields: [] }),
  },
}))

jest.mock('../LoadingSpinner', () => ({
  LoadingSpinner: ({ size }: any) => (
    <div data-testid="loading-spinner" data-size={size}>
      Loading...
    </div>
  ),
}))

const field = (path: string, display_name: string, is_nested = false) => ({
  path,
  display_name,
  sample_value: `sample of ${display_name}`,
  data_type: 'string',
  is_nested,
})

const FIELDS = [
  field('$title', 'Title'),
  field('$context', 'Context'),
  field('$meta.zivil', 'Zivilrecht', true),
  field('$meta.aerzte', 'Ärzte', true),
  field('$answer', 'Answer'),
]

describe('TaskFieldSelector', () => {
  const defaultProps = {
    projectId: 'proj-1',
    value: '',
    onChange: jest.fn(),
  }
  const api = () => require('@/lib/api/projects').projectsAPI

  beforeEach(() => {
    api().getTaskFields.mockReset()
    defaultProps.onChange = jest.fn()
  })

  const renderLoaded = async (
    props: Partial<typeof defaultProps> & any = {},
  ) => {
    api().getTaskFields.mockResolvedValue({ fields: FIELDS })
    render(<TaskFieldSelector {...defaultProps} {...props} />)
    return await screen.findByRole('button', { name: /select a field|\$/i })
  }

  it('shows loading state while fetching fields', () => {
    api().getTaskFields.mockReturnValue(new Promise(() => {}))
    render(<TaskFieldSelector {...defaultProps} />)
    expect(screen.getByTestId('loading-spinner')).toBeInTheDocument()
    expect(screen.getByText('Loading fields...')).toBeInTheDocument()
  })

  it('does not fetch when projectId is empty', () => {
    api().getTaskFields.mockResolvedValue({ fields: [] })
    render(<TaskFieldSelector {...defaultProps} projectId="" />)
    expect(api().getTaskFields).not.toHaveBeenCalled()
  })

  it('applies loading className', () => {
    api().getTaskFields.mockReturnValue(new Promise(() => {}))
    const { container } = render(
      <TaskFieldSelector {...defaultProps} className="my-class" />,
    )
    expect(container.querySelector('.my-class')).toBeInTheDocument()
  })

  it('calls getTaskFields with projectId', () => {
    api().getTaskFields.mockResolvedValue({ fields: [] })
    render(<TaskFieldSelector {...defaultProps} projectId="my-proj" />)
    expect(api().getTaskFields).toHaveBeenCalledWith('my-proj')
  })

  it('shows the fetch error', async () => {
    api().getTaskFields.mockRejectedValue(new Error('boom'))
    jest.spyOn(console, 'error').mockImplementation(() => {})
    render(<TaskFieldSelector {...defaultProps} />)
    expect(await screen.findByText(/failed/i)).toBeInTheDocument()
  })

  it('lists top-level and nested fields, each group sorted by path', async () => {
    await userEvent.click(await renderLoaded())
    const listbox = screen.getByRole('listbox')
    expect(
      Array.from(listbox.children).map(
        (child) =>
          child.querySelector('code')?.textContent ?? child.textContent,
      ),
    ).toEqual([
      'Top-level Fields',
      '$answer',
      '$context',
      '$title',
      'Nested Fields',
      '$meta.aerzte',
      '$meta.zivil',
    ])
  })

  it('filters by path or display name and picks the match', async () => {
    await userEvent.click(await renderLoaded())
    await userEvent.type(screen.getByRole('combobox'), 'arzte')
    const options = within(screen.getByRole('listbox')).getAllByRole('option')
    expect(options).toHaveLength(1)
    expect(screen.queryByText('Top-level Fields')).not.toBeInTheDocument()
    await userEvent.keyboard('{Enter}')
    expect(defaultProps.onChange).toHaveBeenCalledWith('$meta.aerzte')
  })

  it('shows the selected field path and name on the trigger', async () => {
    api().getTaskFields.mockResolvedValue({ fields: FIELDS })
    render(<TaskFieldSelector {...defaultProps} value="$context" />)
    const trigger = await screen.findByRole('button', { name: /\$context/ })
    expect(trigger).toHaveTextContent('Context')
  })

  it('says when the project has no fields', async () => {
    api().getTaskFields.mockResolvedValue({ fields: [] })
    render(<TaskFieldSelector {...defaultProps} />)
    await userEvent.click(
      await screen.findByRole('button', { name: /select a field/i }),
    )
    expect(screen.getByText('No fields found in task data')).toBeInTheDocument()
  })

  it('switches to manual entry and submits a $-prefixed path', async () => {
    await userEvent.click(await renderLoaded({ allowManualEntry: true }))
    await userEvent.click(screen.getByText('Enter custom path...'))
    const input = await screen.findByPlaceholderText('e.g., $context.field')
    await userEvent.type(input, 'custom.path{Enter}')
    expect(defaultProps.onChange).toHaveBeenCalledWith('$custom.path')
    await waitFor(() =>
      expect(
        screen.getByRole('button', { name: /select a field/i }),
      ).toBeInTheDocument(),
    )
  })
})

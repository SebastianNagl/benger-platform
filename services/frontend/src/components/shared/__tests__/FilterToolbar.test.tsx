import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { FilterToolbar } from '../FilterToolbar'

function Harness({
  initialSearch = '',
  hasActiveFilters = false,
  searchHidden = false,
  withFilterField = true,
  onClearFilters,
  clearLabel,
}: {
  initialSearch?: string
  hasActiveFilters?: boolean
  searchHidden?: boolean
  withFilterField?: boolean
  onClearFilters?: () => void
  clearLabel?: string
}) {
  const [search, setSearch] = useState(initialSearch)
  const [status, setStatus] = useState('all')
  return (
    <FilterToolbar
      searchValue={search}
      onSearchChange={setSearch}
      searchPlaceholder="Search…"
      hasActiveFilters={hasActiveFilters}
      searchHidden={searchHidden}
      onClearFilters={onClearFilters}
      clearLabel={clearLabel}
      rightExtras={<span>{`q=${search}`}</span>}
    >
      {withFilterField && (
        <FilterToolbar.Field label="Status">
          <select
            aria-label="Status"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
          >
            <option value="all">All</option>
            <option value="active">Active</option>
          </select>
        </FilterToolbar.Field>
      )}
    </FilterToolbar>
  )
}

describe('FilterToolbar', () => {
  it('renders the search and filters toggle buttons', () => {
    render(<Harness />)
    expect(screen.getByTitle('Search')).toBeInTheDocument()
    expect(screen.getByTitle('Filters')).toBeInTheDocument()
  })

  it('reveals the search input only after clicking the search toggle', async () => {
    const user = userEvent.setup()
    render(<Harness />)

    expect(screen.queryByPlaceholderText('Search…')).not.toBeInTheDocument()

    await user.click(screen.getByTitle('Search'))

    expect(screen.getByPlaceholderText('Search…')).toBeInTheDocument()
  })

  it('reveals the filter panel only after clicking the filters toggle', async () => {
    const user = userEvent.setup()
    render(<Harness />)

    expect(screen.queryByLabelText('Status')).not.toBeInTheDocument()

    await user.click(screen.getByTitle('Filters'))

    expect(screen.getByLabelText('Status')).toBeInTheDocument()
  })

  it('hides the filters toggle when no fields are provided', () => {
    render(<Harness withFilterField={false} />)
    expect(screen.queryByTitle('Filters')).not.toBeInTheDocument()
  })

  it('hides the search toggle when searchHidden is true', () => {
    render(<Harness searchHidden />)
    expect(screen.queryByTitle('Search')).not.toBeInTheDocument()
  })

  it('shows the active dot when hasActiveFilters is true', () => {
    const { container } = render(<Harness hasActiveFilters />)
    // Active dot has bg-emerald-500 and is the only element with that exact rounded-full small dot.
    const dots = container.querySelectorAll('span.bg-emerald-500.rounded-full')
    expect(dots.length).toBeGreaterThan(0)
  })

  it('shows a search active dot when searchValue is non-empty', () => {
    const { container } = render(<Harness initialSearch="foo" />)
    const dots = container.querySelectorAll('span.bg-emerald-500.rounded-full')
    expect(dots.length).toBeGreaterThan(0)
  })

  it('forwards typed search input to onSearchChange', async () => {
    const user = userEvent.setup()
    render(<Harness />)

    await user.click(screen.getByTitle('Search'))
    const input = screen.getByPlaceholderText('Search…')
    await user.type(input, 'hello')

    expect(screen.getByText('q=hello')).toBeInTheDocument()
  })

  describe('clear-filters X pill', () => {
    it('does not render when onClearFilters is not provided', () => {
      render(<Harness hasActiveFilters />)
      expect(screen.queryByTitle('Clear filters')).not.toBeInTheDocument()
    })

    it('renders disabled when onClearFilters is provided but no filters are active', () => {
      render(<Harness onClearFilters={() => {}} />)
      const clearButton = screen.getByTitle('Clear filters')
      expect(clearButton).toBeInTheDocument()
      expect(clearButton).toBeDisabled()
    })

    it('renders enabled when hasActiveFilters is true', () => {
      render(<Harness hasActiveFilters onClearFilters={() => {}} />)
      const clearButton = screen.getByTitle('Clear filters')
      expect(clearButton).toBeEnabled()
    })

    it('uses a custom clearLabel for title and aria-label when provided', () => {
      render(
        <Harness
          hasActiveFilters
          onClearFilters={() => {}}
          clearLabel="Reset everything"
        />
      )
      expect(screen.getByTitle('Reset everything')).toBeInTheDocument()
      expect(
        screen.getByRole('button', { name: 'Reset everything' })
      ).toBeInTheDocument()
    })

    it('calls onClearFilters when clicked', async () => {
      const user = userEvent.setup()
      const onClearFilters = jest.fn()
      render(<Harness hasActiveFilters onClearFilters={onClearFilters} />)

      await user.click(screen.getByTitle('Clear filters'))

      expect(onClearFilters).toHaveBeenCalledTimes(1)
    })

    it('does not call onClearFilters when the button is disabled', async () => {
      const user = userEvent.setup()
      const onClearFilters = jest.fn()
      render(<Harness onClearFilters={onClearFilters} />)

      await user.click(screen.getByTitle('Clear filters'))

      expect(onClearFilters).not.toHaveBeenCalled()
    })
  })
})

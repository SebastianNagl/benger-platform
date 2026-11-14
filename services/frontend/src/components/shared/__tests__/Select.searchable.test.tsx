/**
 * @jest-environment jsdom
 *
 * The searchable mode of the shared Select, which every dropdown of loaded
 * data uses: alphabetical German order, pinned entries first, a search field,
 * keyboard use, groups, disabled options and multi-select.
 */
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import {
  Select,
  SelectContent,
  SelectGroupLabel,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../Select'

jest.mock('@/contexts/I18nContext', () =>
  require('@/test-utils/i18nMock').i18nMock('en'),
)

const ORGS = [
  { id: 'z', name: 'Zeppelin Uni' },
  { id: 'b', name: 'bonn' },
  { id: 'ae', name: 'Ärztekammer' },
  { id: 'a', name: 'Aachen' },
  { id: 'c', name: 'Coburg' },
]

function OrgSelect({
  initial = '',
  onChange = jest.fn(),
  disabledId,
}: {
  initial?: string
  onChange?: jest.Mock
  disabledId?: string
}) {
  const [value, setValue] = useState(initial)
  return (
    <div>
      <Select
        searchable
        value={value}
        onValueChange={(next) => {
          setValue(next)
          onChange(next)
        }}
      >
        <SelectTrigger data-testid="trigger">
          <SelectValue placeholder="Pick an organization" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem pinned value="">
            All organizations
          </SelectItem>
          {ORGS.map((org) => (
            <SelectItem
              key={org.id}
              value={org.id}
              disabled={org.id === disabledId}
            >
              {org.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <p>outside</p>
    </div>
  )
}

const open = async () => {
  await userEvent.click(screen.getByTestId('trigger'))
  return screen.getByRole('listbox')
}
const optionLabels = (listbox: HTMLElement) =>
  within(listbox)
    .queryAllByRole('option')
    .map((option) => option.textContent)

describe('searchable Select', () => {
  it('shows the label of the empty-value entry instead of the placeholder', () => {
    render(<OrgSelect />)
    expect(screen.getByTestId('trigger')).toHaveTextContent('All organizations')
  })

  it('shows the selected label on the trigger', () => {
    render(<OrgSelect initial="ae" />)
    expect(screen.getByTestId('trigger')).toHaveTextContent('Ärztekammer')
  })

  it('lists options alphabetically with umlauts in place and pinned first', async () => {
    render(<OrgSelect />)
    expect(optionLabels(await open())).toEqual([
      'All organizations',
      'Aachen',
      'Ärztekammer',
      'bonn',
      'Coburg',
      'Zeppelin Uni',
    ])
  })

  it('focuses the search field, which filters by label ignoring umlauts and case', async () => {
    render(<OrgSelect />)
    const listbox = await open()
    const search = screen.getByRole('combobox')
    expect(search).toHaveFocus()
    expect(search).toHaveAttribute('placeholder', 'Search...')

    await userEvent.type(search, 'ARZT')
    expect(optionLabels(listbox)).toEqual(['Ärztekammer'])

    await userEvent.clear(search)
    await userEvent.type(search, 'n')
    expect(optionLabels(listbox)).toEqual([
      'All organizations',
      'Aachen',
      'bonn',
      'Zeppelin Uni',
    ])
  })

  it('says so when nothing matches', async () => {
    render(<OrgSelect />)
    const listbox = await open()
    await userEvent.type(screen.getByRole('combobox'), 'xyz')
    expect(optionLabels(listbox)).toEqual([])
    expect(screen.getByText('No matches')).toBeInTheDocument()
  })

  it('selects a clicked option and closes', async () => {
    const onChange = jest.fn()
    render(<OrgSelect onChange={onChange} />)
    await open()
    await userEvent.click(screen.getByRole('option', { name: 'Coburg' }))
    expect(onChange).toHaveBeenCalledWith('c')
    await waitFor(() =>
      expect(screen.queryByRole('listbox')).not.toBeInTheDocument(),
    )
    expect(screen.getByTestId('trigger')).toHaveTextContent('Coburg')
  })

  it('does not report re-picking the current option as a change', async () => {
    const onChange = jest.fn()
    render(<OrgSelect initial="c" onChange={onChange} />)
    await open()
    await userEvent.click(screen.getByRole('option', { name: 'Coburg' }))
    expect(onChange).not.toHaveBeenCalled()
  })

  it('selects by keyboard: arrows move through the sorted list, Enter picks', async () => {
    const onChange = jest.fn()
    render(<OrgSelect onChange={onChange} />)
    await open()
    // First ArrowDown activates "All organizations", then "Aachen", "Ärztekammer".
    await userEvent.keyboard('{ArrowDown}{ArrowDown}{ArrowDown}{Enter}')
    expect(onChange).toHaveBeenCalledWith('ae')
    await waitFor(() => expect(screen.getByTestId('trigger')).toHaveFocus())
  })

  it('picks the first match of a search with Enter', async () => {
    const onChange = jest.fn()
    render(<OrgSelect onChange={onChange} />)
    await open()
    await userEvent.type(screen.getByRole('combobox'), 'co')
    await userEvent.keyboard('{Enter}')
    expect(onChange).toHaveBeenCalledWith('c')
  })

  it('opens from the focused trigger by arrow key or a typed letter', async () => {
    render(<OrgSelect />)
    screen.getByTestId('trigger').focus()
    await userEvent.keyboard('{ArrowDown}')
    expect(screen.getByRole('listbox')).toBeInTheDocument()
    await userEvent.keyboard('{Escape}')
    await waitFor(() =>
      expect(screen.queryByRole('listbox')).not.toBeInTheDocument(),
    )

    screen.getByTestId('trigger').focus()
    await userEvent.keyboard('p')
    expect(screen.getByRole('combobox')).toHaveValue('p')
    expect(optionLabels(screen.getByRole('listbox'))).toEqual(['Zeppelin Uni'])
  })

  it('closes on Escape and on an outside click without selecting', async () => {
    const onChange = jest.fn()
    render(<OrgSelect onChange={onChange} />)
    await open()
    await userEvent.keyboard('{Escape}')
    await waitFor(() =>
      expect(screen.queryByRole('listbox')).not.toBeInTheDocument(),
    )
    await open()
    await userEvent.click(screen.getByText('outside'))
    await waitFor(() =>
      expect(screen.queryByRole('listbox')).not.toBeInTheDocument(),
    )
    expect(onChange).not.toHaveBeenCalled()
  })

  it('starts with an empty search on every open', async () => {
    render(<OrgSelect />)
    await open()
    await userEvent.type(screen.getByRole('combobox'), 'bonn')
    // A single Escape closes even after typing, and focus goes back.
    await userEvent.keyboard('{Escape}')
    await waitFor(() =>
      expect(screen.queryByRole('listbox')).not.toBeInTheDocument(),
    )
    expect(screen.getByTestId('trigger')).toHaveFocus()
    await open()
    expect(screen.getByRole('combobox')).toHaveValue('')
  })

  it('keeps disabled options visible but not selectable', async () => {
    const onChange = jest.fn()
    render(<OrgSelect onChange={onChange} disabledId="b" />)
    await open()
    const bonn = screen.getByRole('option', { name: 'bonn' })
    expect(bonn).toHaveAttribute('aria-disabled', 'true')
    await userEvent.click(bonn)
    expect(onChange).not.toHaveBeenCalled()
  })

  it('does not open when disabled', async () => {
    render(
      <Select searchable disabled value="" onValueChange={jest.fn()}>
        <SelectTrigger data-testid="trigger">
          <SelectValue placeholder="Pick" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="a">A</SelectItem>
        </SelectContent>
      </Select>,
    )
    expect(screen.getByTestId('trigger')).toBeDisabled()
    expect(screen.getByTestId('trigger')).toHaveTextContent('Pick')
  })

  it('sorts within groups, and hides a group heading the search empties', async () => {
    render(
      <Select
        searchable
        value=""
        onValueChange={jest.fn()}
        emptyMessage="Nothing"
      >
        <SelectTrigger data-testid="trigger">
          <SelectValue placeholder="Judge" />
        </SelectTrigger>
        <SelectContent>
          <SelectGroupLabel>Official</SelectGroupLabel>
          <SelectItem value="o2">Sonnet</SelectItem>
          <SelectItem value="o1">Haiku</SelectItem>
          <SelectGroupLabel>Custom</SelectGroupLabel>
          <SelectItem value="c1" textValue="Mistral (local)">
            Mistral <span>(local)</span>
          </SelectItem>
          <SelectItem value="c0">Aleph</SelectItem>
        </SelectContent>
      </Select>,
    )
    const listbox = await open()
    expect(
      Array.from(listbox.children).map((child) => child.textContent),
    ).toEqual([
      'Official',
      'Haiku',
      'Sonnet',
      'Custom',
      'Aleph',
      'Mistral (local)',
    ])

    await userEvent.type(screen.getByRole('combobox'), 'local')
    expect(
      Array.from(listbox.children).map((child) => child.textContent),
    ).toEqual(['Custom', 'Mistral (local)'])

    await userEvent.clear(screen.getByRole('combobox'))
    await userEvent.type(screen.getByRole('combobox'), 'qqq')
    expect(screen.getByText('Nothing')).toBeInTheDocument()
  })

  it('uses the given search placeholder', async () => {
    render(
      <Select
        searchable
        value=""
        onValueChange={jest.fn()}
        searchPlaceholder="Find a project"
      >
        <SelectTrigger data-testid="trigger">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="a">A</SelectItem>
        </SelectContent>
      </Select>,
    )
    await open()
    expect(screen.getByRole('combobox')).toHaveAttribute(
      'placeholder',
      'Find a project',
    )
  })
})

describe('multi-select Select', () => {
  function Multi({ onChange = jest.fn() }: { onChange?: jest.Mock }) {
    const [value, setValue] = useState<string[]>([])
    return (
      <Select
        multiple
        value={value}
        onValueChange={(next) => {
          setValue(next)
          onChange(next)
        }}
      >
        <SelectTrigger data-testid="trigger">
          <SelectValue placeholder="All projects" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="p2">Zivilrecht</SelectItem>
          <SelectItem value="p1">Öffentliches Recht</SelectItem>
          <SelectItem value="p3">Strafrecht</SelectItem>
        </SelectContent>
      </Select>
    )
  }

  it('is searchable and sorted, toggles values and stays open', async () => {
    const onChange = jest.fn()
    render(<Multi onChange={onChange} />)
    expect(screen.getByTestId('trigger')).toHaveTextContent('All projects')
    const listbox = await open()
    expect(optionLabels(listbox)).toEqual([
      'Öffentliches Recht',
      'Strafrecht',
      'Zivilrecht',
    ])

    await userEvent.click(screen.getByRole('option', { name: 'Zivilrecht' }))
    expect(onChange).toHaveBeenLastCalledWith(['p2'])
    expect(screen.getByRole('listbox')).toBeInTheDocument()

    // "oe" finds "Ö" the way German is typed without umlauts.
    await userEvent.type(screen.getByRole('combobox'), 'oeff')
    await userEvent.keyboard('{Enter}')
    expect(onChange).toHaveBeenLastCalledWith(['p2', 'p1'])
    expect(
      within(listbox).getAllByRole('option', { selected: true }),
    ).toHaveLength(1)
  })

  it('lists the selected labels on a plain trigger', async () => {
    render(<Multi />)
    await open()
    await userEvent.click(screen.getByRole('option', { name: 'Strafrecht' }))
    await userEvent.click(screen.getByRole('option', { name: 'Zivilrecht' }))
    expect(screen.getByTestId('trigger')).toHaveTextContent(
      'Strafrecht, Zivilrecht',
    )

    await userEvent.click(screen.getByRole('option', { name: 'Strafrecht' }))
    expect(screen.getByTestId('trigger')).toHaveTextContent('Zivilrecht')
  })
})

describe('plain Select', () => {
  it('keeps the source order of fixed lists', async () => {
    render(
      <Select value="" onValueChange={jest.fn()}>
        <SelectTrigger data-testid="trigger">
          <SelectValue placeholder="Priority" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="low">Low</SelectItem>
          <SelectItem value="medium">Medium</SelectItem>
          <SelectItem value="high">High</SelectItem>
        </SelectContent>
      </Select>,
    )
    const listbox = await open()
    expect(optionLabels(listbox)).toEqual(['Low', 'Medium', 'High'])
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
  })
})

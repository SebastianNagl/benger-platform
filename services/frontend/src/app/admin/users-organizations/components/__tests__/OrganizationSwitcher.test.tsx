/**
 * Organizations page switcher (#385): alphabetical, searchable, and built on
 * Headless UI so it closes on Escape / outside click and works by keyboard.
 */
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import {
  OrganizationSwitcher,
  sortOrganizationsByName,
} from '../OrganizationSwitcher'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({ t: (key: string) => key }),
}))

const org = (id: string, name: string, description?: string) =>
  ({ id, name, description }) as any

const ORGS = [
  org('c', 'Coburg', 'Hochschule Coburg'),
  org('b', 'bonn'),
  org('z', 'Zeppelin Uni'),
  org('ae', 'Ärztekammer'),
  org('a', 'Aachen'),
]

function renderSwitcher(selected: any = null, onSelect: jest.Mock = jest.fn()) {
  render(
    <div>
      <OrganizationSwitcher
        organizations={ORGS}
        selectedOrganization={selected}
        onSelect={onSelect}
      />
      <p>outside</p>
    </div>,
  )
  return onSelect
}

const openSwitcher = async () => {
  await userEvent.click(screen.getByTestId('org-switcher-button'))
  return screen.getByRole('listbox')
}

const optionNames = (listbox: HTMLElement) =>
  within(listbox)
    .getAllByRole('option')
    .map((o) => o.querySelector('span')?.textContent)

describe('sortOrganizationsByName', () => {
  it('sorts case-insensitively with German collation', () => {
    expect(sortOrganizationsByName(ORGS).map((o) => o.name)).toEqual([
      'Aachen',
      'Ärztekammer',
      'bonn',
      'Coburg',
      'Zeppelin Uni',
    ])
  })

  it('does not mutate its input', () => {
    const input = [...ORGS]
    sortOrganizationsByName(input)
    expect(input).toEqual(ORGS)
  })
})

describe('OrganizationSwitcher', () => {
  it('shows the selected org on the trigger', () => {
    renderSwitcher(ORGS[0])
    expect(screen.getByTestId('org-switcher-button')).toHaveTextContent(
      'Coburg',
    )
  })

  it('shows the placeholder when nothing is selected', () => {
    renderSwitcher()
    expect(screen.getByTestId('org-switcher-button')).toHaveTextContent(
      'admin.organizations.selectOrganization',
    )
  })

  it('lists organizations alphabetically from unsorted input', async () => {
    renderSwitcher()
    const listbox = await openSwitcher()
    expect(optionNames(listbox)).toEqual([
      'Aachen',
      'Ärztekammer',
      'bonn',
      'Coburg',
      'Zeppelin Uni',
    ])
  })

  it('filters by name and description and keeps results sorted', async () => {
    renderSwitcher()
    const listbox = await openSwitcher()
    await userEvent.type(screen.getByRole('combobox'), 'hochschule')
    // Matches Coburg by its description only.
    expect(optionNames(listbox)).toEqual(['Coburg'])

    await userEvent.clear(screen.getByRole('combobox'))
    await userEvent.type(screen.getByRole('combobox'), 'N')
    expect(optionNames(listbox)).toEqual(['Aachen', 'bonn', 'Zeppelin Uni'])
  })

  it('shows the empty state when the search matches nothing', async () => {
    renderSwitcher()
    await openSwitcher()
    await userEvent.type(screen.getByRole('combobox'), 'xyz')
    expect(screen.queryAllByRole('option')).toHaveLength(0)
    expect(
      screen.getByText('admin.organizations.noOrganizations'),
    ).toBeInTheDocument()
  })

  it('marks the selected organization', async () => {
    renderSwitcher(ORGS[0])
    const listbox = await openSwitcher()
    const selected = within(listbox).getByRole('option', { selected: true })
    expect(selected).toHaveTextContent('Coburg')
    expect(selected.querySelector('.text-emerald-600')).not.toBeNull()
  })

  it('calls onSelect and closes when an option is clicked', async () => {
    const onSelect = renderSwitcher()
    await openSwitcher()
    await userEvent.click(screen.getByText('bonn'))
    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ id: 'b' }))
    await waitFor(() =>
      expect(screen.queryByRole('listbox')).not.toBeInTheDocument(),
    )
  })

  it('selects with arrow keys and Enter', async () => {
    const onSelect = renderSwitcher()
    await openSwitcher()
    await userEvent.keyboard('{ArrowDown}{ArrowDown}{Enter}')
    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ id: 'ae' }))
  })

  it('closes on Escape without selecting', async () => {
    const onSelect = renderSwitcher()
    await openSwitcher()
    await userEvent.keyboard('{Escape}')
    await waitFor(() =>
      expect(screen.queryByRole('listbox')).not.toBeInTheDocument(),
    )
    expect(onSelect).not.toHaveBeenCalled()
  })

  it('closes on an outside click', async () => {
    renderSwitcher()
    await openSwitcher()
    await userEvent.click(screen.getByText('outside'))
    await waitFor(() =>
      expect(screen.queryByRole('listbox')).not.toBeInTheDocument(),
    )
  })

  it('uses no indigo classes', async () => {
    renderSwitcher(ORGS[0])
    await openSwitcher()
    expect(document.body.innerHTML).not.toMatch(/indigo/)
  })
})

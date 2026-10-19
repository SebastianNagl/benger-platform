/**
 * @jest-environment jsdom
 *
 * FeatureFlagsAdmin (/admin/feature-flags): flags grouped by owner with the
 * master flag first, the three-way state control (with a confirmation before
 * a master flag goes off), the allowlist editor, rows no package registers
 * any more (marked, deletable) and the flag store refresh after every write.
 */
import '@testing-library/jest-dom'
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react'

import type {
  FeatureFlagAdminRow,
  FeatureFlagTarget,
} from '@/lib/api/featureFlags'
import {
  FeatureFlagsAdmin,
  groupFlags,
  targetLabel,
} from '../FeatureFlagsAdmin'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, vars?: Record<string, unknown>) =>
      vars ? `${key} ${JSON.stringify(vars)}` : key,
    locale: 'de',
  }),
}))

const mockAddToast = jest.fn()
jest.mock('@/components/shared/Toast', () => ({
  useToast: () => ({ addToast: mockAddToast, showToast: mockAddToast }),
}))
jest.mock('@/components/shared/Breadcrumb', () => ({
  Breadcrumb: () => <nav data-testid="breadcrumb" />,
}))
jest.mock('@/components/shared/ConfirmationDialog', () => ({
  ConfirmationDialog: (props: {
    isOpen: boolean
    title: string
    message: string
    confirmText?: string
    onConfirm: () => void
    onClose: () => void
  }) =>
    props.isOpen ? (
      <div role="dialog">
        <h2>{props.title}</h2>
        <p>{props.message}</p>
        <button onClick={props.onConfirm}>{props.confirmText}</button>
        <button onClick={props.onClose}>cancel</button>
      </div>
    ) : null,
}))

const mockGetOrganizations = jest.fn()
const mockGetAllUsers = jest.fn()
jest.mock('@/lib/api', () => ({
  __esModule: true,
  default: {
    getOrganizations: (...a: any[]) => mockGetOrganizations(...a),
    getAllUsers: (...a: any[]) => mockGetAllUsers(...a),
  },
}))

const mockList = jest.fn()
const mockSetState = jest.fn()
const mockAddTarget = jest.fn()
const mockRemoveTarget = jest.fn()
const mockRemove = jest.fn()
jest.mock('@/lib/api/featureFlags', () => ({
  featureFlagsAPI: {
    list: (...a: any[]) => mockList(...a),
    setState: (...a: any[]) => mockSetState(...a),
    addTarget: (...a: any[]) => mockAddTarget(...a),
    removeTarget: (...a: any[]) => mockRemoveTarget(...a),
    remove: (...a: any[]) => mockRemove(...a),
  },
}))

const mockRefresh = jest.fn()
jest.mock('@/lib/featureFlags', () => ({
  refreshFeatureFlags: (...a: any[]) => mockRefresh(...a),
}))

const userTarget: FeatureFlagTarget = {
  id: 't-user',
  kind: 'user',
  user_id: 'u1',
  organization_id: null,
  name: 'Erika Muster',
  pseudonym: 'Kluge Eule',
  email: 'erika@test.de',
  username: 'erika',
}
const orgTarget: FeatureFlagTarget = {
  id: 't-org',
  kind: 'organization',
  user_id: null,
  organization_id: 'org-a',
  name: 'Uni A',
  pseudonym: null,
  email: null,
  username: null,
}

function row(
  name: string,
  over: Partial<FeatureFlagAdminRow> = {},
): FeatureFlagAdminRow {
  return {
    name,
    description: `${name} description`,
    owner: 'platform',
    state: 'everyone',
    default_state: 'everyone',
    updated_at: null,
    targets: [],
    registered: true,
    is_master: false,
    ...over,
  }
}

function rows(): FeatureFlagAdminRow[] {
  return [
    row('rubric_generation', { owner: 'extended' }),
    row('stale_flag', { owner: 'extended', registered: false }),
    row('extension.extended', { owner: 'extended', is_master: true }),
    row('extension.compliance', {
      owner: 'compliance',
      is_master: true,
      state: 'allowlist',
      default_state: 'off',
      targets: [userTarget, orgTarget],
    }),
    row('public_api', { updated_at: '2026-10-19T08:30:00Z' }),
  ]
}

async function renderLoaded() {
  render(<FeatureFlagsAdmin />)
  await screen.findByTestId('ff-row-public_api')
}

beforeEach(() => {
  jest.clearAllMocks()
  mockList.mockResolvedValue(rows())
  mockGetOrganizations.mockResolvedValue([
    { id: 'org-a', name: 'a', display_name: 'Uni A' },
    { id: 'org-b', name: 'b', display_name: 'Uni B' },
  ])
  mockGetAllUsers.mockResolvedValue([])
})

describe('groupFlags', () => {
  it('puts platform first, packages by name, master first, unregistered last', () => {
    const groups = groupFlags(rows())
    expect(groups.map((g) => g.owner)).toEqual([
      'platform',
      'compliance',
      'extended',
    ])
    expect(groups[2].rows.map((r) => r.name)).toEqual([
      'extension.extended',
      'rubric_generation',
      'stale_flag',
    ])
  })

  it('treats a missing owner as platform', () => {
    const groups = groupFlags([row('x', { owner: '' })])
    expect(groups[0].owner).toBe('platform')
  })
})

describe('FeatureFlagsAdmin', () => {
  it('renders the groups in order with badges and the change date', async () => {
    await renderLoaded()
    const sections = screen
      .getAllByTestId(/^ff-group-/)
      .map((el) => el.getAttribute('data-testid'))
    expect(sections).toEqual([
      'ff-group-platform',
      'ff-group-compliance',
      'ff-group-extended',
    ])
    const extended = screen.getByTestId('ff-group-extended')
    const names = within(extended)
      .getAllByTestId(/^ff-row-/)
      .map((el) => el.getAttribute('data-testid'))
    expect(names).toEqual([
      'ff-row-extension.extended',
      'ff-row-rubric_generation',
      'ff-row-stale_flag',
    ])
    expect(
      screen.getByTestId('ff-master-extension.extended'),
    ).toBeInTheDocument()
    expect(screen.getByTestId('ff-unregistered-stale_flag')).toBeInTheDocument()
    expect(
      within(screen.getByTestId('ff-row-public_api')).getByText(
        /admin\.featureFlagsConsole\.updatedAt/,
      ),
    ).toBeInTheDocument()
    expect(
      screen.getByText('admin.featureFlagsConsole.groupPlatform'),
    ).toBeInTheDocument()
  })

  it('shows the load error', async () => {
    mockList.mockRejectedValueOnce(new Error('kaputt'))
    render(<FeatureFlagsAdmin />)
    expect(await screen.findByTestId('feature-flags-error')).toHaveTextContent(
      'kaputt',
    )
  })

  it('saves a normal state change at once and refreshes the store', async () => {
    mockSetState.mockResolvedValueOnce(
      row('rubric_generation', { owner: 'extended', state: 'off' }),
    )
    await renderLoaded()
    fireEvent.click(screen.getByTestId('ff-state-rubric_generation-off'))
    await waitFor(() =>
      expect(mockSetState).toHaveBeenCalledWith('rubric_generation', 'off'),
    )
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    await waitFor(() => expect(mockRefresh).toHaveBeenCalled())
    expect(
      screen.getByTestId('ff-state-rubric_generation-off'),
    ).toHaveAttribute('aria-checked', 'true')
  })

  it('asks before switching a master flag off and saves only on confirm', async () => {
    mockSetState.mockResolvedValueOnce(
      row('extension.extended', {
        owner: 'extended',
        is_master: true,
        state: 'off',
      }),
    )
    await renderLoaded()
    fireEvent.click(screen.getByTestId('ff-state-extension.extended-off'))
    const dialog = screen.getByRole('dialog')
    expect(dialog).toHaveTextContent('admin.featureFlagsConsole.masterOffTitle')
    expect(dialog).toHaveTextContent('"owner":"extended"')
    expect(dialog).toHaveTextContent(
      'admin.featureFlagsConsole.masterOffMessage',
    )
    expect(mockSetState).not.toHaveBeenCalled()

    fireEvent.click(
      within(dialog).getByText('admin.featureFlagsConsole.masterOffConfirm'),
    )
    await waitFor(() =>
      expect(mockSetState).toHaveBeenCalledWith('extension.extended', 'off'),
    )
    await waitFor(() => expect(mockRefresh).toHaveBeenCalled())
  })

  it('cancelling the master confirmation changes nothing', async () => {
    await renderLoaded()
    fireEvent.click(screen.getByTestId('ff-state-extension.extended-off'))
    fireEvent.click(within(screen.getByRole('dialog')).getByText('cancel'))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(mockSetState).not.toHaveBeenCalled()
  })

  it('switches a master flag to allowlist without asking', async () => {
    mockSetState.mockResolvedValueOnce(
      row('extension.extended', {
        owner: 'extended',
        is_master: true,
        state: 'allowlist',
      }),
    )
    await renderLoaded()
    fireEvent.click(screen.getByTestId('ff-state-extension.extended-allowlist'))
    await waitFor(() =>
      expect(mockSetState).toHaveBeenCalledWith(
        'extension.extended',
        'allowlist',
      ),
    )
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('offers delete instead of the state control for an unregistered row', async () => {
    mockRemove.mockResolvedValueOnce(undefined)
    await renderLoaded()
    const card = screen.getByTestId('ff-row-stale_flag')
    expect(
      within(card).queryByTestId('ff-state-stale_flag-off'),
    ).not.toBeInTheDocument()
    expect(card).toHaveTextContent('admin.featureFlagsConsole.unregisteredHint')

    fireEvent.click(screen.getByTestId('ff-delete-stale_flag'))
    const dialog = screen.getByRole('dialog')
    expect(dialog).toHaveTextContent('admin.featureFlagsConsole.deleteTitle')
    expect(mockRemove).not.toHaveBeenCalled()
    fireEvent.click(within(dialog).getByText('common.delete'))
    await waitFor(() => expect(mockRemove).toHaveBeenCalledWith('stale_flag'))
    await waitFor(() =>
      expect(screen.queryByTestId('ff-row-stale_flag')).not.toBeInTheDocument(),
    )
    expect(mockAddToast).toHaveBeenCalledWith(
      expect.stringContaining('admin.featureFlagsConsole.deleted'),
      'success',
    )
  })

  it('shows the server message when a delete is refused', async () => {
    mockRemove.mockRejectedValueOnce({
      response: {
        data: {
          detail: {
            code: 'flag_registered',
            flag: 'stale_flag',
            message: 'still registered',
          },
        },
      },
    })
    await renderLoaded()
    fireEvent.click(screen.getByTestId('ff-delete-stale_flag'))
    fireEvent.click(
      within(screen.getByRole('dialog')).getByText('common.delete'),
    )
    await waitFor(() =>
      expect(mockAddToast).toHaveBeenCalledWith('still registered', 'error'),
    )
    expect(screen.getByTestId('ff-row-stale_flag')).toBeInTheDocument()
  })

  it('edits the allowlist: chips, org picker and removal', async () => {
    mockAddTarget.mockResolvedValueOnce({
      id: 't-org-b',
      kind: 'organization',
      organization_id: 'org-b',
      name: 'Uni B',
    })
    mockRemoveTarget.mockResolvedValueOnce(undefined)
    await renderLoaded()
    const allowlist = screen.getByTestId('ff-allowlist-extension.compliance')
    expect(allowlist).toHaveTextContent('Kluge Eule (Erika Muster)')
    expect(allowlist).toHaveTextContent('Uni A')

    // org-a is listed already, so only org-b is offered.
    const select = await screen.findByTestId(
      'ff-org-select-extension.compliance',
    )
    await waitFor(() =>
      expect(within(select).getAllByRole('option')).toHaveLength(2),
    )
    fireEvent.change(select, { target: { value: 'org-b' } })
    fireEvent.click(screen.getByTestId('ff-org-add-extension.compliance'))
    await waitFor(() =>
      expect(mockAddTarget).toHaveBeenCalledWith('extension.compliance', {
        organization_id: 'org-b',
      }),
    )
    expect(await screen.findByTestId('ff-target-t-org-b')).toBeInTheDocument()

    fireEvent.click(screen.getByTestId('ff-target-remove-t-user'))
    await waitFor(() =>
      expect(mockRemoveTarget).toHaveBeenCalledWith(
        'extension.compliance',
        't-user',
      ),
    )
    await waitFor(() =>
      expect(screen.queryByTestId('ff-target-t-user')).not.toBeInTheDocument(),
    )
  })

  it('searches users after a short pause and adds one', async () => {
    jest.useFakeTimers()
    try {
      mockGetAllUsers.mockResolvedValue([
        { id: 'u7', name: 'Max', email: 'max@test.de' },
      ])
      mockAddTarget.mockResolvedValueOnce({
        id: 't-u7',
        kind: 'user',
        user_id: 'u7',
        name: 'Max',
      })
      render(<FeatureFlagsAdmin />)
      await act(async () => {})
      const input = screen.getByTestId('ff-user-search-extension.compliance')
      fireEvent.change(input, { target: { value: 'ma' } })
      await act(async () => {
        jest.advanceTimersByTime(300)
      })
      expect(mockGetAllUsers).toHaveBeenCalledWith({ search: 'ma', limit: 8 })
      fireEvent.click(await screen.findByTestId('ff-user-option-u7'))
      await act(async () => {})
      expect(mockAddTarget).toHaveBeenCalledWith('extension.compliance', {
        user_id: 'u7',
      })
    } finally {
      jest.useRealTimers()
    }
  })
})

describe('targetLabel', () => {
  it('formats users with and without pseudonym, and organizations', () => {
    expect(targetLabel(userTarget)).toBe('Kluge Eule (Erika Muster)')
    expect(targetLabel({ ...userTarget, pseudonym: null })).toBe('Erika Muster')
    expect(targetLabel(orgTarget)).toBe('Uni A')
    expect(
      targetLabel({ id: 'x', kind: 'organization', organization_id: 'o1' }),
    ).toBe('o1')
  })
})

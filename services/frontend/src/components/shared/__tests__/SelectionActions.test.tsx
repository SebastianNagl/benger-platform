/**
 * @jest-environment jsdom
 */

import { ArrowDownTrayIcon, TrashIcon } from '@heroicons/react/24/outline'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import {
  SelectionActions,
  type SelectionAction,
} from '@/components/shared/SelectionActions'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string) => {
      const catalog: Record<
        string,
        any
      > = require('../../../locales/en/common.json')
      const value = key
        .split('.')
        .reduce((node: any, part) => (node ? node[part] : undefined), catalog)
      return typeof value === 'string' ? value : key
    },
    locale: 'en',
  }),
}))

function actions(overrides: Partial<Record<string, jest.Mock>> = {}) {
  return {
    download: overrides.download ?? jest.fn(),
    upload: overrides.upload ?? jest.fn(),
    remove: overrides.remove ?? jest.fn(),
  }
}

function list(handlers: ReturnType<typeof actions>): SelectionAction[] {
  return [
    {
      id: 'download',
      label: 'Download',
      icon: ArrowDownTrayIcon,
      onSelect: handlers.download,
      testId: 'action-download',
    },
    {
      id: 'upload',
      label: 'Upload',
      onSelect: handlers.upload,
      disabled: true,
      testId: 'action-upload',
    },
    {
      id: 'remove',
      label: 'Remove',
      icon: TrashIcon,
      onSelect: handlers.remove,
      danger: true,
      separatorBefore: true,
      testId: 'action-remove',
    },
  ]
}

describe('SelectionActions', () => {
  it('is disabled and shows no count while nothing is selected', () => {
    render(<SelectionActions selectedCount={0} actions={list(actions())} />)
    const button = screen.getByTestId('selection-actions-button')
    expect(button).toBeDisabled()
    expect(button).toHaveTextContent('Actions')
    expect(
      screen.queryByTestId('selection-actions-count'),
    ).not.toBeInTheDocument()
  })

  it('shows the number of selected rows and the default label from the catalog', () => {
    render(<SelectionActions selectedCount={3} actions={list(actions())} />)
    const button = screen.getByTestId('selection-actions-button')
    expect(button).toBeEnabled()
    expect(screen.getByTestId('selection-actions-count')).toHaveTextContent('3')
  })

  it('takes its own label and test id prefix', () => {
    render(
      <SelectionActions
        selectedCount={1}
        actions={list(actions())}
        label="Bulk"
        testId="grading"
      />,
    )
    expect(screen.getByTestId('grading-button')).toHaveTextContent('Bulk')
  })

  it('stays disabled while the caller says so, even with a selection', () => {
    render(
      <SelectionActions selectedCount={2} actions={list(actions())} disabled />,
    )
    expect(screen.getByTestId('selection-actions-button')).toBeDisabled()
  })

  it('is disabled when there is no action to offer', () => {
    render(<SelectionActions selectedCount={2} actions={[]} />)
    expect(screen.getByTestId('selection-actions-button')).toBeDisabled()
  })

  it('opens a menu with the header and the actions in order', async () => {
    const user = userEvent.setup()
    render(
      <SelectionActions
        selectedCount={2}
        selectedLabel="2 selected"
        actions={list(actions())}
      />,
    )
    await user.click(screen.getByTestId('selection-actions-button'))
    const menu = await screen.findByTestId('selection-actions-menu')
    expect(menu).toHaveTextContent('2 selected')
    const items = screen.getAllByRole('menuitem')
    expect(items.map((i) => i.textContent)).toEqual([
      'Download',
      'Upload',
      'Remove',
    ])
    // the divider sits between Upload and Remove
    const separator = menu.querySelector('[role="separator"]')
    expect(separator).not.toBeNull()
    expect(
      items[1].compareDocumentPosition(separator as Element) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy()
    expect(
      (separator as Element).compareDocumentPosition(items[2]) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy()
    // icons only where given
    expect(
      screen.getByTestId('action-download').querySelector('svg'),
    ).not.toBeNull()
    expect(screen.getByTestId('action-upload').querySelector('svg')).toBeNull()
    // destructive actions are red
    expect(screen.getByTestId('action-remove').className).toContain(
      'text-red-600',
    )
  })

  it('runs the chosen action and closes the menu', async () => {
    const user = userEvent.setup()
    const handlers = actions()
    render(<SelectionActions selectedCount={1} actions={list(handlers)} />)
    await user.click(screen.getByTestId('selection-actions-button'))
    await user.click(await screen.findByTestId('action-download'))
    expect(handlers.download).toHaveBeenCalledTimes(1)
    await waitFor(() =>
      expect(
        screen.queryByTestId('selection-actions-menu'),
      ).not.toBeInTheDocument(),
    )
  })

  it('does not run a disabled action', async () => {
    const user = userEvent.setup()
    const handlers = actions()
    render(<SelectionActions selectedCount={1} actions={list(handlers)} />)
    await user.click(screen.getByTestId('selection-actions-button'))
    const upload = await screen.findByTestId('action-upload')
    expect(upload).toHaveAttribute('aria-disabled', 'true')
    await user.click(upload)
    expect(handlers.upload).not.toHaveBeenCalled()
  })
})

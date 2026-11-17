/**
 * The "Unfinished projects" list of the creation wizard: nothing on a failed
 * load, the reason on a failed discard, no request when the user declines.
 *
 * @jest-environment jsdom
 */

import '@testing-library/jest-dom'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { WizardDraftList } from '../WizardDraftList'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, vars?: Record<string, unknown>) =>
      vars ? `${key} ${JSON.stringify(vars)}` : key,
    locale: 'de',
  }),
}))

jest.mock('@/lib/api/wizardDrafts', () => ({
  wizardDraftsAPI: { list: jest.fn(), discard: jest.fn() },
}))

const api = () => require('@/lib/api/wizardDrafts').wizardDraftsAPI

const draft = {
  project_id: 'p1',
  title: 'Klausur',
  kind: 'exam',
  icon: null,
  step_id: 'dataImport',
  target_organization_id: null,
  target_group_id: null,
  created_at: null,
  touched_at: null,
  expires_at: '2026-12-17T10:00:00Z',
}

function renderList(confirm = jest.fn().mockResolvedValue(true)) {
  const onError = jest.fn()
  const onContinue = jest.fn()
  render(
    <WizardDraftList
      onContinue={onContinue}
      confirm={confirm}
      discardMessage={async (_id, title) => `discard ${title}`}
      onError={onError}
    />,
  )
  return { onError, onContinue, confirm }
}

beforeEach(() => jest.clearAllMocks())

it('renders nothing when the list cannot be loaded', async () => {
  api().list.mockRejectedValue(new Error('offline'))
  renderList()
  await waitFor(() => expect(api().list).toHaveBeenCalled())
  expect(screen.queryByTestId('wizard-draft-list')).not.toBeInTheDocument()
})

it('reports a failed discard and keeps the entry', async () => {
  api().list.mockResolvedValue([draft])
  api().discard.mockRejectedValueOnce(new Error('offline'))
  const { onError, confirm } = renderList()
  const user = userEvent.setup()
  await user.click(await screen.findByTestId('wizard-draft-discard'))
  expect(confirm).toHaveBeenCalledWith(
    expect.objectContaining({ message: 'discard Klausur', variant: 'danger' }),
  )
  await waitFor(() =>
    expect(onError).toHaveBeenCalledWith(expect.stringContaining('offline')),
  )
  expect(screen.getByTestId('wizard-draft-item')).toBeInTheDocument()

  api().discard.mockRejectedValueOnce('no message')
  await user.click(screen.getByTestId('wizard-draft-discard'))
  await waitFor(() =>
    expect(onError).toHaveBeenLastCalledWith(
      expect.stringContaining('projects.wizard.unknownError'),
    ),
  )
})

it('does nothing when the discard is declined, and continues a draft', async () => {
  api().list.mockResolvedValue([draft])
  const { onContinue } = renderList(jest.fn().mockResolvedValue(false))
  const user = userEvent.setup()
  await user.click(await screen.findByTestId('wizard-draft-discard'))
  expect(api().discard).not.toHaveBeenCalled()
  await user.click(screen.getByTestId('wizard-draft-continue'))
  expect(onContinue).toHaveBeenCalledWith('p1')
  // A draft without a change date still renders its expiry.
  expect(screen.getByTestId('wizard-draft-item').textContent).toContain('2026')
})

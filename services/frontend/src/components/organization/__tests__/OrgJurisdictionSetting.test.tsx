/**
 * @jest-environment jsdom
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

import { OrgJurisdictionSetting } from '../OrgJurisdictionSetting'

const mockUpdate = jest.fn()
const mockAddToast = jest.fn()

jest.mock('@/contexts/I18nContext', () =>
  require('@/test-utils/i18nMock').i18nMock('de'),
)
jest.mock('@/components/shared/Toast', () => ({
  useToast: () => ({ addToast: mockAddToast }),
}))
jest.mock('@/lib/api/organizations', () => ({
  organizationsAPI: {
    updateOrganizationJurisdiction: (...args: unknown[]) => mockUpdate(...args),
  },
}))

beforeEach(() => {
  mockUpdate.mockReset()
  mockAddToast.mockReset()
})

describe('OrgJurisdictionSetting', () => {
  it('an org admin switches the jurisdiction', async () => {
    mockUpdate.mockResolvedValue({ id: 'o1', jurisdiction: 'FR' })
    const onSaved = jest.fn()
    render(
      <OrgJurisdictionSetting
        organization={{ id: 'o1' }}
        canManage
        onSaved={onSaved}
      />,
    )
    const select = screen.getByTestId('org-jurisdiction-select')
    // Organizations without the setting are German.
    expect(select).toHaveValue('DE')
    fireEvent.change(select, { target: { value: 'FR' } })
    await waitFor(() => expect(onSaved).toHaveBeenCalledWith('FR'))
    expect(mockUpdate).toHaveBeenCalledWith('o1', 'FR')
    expect(mockAddToast).toHaveBeenCalledWith(expect.any(String), 'success')
  })

  it('a failed save shows an error and does not report success', async () => {
    mockUpdate.mockRejectedValue(new Error('403'))
    jest.spyOn(console, 'error').mockImplementation(() => {})
    const onSaved = jest.fn()
    render(
      <OrgJurisdictionSetting
        organization={{ id: 'o1', jurisdiction: 'DE' }}
        canManage
        onSaved={onSaved}
      />,
    )
    fireEvent.change(screen.getByTestId('org-jurisdiction-select'), {
      target: { value: 'FR' },
    })
    await waitFor(() =>
      expect(mockAddToast).toHaveBeenCalledWith(expect.any(String), 'error'),
    )
    expect(onSaved).not.toHaveBeenCalled()
  })

  it('members without management rights only see the value', () => {
    render(
      <OrgJurisdictionSetting
        organization={{ id: 'o1', jurisdiction: 'FR' }}
        canManage={false}
      />,
    )
    expect(screen.queryByTestId('org-jurisdiction-select')).toBeNull()
    expect(screen.getByTestId('org-jurisdiction')).toHaveTextContent(
      'Frankreich',
    )
  })
})

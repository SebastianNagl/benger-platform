/**
 * The shared risk registry (components/shared/settingRisk) and the
 * platform's high-impact project settings (projectSettingRisks): which
 * changes ask first, what the dialog says, and that cancelling leaves the
 * setting as it was.
 *
 * @jest-environment jsdom
 */

import { registerProjectSettingRisks } from '@/components/projects/projectSettingRisks'
import {
  registerSettingRisk,
  riskyChanges,
  settingChanges,
  SettingRiskProvider,
  useGatedSettingChange,
  type SettingRiskContext,
} from '@/components/shared/settingRisk'
import '@testing-library/jest-dom'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { useState } from 'react'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, vars?: Record<string, unknown>) =>
      vars ? `${key}:${JSON.stringify(vars)}` : key,
  }),
}))

const quiet: SettingRiskContext = {
  project: null,
  runningExam: false,
  submittedCount: 0,
}

beforeAll(() => registerProjectSettingRisks())

describe('platform registrations', () => {
  const risky = (key: string, from: unknown, to: unknown) =>
    riskyChanges([{ key, from, to }], quiet).length > 0

  it('asks only for the changes that alter what participants see or may do', () => {
    // Revealing answers: only switching on.
    expect(risky('annotator_full_visibility_after_submit', false, true)).toBe(
      true,
    )
    expect(risky('annotator_full_visibility_after_submit', true, false)).toBe(
      false,
    )
    expect(risky('annotator_step_detail_after_submit', null, true)).toBe(true)
    // Strict timer: only switching on.
    expect(risky('strict_timer_enabled', false, true)).toBe(true)
    expect(risky('strict_timer_enabled', true, false)).toBe(false)
    // Lowering the cap (0 = unlimited) can close tasks; raising cannot.
    expect(risky('maximum_annotations', 0, 3)).toBe(true)
    expect(risky('maximum_annotations', 5, 3)).toBe(true)
    expect(risky('maximum_annotations', 3, 5)).toBe(false)
    expect(risky('maximum_annotations', 3, 0)).toBe(false)
    // Switching annotation off removes it for annotators.
    expect(risky('enable_annotation', true, false)).toBe(true)
    expect(risky('enable_annotation', false, true)).toBe(false)
    // Who may reach the project, and when: any change.
    expect(
      risky('visibility', { visibility: 'private' }, { visibility: 'public' }),
    ).toBe(true)
    expect(risky('access_window', null, { window_start_at: null })).toBe(true)
    // Not registered: never asks.
    expect(risky('randomize_task_order', false, true)).toBe(false)
  })

  it('finds the registered settings that changed between two settings objects', () => {
    expect(
      settingChanges(
        { strict_timer_enabled: false, randomize_task_order: false },
        { strict_timer_enabled: true, randomize_task_order: true },
      ),
    ).toEqual([{ key: 'strict_timer_enabled', from: false, to: true }])
  })
})

function Toggle({ onCancel }: { onCancel?: () => void }) {
  const [on, setOn] = useState(false)
  const applyChange = useGatedSettingChange()
  return (
    <input
      type="checkbox"
      data-testid="toggle"
      checked={on}
      onChange={(e) => {
        const next = e.target.checked
        applyChange(
          [{ key: 'strict_timer_enabled', from: on, to: next }],
          () => setOn(next),
          onCancel,
        )
      }}
    />
  )
}

describe('confirmation dialog', () => {
  it('names the consequence and applies nothing until confirmed', async () => {
    render(
      <SettingRiskProvider context={quiet}>
        <Toggle />
      </SettingRiskProvider>,
    )
    fireEvent.click(screen.getByTestId('toggle'))
    expect(
      await screen.findByText(/project\.settingRisk\.strictTimer/),
    ).toBeInTheDocument()
    expect(screen.getByTestId('toggle')).not.toBeChecked()
    fireEvent.click(screen.getByTestId('confirm-dialog-confirm-button'))
    await waitFor(() => expect(screen.getByTestId('toggle')).toBeChecked())
  })

  it('leaves the setting as it was when cancelled', async () => {
    const onCancel = jest.fn()
    render(
      <SettingRiskProvider context={quiet}>
        <Toggle onCancel={onCancel} />
      </SettingRiskProvider>,
    )
    fireEvent.click(screen.getByTestId('toggle'))
    fireEvent.click(await screen.findByTestId('confirm-dialog-cancel-button'))
    await waitFor(() => expect(onCancel).toHaveBeenCalledTimes(1))
    expect(screen.getByTestId('toggle')).not.toBeChecked()
  })

  it('says that the change applies to a running exam while the window is open', async () => {
    render(
      <SettingRiskProvider context={{ ...quiet, runningExam: true }}>
        <Toggle />
      </SettingRiskProvider>,
    )
    fireEvent.click(screen.getByTestId('toggle'))
    expect(
      await screen.findByText(/shared\.settingRisk\.runningExam/),
    ).toBeInTheDocument()
  })

  it('applies a non-risky change at once, without a dialog', () => {
    registerSettingRisk('test_only_on', {
      isRisky: (_from, to) => to === true,
      label: () => 'x',
      consequence: () => 'y',
    })
    function Off() {
      const [on, setOn] = useState(true)
      const applyChange = useGatedSettingChange()
      return (
        <input
          type="checkbox"
          data-testid="off"
          checked={on}
          onChange={(e) => {
            const next = e.target.checked
            applyChange([{ key: 'test_only_on', from: on, to: next }], () =>
              setOn(next),
            )
          }}
        />
      )
    }
    render(
      <SettingRiskProvider context={quiet}>
        <Off />
      </SettingRiskProvider>,
    )
    fireEvent.click(screen.getByTestId('off'))
    expect(screen.getByTestId('off')).not.toBeChecked()
    expect(
      screen.queryByTestId('confirm-dialog-confirm-button'),
    ).not.toBeInTheDocument()
  })
})

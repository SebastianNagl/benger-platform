/**
 * @jest-environment jsdom
 *
 * Branch + function coverage for StepSettings — the project-creation wizard's
 * annotation-settings step. No prior test existed (was ~25% lines / 20%
 * branches). Fully controlled, no async: every onSettingsChange handler is a
 * direct behavioral assertion.
 *
 * Covers: assignment-mode Select, max/min annotation Selects (incl. the
 * "unlimited" displayValue branch when maximum_annotations === 0), the
 * require-confirm + randomize toggles, the time-limit master toggle (which
 * fans out three fields), the conditional minutes Input + strict-timer toggle
 * that only render while the time limit is enabled, and the minutes-input
 * NaN→30 fallback.
 *
 * The shared Select resolves to the native-<select> jest mock
 * (moduleNameMapper). useI18n is mocked directly to an identity translator.
 */
import { fireEvent, render, screen } from '@testing-library/react'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, fallback?: string) => fallback || key,
    locale: 'en',
  }),
}))

import { StepSettings } from '../StepSettings'
import type { ProjectSettings } from '../types'

const baseSettings = (overrides: Partial<ProjectSettings> = {}): ProjectSettings => ({
  assignment_mode: 'open',
  maximum_annotations: 3,
  min_annotations_per_task: 1,
  randomize_task_order: false,
  require_confirm_before_submit: false,
  annotation_time_limit_enabled: false,
  annotation_time_limit_seconds: null,
  strict_timer_enabled: false,
  ...overrides,
})

const renderStep = (overrides: Partial<ProjectSettings> = {}) => {
  const onSettingsChange = jest.fn()
  const settings = baseSettings(overrides)
  const utils = render(
    <StepSettings settings={settings} onSettingsChange={onSettingsChange} />
  )
  return { onSettingsChange, settings, ...utils }
}

describe('StepSettings — Select handlers', () => {
  it('updates the assignment mode', () => {
    const { onSettingsChange } = renderStep()
    fireEvent.change(screen.getByTestId('wizard-setting-mode'), {
      target: { value: 'manual' },
    })
    expect(onSettingsChange).toHaveBeenCalledWith(
      expect.objectContaining({ assignment_mode: 'manual' })
    )
  })

  it('updates maximum_annotations as an integer', () => {
    const { onSettingsChange } = renderStep()
    fireEvent.change(screen.getByTestId('wizard-setting-max-annotations'), {
      target: { value: '5' },
    })
    expect(onSettingsChange).toHaveBeenCalledWith(
      expect.objectContaining({ maximum_annotations: 5 })
    )
  })

  it('updates maximum_annotations to 0 (unlimited)', () => {
    const { onSettingsChange } = renderStep()
    fireEvent.change(screen.getByTestId('wizard-setting-max-annotations'), {
      target: { value: '0' },
    })
    expect(onSettingsChange).toHaveBeenCalledWith(
      expect.objectContaining({ maximum_annotations: 0 })
    )
  })

  it('renders the "unlimited" displayValue branch when maximum_annotations is 0', () => {
    // The Select mock renders SelectItem options; the "Unlimited" option (value 0)
    // is selected. Just assert the component renders without error in that branch.
    renderStep({ maximum_annotations: 0 })
    expect(
      screen.getByTestId('wizard-setting-max-annotations')
    ).toBeInTheDocument()
    // The Unlimited option label is present
    expect(
      screen.getByText('projects.creation.wizard.stepSettings.unlimited')
    ).toBeInTheDocument()
  })

  it('updates min_annotations_per_task', () => {
    const { onSettingsChange } = renderStep()
    fireEvent.change(screen.getByTestId('wizard-setting-min-annotations'), {
      target: { value: '3' },
    })
    expect(onSettingsChange).toHaveBeenCalledWith(
      expect.objectContaining({ min_annotations_per_task: 3 })
    )
  })
})

describe('StepSettings — toggle handlers', () => {
  it('toggles require_confirm_before_submit', () => {
    const { onSettingsChange } = renderStep()
    fireEvent.click(screen.getByTestId('wizard-setting-require-confirm'))
    expect(onSettingsChange).toHaveBeenCalledWith(
      expect.objectContaining({ require_confirm_before_submit: true })
    )
  })

  it('toggles randomize_task_order', () => {
    const { onSettingsChange } = renderStep()
    fireEvent.click(screen.getByTestId('wizard-setting-randomize'))
    expect(onSettingsChange).toHaveBeenCalledWith(
      expect.objectContaining({ randomize_task_order: true })
    )
  })
})

describe('StepSettings — time-limit section', () => {
  it('does not render the minutes input or strict-timer toggle while the limit is off', () => {
    renderStep({ annotation_time_limit_enabled: false })
    expect(
      screen.queryByText('projects.creation.wizard.stepSettings.minutes')
    ).not.toBeInTheDocument()
    expect(
      screen.queryByText('projects.creation.wizard.stepSettings.strictTimer')
    ).not.toBeInTheDocument()
  })

  it('enabling the time limit sets the default seconds and clears strict mode', () => {
    const { onSettingsChange } = renderStep({
      annotation_time_limit_enabled: false,
    })
    // The time-limit master checkbox is the one without a data-testid in the
    // timer section; locate it via its label.
    const timeLimitLabel = screen.getByText(
      'projects.creation.wizard.stepSettings.timeLimit'
    )
    const checkbox = timeLimitLabel
      .closest('div')!
      .parentElement!.querySelector('input[type="checkbox"]') as HTMLInputElement
    fireEvent.click(checkbox)
    expect(onSettingsChange).toHaveBeenCalledWith(
      expect.objectContaining({
        annotation_time_limit_enabled: true,
        annotation_time_limit_seconds: 1800,
        strict_timer_enabled: false,
      })
    )
  })

  it('renders the minutes input + strict-timer toggle while the limit is enabled', () => {
    renderStep({
      annotation_time_limit_enabled: true,
      annotation_time_limit_seconds: 1800,
    })
    expect(
      screen.getByText('projects.creation.wizard.stepSettings.minutes')
    ).toBeInTheDocument()
    expect(
      screen.getByText('projects.creation.wizard.stepSettings.strictTimer')
    ).toBeInTheDocument()
    // 1800s → 30 minutes shown in the number input
    expect(screen.getByDisplayValue('30')).toBeInTheDocument()
  })

  it('converts the minutes input into seconds on change', () => {
    const { onSettingsChange } = renderStep({
      annotation_time_limit_enabled: true,
      annotation_time_limit_seconds: 1800,
    })
    fireEvent.change(screen.getByDisplayValue('30'), {
      target: { value: '10' },
    })
    expect(onSettingsChange).toHaveBeenCalledWith(
      expect.objectContaining({ annotation_time_limit_seconds: 600 })
    )
  })

  it('falls back to 30 minutes when the input is cleared (NaN guard)', () => {
    const { onSettingsChange } = renderStep({
      annotation_time_limit_enabled: true,
      annotation_time_limit_seconds: 1800,
    })
    fireEvent.change(screen.getByDisplayValue('30'), {
      target: { value: '' },
    })
    expect(onSettingsChange).toHaveBeenCalledWith(
      expect.objectContaining({ annotation_time_limit_seconds: 1800 })
    )
  })

  it('shows the default 30 minutes when seconds is null but the limit is enabled', () => {
    renderStep({
      annotation_time_limit_enabled: true,
      annotation_time_limit_seconds: null,
    })
    expect(screen.getByDisplayValue('30')).toBeInTheDocument()
  })

  it('toggles strict_timer_enabled within the enabled time-limit section', () => {
    const { onSettingsChange } = renderStep({
      annotation_time_limit_enabled: true,
      annotation_time_limit_seconds: 1800,
    })
    const strictLabel = screen.getByText(
      'projects.creation.wizard.stepSettings.strictTimer'
    )
    const strictCheckbox = strictLabel
      .closest('div')!
      .parentElement!.querySelector('input[type="checkbox"]') as HTMLInputElement
    fireEvent.click(strictCheckbox)
    expect(onSettingsChange).toHaveBeenCalledWith(
      expect.objectContaining({ strict_timer_enabled: true })
    )
  })
})

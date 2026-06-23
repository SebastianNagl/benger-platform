/**
 * Tests for AdvancedSettingsCard — the advanced annotation-settings block
 * rendered inside the Annotation ConfigCard on the project detail page.
 *
 * The component is purely presentational and fully prop-drilled: all state
 * lives in the parent and arrives via `advancedSettings` + `setAdvancedSettings`.
 * These tests therefore drive it through a small stateful host (`Harness`) that
 * mirrors the real parent — it holds `advancedSettings` in `useState` and passes
 * a real setter — so updater functions actually apply and conditional sections
 * (timer inputs, questionnaire config) appear/disappear on toggle.
 *
 * The shared `@/components/shared/Select` is auto-mocked by the repo's
 * `moduleNameMapper` to a native <select> (role "combobox"), so each Select
 * is exercised via `userEvent.selectOptions` / change events.
 *
 * @jest-environment jsdom
 */

import '@testing-library/jest-dom'
import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState, type ComponentType } from 'react'
import {
  AdvancedSettingsCard,
  type AdvancedSettings,
} from '@/components/projects/AdvancedSettingsCard'

// A translation fn that returns the key, honouring a string default 2nd arg
// or an object `{ defaultValue }` so the rendered labels are stable + queryable.
const t = (key: string, params?: any): string => {
  if (typeof params === 'string') return params
  if (params && typeof params === 'object' && 'defaultValue' in params) {
    return params.defaultValue
  }
  return key
}

function makeSettings(
  overrides: Partial<AdvancedSettings> = {}
): AdvancedSettings {
  return {
    show_instruction: true,
    instructions_always_visible: false,
    show_skip_button: true,
    show_submit_button: true,
    require_comment_on_skip: false,
    require_confirm_before_submit: false,
    skip_queue: 'requeue_for_others',
    questionnaire_enabled: false,
    questionnaire_config: '',
    maximum_annotations: 1,
    min_annotations_per_task: 1,
    assignment_mode: 'open',
    randomize_task_order: false,
    annotator_full_visibility_after_submit: false,
    review_enabled: false,
    review_mode: 'in_place',
    allow_self_review: false,
    korrektur_enabled: false,
    korrektur_config: [],
    annotation_time_limit_enabled: false,
    annotation_time_limit_seconds: null,
    strict_timer_enabled: false,
    ...overrides,
  }
}

interface HarnessProps {
  initial?: Partial<AdvancedSettings>
  editing?: boolean
  canEdit?: boolean
  ProjectSettingsExtended?: ComponentType<any> | null
  onChange?: (s: AdvancedSettings) => void
}

/**
 * Stateful host that behaves like the real parent. Exposes the live settings
 * to assertions via `onChange` (fired on every setState) so tests can read the
 * exact produced state from updater functions.
 */
function Harness({
  initial,
  editing = true,
  canEdit = true,
  ProjectSettingsExtended = null,
  onChange,
}: HarnessProps) {
  const [settings, setSettings] = useState<AdvancedSettings>(
    makeSettings(initial)
  )

  const set: React.Dispatch<React.SetStateAction<AdvancedSettings>> = (
    update
  ) => {
    setSettings((prev) => {
      const next =
        typeof update === 'function'
          ? (update as (p: AdvancedSettings) => AdvancedSettings)(prev)
          : update
      onChange?.(next)
      return next
    })
  }

  return (
    <AdvancedSettingsCard
      t={t}
      canEditProject={() => canEdit}
      getReadOnlyMessage={(section) => `read-only: ${section}`}
      advancedSettings={settings}
      setAdvancedSettings={set}
      editing={editing}
      ProjectSettingsExtended={ProjectSettingsExtended}
    />
  )
}

// Convenience: find a checkbox by the Label text of its sibling block.
function checkboxForLabel(labelText: string | RegExp): HTMLInputElement {
  const label = screen.getByText(labelText)
  // structure: <div className="flex ..."><div><Label/><p/></div><input/></div>
  const row = label.closest('div.flex') as HTMLElement
  const input = within(row).getByRole('checkbox') as HTMLInputElement
  return input
}

describe('AdvancedSettingsCard', () => {
  describe('canEditProject gating', () => {
    it('renders the read-only message and no controls when editing is forbidden', () => {
      render(<Harness canEdit={false} />)
      expect(
        screen.getByText('read-only: project.settings.title')
      ).toBeInTheDocument()
      // None of the section headings or controls render
      expect(
        screen.queryByText('project.settings.annotationBehavior.title')
      ).not.toBeInTheDocument()
      expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
      expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
    })

    it('renders the full settings form when editing is allowed', () => {
      render(<Harness />)
      expect(
        screen.getByText('project.settings.annotationBehavior.title')
      ).toBeInTheDocument()
      expect(
        screen.getByText('project.settings.interface.title')
      ).toBeInTheDocument()
      expect(
        screen.getByText('Post-Annotation Questionnaire')
      ).toBeInTheDocument()
      // 4 base selects when questionnaire collapsed: max, min, assignment, skip
      expect(screen.getAllByRole('combobox')).toHaveLength(4)
    })
  })

  describe('Annotation behavior — selects', () => {
    it('reflects initial maximum_annotations and updates on change', async () => {
      const user = userEvent.setup()
      const onChange = jest.fn()
      render(<Harness initial={{ maximum_annotations: 2 }} onChange={onChange} />)

      // The max-annotations select is the one containing the "single"/"double" options.
      const maxSelect = screen
        .getByText('project.settings.annotationBehavior.annotations.single')
        .closest('select') as HTMLSelectElement
      expect(maxSelect.value).toBe('2')

      await user.selectOptions(maxSelect, '5')
      expect(onChange).toHaveBeenLastCalledWith(
        expect.objectContaining({ maximum_annotations: 5 })
      )

      await user.selectOptions(maxSelect, '0') // "unlimited"
      expect(onChange).toHaveBeenLastCalledWith(
        expect.objectContaining({ maximum_annotations: 0 })
      )
    })

    it('updates min_annotations_per_task on change', async () => {
      const user = userEvent.setup()
      const onChange = jest.fn()
      render(<Harness onChange={onChange} />)

      const minSelect = screen
        .getByText('project.settings.annotationBehavior.annotations.count3')
        .closest('select') as HTMLSelectElement
      expect(minSelect.value).toBe('1')

      await user.selectOptions(minSelect, '3')
      expect(onChange).toHaveBeenLastCalledWith(
        expect.objectContaining({ min_annotations_per_task: 3 })
      )
    })

    it('updates assignment_mode across all three options', async () => {
      const user = userEvent.setup()
      const onChange = jest.fn()
      render(<Harness onChange={onChange} />)

      const modeSelect = screen
        .getByText('project.settings.annotationBehavior.modes.manual')
        .closest('select') as HTMLSelectElement
      expect(modeSelect.value).toBe('open')

      await user.selectOptions(modeSelect, 'manual')
      expect(onChange).toHaveBeenLastCalledWith(
        expect.objectContaining({ assignment_mode: 'manual' })
      )

      await user.selectOptions(modeSelect, 'auto')
      expect(onChange).toHaveBeenLastCalledWith(
        expect.objectContaining({ assignment_mode: 'auto' })
      )
    })
  })

  describe('Annotation behavior — toggles', () => {
    it('toggles randomize_task_order', async () => {
      const user = userEvent.setup()
      const onChange = jest.fn()
      render(<Harness onChange={onChange} />)

      const cb = checkboxForLabel(/Randomize task order/i)
      expect(cb.checked).toBe(false)
      await user.click(cb)
      expect(onChange).toHaveBeenLastCalledWith(
        expect.objectContaining({ randomize_task_order: true })
      )
      expect(cb.checked).toBe(true)
    })

    it('toggles annotator_full_visibility_after_submit', async () => {
      const user = userEvent.setup()
      const onChange = jest.fn()
      render(<Harness onChange={onChange} />)

      const cb = checkboxForLabel(/Reveal all fields after submission/i)
      await user.click(cb)
      expect(onChange).toHaveBeenLastCalledWith(
        expect.objectContaining({
          annotator_full_visibility_after_submit: true,
        })
      )
    })
  })

  describe('Annotation timer', () => {
    it('hides the minutes input and strict-timer toggle when the limit is disabled', () => {
      render(<Harness initial={{ annotation_time_limit_enabled: false }} />)
      expect(screen.queryByText('Strict timer')).not.toBeInTheDocument()
      expect(screen.queryByRole('spinbutton')).not.toBeInTheDocument()
    })

    it('enabling the timer reveals the minutes input + strict toggle and seeds 1800s', async () => {
      const user = userEvent.setup()
      const onChange = jest.fn()
      render(<Harness onChange={onChange} />)

      const timerToggle = checkboxForLabel(/Annotation time limit/i)
      await user.click(timerToggle)

      // onChange seeds seconds to default 1800 (?? fallback) and keeps strict off
      expect(onChange).toHaveBeenLastCalledWith(
        expect.objectContaining({
          annotation_time_limit_enabled: true,
          annotation_time_limit_seconds: 1800,
          strict_timer_enabled: false,
        })
      )

      // The minutes input (1800s -> 30) and strict toggle now render
      const minutes = screen.getByRole('spinbutton') as HTMLInputElement
      expect(minutes.value).toBe('30')
      expect(screen.getByText('Strict timer')).toBeInTheDocument()
    })

    it('disabling the timer clears seconds to null and forces strict off', async () => {
      const user = userEvent.setup()
      const onChange = jest.fn()
      render(
        <Harness
          initial={{
            annotation_time_limit_enabled: true,
            annotation_time_limit_seconds: 600,
            strict_timer_enabled: true,
          }}
          onChange={onChange}
        />
      )

      const timerToggle = checkboxForLabel(/Annotation time limit/i)
      expect(timerToggle.checked).toBe(true)
      await user.click(timerToggle)

      expect(onChange).toHaveBeenLastCalledWith(
        expect.objectContaining({
          annotation_time_limit_enabled: false,
          annotation_time_limit_seconds: null,
          strict_timer_enabled: false,
        })
      )
    })

    it('renders 30 in the minutes box when seconds is null but the limit is on', () => {
      render(
        <Harness
          initial={{
            annotation_time_limit_enabled: true,
            annotation_time_limit_seconds: null,
          }}
        />
      )
      const minutes = screen.getByRole('spinbutton') as HTMLInputElement
      expect(minutes.value).toBe('30')
    })

    it('renders the rounded minute value from seconds', () => {
      render(
        <Harness
          initial={{
            annotation_time_limit_enabled: true,
            annotation_time_limit_seconds: 150, // 2.5 -> rounds to 3
          }}
        />
      )
      const minutes = screen.getByRole('spinbutton') as HTMLInputElement
      expect(minutes.value).toBe('3')
    })

    it('typing a minute value writes seconds = minutes * 60', () => {
      const onChange = jest.fn()
      render(
        <Harness
          initial={{
            annotation_time_limit_enabled: true,
            annotation_time_limit_seconds: 1800,
          }}
          onChange={onChange}
        />
      )

      const minutes = screen.getByRole('spinbutton') as HTMLInputElement
      // Drive the controlled number input deterministically: value "5" -> 5*60.
      fireEvent.change(minutes, { target: { value: '5' } })
      expect(onChange).toHaveBeenLastCalledWith(
        expect.objectContaining({ annotation_time_limit_seconds: 300 })
      )
    })

    it('an empty/NaN minute value falls back to 30 minutes (1800s)', () => {
      const onChange = jest.fn()
      render(
        <Harness
          initial={{
            annotation_time_limit_enabled: true,
            annotation_time_limit_seconds: 600,
          }}
          onChange={onChange}
        />
      )

      const minutes = screen.getByRole('spinbutton') as HTMLInputElement
      // empty -> parseInt('') NaN -> (|| 30) -> 30 * 60 = 1800
      fireEvent.change(minutes, { target: { value: '' } })
      expect(onChange).toHaveBeenLastCalledWith(
        expect.objectContaining({ annotation_time_limit_seconds: 1800 })
      )
    })

    it('toggles strict_timer_enabled', async () => {
      const user = userEvent.setup()
      const onChange = jest.fn()
      render(
        <Harness
          initial={{
            annotation_time_limit_enabled: true,
            annotation_time_limit_seconds: 1800,
            strict_timer_enabled: false,
          }}
          onChange={onChange}
        />
      )

      const strict = checkboxForLabel(/Strict timer/i)
      expect(strict.checked).toBe(false)
      await user.click(strict)
      expect(onChange).toHaveBeenLastCalledWith(
        expect.objectContaining({ strict_timer_enabled: true })
      )
    })
  })

  describe('Interface settings — toggles', () => {
    const cases: Array<[RegExp, keyof AdvancedSettings, boolean]> = [
      [/project\.settings\.interface\.showInstructions$/i, 'show_instruction', true],
      [/Always show instructions/i, 'instructions_always_visible', false],
      [/project\.settings\.interface\.showSkipButton$/i, 'show_skip_button', true],
      [
        /project\.settings\.interface\.requireCommentOnSkip$/i,
        'require_comment_on_skip',
        false,
      ],
      [
        /project\.settings\.interface\.showSubmitButton$/i,
        'show_submit_button',
        true,
      ],
      [
        /Require confirmation before submit/i,
        'require_confirm_before_submit',
        false,
      ],
    ]

    it.each(cases)(
      'flips %s checkbox',
      async (labelRe, key, initialValue) => {
        const user = userEvent.setup()
        const onChange = jest.fn()
        render(<Harness onChange={onChange} />)

        const cb = checkboxForLabel(labelRe)
        expect(cb.checked).toBe(initialValue)
        await user.click(cb)
        expect(onChange).toHaveBeenLastCalledWith(
          expect.objectContaining({ [key]: !initialValue })
        )
      }
    )
  })

  describe('Interface settings — skip_queue select', () => {
    it('updates skip_queue to each of the three values', async () => {
      const user = userEvent.setup()
      const onChange = jest.fn()
      render(<Harness onChange={onChange} />)

      // The skip-queue select is the one carrying the "Skip permanently" option.
      const skipSelect = screen
        .getByText('Skip permanently')
        .closest('select') as HTMLSelectElement
      expect(skipSelect.value).toBe('requeue_for_others')

      await user.selectOptions(skipSelect, 'requeue_for_me')
      expect(onChange).toHaveBeenLastCalledWith(
        expect.objectContaining({ skip_queue: 'requeue_for_me' })
      )

      await user.selectOptions(skipSelect, 'ignore_skipped')
      expect(onChange).toHaveBeenLastCalledWith(
        expect.objectContaining({ skip_queue: 'ignore_skipped' })
      )

      await user.selectOptions(skipSelect, 'requeue_for_others')
      expect(onChange).toHaveBeenLastCalledWith(
        expect.objectContaining({ skip_queue: 'requeue_for_others' })
      )
    })

    it('falls back to requeue_for_others display when skip_queue is unset', () => {
      // Cast through unknown to simulate a legacy row missing skip_queue.
      render(
        <Harness initial={{ skip_queue: undefined as unknown as AdvancedSettings['skip_queue'] }} />
      )
      const skipSelect = screen
        .getByText('Skip permanently')
        .closest('select') as HTMLSelectElement
      // Component coalesces the value with 'requeue_for_others'.
      expect(skipSelect.value).toBe('requeue_for_others')
    })
  })

  describe('Post-annotation questionnaire', () => {
    it('hides the template + config editor until enabled', () => {
      render(<Harness initial={{ questionnaire_enabled: false }} />)
      expect(screen.queryByText('Template')).not.toBeInTheDocument()
      expect(
        screen.queryByText('Questionnaire Config (Label Studio XML)')
      ).not.toBeInTheDocument()
    })

    it('enabling the questionnaire reveals the template select + config textarea', async () => {
      const user = userEvent.setup()
      const onChange = jest.fn()
      render(<Harness onChange={onChange} />)

      const enable = checkboxForLabel(/Enable Questionnaire/i)
      await user.click(enable)
      expect(onChange).toHaveBeenLastCalledWith(
        expect.objectContaining({ questionnaire_enabled: true })
      )

      expect(screen.getByText('Template')).toBeInTheDocument()
      expect(
        screen.getByText('Questionnaire Config (Label Studio XML)')
      ).toBeInTheDocument()
      // questionnaire adds a 5th combobox (the template picker)
      expect(screen.getAllByRole('combobox')).toHaveLength(5)
    })

    it('selecting the "confidence_difficulty" template writes its XML into the config', async () => {
      const user = userEvent.setup()
      const onChange = jest.fn()
      render(<Harness initial={{ questionnaire_enabled: true }} onChange={onChange} />)

      const templateSelect = screen
        .getByText('Confidence & Difficulty (2 items)')
        .closest('select') as HTMLSelectElement
      await user.selectOptions(templateSelect, 'confidence_difficulty')

      expect(onChange).toHaveBeenCalled()
      const next = onChange.mock.calls.at(-1)![0] as AdvancedSettings
      expect(next.questionnaire_config).toContain(
        'Post-Annotation Feedback'
      )
      expect(next.questionnaire_config).toContain('name="confidence"')
      expect(next.questionnaire_config).not.toContain('guideline_clarity')
    })

    it('selecting the "extended" template writes the 4-item XML', async () => {
      const user = userEvent.setup()
      const onChange = jest.fn()
      render(<Harness initial={{ questionnaire_enabled: true }} onChange={onChange} />)

      const templateSelect = screen
        .getByText('Extended Feedback (4 items)')
        .closest('select') as HTMLSelectElement
      await user.selectOptions(templateSelect, 'extended')

      const next = onChange.mock.calls.at(-1)![0] as AdvancedSettings
      expect(next.questionnaire_config).toContain('guideline_clarity')
      expect(next.questionnaire_config).toContain('name="comments"')
    })

    it('selecting the "utaut_study" template writes the Likert XML', async () => {
      const user = userEvent.setup()
      const onChange = jest.fn()
      render(<Harness initial={{ questionnaire_enabled: true }} onChange={onChange} />)

      const templateSelect = screen
        .getByText('UTAUT Study (12 items, Likert 1-7)')
        .closest('select') as HTMLSelectElement
      await user.selectOptions(templateSelect, 'utaut_study')

      const next = onChange.mock.calls.at(-1)![0] as AdvancedSettings
      expect(next.questionnaire_config).toContain('utaut_pe')
      expect(next.questionnaire_config).toContain('Post-Annotations-Fragebogen')
    })

    it('ignores an unknown template key (the `v in templates` guard is false)', () => {
      const onChange = jest.fn()
      render(
        <Harness
          initial={{
            questionnaire_enabled: true,
            questionnaire_config: '<View>keep-me</View>',
          }}
          onChange={onChange}
        />
      )

      const templateSelect = screen
        .getByText('Confidence & Difficulty (2 items)')
        .closest('select') as HTMLSelectElement
      // Fire a value not present in the templates map -> guard short-circuits,
      // setAdvancedSettings is never called, config stays untouched.
      fireEvent.change(templateSelect, { target: { value: 'does_not_exist' } })
      expect(onChange).not.toHaveBeenCalled()
    })

    it('editing the config textarea updates questionnaire_config', async () => {
      const user = userEvent.setup()
      const onChange = jest.fn()
      render(
        <Harness
          initial={{ questionnaire_enabled: true, questionnaire_config: '' }}
          onChange={onChange}
        />
      )

      const textarea = screen
        .getByText('Questionnaire Config (Label Studio XML)')
        .closest('div')!
        .querySelector('textarea') as HTMLTextAreaElement
      await user.type(textarea, '<View/>')
      expect(onChange).toHaveBeenLastCalledWith(
        expect.objectContaining({ questionnaire_config: '<View/>' })
      )
      expect(textarea.value).toBe('<View/>')
    })

    it('shows the existing config value in the textarea', () => {
      render(
        <Harness
          initial={{
            questionnaire_enabled: true,
            questionnaire_config: '<View>existing</View>',
          }}
        />
      )
      const textarea = screen
        .getByText('Questionnaire Config (Label Studio XML)')
        .closest('div')!
        .querySelector('textarea') as HTMLTextAreaElement
      expect(textarea.value).toBe('<View>existing</View>')
    })
  })

  describe('ProjectSettingsExtended slot', () => {
    it('does not render an extended slot when null', () => {
      render(<Harness ProjectSettingsExtended={null} />)
      expect(screen.queryByTestId('extended-slot')).not.toBeInTheDocument()
    })

    it('renders the extended component with settings, setter, and editing props', () => {
      const Extended: ComponentType<any> = ({ settings, editing }: any) => (
        <div data-testid="extended-slot">
          <span data-testid="extended-editing">{String(editing)}</span>
          <span data-testid="extended-mode">{settings.assignment_mode}</span>
        </div>
      )

      render(
        <Harness
          initial={{ assignment_mode: 'manual' }}
          editing
          ProjectSettingsExtended={Extended}
        />
      )

      expect(screen.getByTestId('extended-slot')).toBeInTheDocument()
      expect(screen.getByTestId('extended-editing')).toHaveTextContent('true')
      expect(screen.getByTestId('extended-mode')).toHaveTextContent('manual')
    })

    it('passes the live setter so the extended slot can mutate parent settings', async () => {
      const user = userEvent.setup()
      const onChange = jest.fn()
      const Extended: ComponentType<any> = ({ onSettingsChange }: any) => (
        <button
          data-testid="ext-btn"
          onClick={() =>
            onSettingsChange((prev: AdvancedSettings) => ({
              ...prev,
              review_enabled: true,
            }))
          }
        >
          enable review
        </button>
      )

      render(
        <Harness ProjectSettingsExtended={Extended} onChange={onChange} />
      )
      await user.click(screen.getByTestId('ext-btn'))
      expect(onChange).toHaveBeenLastCalledWith(
        expect.objectContaining({ review_enabled: true })
      )
    })
  })

  describe('editing=false (read disabled) state', () => {
    it('disables every control when not editing', () => {
      render(
        <Harness
          editing={false}
          initial={{
            annotation_time_limit_enabled: true,
            annotation_time_limit_seconds: 1800,
            questionnaire_enabled: true,
          }}
        />
      )

      // All comboboxes disabled
      screen
        .getAllByRole('combobox')
        .forEach((el) => expect(el).toBeDisabled())
      // All checkboxes disabled
      screen
        .getAllByRole('checkbox')
        .forEach((el) => expect(el).toBeDisabled())
      // Minutes input + config textarea disabled
      expect(screen.getByRole('spinbutton')).toBeDisabled()
      expect(
        screen
          .getByText('Questionnaire Config (Label Studio XML)')
          .closest('div')!
          .querySelector('textarea')
      ).toBeDisabled()
    })
  })
})

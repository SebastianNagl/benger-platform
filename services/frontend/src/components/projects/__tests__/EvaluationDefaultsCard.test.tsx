/**
 * Tests for EvaluationDefaultsCard — the "Evaluation Defaults" SubSection on
 * the project detail page.
 *
 * Mirrors GenerationDefaultsCard but with eval-specific i18n keys, no ref
 * sync, and different bounds/fallbacks (temperature fallback 0 / max 2,
 * max-tokens fallback 500 / max 16000). Pure presentational component: all
 * state is prop-drilled, so each test renders directly with controlled props
 * + jest.fn() callbacks and asserts on DOM / callback invocations. Covers:
 * the 3-mode strategy picker + onChange (setter + lazy beginEdit), both
 * number inputs (value, disabled-unless-custom, float/int onChange parsing,
 * empty -> undefined), the help-text mode override, and the recommended-
 * consensus badge in all three states (uniform / divergent / none) including
 * the reset-to-recommended button.
 *
 * The inputs are fully controlled by the (mocked) parent setters, so their
 * displayed value never changes mid-test. onChange parsing is exercised with
 * `fireEvent.change` (one deterministic event with an explicit target.value)
 * rather than `userEvent.type`, which would append to the stale value.
 *
 * @jest-environment jsdom
 */

import { EvaluationDefaultsCard } from '@/components/projects/EvaluationDefaultsCard'
import type {
  DefaultsMode,
  RecommendedConsensus,
} from '@/components/projects/GenerationDefaultsCard'
import { render, screen, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

// Identity translator: always returns the i18n key, ignoring the German
// fallback passed as the 2nd arg, so every rendered label is a unique key.
const t = (key: string, _fallback?: any) => key

const noConsensusEntry = () => ({
  value: undefined,
  uniform: false,
  anyRec: false,
  perModel: [],
})

const emptyConsensus = (): RecommendedConsensus => ({
  temperature: noConsensusEntry(),
  max_tokens: noConsensusEntry(),
})

function renderCard(
  overrides: Partial<Parameters<typeof EvaluationDefaultsCard>[0]> = {}
) {
  const setEvalDefaultsMode = jest.fn()
  const setEvalDefaultTemperature = jest.fn()
  const setEvalDefaultMaxTokens = jest.fn()
  const beginEditEvaluation = jest.fn()

  const props = {
    t,
    evalDefaultsMode: 'custom' as DefaultsMode,
    setEvalDefaultsMode,
    evalDefaultTemperature: undefined as number | undefined,
    setEvalDefaultTemperature,
    evalDefaultMaxTokens: undefined as number | undefined,
    setEvalDefaultMaxTokens,
    selectedModelIds: [] as string[],
    evalRecConsensus: emptyConsensus(),
    cardEditingEvaluation: false,
    beginEditEvaluation,
    ...overrides,
  }

  const utils = render(<EvaluationDefaultsCard {...props} />)
  return {
    ...utils,
    props,
    setEvalDefaultsMode,
    setEvalDefaultTemperature,
    setEvalDefaultMaxTokens,
    beginEditEvaluation,
  }
}

// SubSection is collapsed by default; click the title to reveal the body.
async function expand(user: ReturnType<typeof userEvent.setup>) {
  await user.click(
    screen.getByRole('button', { name: /project\.evaluationDefaults\.title/i })
  )
}

// Disambiguate the two number inputs by their max: temperature max=2,
// max-tokens max=16000 (the eval-side bound).
function getTemperatureInput(): HTMLInputElement {
  return screen
    .getAllByRole('spinbutton')
    .find((el) => (el as HTMLInputElement).max === '2') as HTMLInputElement
}
function getMaxTokensInput(): HTMLInputElement {
  return screen
    .getAllByRole('spinbutton')
    .find((el) => (el as HTMLInputElement).max === '16000') as HTMLInputElement
}

describe('EvaluationDefaultsCard', () => {
  describe('section shell', () => {
    it('renders the SubSection title and is collapsed (body hidden) by default', () => {
      renderCard()
      expect(
        screen.getByText('project.evaluationDefaults.title')
      ).toBeInTheDocument()
      expect(
        screen.queryByText('project.evaluationDefaults.description')
      ).not.toBeInTheDocument()
      expect(screen.queryAllByRole('spinbutton')).toHaveLength(0)
    })

    it('reveals description, mode picker and both inputs once expanded', async () => {
      const user = userEvent.setup()
      renderCard()
      await expand(user)

      expect(
        screen.getByText('project.evaluationDefaults.description')
      ).toBeInTheDocument()
      expect(
        screen.getByText('project.evaluationDefaults.modeLabel')
      ).toBeInTheDocument()
      expect(screen.getAllByRole('spinbutton')).toHaveLength(2)
      expect(
        screen.getByText('project.evaluationDefaults.defaultTemperature')
      ).toBeInTheDocument()
      expect(
        screen.getByText('project.evaluationDefaults.defaultMaxTokens')
      ).toBeInTheDocument()
    })

    it('uses eval-side input bounds (max-tokens fallback 500, max 16000)', async () => {
      const user = userEvent.setup()
      renderCard({ evalDefaultMaxTokens: undefined })
      await expand(user)
      const maxTok = getMaxTokensInput()
      expect(maxTok.value).toBe('500') // eval fallback (vs generation 4000)
      expect(maxTok.min).toBe('100')
      expect(maxTok.max).toBe('16000') // eval bound (vs generation 128000)
      // Temperature bounds match the generation side.
      const temp = getTemperatureInput()
      expect(temp.min).toBe('0')
      expect(temp.step).toBe('0.1')
    })
  })

  describe('mode picker', () => {
    it('renders the three radio options with the active one checked', async () => {
      const user = userEvent.setup()
      renderCard({ evalDefaultsMode: 'minimum' })
      await expand(user)

      const radios = screen.getAllByRole('radio') as HTMLInputElement[]
      expect(radios).toHaveLength(3)
      expect(radios.map((r) => r.value)).toEqual([
        'recommended',
        'minimum',
        'custom',
      ])
      expect(radios.find((r) => r.checked)?.value).toBe('minimum')
      // Eval-side radio group name (distinct from the generation card).
      expect(radios.every((r) => r.name === 'eval-defaults-mode')).toBe(true)
    })

    it('renders the eval-specific mode labels', async () => {
      const user = userEvent.setup()
      renderCard()
      await expand(user)
      expect(
        screen.getByText('project.evaluationDefaults.modeRecommended')
      ).toBeInTheDocument()
      expect(
        screen.getByText('project.evaluationDefaults.modeMinimum')
      ).toBeInTheDocument()
      expect(
        screen.getByText('project.evaluationDefaults.modeCustom')
      ).toBeInTheDocument()
      expect(
        screen.getByText('project.evaluationDefaults.modeRecommendedDesc')
      ).toBeInTheDocument()
    })

    it('selecting a mode calls the setter and begins editing (no ref here)', async () => {
      const user = userEvent.setup()
      const { setEvalDefaultsMode, beginEditEvaluation } = renderCard({
        evalDefaultsMode: 'custom',
        cardEditingEvaluation: false,
      })
      await expand(user)
      const radios = screen.getAllByRole('radio')
      await user.click(radios[0]) // recommended
      expect(setEvalDefaultsMode).toHaveBeenCalledWith('recommended')
      expect(beginEditEvaluation).toHaveBeenCalledTimes(1)
    })

    it('does NOT begin editing again when already editing', async () => {
      const user = userEvent.setup()
      const { setEvalDefaultsMode, beginEditEvaluation } = renderCard({
        evalDefaultsMode: 'custom',
        cardEditingEvaluation: true,
      })
      await expand(user)
      const radios = screen.getAllByRole('radio')
      await user.click(radios[1]) // minimum
      expect(setEvalDefaultsMode).toHaveBeenCalledWith('minimum')
      expect(beginEditEvaluation).not.toHaveBeenCalled()
    })
  })

  describe('inputs — values, disabled state, help text', () => {
    it('shows fallbacks (0 / 500) when values are undefined', async () => {
      const user = userEvent.setup()
      renderCard({
        evalDefaultTemperature: undefined,
        evalDefaultMaxTokens: undefined,
      })
      await expand(user)
      expect(getTemperatureInput().value).toBe('0')
      expect(getMaxTokensInput().value).toBe('500')
    })

    it('shows the supplied values when defined', async () => {
      const user = userEvent.setup()
      renderCard({ evalDefaultTemperature: 0.2, evalDefaultMaxTokens: 1200 })
      await expand(user)
      expect(getTemperatureInput().value).toBe('0.2')
      expect(getMaxTokensInput().value).toBe('1200')
    })

    it('inputs are enabled in custom mode and the custom help text shows', async () => {
      const user = userEvent.setup()
      renderCard({ evalDefaultsMode: 'custom' })
      await expand(user)
      expect(getTemperatureInput().disabled).toBe(false)
      expect(getMaxTokensInput().disabled).toBe(false)
      expect(
        screen.getByText('project.evaluationDefaults.temperatureHelp')
      ).toBeInTheDocument()
      expect(
        screen.getByText('project.evaluationDefaults.maxTokensHelp')
      ).toBeInTheDocument()
    })

    it.each(['recommended', 'minimum'] as const)(
      'disables inputs and shows the override help text in %s mode',
      async (mode) => {
        const user = userEvent.setup()
        renderCard({ evalDefaultsMode: mode })
        await expand(user)
        expect(getTemperatureInput().disabled).toBe(true)
        expect(getMaxTokensInput().disabled).toBe(true)
        expect(
          screen.getByText(
            'project.evaluationDefaults.temperatureHelpModeOverride'
          )
        ).toBeInTheDocument()
        expect(
          screen.getByText('project.evaluationDefaults.maxTokensHelpModeOverride')
        ).toBeInTheDocument()
        expect(
          screen.queryByText('project.evaluationDefaults.temperatureHelp')
        ).not.toBeInTheDocument()
      }
    )

    it('temperature onChange parses a float and begins editing', async () => {
      const { setEvalDefaultTemperature, beginEditEvaluation } = renderCard({
        evalDefaultsMode: 'custom',
        cardEditingEvaluation: false,
      })
      await userEvent.setup().click(
        screen.getByRole('button', {
          name: /project\.evaluationDefaults\.title/i,
        })
      )
      fireEvent.change(getTemperatureInput(), { target: { value: '1.3' } })
      expect(beginEditEvaluation).toHaveBeenCalledTimes(1)
      expect(setEvalDefaultTemperature).toHaveBeenCalledWith(1.3)
    })

    it('max-tokens onChange parses an int and begins editing', async () => {
      const { setEvalDefaultMaxTokens, beginEditEvaluation } = renderCard({
        evalDefaultsMode: 'custom',
        cardEditingEvaluation: false,
      })
      await userEvent.setup().click(
        screen.getByRole('button', {
          name: /project\.evaluationDefaults\.title/i,
        })
      )
      fireEvent.change(getMaxTokensInput(), { target: { value: '2500' } })
      expect(beginEditEvaluation).toHaveBeenCalledTimes(1)
      expect(setEvalDefaultMaxTokens).toHaveBeenCalledWith(2500)
    })

    it('clearing temperature emits undefined (empty string branch)', async () => {
      const user = userEvent.setup()
      const { setEvalDefaultTemperature } = renderCard({
        evalDefaultsMode: 'custom',
        evalDefaultTemperature: 0.4,
      })
      await expand(user)
      fireEvent.change(getTemperatureInput(), { target: { value: '' } })
      expect(setEvalDefaultTemperature).toHaveBeenLastCalledWith(undefined)
    })

    it('clearing max-tokens emits undefined (empty string branch)', async () => {
      const user = userEvent.setup()
      const { setEvalDefaultMaxTokens } = renderCard({
        evalDefaultsMode: 'custom',
        evalDefaultMaxTokens: 500,
      })
      await expand(user)
      fireEvent.change(getMaxTokensInput(), { target: { value: '' } })
      expect(setEvalDefaultMaxTokens).toHaveBeenLastCalledWith(undefined)
    })

    it('does not begin editing on input change when already editing', async () => {
      const user = userEvent.setup()
      const { beginEditEvaluation, setEvalDefaultTemperature } = renderCard({
        evalDefaultsMode: 'custom',
        cardEditingEvaluation: true,
      })
      await expand(user)
      fireEvent.change(getTemperatureInput(), { target: { value: '0.8' } })
      expect(setEvalDefaultTemperature).toHaveBeenCalledWith(0.8)
      expect(beginEditEvaluation).not.toHaveBeenCalled()
    })
  })

  describe('recommended-consensus badge', () => {
    it('is hidden entirely when no models are selected', async () => {
      const user = userEvent.setup()
      renderCard({
        selectedModelIds: [],
        evalRecConsensus: {
          temperature: { value: 0.1, uniform: true, anyRec: true, perModel: [] },
          max_tokens: { value: 500, uniform: true, anyRec: true, perModel: [] },
        },
      })
      await expand(user)
      expect(
        screen.queryByText('generation.controlModal.recommended')
      ).not.toBeInTheDocument()
    })

    it('shows the uniform recommendation value when consensus is uniform', async () => {
      const user = userEvent.setup()
      renderCard({
        selectedModelIds: ['m1'],
        evalDefaultTemperature: 0.1,
        evalDefaultMaxTokens: 500,
        evalRecConsensus: {
          temperature: { value: 0.1, uniform: true, anyRec: true, perModel: [] },
          max_tokens: { value: 500, uniform: true, anyRec: true, perModel: [] },
        },
      })
      await expand(user)
      // The label + value share one text node ("…recommended: 0.1"), so match
      // by substring.
      expect(
        screen.getAllByText(/generation\.controlModal\.recommended/).length
      ).toBeGreaterThanOrEqual(2)
      expect(screen.getByText(/recommended.*0\.1/)).toBeInTheDocument()
      // Values match defaults -> no reset button.
      expect(
        screen.queryByText('generation.controlModal.resetToRecommended')
      ).not.toBeInTheDocument()
    })

    it('clicking the temperature reset button resets to the recommended value', async () => {
      const user = userEvent.setup()
      const { setEvalDefaultTemperature } = renderCard({
        selectedModelIds: ['m1'],
        evalDefaultTemperature: 1.0, // differs from rec 0.1 -> reset shows
        evalDefaultMaxTokens: 500, // matches
        evalRecConsensus: {
          temperature: { value: 0.1, uniform: true, anyRec: true, perModel: [] },
          max_tokens: { value: 500, uniform: true, anyRec: true, perModel: [] },
        },
      })
      await expand(user)
      await user.click(
        screen.getByRole('button', {
          name: 'generation.controlModal.resetToRecommended',
        })
      )
      expect(setEvalDefaultTemperature).toHaveBeenCalledWith(0.1)
    })

    it('reset on max-tokens uses the 500 fallback when value is undefined', async () => {
      const user = userEvent.setup()
      const { setEvalDefaultMaxTokens } = renderCard({
        selectedModelIds: ['m1'],
        evalDefaultMaxTokens: undefined, // (undefined ?? 500) !== 800 -> reset
        evalDefaultTemperature: 0, // matches rec 0 -> no reset
        evalRecConsensus: {
          temperature: { value: 0, uniform: true, anyRec: true, perModel: [] },
          max_tokens: { value: 800, uniform: true, anyRec: true, perModel: [] },
        },
      })
      await expand(user)
      await user.click(
        screen.getByRole('button', {
          name: 'generation.controlModal.resetToRecommended',
        })
      )
      expect(setEvalDefaultMaxTokens).toHaveBeenCalledWith(800)
    })

    it('temperature reset uses the 0 fallback when value is undefined', async () => {
      const user = userEvent.setup()
      const { setEvalDefaultTemperature } = renderCard({
        selectedModelIds: ['m1'],
        evalDefaultTemperature: undefined, // (undefined ?? 0) !== 0.5 -> reset shows
        evalDefaultMaxTokens: 500, // matches -> no reset on this side
        evalRecConsensus: {
          temperature: { value: 0.5, uniform: true, anyRec: true, perModel: [] },
          max_tokens: { value: 500, uniform: true, anyRec: true, perModel: [] },
        },
      })
      await expand(user)
      await user.click(
        screen.getByRole('button', {
          name: 'generation.controlModal.resetToRecommended',
        })
      )
      expect(setEvalDefaultTemperature).toHaveBeenCalledWith(0.5)
    })

    it('shows the divergent badge with a per-model title when recs differ', async () => {
      const user = userEvent.setup()
      renderCard({
        selectedModelIds: ['m1', 'm2'],
        evalRecConsensus: {
          temperature: {
            value: undefined,
            uniform: false,
            anyRec: true,
            perModel: [
              { model: 'm1', value: 0 },
              { model: 'm2', value: 0.5 },
            ],
          },
          max_tokens: {
            value: undefined,
            uniform: false,
            anyRec: true,
            perModel: [
              { model: 'm1', value: undefined },
              { model: 'm2', value: 2000 },
            ],
          },
        },
      })
      await expand(user)
      const divergent = screen.getAllByText(
        'generation.controlModal.divergentRecommendations'
      )
      expect(divergent).toHaveLength(2)
      expect(divergent[0]).toHaveAttribute('title', 'm1: 0\nm2: 0.5')
      expect(divergent[1]).toHaveAttribute('title', 'm1: —\nm2: 2000')
    })

    it('shows the "no recommendation" badge when nothing is recommended', async () => {
      const user = userEvent.setup()
      renderCard({
        selectedModelIds: ['m1'],
        evalRecConsensus: emptyConsensus(),
      })
      await expand(user)
      expect(
        screen.getAllByText('generation.controlModal.noRecommendation')
      ).toHaveLength(2)
    })

    it('falls through to "no recommendation" when uniform but value is undefined', async () => {
      const user = userEvent.setup()
      renderCard({
        selectedModelIds: ['m1'],
        evalRecConsensus: {
          temperature: { value: undefined, uniform: true, anyRec: false, perModel: [] },
          max_tokens: { value: undefined, uniform: true, anyRec: false, perModel: [] },
        },
      })
      await expand(user)
      expect(
        screen.getAllByText('generation.controlModal.noRecommendation')
      ).toHaveLength(2)
    })
  })
})

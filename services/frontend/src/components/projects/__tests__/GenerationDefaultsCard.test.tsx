/**
 * Tests for GenerationDefaultsCard — the "Generation Defaults" SubSection on
 * the project detail page.
 *
 * The card is a pure presentational component: all state lives in the parent
 * and is prop-drilled in, so every test renders it directly with controlled
 * props + jest.fn() callbacks and asserts on the rendered DOM / callback
 * invocations. Covers: the 3-mode strategy picker (recommended/minimum/custom)
 * and its onChange (ref sync + state setter + lazy beginEdit), the
 * temperature + max-tokens number inputs (value, disabled-when-not-custom,
 * onChange parsing, empty -> undefined), the help-text mode override, and the
 * recommended-consensus badge in all three states (uniform / divergent /
 * none) including the "reset to recommended" button.
 *
 * The inputs are fully controlled by the (mocked) parent setters, so their
 * displayed value never changes mid-test. onChange parsing is therefore
 * exercised with `fireEvent.change` (one deterministic event with an explicit
 * target.value) rather than `userEvent.type`, which would append to the
 * stale controlled value.
 *
 * @jest-environment jsdom
 */

import { createRef } from 'react'
import {
  GenerationDefaultsCard,
  type DefaultsMode,
  type RecommendedConsensus,
} from '@/components/projects/GenerationDefaultsCard'
import { render, screen, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

// Identity translator: always returns the i18n key, ignoring the German
// fallback the component passes as the 2nd arg. This makes every rendered
// label a stable, unique key to assert against (mode labels, help text, and
// the generation.controlModal.* badges alike).
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
  overrides: Partial<Parameters<typeof GenerationDefaultsCard>[0]> = {}
) {
  const setGenDefaultsMode = jest.fn()
  const setGenDefaultTemperature = jest.fn()
  const setGenDefaultMaxTokens = jest.fn()
  const beginEditGeneration = jest.fn()
  const genDefaultsModeRef = createRef<DefaultsMode>() as React.MutableRefObject<DefaultsMode>
  genDefaultsModeRef.current = (overrides.genDefaultsMode as DefaultsMode) ?? 'custom'

  const props = {
    t,
    genDefaultsMode: 'custom' as DefaultsMode,
    setGenDefaultsMode,
    genDefaultsModeRef,
    genDefaultTemperature: undefined as number | undefined,
    setGenDefaultTemperature,
    genDefaultMaxTokens: undefined as number | undefined,
    setGenDefaultMaxTokens,
    selectedModelIds: [] as string[],
    genRecConsensus: emptyConsensus(),
    cardEditingGeneration: false,
    beginEditGeneration,
    ...overrides,
  }

  const utils = render(<GenerationDefaultsCard {...props} />)
  return {
    ...utils,
    props,
    setGenDefaultsMode,
    setGenDefaultTemperature,
    setGenDefaultMaxTokens,
    beginEditGeneration,
    genDefaultsModeRef,
  }
}

// SubSection is collapsed by default; click the title to reveal the card body.
async function expand(user: ReturnType<typeof userEvent.setup>) {
  await user.click(
    screen.getByRole('button', { name: /project\.generationDefaults\.title/i })
  )
}

// The two DefaultParamInputs are <input type="number">. They're disambiguated
// by their max: temperature is max=2, max-tokens is max=128000.
function getTemperatureInput(): HTMLInputElement {
  return screen
    .getAllByRole('spinbutton')
    .find((el) => (el as HTMLInputElement).max === '2') as HTMLInputElement
}
function getMaxTokensInput(): HTMLInputElement {
  return screen
    .getAllByRole('spinbutton')
    .find((el) => (el as HTMLInputElement).max === '128000') as HTMLInputElement
}

describe('GenerationDefaultsCard', () => {
  describe('section shell', () => {
    it('renders the SubSection title and is collapsed (body hidden) by default', () => {
      renderCard()
      expect(
        screen.getByText('project.generationDefaults.title')
      ).toBeInTheDocument()
      // Collapsed: the description and inputs are not mounted.
      expect(
        screen.queryByText('project.generationDefaults.description')
      ).not.toBeInTheDocument()
      expect(screen.queryAllByRole('spinbutton')).toHaveLength(0)
    })

    it('reveals description, mode picker and both inputs once expanded', async () => {
      const user = userEvent.setup()
      renderCard()
      await expand(user)

      expect(
        screen.getByText('project.generationDefaults.description')
      ).toBeInTheDocument()
      expect(
        screen.getByText('project.generationDefaults.modeLabel')
      ).toBeInTheDocument()
      expect(screen.getAllByRole('spinbutton')).toHaveLength(2)
      expect(
        screen.getByText('project.generationDefaults.defaultTemperature')
      ).toBeInTheDocument()
      expect(
        screen.getByText('project.generationDefaults.defaultMaxTokens')
      ).toBeInTheDocument()
    })
  })

  describe('mode picker', () => {
    it('renders the three radio options with the active one checked', async () => {
      const user = userEvent.setup()
      renderCard({ genDefaultsMode: 'recommended' })
      await expand(user)

      const radios = screen.getAllByRole('radio') as HTMLInputElement[]
      expect(radios).toHaveLength(3)
      expect(radios.map((r) => r.value)).toEqual([
        'recommended',
        'minimum',
        'custom',
      ])
      const checked = radios.find((r) => r.checked)
      expect(checked?.value).toBe('recommended')
      // All radios share the generation-side name.
      expect(radios.every((r) => r.name === 'gen-defaults-mode')).toBe(true)
    })

    it('renders the mode labels + descriptions (one row per mode)', async () => {
      const user = userEvent.setup()
      renderCard()
      await expand(user)
      expect(
        screen.getByText('project.generationDefaults.modeRecommended')
      ).toBeInTheDocument()
      expect(
        screen.getByText('project.generationDefaults.modeRecommendedDesc')
      ).toBeInTheDocument()
      expect(
        screen.getByText('project.generationDefaults.modeMinimum')
      ).toBeInTheDocument()
      expect(
        screen.getByText('project.generationDefaults.modeCustom')
      ).toBeInTheDocument()
    })

    it('selecting a mode syncs the ref, calls the setter, and begins editing', async () => {
      const user = userEvent.setup()
      const { setGenDefaultsMode, beginEditGeneration, genDefaultsModeRef } =
        renderCard({ genDefaultsMode: 'custom', cardEditingGeneration: false })
      await expand(user)

      // The minimum radio is the 2nd one.
      const radios = screen.getAllByRole('radio')
      await user.click(radios[1])

      expect(setGenDefaultsMode).toHaveBeenCalledWith('minimum')
      expect(genDefaultsModeRef.current).toBe('minimum')
      expect(beginEditGeneration).toHaveBeenCalledTimes(1)
    })

    it('does NOT begin editing again when already editing', async () => {
      const user = userEvent.setup()
      const { setGenDefaultsMode, beginEditGeneration } = renderCard({
        genDefaultsMode: 'custom',
        cardEditingGeneration: true,
      })
      await expand(user)

      const radios = screen.getAllByRole('radio')
      await user.click(radios[0]) // recommended

      expect(setGenDefaultsMode).toHaveBeenCalledWith('recommended')
      expect(beginEditGeneration).not.toHaveBeenCalled()
    })
  })

  describe('inputs — values, disabled state, help text', () => {
    it('shows fallbacks (0 / 4000) when values are undefined', async () => {
      const user = userEvent.setup()
      renderCard({
        genDefaultTemperature: undefined,
        genDefaultMaxTokens: undefined,
      })
      await expand(user)
      expect(getTemperatureInput().value).toBe('0')
      expect(getMaxTokensInput().value).toBe('4000')
    })

    it('shows the supplied values when defined', async () => {
      const user = userEvent.setup()
      renderCard({ genDefaultTemperature: 0.7, genDefaultMaxTokens: 8000 })
      await expand(user)
      expect(getTemperatureInput().value).toBe('0.7')
      expect(getMaxTokensInput().value).toBe('8000')
    })

    it('inputs are enabled in custom mode and the custom help text shows', async () => {
      const user = userEvent.setup()
      renderCard({ genDefaultsMode: 'custom' })
      await expand(user)
      expect(getTemperatureInput().disabled).toBe(false)
      expect(getMaxTokensInput().disabled).toBe(false)
      expect(
        screen.getByText('project.generationDefaults.temperatureHelp')
      ).toBeInTheDocument()
      expect(
        screen.getByText('project.generationDefaults.maxTokensHelp')
      ).toBeInTheDocument()
    })

    it.each(['recommended', 'minimum'] as const)(
      'disables inputs and shows the override help text in %s mode',
      async (mode) => {
        const user = userEvent.setup()
        renderCard({ genDefaultsMode: mode })
        await expand(user)
        expect(getTemperatureInput().disabled).toBe(true)
        expect(getMaxTokensInput().disabled).toBe(true)
        expect(
          screen.getByText(
            'project.generationDefaults.temperatureHelpModeOverride'
          )
        ).toBeInTheDocument()
        expect(
          screen.getByText('project.generationDefaults.maxTokensHelpModeOverride')
        ).toBeInTheDocument()
        // The custom help text is NOT shown in override modes.
        expect(
          screen.queryByText('project.generationDefaults.temperatureHelp')
        ).not.toBeInTheDocument()
      }
    )

    it('temperature onChange parses a float and begins editing', async () => {
      const { setGenDefaultTemperature, beginEditGeneration } = renderCard({
        genDefaultsMode: 'custom',
        cardEditingGeneration: false,
      })
      await userEvent.setup().click(
        screen.getByRole('button', {
          name: /project\.generationDefaults\.title/i,
        })
      )
      fireEvent.change(getTemperatureInput(), { target: { value: '1.5' } })
      expect(beginEditGeneration).toHaveBeenCalledTimes(1)
      expect(setGenDefaultTemperature).toHaveBeenCalledWith(1.5)
    })

    it('max-tokens onChange parses an int and begins editing', async () => {
      const { setGenDefaultMaxTokens, beginEditGeneration } = renderCard({
        genDefaultsMode: 'custom',
        cardEditingGeneration: false,
      })
      await userEvent.setup().click(
        screen.getByRole('button', {
          name: /project\.generationDefaults\.title/i,
        })
      )
      fireEvent.change(getMaxTokensInput(), { target: { value: '12000' } })
      expect(beginEditGeneration).toHaveBeenCalledTimes(1)
      expect(setGenDefaultMaxTokens).toHaveBeenCalledWith(12000)
    })

    it('clearing temperature emits undefined (empty string branch)', async () => {
      const user = userEvent.setup()
      const { setGenDefaultTemperature } = renderCard({
        genDefaultsMode: 'custom',
        genDefaultTemperature: 0.5,
      })
      await expand(user)
      fireEvent.change(getTemperatureInput(), { target: { value: '' } })
      expect(setGenDefaultTemperature).toHaveBeenLastCalledWith(undefined)
    })

    it('clearing max-tokens emits undefined (empty string branch)', async () => {
      const user = userEvent.setup()
      const { setGenDefaultMaxTokens } = renderCard({
        genDefaultsMode: 'custom',
        genDefaultMaxTokens: 4000,
      })
      await expand(user)
      fireEvent.change(getMaxTokensInput(), { target: { value: '' } })
      expect(setGenDefaultMaxTokens).toHaveBeenLastCalledWith(undefined)
    })

    it('does not begin editing on input change when already editing', async () => {
      const user = userEvent.setup()
      const { beginEditGeneration, setGenDefaultTemperature } = renderCard({
        genDefaultsMode: 'custom',
        cardEditingGeneration: true,
      })
      await expand(user)
      fireEvent.change(getTemperatureInput(), { target: { value: '0.9' } })
      expect(setGenDefaultTemperature).toHaveBeenCalledWith(0.9)
      expect(beginEditGeneration).not.toHaveBeenCalled()
    })
  })

  describe('recommended-consensus badge', () => {
    it('is hidden entirely when no models are selected', async () => {
      const user = userEvent.setup()
      renderCard({
        selectedModelIds: [],
        genRecConsensus: {
          temperature: { value: 0.3, uniform: true, anyRec: true, perModel: [] },
          max_tokens: { value: 4000, uniform: true, anyRec: true, perModel: [] },
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
        genDefaultTemperature: 0.3, // matches -> no reset button
        genDefaultMaxTokens: 4000, // matches -> no reset button
        genRecConsensus: {
          temperature: { value: 0.3, uniform: true, anyRec: true, perModel: [] },
          max_tokens: { value: 4000, uniform: true, anyRec: true, perModel: [] },
        },
      })
      await expand(user)
      // The label + value share one text node ("…recommended: 0.3"), so match
      // by substring.
      const recs = screen.getAllByText(/generation\.controlModal\.recommended/)
      expect(recs.length).toBeGreaterThanOrEqual(2)
      // Value 0.3 is rendered next to the temperature label.
      expect(screen.getByText(/recommended.*0\.3/)).toBeInTheDocument()
      // Values match defaults -> no reset-to-recommended button.
      expect(
        screen.queryByText('generation.controlModal.resetToRecommended')
      ).not.toBeInTheDocument()
    })

    it('shows a reset button when the current value differs, and clicking it resets', async () => {
      const user = userEvent.setup()
      const { setGenDefaultTemperature } = renderCard({
        selectedModelIds: ['m1'],
        genDefaultTemperature: 1.0, // differs from rec 0.3 -> reset shows
        genDefaultMaxTokens: 4000, // matches -> no reset on this side
        genRecConsensus: {
          temperature: { value: 0.3, uniform: true, anyRec: true, perModel: [] },
          max_tokens: { value: 4000, uniform: true, anyRec: true, perModel: [] },
        },
      })
      await expand(user)
      const resetBtn = screen.getByRole('button', {
        name: 'generation.controlModal.resetToRecommended',
      })
      await user.click(resetBtn)
      expect(setGenDefaultTemperature).toHaveBeenCalledWith(0.3)
    })

    it('reset button on max-tokens uses the 4000 fallback when value is undefined', async () => {
      const user = userEvent.setup()
      const { setGenDefaultMaxTokens } = renderCard({
        selectedModelIds: ['m1'],
        genDefaultMaxTokens: undefined, // (undefined ?? 4000) !== 8000 -> reset shows
        genDefaultTemperature: 0, // (0 ?? 0) === 0 rec, no reset
        genRecConsensus: {
          temperature: { value: 0, uniform: true, anyRec: true, perModel: [] },
          max_tokens: { value: 8000, uniform: true, anyRec: true, perModel: [] },
        },
      })
      await expand(user)
      const resetBtn = screen.getByRole('button', {
        name: 'generation.controlModal.resetToRecommended',
      })
      await user.click(resetBtn)
      expect(setGenDefaultMaxTokens).toHaveBeenCalledWith(8000)
    })

    it('temperature reset uses the 0 fallback when value is undefined', async () => {
      const user = userEvent.setup()
      const { setGenDefaultTemperature } = renderCard({
        selectedModelIds: ['m1'],
        genDefaultTemperature: undefined, // (undefined ?? 0) !== 0.5 -> reset shows
        genDefaultMaxTokens: 4000, // matches -> no reset on this side
        genRecConsensus: {
          temperature: { value: 0.5, uniform: true, anyRec: true, perModel: [] },
          max_tokens: { value: 4000, uniform: true, anyRec: true, perModel: [] },
        },
      })
      await expand(user)
      await user.click(
        screen.getByRole('button', {
          name: 'generation.controlModal.resetToRecommended',
        })
      )
      expect(setGenDefaultTemperature).toHaveBeenCalledWith(0.5)
    })

    it('shows the divergent badge with a per-model title when recs differ', async () => {
      const user = userEvent.setup()
      renderCard({
        selectedModelIds: ['m1', 'm2'],
        genRecConsensus: {
          temperature: {
            value: undefined,
            uniform: false,
            anyRec: true,
            perModel: [
              { model: 'm1', value: 0.2 },
              { model: 'm2', value: 0.9 },
            ],
          },
          max_tokens: {
            value: undefined,
            uniform: false,
            anyRec: true,
            perModel: [
              { model: 'm1', value: 1000 },
              { model: 'm2', value: undefined },
            ],
          },
        },
      })
      await expand(user)
      const divergent = screen.getAllByText(
        'generation.controlModal.divergentRecommendations'
      )
      expect(divergent).toHaveLength(2)
      // Temperature tooltip lists both models' values.
      expect(divergent[0]).toHaveAttribute('title', 'm1: 0.2\nm2: 0.9')
      // Max-tokens tooltip renders the em-dash for the missing value.
      expect(divergent[1]).toHaveAttribute('title', 'm1: 1000\nm2: —')
    })

    it('shows the "no recommendation" badge when nothing is recommended', async () => {
      const user = userEvent.setup()
      renderCard({
        selectedModelIds: ['m1'],
        genRecConsensus: emptyConsensus(),
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
        genRecConsensus: {
          // uniform true but value undefined -> first branch fails, anyRec false
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

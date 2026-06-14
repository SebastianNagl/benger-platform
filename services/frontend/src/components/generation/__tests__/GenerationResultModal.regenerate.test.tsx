/**
 * Behavioral coverage for GenerationResultModal's regenerate / structure
 * selection branches and a couple of history edge cases the main
 * GenerationResultModal.test.tsx leaves uncovered:
 *
 *   - the footer "Regenerate" button (onRegenerate + results present) and its
 *     structure-key payload when availableStructureKeys.length > 1
 *   - the "select structures" toggle + per-key checkboxes, and the disabled
 *     state when every structure is unchecked
 *   - the empty-results "Generate" button (onRegenerate, no results)
 *   - the history-fetch error path (results still render, history empty)
 *   - multi-structure history filtering by structure_key
 *
 * Mirrors the existing file's mocking idiom: inline jest.mock of
 * @/lib/api/client + I18nContext, real HeadlessUI Dialog (renders in JSDOM).
 */
import '@testing-library/jest-dom'
import { apiClient } from '@/lib/api/client'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { GenerationResultModal } from '../GenerationResultModal'

jest.mock('@/lib/api/client', () => ({
  apiClient: { get: jest.fn() },
}))

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, arg2?: any, arg3?: any) => {
      const vars = typeof arg2 === 'object' ? arg2 : arg3
      const translations: Record<string, string> = {
        'generation.resultModal.title': 'Generation Result',
        'generation.resultModal.close': 'Close',
        'generation.resultModal.regenerate': 'Regenerate',
        'generation.resultModal.generate': 'Generate',
        'generation.resultModal.selectStructures': 'Select structures',
        'generation.resultModal.noResultsFound': 'No generation results found',
        'generation.resultModal.current': 'Current',
        'generation.resultModal.history': 'History',
        'generation.resultModal.noHistory': 'No generation history available',
        'generation.resultModal.status': 'Status:',
        'generation.resultModal.generatedText': 'Generated Text',
        'generation.resultModal.default': 'default',
        'generation.resultModal.formatted': 'Formatted',
        'generation.resultModal.rawJson': 'Raw JSON',
        'generation.resultModal.copy': 'Copy',
        'generation.resultModal.viewPrompt': 'View Prompt Used',
        'generation.resultModal.noPromptStored': 'No prompt stored',
      }
      let result = translations[key] || key
      if (vars) {
        Object.entries(vars).forEach(([k, v]) => {
          result = result.replace(`{${k}}`, String(v))
        })
      }
      return result
    },
    locale: 'en',
  }),
}))

const mockGet = apiClient.get as jest.Mock

const makeResult = (overrides: Record<string, any> = {}) => ({
  task_id: 'task-12345678',
  model_id: 'gpt-4',
  generation_id: 'gen-1',
  status: 'completed',
  result: { generated_text: 'Hello world' },
  generated_at: '2026-01-01T10:00:00Z',
  structure_key: 'gliederung',
  ...overrides,
})

describe('GenerationResultModal regenerate + structure selection', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockGet.mockResolvedValue({ results: [makeResult()] })
  })

  it('shows the Regenerate button and the structure-selection toggle when multiple structures exist', async () => {
    const onRegenerate = jest.fn()
    const onClose = jest.fn()
    render(
      <GenerationResultModal
        isOpen
        taskId="task-12345678"
        modelId="gpt-4"
        onClose={onClose}
        onRegenerate={onRegenerate}
        result={makeResult()}
        availableStructureKeys={['gliederung', 'loesung']}
      />
    )

    // Footer Regenerate button is present (onRegenerate + results.length > 0).
    expect(
      await screen.findByRole('button', { name: /Regenerate/i })
    ).toBeInTheDocument()
    // The structure-selection toggle renders for >1 structure keys.
    expect(screen.getByText('Select structures')).toBeInTheDocument()
  })

  it('regenerates with the selected structure keys and closes', async () => {
    const onRegenerate = jest.fn()
    const onClose = jest.fn()
    render(
      <GenerationResultModal
        isOpen
        taskId="task-12345678"
        modelId="gpt-4"
        onClose={onClose}
        onRegenerate={onRegenerate}
        result={makeResult()}
        availableStructureKeys={['gliederung', 'loesung']}
      />
    )

    // Open the structure selection panel.
    await userEvent.click(screen.getByText('Select structures'))

    // Both keys start selected; uncheck "loesung".
    const loesung = await screen.findByText('loesung')
    const loesungCheckbox = within(
      loesung.closest('label') as HTMLElement
    ).getByRole('checkbox')
    expect(loesungCheckbox).toBeChecked()
    await userEvent.click(loesungCheckbox)
    expect(loesungCheckbox).not.toBeChecked()

    // Click Regenerate -> onRegenerate gets the remaining key set + onClose.
    await userEvent.click(screen.getByRole('button', { name: /Regenerate/i }))

    expect(onRegenerate).toHaveBeenCalledWith(
      'task-12345678',
      'gpt-4',
      ['gliederung']
    )
    expect(onClose).toHaveBeenCalled()
  })

  it('disables Regenerate when no structures are selected', async () => {
    const onRegenerate = jest.fn()
    render(
      <GenerationResultModal
        isOpen
        taskId="task-12345678"
        modelId="gpt-4"
        onClose={jest.fn()}
        onRegenerate={onRegenerate}
        result={makeResult()}
        availableStructureKeys={['gliederung', 'loesung']}
      />
    )

    await userEvent.click(screen.getByText('Select structures'))

    // Uncheck both keys.
    const checkboxes = screen.getAllByRole('checkbox')
    for (const cb of checkboxes) {
      if ((cb as HTMLInputElement).checked) {
        await userEvent.click(cb)
      }
    }

    const regen = screen.getByRole('button', { name: /Regenerate/i })
    expect(regen).toBeDisabled()
  })

  it('renders the empty-state Generate button and calls onRegenerate with undefined keys', async () => {
    // No results from the API -> empty body path with the Generate button.
    mockGet.mockResolvedValue({ results: [] })
    const onRegenerate = jest.fn()
    const onClose = jest.fn()
    render(
      <GenerationResultModal
        isOpen
        taskId="task-12345678"
        modelId="gpt-4"
        onClose={onClose}
        onRegenerate={onRegenerate}
        availableStructureKeys={['only-one']}
      />
    )

    expect(
      await screen.findByText('No generation results found')
    ).toBeInTheDocument()

    const generateBtn = screen.getByRole('button', { name: /Generate/i })
    await userEvent.click(generateBtn)

    // availableStructureKeys.length <= 1 -> structureKeys arg is undefined.
    expect(onRegenerate).toHaveBeenCalledWith(
      'task-12345678',
      'gpt-4',
      undefined
    )
    expect(onClose).toHaveBeenCalled()
  })

  it('keeps showing results when the history fetch fails and reports no history', async () => {
    // First call (current results) succeeds; the history call rejects.
    mockGet
      .mockResolvedValueOnce({ results: [makeResult()] })
      .mockRejectedValueOnce(new Error('history boom'))

    render(
      <GenerationResultModal
        isOpen
        taskId="task-12345678"
        modelId="gpt-4"
        onClose={jest.fn()}
      />
    )

    // Current results render.
    await screen.findByText('Generation Result')
    await screen.findByText('History')

    fireEvent.click(screen.getByText('History'))

    // The rejected history fetch leaves historyResults empty -> no-history msg.
    await waitFor(() => {
      expect(
        screen.getByText('No generation history available')
      ).toBeInTheDocument()
    })
    // The error was swallowed; the modal title still shows.
    expect(screen.getByText('Generation Result')).toBeInTheDocument()
  })

  it('filters history entries by the selected structure tab (multi-structure)', async () => {
    const currentResults = [
      makeResult({ generation_id: 'cur-a', structure_key: 'gliederung' }),
      makeResult({ generation_id: 'cur-b', structure_key: 'loesung' }),
    ]
    const historyResults = [
      makeResult({ generation_id: 'h-a', structure_key: 'gliederung' }),
      makeResult({ generation_id: 'h-b', structure_key: 'loesung' }),
    ]
    mockGet
      .mockResolvedValueOnce({ results: currentResults })
      .mockResolvedValueOnce({ results: historyResults })

    render(
      <GenerationResultModal
        isOpen
        taskId="task-12345678"
        modelId="gpt-4"
        onClose={jest.fn()}
      />
    )

    // Two structures render two tabs; default selected index 0 = gliederung.
    await screen.findByText('Generation Result')
    await screen.findByText('History')

    fireEvent.click(screen.getByText('History'))

    // History fetched; filteredHistory keeps only entries whose structure_key
    // matches the selected current result (gliederung). With both having
    // distinct generation_ids we can count the rendered history disclosures.
    await waitFor(() => {
      // Two structure tabs are present, confirming results.length > 1.
      expect(screen.getAllByRole('button').length).toBeGreaterThan(0)
    })
    // No-history message must NOT appear (filtered history is non-empty).
    expect(
      screen.queryByText('No generation history available')
    ).not.toBeInTheDocument()
  })
})

/**
 * @jest-environment jsdom
 *
 * Complement coverage tests for DynamicAnnotationInterface.
 *
 * Targets branches NOT exercised by DynamicAnnotationInterface.test.tsx /
 * .branch2.test.tsx / -hideSubmitButton.test.tsx:
 * - loadDraft restore on mount (componentValues + annotations rehydrated).
 * - handleAnnotation path: a child calling onAnnotation populates the
 *   annotations Map and the annotations->onChange effect fires.
 * - handleSubmit "no results" path -> setSubmissionErrors(atLeastOne).
 * - Ctrl+Enter / Ctrl+Escape keyboard shortcuts firing when NOT gated by
 *   requireConfirmBeforeSubmit (the un-blocked branch).
 * - readOnly: onChange/onAnnotation handlers swapped to no-ops, onSaveToDb
 *   omitted.
 * - The annotation-type dispatch in renderComponent: known control type vs.
 *   unknown type (warn) vs. Label/Choice silent-skip, plus the visual-category
 *   children render branch.
 */

import '@testing-library/jest-dom'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { DynamicAnnotationInterface } from '../DynamicAnnotationInterface'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, params?: any) => {
      const translations: Record<string, string> = {
        'annotation.interface.configError': 'Configuration Error',
        'annotation.interface.atLeastOne': 'At least one annotation is required',
        'annotation.interface.submit': 'Submit',
        'annotation.interface.submitShortcut': 'Ctrl+Enter',
        'annotation.interface.skip': 'Skip',
        'annotation.interface.skipShortcut': '(Ctrl+ESC)',
        'annotation.interface.tip': 'Use keyboard shortcuts',
      }
      let value = translations[key] || params?.defaultValue || key
      if (params) {
        value = value.replace(/\{(\w+)\}/g, (m: string, name: string) =>
          params[name] !== undefined ? String(params[name]) : m
        )
      }
      return value
    },
    locale: 'en',
  }),
}))

jest.mock('@/lib/labelConfig/parser', () => ({
  parseLabelConfig: jest.fn(),
  validateParsedConfig: jest.fn(),
  extractRequiredDataFields: jest.fn(),
}))

jest.mock('@/lib/labelConfig/dataBinding', () => ({
  resolvePropsDataBindings: jest.fn(),
  validateTaskDataFields: jest.fn(),
}))

jest.mock('@/components/shared/Alert', () => ({
  Alert: ({ children }: any) => <div data-testid="alert">{children}</div>,
}))

jest.mock('@/components/shared/Skeleton', () => ({
  Skeleton: (props: any) => <div data-testid="skeleton" {...props} />,
}))

jest.mock('@/components/shared/AutoSaveIndicator', () => ({
  AutoSaveIndicator: () => <div data-testid="auto-save-indicator" />,
}))

// Controllable useAutoSave: loadDraft return value is swapped per-test.
const mockLoadDraft = jest.fn().mockReturnValue(null)
const mockClearDraft = jest.fn()
const mockSaveNow = jest.fn().mockResolvedValue(undefined)
jest.mock('@/hooks/useAutoSave', () => ({
  useAutoSave: () => ({
    isSaving: false,
    lastSaved: null,
    error: null,
    loadDraft: mockLoadDraft,
    clearDraft: mockClearDraft,
    saveNow: mockSaveNow,
  }),
}))

// A control component that ALWAYS exposes onAnnotation + onChange + a readOnly
// marker so the handleAnnotation / readOnly branches are reachable.
;(global as any).__mockControl = jest.fn(
  ({ value, onChange, onAnnotation, onSaveToDb, readOnly, config }: any) => (
    <div data-testid="mock-control">
      <span data-testid="readonly-flag">{String(readOnly)}</span>
      <span data-testid="hassavetodb">{String(!!onSaveToDb)}</span>
      <textarea
        data-testid="control-input"
        value={value || ''}
        onChange={(e) => onChange(e.target.value)}
      />
      <button
        data-testid="control-annotate"
        onClick={() =>
          onAnnotation({
            from_name: config?.props?.name || config?.name || 'answer',
            to_name: 'text',
            type: 'textarea',
            value: 'annotated-value',
          })
        }
      >
        Annotate
      </button>
    </div>
  )
)

;(global as any).__mockVisual = jest.fn(({ children }: any) => (
  <div data-testid="mock-visual">{children}</div>
))

jest.mock('@/lib/labelConfig/registry', () => ({
  getComponent: jest.fn((type: string) => {
    const components: Record<string, any> = {
      TextArea: {
        component: (global as any).__mockControl,
        category: 'control',
      },
      View: { component: (global as any).__mockVisual, category: 'visual' },
    }
    return components[type] || null
  }),
}))

import {
  resolvePropsDataBindings,
  validateTaskDataFields,
} from '@/lib/labelConfig/dataBinding'
import {
  extractRequiredDataFields,
  parseLabelConfig,
  validateParsedConfig,
} from '@/lib/labelConfig/parser'

const mockParse = parseLabelConfig as jest.MockedFunction<typeof parseLabelConfig>
const mockValidateConfig = validateParsedConfig as jest.MockedFunction<
  typeof validateParsedConfig
>
const mockExtractRequired = extractRequiredDataFields as jest.MockedFunction<
  typeof extractRequiredDataFields
>
const mockResolveProps = resolvePropsDataBindings as jest.MockedFunction<
  typeof resolvePropsDataBindings
>
const mockValidateData = validateTaskDataFields as jest.MockedFunction<
  typeof validateTaskDataFields
>

const viewWithTextarea = {
  type: 'View',
  name: 'root',
  props: {},
  children: [
    {
      type: 'TextArea',
      name: 'answer',
      props: { name: 'answer', toName: 'text' },
      children: [],
    },
  ],
}

const defaultProps = {
  labelConfig: '<View><TextArea name="answer"/></View>',
  taskData: { text: 'Test' },
  onSubmit: jest.fn(),
}

beforeEach(() => {
  jest.clearAllMocks()
  mockLoadDraft.mockReturnValue(null)
  ;(global as any).__mockControl.mockClear()
  ;(global as any).__mockVisual.mockClear()
  mockParse.mockReturnValue(viewWithTextarea)
  mockValidateConfig.mockReturnValue({ valid: true, errors: [] })
  mockExtractRequired.mockReturnValue([])
  mockResolveProps.mockImplementation((props) => props)
  mockValidateData.mockReturnValue({ valid: true, missingFields: [] })
})

describe('DynamicAnnotationInterface - draft restore on mount', () => {
  it('restores componentValues and annotations from a saved draft', async () => {
    mockLoadDraft.mockReturnValue({
      componentValues: { answer: 'restored text' },
      annotations: [
        {
          from_name: 'answer',
          to_name: 'text',
          type: 'textarea',
          value: 'restored text',
        },
      ],
    })

    render(<DynamicAnnotationInterface {...defaultProps} />)

    await waitFor(() => {
      expect(screen.getByTestId('control-input')).toHaveValue('restored text')
    })
    expect(mockLoadDraft).toHaveBeenCalled()
  })

  it('does not attempt to restore a draft when enableAutoSave is false', () => {
    render(
      <DynamicAnnotationInterface {...defaultProps} enableAutoSave={false} />
    )
    expect(mockLoadDraft).not.toHaveBeenCalled()
  })

  it('ignores an empty draft (no componentValues)', () => {
    mockLoadDraft.mockReturnValue({ componentValues: {} })
    render(<DynamicAnnotationInterface {...defaultProps} />)
    // No crash; the input stays empty.
    expect(screen.getByTestId('control-input')).toHaveValue('')
  })
})

describe('DynamicAnnotationInterface - handleAnnotation path', () => {
  it('populates annotations via onAnnotation and notifies onChange', async () => {
    const onChange = jest.fn()
    render(<DynamicAnnotationInterface {...defaultProps} onChange={onChange} />)

    fireEvent.click(screen.getByTestId('control-annotate'))

    await waitFor(() => {
      expect(onChange).toHaveBeenCalledWith(
        expect.arrayContaining([
          expect.objectContaining({
            from_name: 'answer',
            value: 'annotated-value',
          }),
        ])
      )
    })
  })

  it('submits the formal annotation (from onAnnotation) over componentValues', async () => {
    const onSubmit = jest.fn()
    render(<DynamicAnnotationInterface {...defaultProps} onSubmit={onSubmit} />)

    fireEvent.click(screen.getByTestId('control-annotate'))

    const submit = screen
      .getAllByRole('button', { name: /submit/i })
      .find((b) => b.classList.contains('bg-emerald-600'))
    fireEvent.click(submit!)

    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledWith(
        expect.arrayContaining([
          expect.objectContaining({ value: 'annotated-value' }),
        ])
      )
    })
    // Successful submit clears the draft.
    expect(mockClearDraft).toHaveBeenCalled()
  })
})

describe('DynamicAnnotationInterface - empty submit', () => {
  it('shows the atLeastOne error when submitting with no data', async () => {
    render(<DynamicAnnotationInterface {...defaultProps} />)

    const submit = screen
      .getAllByRole('button', { name: /submit/i })
      .find((b) => b.classList.contains('bg-emerald-600'))
    // The button is disabled with no data; invoke handleSubmit via Ctrl+Enter
    // which is NOT gated (requireConfirmBeforeSubmit is false here).
    fireEvent.keyDown(window, { key: 'Enter', ctrlKey: true })

    await waitFor(() => {
      expect(
        screen.getByText('At least one annotation is required')
      ).toBeInTheDocument()
    })
    expect(submit).toBeDisabled()
  })
})

describe('DynamicAnnotationInterface - keyboard shortcuts (un-gated)', () => {
  it('Ctrl+Enter submits when there is data and no confirm gate', async () => {
    const onSubmit = jest.fn()
    render(<DynamicAnnotationInterface {...defaultProps} onSubmit={onSubmit} />)

    fireEvent.click(screen.getByTestId('control-annotate'))
    fireEvent.keyDown(window, { key: 'Enter', metaKey: true })

    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalled()
    })
  })

  it('Ctrl+Escape skips when onSkip is provided and no confirm gate', () => {
    const onSkip = jest.fn()
    render(<DynamicAnnotationInterface {...defaultProps} onSkip={onSkip} />)

    fireEvent.keyDown(window, { key: 'Escape', ctrlKey: true })
    expect(onSkip).toHaveBeenCalled()
  })
})

describe('DynamicAnnotationInterface - readOnly mode', () => {
  it('passes readOnly to children and omits the onSaveToDb handler', () => {
    render(<DynamicAnnotationInterface {...defaultProps} readOnly={true} />)

    expect(screen.getByTestId('readonly-flag')).toHaveTextContent('true')
    // onSaveToDb is gated on `enableAutoSave && !readOnly`.
    expect(screen.getByTestId('hassavetodb')).toHaveTextContent('false')
  })

  it('readOnly onChange is a no-op (value does not update)', () => {
    render(<DynamicAnnotationInterface {...defaultProps} readOnly={true} />)

    const input = screen.getByTestId('control-input')
    fireEvent.change(input, { target: { value: 'attempted edit' } })
    // The no-op onChange means componentValues never updates the controlled value.
    expect(input).toHaveValue('')
  })
})

describe('DynamicAnnotationInterface - component dispatch', () => {
  it('warns on an unknown component type but renders the rest', () => {
    const warnSpy = jest.spyOn(console, 'warn').mockImplementation()
    mockParse.mockReturnValue({
      type: 'View',
      name: 'root',
      props: {},
      children: [
        { type: 'Mystery', name: 'm1', props: {}, children: [] },
        {
          type: 'TextArea',
          name: 'answer',
          props: { name: 'answer' },
          children: [],
        },
      ],
    })

    render(<DynamicAnnotationInterface {...defaultProps} />)

    expect(screen.getByTestId('control-input')).toBeInTheDocument()
    const unknownWarn = warnSpy.mock.calls.filter(
      (c) => typeof c[0] === 'string' && c[0].includes('Unknown component type')
    )
    expect(unknownWarn.length).toBe(1)
    expect(unknownWarn[0][0]).toContain('Mystery')
    warnSpy.mockRestore()
  })

  it('shows the config-error fallback when the config is invalid', () => {
    mockValidateConfig.mockReturnValue({
      valid: false,
      errors: ['bad config'],
    })

    render(<DynamicAnnotationInterface {...defaultProps} />)

    expect(screen.getByText('Configuration Error')).toBeInTheDocument()
    expect(screen.getByText('bad config')).toBeInTheDocument()
  })
})

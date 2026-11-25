/**
 * @jest-environment jsdom
 *
 * The annotation form shows in one step: while the code of its field types
 * loads it shows one placeholder, then every field at once, instead of a
 * placeholder per field that each swap for the field as its code arrives.
 */

import '@testing-library/jest-dom'
import { act, render, screen } from '@testing-library/react'
import { DynamicAnnotationInterface } from '../DynamicAnnotationInterface'

let mockLocale: 'de' | 'en' = 'de'
jest.mock('@/contexts/I18nContext', () => {
  const trees: Record<string, unknown> = {
    de: require('@/locales/de/common.json'),
    en: require('@/locales/en/common.json'),
  }
  const lookup = (tree: unknown, key: string) =>
    key
      .split('.')
      .reduce<unknown>(
        (v, k) =>
          v && typeof v === 'object'
            ? (v as Record<string, unknown>)[k]
            : undefined,
        tree,
      )
  return {
    useI18n: () => ({
      t: (key: string) => {
        const value = lookup(trees[mockLocale], key)
        return typeof value === 'string' ? value : key
      },
      locale: mockLocale,
    }),
  }
})

jest.mock('@/lib/labelConfig/parser', () => ({
  parseLabelConfig: jest.fn(() => ({
    type: 'View',
    name: 'root',
    props: {},
    children: [
      { type: 'Text', name: 'text', props: {}, children: [] },
      { type: 'TextArea', name: 'answer', props: {}, children: [] },
    ],
  })),
  validateParsedConfig: jest.fn(() => ({ valid: true, errors: [] })),
  extractRequiredDataFields: jest.fn(() => []),
}))

jest.mock('@/lib/labelConfig/dataBinding', () => ({
  resolvePropsDataBindings: jest.fn((props: unknown) => props),
  validateTaskDataFields: jest.fn(() => ({ valid: true, missingFields: [] })),
}))

const mockLoaded: Record<string, boolean> = {}
const mockPending: Record<string, () => void> = {}
jest.mock('@/lib/labelConfig/registry', () => ({
  getComponent: jest.fn((type: string) => ({
    component: ({ children }: any) => (
      <div data-testid={`field-${type}`}>{children}</div>
    ),
    category: type === 'View' ? 'visual' : 'control',
    isLoaded: () => mockLoaded[type] === true,
    preload: () =>
      mockLoaded[type]
        ? Promise.resolve()
        : new Promise<void>((resolve) => {
            mockPending[type] = () => {
              mockLoaded[type] = true
              resolve()
            }
          }),
  })),
}))

jest.mock('@/components/shared/AutoSaveIndicator', () => ({
  AutoSaveIndicator: () => null,
}))

jest.mock('@/hooks/useAutoSave', () => ({
  useAutoSave: () => ({
    isSaving: false,
    lastSaved: null,
    error: null,
    loadDraft: () => null,
    clearDraft: jest.fn(),
    saveNow: jest.fn(),
  }),
}))

const props = {
  labelConfig: '<View/>',
  taskData: { text: 'Fall' },
  onSubmit: jest.fn(),
}

beforeEach(() => {
  for (const key of Object.keys(mockLoaded)) delete mockLoaded[key]
  for (const key of Object.keys(mockPending)) delete mockPending[key]
})

describe('DynamicAnnotationInterface field loading', () => {
  it('shows one placeholder until every field type is loaded, then all fields', async () => {
    render(<DynamicAnnotationInterface {...props} />)
    expect(screen.getByTestId('annotation-fields-loading')).toBeInTheDocument()
    expect(screen.queryByTestId('field-View')).not.toBeInTheDocument()

    await act(async () => mockPending.View())
    await act(async () => mockPending.Text())
    // One type still loading: still the placeholder, no partial form.
    expect(screen.getByTestId('annotation-fields-loading')).toBeInTheDocument()
    expect(screen.queryByTestId('field-Text')).not.toBeInTheDocument()

    await act(async () => mockPending.TextArea())
    expect(
      screen.queryByTestId('annotation-fields-loading'),
    ).not.toBeInTheDocument()
    expect(screen.getByTestId('field-View')).toBeInTheDocument()
    expect(screen.getByTestId('field-Text')).toBeInTheDocument()
    expect(screen.getByTestId('field-TextArea')).toBeInTheDocument()
  })

  it('renders the fields in its first frame when their code is already loaded', () => {
    mockLoaded.View = mockLoaded.Text = mockLoaded.TextArea = true
    render(<DynamicAnnotationInterface {...props} />)
    expect(
      screen.queryByTestId('annotation-fields-loading'),
    ).not.toBeInTheDocument()
    expect(screen.getByTestId('field-TextArea')).toBeInTheDocument()
  })
})

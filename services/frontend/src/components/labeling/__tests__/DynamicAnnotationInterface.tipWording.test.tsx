/**
 * @jest-environment jsdom
 *
 * The keyboard-shortcut tip under the annotation interface. The same
 * component renders in the expert labeling page (formal "Sie") and in the
 * student exam editor (informal "du"), so the tip is worded neutrally: it
 * addresses nobody. Rendered with the real German and English locale texts.
 */

import '@testing-library/jest-dom'
import { render, screen } from '@testing-library/react'
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
    children: [],
  })),
  validateParsedConfig: jest.fn(() => ({ valid: true, errors: [] })),
  extractRequiredDataFields: jest.fn(() => []),
}))

jest.mock('@/lib/labelConfig/dataBinding', () => ({
  resolvePropsDataBindings: jest.fn((props: unknown) => props),
  validateTaskDataFields: jest.fn(() => ({ valid: true, missingFields: [] })),
}))

jest.mock('@/lib/labelConfig/registry', () => ({
  getComponent: jest.fn(() => ({
    component: ({ children }: any) => <div>{children}</div>,
    category: 'visual',
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

// Formal and informal address, as whole words.
const FORMAL = /\b(Sie|Ihnen|Ihr\w*)\b/
const INFORMAL = /\b(du|dich|dir|dein\w*)\b/i

describe('DynamicAnnotationInterface keyboard tip', () => {
  it('addresses nobody in German, so it fits the expert and the student editor', () => {
    mockLocale = 'de'
    render(<DynamicAnnotationInterface {...props} />)
    const tip = screen.getByText(/^Tipp:/)
    expect(tip).toHaveTextContent('Tastenkombinationen')
    expect(tip.textContent).not.toMatch(FORMAL)
    expect(tip.textContent).not.toMatch(INFORMAL)
    expect(tip.textContent).not.toContain('Verwenden Sie')
  })

  it('has an English text as well', () => {
    mockLocale = 'en'
    render(<DynamicAnnotationInterface {...props} />)
    expect(screen.getByText(/^Tip:/)).toHaveTextContent(/keyboard shortcuts/i)
  })
})

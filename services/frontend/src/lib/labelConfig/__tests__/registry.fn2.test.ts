/**
 * Additional function coverage for registry.ts
 * Covers: getComponent, isTagSupported, getSupportedTags, registerComponent,
 * createComponentInstance, and remaining extractValue functions
 */

import {
  componentRegistry,
  getComponent,
  isTagSupported,
  getSupportedTags,
  registerComponent,
  createComponentInstance,
} from '../registry'

describe('registry - exported utility functions', () => {
  describe('getComponent', () => {
    it('returns component for registered tag', () => {
      const result = getComponent('Text')
      expect(result).toBeDefined()
      expect(result?.category).toBe('object')
    })

    it('returns component for control tag', () => {
      const result = getComponent('Choices')
      expect(result).toBeDefined()
      expect(result?.category).toBe('control')
    })

    it('returns undefined for unknown tag', () => {
      const result = getComponent('NonExistentTag')
      expect(result).toBeUndefined()
    })

    it('returns visual component', () => {
      const result = getComponent('View')
      expect(result).toBeDefined()
      expect(result?.category).toBe('visual')
    })
  })

  describe('isTagSupported', () => {
    it('returns true for supported tags', () => {
      expect(isTagSupported('Text')).toBe(true)
      expect(isTagSupported('Image')).toBe(true)
      expect(isTagSupported('TextArea')).toBe(true)
      expect(isTagSupported('Choices')).toBe(true)
      expect(isTagSupported('Labels')).toBe(true)
      expect(isTagSupported('Rating')).toBe(true)
      expect(isTagSupported('Likert')).toBe(true)
      expect(isTagSupported('Number')).toBe(true)
      expect(isTagSupported('View')).toBe(true)
      expect(isTagSupported('Header')).toBe(true)
      expect(isTagSupported('Style')).toBe(true)
    })

    it('returns false for unsupported tags', () => {
      expect(isTagSupported('FooBar')).toBe(false)
      expect(isTagSupported('')).toBe(false)
      expect(isTagSupported('text')).toBe(false) // case-sensitive
    })
  })

  describe('getSupportedTags', () => {
    it('returns all tags when no category specified', () => {
      const tags = getSupportedTags()
      expect(tags).toContain('Text')
      expect(tags).toContain('Image')
      expect(tags).toContain('Choices')
      expect(tags).toContain('View')
      expect(tags.length).toBeGreaterThan(10)
    })

    it('returns only object tags', () => {
      const tags = getSupportedTags('object')
      expect(tags).toContain('Text')
      expect(tags).toContain('Image')
      expect(tags).not.toContain('Choices')
      expect(tags).not.toContain('View')
    })

    it('returns only control tags', () => {
      const tags = getSupportedTags('control')
      expect(tags).toContain('Choices')
      expect(tags).toContain('TextArea')
      expect(tags).toContain('Rating')
      expect(tags).not.toContain('Text')
      expect(tags).not.toContain('View')
    })

    it('returns only visual tags', () => {
      const tags = getSupportedTags('visual')
      expect(tags).toContain('View')
      expect(tags).toContain('Header')
      expect(tags).toContain('Style')
      expect(tags).not.toContain('Text')
      expect(tags).not.toContain('Choices')
    })
  })

  describe('registerComponent', () => {
    it('registers a new component', () => {
      const mockComponent = {
        component: (() => null) as any,
        category: 'control' as const,
      }

      registerComponent('CustomTag', mockComponent)
      expect(componentRegistry['CustomTag']).toBe(mockComponent)
      expect(isTagSupported('CustomTag')).toBe(true)

      // Clean up
      delete componentRegistry['CustomTag']
    })

    it('overrides existing component', () => {
      const originalComponent = getComponent('Text')
      const mockComponent = {
        component: (() => null) as any,
        category: 'object' as const,
      }

      registerComponent('Text', mockComponent)
      expect(componentRegistry['Text']).toBe(mockComponent)

      // Restore original
      if (originalComponent) {
        componentRegistry['Text'] = originalComponent
      }
    })
  })

  describe('createComponentInstance', () => {
    it('returns null for unknown component type', () => {
      const config = { type: 'UnknownType', name: 'test', attrs: {}, children: [] }
      const result = createComponentInstance(
        config,
        {},
        jest.fn(),
        jest.fn()
      )
      expect(result).toBeNull()
    })

    it('creates element for known component type', () => {
      const config = { type: 'Text', name: 'test', attrs: { value: '$text' }, children: [] }
      const result = createComponentInstance(
        config,
        { text: 'Hello' },
        jest.fn(),
        jest.fn()
      )
      expect(result).not.toBeNull()
    })
  })

  describe('extractValue functions', () => {
    it('TextArea extractValue wraps in text array', () => {
      const extract = componentRegistry.TextArea.extractValue!
      expect(extract('hello')).toEqual({ text: ['hello'] })
    })

    it('Choices extractValue wraps single value in array', () => {
      const extract = componentRegistry.Choices.extractValue!
      expect(extract('option1')).toEqual({ choices: ['option1'] })
    })

    it('Choices extractValue keeps array as-is', () => {
      const extract = componentRegistry.Choices.extractValue!
      expect(extract(['a', 'b'])).toEqual({ choices: ['a', 'b'] })
    })

    it('Labels extractValue passes through value', () => {
      const extract = componentRegistry.Labels.extractValue!
      const val = { start: 0, end: 5, labels: ['PER'] }
      expect(extract(val)).toEqual(val)
    })

    it('Rating extractValue wraps in rating object', () => {
      const extract = componentRegistry.Rating.extractValue!
      expect(extract(4)).toEqual({ rating: 4 })
    })

    it('Likert extractValue wraps in likert object', () => {
      const extract = componentRegistry.Likert.extractValue!
      expect(extract(3)).toEqual({ likert: 3 })
    })

    it('Number extractValue wraps in number object', () => {
      const extract = componentRegistry.Number.extractValue!
      expect(extract(42)).toEqual({ number: 42 })
    })
  })
})

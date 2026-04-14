/**
 * @jest-environment jsdom
 */

import React from 'react'
import { ParsedComponent } from '../parser'
import {
  AnnotationComponent,
  AnnotationComponentProps,
  componentRegistry,
  createComponentInstance,
  getComponent,
  getSupportedTags,
  isTagSupported,
  registerComponent,
} from '../registry'

describe('registry', () => {
  describe('componentRegistry', () => {
    it('should contain all object tags', () => {
      expect(componentRegistry.Text).toBeDefined()
      expect(componentRegistry.Text.category).toBe('object')
      expect(componentRegistry.Image).toBeDefined()
      expect(componentRegistry.Image.category).toBe('object')
    })

    it('should contain all control tags', () => {
      expect(componentRegistry.TextArea).toBeDefined()
      expect(componentRegistry.TextArea.category).toBe('control')
      expect(componentRegistry.Choices).toBeDefined()
      expect(componentRegistry.Choices.category).toBe('control')
      expect(componentRegistry.Labels).toBeDefined()
      expect(componentRegistry.Labels.category).toBe('control')
      expect(componentRegistry.Rating).toBeDefined()
      expect(componentRegistry.Rating.category).toBe('control')
      expect(componentRegistry.Likert).toBeDefined()
      expect(componentRegistry.Likert.category).toBe('control')
      expect(componentRegistry.Number).toBeDefined()
      expect(componentRegistry.Number.category).toBe('control')
    })

    it('should contain all visual tags', () => {
      expect(componentRegistry.View).toBeDefined()
      expect(componentRegistry.View.category).toBe('visual')
      expect(componentRegistry.Header).toBeDefined()
      expect(componentRegistry.Header.category).toBe('visual')
      expect(componentRegistry.Style).toBeDefined()
      expect(componentRegistry.Style.category).toBe('visual')
    })

    it('should have correct component structure for all entries', () => {
      Object.entries(componentRegistry).forEach(([tagName, component]) => {
        expect(component.component).toBeDefined()
        expect(component.category).toMatch(/^(object|control|visual)$/)
        expect(['object', 'control', 'visual']).toContain(component.category)
      })
    })

    it('should have extractValue functions for control components', () => {
      expect(componentRegistry.TextArea.extractValue).toBeDefined()
      expect(componentRegistry.Choices.extractValue).toBeDefined()
      expect(componentRegistry.Labels.extractValue).toBeDefined()
      expect(componentRegistry.Rating.extractValue).toBeDefined()
      expect(componentRegistry.Likert.extractValue).toBeDefined()
      expect(componentRegistry.Number.extractValue).toBeDefined()
    })

    it('should not have extractValue functions for object components', () => {
      expect(componentRegistry.Text.extractValue).toBeUndefined()
      expect(componentRegistry.Image.extractValue).toBeUndefined()
    })

    it('should not have extractValue functions for visual components', () => {
      expect(componentRegistry.View.extractValue).toBeUndefined()
      expect(componentRegistry.Header.extractValue).toBeUndefined()
      expect(componentRegistry.Style.extractValue).toBeUndefined()
    })
  })

  describe('getComponent', () => {
    it('should return component for supported tag', () => {
      const textComponent = getComponent('Text')
      expect(textComponent).toBeDefined()
      expect(textComponent?.category).toBe('object')
    })

    it('should return component for all registered tags', () => {
      const tags = [
        'Text',
        'Image',
        'TextArea',
        'Choices',
        'Labels',
        'Rating',
        'Likert',
        'Number',
        'View',
        'Header',
        'Style',
      ]

      tags.forEach((tag) => {
        const component = getComponent(tag)
        expect(component).toBeDefined()
        expect(component?.component).toBeDefined()
      })
    })

    it('should return undefined for unsupported tag', () => {
      expect(getComponent('UnknownTag')).toBeUndefined()
      expect(getComponent('InvalidComponent')).toBeUndefined()
      expect(getComponent('')).toBeUndefined()
    })

    it('should be case-sensitive', () => {
      expect(getComponent('Text')).toBeDefined()
      expect(getComponent('text')).toBeUndefined()
      expect(getComponent('TEXT')).toBeUndefined()
    })
  })

  describe('isTagSupported', () => {
    it('should return true for supported tags', () => {
      expect(isTagSupported('Text')).toBe(true)
      expect(isTagSupported('TextArea')).toBe(true)
      expect(isTagSupported('View')).toBe(true)
    })

    it('should return false for unsupported tags', () => {
      expect(isTagSupported('UnknownTag')).toBe(false)
      expect(isTagSupported('InvalidComponent')).toBe(false)
      expect(isTagSupported('')).toBe(false)
    })

    it('should be case-sensitive', () => {
      expect(isTagSupported('Text')).toBe(true)
      expect(isTagSupported('text')).toBe(false)
      expect(isTagSupported('TEXT')).toBe(false)
    })

    it('should return true for all registered components', () => {
      const allTags = Object.keys(componentRegistry)
      allTags.forEach((tag) => {
        expect(isTagSupported(tag)).toBe(true)
      })
    })
  })

  describe('getSupportedTags', () => {
    it('should return all tags when no category specified', () => {
      const tags = getSupportedTags()
      expect(tags).toContain('Text')
      expect(tags).toContain('TextArea')
      expect(tags).toContain('View')
      expect(tags.length).toBeGreaterThanOrEqual(10)
    })

    it('should return only object tags when category is object', () => {
      const objectTags = getSupportedTags('object')
      expect(objectTags).toContain('Text')
      expect(objectTags).toContain('Image')
      expect(objectTags).not.toContain('TextArea')
      expect(objectTags).not.toContain('View')
    })

    it('should return only control tags when category is control', () => {
      const controlTags = getSupportedTags('control')
      expect(controlTags).toContain('TextArea')
      expect(controlTags).toContain('Choices')
      expect(controlTags).toContain('Labels')
      expect(controlTags).toContain('Rating')
      expect(controlTags).toContain('Likert')
      expect(controlTags).toContain('Number')
      expect(controlTags).not.toContain('Text')
      expect(controlTags).not.toContain('View')
    })

    it('should return only visual tags when category is visual', () => {
      const visualTags = getSupportedTags('visual')
      expect(visualTags).toContain('View')
      expect(visualTags).toContain('Header')
      expect(visualTags).toContain('Style')
      expect(visualTags).not.toContain('Text')
      expect(visualTags).not.toContain('TextArea')
    })

    it('should return arrays with correct lengths by category', () => {
      const allTags = getSupportedTags()
      const objectTags = getSupportedTags('object')
      const controlTags = getSupportedTags('control')
      const visualTags = getSupportedTags('visual')

      expect(allTags.length).toBe(
        objectTags.length + controlTags.length + visualTags.length
      )
    })

    it('should return unique tag names', () => {
      const tags = getSupportedTags()
      const uniqueTags = new Set(tags)
      expect(tags.length).toBe(uniqueTags.size)
    })
  })

  describe('registerComponent', () => {
    const MockComponent: React.ComponentType<AnnotationComponentProps> = ({
      config,
      value,
    }) => React.createElement('div', null, `Mock: ${config.type}`)

    afterEach(() => {
      // Clean up any registered custom components
      if (componentRegistry.CustomTag) {
        delete componentRegistry.CustomTag
      }
    })

    it('should register a new component', () => {
      const customComponent: AnnotationComponent = {
        component: MockComponent,
        category: 'control',
      }

      registerComponent('CustomTag', customComponent)

      expect(isTagSupported('CustomTag')).toBe(true)
      expect(getComponent('CustomTag')).toBe(customComponent)
    })

    it('should allow overriding existing components', () => {
      const originalText = getComponent('Text')
      const customComponent: AnnotationComponent = {
        component: MockComponent,
        category: 'object',
      }

      registerComponent('Text', customComponent)

      expect(getComponent('Text')).toBe(customComponent)
      expect(getComponent('Text')).not.toBe(originalText)

      // Restore original
      if (originalText) {
        registerComponent('Text', originalText)
      }
    })

    it('should register component with all properties', () => {
      const extractValue = (value: any) => ({ custom: value })
      const validate = (config: ParsedComponent) => []

      const customComponent: AnnotationComponent = {
        component: MockComponent,
        extractValue,
        validate,
        category: 'control',
      }

      registerComponent('CustomTag', customComponent)

      const registered = getComponent('CustomTag')
      expect(registered?.component).toBe(MockComponent)
      expect(registered?.extractValue).toBe(extractValue)
      expect(registered?.validate).toBe(validate)
      expect(registered?.category).toBe('control')
    })

    it('should make registered component available in getSupportedTags', () => {
      const customComponent: AnnotationComponent = {
        component: MockComponent,
        category: 'control',
      }

      registerComponent('CustomTag', customComponent)

      const allTags = getSupportedTags()
      const controlTags = getSupportedTags('control')

      expect(allTags).toContain('CustomTag')
      expect(controlTags).toContain('CustomTag')
    })
  })

  describe('createComponentInstance', () => {
    const mockConfig: ParsedComponent = {
      type: 'TextArea',
      name: 'answer',
      props: {
        name: 'answer',
        toName: 'text',
      },
      children: [],
    }

    const mockTaskData = {
      text: 'Sample text',
    }

    const mockOnChange = jest.fn()
    const mockOnAnnotation = jest.fn()

    beforeEach(() => {
      jest.clearAllMocks()
    })

    it('should create component instance for supported tag', () => {
      const instance = createComponentInstance(
        mockConfig,
        mockTaskData,
        mockOnChange,
        mockOnAnnotation
      )

      expect(instance).not.toBeNull()
      expect(React.isValidElement(instance)).toBe(true)
    })

    it('should return null for unsupported tag', () => {
      const invalidConfig: ParsedComponent = {
        type: 'UnknownTag',
        props: {},
        children: [],
      }

      const instance = createComponentInstance(
        invalidConfig,
        mockTaskData,
        mockOnChange,
        mockOnAnnotation
      )

      expect(instance).toBeNull()
    })

    it('should pass correct props to component', () => {
      const instance = createComponentInstance(
        mockConfig,
        mockTaskData,
        mockOnChange,
        mockOnAnnotation
      )

      expect(instance).not.toBeNull()
      if (instance) {
        expect(instance.props).toMatchObject({
          config: mockConfig,
          taskData: mockTaskData,
          value: null,
          onChange: mockOnChange,
          onAnnotation: mockOnAnnotation,
        })
      }
    })

    it('should create instances for all supported component types', () => {
      const componentTypes = [
        'Text',
        'Image',
        'TextArea',
        'Choices',
        'Labels',
        'Rating',
        'Likert',
        'Number',
        'View',
        'Header',
        'Style',
      ]

      componentTypes.forEach((type) => {
        const config: ParsedComponent = {
          type,
          props: { name: 'test' },
          children: [],
        }

        const instance = createComponentInstance(
          config,
          mockTaskData,
          mockOnChange,
          mockOnAnnotation
        )

        expect(instance).not.toBeNull()
        expect(React.isValidElement(instance)).toBe(true)
      })
    })

    it('should initialize value as null', () => {
      const instance = createComponentInstance(
        mockConfig,
        mockTaskData,
        mockOnChange,
        mockOnAnnotation
      )

      expect(instance).not.toBeNull()
      if (instance) {
        expect(instance.props.value).toBeNull()
      }
    })

    it('should pass hideSubmitButton when provided', () => {
      const config: ParsedComponent = {
        type: 'TextArea',
        props: {
          name: 'answer',
          toName: 'text',
        },
        children: [],
      }

      const instance = createComponentInstance(
        config,
        mockTaskData,
        mockOnChange,
        mockOnAnnotation
      )

      expect(instance).not.toBeNull()
      if (instance) {
        // hideSubmitButton should be undefined by default (not passed)
        expect(instance.props.hideSubmitButton).toBeUndefined()
      }
    })
  })

  describe('extractValue functions', () => {
    describe('TextArea extractValue', () => {
      it('should extract text value', () => {
        const extractValue = componentRegistry.TextArea.extractValue
        expect(extractValue).toBeDefined()

        const result = extractValue?.('This is my answer')
        expect(result).toEqual({ text: ['This is my answer'] })
      })

      it('should handle empty string', () => {
        const extractValue = componentRegistry.TextArea.extractValue
        const result = extractValue?.('')
        expect(result).toEqual({ text: [''] })
      })
    })

    describe('Choices extractValue', () => {
      it('should extract single choice as array', () => {
        const extractValue = componentRegistry.Choices.extractValue
        expect(extractValue).toBeDefined()

        const result = extractValue?.('option1')
        expect(result).toEqual({ choices: ['option1'] })
      })

      it('should extract multiple choices as array', () => {
        const extractValue = componentRegistry.Choices.extractValue
        const result = extractValue?.(['option1', 'option2'])
        expect(result).toEqual({ choices: ['option1', 'option2'] })
      })

      it('should handle empty array', () => {
        const extractValue = componentRegistry.Choices.extractValue
        const result = extractValue?.([])
        expect(result).toEqual({ choices: [] })
      })
    })

    describe('Labels extractValue', () => {
      it('should return value as-is', () => {
        const extractValue = componentRegistry.Labels.extractValue
        expect(extractValue).toBeDefined()

        const testValue = { label: 'positive', confidence: 0.9 }
        const result = extractValue?.(testValue)
        expect(result).toEqual(testValue)
      })
    })

    describe('Rating extractValue', () => {
      it('should extract rating value', () => {
        const extractValue = componentRegistry.Rating.extractValue
        expect(extractValue).toBeDefined()

        const result = extractValue?.(4)
        expect(result).toEqual({ rating: 4 })
      })

      it('should handle zero rating', () => {
        const extractValue = componentRegistry.Rating.extractValue
        const result = extractValue?.(0)
        expect(result).toEqual({ rating: 0 })
      })

      it('should handle maximum rating', () => {
        const extractValue = componentRegistry.Rating.extractValue
        const result = extractValue?.(5)
        expect(result).toEqual({ rating: 5 })
      })
    })

    describe('Likert extractValue', () => {
      it('should extract likert value', () => {
        const extractValue = componentRegistry.Likert.extractValue
        expect(extractValue).toBeDefined()

        const result = extractValue?.(5)
        expect(result).toEqual({ likert: 5 })
      })

      it('should handle boundary values', () => {
        const extractValue = componentRegistry.Likert.extractValue
        expect(extractValue?.(1)).toEqual({ likert: 1 })
        expect(extractValue?.(7)).toEqual({ likert: 7 })
      })
    })

    describe('Number extractValue', () => {
      it('should extract number value', () => {
        const extractValue = componentRegistry.Number.extractValue
        expect(extractValue).toBeDefined()

        const result = extractValue?.(42)
        expect(result).toEqual({ number: 42 })
      })

      it('should handle zero', () => {
        const extractValue = componentRegistry.Number.extractValue
        const result = extractValue?.(0)
        expect(result).toEqual({ number: 0 })
      })

      it('should handle negative numbers', () => {
        const extractValue = componentRegistry.Number.extractValue
        const result = extractValue?.(-10)
        expect(result).toEqual({ number: -10 })
      })

      it('should handle decimal numbers', () => {
        const extractValue = componentRegistry.Number.extractValue
        const result = extractValue?.(3.14159)
        expect(result).toEqual({ number: 3.14159 })
      })
    })
  })

  describe('component lazy loading', () => {
    it('should have lazy-loaded components', () => {
      Object.entries(componentRegistry).forEach(([tagName, component]) => {
        expect(component.component).toBeDefined()
        // Lazy components have $$typeof symbol
        expect(component.component.$$typeof).toBeDefined()
      })
    })
  })

  describe('category validation', () => {
    it('should have exactly 2 object components', () => {
      const objectTags = getSupportedTags('object')
      expect(objectTags.length).toBe(2)
    })

    it('should have exactly 10 control components', () => {
      const controlTags = getSupportedTags('control')
      expect(controlTags.length).toBe(10)
    })

    it('should have exactly 3 visual components', () => {
      const visualTags = getSupportedTags('visual')
      expect(visualTags.length).toBe(3)
    })
  })

  describe('integration with ParsedComponent', () => {
    it('should handle complex config structures', () => {
      const config: ParsedComponent = {
        type: 'View',
        props: {
          className: 'annotation-view',
        },
        children: [
          {
            type: 'Text',
            name: 'question',
            props: {
              name: 'question',
              value: '$question',
            },
            children: [],
          },
          {
            type: 'TextArea',
            name: 'answer',
            props: {
              name: 'answer',
              toName: 'question',
              required: 'true',
            },
            children: [],
          },
        ],
      }

      const instance = createComponentInstance(
        config,
        { question: 'What is the answer?' },
        jest.fn(),
        jest.fn()
      )

      expect(instance).not.toBeNull()
      expect(React.isValidElement(instance)).toBe(true)
    })
  })

  describe('type safety', () => {
    it('should enforce AnnotationComponent interface', () => {
      const validComponent: AnnotationComponent = {
        component: (() => null) as any,
        category: 'control',
      }

      expect(validComponent.component).toBeDefined()
      expect(validComponent.category).toBe('control')
    })

    it('should enforce correct category values', () => {
      const categories: Array<'object' | 'control' | 'visual'> = [
        'object',
        'control',
        'visual',
      ]

      categories.forEach((category) => {
        const component: AnnotationComponent = {
          component: (() => null) as any,
          category,
        }
        expect(component.category).toBe(category)
      })
    })
  })

  describe('component registry completeness', () => {
    it('should have components for all object types', () => {
      const objectComponents = ['Text', 'Image']
      objectComponents.forEach((type) => {
        const component = componentRegistry[type]
        expect(component).toBeDefined()
        expect(component.component).toBeDefined()
        expect(component.category).toBe('object')
      })
    })

    it('should have components for all control types', () => {
      const controlComponents = [
        'TextArea',
        'Choices',
        'Labels',
        'Rating',
        'Likert',
        'Number',
      ]
      controlComponents.forEach((type) => {
        const component = componentRegistry[type]
        expect(component).toBeDefined()
        expect(component.component).toBeDefined()
        expect(component.category).toBe('control')
      })
    })

    it('should have components for all visual types', () => {
      const visualComponents = ['View', 'Header', 'Style']
      visualComponents.forEach((type) => {
        const component = componentRegistry[type]
        expect(component).toBeDefined()
        expect(component.component).toBeDefined()
        expect(component.category).toBe('visual')
      })
    })

    it('should have exactly 15 components registered', () => {
      const totalComponents = Object.keys(componentRegistry).length
      expect(totalComponents).toBe(15)
    })

    it('should have lazy components that are React components', () => {
      Object.entries(componentRegistry).forEach(([tagName, component]) => {
        expect(component.component).toBeDefined()
        expect(typeof component.component).toBe('object')
      })
    })
  })

  describe('extractValue edge cases', () => {
    it('should handle undefined values in TextArea', () => {
      const extractValue = componentRegistry.TextArea.extractValue
      const result = extractValue?.(undefined)
      expect(result).toEqual({ text: [undefined] })
    })

    it('should handle null values in Choices', () => {
      const extractValue = componentRegistry.Choices.extractValue
      const result = extractValue?.(null)
      expect(result).toEqual({ choices: [null] })
    })

    it('should handle complex objects in Labels', () => {
      const extractValue = componentRegistry.Labels.extractValue
      const complexValue = {
        label: 'positive',
        confidence: 0.9,
        metadata: { annotator: 'user1' },
      }
      const result = extractValue?.(complexValue)
      expect(result).toEqual(complexValue)
    })

    it('should handle float values in Rating', () => {
      const extractValue = componentRegistry.Rating.extractValue
      const result = extractValue?.(3.5)
      expect(result).toEqual({ rating: 3.5 })
    })

    it('should handle very large numbers in Number', () => {
      const extractValue = componentRegistry.Number.extractValue
      const result = extractValue?.(Number.MAX_SAFE_INTEGER)
      expect(result).toEqual({ number: Number.MAX_SAFE_INTEGER })
    })

    it('should handle very small numbers in Number', () => {
      const extractValue = componentRegistry.Number.extractValue
      const result = extractValue?.(Number.MIN_SAFE_INTEGER)
      expect(result).toEqual({ number: Number.MIN_SAFE_INTEGER })
    })
  })

  describe('createComponentInstance edge cases', () => {
    const mockOnChange = jest.fn()
    const mockOnAnnotation = jest.fn()

    it('should handle empty config props', () => {
      const config: ParsedComponent = {
        type: 'Text',
        props: {},
        children: [],
      }

      const instance = createComponentInstance(
        config,
        {},
        mockOnChange,
        mockOnAnnotation
      )

      expect(instance).not.toBeNull()
      expect(React.isValidElement(instance)).toBe(true)
    })

    it('should handle empty task data', () => {
      const config: ParsedComponent = {
        type: 'TextArea',
        props: { name: 'test' },
        children: [],
      }

      const instance = createComponentInstance(
        config,
        {},
        mockOnChange,
        mockOnAnnotation
      )

      expect(instance).not.toBeNull()
      if (instance) {
        expect(instance.props.taskData).toEqual({})
      }
    })

    it('should handle config with children', () => {
      const config: ParsedComponent = {
        type: 'Choices',
        props: { name: 'choice' },
        children: [
          {
            type: 'Choice',
            props: { value: 'option1' },
            children: [],
          },
        ],
      }

      const instance = createComponentInstance(
        config,
        {},
        mockOnChange,
        mockOnAnnotation
      )

      expect(instance).not.toBeNull()
      if (instance) {
        expect(instance.props.config.children).toHaveLength(1)
      }
    })

    it('should handle config without name property', () => {
      const config: ParsedComponent = {
        type: 'View',
        props: { className: 'container' },
        children: [],
      }

      const instance = createComponentInstance(
        config,
        {},
        mockOnChange,
        mockOnAnnotation
      )

      expect(instance).not.toBeNull()
      if (instance) {
        expect(instance.props.config.name).toBeUndefined()
      }
    })
  })

  describe('registerComponent edge cases', () => {
    const MockComponent: React.ComponentType<AnnotationComponentProps> = () =>
      React.createElement('div', null, 'Mock')

    afterEach(() => {
      // Clean up test components
      const testKeys = Object.keys(componentRegistry).filter((key) =>
        key.startsWith('Test')
      )
      testKeys.forEach((key) => delete componentRegistry[key])
    })

    it('should register multiple custom components', () => {
      const component1: AnnotationComponent = {
        component: MockComponent,
        category: 'control',
      }
      const component2: AnnotationComponent = {
        component: MockComponent,
        category: 'visual',
      }

      registerComponent('TestComponent1', component1)
      registerComponent('TestComponent2', component2)

      expect(isTagSupported('TestComponent1')).toBe(true)
      expect(isTagSupported('TestComponent2')).toBe(true)
    })

    it('should allow re-registering the same component', () => {
      const component: AnnotationComponent = {
        component: MockComponent,
        category: 'control',
      }

      registerComponent('TestComponent', component)
      registerComponent('TestComponent', component)

      expect(isTagSupported('TestComponent')).toBe(true)
      expect(getComponent('TestComponent')).toBe(component)
    })

    it('should update component when overriding', () => {
      const component1: AnnotationComponent = {
        component: MockComponent,
        category: 'control',
        extractValue: (v) => ({ old: v }),
      }
      const component2: AnnotationComponent = {
        component: MockComponent,
        category: 'object',
        extractValue: (v) => ({ new: v }),
      }

      registerComponent('TestComponent', component1)
      expect(getComponent('TestComponent')?.category).toBe('control')

      registerComponent('TestComponent', component2)
      expect(getComponent('TestComponent')?.category).toBe('object')
    })
  })

  describe('getSupportedTags filtering', () => {
    it('should maintain consistent ordering', () => {
      const tags1 = getSupportedTags()
      const tags2 = getSupportedTags()

      expect(tags1).toEqual(tags2)
    })

    it('should return independent arrays for different categories', () => {
      const objectTags = getSupportedTags('object')
      const controlTags = getSupportedTags('control')
      const visualTags = getSupportedTags('visual')

      const allCategories = [
        ...objectTags,
        ...controlTags,
        ...visualTags,
      ].sort()
      const allTags = getSupportedTags().sort()

      expect(allCategories).toEqual(allTags)
    })

    it('should return new array instances', () => {
      const tags1 = getSupportedTags()
      const tags2 = getSupportedTags()

      expect(tags1).not.toBe(tags2)
      expect(tags1).toEqual(tags2)
    })
  })

  describe('component props validation', () => {
    it('should accept all required AnnotationComponentProps', () => {
      const config: ParsedComponent = {
        type: 'TextArea',
        props: { name: 'test' },
        children: [],
      }

      const taskData = { text: 'sample' }
      const value = 'current value'
      const onChange = jest.fn()
      const onAnnotation = jest.fn()

      const instance = createComponentInstance(
        config,
        taskData,
        onChange,
        onAnnotation
      )

      expect(instance).not.toBeNull()
      if (instance) {
        expect(instance.props).toMatchObject({
          config,
          taskData,
          value: null,
          onChange,
          onAnnotation,
        })
      }
    })

    it('should not include hideSubmitButton by default', () => {
      const config: ParsedComponent = {
        type: 'TextArea',
        props: {},
        children: [],
      }

      const instance = createComponentInstance(config, {}, jest.fn(), jest.fn())

      if (instance) {
        expect(instance.props.hideSubmitButton).toBeUndefined()
      }
    })
  })
})

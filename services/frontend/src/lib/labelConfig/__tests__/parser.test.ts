/**
 * @jest-environment jsdom
 *
 * Comprehensive tests for Label Configuration Parser
 * Tests XML/JSON parsing, validation logic, error handling, and data extraction
 */

import {
  extractDataFields,
  extractRequiredDataFields,
  ParsedComponent,
  ParseError,
  parseLabelConfig,
  validateParsedConfig,
} from '../parser'

describe('parseLabelConfig', () => {
  describe('valid XML parsing', () => {
    it('should parse simple View element', () => {
      const xml = '<View></View>'
      const result = parseLabelConfig(xml) as ParsedComponent

      expect(result).toHaveProperty('type', 'View')
      expect(result).toHaveProperty('props', {})
      expect(result).toHaveProperty('children', [])
    })

    it('should parse View with attributes', () => {
      const xml = '<View className="container" style="padding: 10px"></View>'
      const result = parseLabelConfig(xml) as ParsedComponent

      expect(result.type).toBe('View')
      expect(result.props.className).toBe('container')
      expect(result.props.style).toBe('padding: 10px')
    })

    it('should parse nested components', () => {
      const xml = `
        <View>
          <Text name="text" value="$content"></Text>
        </View>
      `
      const result = parseLabelConfig(xml) as ParsedComponent

      expect(result.type).toBe('View')
      expect(result.children).toHaveLength(1)
      expect(result.children[0].type).toBe('Text')
      expect(result.children[0].name).toBe('text')
      expect(result.children[0].props.name).toBe('text')
      expect(result.children[0].props.value).toBe('$content')
    })

    it('should parse deeply nested components', () => {
      const xml = `
        <View>
          <Header>
            <Text name="title" value="$title"></Text>
          </Header>
          <Choices name="choice" toName="text">
            <Choice value="positive"></Choice>
            <Choice value="negative"></Choice>
          </Choices>
        </View>
      `
      const result = parseLabelConfig(xml) as ParsedComponent

      expect(result.type).toBe('View')
      expect(result.children).toHaveLength(2)
      expect(result.children[0].type).toBe('Header')
      expect(result.children[0].children).toHaveLength(1)
      expect(result.children[1].type).toBe('Choices')
      expect(result.children[1].children).toHaveLength(2)
    })

    it('should extract text content from elements', () => {
      const xml = `
        <View>
          <Choice value="positive">Positive</Choice>
          <Choice value="negative">Negative</Choice>
        </View>
      `
      const result = parseLabelConfig(xml) as ParsedComponent

      expect(result.children[0].props.content).toBe('Positive')
      expect(result.children[1].props.content).toBe('Negative')
    })

    it('should trim whitespace from text content', () => {
      const xml = `
        <View>
          <Choice value="test">
            Test Content
          </Choice>
        </View>
      `
      const result = parseLabelConfig(xml) as ParsedComponent

      expect(result.children[0].props.content).toBe('Test Content')
    })

    it('should not add content prop for empty text', () => {
      const xml = `
        <View>
          <Choice value="test">   </Choice>
        </View>
      `
      const result = parseLabelConfig(xml) as ParsedComponent

      expect(result.children[0].props.content).toBeUndefined()
    })

    it('should parse TextArea component', () => {
      const xml = `
        <View>
          <TextArea name="answer" toName="question" placeholder="Enter answer"></TextArea>
        </View>
      `
      const result = parseLabelConfig(xml) as ParsedComponent

      expect(result.children[0].type).toBe('TextArea')
      expect(result.children[0].name).toBe('answer')
      expect(result.children[0].props.toName).toBe('question')
      expect(result.children[0].props.placeholder).toBe('Enter answer')
    })

    it('should parse Choices with multiple Choice children', () => {
      const xml = `
        <View>
          <Choices name="sentiment" toName="text" choice="multiple">
            <Choice value="positive">Positive</Choice>
            <Choice value="neutral">Neutral</Choice>
            <Choice value="negative">Negative</Choice>
          </Choices>
        </View>
      `
      const result = parseLabelConfig(xml) as ParsedComponent

      expect(result.children[0].type).toBe('Choices')
      expect(result.children[0].children).toHaveLength(3)
      expect(result.children[0].children[0].props.value).toBe('positive')
      expect(result.children[0].children[1].props.value).toBe('neutral')
      expect(result.children[0].children[2].props.value).toBe('negative')
    })

    it('should handle self-closing tags', () => {
      const xml = `
        <View>
          <Text name="text" value="$content" />
          <Choice value="test" />
        </View>
      `
      const result = parseLabelConfig(xml) as ParsedComponent

      expect(result.children).toHaveLength(2)
      expect(result.children[0].type).toBe('Text')
      expect(result.children[1].type).toBe('Choice')
    })

    it('should parse complex Label Studio config', () => {
      const xml = `
        <View>
          <Header value="Legal Document Classification" />
          <Text name="context" value="$context" />
          <Choices name="category" toName="context" choice="single" required="true">
            <Choice value="civil">Civil Law</Choice>
            <Choice value="criminal">Criminal Law</Choice>
            <Choice value="administrative">Administrative Law</Choice>
          </Choices>
          <TextArea name="reasoning" toName="context" placeholder="Explain your choice" />
        </View>
      `
      const result = parseLabelConfig(xml) as ParsedComponent

      expect(result.type).toBe('View')
      expect(result.children).toHaveLength(4)
      expect(result.children[0].type).toBe('Header')
      expect(result.children[1].type).toBe('Text')
      expect(result.children[2].type).toBe('Choices')
      expect(result.children[2].props.required).toBe('true')
      expect(result.children[3].type).toBe('TextArea')
    })
  })

  describe('error handling', () => {
    it('should return error for invalid XML', () => {
      const xml = '<View><Text></View>'
      const result = parseLabelConfig(xml) as ParseError

      expect(result).toHaveProperty('message')
      expect(typeof result.message).toBe('string')
      expect(result.message.length).toBeGreaterThan(0)
    })

    it('should return error for malformed XML', () => {
      const xml = '<View><Text name="test"</View>'
      const result = parseLabelConfig(xml) as ParseError

      expect(result).toHaveProperty('message')
      expect(typeof result.message).toBe('string')
    })

    it('should return error for empty string', () => {
      const xml = ''
      const result = parseLabelConfig(xml) as ParseError

      expect(result).toHaveProperty('message')
    })

    it('should return error for unclosed tags', () => {
      const xml = '<View><Text name="test">'
      const result = parseLabelConfig(xml) as ParseError

      expect(result).toHaveProperty('message')
    })

    it('should return error for mismatched tags', () => {
      const xml = '<View><Text></Choice></View>'
      const result = parseLabelConfig(xml) as ParseError

      expect(result).toHaveProperty('message')
    })

    it('should handle invalid characters in XML', () => {
      const xml = '<View attr="test&invalid"></View>'
      const result = parseLabelConfig(xml)

      // Browser may handle it as error or parse successfully
      expect(result).toHaveProperty('message')
    })

    it('should handle generic errors with Error instance', () => {
      // Test error handling with Error instance
      const xml = '<View>'
      const result = parseLabelConfig(xml) as ParseError

      expect(result).toHaveProperty('message')
      expect(typeof result.message).toBe('string')
    })

    it('should handle generic errors with non-Error values', () => {
      // This test ensures the catch block handles non-Error throws
      // Most XML errors will be caught by DOMParser, but this tests the fallback
      const xml = ''
      const result = parseLabelConfig(xml) as ParseError

      expect(result).toHaveProperty('message')
      expect(typeof result.message).toBe('string')
    })
  })
})

describe('validateParsedConfig', () => {
  describe('root element validation', () => {
    it('should accept View as root element', () => {
      const config: ParsedComponent = {
        type: 'View',
        props: {},
        children: [],
      }

      const result = validateParsedConfig(config)

      expect(result.valid).toBe(true)
      expect(result.errors).toHaveLength(0)
    })

    it('should reject non-View root element', () => {
      const config: ParsedComponent = {
        type: 'Text',
        props: {},
        children: [],
      }

      const result = validateParsedConfig(config)

      expect(result.valid).toBe(false)
      expect(result.errors).toContain('Root element must be <View>')
    })

    it('should reject Header as root element', () => {
      const config: ParsedComponent = {
        type: 'Header',
        props: {},
        children: [],
      }

      const result = validateParsedConfig(config)

      expect(result.valid).toBe(false)
      expect(result.errors).toHaveLength(1)
    })
  })

  describe('Text component validation', () => {
    it('should accept valid Text component', () => {
      const config: ParsedComponent = {
        type: 'View',
        props: {},
        children: [
          {
            type: 'Text',
            name: 'text',
            props: { name: 'text', value: '$content' },
            children: [],
          },
        ],
      }

      const result = validateParsedConfig(config)

      expect(result.valid).toBe(true)
      expect(result.errors).toHaveLength(0)
    })

    it('should reject Text without name attribute', () => {
      const config: ParsedComponent = {
        type: 'View',
        props: {},
        children: [
          {
            type: 'Text',
            props: { value: '$content' },
            children: [],
          },
        ],
      }

      const result = validateParsedConfig(config)

      expect(result.valid).toBe(false)
      expect(
        result.errors.some((e) =>
          e.includes("Text component requires 'name' attribute")
        )
      ).toBe(true)
    })

    it('should reject Text without value attribute', () => {
      const config: ParsedComponent = {
        type: 'View',
        props: {},
        children: [
          {
            type: 'Text',
            name: 'text',
            props: { name: 'text' },
            children: [],
          },
        ],
      }

      const result = validateParsedConfig(config)

      expect(result.valid).toBe(false)
      expect(
        result.errors.some((e) =>
          e.includes("Text component requires 'value' attribute")
        )
      ).toBe(true)
    })

    it('should reject Text without both attributes', () => {
      const config: ParsedComponent = {
        type: 'View',
        props: {},
        children: [
          {
            type: 'Text',
            props: {},
            children: [],
          },
        ],
      }

      const result = validateParsedConfig(config)

      expect(result.valid).toBe(false)
      expect(result.errors).toHaveLength(2)
    })
  })

  describe('TextArea component validation', () => {
    it('should accept valid TextArea component', () => {
      const config: ParsedComponent = {
        type: 'View',
        props: {},
        children: [
          {
            type: 'TextArea',
            name: 'answer',
            props: { name: 'answer', toName: 'question' },
            children: [],
          },
        ],
      }

      const result = validateParsedConfig(config)

      expect(result.valid).toBe(true)
      expect(result.errors).toHaveLength(0)
    })

    it('should reject TextArea without name attribute', () => {
      const config: ParsedComponent = {
        type: 'View',
        props: {},
        children: [
          {
            type: 'TextArea',
            props: { toName: 'question' },
            children: [],
          },
        ],
      }

      const result = validateParsedConfig(config)

      expect(result.valid).toBe(false)
      expect(
        result.errors.some((e) =>
          e.includes("TextArea component requires 'name' attribute")
        )
      ).toBe(true)
    })

    it('should reject TextArea without toName attribute', () => {
      const config: ParsedComponent = {
        type: 'View',
        props: {},
        children: [
          {
            type: 'TextArea',
            name: 'answer',
            props: { name: 'answer' },
            children: [],
          },
        ],
      }

      const result = validateParsedConfig(config)

      expect(result.valid).toBe(false)
      expect(
        result.errors.some((e) =>
          e.includes("TextArea component requires 'toName' attribute")
        )
      ).toBe(true)
    })
  })

  describe('Choices component validation', () => {
    it('should accept valid Choices component', () => {
      const config: ParsedComponent = {
        type: 'View',
        props: {},
        children: [
          {
            type: 'Choices',
            name: 'sentiment',
            props: { name: 'sentiment', toName: 'text' },
            children: [
              { type: 'Choice', props: { value: 'positive' }, children: [] },
            ],
          },
        ],
      }

      const result = validateParsedConfig(config)

      expect(result.valid).toBe(true)
      expect(result.errors).toHaveLength(0)
    })

    it('should reject Choices without name attribute', () => {
      const config: ParsedComponent = {
        type: 'View',
        props: {},
        children: [
          {
            type: 'Choices',
            props: { toName: 'text' },
            children: [
              { type: 'Choice', props: { value: 'positive' }, children: [] },
            ],
          },
        ],
      }

      const result = validateParsedConfig(config)

      expect(result.valid).toBe(false)
      expect(
        result.errors.some((e) =>
          e.includes("Choices component requires 'name' attribute")
        )
      ).toBe(true)
    })

    it('should reject Choices without toName attribute', () => {
      const config: ParsedComponent = {
        type: 'View',
        props: {},
        children: [
          {
            type: 'Choices',
            name: 'sentiment',
            props: { name: 'sentiment' },
            children: [
              { type: 'Choice', props: { value: 'positive' }, children: [] },
            ],
          },
        ],
      }

      const result = validateParsedConfig(config)

      expect(result.valid).toBe(false)
      expect(
        result.errors.some((e) =>
          e.includes("Choices component requires 'toName' attribute")
        )
      ).toBe(true)
    })

    it('should reject Choices without children', () => {
      const config: ParsedComponent = {
        type: 'View',
        props: {},
        children: [
          {
            type: 'Choices',
            name: 'sentiment',
            props: { name: 'sentiment', toName: 'text' },
            children: [],
          },
        ],
      }

      const result = validateParsedConfig(config)

      expect(result.valid).toBe(false)
      expect(
        result.errors.some((e) =>
          e.includes('Choices component requires at least one Choice')
        )
      ).toBe(true)
    })
  })

  describe('Choice component validation', () => {
    it('should accept valid Choice component', () => {
      const config: ParsedComponent = {
        type: 'View',
        props: {},
        children: [
          {
            type: 'Choices',
            name: 'sentiment',
            props: { name: 'sentiment', toName: 'text' },
            children: [
              { type: 'Choice', props: { value: 'positive' }, children: [] },
            ],
          },
        ],
      }

      const result = validateParsedConfig(config)

      expect(result.valid).toBe(true)
    })

    it('should reject Choice without value attribute', () => {
      const config: ParsedComponent = {
        type: 'View',
        props: {},
        children: [
          {
            type: 'Choices',
            name: 'sentiment',
            props: { name: 'sentiment', toName: 'text' },
            children: [{ type: 'Choice', props: {}, children: [] }],
          },
        ],
      }

      const result = validateParsedConfig(config)

      expect(result.valid).toBe(false)
      expect(
        result.errors.some((e) =>
          e.includes("Choice component requires 'value' attribute")
        )
      ).toBe(true)
    })
  })

  describe('nested validation', () => {
    it('should validate deeply nested components', () => {
      const config: ParsedComponent = {
        type: 'View',
        props: {},
        children: [
          {
            type: 'Header',
            props: {},
            children: [
              {
                type: 'Text',
                props: {},
                children: [],
              },
            ],
          },
        ],
      }

      const result = validateParsedConfig(config)

      expect(result.valid).toBe(false)
      expect(result.errors.length).toBeGreaterThan(0)
    })

    it('should collect multiple errors from nested components', () => {
      const config: ParsedComponent = {
        type: 'View',
        props: {},
        children: [
          {
            type: 'Text',
            props: {},
            children: [],
          },
          {
            type: 'TextArea',
            props: {},
            children: [],
          },
          {
            type: 'Choices',
            props: {},
            children: [],
          },
        ],
      }

      const result = validateParsedConfig(config)

      expect(result.valid).toBe(false)
      expect(result.errors.length).toBeGreaterThan(4)
    })

    it('should include path in error messages', () => {
      const config: ParsedComponent = {
        type: 'View',
        props: {},
        children: [
          {
            type: 'Text',
            props: {},
            children: [],
          },
        ],
      }

      const result = validateParsedConfig(config)

      expect(result.errors[0]).toContain('View')
      expect(result.errors[0]).toContain('Text')
    })
  })

  describe('valid complex configurations', () => {
    it('should accept complete valid configuration', () => {
      const config: ParsedComponent = {
        type: 'View',
        props: {},
        children: [
          {
            type: 'Text',
            name: 'context',
            props: { name: 'context', value: '$context' },
            children: [],
          },
          {
            type: 'Choices',
            name: 'category',
            props: { name: 'category', toName: 'context' },
            children: [
              { type: 'Choice', props: { value: 'civil' }, children: [] },
              { type: 'Choice', props: { value: 'criminal' }, children: [] },
            ],
          },
          {
            type: 'TextArea',
            name: 'reasoning',
            props: { name: 'reasoning', toName: 'context' },
            children: [],
          },
        ],
      }

      const result = validateParsedConfig(config)

      expect(result.valid).toBe(true)
      expect(result.errors).toHaveLength(0)
    })

    it('should allow unknown component types without validation', () => {
      const config: ParsedComponent = {
        type: 'View',
        props: {},
        children: [
          {
            type: 'CustomComponent',
            props: {},
            children: [],
          },
        ],
      }

      const result = validateParsedConfig(config)

      expect(result.valid).toBe(true)
    })
  })
})

describe('extractDataFields', () => {
  describe('basic extraction', () => {
    it('should extract data fields from props', () => {
      const config: ParsedComponent = {
        type: 'View',
        props: {},
        children: [
          {
            type: 'Text',
            name: 'text',
            props: { name: 'text', value: '$content' },
            children: [],
          },
        ],
      }

      const fields = extractDataFields(config)

      expect(fields).toContain('content')
      expect(fields).toHaveLength(1)
    })

    it('should extract multiple data fields', () => {
      const config: ParsedComponent = {
        type: 'View',
        props: {},
        children: [
          {
            type: 'Text',
            name: 'context',
            props: { name: 'context', value: '$context' },
            children: [],
          },
          {
            type: 'Text',
            name: 'question',
            props: { name: 'question', value: '$question' },
            children: [],
          },
        ],
      }

      const fields = extractDataFields(config)

      expect(fields).toContain('context')
      expect(fields).toContain('question')
      expect(fields).toHaveLength(2)
    })

    it('should extract fields from nested components', () => {
      const config: ParsedComponent = {
        type: 'View',
        props: {},
        children: [
          {
            type: 'Header',
            props: { title: '$title' },
            children: [
              {
                type: 'Text',
                props: { value: '$subtitle' },
                children: [],
              },
            ],
          },
        ],
      }

      const fields = extractDataFields(config)

      expect(fields).toContain('title')
      expect(fields).toContain('subtitle')
      expect(fields).toHaveLength(2)
    })

    it('should not extract non-data props', () => {
      const config: ParsedComponent = {
        type: 'View',
        props: {},
        children: [
          {
            type: 'Text',
            name: 'text',
            props: {
              name: 'text',
              value: 'static value',
              className: 'container',
            },
            children: [],
          },
        ],
      }

      const fields = extractDataFields(config)

      expect(fields).toHaveLength(0)
    })

    it('should deduplicate field names', () => {
      const config: ParsedComponent = {
        type: 'View',
        props: {},
        children: [
          {
            type: 'Text',
            props: { value: '$content' },
            children: [],
          },
          {
            type: 'TextArea',
            props: { toName: '$content' },
            children: [],
          },
        ],
      }

      const fields = extractDataFields(config)

      expect(fields).toEqual(['content'])
      expect(fields).toHaveLength(1)
    })
  })

  describe('edge cases', () => {
    it('should return empty array for config without data fields', () => {
      const config: ParsedComponent = {
        type: 'View',
        props: {},
        children: [],
      }

      const fields = extractDataFields(config)

      expect(fields).toEqual([])
    })

    it('should handle config with only static content', () => {
      const config: ParsedComponent = {
        type: 'View',
        props: {},
        children: [
          {
            type: 'Header',
            props: { value: 'Static Title' },
            children: [],
          },
        ],
      }

      const fields = extractDataFields(config)

      expect(fields).toEqual([])
    })

    it('should extract nested path fields', () => {
      const config: ParsedComponent = {
        type: 'View',
        props: {},
        children: [
          {
            type: 'Text',
            props: { value: '$user.name' },
            children: [],
          },
        ],
      }

      const fields = extractDataFields(config)

      expect(fields).toContain('user.name')
    })
  })

  describe('complex configurations', () => {
    it('should extract all fields from complex config', () => {
      const config: ParsedComponent = {
        type: 'View',
        props: {},
        children: [
          {
            type: 'Text',
            name: 'context',
            props: { name: 'context', value: '$context' },
            children: [],
          },
          {
            type: 'Text',
            name: 'question',
            props: { name: 'question', value: '$question' },
            children: [],
          },
          {
            type: 'Choices',
            name: 'category',
            props: { name: 'category', toName: '$context' },
            children: [],
          },
        ],
      }

      const fields = extractDataFields(config)

      expect(fields).toContain('context')
      expect(fields).toContain('question')
      expect(fields).toHaveLength(2)
    })
  })
})

describe('extractRequiredDataFields', () => {
  describe('required field extraction', () => {
    it('should extract fields from components with required="true"', () => {
      const config: ParsedComponent = {
        type: 'View',
        props: {},
        children: [
          {
            type: 'Text',
            props: { value: '$context', required: 'true' },
            children: [],
          },
        ],
      }

      const fields = extractRequiredDataFields(config)

      expect(fields).toContain('context')
      expect(fields).toHaveLength(1)
    })

    it('should extract fields from components with required=true (boolean)', () => {
      const config: ParsedComponent = {
        type: 'View',
        props: {},
        children: [
          {
            type: 'Text',
            props: { value: '$context', required: true },
            children: [],
          },
        ],
      }

      const fields = extractRequiredDataFields(config)

      expect(fields).toContain('context')
      expect(fields).toHaveLength(1)
    })

    it('should not extract fields from non-required components', () => {
      const config: ParsedComponent = {
        type: 'View',
        props: {},
        children: [
          {
            type: 'Text',
            props: { value: '$context' },
            children: [],
          },
        ],
      }

      const fields = extractRequiredDataFields(config)

      expect(fields).toEqual([])
    })

    it('should not extract fields with required="false"', () => {
      const config: ParsedComponent = {
        type: 'View',
        props: {},
        children: [
          {
            type: 'Text',
            props: { value: '$context', required: 'false' },
            children: [],
          },
        ],
      }

      const fields = extractRequiredDataFields(config)

      expect(fields).toEqual([])
    })

    it('should extract only required fields from mixed config', () => {
      const config: ParsedComponent = {
        type: 'View',
        props: {},
        children: [
          {
            type: 'Text',
            props: { value: '$context', required: 'true' },
            children: [],
          },
          {
            type: 'Text',
            props: { value: '$question' },
            children: [],
          },
          {
            type: 'TextArea',
            props: { toName: '$answer', required: true },
            children: [],
          },
        ],
      }

      const fields = extractRequiredDataFields(config)

      expect(fields).toContain('context')
      expect(fields).toContain('answer')
      expect(fields).not.toContain('question')
      expect(fields).toHaveLength(2)
    })
  })

  describe('nested required fields', () => {
    it('should extract required fields from nested components', () => {
      const config: ParsedComponent = {
        type: 'View',
        props: {},
        children: [
          {
            type: 'Header',
            props: {},
            children: [
              {
                type: 'Text',
                props: { value: '$title', required: 'true' },
                children: [],
              },
            ],
          },
        ],
      }

      const fields = extractRequiredDataFields(config)

      expect(fields).toContain('title')
    })

    it('should deduplicate required fields', () => {
      const config: ParsedComponent = {
        type: 'View',
        props: {},
        children: [
          {
            type: 'Text',
            props: { value: '$context', required: 'true' },
            children: [],
          },
          {
            type: 'TextArea',
            props: { toName: '$context', required: true },
            children: [],
          },
        ],
      }

      const fields = extractRequiredDataFields(config)

      expect(fields).toEqual(['context'])
      expect(fields).toHaveLength(1)
    })
  })

  describe('edge cases', () => {
    it('should return empty array when no required fields', () => {
      const config: ParsedComponent = {
        type: 'View',
        props: {},
        children: [
          {
            type: 'Text',
            props: { value: '$context' },
            children: [],
          },
        ],
      }

      const fields = extractRequiredDataFields(config)

      expect(fields).toEqual([])
    })

    it('should handle empty config', () => {
      const config: ParsedComponent = {
        type: 'View',
        props: {},
        children: [],
      }

      const fields = extractRequiredDataFields(config)

      expect(fields).toEqual([])
    })

    it('should handle required components without data fields', () => {
      const config: ParsedComponent = {
        type: 'View',
        props: {},
        children: [
          {
            type: 'Header',
            props: { value: 'Static', required: 'true' },
            children: [],
          },
        ],
      }

      const fields = extractRequiredDataFields(config)

      expect(fields).toEqual([])
    })
  })
})

describe('integration tests', () => {
  describe('parse and validate workflow', () => {
    it('should parse and validate valid Label Studio config', () => {
      const xml = `
        <View>
          <Text name="context" value="$context" />
          <Choices name="category" toName="context">
            <Choice value="civil">Civil Law</Choice>
            <Choice value="criminal">Criminal Law</Choice>
          </Choices>
        </View>
      `

      const parsed = parseLabelConfig(xml) as ParsedComponent
      expect(parsed).toHaveProperty('type', 'View')

      const validation = validateParsedConfig(parsed)
      expect(validation.valid).toBe(true)
      expect(validation.errors).toHaveLength(0)
    })

    it('should parse and detect validation errors', () => {
      const xml = `
        <View>
          <Text value="$context" />
          <Choices name="category">
            <Choice>Civil Law</Choice>
          </Choices>
        </View>
      `

      const parsed = parseLabelConfig(xml) as ParsedComponent
      const validation = validateParsedConfig(parsed)

      expect(validation.valid).toBe(false)
      expect(validation.errors.length).toBeGreaterThan(0)
    })
  })

  describe('parse and extract workflow', () => {
    it('should parse and extract data fields', () => {
      const xml = `
        <View>
          <Text name="context" value="$context" />
          <Text name="question" value="$question" />
          <TextArea name="answer" toName="context" />
        </View>
      `

      const parsed = parseLabelConfig(xml) as ParsedComponent
      const fields = extractDataFields(parsed)

      expect(fields).toContain('context')
      expect(fields).toContain('question')
      expect(fields).toHaveLength(2)
    })

    it('should parse and extract required fields', () => {
      const xml = `
        <View>
          <Text name="context" value="$context" required="true" />
          <Text name="question" value="$question" />
          <Choices name="category" toName="context" required="true">
            <Choice value="test" />
          </Choices>
        </View>
      `

      const parsed = parseLabelConfig(xml) as ParsedComponent
      const requiredFields = extractRequiredDataFields(parsed)

      expect(requiredFields).toContain('context')
      expect(requiredFields).not.toContain('question')
      expect(requiredFields).toHaveLength(1)
    })
  })

  describe('real-world Label Studio configs', () => {
    it('should handle German legal document classification config', () => {
      const xml = `
        <View>
          <Header value="Rechtsdokument Klassifizierung" />
          <Text name="document" value="$text" required="true" />
          <Choices name="rechtsgebiet" toName="document" choice="single" required="true">
            <Choice value="zivilrecht">Zivilrecht</Choice>
            <Choice value="strafrecht">Strafrecht</Choice>
            <Choice value="verwaltungsrecht">Verwaltungsrecht</Choice>
          </Choices>
          <TextArea name="begruendung" toName="document" placeholder="Begründung" />
        </View>
      `

      const parsed = parseLabelConfig(xml) as ParsedComponent
      expect(parsed.type).toBe('View')

      const validation = validateParsedConfig(parsed)
      expect(validation.valid).toBe(true)

      const fields = extractDataFields(parsed)
      expect(fields).toContain('text')

      const requiredFields = extractRequiredDataFields(parsed)
      expect(requiredFields).toContain('text')
    })

    it('should handle multi-field annotation config', () => {
      const xml = `
        <View>
          <Text name="context" value="$context" />
          <Text name="question" value="$question" />
          <Choices name="answer_type" toName="question" choice="single">
            <Choice value="yes">Ja</Choice>
            <Choice value="no">Nein</Choice>
            <Choice value="unclear">Unklar</Choice>
          </Choices>
          <TextArea name="explanation" toName="question" required="true" />
        </View>
      `

      const parsed = parseLabelConfig(xml) as ParsedComponent
      const validation = validateParsedConfig(parsed)
      const fields = extractDataFields(parsed)
      const requiredFields = extractRequiredDataFields(parsed)

      expect(validation.valid).toBe(true)
      expect(fields).toEqual(['context', 'question'])
      expect(requiredFields).toEqual([])
    })
  })
})

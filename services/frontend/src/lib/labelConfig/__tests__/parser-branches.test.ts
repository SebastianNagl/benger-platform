/**
 * Branch coverage tests for parser.ts
 *
 * Targets: validateParsedConfig with non-View root, validateComponent switch
 * extractRequiredDataFields required=true vs required="true",
 * parseLabelConfig error branch.
 */

import {
  parseLabelConfig,
  validateParsedConfig,
  extractDataFields,
  extractRequiredDataFields,
  ParsedComponent,
} from '../parser'

describe('parseLabelConfig', () => {
  it('should parse valid XML', () => {
    const result = parseLabelConfig('<View><Text name="t" value="$text"/></View>')
    expect('type' in result).toBe(true)
    expect((result as ParsedComponent).type).toBe('View')
  })

  it('should return error for invalid XML', () => {
    const result = parseLabelConfig('<View><Unclosed</View>')
    expect('message' in result).toBe(true)
  })

  it('should preserve text content as props.content', () => {
    const result = parseLabelConfig('<View><Header>Title Here</Header></View>')
    const header = (result as ParsedComponent).children[0]
    expect(header.props.content).toBe('Title Here')
  })

  it('should not set content for elements with children', () => {
    const result = parseLabelConfig('<View><Choices name="c" toName="t"><Choice value="a"/></Choices></View>')
    const choices = (result as ParsedComponent).children[0]
    expect(choices.props.content).toBeUndefined()
  })
})

describe('validateParsedConfig', () => {
  it('should report error for non-View root element', () => {
    const config: ParsedComponent = { type: 'NotView', props: {}, children: [] }
    const result = validateParsedConfig(config)
    expect(result.valid).toBe(false)
    expect(result.errors).toContain('Root element must be <View>')
  })

  it('should validate Text component requires name', () => {
    const config: ParsedComponent = {
      type: 'View',
      props: {},
      children: [{ type: 'Text', props: { value: '$text' }, children: [] }],
    }
    const result = validateParsedConfig(config)
    expect(result.errors.some((e) => e.includes('Text component requires \'name\''))).toBe(true)
  })

  it('should validate Text component requires value', () => {
    const config: ParsedComponent = {
      type: 'View',
      props: {},
      children: [{ type: 'Text', props: { name: 't' }, children: [] }],
    }
    const result = validateParsedConfig(config)
    expect(result.errors.some((e) => e.includes('Text component requires \'value\''))).toBe(true)
  })

  it('should validate TextArea requires name and toName', () => {
    const config: ParsedComponent = {
      type: 'View',
      props: {},
      children: [{ type: 'TextArea', props: {}, children: [] }],
    }
    const result = validateParsedConfig(config)
    expect(result.errors.some((e) => e.includes('TextArea component requires \'name\''))).toBe(true)
    expect(result.errors.some((e) => e.includes('TextArea component requires \'toName\''))).toBe(true)
  })

  it('should validate Choices requires children', () => {
    const config: ParsedComponent = {
      type: 'View',
      props: {},
      children: [{ type: 'Choices', props: { name: 'c', toName: 't' }, children: [] }],
    }
    const result = validateParsedConfig(config)
    expect(result.errors.some((e) => e.includes('at least one Choice'))).toBe(true)
  })

  it('should validate Choices requires name and toName', () => {
    const config: ParsedComponent = {
      type: 'View',
      props: {},
      children: [{ type: 'Choices', props: {}, children: [{ type: 'Choice', props: { value: 'a' }, children: [] }] }],
    }
    const result = validateParsedConfig(config)
    expect(result.errors.some((e) => e.includes('Choices component requires \'name\''))).toBe(true)
    expect(result.errors.some((e) => e.includes('Choices component requires \'toName\''))).toBe(true)
  })

  it('should validate Choice requires value', () => {
    const config: ParsedComponent = {
      type: 'View',
      props: {},
      children: [
        {
          type: 'Choices',
          props: { name: 'c', toName: 't' },
          children: [{ type: 'Choice', props: {}, children: [] }],
        },
      ],
    }
    const result = validateParsedConfig(config)
    expect(result.errors.some((e) => e.includes('Choice component requires \'value\''))).toBe(true)
  })

  it('should return valid for correct configuration', () => {
    const config: ParsedComponent = {
      type: 'View',
      props: {},
      children: [
        { type: 'Text', props: { name: 't', value: '$text' }, children: [] },
        {
          type: 'Choices',
          props: { name: 'c', toName: 't' },
          children: [{ type: 'Choice', props: { value: 'a' }, children: [] }],
        },
      ],
    }
    const result = validateParsedConfig(config)
    expect(result.valid).toBe(true)
  })
})

describe('extractDataFields', () => {
  it('should extract $ references from props', () => {
    const config: ParsedComponent = {
      type: 'View',
      props: {},
      children: [
        { type: 'Text', props: { name: 't', value: '$text' }, children: [] },
        { type: 'Text', props: { name: 'q', value: '$question' }, children: [] },
      ],
    }
    const fields = extractDataFields(config)
    expect(fields).toContain('text')
    expect(fields).toContain('question')
  })

  it('should not extract non-$ values', () => {
    const config: ParsedComponent = {
      type: 'View',
      props: {},
      children: [{ type: 'Header', props: { value: 'static' }, children: [] }],
    }
    const fields = extractDataFields(config)
    expect(fields).toEqual([])
  })
})

describe('extractRequiredDataFields', () => {
  it('should extract fields only from required=true components', () => {
    const config: ParsedComponent = {
      type: 'View',
      props: {},
      children: [
        { type: 'TextArea', props: { name: 'a', toName: 't', value: '$field1', required: 'true' }, children: [] },
        { type: 'TextArea', props: { name: 'b', toName: 't', value: '$field2' }, children: [] },
      ],
    }
    const fields = extractRequiredDataFields(config)
    expect(fields).toContain('field1')
    expect(fields).not.toContain('field2')
  })

  it('should handle boolean required=true', () => {
    const config: ParsedComponent = {
      type: 'View',
      props: {},
      children: [
        { type: 'TextArea', props: { name: 'a', toName: 't', value: '$field1', required: true }, children: [] },
      ],
    }
    const fields = extractRequiredDataFields(config)
    expect(fields).toContain('field1')
  })

  it('should return empty for no required fields', () => {
    const config: ParsedComponent = {
      type: 'View',
      props: {},
      children: [
        { type: 'TextArea', props: { name: 'a', toName: 't', value: '$field1' }, children: [] },
      ],
    }
    const fields = extractRequiredDataFields(config)
    expect(fields).toEqual([])
  })
})

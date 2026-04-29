/**
 * Comprehensive tests for dataBinding.ts
 * Target: 90%+ coverage
 */

import {
  buildAnnotationResult,
  buildSpanAnnotationResult,
  mapLegacyAnnotation,
  parseSpanAnnotations,
  resolveDataBinding,
  resolvePropsDataBindings,
  validateTaskDataFields,
} from '../dataBinding'

describe('dataBinding', () => {
  describe('resolveDataBinding', () => {
    describe('basic data binding', () => {
      it('should resolve simple data binding from root level', () => {
        const taskData = { text: 'Hello World' }
        expect(resolveDataBinding('$text', taskData)).toBe('Hello World')
      })

      it('should resolve simple data binding from nested data property', () => {
        const taskData = { data: { text: 'Hello World' } }
        expect(resolveDataBinding('$text', taskData)).toBe('Hello World')
      })

      it('should prefer root level over nested data property', () => {
        const taskData = {
          text: 'Root text',
          data: { text: 'Nested text' },
        }
        expect(resolveDataBinding('$text', taskData)).toBe('Root text')
      })

      it('should return static text as-is', () => {
        const taskData = {}
        expect(resolveDataBinding('static text', taskData)).toBe('static text')
      })

      it('should return non-string values as-is', () => {
        const taskData = {}
        expect(resolveDataBinding(123, taskData)).toBe(123)
        expect(resolveDataBinding(true, taskData)).toBe(true)
        expect(resolveDataBinding(null, taskData)).toBe(null)
        expect(resolveDataBinding(undefined, taskData)).toBe(undefined)
        expect(resolveDataBinding({ key: 'value' }, taskData)).toEqual({
          key: 'value',
        })
        expect(resolveDataBinding([1, 2, 3], taskData)).toEqual([1, 2, 3])
      })

      it('should return string without $ prefix as-is', () => {
        const taskData = { text: 'Hello' }
        expect(resolveDataBinding('text', taskData)).toBe('text')
        expect(resolveDataBinding('no-dollar', taskData)).toBe('no-dollar')
      })
    })

    describe('nested path resolution', () => {
      it('should resolve nested path at root level', () => {
        const taskData = {
          user: {
            name: 'John Doe',
            email: 'john@example.com',
          },
        }
        expect(resolveDataBinding('$user.name', taskData)).toBe('John Doe')
        expect(resolveDataBinding('$user.email', taskData)).toBe(
          'john@example.com'
        )
      })

      it('should resolve nested path in data property', () => {
        const taskData = {
          data: {
            user: {
              name: 'Jane Doe',
              email: 'jane@example.com',
            },
          },
        }
        expect(resolveDataBinding('$user.name', taskData)).toBe('Jane Doe')
        expect(resolveDataBinding('$user.email', taskData)).toBe(
          'jane@example.com'
        )
      })

      it('should resolve deeply nested paths', () => {
        const taskData = {
          document: {
            metadata: {
              author: {
                name: 'Test Author',
                id: 123,
              },
            },
          },
        }
        expect(
          resolveDataBinding('$document.metadata.author.name', taskData)
        ).toBe('Test Author')
        expect(
          resolveDataBinding('$document.metadata.author.id', taskData)
        ).toBe(123)
      })

      it('should return undefined for missing nested path', () => {
        const taskData = {
          user: { name: 'John' },
        }
        expect(resolveDataBinding('$user.missing', taskData)).toBeUndefined()
        expect(
          resolveDataBinding('$user.name.invalid', taskData)
        ).toBeUndefined()
      })

      it('should return undefined for path through null value', () => {
        const taskData = {
          user: null,
        }
        expect(resolveDataBinding('$user.name', taskData)).toBeUndefined()
      })

      it('should return undefined for path through non-object value', () => {
        const taskData = {
          text: 'string value',
        }
        expect(resolveDataBinding('$text.property', taskData)).toBeUndefined()
      })
    })

    describe('case-insensitive key resolution', () => {
      it('should resolve $sachverhalt when task data has Sachverhalt', () => {
        const taskData = { Sachverhalt: 'Legal case text' }
        expect(resolveDataBinding('$sachverhalt', taskData)).toBe(
          'Legal case text'
        )
      })

      it('should resolve $Sachverhalt when task data has sachverhalt', () => {
        const taskData = { sachverhalt: 'Legal case text' }
        expect(resolveDataBinding('$Sachverhalt', taskData)).toBe(
          'Legal case text'
        )
      })

      it('should prefer exact case match over case-insensitive match', () => {
        const taskData = {
          sachverhalt: 'lowercase',
          Sachverhalt: 'capitalized',
        }
        expect(resolveDataBinding('$sachverhalt', taskData)).toBe('lowercase')
        expect(resolveDataBinding('$Sachverhalt', taskData)).toBe('capitalized')
      })

      it('should resolve case-insensitively in nested data property', () => {
        const taskData = { data: { Sachverhalt: 'nested case text' } }
        expect(resolveDataBinding('$sachverhalt', taskData)).toBe(
          'nested case text'
        )
      })

      it('should resolve nested paths case-insensitively', () => {
        const taskData = { Document: { Metadata: { Author: 'Test' } } }
        expect(
          resolveDataBinding('$document.metadata.author', taskData)
        ).toBe('Test')
      })
    })

    describe('edge cases', () => {
      it('should handle empty string binding', () => {
        const taskData = { '': 'empty key' }
        // When binding is just '$', it tries to get empty string key from taskData
        // Since taskData has '' key, it returns 'empty key'
        expect(resolveDataBinding('$', taskData)).toBe('empty key')
      })

      it('should handle null taskData.data', () => {
        const taskData = {
          data: null,
          text: 'Root text',
        }
        expect(resolveDataBinding('$text', taskData)).toBe('Root text')
      })

      it('should handle undefined taskData.data', () => {
        const taskData = {
          data: undefined,
          text: 'Root text',
        }
        expect(resolveDataBinding('$text', taskData)).toBe('Root text')
      })

      it('should handle non-object taskData.data', () => {
        const taskData = {
          data: 'string value',
          text: 'Root text',
        }
        expect(resolveDataBinding('$text', taskData)).toBe('Root text')
      })

      it('should handle empty taskData', () => {
        const taskData = {}
        expect(resolveDataBinding('$text', taskData)).toBeUndefined()
      })

      it('should handle missing key in both root and data', () => {
        const taskData = {
          data: { other: 'value' },
          another: 'value',
        }
        expect(resolveDataBinding('$missing', taskData)).toBeUndefined()
      })

      it('should resolve null values correctly', () => {
        const taskData = { field: null }
        expect(resolveDataBinding('$field', taskData)).toBeNull()
      })

      it('should resolve undefined values correctly from root', () => {
        const taskData = { field: undefined }
        expect(resolveDataBinding('$field', taskData)).toBeUndefined()
      })

      it('should resolve array values', () => {
        const taskData = { items: [1, 2, 3] }
        expect(resolveDataBinding('$items', taskData)).toEqual([1, 2, 3])
      })

      it('should resolve object values', () => {
        const taskData = { config: { key: 'value' } }
        expect(resolveDataBinding('$config', taskData)).toEqual({
          key: 'value',
        })
      })
    })
  })

  describe('resolvePropsDataBindings', () => {
    it('should resolve all data bindings in props object', () => {
      const props = {
        value: '$text',
        placeholder: '$placeholder',
        label: 'Static Label',
      }
      const taskData = {
        text: 'Hello',
        placeholder: 'Enter text...',
      }

      const resolved = resolvePropsDataBindings(props, taskData)

      expect(resolved).toEqual({
        value: 'Hello',
        placeholder: 'Enter text...',
        label: 'Static Label',
      })
    })

    it('should handle empty props object', () => {
      const props = {}
      const taskData = { text: 'Hello' }

      const resolved = resolvePropsDataBindings(props, taskData)

      expect(resolved).toEqual({})
    })

    it('should handle props with no data bindings', () => {
      const props = {
        label: 'Static',
        placeholder: 'No binding',
      }
      const taskData = { text: 'Hello' }

      const resolved = resolvePropsDataBindings(props, taskData)

      expect(resolved).toEqual({
        label: 'Static',
        placeholder: 'No binding',
      })
    })

    it('should handle nested path bindings in props', () => {
      const props = {
        userName: '$user.name',
        userEmail: '$user.email',
      }
      const taskData = {
        user: {
          name: 'John Doe',
          email: 'john@example.com',
        },
      }

      const resolved = resolvePropsDataBindings(props, taskData)

      expect(resolved).toEqual({
        userName: 'John Doe',
        userEmail: 'john@example.com',
      })
    })

    it('should handle missing bindings gracefully', () => {
      const props = {
        value: '$missing',
        label: '$alsoMissing',
      }
      const taskData = { text: 'Hello' }

      const resolved = resolvePropsDataBindings(props, taskData)

      expect(resolved).toEqual({
        value: undefined,
        label: undefined,
      })
    })

    it('should handle mixed types in props', () => {
      const props = {
        text: '$text',
        number: 123,
        boolean: true,
        object: { key: 'value' },
        array: [1, 2, 3],
      }
      const taskData = { text: 'Hello' }

      const resolved = resolvePropsDataBindings(props, taskData)

      expect(resolved).toEqual({
        text: 'Hello',
        number: 123,
        boolean: true,
        object: { key: 'value' },
        array: [1, 2, 3],
      })
    })
  })

  describe('buildAnnotationResult', () => {
    describe('TextArea component', () => {
      it('should build TextArea annotation result', () => {
        const result = buildAnnotationResult(
          'answer',
          'TextArea',
          'My answer text',
          'question'
        )

        expect(result).toEqual({
          value: { text: ['My answer text'] },
          from_name: 'answer',
          to_name: 'question',
          type: 'textarea',
        })
      })

      it('should handle empty TextArea value', () => {
        const result = buildAnnotationResult(
          'answer',
          'TextArea',
          '',
          'question'
        )

        expect(result).toEqual({
          value: { text: [''] },
          from_name: 'answer',
          to_name: 'question',
          type: 'textarea',
        })
      })
    })

    describe('Choices component', () => {
      it('should build Choices annotation result with single choice', () => {
        const result = buildAnnotationResult(
          'sentiment',
          'Choices',
          'Positive',
          'text'
        )

        expect(result).toEqual({
          value: { choices: ['Positive'] },
          from_name: 'sentiment',
          to_name: 'text',
          type: 'choices',
        })
      })

      it('should build Choices annotation result with array of choices', () => {
        const result = buildAnnotationResult(
          'tags',
          'Choices',
          ['Tag1', 'Tag2', 'Tag3'],
          'text'
        )

        expect(result).toEqual({
          value: { choices: ['Tag1', 'Tag2', 'Tag3'] },
          from_name: 'tags',
          to_name: 'text',
          type: 'choices',
        })
      })
    })

    describe('other component types', () => {
      it('should build Rating annotation result', () => {
        const result = buildAnnotationResult('quality', 'Rating', 5, 'text')

        expect(result).toEqual({
          value: 5,
          from_name: 'quality',
          to_name: 'text',
          type: 'rating',
        })
      })

      it('should build Number annotation result', () => {
        const result = buildAnnotationResult('count', 'Number', 42, 'text')

        expect(result).toEqual({
          value: 42,
          from_name: 'count',
          to_name: 'text',
          type: 'number',
        })
      })

      it('should build Labels annotation result', () => {
        const result = buildAnnotationResult(
          'entities',
          'Labels',
          { start: 0, end: 5, labels: ['Person'] },
          'text'
        )

        expect(result).toEqual({
          value: { start: 0, end: 5, labels: ['Person'] },
          from_name: 'entities',
          to_name: 'text',
          type: 'labels',
        })
      })

      it('should use lowercase type for unknown component types', () => {
        const result = buildAnnotationResult(
          'custom',
          'CustomComponent',
          'value',
          'text'
        )

        expect(result).toEqual({
          value: 'value',
          from_name: 'custom',
          to_name: 'text',
          type: 'customcomponent',
        })
      })
    })

    describe('type mapping', () => {
      it('should map component types to annotation types correctly', () => {
        const mappings = [
          { componentType: 'TextArea', expected: 'textarea' },
          { componentType: 'Choices', expected: 'choices' },
          { componentType: 'Labels', expected: 'labels' },
          { componentType: 'Rating', expected: 'rating' },
          { componentType: 'Number', expected: 'number' },
        ]

        mappings.forEach(({ componentType, expected }) => {
          const result = buildAnnotationResult(
            'test',
            componentType,
            'value',
            'target'
          )
          expect(result.type).toBe(expected)
        })
      })
    })
  })

  describe('mapLegacyAnnotation', () => {
    describe('short_answer field', () => {
      it('should map short_answer to textarea annotation', () => {
        const result = mapLegacyAnnotation('short_answer', 'My answer')

        expect(result).toEqual({
          value: { text: ['My answer'] },
          from_name: 'short_answer',
          to_name: 'question',
          type: 'textarea',
        })
      })

      it('should handle empty short_answer', () => {
        const result = mapLegacyAnnotation('short_answer', '')

        expect(result).toEqual({
          value: { text: [''] },
          from_name: 'short_answer',
          to_name: 'question',
          type: 'textarea',
        })
      })
    })

    describe('reasoning field', () => {
      it('should map reasoning to textarea annotation', () => {
        const result = mapLegacyAnnotation('reasoning', 'My reasoning')

        expect(result).toEqual({
          value: { text: ['My reasoning'] },
          from_name: 'reasoning',
          to_name: 'question',
          type: 'textarea',
        })
      })
    })

    describe('confidence field', () => {
      it('should map confidence to choices annotation with string', () => {
        const result = mapLegacyAnnotation('confidence', 'High')

        expect(result).toEqual({
          value: { choices: ['High'] },
          from_name: 'confidence',
          to_name: 'question',
          type: 'choices',
        })
      })

      it('should map confidence to choices annotation with array', () => {
        const result = mapLegacyAnnotation('confidence', ['High', 'Medium'])

        expect(result).toEqual({
          value: { choices: ['High', 'Medium'] },
          from_name: 'confidence',
          to_name: 'question',
          type: 'choices',
        })
      })
    })

    describe('unknown fields', () => {
      it('should return null for unknown field names', () => {
        expect(mapLegacyAnnotation('unknown', 'value')).toBeNull()
        expect(mapLegacyAnnotation('invalid', 'value')).toBeNull()
        expect(mapLegacyAnnotation('custom_field', 'value')).toBeNull()
      })

      it('should return null for empty field name', () => {
        expect(mapLegacyAnnotation('', 'value')).toBeNull()
      })
    })

    describe('all legacy fields', () => {
      it('should map all supported legacy fields correctly', () => {
        const fields = [
          { name: 'short_answer', type: 'textarea' },
          { name: 'reasoning', type: 'textarea' },
          { name: 'confidence', type: 'choices' },
        ]

        fields.forEach(({ name, type }) => {
          const result = mapLegacyAnnotation(name, 'test value')
          expect(result).not.toBeNull()
          expect(result?.type).toBe(type)
          expect(result?.from_name).toBe(name)
          expect(result?.to_name).toBe('question')
        })
      })
    })
  })

  describe('validateTaskDataFields', () => {
    describe('flat data structure', () => {
      it('should validate all required fields present', () => {
        const taskData = {
          context: 'Test context',
          question: 'Test question',
          answer: 'Test answer',
        }
        const result = validateTaskDataFields(
          ['context', 'question', 'answer'],
          taskData
        )

        expect(result.valid).toBe(true)
        expect(result.missingFields).toEqual([])
      })

      it('should detect single missing field', () => {
        const taskData = {
          context: 'Test context',
          answer: 'Test answer',
        }
        const result = validateTaskDataFields(
          ['context', 'question', 'answer'],
          taskData
        )

        expect(result.valid).toBe(false)
        expect(result.missingFields).toEqual(['question'])
      })

      it('should detect multiple missing fields', () => {
        const taskData = {
          context: 'Test context',
        }
        const result = validateTaskDataFields(
          ['context', 'question', 'answer'],
          taskData
        )

        expect(result.valid).toBe(false)
        expect(result.missingFields).toEqual(['question', 'answer'])
      })

      it('should detect all fields missing', () => {
        const taskData = {}
        const result = validateTaskDataFields(['context', 'question'], taskData)

        expect(result.valid).toBe(false)
        expect(result.missingFields).toEqual(['context', 'question'])
      })

      it('should treat null values as missing', () => {
        const taskData = {
          context: 'Test context',
          question: null,
        }
        const result = validateTaskDataFields(['context', 'question'], taskData)

        expect(result.valid).toBe(false)
        expect(result.missingFields).toEqual(['question'])
      })

      it('should treat undefined values as missing', () => {
        const taskData = {
          context: 'Test context',
          question: undefined,
        }
        const result = validateTaskDataFields(['context', 'question'], taskData)

        expect(result.valid).toBe(false)
        expect(result.missingFields).toEqual(['question'])
      })
    })

    describe('nested data structure', () => {
      it('should validate fields in data property', () => {
        const taskData = {
          data: {
            context: 'Test context',
            question: 'Test question',
          },
        }
        const result = validateTaskDataFields(['context', 'question'], taskData)

        expect(result.valid).toBe(true)
        expect(result.missingFields).toEqual([])
      })

      it('should detect missing fields in data property', () => {
        const taskData = {
          data: {
            context: 'Test context',
          },
        }
        const result = validateTaskDataFields(['context', 'question'], taskData)

        expect(result.valid).toBe(false)
        expect(result.missingFields).toEqual(['question'])
      })

      it('should prefer root level over data property', () => {
        const taskData = {
          context: 'Root context',
          data: {
            context: 'Nested context',
            question: 'Nested question',
          },
        }
        const result = validateTaskDataFields(['context', 'question'], taskData)

        expect(result.valid).toBe(true)
        expect(result.missingFields).toEqual([])
      })

      it('should handle mixed root and nested fields', () => {
        const taskData = {
          context: 'Root context',
          data: {
            question: 'Nested question',
          },
        }
        const result = validateTaskDataFields(['context', 'question'], taskData)

        expect(result.valid).toBe(true)
        expect(result.missingFields).toEqual([])
      })
    })

    describe('case-insensitive field validation', () => {
      it('should validate fields present with different casing', () => {
        const taskData = {
          Sachverhalt: 'text',
          Musterloesung: 'solution',
        }
        const result = validateTaskDataFields(
          ['sachverhalt', 'musterloesung'],
          taskData
        )
        expect(result.valid).toBe(true)
        expect(result.missingFields).toEqual([])
      })

      it('should validate uppercase required fields against lowercase data', () => {
        const taskData = { sachverhalt: 'text' }
        const result = validateTaskDataFields(['Sachverhalt'], taskData)
        expect(result.valid).toBe(true)
        expect(result.missingFields).toEqual([])
      })
    })

    describe('nested path validation', () => {
      it('should validate nested paths at root level', () => {
        const taskData = {
          user: {
            name: 'John Doe',
          },
        }
        const result = validateTaskDataFields(['user.name'], taskData)

        expect(result.valid).toBe(true)
        expect(result.missingFields).toEqual([])
      })

      it('should validate nested paths in data property', () => {
        const taskData = {
          data: {
            user: {
              name: 'Jane Doe',
            },
          },
        }
        const result = validateTaskDataFields(['user.name'], taskData)

        expect(result.valid).toBe(true)
        expect(result.missingFields).toEqual([])
      })

      it('should detect missing nested paths', () => {
        const taskData = {
          user: {
            email: 'john@example.com',
          },
        }
        const result = validateTaskDataFields(['user.name'], taskData)

        expect(result.valid).toBe(false)
        expect(result.missingFields).toEqual(['user.name'])
      })

      it('should validate deeply nested paths', () => {
        const taskData = {
          document: {
            metadata: {
              author: {
                name: 'Test Author',
              },
            },
          },
        }
        const result = validateTaskDataFields(
          ['document.metadata.author.name'],
          taskData
        )

        expect(result.valid).toBe(true)
        expect(result.missingFields).toEqual([])
      })
    })

    describe('edge cases', () => {
      it('should validate empty required fields array', () => {
        const taskData = { context: 'Test' }
        const result = validateTaskDataFields([], taskData)

        expect(result.valid).toBe(true)
        expect(result.missingFields).toEqual([])
      })

      it('should handle null data property', () => {
        const taskData = {
          data: null,
          context: 'Root context',
        }
        const result = validateTaskDataFields(['context'], taskData)

        expect(result.valid).toBe(true)
        expect(result.missingFields).toEqual([])
      })

      it('should handle undefined data property', () => {
        const taskData = {
          data: undefined,
          context: 'Root context',
        }
        const result = validateTaskDataFields(['context'], taskData)

        expect(result.valid).toBe(true)
        expect(result.missingFields).toEqual([])
      })

      it('should handle non-object data property', () => {
        const taskData = {
          data: 'string value',
          context: 'Root context',
        }
        const result = validateTaskDataFields(['context'], taskData)

        expect(result.valid).toBe(true)
        expect(result.missingFields).toEqual([])
      })

      it('should handle empty object data property', () => {
        const taskData = {
          data: {},
        }
        const result = validateTaskDataFields(['context'], taskData)

        expect(result.valid).toBe(false)
        expect(result.missingFields).toEqual(['context'])
      })

      it('should handle empty string values as valid', () => {
        const taskData = {
          context: '',
          question: '',
        }
        const result = validateTaskDataFields(['context', 'question'], taskData)

        expect(result.valid).toBe(true)
        expect(result.missingFields).toEqual([])
      })

      it('should handle zero values as valid', () => {
        const taskData = {
          count: 0,
          rating: 0,
        }
        const result = validateTaskDataFields(['count', 'rating'], taskData)

        expect(result.valid).toBe(true)
        expect(result.missingFields).toEqual([])
      })

      it('should handle false boolean values as valid', () => {
        const taskData = {
          flag: false,
          enabled: false,
        }
        const result = validateTaskDataFields(['flag', 'enabled'], taskData)

        expect(result.valid).toBe(true)
        expect(result.missingFields).toEqual([])
      })
    })
  })

  describe('buildSpanAnnotationResult', () => {
    it('should build annotation result with single span', () => {
      const spans = [
        {
          id: 'span-1',
          start: 0,
          end: 10,
          text: 'John Smith',
          labels: ['PERSON'],
        },
      ]

      const result = buildSpanAnnotationResult('label', 'text', spans)

      expect(result).toEqual({
        from_name: 'label',
        to_name: 'text',
        type: 'labels',
        value: {
          spans: [
            {
              id: 'span-1',
              start: 0,
              end: 10,
              text: 'John Smith',
              labels: ['PERSON'],
            },
          ],
        },
      })
    })

    it('should build annotation result with multiple spans', () => {
      const spans = [
        {
          id: 'span-1',
          start: 0,
          end: 10,
          text: 'John Smith',
          labels: ['PERSON'],
        },
        {
          id: 'span-2',
          start: 20,
          end: 36,
          text: 'Acme Corporation',
          labels: ['ORGANIZATION'],
        },
        {
          id: 'span-3',
          start: 43,
          end: 55,
          text: 'January 2024',
          labels: ['DATE'],
        },
      ]

      const result = buildSpanAnnotationResult('entities', 'content', spans)

      expect(result.from_name).toBe('entities')
      expect(result.to_name).toBe('content')
      expect(result.type).toBe('labels')
      expect(result.value.spans).toHaveLength(3)
      expect(result.value.spans[0].labels).toEqual(['PERSON'])
      expect(result.value.spans[1].labels).toEqual(['ORGANIZATION'])
      expect(result.value.spans[2].labels).toEqual(['DATE'])
    })

    it('should build annotation result with empty spans array', () => {
      const result = buildSpanAnnotationResult('label', 'text', [])

      expect(result).toEqual({
        from_name: 'label',
        to_name: 'text',
        type: 'labels',
        value: { spans: [] },
      })
    })

    it('should handle spans with multiple labels', () => {
      const spans = [
        {
          id: 'span-1',
          start: 0,
          end: 15,
          text: 'Dr. John Smith',
          labels: ['PERSON', 'TITLE'],
        },
      ]

      const result = buildSpanAnnotationResult('label', 'text', spans)

      expect(result.value.spans[0].labels).toEqual(['PERSON', 'TITLE'])
    })
  })

  describe('parseSpanAnnotations', () => {
    it('should parse spans from new format with spans array', () => {
      const annotationResult = {
        from_name: 'label',
        to_name: 'text',
        type: 'labels',
        value: {
          spans: [
            {
              id: 'span-1',
              start: 0,
              end: 10,
              text: 'John Smith',
              labels: ['PERSON'],
            },
            {
              id: 'span-2',
              start: 20,
              end: 36,
              text: 'Acme Corporation',
              labels: ['ORGANIZATION'],
            },
          ],
        },
      }

      const spans = parseSpanAnnotations(annotationResult)

      expect(spans).toHaveLength(2)
      expect(spans[0]).toEqual({
        id: 'span-1',
        start: 0,
        end: 10,
        text: 'John Smith',
        labels: ['PERSON'],
      })
      expect(spans[1]).toEqual({
        id: 'span-2',
        start: 20,
        end: 36,
        text: 'Acme Corporation',
        labels: ['ORGANIZATION'],
      })
    })

    it('should parse legacy format with single span', () => {
      const annotationResult = {
        id: 'legacy-span-1',
        from_name: 'label',
        to_name: 'text',
        type: 'labels',
        value: {
          start: 0,
          end: 10,
          text: 'John Smith',
          labels: ['PERSON'],
        },
      }

      const spans = parseSpanAnnotations(annotationResult)

      expect(spans).toHaveLength(1)
      expect(spans[0].start).toBe(0)
      expect(spans[0].end).toBe(10)
      expect(spans[0].text).toBe('John Smith')
      expect(spans[0].labels).toEqual(['PERSON'])
    })

    it('should return empty array for null result', () => {
      const spans = parseSpanAnnotations(null)
      expect(spans).toEqual([])
    })

    it('should return empty array for result with null value', () => {
      const annotationResult = {
        from_name: 'label',
        to_name: 'text',
        type: 'labels',
        value: null,
      }

      const spans = parseSpanAnnotations(annotationResult as any)
      expect(spans).toEqual([])
    })

    it('should return empty array for result with empty spans array', () => {
      const annotationResult = {
        from_name: 'label',
        to_name: 'text',
        type: 'labels',
        value: { spans: [] },
      }

      const spans = parseSpanAnnotations(annotationResult)
      expect(spans).toEqual([])
    })

    it('should generate id for spans without id', () => {
      const annotationResult = {
        from_name: 'label',
        to_name: 'text',
        type: 'labels',
        value: {
          spans: [
            {
              start: 0,
              end: 10,
              text: 'John Smith',
              labels: ['PERSON'],
            },
          ],
        },
      }

      const spans = parseSpanAnnotations(annotationResult)

      expect(spans).toHaveLength(1)
      expect(spans[0].id).toBeDefined()
      expect(spans[0].id).toMatch(/^span-/)
    })

    it('should handle missing fields with defaults', () => {
      const annotationResult = {
        from_name: 'label',
        to_name: 'text',
        type: 'labels',
        value: {
          spans: [{}],
        },
      }

      const spans = parseSpanAnnotations(annotationResult)

      expect(spans).toHaveLength(1)
      expect(spans[0].start).toBe(0)
      expect(spans[0].end).toBe(0)
      expect(spans[0].text).toBe('')
      expect(spans[0].labels).toEqual([])
    })

    it('should handle result with no spans property and no start', () => {
      const annotationResult = {
        from_name: 'label',
        to_name: 'text',
        type: 'labels',
        value: { other: 'data' },
      }

      const spans = parseSpanAnnotations(annotationResult)
      expect(spans).toEqual([])
    })
  })
})

/**
 * Unit tests for JSON utility functions
 */

import {
  extractFieldPaths,
  flattenJson,
  getNestedValue,
  searchInNestedObject,
  valueMatchesQuery,
} from '../jsonUtils'

describe('flattenJson', () => {
  it('should flatten simple object', () => {
    const obj = { a: 1, b: 2 }
    const result = flattenJson(obj)
    expect(result).toEqual({ a: 1, b: 2 })
  })

  it('should flatten nested object with dot notation', () => {
    const obj = {
      user: {
        name: 'John',
        address: {
          city: 'Munich',
          country: 'Germany',
        },
      },
    }
    const result = flattenJson(obj)
    expect(result).toEqual({
      'user.name': 'John',
      'user.address.city': 'Munich',
      'user.address.country': 'Germany',
    })
  })

  it('should handle arrays with bracket notation', () => {
    const obj = {
      items: ['apple', 'banana'],
      nested: {
        tags: ['tag1', 'tag2'],
      },
    }
    const result = flattenJson(obj)
    expect(result).toEqual({
      items: ['apple', 'banana'], // Simple arrays kept as-is
      'nested.tags': ['tag1', 'tag2'],
    })
  })

  it('should handle arrays of objects', () => {
    const obj = {
      users: [
        { id: 1, name: 'Alice' },
        { id: 2, name: 'Bob' },
      ],
    }
    const result = flattenJson(obj)
    expect(result).toEqual({
      'users[0].id': 1,
      'users[0].name': 'Alice',
      'users[1].id': 2,
      'users[1].name': 'Bob',
    })
  })

  it('should respect maxDepth parameter', () => {
    const obj = {
      level1: {
        level2: {
          level3: {
            level4: 'deep',
          },
        },
      },
    }
    const result = flattenJson(obj, '', 2)
    expect(result).toEqual({
      'level1.level2': { level3: { level4: 'deep' } },
    })
  })

  it('should handle null and undefined values', () => {
    const obj = {
      nullValue: null,
      undefinedValue: undefined,
      nested: {
        nullNested: null,
      },
    }
    const result = flattenJson(obj)
    expect(result).toEqual({
      nullValue: null,
      undefinedValue: undefined,
      'nested.nullNested': null,
    })
  })

  it('should handle empty objects and arrays', () => {
    const obj = {
      emptyObj: {},
      emptyArr: [],
      nested: {
        empty: {},
      },
    }
    const result = flattenJson(obj)
    expect(result).toEqual({
      emptyArr: [],
    })
  })
})

describe('getNestedValue', () => {
  const testObj = {
    user: {
      name: 'John',
      address: {
        city: 'Munich',
      },
      scores: [10, 20, 30],
    },
    items: [
      { id: 1, name: 'Item1' },
      { id: 2, name: 'Item2' },
    ],
  }

  it('should get simple property', () => {
    const result = getNestedValue(testObj, 'user')
    expect(result).toEqual(testObj.user)
  })

  it('should get nested property with dot notation', () => {
    const result = getNestedValue(testObj, 'user.name')
    expect(result).toBe('John')
  })

  it('should get deeply nested property', () => {
    const result = getNestedValue(testObj, 'user.address.city')
    expect(result).toBe('Munich')
  })

  it('should handle array index notation', () => {
    const result = getNestedValue(testObj, 'user.scores[1]')
    expect(result).toBe(20)
  })

  it('should handle array of objects', () => {
    const result = getNestedValue(testObj, 'items[0].name')
    expect(result).toBe('Item1')
  })

  it('should return undefined for non-existent path', () => {
    const result = getNestedValue(testObj, 'user.nonexistent.path')
    expect(result).toBeUndefined()
  })

  it('should return undefined for null or undefined object', () => {
    expect(getNestedValue(null, 'any.path')).toBeUndefined()
    expect(getNestedValue(undefined, 'any.path')).toBeUndefined()
  })

  it('should handle empty path', () => {
    expect(getNestedValue(testObj, '')).toBeUndefined()
  })
})

describe('extractFieldPaths', () => {
  it('should extract all unique field paths from array of objects', () => {
    const objects = [
      { id: 1, name: 'Alice', age: 30 },
      { id: 2, name: 'Bob', city: 'Berlin' },
      { id: 3, age: 25, city: 'Munich' },
    ]
    const paths = extractFieldPaths(objects)
    expect(paths).toEqual(['age', 'city', 'id', 'name'])
  })

  it('should extract nested field paths', () => {
    const objects = [
      { user: { name: 'Alice', age: 30 } },
      { user: { name: 'Bob', address: { city: 'Berlin' } } },
    ]
    const paths = extractFieldPaths(objects)
    expect(paths).toContain('user.name')
    expect(paths).toContain('user.age')
    expect(paths).toContain('user.address.city')
  })

  it('should handle empty array', () => {
    const paths = extractFieldPaths([])
    expect(paths).toEqual([])
  })

  it('should respect maxDepth parameter', () => {
    const objects = [
      {
        level1: {
          level2: {
            level3: {
              level4: 'deep',
            },
          },
        },
      },
    ]
    const paths = extractFieldPaths(objects, 2)
    expect(paths).toEqual(['level1.level2'])
  })
})

describe('valueMatchesQuery', () => {
  it('should match string values case-insensitively', () => {
    expect(valueMatchesQuery('Hello World', 'hello')).toBe(true)
    expect(valueMatchesQuery('Hello World', 'WORLD')).toBe(true)
    expect(valueMatchesQuery('Hello World', 'foo')).toBe(false)
  })

  it('should match number values', () => {
    expect(valueMatchesQuery(123, '123')).toBe(true)
    expect(valueMatchesQuery(123, '12')).toBe(true)
    expect(valueMatchesQuery(123, '456')).toBe(false)
  })

  it('should match boolean values', () => {
    expect(valueMatchesQuery(true, 'true')).toBe(true)
    expect(valueMatchesQuery(false, 'false')).toBe(true)
    expect(valueMatchesQuery(true, 'false')).toBe(false)
  })

  it('should search in arrays', () => {
    expect(valueMatchesQuery(['apple', 'banana'], 'apple')).toBe(true)
    expect(valueMatchesQuery(['apple', 'banana'], 'BANANA')).toBe(true)
    expect(valueMatchesQuery(['apple', 'banana'], 'orange')).toBe(false)
  })

  it('should search in nested objects', () => {
    const obj = { name: 'John', city: 'Munich' }
    expect(valueMatchesQuery(obj, 'john')).toBe(true)
    expect(valueMatchesQuery(obj, 'munich')).toBe(true)
    expect(valueMatchesQuery(obj, 'berlin')).toBe(false)
  })

  it('should handle null and undefined', () => {
    expect(valueMatchesQuery(null, 'null')).toBe(false)
    expect(valueMatchesQuery(undefined, 'undefined')).toBe(false)
  })

  it('should return true for empty query', () => {
    expect(valueMatchesQuery('anything', '')).toBe(true)
    expect(valueMatchesQuery(123, '')).toBe(true)
  })
})

describe('searchInNestedObject', () => {
  const testObj = {
    user: {
      name: 'John Doe',
      email: 'john@example.com',
      address: {
        city: 'Munich',
        country: 'Germany',
      },
    },
    tags: ['developer', 'senior'],
    active: true,
  }

  it('should find query in top-level fields', () => {
    // Search for values, not keys
    expect(searchInNestedObject(testObj, 'true')).toBe(true) // Finds boolean true
    expect(searchInNestedObject(testObj, 'developer')).toBe(true) // Finds in tags array
  })

  it('should find query in nested fields', () => {
    expect(searchInNestedObject(testObj, 'john')).toBe(true)
    expect(searchInNestedObject(testObj, 'munich')).toBe(true)
    expect(searchInNestedObject(testObj, 'germany')).toBe(true)
  })

  it('should find query in arrays', () => {
    expect(searchInNestedObject(testObj, 'developer')).toBe(true)
    expect(searchInNestedObject(testObj, 'senior')).toBe(true)
  })

  it('should be case-insensitive', () => {
    expect(searchInNestedObject(testObj, 'JOHN')).toBe(true)
    expect(searchInNestedObject(testObj, 'Munich')).toBe(true)
  })

  it('should return false for non-matching query', () => {
    expect(searchInNestedObject(testObj, 'notfound')).toBe(false)
    expect(searchInNestedObject(testObj, 'berlin')).toBe(false)
  })

  it('should return true for empty query', () => {
    expect(searchInNestedObject(testObj, '')).toBe(true)
  })

  it('should handle complex nested structures', () => {
    const complexObj = {
      data: {
        prompts: {
          prompt_clean: 'Eine GmbH verkauft ihr Grundstück',
          prompt_enhanced: 'Detaillierte Rechtsfrage',
        },
        fall: 'Der Geschäftsführer handelt ohne Gesellschafterbeschluss',
      },
    }
    expect(searchInNestedObject(complexObj, 'Gesellschafterbeschluss')).toBe(
      true
    )
    expect(searchInNestedObject(complexObj, 'GmbH')).toBe(true)
    expect(searchInNestedObject(complexObj, 'Rechtsfrage')).toBe(true)
  })
})

describe('flattenJson - Additional Edge Cases', () => {
  it('should handle primitives as input', () => {
    expect(flattenJson('string')).toEqual({})
    expect(flattenJson(123)).toEqual({})
    expect(flattenJson(true)).toEqual({})
  })

  it('should handle null as root input', () => {
    expect(flattenJson(null)).toEqual({})
  })

  it('should handle undefined as root input', () => {
    expect(flattenJson(undefined)).toEqual({})
  })

  it('should handle deeply nested arrays of objects', () => {
    const obj = {
      matrix: [
        [
          { x: 1, y: 2 },
          { x: 3, y: 4 },
        ],
        [
          { x: 5, y: 6 },
          { x: 7, y: 8 },
        ],
      ],
    }
    const result = flattenJson(obj)
    // Keys contain literal brackets, so access directly
    expect(result['matrix[0][0].x']).toBe(1)
    expect(result['matrix[0][0].y']).toBe(2)
    expect(result['matrix[1][1].x']).toBe(7)
    expect(result['matrix[1][1].y']).toBe(8)
  })

  it('should handle mixed primitive array', () => {
    const obj = {
      mixed: [1, 'two', true, null],
    }
    const result = flattenJson(obj)
    expect(result.mixed).toEqual([1, 'two', true, null])
  })

  it('should handle array with null values', () => {
    const obj = {
      items: [null, null, null],
    }
    const result = flattenJson(obj)
    expect(result.items).toEqual([null, null, null])
  })

  it('should handle deeply nested empty objects', () => {
    const obj = {
      level1: {
        level2: {
          level3: {},
        },
      },
    }
    const result = flattenJson(obj)
    expect(Object.keys(result)).toHaveLength(0)
  })

  it('should handle max depth with arrays', () => {
    const obj = {
      deep: [[[[[{ value: 'too deep' }]]]]],
    }
    const result = flattenJson(obj, '', 2)
    // Key contains literal brackets, so access directly
    expect(result['deep[0]']).toBeDefined()
  })

  it('should handle objects with hasOwnProperty keys', () => {
    const obj = {
      hasOwnProperty: 'value',
      toString: 'another',
      constructor: 'test',
    }
    const result = flattenJson(obj)
    expect(result.hasOwnProperty).toBe('value')
    expect(result.toString).toBe('another')
    expect(result.constructor).toBe('test')
  })

  it('should handle with custom prefix', () => {
    const obj = { a: { b: 1 } }
    const result = flattenJson(obj, 'root')
    // Keys contain literal dots, so access directly
    expect(result['root.a.b']).toBe(1)
  })

  it('should handle complex array of objects with different structures', () => {
    const obj = {
      items: [
        { id: 1, name: 'A' },
        { id: 2, age: 30 },
        { id: 3, active: true },
      ],
    }
    const result = flattenJson(obj)
    // Keys contain literal brackets, so access directly
    expect(result['items[0].id']).toBe(1)
    expect(result['items[0].name']).toBe('A')
    expect(result['items[1].id']).toBe(2)
    expect(result['items[1].age']).toBe(30)
    expect(result['items[2].id']).toBe(3)
    expect(result['items[2].active']).toBe(true)
  })
})

describe('getNestedValue - Additional Edge Cases', () => {
  it('should handle path with only brackets', () => {
    const obj = [[['deep']]]
    expect(getNestedValue(obj, '[0][0][0]')).toBe('deep')
  })

  it('should handle numeric string keys in objects', () => {
    const obj = { '0': { '1': 'value' } }
    expect(getNestedValue(obj, '0.1')).toBe('value')
  })

  it('should return undefined for out of bounds array index', () => {
    const obj = { arr: [1, 2, 3] }
    expect(getNestedValue(obj, 'arr[99]')).toBeUndefined()
  })

  it('should handle negative array indices', () => {
    const obj = { arr: [1, 2, 3] }
    expect(getNestedValue(obj, 'arr[-1]')).toBeUndefined()
  })

  it('should handle path through null values', () => {
    const obj = { a: { b: null } }
    expect(getNestedValue(obj, 'a.b.c')).toBeUndefined()
  })

  it('should handle path through undefined values', () => {
    const obj = { a: { b: undefined } }
    expect(getNestedValue(obj, 'a.b.c')).toBeUndefined()
  })

  it('should handle complex bracket notation', () => {
    const obj = { items: [{ data: [{ value: 42 }] }] }
    expect(getNestedValue(obj, 'items[0].data[0].value')).toBe(42)
  })

  it('should handle whitespace in brackets', () => {
    const obj = { arr: ['value'] }
    // Function tolerates whitespace - Number(' 0 ') = 0
    expect(getNestedValue(obj, 'arr[ 0 ]')).toBe('value')
  })
})

describe('extractFieldPaths - Additional Edge Cases', () => {
  it('should handle objects with only empty objects', () => {
    const objects = [{}, {}, {}]
    const paths = extractFieldPaths(objects)
    expect(paths).toEqual([])
  })

  it('should handle single object', () => {
    const objects = [{ id: 1, name: 'Test' }]
    const paths = extractFieldPaths(objects)
    expect(paths).toEqual(['id', 'name'])
  })

  it('should handle objects with arrays', () => {
    const objects = [{ tags: ['a', 'b'] }, { tags: ['c', 'd', 'e'] }]
    const paths = extractFieldPaths(objects)
    expect(paths).toContain('tags')
  })

  it('should handle objects with null values', () => {
    const objects = [
      { a: null, b: 'value' },
      { a: 'value', b: null },
    ]
    const paths = extractFieldPaths(objects)
    expect(paths).toEqual(['a', 'b'])
  })

  it('should sort paths alphabetically', () => {
    const objects = [{ z: 1, a: 2, m: 3 }]
    const paths = extractFieldPaths(objects)
    expect(paths).toEqual(['a', 'm', 'z'])
  })

  it('should handle very deeply nested objects', () => {
    const objects = [
      {
        level1: {
          level2: {
            level3: {
              level4: {
                level5: 'deep',
              },
            },
          },
        },
      },
    ]
    const paths = extractFieldPaths(objects, 10)
    expect(paths).toContain('level1.level2.level3.level4.level5')
  })
})

describe('valueMatchesQuery - Additional Edge Cases', () => {
  it('should handle numeric query', () => {
    expect(valueMatchesQuery(456, '4')).toBe(true)
    expect(valueMatchesQuery(456, '56')).toBe(true)
    expect(valueMatchesQuery(456, '789')).toBe(false)
  })

  it('should handle boolean true query', () => {
    expect(valueMatchesQuery(true, 'tru')).toBe(true)
    expect(valueMatchesQuery(true, 'rue')).toBe(true)
  })

  it('should handle arrays with nested objects', () => {
    const arr = [{ name: 'John' }, { name: 'Jane' }]
    expect(valueMatchesQuery(arr, 'john')).toBe(true)
    expect(valueMatchesQuery(arr, 'jane')).toBe(true)
    expect(valueMatchesQuery(arr, 'bob')).toBe(false)
  })

  it('should handle nested objects with deep nesting', () => {
    const obj = {
      level1: {
        level2: {
          level3: 'found',
        },
      },
    }
    expect(valueMatchesQuery(obj, 'found')).toBe(true)
    expect(valueMatchesQuery(obj, 'missing')).toBe(false)
  })

  it('should handle empty arrays', () => {
    expect(valueMatchesQuery([], 'anything')).toBe(false)
  })

  it('should handle empty objects', () => {
    expect(valueMatchesQuery({}, 'anything')).toBe(false)
  })

  it('should handle zero as value', () => {
    expect(valueMatchesQuery(0, '0')).toBe(true)
    expect(valueMatchesQuery(0, 'zero')).toBe(false)
  })

  it('should handle empty string value', () => {
    expect(valueMatchesQuery('', 'anything')).toBe(false)
    expect(valueMatchesQuery('', '')).toBe(true)
  })

  it('should be case insensitive for mixed case', () => {
    expect(valueMatchesQuery('HeLLo WoRLd', 'hello')).toBe(true)
    expect(valueMatchesQuery('HeLLo WoRLd', 'WORLD')).toBe(true)
  })
})

describe('searchInNestedObject - Additional Edge Cases', () => {
  it('should handle null object', () => {
    // null without prefix flattens to empty object, so no values to search
    expect(searchInNestedObject(null, 'query')).toBe(false)
  })

  it('should handle undefined object', () => {
    // undefined without prefix flattens to empty object, so no values to search
    expect(searchInNestedObject(undefined, 'query')).toBe(false)
  })

  it('should handle primitive values', () => {
    // primitives without prefix flatten to empty object, so no values to search
    expect(searchInNestedObject('string', 'str')).toBe(false)
    expect(searchInNestedObject(123, '12')).toBe(false)
    expect(searchInNestedObject(true, 'true')).toBe(false)
  })

  it('should handle deeply nested arrays', () => {
    const obj = {
      matrix: [
        [
          [1, 2, 3],
          [4, 5, 6],
        ],
        [
          [7, 8, 9],
          [10, 11, 12],
        ],
      ],
    }
    expect(searchInNestedObject(obj, '11')).toBe(true)
    expect(searchInNestedObject(obj, '99')).toBe(false)
  })

  it('should handle objects with special characters', () => {
    const obj = {
      'special-key': 'special-value',
      'key.with.dots': 'value',
    }
    expect(searchInNestedObject(obj, 'special-value')).toBe(true)
    expect(searchInNestedObject(obj, 'value')).toBe(true)
  })

  it('should handle large nested structures within depth limit', () => {
    const obj = {
      level1: {
        level2: {
          level3: {
            level4: {
              level5: 'deep',
            },
          },
        },
      },
    }
    expect(() => searchInNestedObject(obj, 'deep')).not.toThrow()
  })

  it('should handle very large objects', () => {
    const largeObj: any = {}
    for (let i = 0; i < 1000; i++) {
      largeObj[`key${i}`] = `value${i}`
    }
    expect(searchInNestedObject(largeObj, 'value500')).toBe(true)
    expect(searchInNestedObject(largeObj, 'value9999')).toBe(false)
  })

  it('should handle mixed types in nested structure', () => {
    const obj = {
      string: 'text',
      number: 42,
      boolean: true,
      null: null,
      undefined: undefined,
      array: [1, 'two', true],
      object: { nested: 'value' },
    }
    expect(searchInNestedObject(obj, 'text')).toBe(true)
    expect(searchInNestedObject(obj, '42')).toBe(true)
    expect(searchInNestedObject(obj, 'true')).toBe(true)
    expect(searchInNestedObject(obj, 'two')).toBe(true)
    expect(searchInNestedObject(obj, 'value')).toBe(true)
  })
})

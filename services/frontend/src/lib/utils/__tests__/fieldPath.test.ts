import {
  formatValue,
  getAllPaths,
  getValueByPath,
  hasPath,
  setValueByPath,
} from '../fieldPath'

describe('getValueByPath', () => {
  it('gets simple property value', () => {
    const data = { name: 'John', age: 30 }
    expect(getValueByPath(data, 'name')).toBe('John')
    expect(getValueByPath(data, 'age')).toBe(30)
  })

  it('gets nested property value', () => {
    const data = { user: { name: 'John', address: { city: 'NYC' } } }
    expect(getValueByPath(data, 'user.name')).toBe('John')
    expect(getValueByPath(data, 'user.address.city')).toBe('NYC')
  })

  it('gets array element by index', () => {
    const data = { items: ['first', 'second', 'third'] }
    expect(getValueByPath(data, 'items[0]')).toBe('first')
    expect(getValueByPath(data, 'items[1]')).toBe('second')
    expect(getValueByPath(data, 'items[2]')).toBe('third')
  })

  it('gets nested array element properties', () => {
    const data = { items: [{ value: 42 }, { value: 84 }] }
    expect(getValueByPath(data, 'items[0].value')).toBe(42)
    expect(getValueByPath(data, 'items[1].value')).toBe(84)
  })

  it('handles mixed array and object notation', () => {
    const data = {
      users: [{ profile: { name: 'Alice' } }, { profile: { name: 'Bob' } }],
    }
    expect(getValueByPath(data, 'users[0].profile.name')).toBe('Alice')
    expect(getValueByPath(data, 'users[1].profile.name')).toBe('Bob')
  })

  it('returns default value for missing path', () => {
    const data = { name: 'John' }
    expect(getValueByPath(data, 'missing', 'default')).toBe('default')
    expect(getValueByPath(data, 'user.name', 'default')).toBe('default')
  })

  it('returns undefined when no default value provided for missing path', () => {
    const data = { name: 'John' }
    expect(getValueByPath(data, 'missing')).toBeUndefined()
  })

  it('returns default value for null data', () => {
    expect(getValueByPath(null, 'path', 'default')).toBe('default')
    expect(getValueByPath(undefined, 'path', 'default')).toBe('default')
  })

  it('returns default value for undefined path', () => {
    const data = { name: 'John' }
    expect(getValueByPath(data, undefined, 'default')).toBe('default')
  })

  it('returns default value for empty string path', () => {
    const data = { name: 'John' }
    expect(getValueByPath(data, '', 'default')).toBe('default')
  })

  it('handles null values in path', () => {
    const data = { user: null }
    expect(getValueByPath(data, 'user.name', 'default')).toBe('default')
  })

  it('handles undefined values in path', () => {
    const data = { user: undefined }
    expect(getValueByPath(data, 'user.name', 'default')).toBe('default')
  })

  it('returns value when it is 0', () => {
    const data = { count: 0 }
    expect(getValueByPath(data, 'count')).toBe(0)
  })

  it('returns value when it is false', () => {
    const data = { enabled: false }
    expect(getValueByPath(data, 'enabled')).toBe(false)
  })

  it('returns value when it is empty string', () => {
    const data = { text: '' }
    expect(getValueByPath(data, 'text')).toBe('')
  })

  it('handles numeric string segments', () => {
    const data = { items: { '0': 'value' } }
    expect(getValueByPath(data, 'items.0')).toBe('value')
  })
})

describe('setValueByPath', () => {
  it('sets simple property value', () => {
    const data = { name: 'John' }
    setValueByPath(data, 'age', 30)
    expect(data).toEqual({ name: 'John', age: 30 })
  })

  it('sets nested property value', () => {
    const data = { user: { name: 'John' } }
    setValueByPath(data, 'user.age', 30)
    expect(data).toEqual({ user: { name: 'John', age: 30 } })
  })

  it('creates nested structure if missing', () => {
    const data = {}
    setValueByPath(data, 'user.profile.name', 'John')
    expect(data).toEqual({ user: { profile: { name: 'John' } } })
  })

  it('sets array element by index', () => {
    const data = { items: [] }
    setValueByPath(data, 'items[0]', 'first')
    setValueByPath(data, 'items[1]', 'second')
    expect(data.items).toEqual(['first', 'second'])
  })

  it('sets nested array element properties', () => {
    const data = { items: [] }
    setValueByPath(data, 'items[0].value', 42)
    expect(data).toEqual({ items: [{ value: 42 }] })
  })

  it('creates array when next segment is numeric', () => {
    const data = {}
    setValueByPath(data, 'list[0]', 'item')
    expect(Array.isArray(data.list)).toBe(true)
    expect(data.list[0]).toBe('item')
  })

  it('creates object when next segment is not numeric', () => {
    const data = {}
    setValueByPath(data, 'user.name', 'John')
    expect(typeof data.user).toBe('object')
    expect(Array.isArray(data.user)).toBe(false)
  })

  it('handles array notation conversion', () => {
    const data = {}
    setValueByPath(data, 'items[0]', 'value')
    expect(data.items[0]).toBe('value')
  })

  it('returns modified data object', () => {
    const data = {}
    const result = setValueByPath(data, 'name', 'John')
    expect(result).toBe(data)
    expect(result.name).toBe('John')
  })

  it('returns original data when path is empty', () => {
    const data = { name: 'John' }
    const result = setValueByPath(data, '', 'value')
    expect(result).toBe(data)
    expect(result).toEqual({ name: 'John' })
  })

  it('overwrites existing values', () => {
    const data = { name: 'John', age: 25 }
    setValueByPath(data, 'age', 30)
    expect(data.age).toBe(30)
  })

  it('handles numeric string segments in last position', () => {
    const data = { items: {} }
    setValueByPath(data, 'items.0', 'value')
    expect(data.items[0]).toBe('value')
  })
})

describe('hasPath', () => {
  it('returns true for existing simple path', () => {
    const data = { name: 'John', age: 30 }
    expect(hasPath(data, 'name')).toBe(true)
    expect(hasPath(data, 'age')).toBe(true)
  })

  it('returns true for existing nested path', () => {
    const data = { user: { name: 'John', profile: { city: 'NYC' } } }
    expect(hasPath(data, 'user.name')).toBe(true)
    expect(hasPath(data, 'user.profile.city')).toBe(true)
  })

  it('returns true for existing array path', () => {
    const data = { items: ['a', 'b', 'c'] }
    expect(hasPath(data, 'items[0]')).toBe(true)
    expect(hasPath(data, 'items[2]')).toBe(true)
  })

  it('returns false for missing path', () => {
    const data = { name: 'John' }
    expect(hasPath(data, 'missing')).toBe(false)
    expect(hasPath(data, 'user.name')).toBe(false)
  })

  it('returns false for out of bounds array index', () => {
    const data = { items: ['a', 'b'] }
    expect(hasPath(data, 'items[5]')).toBe(false)
  })

  it('returns true for values that are 0, false, or empty string', () => {
    const data = { count: 0, enabled: false, text: '' }
    expect(hasPath(data, 'count')).toBe(true)
    expect(hasPath(data, 'enabled')).toBe(true)
    expect(hasPath(data, 'text')).toBe(true)
  })

  it('returns false for undefined values', () => {
    const data = { value: undefined }
    expect(hasPath(data, 'value')).toBe(false)
  })
})

describe('getAllPaths', () => {
  it('returns all leaf paths from flat object', () => {
    const data = { name: 'John', age: 30, city: 'NYC' }
    const paths = getAllPaths(data)

    expect(paths).toContain('name')
    expect(paths).toContain('age')
    expect(paths).toContain('city')
    expect(paths).toHaveLength(3)
  })

  it('returns all leaf paths from nested object', () => {
    const data = {
      user: {
        name: 'John',
        profile: {
          age: 30,
          city: 'NYC',
        },
      },
    }
    const paths = getAllPaths(data)

    expect(paths).toContain('user.name')
    expect(paths).toContain('user.profile.age')
    expect(paths).toContain('user.profile.city')
    expect(paths).toHaveLength(3)
  })

  it('returns all leaf paths from arrays with notation', () => {
    const data = {
      items: [{ value: 1 }, { value: 2 }],
    }
    const paths = getAllPaths(data)

    expect(paths).toContain('items[0].value')
    expect(paths).toContain('items[1].value')
    expect(paths).toHaveLength(2)
  })

  it('returns all leaf paths from mixed structures', () => {
    const data = {
      name: 'Project',
      users: [
        { name: 'Alice', age: 30 },
        { name: 'Bob', age: 25 },
      ],
      metadata: {
        created: '2024-01-01',
        tags: ['a', 'b'],
      },
    }
    const paths = getAllPaths(data)

    expect(paths).toContain('name')
    expect(paths).toContain('users[0].name')
    expect(paths).toContain('users[0].age')
    expect(paths).toContain('users[1].name')
    expect(paths).toContain('users[1].age')
    expect(paths).toContain('metadata.created')
    expect(paths).toContain('metadata.tags[0]')
    expect(paths).toContain('metadata.tags[1]')
  })

  it('returns empty array for null input', () => {
    expect(getAllPaths(null)).toEqual([])
    expect(getAllPaths(undefined)).toEqual([])
  })

  it('returns empty array for primitive values without prefix', () => {
    expect(getAllPaths(42)).toEqual([])
    expect(getAllPaths('string')).toEqual([])
    expect(getAllPaths(true)).toEqual([])
  })

  it('returns single path for primitive value with prefix', () => {
    expect(getAllPaths(42, 'value')).toEqual(['value'])
    expect(getAllPaths('string', 'text')).toEqual(['text'])
  })

  it('handles Date objects as leaf values', () => {
    const data = { created: new Date('2024-01-01') }
    const paths = getAllPaths(data)

    expect(paths).toContain('created')
    expect(paths).toHaveLength(1)
  })

  it('handles empty objects', () => {
    expect(getAllPaths({})).toEqual([])
  })

  it('handles empty arrays', () => {
    expect(getAllPaths([])).toEqual([])
  })

  it('handles arrays of primitives', () => {
    const data = { tags: ['a', 'b', 'c'] }
    const paths = getAllPaths(data)

    expect(paths).toContain('tags[0]')
    expect(paths).toContain('tags[1]')
    expect(paths).toContain('tags[2]')
    expect(paths).toHaveLength(3)
  })
})

describe('formatValue', () => {
  it('formats null and undefined as empty string', () => {
    expect(formatValue(null)).toBe('')
    expect(formatValue(undefined)).toBe('')
  })

  it('formats boolean true as Yes', () => {
    expect(formatValue(true)).toBe('Yes')
  })

  it('formats boolean false as No', () => {
    expect(formatValue(false)).toBe('No')
  })

  it('formats Date objects', () => {
    const date = new Date('2024-01-15')
    const formatted = formatValue(date)

    expect(formatted).toContain('1')
    expect(formatted).toContain('15')
    expect(formatted).toContain('2024')
  })

  it('formats arrays by joining formatted values', () => {
    expect(formatValue(['a', 'b', 'c'])).toBe('a, b, c')
    expect(formatValue([1, 2, 3])).toBe('1, 2, 3')
  })

  it('formats nested arrays', () => {
    expect(formatValue([true, false])).toBe('Yes, No')
  })

  it('formats arrays with null values', () => {
    expect(formatValue(['a', null, 'b'])).toBe('a, , b')
  })

  it('formats objects as JSON', () => {
    const obj = { name: 'John', age: 30 }
    const formatted = formatValue(obj)

    expect(formatted).toContain('"name"')
    expect(formatted).toContain('"John"')
    expect(formatted).toContain('"age"')
    expect(formatted).toContain('30')
  })

  it('formats numbers as strings', () => {
    expect(formatValue(42)).toBe('42')
    expect(formatValue(3.14)).toBe('3.14')
    expect(formatValue(0)).toBe('0')
  })

  it('formats strings as-is', () => {
    expect(formatValue('hello')).toBe('hello')
    expect(formatValue('')).toBe('')
  })

  it('formats complex nested objects', () => {
    const obj = {
      user: { name: 'John' },
      items: [1, 2],
    }
    const formatted = formatValue(obj)

    expect(formatted).toContain('"user"')
    expect(formatted).toContain('"name"')
    expect(formatted).toContain('"items"')
  })
})

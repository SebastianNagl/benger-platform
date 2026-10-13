import {
  getMetricCell,
  getMetricDetail,
  hasMetricCell,
  hasMetricDetail,
  registerMetricCell,
  registerMetricDetail,
} from '../metricRenderers'
import { setRegistrationOwner } from '../owner'

describe('Metric Cell Renderer Registry', () => {
  test('getMetricCell returns null for unregistered metric', () => {
    expect(getMetricCell('definitely_not_registered_metric')).toBeNull()
  })

  test('hasMetricCell returns false for unregistered metric', () => {
    expect(hasMetricCell('also_not_registered')).toBe(false)
  })

  test('registerMetricCell + getMetricCell roundtrip and invocation', () => {
    registerMetricCell('test_metric_cell', (v: any) => v?.value ?? null)
    const fn = getMetricCell('test_metric_cell')
    expect(fn).toBeTruthy()
    expect(fn!({ value: 7.5 })).toBe(7.5)
    expect(fn!({})).toBeNull()
    expect(hasMetricCell('test_metric_cell')).toBe(true)
  })

  test('register overwrites prior renderer for same metric', () => {
    registerMetricCell('test_metric_cell_overwrite', () => 'first')
    registerMetricCell('test_metric_cell_overwrite', () => 'second')
    expect(getMetricCell('test_metric_cell_overwrite')!(null)).toBe('second')
  })
})

describe('Metric Detail Renderer Registry', () => {
  test('getMetricDetail returns null for unregistered metric', () => {
    expect(getMetricDetail('not_registered_detail')).toBeNull()
  })

  test('hasMetricDetail returns false for unregistered metric', () => {
    expect(hasMetricDetail('not_registered_detail')).toBe(false)
  })

  test('registerMetricDetail + getMetricDetail roundtrip', () => {
    const StubComponent = (() => null) as any
    registerMetricDetail('test_metric_detail', StubComponent)
    expect(getMetricDetail('test_metric_detail')).toBe(StubComponent)
    expect(hasMetricDetail('test_metric_detail')).toBe(true)
  })
})

describe('Metric renderer owner attribution', () => {
  let warn: jest.SpyInstance

  beforeEach(() => {
    setRegistrationOwner(null)
    warn = jest.spyOn(console, 'warn').mockImplementation(() => undefined)
  })

  afterEach(() => {
    setRegistrationOwner(null)
    warn.mockRestore()
  })

  test('a different owner overwriting a cell renderer warns and wins', () => {
    setRegistrationOwner('extended')
    registerMetricCell('owner_cell', () => 'first')
    registerMetricCell('owner_cell', () => 'first again')
    expect(warn).not.toHaveBeenCalled()
    setRegistrationOwner('compliance')
    registerMetricCell('owner_cell', () => 'second')
    expect(warn).toHaveBeenCalledWith(
      '[extensions] metric cell "owner_cell" registered by compliance replaces extended',
    )
    expect(getMetricCell('owner_cell')!(null)).toBe('second')
  })

  test('cell and detail renderers are attributed separately', () => {
    const Detail = (() => null) as any
    setRegistrationOwner('extended')
    registerMetricCell('owner_split', () => 'cell')
    setRegistrationOwner('compliance')
    registerMetricDetail('owner_split', Detail)
    expect(warn).not.toHaveBeenCalled()
    registerMetricDetail('owner_split', Detail)
    expect(warn).not.toHaveBeenCalled()
    setRegistrationOwner('extended')
    registerMetricDetail('owner_split', Detail)
    expect(warn).toHaveBeenCalledWith(
      '[extensions] metric detail "owner_split" registered by extended replaces compliance',
    )
    expect(getMetricDetail('owner_split')).toBe(Detail)
  })
})

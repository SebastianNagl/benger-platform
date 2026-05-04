import {
  registerMetricCell,
  registerMetricDetail,
  getMetricCell,
  getMetricDetail,
  hasMetricCell,
  hasMetricDetail,
} from '../metricRenderers'

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

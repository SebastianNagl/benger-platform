/**
 * @jest-environment jsdom
 *
 * preloadableLazy: an annotation component whose code can be loaded ahead,
 * so the form renders every field in its first frame instead of one
 * placeholder per field that each swap for the field as its code arrives.
 */
import '@testing-library/jest-dom'
import { act, render, screen } from '@testing-library/react'
import React, { Suspense, useState } from 'react'

import { preloadableLazy, type AnnotationComponentProps } from '../registry'

function Field({ value }: AnnotationComponentProps) {
  const [count, setCount] = useState(0)
  return (
    <button data-testid="field" onClick={() => setCount((c) => c + 1)}>
      {String(value)}:{count}
    </button>
  )
}

const props = {
  config: { type: 'X', props: {}, children: [] },
  taskData: {},
  value: 'v',
  onChange: () => {},
  onAnnotation: () => {},
} as AnnotationComponentProps

function deferredModule() {
  let resolve!: () => void
  const loader = jest.fn(
    () =>
      new Promise<{ default: typeof Field }>((done) => {
        resolve = () => done({ default: Field })
      }),
  )
  return { loader, resolve: () => resolve() }
}

describe('preloadableLazy', () => {
  it('suspends like React.lazy when rendered before its code is in', async () => {
    const { loader, resolve } = deferredModule()
    const { component: C, isLoaded } = preloadableLazy(loader)
    render(
      <Suspense fallback={<p>loading</p>}>
        <C {...props} />
      </Suspense>,
    )
    expect(screen.getByText('loading')).toBeInTheDocument()
    expect(isLoaded()).toBe(false)
    await act(async () => resolve())
    expect(await screen.findByTestId('field')).toHaveTextContent('v:0')
    expect(isLoaded()).toBe(true)
  })

  it('renders directly, without a fallback frame, once preloaded', async () => {
    const { loader, resolve } = deferredModule()
    const { component: C, preload, isLoaded } = preloadableLazy(loader)
    const pending = preload()
    await act(async () => {
      resolve()
      await pending
    })
    expect(isLoaded()).toBe(true)
    render(
      <Suspense fallback={<p>loading</p>}>
        <C {...props} />
      </Suspense>,
    )
    expect(screen.queryByText('loading')).not.toBeInTheDocument()
    expect(screen.getByTestId('field')).toHaveTextContent('v:0')
    // One load for preload and render together.
    expect(loader).toHaveBeenCalledTimes(1)
  })

  it('keeps a mounted field (and its state) when its code arrives', async () => {
    const { loader, resolve } = deferredModule()
    const { component: C } = preloadableLazy(loader)
    const { rerender } = render(
      <Suspense fallback={<p>loading</p>}>
        <C {...props} />
      </Suspense>,
    )
    await act(async () => resolve())
    const field = await screen.findByTestId('field')
    act(() => field.click())
    expect(field).toHaveTextContent('v:1')
    rerender(
      <Suspense fallback={<p>loading</p>}>
        <C {...props} value="w" />
      </Suspense>,
    )
    expect(screen.getByTestId('field')).toHaveTextContent('w:1')
  })

  it('retries a failed load', async () => {
    const loader = jest
      .fn()
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValueOnce({ default: Field })
    const { preload, isLoaded } = preloadableLazy(loader)
    await expect(preload()).rejects.toThrow('offline')
    await preload()
    expect(isLoaded()).toBe(true)
    expect(loader).toHaveBeenCalledTimes(2)
  })
})

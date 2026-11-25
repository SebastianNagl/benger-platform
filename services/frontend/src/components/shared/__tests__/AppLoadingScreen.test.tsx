/**
 * @jest-environment jsdom
 */
import { ShellVariantProvider } from '@/components/layout/ShellVariant'
import { useUIStore } from '@/stores'
import { act, render, screen } from '@testing-library/react'
import { AppLoadingScreen } from '../AppLoadingScreen'

describe('AppLoadingScreen', () => {
  afterEach(() => {
    act(() => useUIStore.setState({ isSidebarHidden: false }))
  })

  it('centers on the content area next to the pinned sidebar', () => {
    render(<AppLoadingScreen testId="screen" />)
    const el = screen.getByTestId('screen')
    expect(el).toHaveAttribute('data-sidebar-offset', 'true')
    expect(el.className).toContain('lg:pl-64')
    expect(el.className).toContain('xl:pl-72')
    expect(el.className).toContain('2xl:pl-80')
  })

  it('centers on the window when the sidebar is hidden', () => {
    act(() => useUIStore.setState({ isSidebarHidden: true }))
    render(<AppLoadingScreen testId="screen" />)
    const el = screen.getByTestId('screen')
    expect(el).not.toHaveAttribute('data-sidebar-offset')
    expect(el.className).not.toContain('lg:pl-64')
  })

  it('has no offset in the visitor shell', () => {
    render(
      <ShellVariantProvider value="public">
        <AppLoadingScreen testId="screen" />
      </ShellVariantProvider>,
    )
    expect(screen.getByTestId('screen')).not.toHaveAttribute(
      'data-sidebar-offset',
    )
  })
})

describe('AppLoadingScreen in a page', () => {
  afterEach(() => {
    act(() => useUIStore.setState({ isSidebarHidden: false }))
  })

  it('leaves the shell visible and usable', () => {
    render(<AppLoadingScreen testId="screen" covering={false} label="x" />)
    const el = screen.getByTestId('screen')
    expect(el.className).toContain('pointer-events-none')
    expect(el.className).not.toContain('z-50')
    expect(el.className).not.toContain('bg-white')
  })

  it('centers on the same box as the covering screen', () => {
    const { rerender } = render(<AppLoadingScreen testId="screen" />)
    const box = (c: string) =>
      c.split(' ').filter((k) => /^(fixed|inset-|.*pl-)/.test(k))
    const covering = box(screen.getByTestId('screen').className)
    rerender(<AppLoadingScreen testId="screen" covering={false} />)
    expect(box(screen.getByTestId('screen').className)).toEqual(covering)
  })
})

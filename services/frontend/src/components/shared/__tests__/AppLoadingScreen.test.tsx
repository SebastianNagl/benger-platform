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

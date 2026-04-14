/**
 * fn3 function coverage for MobileNavigation.tsx
 * Targets: MenuIcon, XIcon, MobileNavigationDialog, useIsInsideMobileNavigation,
 *          useMobileNavigationStore toggle/open/close
 */

import React from 'react'
import { render, screen, fireEvent, act } from '@testing-library/react'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    locale: 'en',
    t: (key: string) => key,
    changeLocale: jest.fn(),
    isReady: true,
  }),
}))

// Mock headlessui
jest.mock('@headlessui/react', () => ({
  Dialog: ({ children, open }: any) => open ? <div data-testid="dialog">{children}</div> : null,
  DialogBackdrop: ({ children }: any) => <div>{children}</div>,
  DialogPanel: ({ children }: any) => <div>{children}</div>,
  TransitionChild: ({ children }: any) => <div>{children}</div>,
}))

// Mock framer-motion
jest.mock('framer-motion', () => ({
  motion: {
    div: ({ children, ...props }: any) => <div {...props}>{children}</div>,
  },
}))

// Mock Header and Navigation
jest.mock('@/components/layout/Header', () => ({
  Header: () => <div data-testid="header">Header</div>,
}))

jest.mock('@/components/layout/Navigation', () => ({
  Navigation: () => <nav data-testid="navigation">Nav</nav>,
}))

import { MobileNavigation, useMobileNavigationStore, useIsInsideMobileNavigation } from '../MobileNavigation'

describe('MobileNavigation fn3', () => {
  beforeEach(() => {
    // Reset store state
    useMobileNavigationStore.setState({ isOpen: false })
  })

  it('renders toggle button', () => {
    render(<MobileNavigation />)
    const btn = screen.getByRole('button')
    expect(btn).toBeInTheDocument()
  })

  it('toggles navigation on button click', () => {
    render(<MobileNavigation />)
    const btn = screen.getByRole('button')

    expect(useMobileNavigationStore.getState().isOpen).toBe(false)
    fireEvent.click(btn)
    expect(useMobileNavigationStore.getState().isOpen).toBe(true)
    fireEvent.click(btn)
    expect(useMobileNavigationStore.getState().isOpen).toBe(false)
  })

  it('store open/close methods work directly', () => {
    const { open, close, toggle } = useMobileNavigationStore.getState()

    act(() => open())
    expect(useMobileNavigationStore.getState().isOpen).toBe(true)

    act(() => close())
    expect(useMobileNavigationStore.getState().isOpen).toBe(false)

    act(() => toggle())
    expect(useMobileNavigationStore.getState().isOpen).toBe(true)
  })
})

describe('useIsInsideMobileNavigation', () => {
  it('returns false when outside MobileNavigation', () => {
    function TestConsumer() {
      const isInside = useIsInsideMobileNavigation()
      return <span>{isInside ? 'inside' : 'outside'}</span>
    }
    render(<TestConsumer />)
    expect(screen.getByText('outside')).toBeInTheDocument()
  })
})

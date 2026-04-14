/**
 * Additional coverage for MobileNavigation - store functions, context hook
 */

import { render, screen } from '@testing-library/react'
import React from 'react'
import { useIsInsideMobileNavigation, useMobileNavigationStore } from '../MobileNavigation'

// We only test the non-JSX exports to avoid complex mocking of HeadlessUI+framer-motion

describe('useMobileNavigationStore', () => {
  afterEach(() => {
    // Reset store to default
    useMobileNavigationStore.setState({ isOpen: false })
  })

  it('starts with isOpen false', () => {
    expect(useMobileNavigationStore.getState().isOpen).toBe(false)
  })

  it('open sets isOpen to true', () => {
    useMobileNavigationStore.getState().open()
    expect(useMobileNavigationStore.getState().isOpen).toBe(true)
  })

  it('close sets isOpen to false', () => {
    useMobileNavigationStore.getState().open()
    useMobileNavigationStore.getState().close()
    expect(useMobileNavigationStore.getState().isOpen).toBe(false)
  })

  it('toggle flips isOpen from false to true', () => {
    useMobileNavigationStore.getState().toggle()
    expect(useMobileNavigationStore.getState().isOpen).toBe(true)
  })

  it('toggle flips isOpen from true to false', () => {
    useMobileNavigationStore.setState({ isOpen: true })
    useMobileNavigationStore.getState().toggle()
    expect(useMobileNavigationStore.getState().isOpen).toBe(false)
  })
})

describe('useIsInsideMobileNavigation', () => {
  it('returns false by default (outside provider)', () => {
    let result: boolean = true
    function TestComponent() {
      result = useIsInsideMobileNavigation()
      return null
    }
    render(<TestComponent />)
    expect(result).toBe(false)
  })
})

/**
 * @jest-environment jsdom
 *
 * Tests for the student⇄expert view-mode toggle COMPONENT (Issue #35, platform
 * shell).
 *
 * The component is a pure view over useViewModeSwitch(): it renders nothing when
 * the switch is unavailable (community edition OR the closed-beta lock), a
 * neutral skeleton while loading, and the dropdown when ready. The hook's own
 * gating (incl. the beta lock) + the switchTo action are covered in
 * useViewModeSwitch.test.tsx.
 */

import { fireEvent, render, screen } from '@testing-library/react'
import React from 'react'

// --- Mocks -----------------------------------------------------------------

const mockSwitchTo = jest.fn()
let mockViewMode: {
  status: 'unavailable' | 'loading' | 'ready'
  resolved: 'student' | 'expert'
  pending: boolean
  switchTo: jest.Mock
} = {
  status: 'ready',
  resolved: 'student',
  pending: false,
  switchTo: mockSwitchTo,
}

jest.mock('@/hooks/useViewModeSwitch', () => ({
  useViewModeSwitch: () => mockViewMode,
}))

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({ t: (k: string) => k }),
}))

import { ViewModeToggle } from '../ViewModeToggle'

describe('ViewModeToggle', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockViewMode = {
      status: 'ready',
      resolved: 'student',
      pending: false,
      switchTo: mockSwitchTo,
    }
  })

  it('renders nothing when the switch is unavailable (community edition / beta lock)', () => {
    mockViewMode = { ...mockViewMode, status: 'unavailable' }
    const { container } = render(<ViewModeToggle />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders a neutral skeleton while loading (no role flicker)', () => {
    mockViewMode = { ...mockViewMode, status: 'loading' }
    render(<ViewModeToggle />)
    expect(screen.getByTestId('view-mode-toggle-skeleton')).toBeInTheDocument()
    expect(screen.queryByTestId('view-mode-toggle')).not.toBeInTheDocument()
  })

  it('renders the dropdown trigger when the switch is ready', () => {
    render(<ViewModeToggle />)
    const trigger = screen.getByTestId('view-mode-toggle')
    expect(trigger).toBeInTheDocument()
    // The trigger reflects the current resolved mode.
    expect(trigger).toHaveAttribute('data-ui-mode', 'student')
  })

  it('disables the trigger while a switch is pending', () => {
    mockViewMode = { ...mockViewMode, pending: true }
    render(<ViewModeToggle />)
    expect(screen.getByTestId('view-mode-toggle')).toBeDisabled()
  })

  it('opening the dropdown does NOT switch — only selecting an option does', async () => {
    render(<ViewModeToggle />)
    fireEvent.click(screen.getByTestId('view-mode-toggle')) // open menu
    expect(mockSwitchTo).not.toHaveBeenCalled()

    // Select the expert option (unique text — the trigger shows the student label).
    const expertOption = await screen.findByText('student.view.expert')
    fireEvent.click(expertOption)
    expect(mockSwitchTo).toHaveBeenCalledWith('expert')
  })

  it('shows both modes; selecting a mode calls switchTo with it', async () => {
    render(<ViewModeToggle />)
    fireEvent.click(screen.getByTestId('view-mode-toggle'))
    await screen.findByText('student.view.expert')
    const studentOption = document.querySelector(
      '[data-ui-mode-option="student"]'
    ) as HTMLElement
    const expertOption = document.querySelector(
      '[data-ui-mode-option="expert"]'
    ) as HTMLElement
    expect(studentOption).toBeInTheDocument()
    expect(expertOption).toBeInTheDocument()
    fireEvent.click(studentOption)
    expect(mockSwitchTo).toHaveBeenCalledWith('student')
  })

  it('renders the sidebar variant trigger', () => {
    render(<ViewModeToggle variant="sidebar" />)
    expect(screen.getByTestId('view-mode-toggle')).toBeInTheDocument()
  })
})

/**
 * @jest-environment jsdom
 *
 * Branch coverage: ThemeToggle.tsx
 * Target: br1[0] L29 - !mounted path (before hydration)
 */

jest.mock('next-themes', () => ({
  useTheme: () => ({ resolvedTheme: 'light', setTheme: jest.fn() }),
}))

jest.mock('@/contexts/HydrationContext', () => ({
  useHydration: () => false,
}))

import { render } from '@testing-library/react'
import { ThemeToggle } from '../ThemeToggle'

describe('ThemeToggle br3', () => {
  it('renders unmounted state (pre-hydration)', () => {
    const { container } = render(<ThemeToggle />)
    expect(container.querySelector('svg')).toBeInTheDocument()
    expect(container.querySelector('button')).not.toBeInTheDocument()
  })
})

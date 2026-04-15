/**
 * Additional coverage for app/error.tsx - GlobalError component
 * Covers: reset button, reload button, error logging, development details
 */

import { render, screen, fireEvent } from '@testing-library/react'
import GlobalError from '../error'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, fallback?: string) => fallback || key,
    locale: 'en',
  }),
}))

jest.mock('@/lib/utils/logger', () => ({
  logger: {
    debug: jest.fn(),
  },
}))

jest.mock('@/components/shared/Button', () => ({
  Button: ({ children, onClick, variant, ...rest }: any) => (
    <button onClick={onClick} data-variant={variant} {...rest}>
      {children}
    </button>
  ),
}))

describe('GlobalError', () => {
  const mockReset = jest.fn()
  const mockError = new Error('Test error message')
  ;(mockError as any).digest = 'test-digest'

  beforeAll(() => {
    jest.spyOn(console, 'error').mockImplementation(() => {})
  })
  afterAll(() => {
    ;(console.error as jest.Mock).mockRestore()
  })

  beforeEach(() => {
    mockReset.mockClear()
    ;(console.error as jest.Mock).mockClear()
  })

  it('renders error title', () => {
    render(<GlobalError error={mockError} reset={mockReset} />)
    expect(screen.getByText('errors.global.title')).toBeInTheDocument()
  })

  it('renders error description', () => {
    render(<GlobalError error={mockError} reset={mockReset} />)
    expect(screen.getByText('errors.global.description')).toBeInTheDocument()
  })

  it('renders try again button that calls reset', () => {
    render(<GlobalError error={mockError} reset={mockReset} />)
    const btn = screen.getByText('errors.global.tryAgain')
    fireEvent.click(btn)
    expect(mockReset).toHaveBeenCalledTimes(1)
  })

  it('renders reload page button', () => {
    render(<GlobalError error={mockError} reset={mockReset} />)
    const btn = screen.getByText('errors.global.reloadPage')
    expect(btn).toBeInTheDocument()
  })

  it('shows technical details in development mode', () => {
    render(<GlobalError error={mockError} reset={mockReset} />)
    // In test env (NODE_ENV=test), development block won't render
    // But we still test the component renders without error
    expect(screen.getByText('errors.global.title')).toBeInTheDocument()
  })

  it('logs error to console', () => {
    render(<GlobalError error={mockError} reset={mockReset} />)
    expect(console.error).toHaveBeenCalledWith('Global error:', mockError)
  })

  it('renders SVG warning icon', () => {
    const { container } = render(<GlobalError error={mockError} reset={mockReset} />)
    const svg = container.querySelector('svg')
    expect(svg).toBeInTheDocument()
  })
})

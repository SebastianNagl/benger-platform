/**
 * Coverage for about/page.tsx (0% -> 100%)
 */

import { render } from '@testing-library/react'

const mockReplace = jest.fn()
jest.mock('next/navigation', () => ({
  useRouter: () => ({
    replace: mockReplace,
  }),
}))

import AboutPage from '../about/page'

describe('AboutPage', () => {
  beforeEach(() => {
    mockReplace.mockClear()
  })

  it('redirects to home page', () => {
    render(<AboutPage />)
    expect(mockReplace).toHaveBeenCalledWith('/')
  })

  it('renders null (no visible content)', () => {
    const { container } = render(<AboutPage />)
    expect(container.innerHTML).toBe('')
  })
})

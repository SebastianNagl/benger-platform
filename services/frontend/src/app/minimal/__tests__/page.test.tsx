/**
 * Tests for the minimal page and layout
 */

import { render, screen } from '@testing-library/react'
import React from 'react'
import MinimalLayout from '../layout'
import MinimalPage from '../page'

jest.mock('@/lib/utils/translate', () => ({
  translate: (key: string) => key,
}))

describe('MinimalPage', () => {
  it('should render the minimal page heading', () => {
    render(<MinimalPage />)
    expect(screen.getByText('layout.minimal.pageTitle')).toBeInTheDocument()
  })
})

describe('MinimalLayout', () => {
  it('should render children', () => {
    render(
      <MinimalLayout>
        <div data-testid="child">Hello</div>
      </MinimalLayout>,
    )
    expect(screen.getByTestId('child')).toBeInTheDocument()
  })
})

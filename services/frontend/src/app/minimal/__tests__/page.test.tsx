/**
 * Tests for the minimal page and layout
 */

import React from 'react'
import { render, screen } from '@testing-library/react'
import MinimalPage from '../page'
import MinimalLayout from '../layout'

describe('MinimalPage', () => {
  it('should render the minimal page heading', () => {
    render(<MinimalPage />)
    expect(screen.getByText('Minimal Page')).toBeInTheDocument()
  })
})

describe('MinimalLayout', () => {
  it('should render children', () => {
    render(
      <MinimalLayout>
        <div data-testid="child">Hello</div>
      </MinimalLayout>
    )
    expect(screen.getByTestId('child')).toBeInTheDocument()
  })
})

/**
 * @jest-environment jsdom
 */

import { describe, expect, it } from '@jest/globals'
import '@testing-library/jest-dom'
import { render, screen } from '@testing-library/react'

// Simple test component
const TestComponent = () => {
  return (
    <div>
      <h1>BenGER Frontend</h1>
      <p>Testing setup works!</p>
    </div>
  )
}

describe('Frontend Test Setup', () => {
  it('should render test component correctly', () => {
    render(<TestComponent />)

    expect(screen.getByText('BenGER Frontend')).toBeTruthy()
    expect(screen.getByText('Testing setup works!')).toBeTruthy()
  })

  it('should handle basic functionality', () => {
    const mockFn = jest.fn()
    mockFn('test')

    expect(mockFn).toHaveBeenCalledWith('test')
    expect(mockFn).toHaveBeenCalledTimes(1)
  })
})

// Test API utilities
describe('API Configuration', () => {
  it('should have correct environment variables', () => {
    expect(process.env.NEXT_PUBLIC_API_URL).toBe('http://localhost:8001')
  })
})

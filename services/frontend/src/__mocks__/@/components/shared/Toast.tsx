/**
 * Mock implementation of Toast components and hooks
 * Issue #360: Fix frontend test mock issues
 */

import React from 'react'

// Mock ToastProvider component
export function ToastProvider({ children }: { children: React.ReactNode }) {
  return <div data-testid="toast-provider">{children}</div>
}

// Create a jest mock function that supports both auto-mocking and manual mocking
const mockUseToast = jest.fn(() => ({
  addToast: jest.fn(),
  removeToast: jest.fn(),
}))

// Export as useToast - this allows tests to call mockReturnValue on it
export const useToast = mockUseToast

// Additional exports that might be used
export default ToastProvider

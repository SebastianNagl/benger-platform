import { AuthProvider } from '@/contexts/AuthContext'
import { I18nProvider } from '@/contexts/I18nContext'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, RenderOptions } from '@testing-library/react'
import React from 'react'

const AllProviders = ({ children }: { children: React.ReactNode }) => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        staleTime: 0,
        gcTime: 0,
      },
      mutations: {
        retry: false,
      },
    },
  })

  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <I18nProvider>{children}</I18nProvider>
      </AuthProvider>
    </QueryClientProvider>
  )
}

export const renderWithProviders = (
  ui: React.ReactElement,
  options?: RenderOptions
) => render(ui, { wrapper: AllProviders, ...options })

// Mock implementations for common contexts
export const mockAuthContext = {
  user: {
    id: 'test-user-id',
    username: 'testuser',
    email: 'test@example.com',
    name: 'Test User',
    is_superadmin: false,
    is_active: true,
    organizations: [],
  },
  login: jest.fn(),
  logout: jest.fn(),
  signup: jest.fn(),
  updateUser: jest.fn(),
  isLoading: false,
  refreshAuth: jest.fn(),
  apiClient: null,
}

export const mockI18nContext = {
  t: (key: string) => key,
  locale: 'en',
  changeLanguage: jest.fn(),
  languages: ['en', 'de'],
}

// Helper to create test task data
export const createTestTaskData = (overrides = {}) => ({
  id: 'task-1',
  question: 'Test Question',
  reference_answers: ['Test Answer'],
  context: 'Test Context',
  ...overrides,
})

// Helper to create test annotation
export const createTestAnnotation = (overrides = {}) => ({
  id: 'annotation-1',
  task_id: 'task-1',
  user_id: 'user-1',
  value: 'Test annotation value',
  created_at: new Date().toISOString(),
  ...overrides,
})

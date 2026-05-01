/**
 * @jest-environment jsdom
 */

import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { api } from '@/lib/api'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { mockToast as __mockToast } from '@/test-utils/setupTests'
const toast = Object.assign(__mockToast.addToast, {
  success: __mockToast.success,
  error: __mockToast.error,
  loading: jest.fn(),
  dismiss: jest.fn(),
})
import TestNotificationsPage from '../page'

jest.mock('@/contexts/AuthContext')
jest.mock('@/contexts/I18nContext')
jest.mock('@/lib/api')
// Toast mocking handled by setupTests.

const mockApiNotifications = {
  createTestNotification: jest.fn(),
  generateTestNotifications: jest.fn(),
}

const mockApi = {
  markAllNotificationsAsRead: jest.fn(),
}

describe('TestNotificationsPage', () => {
  const mockT = (key: string, params?: Record<string, any>) => {
    if (params) {
      return Object.entries(params).reduce(
        (str, [k, v]) => str.replace(`{${k}}`, String(v)),
        key
      )
    }
    return key
  }

  beforeEach(() => {
    jest.clearAllMocks()

    const mockUseAuth = useAuth as jest.MockedFunction<typeof useAuth>
    mockUseAuth.mockReturnValue({
      user: {
        id: '1',
        username: 'admin',
        email: 'admin@example.com',
        name: 'Admin User',
        is_superadmin: true,
        is_active: true,
        created_at: '2024-01-01T00:00:00Z',
      } as any,
      login: jest.fn(),
      signup: jest.fn(),
      logout: jest.fn(),
      updateUser: jest.fn(),
      isLoading: false,
      refreshAuth: jest.fn(),
      apiClient: {} as any,
      organizations: [],
      currentOrganization: null,
      setCurrentOrganization: jest.fn(),
      refreshOrganizations: jest.fn(),
    })

    const mockUseI18n = useI18n as jest.MockedFunction<typeof useI18n>
    mockUseI18n.mockReturnValue({
      locale: 'en',
      t: mockT,
      changeLocale: jest.fn(),
    })
    ;(api as any).notifications = mockApiNotifications
    ;(api as any).markAllNotificationsAsRead =
      mockApi.markAllNotificationsAsRead

    mockApiNotifications.createTestNotification.mockResolvedValue({})
    mockApiNotifications.generateTestNotifications.mockResolvedValue({
      count: 9,
      message: 'Generated 9 test notifications!',
    })
    mockApi.markAllNotificationsAsRead.mockResolvedValue({})
  })

  describe('Access Control', () => {
    it('should display access denied for non-superadmin users', () => {
      const mockUseAuth = useAuth as jest.MockedFunction<typeof useAuth>
      mockUseAuth.mockReturnValue({
        user: {
          id: '2',
          username: 'regular',
          email: 'user@example.com',
          name: 'Regular User',
          is_superadmin: false,
          is_active: true,
          created_at: '2024-01-01T00:00:00Z',
        } as any,
        login: jest.fn(),
        signup: jest.fn(),
        logout: jest.fn(),
        updateUser: jest.fn(),
        isLoading: false,
        refreshAuth: jest.fn(),
        apiClient: {} as any,
        organizations: [],
        currentOrganization: null,
        setCurrentOrganization: jest.fn(),
        refreshOrganizations: jest.fn(),
      })

      render(<TestNotificationsPage />)

      expect(screen.getByText('admin.accessDenied')).toBeInTheDocument()
      expect(screen.getByText('admin.accessDeniedDesc')).toBeInTheDocument()
    })

    it('should display page content for superadmin users', () => {
      render(<TestNotificationsPage />)

      expect(
        screen.getByText('admin.testNotifications.title')
      ).toBeInTheDocument()
      expect(
        screen.getByText('admin.testNotifications.description')
      ).toBeInTheDocument()
    })
  })

  describe('Notification Types Display', () => {
    it('should display all notification types grouped by category', () => {
      render(<TestNotificationsPage />)

      // Category headers use t('admin.testNotifications.categoryHeader', { category })
      // With mockT, this returns the key with {category} replaced by the category key value
      const categoryHeaders = screen.getAllByText('admin.testNotifications.categoryHeader')
      expect(categoryHeaders.length).toBeGreaterThan(0)
    })

    it('should display project notification types', () => {
      render(<TestNotificationsPage />)

      expect(screen.getByText('admin.testNotifications.types.projectCreated.title')).toBeInTheDocument()
      expect(screen.getByText('admin.testNotifications.types.projectCompleted.title')).toBeInTheDocument()
    })

    it('should display generation notification types', () => {
      render(<TestNotificationsPage />)

      expect(screen.getByText('admin.testNotifications.types.generationCompleted.title')).toBeInTheDocument()
    })

    it('should display evaluation notification types', () => {
      render(<TestNotificationsPage />)

      expect(screen.getByText('admin.testNotifications.types.evaluationCompleted.title')).toBeInTheDocument()
      expect(screen.getByText('admin.testNotifications.types.evaluationFailed.title')).toBeInTheDocument()
    })

    it('should display annotation notification types', () => {
      render(<TestNotificationsPage />)

      expect(screen.getByText('admin.testNotifications.types.annotationCompleted.title')).toBeInTheDocument()
    })

    it('should display organization notification types', () => {
      render(<TestNotificationsPage />)

      expect(screen.getByText('admin.testNotifications.types.memberJoined.title')).toBeInTheDocument()
    })

    it('should display system notification types', () => {
      render(<TestNotificationsPage />)

      expect(screen.getByText('admin.testNotifications.types.systemAlert.title')).toBeInTheDocument()
      expect(screen.getByText('admin.testNotifications.types.errorOccurred.title')).toBeInTheDocument()
    })

    it('should display generate button for each notification type', () => {
      render(<TestNotificationsPage />)

      const generateButtons = screen.getAllByText('admin.testNotifications.generate')
      expect(generateButtons.length).toBe(9)
    })
  })

  describe('Individual Notification Generation', () => {
    it('should generate a single test notification when Generate is clicked', async () => {
      const user = userEvent.setup()
      render(<TestNotificationsPage />)

      const generateButtons = screen.getAllByText('admin.testNotifications.generate')
      await user.click(generateButtons[0])

      await waitFor(() => {
        expect(
          mockApiNotifications.createTestNotification
        ).toHaveBeenCalledWith({
          type: 'project_created',
          title: 'admin.testNotifications.types.projectCreated.title',
          message: 'admin.testNotifications.types.projectCreated.message',
          data: expect.objectContaining({
            test: true,
            category: 'admin.testNotifications.types.projectCreated.category',
          }),
        })
      })
    })

    it('should show success toast on successful notification generation', async () => {
      const user = userEvent.setup()
      render(<TestNotificationsPage />)

      const generateButtons = screen.getAllByText('admin.testNotifications.generate')
      await user.click(generateButtons[0])

      await waitFor(() => {
        expect(toast.success).toHaveBeenCalledWith(
          'admin.testNotifications.sent'
        )
      })
    })

    it('should show error toast on failed notification generation', async () => {
      // Suppress expected console.error from error handling path
      const consoleSpy = jest.spyOn(console, 'error').mockImplementation(() => {})

      mockApiNotifications.createTestNotification.mockRejectedValue(
        new Error('API Error')
      )

      const user = userEvent.setup()
      render(<TestNotificationsPage />)

      const generateButtons = screen.getAllByText('admin.testNotifications.generate')
      await user.click(generateButtons[0])

      await waitFor(() => {
        expect(toast.error).toHaveBeenCalledWith(
          'admin.testNotifications.sendFailed'
        )
      })

      consoleSpy.mockRestore()
    })

    it('should disable buttons while generating', async () => {
      mockApiNotifications.createTestNotification.mockImplementation(
        () => new Promise((resolve) => setTimeout(resolve, 100))
      )

      const user = userEvent.setup()
      render(<TestNotificationsPage />)

      const generateButtons = screen.getAllByText('admin.testNotifications.generate')
      await user.click(generateButtons[0])

      await waitFor(() => {
        expect(screen.getByText('admin.testNotifications.generating')).toBeInTheDocument()
      })

      generateButtons.slice(1).forEach((button) => {
        expect(button).toBeDisabled()
      })
    })

    it('should generate different notification types', async () => {
      const user = userEvent.setup()
      render(<TestNotificationsPage />)

      const generateButtons = screen.getAllByText('admin.testNotifications.generate')

      await user.click(generateButtons[2])

      await waitFor(() => {
        expect(
          mockApiNotifications.createTestNotification
        ).toHaveBeenCalledWith(
          expect.objectContaining({
            type: 'llm_generation_completed',
          })
        )
      })
    })
  })

  describe('Bulk Actions', () => {
    it('should display bulk actions section', () => {
      render(<TestNotificationsPage />)

      expect(screen.getByText('admin.testNotifications.bulkActions')).toBeInTheDocument()
      expect(screen.getByText('admin.testNotifications.generateAll')).toBeInTheDocument()
      expect(screen.getByText('admin.testNotifications.clearAll')).toBeInTheDocument()
    })

    it('should generate all notification types with bulk endpoint', async () => {
      const user = userEvent.setup()
      render(<TestNotificationsPage />)

      const generateAllButton = screen.getByText('admin.testNotifications.generateAll')
      await user.click(generateAllButton)

      await waitFor(() => {
        expect(
          mockApiNotifications.generateTestNotifications
        ).toHaveBeenCalled()
      })
    })

    it('should show success toast with count after bulk generation', async () => {
      const user = userEvent.setup()
      render(<TestNotificationsPage />)

      const generateAllButton = screen.getByText('admin.testNotifications.generateAll')
      await user.click(generateAllButton)

      await waitFor(() => {
        expect(toast.success).toHaveBeenCalledWith(
          'Generated 9 test notifications!'
        )
      })
    })

    it('should fallback to individual calls if bulk endpoint fails', async () => {
      mockApiNotifications.generateTestNotifications.mockRejectedValue(
        new Error('Bulk endpoint not available')
      )

      const user = userEvent.setup()
      render(<TestNotificationsPage />)

      const generateAllButton = screen.getByText('admin.testNotifications.generateAll')
      await user.click(generateAllButton)

      await waitFor(() => {
        expect(mockApiNotifications.createTestNotification).toHaveBeenCalled()
      })
    })

    it('should show success toast after fallback generation', async () => {
      mockApiNotifications.generateTestNotifications.mockRejectedValue(
        new Error('Bulk endpoint not available')
      )

      const user = userEvent.setup()
      render(<TestNotificationsPage />)

      const generateAllButton = screen.getByText('admin.testNotifications.generateAll')
      await user.click(generateAllButton)

      // Fallback loop iterates per notification type with delays
      await waitFor(
        () => {
          expect(toast.success).toHaveBeenCalledWith(
            'admin.testNotifications.sent'
          )
        },
        { timeout: 5000 }
      )
    })

    it('should handle fallback failure gracefully', async () => {
      mockApiNotifications.generateTestNotifications.mockRejectedValue(
        new Error('Bulk error')
      )
      mockApiNotifications.createTestNotification.mockRejectedValue(
        new Error('Individual error')
      )

      const user = userEvent.setup()
      render(<TestNotificationsPage />)

      const generateAllButton = screen.getByText('admin.testNotifications.generateAll')
      await user.click(generateAllButton)

      await waitFor(() => {
        expect(toast.error).toHaveBeenCalledWith(
          'admin.testNotifications.sendFailed'
        )
      })
    })

    it('should disable buttons during bulk generation', async () => {
      mockApiNotifications.generateTestNotifications.mockImplementation(
        () => new Promise((resolve) => setTimeout(resolve, 100))
      )

      const user = userEvent.setup()
      render(<TestNotificationsPage />)

      const generateAllButton = screen.getByText('admin.testNotifications.generateAll')
      await user.click(generateAllButton)

      await waitFor(() => {
        expect(screen.getByText('admin.testNotifications.generating')).toBeInTheDocument()
      })

      const clearButton = screen.getByText('admin.testNotifications.clearAll')
      expect(clearButton).toBeDisabled()
    })
  })

  describe('Clear All Notifications', () => {
    it('should show confirmation dialog before clearing', async () => {
      window.confirm = jest.fn(() => false)

      const user = userEvent.setup()
      render(<TestNotificationsPage />)

      const clearButton = screen.getByText('admin.testNotifications.clearAll')
      await user.click(clearButton)

      expect(window.confirm).toHaveBeenCalledWith(
        'admin.testNotifications.clearConfirm'
      )
      expect(mockApi.markAllNotificationsAsRead).not.toHaveBeenCalled()
    })

    it('should clear notifications when confirmed', async () => {
      window.confirm = jest.fn(() => true)

      const user = userEvent.setup()
      render(<TestNotificationsPage />)

      const clearButton = screen.getByText('admin.testNotifications.clearAll')
      await user.click(clearButton)

      await waitFor(() => {
        expect(mockApi.markAllNotificationsAsRead).toHaveBeenCalled()
      })
    })

    it('should show success toast after clearing', async () => {
      window.confirm = jest.fn(() => true)

      const user = userEvent.setup()
      render(<TestNotificationsPage />)

      const clearButton = screen.getByText('admin.testNotifications.clearAll')
      await user.click(clearButton)

      await waitFor(() => {
        expect(toast.success).toHaveBeenCalledWith(
          'admin.testNotifications.cleared'
        )
      })
    })

    it('should handle clear failure', async () => {
      window.confirm = jest.fn(() => true)
      mockApi.markAllNotificationsAsRead.mockRejectedValue(
        new Error('Clear failed')
      )

      const user = userEvent.setup()
      render(<TestNotificationsPage />)

      const clearButton = screen.getByText('admin.testNotifications.clearAll')
      await user.click(clearButton)

      await waitFor(() => {
        expect(toast.error).toHaveBeenCalledWith(
          'admin.testNotifications.clearFailed'
        )
      })
    })

    it('should disable buttons during clear operation', async () => {
      window.confirm = jest.fn(() => true)
      mockApi.markAllNotificationsAsRead.mockImplementation(
        () => new Promise((resolve) => setTimeout(resolve, 100))
      )

      const user = userEvent.setup()
      render(<TestNotificationsPage />)

      const clearButton = screen.getByText('admin.testNotifications.clearAll')
      await user.click(clearButton)

      await waitFor(() => {
        expect(screen.getByText('admin.testNotifications.clearing')).toBeInTheDocument()
      })

      const generateAllButton = screen.getByText('admin.testNotifications.generateAll')
      expect(generateAllButton).toBeDisabled()
    })
  })

  describe('Implementation Status Section', () => {
    it('should display implementation status', () => {
      render(<TestNotificationsPage />)

      expect(screen.getByText('admin.testNotifications.status.title')).toBeInTheDocument()
    })

    it('should show completed frontend tasks', () => {
      render(<TestNotificationsPage />)

      expect(
        screen.getByText('admin.testNotifications.status.item1')
      ).toBeInTheDocument()
      expect(
        screen.getByText('admin.testNotifications.status.item2')
      ).toBeInTheDocument()
      expect(
        screen.getByText('admin.testNotifications.status.item3')
      ).toBeInTheDocument()
    })

    it('should show pending backend tasks info', () => {
      render(<TestNotificationsPage />)

      expect(
        screen.getByText('admin.testNotifications.status.item6')
      ).toBeInTheDocument()
      expect(
        screen.getByText('admin.testNotifications.status.note')
      ).toBeInTheDocument()
    })
  })

  describe('Breadcrumb Navigation', () => {
    it('should display breadcrumb navigation', () => {
      render(<TestNotificationsPage />)

      // Dashboard renders as HomeIcon, not text
      expect(screen.getByText('admin.testNotifications.breadcrumb')).toBeInTheDocument()
    })
  })

  describe('Notification Type Details', () => {
    it('should display notification descriptions', () => {
      render(<TestNotificationsPage />)

      expect(
        screen.getByText('admin.testNotifications.types.projectCreated.description')
      ).toBeInTheDocument()
      expect(
        screen.getByText('admin.testNotifications.types.projectCompleted.description')
      ).toBeInTheDocument()
    })

    it('should display notification messages', () => {
      render(<TestNotificationsPage />)

      expect(
        screen.getByText('admin.testNotifications.types.projectCreated.message')
      ).toBeInTheDocument()
      expect(
        screen.getByText('admin.testNotifications.types.projectCompleted.message')
      ).toBeInTheDocument()
    })

    it('should display appropriate icons for each notification type', () => {
      render(<TestNotificationsPage />)

      const notificationCards = screen.getAllByRole('generic', {
        hidden: true,
      })

      expect(notificationCards.length).toBeGreaterThan(0)
    })

    it('should apply correct color classes for different notification types', () => {
      const { container } = render(<TestNotificationsPage />)

      expect(container.querySelector('.text-blue-600')).toBeInTheDocument()
      expect(container.querySelector('.text-green-600')).toBeInTheDocument()
      expect(container.querySelector('.text-red-600')).toBeInTheDocument()
    })
  })

  describe('Loading States', () => {
    it('should show individual loading state for specific notification', async () => {
      mockApiNotifications.createTestNotification.mockImplementation(
        () => new Promise((resolve) => setTimeout(resolve, 100))
      )

      const user = userEvent.setup()
      render(<TestNotificationsPage />)

      const generateButtons = screen.getAllByText('admin.testNotifications.generate')
      await user.click(generateButtons[0])

      await waitFor(() => {
        expect(screen.getByText('admin.testNotifications.generating')).toBeInTheDocument()
      })

      const otherButtons = generateButtons.slice(1)
      otherButtons.forEach((button) => {
        expect(button).toBeDisabled()
      })
    })

    it('should restore buttons after generation completes', async () => {
      const user = userEvent.setup()
      render(<TestNotificationsPage />)

      const generateButtons = screen.getAllByText('admin.testNotifications.generate')
      await user.click(generateButtons[0])

      await waitFor(() => {
        expect(toast.success).toHaveBeenCalled()
      })

      generateButtons.forEach((button) => {
        expect(button).not.toBeDisabled()
      })
    })
  })

  describe('Error Handling', () => {
    it('should log errors to console on failure', async () => {
      const consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation()
      mockApiNotifications.createTestNotification.mockRejectedValue(
        new Error('Test error')
      )

      const user = userEvent.setup()
      render(<TestNotificationsPage />)

      const generateButtons = screen.getAllByText('admin.testNotifications.generate')
      await user.click(generateButtons[0])

      await waitFor(() => {
        expect(consoleErrorSpy).toHaveBeenCalledWith(
          'Failed to generate test notification:',
          expect.any(Error)
        )
      }, { timeout: 5000 })

      consoleErrorSpy.mockRestore()
    })

    it('should handle network errors gracefully', async () => {
      mockApiNotifications.createTestNotification.mockRejectedValue(
        new Error('Network error')
      )

      const user = userEvent.setup()
      render(<TestNotificationsPage />)

      const generateButtons = screen.getAllByText('admin.testNotifications.generate')
      await user.click(generateButtons[0])

      await waitFor(() => {
        expect(toast.error).toHaveBeenCalledWith(
          'admin.testNotifications.sendFailed'
        )
      }, { timeout: 5000 })
    })

    it('should continue working after an error', async () => {
      mockApiNotifications.createTestNotification
        .mockRejectedValueOnce(new Error('First error'))

      const user = userEvent.setup()
      render(<TestNotificationsPage />)

      const generateButtons = screen.getAllByText('admin.testNotifications.generate')

      await user.click(generateButtons[0])
      await waitFor(() => {
        expect(toast.error).toHaveBeenCalledWith(
          'admin.testNotifications.sendFailed'
        )
      }, { timeout: 5000 })

      await user.click(generateButtons[1])
      await waitFor(() => {
        expect(toast.success).toHaveBeenCalledWith(
          'admin.testNotifications.sent'
        )
      }, { timeout: 5000 })
    })
  })
})

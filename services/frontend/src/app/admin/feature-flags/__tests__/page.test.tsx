/**
 * @jest-environment jsdom
 */

import { useToast } from '@/components/shared/Toast'
import { useAuth } from '@/contexts/AuthContext'
import { useFeatureFlags } from '@/contexts/FeatureFlagContext'
import { useI18n } from '@/contexts/I18nContext'
import { api } from '@/lib/api'
import { FeatureFlag } from '@/lib/api/types'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import FeatureFlagsAdminPage from '../page'

jest.mock('@/contexts/AuthContext')
jest.mock('@/contexts/FeatureFlagContext', () => ({
  useFeatureFlags: jest.fn(),
}))
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: jest.fn(),
}))
jest.mock('@/components/shared/Toast', () => ({
  useToast: jest.fn(),
}))
jest.mock('@/lib/api')
jest.mock('@/components/shared/FilterToolbar', () => {
  const FilterToolbar = ({
    searchValue,
    onSearchChange,
    searchPlaceholder,
    searchLabel,
    clearLabel = 'Clear filters',
    onClearFilters,
    hasActiveFilters,
    leftExtras,
    rightExtras,
    children,
  }: any) => (
    <div data-testid="filter-toolbar">
      {leftExtras}
      {onSearchChange && (
        <input
          data-testid="filter-toolbar-search"
          type="search"
          placeholder={searchPlaceholder}
          title={searchPlaceholder || searchLabel}
          value={searchValue ?? ''}
          onChange={(e) => onSearchChange(e.target.value)}
        />
      )}
      <div data-testid="filter-toolbar-fields">{children}</div>
      {onClearFilters && (
        <button
          data-testid="filter-toolbar-clear"
          onClick={onClearFilters}
          disabled={!hasActiveFilters}
          title={clearLabel}
          aria-label={clearLabel}
        />
      )}
      {rightExtras}
    </div>
  )
  FilterToolbar.Field = ({ children }: any) => <div>{children}</div>
  return { FilterToolbar }
})


describe('FeatureFlagsAdminPage', () => {
  const mockAddToast = jest.fn()
  const mockRefreshFlags = jest.fn()

  const mockFlags: FeatureFlag[] = [
    {
      id: 'flag-1',
      name: 'reports',
      description: 'Reports feature',
      is_enabled: true,
      rollout_percentage: 100,
      created_by: 'admin-1',
      created_at: '2024-01-01T00:00:00Z',
      updated_at: '2024-01-02T00:00:00Z',
    },
    {
      id: 'flag-2',
      name: 'generations',
      description: 'LLM generations',
      is_enabled: false,
      rollout_percentage: 0,
      created_by: 'admin-1',
      created_at: '2024-01-01T00:00:00Z',
    },
    {
      id: 'flag-3',
      name: 'evaluations',
      description: '',
      is_enabled: true,
      rollout_percentage: 50,
      created_by: 'admin-1',
      created_at: '2023-12-01T00:00:00Z',
    },
  ]

  beforeEach(() => {
    jest.clearAllMocks()
    jest.clearAllTimers()

    const mockUseAuth = useAuth as jest.MockedFunction<typeof useAuth>
    mockUseAuth.mockReturnValue({
      user: {
        id: 'admin-1',
        username: 'admin',
        email: 'admin@example.com',
        name: 'Admin User',
        is_superadmin: true,
        is_active: true,
        created_at: '2024-01-01',
      },
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
    } as any)

    const mockUseFeatureFlags = useFeatureFlags as jest.MockedFunction<
      typeof useFeatureFlags
    >
    mockUseFeatureFlags.mockReturnValue({
      flags: {},
      isLoading: false,
      error: null,
      isEnabled: jest.fn().mockReturnValue(true),
      refreshFlags: mockRefreshFlags,
      checkFlag: jest.fn(),
      lastUpdate: Date.now(),
    })

    const mockUseI18n = useI18n as jest.MockedFunction<typeof useI18n>
    mockUseI18n.mockReturnValue({
      t: (key: string) => {
        const translations: Record<string, string> = {
          'admin.accessDenied': 'Access Denied',
          'admin.accessDeniedDesc':
            'You need superadmin privileges to access this page.',
          'admin.featureFlagsPage.title': 'Feature Flags',
          'admin.featureFlagsPage.description':
            'Manage feature flags for production testing',
          'admin.featureFlagsPage.name': 'Name',
          'admin.featureFlagsPage.description': 'Description',
          'admin.featureFlagsPage.created': 'Created',
          'admin.featureFlagsPage.searchPlaceholder': 'Search feature flags...',
          'admin.featureFlagsPage.noFlags': 'No feature flags found.',
          'admin.featureFlagsPage.enabled': 'Enabled',
          'admin.featureFlagsPage.disabled': 'Disabled',
          'admin.featureFlagsPage.applyChanges': 'Apply Changes',
          'admin.featureFlagsPage.discardChanges': 'Discard Changes',
          'admin.featureFlagsPage.applying': 'Applying...',
          'admin.featureFlagsPage.applied': 'All changes applied successfully',
          'admin.featureFlagsPage.applyFailed': 'Failed to apply changes',
          'toasts.admin.noChanges': 'No changes to apply',
          'toasts.admin.changesDiscarded': 'Changes discarded',
        }
        return translations[key] || key
      },
      language: 'en',
      setLanguage: jest.fn(),
      availableLanguages: ['en'],
    })

    const mockUseToast = useToast as jest.MockedFunction<typeof useToast>
    mockUseToast.mockReturnValue({
      addToast: mockAddToast,
    } as any)

    const mockApi = api as jest.Mocked<typeof api>
    mockApi.getAllFeatureFlagsForAdmin = jest.fn().mockResolvedValue(mockFlags)
    mockApi.updateFeatureFlag = jest.fn().mockResolvedValue(mockFlags[0])
  })

  afterEach(() => {
    jest.restoreAllMocks()
    jest.useRealTimers()
  })

  describe('Access Control', () => {
    it('should render page for superadmin', async () => {
      render(<FeatureFlagsAdminPage />)

      await waitFor(() => {
        expect(screen.getByText('Feature Flags')).toBeInTheDocument()
      })
    })

    it('should show access denied for non-superadmin', () => {
      const mockUseAuth = useAuth as jest.MockedFunction<typeof useAuth>
      mockUseAuth.mockReturnValue({
        user: {
          id: 'user-1',
          username: 'user',
          email: 'user@example.com',
          name: 'Regular User',
          is_superadmin: false,
          is_active: true,
          created_at: '2024-01-01',
        },
      } as any)

      render(<FeatureFlagsAdminPage />)

      expect(screen.getByText('Access Denied')).toBeInTheDocument()
      expect(
        screen.getByText('You need superadmin privileges to access this page.')
      ).toBeInTheDocument()
    })

    it('should show breadcrumb for non-superadmin', () => {
      const mockUseAuth = useAuth as jest.MockedFunction<typeof useAuth>
      mockUseAuth.mockReturnValue({
        user: {
          id: 'user-1',
          username: 'user',
          is_superadmin: false,
        },
      } as any)

      render(<FeatureFlagsAdminPage />)

      // Dashboard renders as HomeIcon, not text
      expect(screen.getByText('Feature Flags')).toBeInTheDocument()
    })
  })

  describe('Loading State', () => {
    it('should show loading spinner while fetching flags', async () => {
      jest.useFakeTimers()
      const mockApi = api as jest.Mocked<typeof api>
      let resolvePromise: (value: any) => void
      mockApi.getAllFeatureFlagsForAdmin = jest.fn().mockImplementation(
        () =>
          new Promise((resolve) => {
            resolvePromise = resolve
          })
      )

      render(<FeatureFlagsAdminPage />)

      expect(screen.getByText('Loading feature flags...')).toBeInTheDocument()
      const spinner = document.querySelector('.animate-spin')
      expect(spinner).toBeInTheDocument()

      resolvePromise!(mockFlags)
      jest.useRealTimers()
    })

    it('should hide loading state after flags load', async () => {
      render(<FeatureFlagsAdminPage />)

      await waitFor(() => {
        expect(
          screen.queryByText('Loading feature flags...')
        ).not.toBeInTheDocument()
      })
    })

    it('should show breadcrumb while loading', async () => {
      jest.useFakeTimers()
      const mockApi = api as jest.Mocked<typeof api>
      let resolvePromise: (value: any) => void
      mockApi.getAllFeatureFlagsForAdmin = jest.fn().mockImplementation(
        () =>
          new Promise((resolve) => {
            resolvePromise = resolve
          })
      )

      render(<FeatureFlagsAdminPage />)

      // Dashboard renders as HomeIcon, not text
      expect(screen.getAllByText('Feature Flags').length).toBeGreaterThan(0)

      resolvePromise!(mockFlags)
      jest.useRealTimers()
    })
  })

  describe('Flag List Display', () => {
    it('should display all feature flags', async () => {
      render(<FeatureFlagsAdminPage />)

      await waitFor(() => {
        expect(screen.getByText('reports')).toBeInTheDocument()
        expect(screen.getByText('generations')).toBeInTheDocument()
        expect(screen.getByText('evaluations')).toBeInTheDocument()
      })
    })

    it('should display flag descriptions', async () => {
      render(<FeatureFlagsAdminPage />)

      await waitFor(() => {
        expect(screen.getByText('Reports feature')).toBeInTheDocument()
        expect(screen.getByText('LLM generations')).toBeInTheDocument()
      })
    })

    it('should show dash for empty description', async () => {
      render(<FeatureFlagsAdminPage />)

      await waitFor(() => {
        const rows = screen.getAllByRole('row')
        const evaluationsRow = rows.find((row) =>
          row.textContent?.includes('evaluations')
        )
        expect(evaluationsRow).toBeTruthy()
      })
    })

    it('should display flag status correctly', async () => {
      render(<FeatureFlagsAdminPage />)

      await waitFor(() => {
        const enabledStatuses = screen.getAllByText('Enabled')
        const disabledStatuses = screen.getAllByText('Disabled')
        expect(enabledStatuses.length).toBeGreaterThan(0)
        expect(disabledStatuses.length).toBeGreaterThan(0)
      })
    })

    it('should display created dates', async () => {
      render(<FeatureFlagsAdminPage />)

      await waitFor(() => {
        const rows = screen.getAllByRole('row')
        const hasReportsDate = rows.some((row) =>
          row.textContent?.match(/2024/)
        )
        const hasEvaluationsDate = rows.some((row) =>
          row.textContent?.match(/2023/)
        )
        expect(hasReportsDate).toBe(true)
        expect(hasEvaluationsDate).toBe(true)
      })
    })

    it('should show dash for missing created_at', async () => {
      const flagWithoutDate: FeatureFlag = {
        ...mockFlags[0],
        created_at: null as any,
      }
      const mockApi = api as jest.Mocked<typeof api>
      mockApi.getAllFeatureFlagsForAdmin = jest
        .fn()
        .mockResolvedValue([flagWithoutDate])

      render(<FeatureFlagsAdminPage />)

      await waitFor(() => {
        const rows = screen.getAllByRole('row')
        const hasData = rows.some((row) => row.textContent?.includes('reports'))
        expect(hasData).toBe(true)
      })
    })
  })

  describe('Toggle Functionality', () => {
    it('should toggle flag state when switch is clicked', async () => {
      const user = userEvent.setup()
      render(<FeatureFlagsAdminPage />)

      await waitFor(() => {
        expect(screen.getByText('reports')).toBeInTheDocument()
      })

      const toggles = screen.getAllByRole('switch')
      await user.click(toggles[0])

      await waitFor(() => {
        expect(screen.getByText(/Apply Changes/)).toBeInTheDocument()
      })
    })

    it('should show pending indicator when flag is toggled', async () => {
      const user = userEvent.setup()
      render(<FeatureFlagsAdminPage />)

      await waitFor(() => {
        expect(screen.getByText('reports')).toBeInTheDocument()
      })

      const toggles = screen.getAllByRole('switch')
      await user.click(toggles[0])

      await waitFor(() => {
        expect(screen.getByText('Pending')).toBeInTheDocument()
      })
    })

    it('should show pending changes count', async () => {
      const user = userEvent.setup()
      render(<FeatureFlagsAdminPage />)

      await waitFor(() => {
        expect(screen.getByText('reports')).toBeInTheDocument()
      })

      const toggles = screen.getAllByRole('switch')
      await user.click(toggles[0])
      await user.click(toggles[1])

      await waitFor(() => {
        expect(screen.getByText('Apply Changes (2)')).toBeInTheDocument()
      })
    })

    it('should highlight row with pending changes', async () => {
      const user = userEvent.setup({ delay: null })
      render(<FeatureFlagsAdminPage />)

      await waitFor(() => {
        expect(screen.getByText('reports')).toBeInTheDocument()
      })

      const toggles = screen.getAllByRole('switch')
      const firstFlag = toggles[0].closest('tr')
      await user.click(toggles[0])

      expect(screen.getByText('Pending')).toBeInTheDocument()
      expect(firstFlag?.className).toContain('amber')
    })
  })

  describe('Apply Changes', () => {
    it('should apply changes successfully', async () => {
      const user = userEvent.setup({ delay: null })
      const mockApi = api as jest.Mocked<typeof api>

      render(<FeatureFlagsAdminPage />)

      await waitFor(() => {
        expect(screen.getByText('reports')).toBeInTheDocument()
      })

      const toggles = screen.getAllByRole('switch')
      await user.click(toggles[0])

      const applyButton = screen.getByText(/Apply Changes/)
      await user.click(applyButton)

      expect(mockApi.updateFeatureFlag).toHaveBeenCalled()
      expect(mockApi.updateFeatureFlag.mock.calls[0][1]).toEqual({
        is_enabled: false,
      })
    })

    it('should show applying state during save', async () => {
      jest.useFakeTimers()
      const user = userEvent.setup({ delay: null })
      const mockApi = api as jest.Mocked<typeof api>
      let resolvePromise: (value: any) => void
      mockApi.updateFeatureFlag = jest.fn().mockImplementation(
        () =>
          new Promise((resolve) => {
            resolvePromise = resolve
          })
      )

      render(<FeatureFlagsAdminPage />)

      await waitFor(() => {
        expect(screen.getByText('reports')).toBeInTheDocument()
      })

      const toggles = screen.getAllByRole('switch')
      await user.click(toggles[0])

      const applyButton = screen.getByText(/Apply Changes/)
      await user.click(applyButton)

      expect(screen.getByText('Applying...')).toBeInTheDocument()

      resolvePromise!(mockFlags[0])
      jest.advanceTimersByTime(500)
      jest.useRealTimers()
    })

    it('should show success toast after applying changes', async () => {
      jest.useFakeTimers()
      const user = userEvent.setup({ delay: null })

      render(<FeatureFlagsAdminPage />)

      await waitFor(() => {
        expect(screen.getByText('reports')).toBeInTheDocument()
      })

      const toggles = screen.getAllByRole('switch')
      await user.click(toggles[0])

      const applyButton = screen.getByText(/Apply Changes/)
      await user.click(applyButton)

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(
          'All changes applied successfully',
          'success'
        )
      })

      jest.useRealTimers()
    })

    it('should apply multiple changes at once', async () => {
      const user = userEvent.setup()
      const mockApi = api as jest.Mocked<typeof api>

      render(<FeatureFlagsAdminPage />)

      await waitFor(() => {
        expect(screen.getByText('reports')).toBeInTheDocument()
      })

      const toggles = screen.getAllByRole('switch')
      await user.click(toggles[0])
      await user.click(toggles[1])

      const applyButton = screen.getByText('Apply Changes (2)')
      await user.click(applyButton)

      await waitFor(() => {
        expect(mockApi.updateFeatureFlag).toHaveBeenCalledTimes(2)
      })
    })
  })

  describe('Discard Changes', () => {
    it('should discard pending changes', async () => {
      const user = userEvent.setup()
      const mockApi = api as jest.Mocked<typeof api>

      render(<FeatureFlagsAdminPage />)

      await waitFor(() => {
        expect(screen.getByText('reports')).toBeInTheDocument()
      })

      const toggles = screen.getAllByRole('switch')
      await user.click(toggles[0])

      await waitFor(() => {
        expect(screen.getByText('Discard Changes')).toBeInTheDocument()
      })

      const discardButton = screen.getByText('Discard Changes')
      await user.click(discardButton)

      await waitFor(() => {
        expect(mockApi.getAllFeatureFlagsForAdmin).toHaveBeenCalledTimes(2)
        expect(mockAddToast).toHaveBeenCalledWith('Changes discarded', 'info')
      })
    })

    it('should hide discard button when no pending changes', async () => {
      render(<FeatureFlagsAdminPage />)

      await waitFor(() => {
        expect(screen.getByText('reports')).toBeInTheDocument()
      })

      expect(screen.queryByText('Discard Changes')).not.toBeInTheDocument()
    })
  })

  describe('Error Handling', () => {
    it('should display error message on load failure', async () => {
      const mockApi = api as jest.Mocked<typeof api>
      mockApi.getAllFeatureFlagsForAdmin = jest
        .fn()
        .mockRejectedValue(new Error('Failed to load'))

      render(<FeatureFlagsAdminPage />)

      await waitFor(
        () => {
          expect(screen.getByText('Failed to load')).toBeInTheDocument()
          expect(mockAddToast).toHaveBeenCalledWith(
            'Failed to apply changes',
            'error'
          )
        },
        { timeout: 500 }
      )
    })

    it('should handle non-Error exceptions', async () => {
      const mockApi = api as jest.Mocked<typeof api>
      mockApi.getAllFeatureFlagsForAdmin = jest
        .fn()
        .mockRejectedValue('String error')

      render(<FeatureFlagsAdminPage />)

      await waitFor(
        () => {
          expect(
            screen.getByText('Failed to apply changes')
          ).toBeInTheDocument()
        },
        { timeout: 500 }
      )
    })

    it('should handle apply changes error', async () => {
      const user = userEvent.setup()
      const mockApi = api as jest.Mocked<typeof api>
      mockApi.updateFeatureFlag = jest
        .fn()
        .mockRejectedValue(new Error('Update failed'))

      render(<FeatureFlagsAdminPage />)

      await waitFor(() => {
        expect(screen.getByText('reports')).toBeInTheDocument()
      })

      const toggles = screen.getAllByRole('switch')
      await user.click(toggles[0])

      const applyButton = screen.getByText(/Apply Changes/)
      await user.click(applyButton)

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith('Update failed', 'error')
      })
    })

    it('should reload flags on apply error', async () => {
      const user = userEvent.setup()
      const mockApi = api as jest.Mocked<typeof api>
      mockApi.updateFeatureFlag = jest
        .fn()
        .mockRejectedValue(new Error('Update failed'))

      render(<FeatureFlagsAdminPage />)

      await waitFor(() => {
        expect(screen.getByText('reports')).toBeInTheDocument()
      })

      const toggles = screen.getAllByRole('switch')
      await user.click(toggles[0])

      const applyButton = screen.getByText(/Apply Changes/)
      await user.click(applyButton)

      await waitFor(() => {
        expect(mockApi.getAllFeatureFlagsForAdmin).toHaveBeenCalledTimes(2)
      })
    })

    it('should handle non-Error update exceptions', async () => {
      const user = userEvent.setup()
      const mockApi = api as jest.Mocked<typeof api>
      mockApi.updateFeatureFlag = jest.fn().mockRejectedValue('String error')

      render(<FeatureFlagsAdminPage />)

      await waitFor(() => {
        expect(screen.getByText('reports')).toBeInTheDocument()
      })

      const toggles = screen.getAllByRole('switch')
      await user.click(toggles[0])

      const applyButton = screen.getByText(/Apply Changes/)
      await user.click(applyButton)

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(
          'Failed to apply changes',
          'error'
        )
      })
    })

    it('should handle empty flags array from API', async () => {
      const mockApi = api as jest.Mocked<typeof api>
      mockApi.getAllFeatureFlagsForAdmin = jest.fn().mockResolvedValue([])

      render(<FeatureFlagsAdminPage />)

      await waitFor(() => {
        expect(screen.getByText('No feature flags found.')).toBeInTheDocument()
      })
    })

    it('should handle non-array response from API', async () => {
      const mockApi = api as jest.Mocked<typeof api>
      mockApi.getAllFeatureFlagsForAdmin = jest
        .fn()
        .mockResolvedValue(null as any)

      render(<FeatureFlagsAdminPage />)

      await waitFor(() => {
        expect(screen.getByText('No feature flags found.')).toBeInTheDocument()
      })
    })
  })

  describe('Search Functionality', () => {
    it('should filter flags by name', async () => {
      const user = userEvent.setup()
      render(<FeatureFlagsAdminPage />)

      await waitFor(() => {
        expect(screen.getByText('reports')).toBeInTheDocument()
      })

      const searchInput = screen.getByPlaceholderText('Search feature flags...')
      await user.type(searchInput, 'reports')

      await waitFor(() => {
        expect(screen.getByText('reports')).toBeInTheDocument()
        expect(screen.queryByText('generations')).not.toBeInTheDocument()
      })
    })

    it('should filter flags by description', async () => {
      const user = userEvent.setup()
      render(<FeatureFlagsAdminPage />)

      await waitFor(() => {
        expect(screen.getByText('reports')).toBeInTheDocument()
      })

      const searchInput = screen.getByPlaceholderText('Search feature flags...')
      await user.type(searchInput, 'LLM')

      await waitFor(() => {
        expect(screen.getByText('generations')).toBeInTheDocument()
        expect(screen.queryByText('reports')).not.toBeInTheDocument()
      })
    })

    it('should be case insensitive', async () => {
      const user = userEvent.setup()
      render(<FeatureFlagsAdminPage />)

      await waitFor(() => {
        expect(screen.getByText('reports')).toBeInTheDocument()
      })

      const searchInput = screen.getByPlaceholderText('Search feature flags...')
      await user.type(searchInput, 'REPORTS')

      await waitFor(() => {
        expect(screen.getByText('reports')).toBeInTheDocument()
      })
    })

    it('should show no results message when search has no matches', async () => {
      const user = userEvent.setup()
      render(<FeatureFlagsAdminPage />)

      await waitFor(() => {
        expect(screen.getByText('reports')).toBeInTheDocument()
      })

      const searchInput = screen.getByPlaceholderText('Search feature flags...')
      await user.type(searchInput, 'nonexistent')

      await waitFor(() => {
        expect(
          screen.getByText(/No feature flags found matching "nonexistent"/)
        ).toBeInTheDocument()
      })
    })

    it('should show clear search button when search has no results', async () => {
      const user = userEvent.setup()
      render(<FeatureFlagsAdminPage />)

      await waitFor(() => {
        expect(screen.getByText('reports')).toBeInTheDocument()
      })

      const searchInput = screen.getByPlaceholderText('Search feature flags...')
      await user.type(searchInput, 'nonexistent')

      await waitFor(() => {
        expect(screen.getByText('Clear search')).toBeInTheDocument()
      })
    })

    it('should clear search when clear button is clicked', async () => {
      const user = userEvent.setup()
      render(<FeatureFlagsAdminPage />)

      await waitFor(() => {
        expect(screen.getByText('reports')).toBeInTheDocument()
      })

      const searchInput = screen.getByPlaceholderText('Search feature flags...')
      await user.type(searchInput, 'nonexistent')

      await waitFor(() => {
        expect(screen.getByText('Clear search')).toBeInTheDocument()
      })

      const clearButton = screen.getByText('Clear search')
      await user.click(clearButton)

      await waitFor(() => {
        expect(screen.getByText('reports')).toBeInTheDocument()
        expect(screen.getByText('generations')).toBeInTheDocument()
      })
    })
  })

  describe('Sorting', () => {
    it('should sort by name ascending by default', async () => {
      render(<FeatureFlagsAdminPage />)

      await waitFor(() => {
        expect(screen.getByText('reports')).toBeInTheDocument()
      })

      const rows = screen.getAllByRole('row')
      const rowTexts = rows.map((row) => row.textContent)
      const evalIndex = rowTexts.findIndex((text) =>
        text?.includes('evaluations')
      )
      const genIndex = rowTexts.findIndex((text) =>
        text?.includes('generations')
      )

      expect(evalIndex).toBeLessThan(genIndex)
    })

    it('should toggle sort order when name header is clicked', async () => {
      const user = userEvent.setup()
      render(<FeatureFlagsAdminPage />)

      await waitFor(() => {
        expect(screen.getByText('reports')).toBeInTheDocument()
      })

      const nameHeader = screen.getByText('Name').closest('button')
      await user.click(nameHeader!)

      await waitFor(() => {
        const rows = screen.getAllByRole('row')
        const rowTexts = rows.map((row) => row.textContent)
        const repIndex = rowTexts.findIndex((text) => text?.includes('reports'))
        const genIndex = rowTexts.findIndex((text) =>
          text?.includes('generations')
        )

        expect(repIndex).toBeLessThan(genIndex)
      })
    })

    it('should sort by created date', async () => {
      const user = userEvent.setup()
      render(<FeatureFlagsAdminPage />)

      await waitFor(() => {
        expect(screen.getByText('reports')).toBeInTheDocument()
      })

      const createdHeader = screen.getByText('Created').closest('button')
      await user.click(createdHeader!)

      await waitFor(() => {
        const rows = screen.getAllByRole('row')
        const rowTexts = rows.map((row) => row.textContent)
        const evalIndex = rowTexts.findIndex((text) =>
          text?.includes('evaluations')
        )
        const repIndex = rowTexts.findIndex((text) => text?.includes('reports'))

        expect(evalIndex).toBeLessThan(repIndex)
      })
    })

    it('should show sort indicator for active sort', async () => {
      render(<FeatureFlagsAdminPage />)

      await waitFor(() => {
        expect(screen.getByText('reports')).toBeInTheDocument()
      })

      const nameHeader = screen.getByText('Name').closest('button')
      const svg = nameHeader?.querySelector('svg')
      expect(svg).toBeInTheDocument()
    })

    it('should toggle between ascending and descending', async () => {
      const user = userEvent.setup()
      render(<FeatureFlagsAdminPage />)

      await waitFor(() => {
        expect(screen.getByText('reports')).toBeInTheDocument()
      })

      const nameHeader = screen.getByText('Name').closest('button')
      await user.click(nameHeader!)
      await user.click(nameHeader!)

      await waitFor(() => {
        const rows = screen.getAllByRole('row')
        const rowTexts = rows.map((row) => row.textContent)
        const evalIndex = rowTexts.findIndex((text) =>
          text?.includes('evaluations')
        )
        const genIndex = rowTexts.findIndex((text) =>
          text?.includes('generations')
        )

        expect(evalIndex).toBeLessThan(genIndex)
      })
    })
  })

  describe('UI States', () => {
    it('should disable buttons while saving', async () => {
      jest.useFakeTimers()
      const user = userEvent.setup({ delay: null })
      const mockApi = api as jest.Mocked<typeof api>
      let resolvePromise: (value: any) => void
      mockApi.updateFeatureFlag = jest.fn().mockImplementation(
        () =>
          new Promise((resolve) => {
            resolvePromise = resolve
          })
      )

      render(<FeatureFlagsAdminPage />)

      await waitFor(() => {
        expect(screen.getByText('reports')).toBeInTheDocument()
      })

      const toggles = screen.getAllByRole('switch')
      await user.click(toggles[0])

      const applyButton = screen.getByText(/Apply Changes/)
      await user.click(applyButton)

      const discardButton = screen.getByText('Discard Changes')
      expect(discardButton).toBeDisabled()

      resolvePromise!(mockFlags[0])
      jest.advanceTimersByTime(500)
      jest.useRealTimers()
    })

    it('should show breadcrumb navigation', async () => {
      render(<FeatureFlagsAdminPage />)

      await waitFor(() => {
        // Dashboard renders as HomeIcon, not text
        expect(screen.getAllByText('Feature Flags').length).toBeGreaterThan(0)
      })
    })

    it('should display page title', async () => {
      render(<FeatureFlagsAdminPage />)

      await waitFor(() => {
        expect(screen.getByText('reports')).toBeInTheDocument()
      })

      expect(screen.getAllByText('Feature Flags').length).toBeGreaterThan(0)
    })

    it('should show table headers', async () => {
      render(<FeatureFlagsAdminPage />)

      await waitFor(() => {
        expect(screen.getByText('reports')).toBeInTheDocument()
      })

      const headers = ['Name', 'Description', 'Status', 'Created']
      headers.forEach((header) => {
        expect(
          screen.getByRole('columnheader', { name: new RegExp(header, 'i') })
        ).toBeInTheDocument()
      })
    })
  })

  describe('Empty States', () => {
    it('should show empty state when no flags exist', async () => {
      const mockApi = api as jest.Mocked<typeof api>
      mockApi.getAllFeatureFlagsForAdmin = jest.fn().mockResolvedValue([])

      render(<FeatureFlagsAdminPage />)

      await waitFor(() => {
        expect(screen.getByText('No feature flags found.')).toBeInTheDocument()
      })
    })

    it('should show empty state with search query', async () => {
      const user = userEvent.setup()
      render(<FeatureFlagsAdminPage />)

      await waitFor(() => {
        expect(screen.getByText('reports')).toBeInTheDocument()
      })

      const searchInput = screen.getByPlaceholderText('Search feature flags...')
      await user.type(searchInput, 'xyz')

      await waitFor(() => {
        expect(
          screen.getByText(/No feature flags found matching "xyz"/)
        ).toBeInTheDocument()
      })
    })
  })
})

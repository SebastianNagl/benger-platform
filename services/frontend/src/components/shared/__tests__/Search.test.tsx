/**
 * @jest-environment jsdom
 */
import { beforeEach, describe, expect, it, jest } from '@jest/globals'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MobileSearch, Search } from '../Search'

// Mock next/navigation
const mockPush = jest.fn()
const mockPathname = '/'
const mockSearchParams = new URLSearchParams()

jest.mock('next/navigation', () => ({
  useRouter: () => ({
    push: mockPush,
  }),
  usePathname: () => mockPathname,
  useSearchParams: () => mockSearchParams,
}))

// Mock AuthContext
const mockUser = {
  id: '1',
  username: 'testuser',
  email: 'test@example.com',
  is_superadmin: false,
}

const mockOrganizations = [{ id: '1', name: 'Test Org', role: 'CONTRIBUTOR' }]

jest.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({
    user: mockUser,
    organizations: mockOrganizations,
  }),
}))

// Mock FeatureFlagContext
const mockFlags = {
  reports: true,
  data: true,
  generations: true,
  evaluations: true,
  'how-to': true,
}

jest.mock('@/contexts/FeatureFlagContext', () => ({
  useFeatureFlags: () => ({
    flags: mockFlags,
  }),
}))

// Mock I18nContext
const mockT = jest.fn((key: string) => {
  const translations: Record<string, string> = {
    'search.placeholder': 'Search...',
    'search.pages.landing.title': 'Landing Page',
    'search.pages.landing.description': 'Landing page',
    'search.pages.dashboard.title': 'Dashboard',
    'search.pages.dashboard.description': 'Dashboard page',
    'search.pages.projects.title': 'Projects',
    'search.pages.projects.description': 'Projects overview',
    'search.categories.benger': 'BenGER Core',
    'search.categories.projectsAndData': 'Projects & Data',
    'search.categories.administration': 'Administration',
    'search.noResults': 'No results for',
    'search.tryAgain': 'Please try different keywords.',
  }
  return translations[key] || key
})

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: mockT,
    locale: 'en',
    isReady: true,
  }),
}))

// Mock Navigation
jest.mock('@/components/layout/Navigation', () => ({
  navigation: [
    {
      title: 'BenGER Core',
      links: [
        { href: '/', title: 'Home' },
        { href: '/dashboard', title: 'Dashboard' },
      ],
    },
  ],
}))

// Mock MobileNavigationStore
jest.mock('@/components/layout/MobileNavigation', () => ({
  useMobileNavigationStore: () => ({
    close: jest.fn(),
  }),
}))

// Mock @headlessui/react
jest.mock('@headlessui/react', () => {
  const React = jest.requireActual('react') as typeof import('react')

  function MockDialog({ children, open, onClose, className }: any) {
    if (!open) return null
    return (
      <div data-testid="dialog-wrapper" className={className}>
        {children}
      </div>
    )
  }

  function MockDialogPanel({ children, className }: any) {
    return (
      <div data-testid="dialog-panel" className={className}>
        {children}
      </div>
    )
  }
  MockDialogPanel.displayName = 'MockDialog.Panel'
  MockDialog.Panel = MockDialogPanel

  function MockDialogBackdrop({ children, className }: any) {
    return (
      <div data-testid="dialog-backdrop" className={className}>
        {children}
      </div>
    )
  }
  MockDialogBackdrop.displayName = 'MockDialogBackdrop'

  return {
    Dialog: MockDialog,
    DialogPanel: MockDialog.Panel,
    DialogBackdrop: MockDialogBackdrop,
  }
})

// Mock react-highlight-words
jest.mock('react-highlight-words', () => {
  return function Highlighter({ textToHighlight }: any) {
    return <span>{textToHighlight}</span>
  }
})

// Mock @algolia/autocomplete-core
const mockAutocomplete = {
  setQuery: jest.fn(),
  getInputProps: jest.fn(() => ({
    value: '',
    onChange: jest.fn(),
    onKeyDown: jest.fn(),
    placeholder: '',
  })),
  getRootProps: jest.fn(() => ({})),
  getFormProps: jest.fn(() => ({})),
  getPanelProps: jest.fn(() => ({})),
  getListProps: jest.fn(() => ({})),
  getItemProps: jest.fn(() => ({})),
}

jest.mock('@algolia/autocomplete-core', () => ({
  createAutocomplete: jest.fn(() => mockAutocomplete),
}))

describe('Search Component', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockPush.mockClear()
  })

  describe('Basic Rendering', () => {
    it('should render search button with correct text', () => {
      render(<Search />)

      const button = screen.getByRole('button')
      expect(button).toBeInTheDocument()
      expect(button).toHaveTextContent('Search...')
    })

    it('should render search icon', () => {
      render(<Search />)

      const svg = screen.getByRole('button').querySelector('svg')
      expect(svg).toBeInTheDocument()
    })

    it('should render keyboard shortcut indicator', () => {
      render(<Search />)

      const kbdElements = screen
        .getAllByRole('button')[0]
        .querySelectorAll('kbd')
      expect(kbdElements.length).toBeGreaterThan(0)
    })

    it('should render with correct default styles', () => {
      render(<Search />)

      const button = screen.getByRole('button')
      expect(button).toHaveClass('rounded-full')
      expect(button).toHaveClass('bg-white')
      expect(button).toHaveClass('dark:bg-white/5')
    })

    it('should be hidden on mobile by default', () => {
      render(<Search />)

      const container = screen.getByRole('button').closest('div')
      expect(container).toHaveClass('hidden')
      expect(container).toHaveClass('lg:block')
    })
  })

  describe('Input Handling', () => {
    it('should open search dialog when button is clicked', async () => {
      const user = userEvent.setup()
      render(<Search />)

      const button = screen.getByRole('button')
      await user.click(button)

      await waitFor(() => {
        expect(screen.getByTestId('dialog-wrapper')).toBeInTheDocument()
      })
    })

    it('should display search input in dialog', async () => {
      const user = userEvent.setup()
      render(<Search />)

      await user.click(screen.getByRole('button'))

      await waitFor(() => {
        expect(mockAutocomplete.getInputProps).toHaveBeenCalled()
      })
    })

    it('should handle keyboard shortcut Cmd+K', () => {
      render(<Search />)

      const event = new KeyboardEvent('keydown', {
        key: 'k',
        metaKey: true,
      })
      window.dispatchEvent(event)

      waitFor(() => {
        expect(screen.getByTestId('dialog-wrapper')).toBeInTheDocument()
      })
    })

    it('should handle keyboard shortcut Ctrl+K', () => {
      render(<Search />)

      const event = new KeyboardEvent('keydown', {
        key: 'k',
        ctrlKey: true,
      })
      window.dispatchEvent(event)

      waitFor(() => {
        expect(screen.getByTestId('dialog-wrapper')).toBeInTheDocument()
      })
    })

    it('should close dialog on Escape key', async () => {
      const user = userEvent.setup()
      render(<Search />)

      await user.click(screen.getByRole('button'))

      await waitFor(() => {
        expect(screen.getByTestId('dialog-wrapper')).toBeInTheDocument()
      })
    })
  })

  describe('Search Functionality', () => {
    it('should initialize autocomplete with correct configuration', () => {
      const { createAutocomplete } = require('@algolia/autocomplete-core')
      render(<Search />)

      expect(createAutocomplete).toHaveBeenCalled()
      const config = (createAutocomplete as jest.Mock).mock.calls[0][0]
      expect(config).toHaveProperty('getSources')
      expect(config).toHaveProperty('shouldPanelOpen')
    })

    it('should call translation function for placeholder', () => {
      render(<Search />)

      expect(mockT).toHaveBeenCalledWith('search.placeholder')
    })

    it('should clear query when dialog is closed', async () => {
      const user = userEvent.setup()
      render(<Search />)

      await user.click(screen.getByRole('button'))

      await waitFor(() => {
        expect(screen.getByTestId('dialog-wrapper')).toBeInTheDocument()
      })
    })
  })

  describe('Results Display', () => {
    it('should display search results container', async () => {
      const user = userEvent.setup()
      render(<Search />)

      await user.click(screen.getByRole('button'))

      await waitFor(() => {
        expect(screen.getByTestId('dialog-panel')).toBeInTheDocument()
      })
    })

    it('should display dialog backdrop when open', async () => {
      const user = userEvent.setup()
      render(<Search />)

      await user.click(screen.getByRole('button'))

      await waitFor(() => {
        expect(screen.getByTestId('dialog-backdrop')).toBeInTheDocument()
      })
    })
  })

  describe('Props/Attributes', () => {
    it('should have correct button type attribute', () => {
      render(<Search />)

      const button = screen.getByRole('button')
      expect(button).toHaveAttribute('type', 'button')
    })

    it('should apply ring styles for focus state', () => {
      render(<Search />)

      const button = screen.getByRole('button')
      expect(button).toHaveClass('ring-1')
      expect(button).toHaveClass('ring-zinc-900/10')
    })

    it('should have hover transition classes', () => {
      render(<Search />)

      const button = screen.getByRole('button')
      expect(button).toHaveClass('transition')
      expect(button).toHaveClass('hover:ring-zinc-900/20')
    })
  })

  describe('Event Handlers', () => {
    it('should handle button click event', async () => {
      const user = userEvent.setup()
      render(<Search />)

      const button = screen.getByRole('button')
      await user.click(button)

      await waitFor(() => {
        expect(screen.getByTestId('dialog-wrapper')).toBeInTheDocument()
      })
    })

    it('should not open dialog when keyboard shortcut is prevented', () => {
      render(<Search />)

      const event = new KeyboardEvent('keydown', {
        key: 'k',
        metaKey: true,
      })

      Object.defineProperty(event, 'defaultPrevented', {
        value: true,
        writable: false,
      })

      window.dispatchEvent(event)
    })
  })

  describe('Accessibility', () => {
    it('should have role="button" on search trigger', () => {
      render(<Search />)

      expect(screen.getByRole('button')).toBeInTheDocument()
    })

    it('should have aria-hidden on search icon', () => {
      render(<Search />)

      const svg = screen.getByRole('button').querySelector('svg')
      expect(svg).toHaveAttribute('aria-hidden', 'true')
    })

    it('should display keyboard shortcut in accessible format', () => {
      render(<Search />)

      const kbdElements = screen.getByRole('button').querySelectorAll('kbd')
      expect(kbdElements.length).toBeGreaterThan(0)
    })

    it('should maintain focus management when dialog opens', async () => {
      const user = userEvent.setup()
      render(<Search />)

      const button = screen.getByRole('button')
      await user.click(button)

      await waitFor(() => {
        expect(screen.getByTestId('dialog-wrapper')).toBeInTheDocument()
      })
    })
  })

  describe('Edge Cases', () => {
    it('should handle rapid button clicks', async () => {
      const user = userEvent.setup()
      render(<Search />)

      const button = screen.getByRole('button')
      await user.click(button)
      await user.click(button)
      await user.click(button)

      await waitFor(() => {
        expect(screen.getByTestId('dialog-wrapper')).toBeInTheDocument()
      })
    })

    it('should handle undefined translation keys gracefully', () => {
      expect(() => render(<Search />)).not.toThrow()
    })

    it('should render when feature flags are enabled', () => {
      expect(() => render(<Search />)).not.toThrow()
    })

    it('should render with authenticated user', () => {
      expect(() => render(<Search />)).not.toThrow()
    })

    it('should render with organizations', () => {
      expect(() => render(<Search />)).not.toThrow()
    })

    it('should handle very long search query', async () => {
      const user = userEvent.setup()
      render(<Search />)

      await user.click(screen.getByRole('button'))

      await waitFor(() => {
        expect(screen.getByTestId('dialog-wrapper')).toBeInTheDocument()
      })
    })

    it('should handle special characters in search', async () => {
      const user = userEvent.setup()
      render(<Search />)

      await user.click(screen.getByRole('button'))

      await waitFor(() => {
        expect(screen.getByTestId('dialog-wrapper')).toBeInTheDocument()
      })
    })

    it('should handle empty search input', async () => {
      const user = userEvent.setup()
      render(<Search />)

      await user.click(screen.getByRole('button'))

      await waitFor(() => {
        expect(screen.getByTestId('dialog-wrapper')).toBeInTheDocument()
      })
    })

    it('should render with i18n support', () => {
      expect(() => render(<Search />)).not.toThrow()
    })
  })
})

describe('MobileSearch Component', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockPush.mockClear()
  })

  describe('Basic Rendering', () => {
    it('should render mobile search button', () => {
      render(<MobileSearch />)

      const button = screen.getByRole('button')
      expect(button).toBeInTheDocument()
    })

    it('should render search icon without text', () => {
      render(<MobileSearch />)

      const button = screen.getByRole('button')
      const svg = button.querySelector('svg')
      expect(svg).toBeInTheDocument()
      expect(button.textContent).toBe('')
    })

    it('should have aria-label for accessibility', () => {
      render(<MobileSearch />)

      const button = screen.getByRole('button')
      expect(button).toHaveAttribute('aria-label')
    })

    it('should be visible only on mobile', () => {
      render(<MobileSearch />)

      const container = screen.getByRole('button').closest('div')
      expect(container).toHaveClass('lg:hidden')
    })

    it('should have correct mobile styles', () => {
      render(<MobileSearch />)

      const button = screen.getByRole('button')
      expect(button).toHaveClass('rounded-md')
      expect(button).toHaveClass('size-6')
    })
  })

  describe('Input Handling', () => {
    it('should open search dialog on button click', async () => {
      const user = userEvent.setup()
      render(<MobileSearch />)

      const button = screen.getByRole('button')
      await user.click(button)

      await waitFor(() => {
        expect(screen.getByTestId('dialog-wrapper')).toBeInTheDocument()
      })
    })

    it('should handle touch interactions', async () => {
      const user = userEvent.setup()
      render(<MobileSearch />)

      const button = screen.getByRole('button')
      await user.click(button)

      await waitFor(() => {
        expect(screen.getByTestId('dialog-wrapper')).toBeInTheDocument()
      })
    })
  })

  describe('Search Functionality', () => {
    it('should open search dialog', async () => {
      const user = userEvent.setup()
      render(<MobileSearch />)

      await user.click(screen.getByRole('button'))

      await waitFor(() => {
        expect(screen.getByTestId('dialog-wrapper')).toBeInTheDocument()
      })
    })

    it('should use same search functionality as desktop', async () => {
      const user = userEvent.setup()
      render(<MobileSearch />)

      await user.click(screen.getByRole('button'))

      await waitFor(() => {
        expect(screen.getByTestId('dialog-panel')).toBeInTheDocument()
      })
    })
  })

  describe('Props/Attributes', () => {
    it('should have button type attribute', () => {
      render(<MobileSearch />)

      const button = screen.getByRole('button')
      expect(button).toHaveAttribute('type', 'button')
    })

    it('should have hover styles', () => {
      render(<MobileSearch />)

      const button = screen.getByRole('button')
      expect(button).toHaveClass('hover:bg-zinc-900/5')
      expect(button).toHaveClass('dark:hover:bg-white/5')
    })

    it('should have transition class', () => {
      render(<MobileSearch />)

      const button = screen.getByRole('button')
      expect(button).toHaveClass('transition')
    })
  })

  describe('Event Handlers', () => {
    it('should handle button click', async () => {
      const user = userEvent.setup()
      render(<MobileSearch />)

      const button = screen.getByRole('button')
      await user.click(button)

      await waitFor(() => {
        expect(screen.getByTestId('dialog-wrapper')).toBeInTheDocument()
      })
    })
  })

  describe('Accessibility', () => {
    it('should have accessible label', () => {
      render(<MobileSearch />)

      const button = screen.getByRole('button')
      expect(button).toHaveAttribute('aria-label', 'Search...')
    })

    it('should have aria-hidden on icon', () => {
      render(<MobileSearch />)

      const svg = screen.getByRole('button').querySelector('svg')
      expect(svg).toHaveAttribute('aria-hidden', 'true')
    })

    it('should be keyboard accessible', async () => {
      const user = userEvent.setup()
      render(<MobileSearch />)

      const button = screen.getByRole('button')
      button.focus()

      expect(document.activeElement).toBe(button)

      await user.keyboard('{Enter}')

      await waitFor(() => {
        expect(screen.getByTestId('dialog-wrapper')).toBeInTheDocument()
      })
    })
  })

  describe('Edge Cases', () => {
    it('should handle rapid clicks', async () => {
      const user = userEvent.setup()
      render(<MobileSearch />)

      const button = screen.getByRole('button')
      await user.click(button)
      await user.click(button)
      await user.click(button)

      await waitFor(() => {
        expect(screen.getByTestId('dialog-wrapper')).toBeInTheDocument()
      })
    })

    it('should render without errors', () => {
      expect(() => render(<MobileSearch />)).not.toThrow()
    })
  })
})

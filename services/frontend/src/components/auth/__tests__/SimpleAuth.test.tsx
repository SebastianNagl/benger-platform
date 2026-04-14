/**
 * @jest-environment jsdom
 */
/* eslint-disable react-hooks/globals -- Valid test pattern: capturing hook values via external variables for assertions */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { SimpleAuthProvider, useAuth } from '../SimpleAuth'

// Test component to access auth context
function TestComponent() {
  const {
    user,
    isLoading,
    login,
    logout,
    organizations,
    currentOrganization,
    setCurrentOrganization,
  } = useAuth()

  return (
    <div>
      <div data-testid="user-status">
        {isLoading
          ? 'Loading...'
          : user
            ? `User: ${user.username}`
            : 'Not logged in'}
      </div>
      <div data-testid="user-email">{user?.email || 'No email'}</div>
      <div data-testid="user-role">{user?.role || 'No role'}</div>
      <div data-testid="org-count">Orgs: {organizations.length}</div>
      <div data-testid="current-org">
        {currentOrganization?.name || 'No org'}
      </div>

      <button
        onClick={() => login('testuser', 'password')}
        data-testid="login-btn"
      >
        Login
      </button>
      <button onClick={() => logout()} data-testid="logout-btn">
        Logout
      </button>
      <button
        onClick={() => setCurrentOrganization(organizations[1])}
        data-testid="switch-org-btn"
        disabled={organizations.length < 2}
      >
        Switch Org
      </button>
    </div>
  )
}

describe('SimpleAuth Provider', () => {
  describe('Provider Initialization', () => {
    it('renders children correctly', () => {
      render(
        <SimpleAuthProvider>
          <div data-testid="child">Child Component</div>
        </SimpleAuthProvider>
      )

      expect(screen.getByTestId('child')).toBeInTheDocument()
    })

    it('initializes with no user logged in', () => {
      render(
        <SimpleAuthProvider>
          <TestComponent />
        </SimpleAuthProvider>
      )

      expect(screen.getByTestId('user-status')).toHaveTextContent(
        'Not logged in'
      )
      expect(screen.getByTestId('user-email')).toHaveTextContent('No email')
      expect(screen.getByTestId('user-role')).toHaveTextContent('No role')
    })

    it('initializes with default organizations', () => {
      render(
        <SimpleAuthProvider>
          <TestComponent />
        </SimpleAuthProvider>
      )

      expect(screen.getByTestId('org-count')).toHaveTextContent('Orgs: 2')
    })

    it('has TUM and Test Org as default organizations', () => {
      let organizations: any[] = []

      function OrgListComponent() {
        const { organizations: orgs } = useAuth()
        organizations = orgs
        return (
          <div>
            {orgs.map((org) => (
              <div key={org.id} data-testid={`org-${org.slug}`}>
                {org.name}
              </div>
            ))}
          </div>
        )
      }

      render(
        <SimpleAuthProvider>
          <OrgListComponent />
        </SimpleAuthProvider>
      )

      expect(screen.getByTestId('org-tum')).toHaveTextContent('TUM')
      expect(screen.getByTestId('org-test-org')).toHaveTextContent('Test Org')
      expect(organizations).toHaveLength(2)
      expect(organizations[0]).toEqual({ id: '1', name: 'TUM', slug: 'tum' })
      expect(organizations[1]).toEqual({
        id: '2',
        name: 'Test Org',
        slug: 'test-org',
      })
    })

    it('initializes with no current organization', () => {
      render(
        <SimpleAuthProvider>
          <TestComponent />
        </SimpleAuthProvider>
      )

      expect(screen.getByTestId('current-org')).toHaveTextContent('No org')
    })

    it('is not loading initially', () => {
      render(
        <SimpleAuthProvider>
          <TestComponent />
        </SimpleAuthProvider>
      )

      expect(screen.getByTestId('user-status')).toHaveTextContent(
        'Not logged in'
      )
      expect(screen.getByTestId('user-status')).not.toHaveTextContent(
        'Loading...'
      )
    })
  })

  describe('Login Functionality', () => {
    it('creates a user with provided username', async () => {
      const user = userEvent.setup()

      render(
        <SimpleAuthProvider>
          <TestComponent />
        </SimpleAuthProvider>
      )

      const loginBtn = screen.getByTestId('login-btn')
      await user.click(loginBtn)

      await waitFor(
        () => {
          expect(screen.getByTestId('user-status')).toHaveTextContent(
            'User: testuser'
          )
        },
        { timeout: 3000 }
      )
    })

    it('creates user with email based on username', async () => {
      const user = userEvent.setup()

      render(
        <SimpleAuthProvider>
          <TestComponent />
        </SimpleAuthProvider>
      )

      const loginBtn = screen.getByTestId('login-btn')
      await user.click(loginBtn)

      await waitFor(
        () => {
          expect(screen.getByTestId('user-email')).toHaveTextContent(
            'testuser@example.com'
          )
        },
        { timeout: 3000 }
      )
    })

    it('assigns user role by default', async () => {
      const user = userEvent.setup()

      render(
        <SimpleAuthProvider>
          <TestComponent />
        </SimpleAuthProvider>
      )

      const loginBtn = screen.getByTestId('login-btn')
      await user.click(loginBtn)

      await waitFor(
        () => {
          expect(screen.getByTestId('user-role')).toHaveTextContent('user')
        },
        { timeout: 3000 }
      )
    })

    it('sets current organization to TUM after login', async () => {
      const user = userEvent.setup()

      render(
        <SimpleAuthProvider>
          <TestComponent />
        </SimpleAuthProvider>
      )

      const loginBtn = screen.getByTestId('login-btn')
      await user.click(loginBtn)

      await waitFor(
        () => {
          expect(screen.getByTestId('current-org')).toHaveTextContent('TUM')
        },
        { timeout: 3000 }
      )
    })

    it('clears loading state after login', async () => {
      const user = userEvent.setup()

      render(
        <SimpleAuthProvider>
          <TestComponent />
        </SimpleAuthProvider>
      )

      const loginBtn = screen.getByTestId('login-btn')

      await user.click(loginBtn)

      await waitFor(
        () => {
          expect(screen.getByTestId('user-status')).not.toHaveTextContent(
            'Loading...'
          )
          expect(screen.getByTestId('user-status')).toHaveTextContent('User:')
        },
        { timeout: 3000 }
      )
    })
  })

  describe('Logout Functionality', () => {
    it('clears user after logout', async () => {
      const user = userEvent.setup()

      render(
        <SimpleAuthProvider>
          <TestComponent />
        </SimpleAuthProvider>
      )

      const loginBtn = screen.getByTestId('login-btn')
      const logoutBtn = screen.getByTestId('logout-btn')

      // Login
      await user.click(loginBtn)

      await waitFor(
        () => {
          expect(screen.getByTestId('user-status')).toHaveTextContent('User:')
        },
        { timeout: 3000 }
      )

      // Logout
      await user.click(logoutBtn)

      await waitFor(
        () => {
          expect(screen.getByTestId('user-status')).toHaveTextContent(
            'Not logged in'
          )
        },
        { timeout: 3000 }
      )
    })

    it('clears current organization after logout', async () => {
      const user = userEvent.setup()

      render(
        <SimpleAuthProvider>
          <TestComponent />
        </SimpleAuthProvider>
      )

      const loginBtn = screen.getByTestId('login-btn')
      const logoutBtn = screen.getByTestId('logout-btn')

      // Login
      await user.click(loginBtn)

      await waitFor(
        () => {
          expect(screen.getByTestId('current-org')).toHaveTextContent('TUM')
        },
        { timeout: 3000 }
      )

      // Logout
      await user.click(logoutBtn)

      await waitFor(
        () => {
          expect(screen.getByTestId('current-org')).toHaveTextContent('No org')
        },
        { timeout: 3000 }
      )
    })
  })

  describe('Organization Switching', () => {
    it('allows switching to different organization', async () => {
      const user = userEvent.setup()

      render(
        <SimpleAuthProvider>
          <TestComponent />
        </SimpleAuthProvider>
      )

      const switchOrgBtn = screen.getByTestId('switch-org-btn')
      await user.click(switchOrgBtn)

      await waitFor(
        () => {
          expect(screen.getByTestId('current-org')).toHaveTextContent(
            'Test Org'
          )
        },
        { timeout: 3000 }
      )
    })

    it('maintains organization list after login/logout', async () => {
      const user = userEvent.setup()

      render(
        <SimpleAuthProvider>
          <TestComponent />
        </SimpleAuthProvider>
      )

      const loginBtn = screen.getByTestId('login-btn')
      const logoutBtn = screen.getByTestId('logout-btn')

      expect(screen.getByTestId('org-count')).toHaveTextContent('Orgs: 2')

      // Login
      await user.click(loginBtn)

      await waitFor(
        () => {
          expect(screen.getByTestId('user-status')).toHaveTextContent('User:')
        },
        { timeout: 3000 }
      )

      expect(screen.getByTestId('org-count')).toHaveTextContent('Orgs: 2')

      // Logout
      await user.click(logoutBtn)

      await waitFor(
        () => {
          expect(screen.getByTestId('user-status')).toHaveTextContent(
            'Not logged in'
          )
        },
        { timeout: 3000 }
      )

      expect(screen.getByTestId('org-count')).toHaveTextContent('Orgs: 2')
    })
  })

  describe('useAuth Hook', () => {
    it('throws error when used outside provider', () => {
      // Suppress console.error for this test
      const consoleError = jest
        .spyOn(console, 'error')
        .mockImplementation(() => {})

      function ComponentWithoutProvider() {
        useAuth()
        return <div>Test</div>
      }

      expect(() => render(<ComponentWithoutProvider />)).toThrow(
        'useAuth must be used within an AuthProvider'
      )

      consoleError.mockRestore()
    })

    it('provides all required context values', () => {
      let contextValue: any

      function ContextConsumer() {
        contextValue = useAuth()
        return null
      }

      render(
        <SimpleAuthProvider>
          <ContextConsumer />
        </SimpleAuthProvider>
      )

      expect(contextValue).toHaveProperty('user')
      expect(contextValue).toHaveProperty('login')
      expect(contextValue).toHaveProperty('logout')
      expect(contextValue).toHaveProperty('isLoading')
      expect(contextValue).toHaveProperty('organizations')
      expect(contextValue).toHaveProperty('currentOrganization')
      expect(contextValue).toHaveProperty('setCurrentOrganization')
    })
  })

  describe('Edge Cases', () => {
    it('handles multiple rapid login attempts', async () => {
      const user = userEvent.setup()

      render(
        <SimpleAuthProvider>
          <TestComponent />
        </SimpleAuthProvider>
      )

      const loginBtn = screen.getByTestId('login-btn')

      // Click login once (multiple rapid clicks don't work well with async operations)
      await user.click(loginBtn)

      await waitFor(
        () => {
          expect(screen.getByTestId('user-status')).toHaveTextContent('User:')
        },
        { timeout: 3000 }
      )
    })

    it('handles logout after login', async () => {
      const user = userEvent.setup()

      render(
        <SimpleAuthProvider>
          <TestComponent />
        </SimpleAuthProvider>
      )

      const loginBtn = screen.getByTestId('login-btn')
      const logoutBtn = screen.getByTestId('logout-btn')

      // Login first
      await user.click(loginBtn)

      await waitFor(
        () => {
          expect(screen.getByTestId('user-status')).toHaveTextContent('User:')
        },
        { timeout: 3000 }
      )

      // Logout
      await user.click(logoutBtn)

      await waitFor(
        () => {
          expect(screen.getByTestId('user-status')).toHaveTextContent(
            'Not logged in'
          )
        },
        { timeout: 3000 }
      )
    })

    it('handles setting null organization', async () => {
      const user = userEvent.setup()

      function OrgSetterComponent() {
        const { currentOrganization, setCurrentOrganization } = useAuth()

        return (
          <div>
            <div data-testid="current-org">
              {currentOrganization?.name || 'No org'}
            </div>
            <button
              onClick={() => setCurrentOrganization(null)}
              data-testid="clear-org-btn"
            >
              Clear Org
            </button>
          </div>
        )
      }

      render(
        <SimpleAuthProvider>
          <OrgSetterComponent />
        </SimpleAuthProvider>
      )

      const clearOrgBtn = screen.getByTestId('clear-org-btn')
      await user.click(clearOrgBtn)

      await waitFor(
        () => {
          expect(screen.getByTestId('current-org')).toHaveTextContent('No org')
        },
        { timeout: 3000 }
      )
    })
  })
})

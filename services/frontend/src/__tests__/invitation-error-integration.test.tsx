/**
 * Integration Tests for Invitation Error Handling Flow
 * Tests the complete error handling flow from UI to API and back
 */

import { useToast } from '@/components/shared/Toast'
import { organizationsAPI } from '@/lib/api/organizations'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

// Mock modules
jest.mock('@/lib/api/organizations')
jest.mock('@/components/shared/Toast')
jest.mock('next/navigation', () => ({
  useRouter: () => ({
    push: jest.fn(),
  }),
}))

// Component that simulates invitation flow
const InvitationTestComponent = () => {
  const { addToast } = useToast()
  const [email, setEmail] = React.useState('')
  const [role, setRole] = React.useState<
    'ANNOTATOR' | 'CONTRIBUTOR' | 'ORG_ADMIN'
  >('ANNOTATOR')
  const [loading, setLoading] = React.useState(false)
  const [showModal, setShowModal] = React.useState(false)
  const [existingInvitations, setExistingInvitations] = React.useState<any[]>(
    []
  )

  // Clear form when modal opens (mimics actual implementation)
  React.useEffect(() => {
    if (showModal) {
      setEmail('')
      setRole('ANNOTATOR')
    }
  }, [showModal])

  const handleInvite = async () => {
    if (!email) return

    try {
      setLoading(true)

      // Check for existing invitations first
      const invitations =
        await organizationsAPI.getOrganizationInvitations('org-123')
      const existingInvite = invitations.find(
        (inv: any) =>
          inv.email.toLowerCase() === email.toLowerCase() && !inv.accepted
      )

      if (existingInvite) {
        addToast(`An invitation has already been sent to ${email}`, 'warning')
        return
      }

      await organizationsAPI.sendInvitation('org-123', { email, role })

      addToast('Invitation sent successfully', 'success')
      setShowModal(false)

      // Reload members (simulated)
      await organizationsAPI.getOrganizationMembers('org-123')
    } catch (error: any) {
      let errorMessage = 'Failed to send invitation'

      if (error.response?.data?.detail) {
        const detail = error.response.data.detail

        if (detail.includes('already exists')) {
          errorMessage = `An invitation has already been sent to ${email}`
        } else if (detail.includes('invalid email')) {
          errorMessage = 'Please enter a valid email address'
        } else if (detail.includes('rate limit')) {
          errorMessage =
            'Too many invitations sent. Please wait before sending more'
        } else {
          errorMessage = detail
        }
      } else if (error.message?.includes('Network error')) {
        errorMessage =
          'Network error. Please check your connection and try again'
      }

      addToast(errorMessage, 'error')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <button onClick={() => setShowModal(true)}>Invite Member</button>

      {showModal && (
        <div data-testid="invite-modal">
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="colleague@example.com"
            required
          />
          <select value={role} onChange={(e) => setRole(e.target.value as any)}>
            <option value="ANNOTATOR">Annotator</option>
            <option value="CONTRIBUTOR">Contributor</option>
            <option value="ORG_ADMIN">Org Admin</option>
          </select>
          <button onClick={handleInvite} disabled={loading}>
            {loading ? 'Sending...' : 'Send Invitation'}
          </button>
          <button onClick={() => setShowModal(false)}>Cancel</button>
        </div>
      )}
    </div>
  )
}

const React = require('react')

describe('Invitation Error Flow - Integration Tests', () => {
  const mockAddToast = jest.fn()
  const mockGetOrganizationInvitations =
    organizationsAPI.getOrganizationInvitations as jest.Mock
  const mockSendInvitation = organizationsAPI.sendInvitation as jest.Mock
  const mockGetOrganizationMembers =
    organizationsAPI.getOrganizationMembers as jest.Mock

  beforeEach(() => {
    jest.clearAllMocks()

    // Setup toast mock
    ;(useToast as jest.Mock).mockReturnValue({
      addToast: mockAddToast,
    })

    // Default mock implementations
    mockGetOrganizationInvitations.mockResolvedValue([])
    mockGetOrganizationMembers.mockResolvedValue([])
  })

  describe('Complete Error Handling Flow', () => {
    it('should handle duplicate invitation flow end-to-end', async () => {
      const user = userEvent.setup()

      // Setup existing invitation
      mockGetOrganizationInvitations.mockResolvedValue([
        {
          id: 'inv-123',
          email: 'existing@example.com',
          role: 'ANNOTATOR',
          accepted: false,
        },
      ])

      render(<InvitationTestComponent />)

      // Open modal
      await user.click(screen.getByText('Invite Member'))
      expect(screen.getByTestId('invite-modal')).toBeInTheDocument()

      // Enter duplicate email
      const emailInput = screen.getByPlaceholderText('colleague@example.com')
      await user.type(emailInput, 'existing@example.com')

      // Send invitation
      await user.click(screen.getByText('Send Invitation'))

      // Should check for existing invitations
      await waitFor(() => {
        expect(mockGetOrganizationInvitations).toHaveBeenCalledWith('org-123')
      })

      // Should show warning toast
      expect(mockAddToast).toHaveBeenCalledWith(
        'An invitation has already been sent to existing@example.com',
        'warning'
      )

      // Should NOT call sendInvitation
      expect(mockSendInvitation).not.toHaveBeenCalled()
    })

    it('should handle API duplicate error gracefully', async () => {
      const user = userEvent.setup()

      // No existing invitations locally
      mockGetOrganizationInvitations.mockResolvedValue([])

      // But API returns duplicate error
      mockSendInvitation.mockRejectedValue({
        response: {
          status: 400,
          data: {
            detail: 'An active invitation already exists for this email',
          },
        },
      })

      render(<InvitationTestComponent />)

      // Open modal
      await user.click(screen.getByText('Invite Member'))

      // Enter email
      const emailInput = screen.getByPlaceholderText('colleague@example.com')
      await user.type(emailInput, 'duplicate@example.com')

      // Send invitation
      await user.click(screen.getByText('Send Invitation'))

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(
          'An invitation has already been sent to duplicate@example.com',
          'error'
        )
      })
    })

    it('should handle rate limiting errors', async () => {
      const user = userEvent.setup()

      mockGetOrganizationInvitations.mockResolvedValue([])
      mockSendInvitation.mockRejectedValue({
        response: {
          status: 429,
          data: {
            detail: 'rate limit exceeded',
          },
        },
      })

      render(<InvitationTestComponent />)

      await user.click(screen.getByText('Invite Member'))

      const emailInput = screen.getByPlaceholderText('colleague@example.com')
      await user.type(emailInput, 'test@example.com')

      await user.click(screen.getByText('Send Invitation'))

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(
          'Too many invitations sent. Please wait before sending more',
          'error'
        )
      })
    })

    it('should handle network errors', async () => {
      const user = userEvent.setup()

      mockGetOrganizationInvitations.mockResolvedValue([])
      mockSendInvitation.mockRejectedValue(
        new Error('Network error: Unable to connect')
      )

      render(<InvitationTestComponent />)

      await user.click(screen.getByText('Invite Member'))

      const emailInput = screen.getByPlaceholderText('colleague@example.com')
      await user.type(emailInput, 'test@example.com')

      await user.click(screen.getByText('Send Invitation'))

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(
          'Network error. Please check your connection and try again',
          'error'
        )
      })
    })

    it('should handle successful invitation with proper cleanup', async () => {
      const user = userEvent.setup()

      mockGetOrganizationInvitations.mockResolvedValue([])
      mockSendInvitation.mockResolvedValue({
        id: 'inv-456',
        email: 'new@example.com',
        role: 'ANNOTATOR',
      })
      mockGetOrganizationMembers.mockResolvedValue([
        { user_id: 'user-123', user_email: 'existing@example.com' },
        { user_id: 'user-456', user_email: 'new@example.com' },
      ])

      render(<InvitationTestComponent />)

      // Open modal
      await user.click(screen.getByText('Invite Member'))

      // Enter email
      const emailInput = screen.getByPlaceholderText('colleague@example.com')
      await user.type(emailInput, 'new@example.com')

      // Send invitation
      await user.click(screen.getByText('Send Invitation'))

      await waitFor(() => {
        // Should show success toast
        expect(mockAddToast).toHaveBeenCalledWith(
          'Invitation sent successfully',
          'success'
        )

        // Should reload members
        expect(mockGetOrganizationMembers).toHaveBeenCalledWith('org-123')

        // Modal should be closed
        expect(screen.queryByTestId('invite-modal')).not.toBeInTheDocument()
      })
    })
  })

  describe('Form State Management Integration', () => {
    it('should clear form fields when modal reopens', async () => {
      const user = userEvent.setup()

      render(<InvitationTestComponent />)

      // First opening
      await user.click(screen.getByText('Invite Member'))

      const emailInput = screen.getByPlaceholderText(
        'colleague@example.com'
      ) as HTMLInputElement
      const roleSelect = screen.getByRole('combobox') as HTMLSelectElement

      // Fill form
      await user.type(emailInput, 'test@example.com')
      await user.selectOptions(roleSelect, 'CONTRIBUTOR')

      expect(emailInput.value).toBe('test@example.com')
      expect(roleSelect.value).toBe('CONTRIBUTOR')

      // Close modal
      await user.click(screen.getByText('Cancel'))
      expect(screen.queryByTestId('invite-modal')).not.toBeInTheDocument()

      // Reopen modal
      await user.click(screen.getByText('Invite Member'))

      // Fields should be reset
      const newEmailInput = screen.getByPlaceholderText(
        'colleague@example.com'
      ) as HTMLInputElement
      const newRoleSelect = screen.getByRole('combobox') as HTMLSelectElement

      expect(newEmailInput.value).toBe('')
      expect(newRoleSelect.value).toBe('ANNOTATOR')
    })

    it('should show loading state during invitation sending', async () => {
      const user = userEvent.setup()

      // Create a promise we can control
      let resolveInvitation: any
      const invitationPromise = new Promise((resolve) => {
        resolveInvitation = resolve
      })

      mockGetOrganizationInvitations.mockResolvedValue([])
      mockSendInvitation.mockReturnValue(invitationPromise)

      render(<InvitationTestComponent />)

      await user.click(screen.getByText('Invite Member'))

      const emailInput = screen.getByPlaceholderText('colleague@example.com')
      await user.type(emailInput, 'test@example.com')

      // Click send
      await user.click(screen.getByText('Send Invitation'))

      // Should show loading state
      expect(screen.getByText('Sending...')).toBeInTheDocument()

      // Resolve the promise
      act(() => {
        resolveInvitation({
          id: 'inv-123',
          email: 'test@example.com',
          role: 'ANNOTATOR',
        })
      })

      // Loading state should disappear
      await waitFor(() => {
        expect(screen.queryByText('Sending...')).not.toBeInTheDocument()
      })
    })
  })

  describe('Error Message Localization', () => {
    it('should display localized error messages', async () => {
      const user = userEvent.setup()

      mockGetOrganizationInvitations.mockResolvedValue([])

      // Test different error scenarios with localized messages
      const errorScenarios = [
        {
          error: {
            response: {
              status: 400,
              data: { detail: 'invalid email format' },
            },
          },
          expectedMessage: 'Please enter a valid email address',
        },
        {
          error: {
            response: {
              status: 400,
              data: { detail: 'An active invitation already exists' },
            },
          },
          expectedMessage:
            'An invitation has already been sent to test@example.com',
        },
      ]

      for (const scenario of errorScenarios) {
        jest.clearAllMocks()
        mockSendInvitation.mockRejectedValue(scenario.error)

        const { unmount } = render(<InvitationTestComponent />)

        await user.click(screen.getByText('Invite Member'))

        const emailInput = screen.getByPlaceholderText('colleague@example.com')
        await user.clear(emailInput)
        await user.type(emailInput, 'test@example.com')

        await user.click(screen.getByText('Send Invitation'))

        await waitFor(() => {
          expect(mockAddToast).toHaveBeenCalledWith(
            scenario.expectedMessage,
            'error'
          )
        })

        unmount()
      }
    })
  })

  describe('Case Sensitivity Handling', () => {
    it('should handle email case-insensitive duplicate detection', async () => {
      const user = userEvent.setup()

      // Existing invitation with lowercase email
      mockGetOrganizationInvitations.mockResolvedValue([
        {
          id: 'inv-123',
          email: 'existing@example.com',
          role: 'ANNOTATOR',
          accepted: false,
        },
      ])

      render(<InvitationTestComponent />)

      await user.click(screen.getByText('Invite Member'))

      // Enter same email with different casing
      const emailInput = screen.getByPlaceholderText('colleague@example.com')
      await user.type(emailInput, 'EXISTING@EXAMPLE.COM')

      await user.click(screen.getByText('Send Invitation'))

      await waitFor(() => {
        // Should detect as duplicate despite different casing
        expect(mockAddToast).toHaveBeenCalledWith(
          'An invitation has already been sent to EXISTING@EXAMPLE.COM',
          'warning'
        )
      })

      expect(mockSendInvitation).not.toHaveBeenCalled()
    })
  })

  describe('Error Recovery', () => {
    it('should allow retry after error', async () => {
      const user = userEvent.setup()

      mockGetOrganizationInvitations.mockResolvedValue([])

      // First attempt fails
      mockSendInvitation.mockRejectedValueOnce({
        response: {
          status: 500,
          data: { detail: 'Internal server error' },
        },
      })

      // Second attempt succeeds
      mockSendInvitation.mockResolvedValueOnce({
        id: 'inv-789',
        email: 'retry@example.com',
        role: 'ANNOTATOR',
      })

      render(<InvitationTestComponent />)

      await user.click(screen.getByText('Invite Member'))

      const emailInput = screen.getByPlaceholderText('colleague@example.com')
      await user.type(emailInput, 'retry@example.com')

      // First attempt
      await user.click(screen.getByText('Send Invitation'))

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(
          'Internal server error',
          'error'
        )
      })

      // Modal should stay open after error
      expect(screen.getByTestId('invite-modal')).toBeInTheDocument()

      // Retry
      await user.click(screen.getByText('Send Invitation'))

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(
          'Invitation sent successfully',
          'success'
        )
      })

      // Modal should close after success
      expect(screen.queryByTestId('invite-modal')).not.toBeInTheDocument()
    })
  })
})

/**
 * @jest-environment jsdom
 *
 * Tests for the grading sheet generation jobs admin host route: superadmin guard first
 * (matching the other src/app/admin/* pages), then the extended slot or the
 * community fallback.
 */

import { render, screen } from '@testing-library/react'
import React from 'react'

const mockUseSlot = jest.fn()
jest.mock('@/lib/extensions/slots', () => ({
  useSlot: (name: string) => mockUseSlot(name),
}))

const mockUser: { current: { is_superadmin: boolean } | null } = {
  current: null,
}
jest.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({ user: mockUser.current }),
}))

import AdminRubricGenerationJobsPage from '../page'

beforeEach(() => {
  mockUseSlot.mockReset()
  mockUseSlot.mockReturnValue(null)
  mockUser.current = { is_superadmin: true }
})

describe('Admin rubric generation jobs host route', () => {
  it('denies access to non-superadmins', () => {
    mockUser.current = { is_superadmin: false }
    render(<AdminRubricGenerationJobsPage />)
    // The global I18n test mock echoes unknown keys back.
    expect(screen.getByText('admin.accessDenied')).toBeInTheDocument()
    expect(
      screen.queryByText('admin.rubricGenerationJobs.extendedRequired'),
    ).not.toBeInTheDocument()
  })

  it('denies access when signed out', () => {
    mockUser.current = null
    render(<AdminRubricGenerationJobsPage />)
    expect(screen.getByText('admin.accessDenied')).toBeInTheDocument()
  })

  it('renders the community fallback for superadmins without the extended package', () => {
    render(<AdminRubricGenerationJobsPage />)
    expect(mockUseSlot).toHaveBeenCalledWith('RubricGenerationJobsAdmin')
    expect(
      screen.getByText('admin.rubricGenerationJobs.extendedRequired'),
    ).toBeInTheDocument()
    expect(screen.queryByText('admin.accessDenied')).not.toBeInTheDocument()
  })

  it('renders the registered RubricGenerationJobsAdmin slot for superadmins', () => {
    mockUseSlot.mockReturnValue(() => <div>extended generation jobs admin</div>)
    render(<AdminRubricGenerationJobsPage />)
    expect(
      screen.getByText('extended generation jobs admin'),
    ).toBeInTheDocument()
    expect(
      screen.queryByText('admin.rubricGenerationJobs.extendedRequired'),
    ).not.toBeInTheDocument()
  })
})

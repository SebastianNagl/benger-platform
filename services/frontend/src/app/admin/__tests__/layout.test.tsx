/**
 * @jest-environment jsdom
 */

import { render, screen } from '@testing-library/react'
import AdminLayout from '../layout'

describe('AdminLayout', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('renders children correctly', () => {
    const testContent = 'Test admin content'

    render(
      <AdminLayout>
        <div>{testContent}</div>
      </AdminLayout>
    )

    // Verify content is rendered
    expect(screen.getByText(testContent)).toBeInTheDocument()
  })

  it('passes through ReactNode children correctly', () => {
    const ComplexChild = () => (
      <div>
        <h1>Admin Page</h1>
        <button>Action Button</button>
        <span>Status: Active</span>
      </div>
    )

    render(
      <AdminLayout>
        <ComplexChild />
      </AdminLayout>
    )

    // Verify all child elements are rendered
    expect(screen.getByText('Admin Page')).toBeInTheDocument()
    expect(screen.getByText('Action Button')).toBeInTheDocument()
    expect(screen.getByText('Status: Active')).toBeInTheDocument()
  })

  it('handles multiple children correctly', () => {
    render(
      <AdminLayout>
        <div>First child</div>
        <div>Second child</div>
        <span>Third child</span>
      </AdminLayout>
    )

    // Verify all children are rendered
    expect(screen.getByText('First child')).toBeInTheDocument()
    expect(screen.getByText('Second child')).toBeInTheDocument()
    expect(screen.getByText('Third child')).toBeInTheDocument()
  })

  it('maintains the same API as other layout components', () => {
    // This test ensures our admin layout follows the same pattern as other layouts
    const props = {
      children: <div>Test content</div>,
    }

    render(<AdminLayout {...props} />)

    // Verify content is rendered
    expect(screen.getByText('Test content')).toBeInTheDocument()
  })
})

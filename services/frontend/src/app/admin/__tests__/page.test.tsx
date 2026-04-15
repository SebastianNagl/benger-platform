/**
 * Test for admin page redirect
 */

jest.mock('next/navigation', () => ({
  redirect: jest.fn(),
}))

import { redirect } from 'next/navigation'
import AdminPage from '../page'

describe('AdminPage', () => {
  it('should redirect to home page', () => {
    try {
      AdminPage()
    } catch {
      // redirect throws in Next.js
    }
    expect(redirect).toHaveBeenCalledWith('/')
  })
})

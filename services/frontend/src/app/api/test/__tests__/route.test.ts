/**
 * Test for the test API route
 */

import { GET } from '../route'

describe('GET /api/test', () => {
  it('should return a JSON response with message and timestamp', async () => {
    const response = await GET()
    const data = await response.json()

    expect(data.message).toBe('Frontend API route is working!')
    expect(data.timestamp).toBeDefined()
  })
})

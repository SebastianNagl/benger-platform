import apiClient from '@/lib/api'
import { sharesAPI } from '../shares'

jest.mock('@/lib/api', () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn(), put: jest.fn(), delete: jest.fn() },
}))

const client = apiClient as unknown as Record<'get' | 'post' | 'put' | 'delete', jest.Mock>

beforeEach(() => {
  Object.values(client).forEach((m) => m.mockReset())
})

describe('sharesAPI', () => {
  it('listShares reads the share list (array or {items})', async () => {
    client.get.mockResolvedValueOnce([{ id: 's1' }])
    expect(await sharesAPI.listShares('p1')).toEqual([{ id: 's1' }])
    expect(client.get).toHaveBeenCalledWith('/projects/p1/shares')
    client.get.mockResolvedValueOnce({ items: [{ id: 's2' }] })
    expect(await sharesAPI.listShares('p1')).toEqual([{ id: 's2' }])
    client.get.mockResolvedValueOnce(null)
    expect(await sharesAPI.listShares('p1')).toEqual([])
  })

  it('createShare posts the body and returns the link', async () => {
    client.post.mockResolvedValueOnce({ id: 's1', token: 't' })
    const out = await sharesAPI.createShare('p1', { password: 'pw1234', is_listed: true })
    expect(client.post).toHaveBeenCalledWith('/projects/p1/shares', {
      password: 'pw1234',
      is_listed: true,
    })
    expect(out).toEqual({ id: 's1', token: 't' })
  })

  it('updateShare PUTs partial fields to the share id (token preserved server-side)', async () => {
    client.put.mockResolvedValueOnce({ id: 's1', token: 'same' })
    await sharesAPI.updateShare('p1', 's1', { password: 'neu1234' })
    expect(client.put).toHaveBeenCalledWith('/projects/p1/shares/s1', { password: 'neu1234' })
    await sharesAPI.updateShare('p1', 's1', { is_listed: false, max_uses: 5 })
    expect(client.put).toHaveBeenLastCalledWith('/projects/p1/shares/s1', {
      is_listed: false,
      max_uses: 5,
    })
  })

  it('revokeShare deletes the share', async () => {
    await sharesAPI.revokeShare('p1', 's1')
    expect(client.delete).toHaveBeenCalledWith('/projects/p1/shares/s1')
  })

  it('getRoster normalizes the bare list the backend returns', async () => {
    client.get.mockResolvedValueOnce([{ user_id: 'u1', attempts: 2 }])
    expect(await sharesAPI.getRoster('p1')).toEqual([{ user_id: 'u1', attempts: 2 }])
    expect(client.get).toHaveBeenCalledWith('/projects/p1/shares/roster')
  })

  it('evictMember deletes the roster entry', async () => {
    await sharesAPI.evictMember('p1', 'u1')
    expect(client.delete).toHaveBeenCalledWith('/projects/p1/shares/roster/u1')
  })
})

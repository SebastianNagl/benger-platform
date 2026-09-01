/**
 * OrganizationsClient — organization-group methods (org → group → user layer).
 * Covers: getGroups, createGroup, updateGroup, deleteGroup, getGroupMembers,
 *         addGroupMember, updateGroupMember, removeGroupMember, and the
 *         group_id scope threading on the org api-key methods.
 */

const calls: Array<{ method: string; endpoint: string; data?: any }> = []

jest.mock('../base', () => ({
  BaseApiClient: class MockBaseApiClient {
    protected async get(endpoint: string): Promise<any> {
      calls.push({ method: 'GET', endpoint })
      return []
    }

    protected async post(endpoint: string, data?: any): Promise<any> {
      calls.push({ method: 'POST', endpoint, data })
      return {}
    }

    protected async put(endpoint: string, data?: any): Promise<any> {
      calls.push({ method: 'PUT', endpoint, data })
      return {}
    }

    protected async patch(endpoint: string, data?: any): Promise<any> {
      calls.push({ method: 'PATCH', endpoint, data })
      return {}
    }

    protected async delete(endpoint: string): Promise<any> {
      calls.push({ method: 'DELETE', endpoint })
      return {}
    }
  },
}))

import { OrganizationsClient } from '../organizations'

describe('OrganizationsClient — groups', () => {
  const client = new OrganizationsClient()

  beforeEach(() => {
    calls.length = 0
  })

  it('getGroups GETs the org group list', async () => {
    await client.getGroups('org-1')
    expect(calls[0]).toEqual({
      method: 'GET',
      endpoint: '/organizations/org-1/groups',
    })
  })

  it('createGroup POSTs name + description', async () => {
    await client.createGroup('org-1', { name: 'LS A', description: 'Chair' })
    expect(calls[0]).toEqual({
      method: 'POST',
      endpoint: '/organizations/org-1/groups',
      data: { name: 'LS A', description: 'Chair' },
    })
  })

  it('updateGroup PATCHes the partial payload', async () => {
    await client.updateGroup('org-1', 'grp-1', { is_active: false })
    expect(calls[0]).toEqual({
      method: 'PATCH',
      endpoint: '/organizations/org-1/groups/grp-1',
      data: { is_active: false },
    })
  })

  it('deleteGroup DELETEs the group', async () => {
    await client.deleteGroup('org-1', 'grp-1')
    expect(calls[0]).toEqual({
      method: 'DELETE',
      endpoint: '/organizations/org-1/groups/grp-1',
    })
  })

  it('getGroupMembers GETs the member list', async () => {
    await client.getGroupMembers('org-1', 'grp-1')
    expect(calls[0]).toEqual({
      method: 'GET',
      endpoint: '/organizations/org-1/groups/grp-1/members',
    })
  })

  it('addGroupMember POSTs user + admin flag', async () => {
    await client.addGroupMember('org-1', 'grp-1', {
      user_id: 'u-9',
      is_group_admin: true,
    })
    expect(calls[0]).toEqual({
      method: 'POST',
      endpoint: '/organizations/org-1/groups/grp-1/members',
      data: { user_id: 'u-9', is_group_admin: true },
    })
  })

  it('updateGroupMember PATCHes the admin flag', async () => {
    await client.updateGroupMember('org-1', 'grp-1', 'u-9', {
      is_group_admin: false,
    })
    expect(calls[0]).toEqual({
      method: 'PATCH',
      endpoint: '/organizations/org-1/groups/grp-1/members/u-9',
      data: { is_group_admin: false },
    })
  })

  it('removeGroupMember DELETEs the membership', async () => {
    await client.removeGroupMember('org-1', 'grp-1', 'u-9')
    expect(calls[0]).toEqual({
      method: 'DELETE',
      endpoint: '/organizations/org-1/groups/grp-1/members/u-9',
    })
  })

  describe('org api-key scope threading', () => {
    it('appends ?group_id= when a scope is given and omits it org-wide', async () => {
      await client.getOrgApiKeyStatus('org-1')
      await client.getOrgApiKeyStatus('org-1', 'grp-1')
      expect(calls[0].endpoint).toBe('/organizations/org-1/api-keys/status')
      expect(calls[1].endpoint).toBe(
        '/organizations/org-1/api-keys/status?group_id=grp-1'
      )
    })

    it('threads the scope through set / remove / test / test-saved', async () => {
      await client.setOrgApiKey('org-1', 'openai', 'sk-x', 'grp-1')
      await client.removeOrgApiKey('org-1', 'openai', 'grp-1')
      await client.testOrgApiKey('org-1', 'openai', 'sk-x', 'grp-1')
      await client.testSavedOrgApiKey('org-1', 'openai', 'grp-1')
      expect(calls.map((c) => c.endpoint)).toEqual([
        '/organizations/org-1/api-keys/openai?group_id=grp-1',
        '/organizations/org-1/api-keys/openai?group_id=grp-1',
        '/organizations/org-1/api-keys/openai/test?group_id=grp-1',
        '/organizations/org-1/api-keys/openai/test-saved?group_id=grp-1',
      ])
    })

    it('keeps the legacy call shapes when no scope is given', async () => {
      await client.setOrgApiKey('org-1', 'openai', 'sk-x')
      await client.removeOrgApiKey('org-1', 'openai')
      expect(calls.map((c) => c.endpoint)).toEqual([
        '/organizations/org-1/api-keys/openai',
        '/organizations/org-1/api-keys/openai',
      ])
    })
  })
})

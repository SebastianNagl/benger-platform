/**
 * Tests for OrganizationsClient — org S3 storage connection methods
 * (cloud imports): listStorageConnections, createStorageConnection,
 * updateStorageConnection, deleteStorageConnection, testStorageConnection,
 * testSavedStorageConnection, listStorageConnectionObjects.
 */

import { OrganizationsClient } from '../organizations'

const mockCalls: Array<{ method: string; endpoint: string; data?: any }> = []
let mockNextResponse: any = {}

// Mock BaseApiClient (records every request; same pattern as the sibling suites)
jest.mock('../base', () => ({
  BaseApiClient: class MockBaseApiClient {
    protected async get(endpoint: string): Promise<any> {
      mockCalls.push({ method: 'GET', endpoint })
      return mockNextResponse
    }

    protected async post(endpoint: string, data?: any): Promise<any> {
      mockCalls.push({ method: 'POST', endpoint, data })
      return mockNextResponse
    }

    protected async put(endpoint: string, data?: any): Promise<any> {
      mockCalls.push({ method: 'PUT', endpoint, data })
      return mockNextResponse
    }

    protected async delete(endpoint: string): Promise<any> {
      mockCalls.push({ method: 'DELETE', endpoint })
      return mockNextResponse
    }
  },
}))

describe('OrganizationsClient — storage connections', () => {
  let client: OrganizationsClient

  beforeEach(() => {
    client = new OrganizationsClient()
    mockCalls.length = 0
    mockNextResponse = {}
  })

  it('listStorageConnections GETs the org collection', async () => {
    mockNextResponse = [{ id: 'conn-1' }]
    const res = await client.listStorageConnections('org-1')
    expect(mockCalls).toEqual([
      { method: 'GET', endpoint: '/organizations/org-1/storage-connections' },
    ])
    expect(res).toEqual([{ id: 'conn-1' }])
  })

  it('createStorageConnection POSTs the full body', async () => {
    const body = {
      name: 'Chair bucket',
      endpoint_url: 'https://minio.example.org',
      bucket: 'law-exams',
      prefix: 'imports/',
      region: 'eu-central-1',
      use_ssl: true,
      access_key: 'AKIA123',
      secret_key: 'secret456',
    }
    await client.createStorageConnection('org-1', body)
    expect(mockCalls).toEqual([
      {
        method: 'POST',
        endpoint: '/organizations/org-1/storage-connections',
        data: body,
      },
    ])
  })

  it('updateStorageConnection PUTs a partial body (credentials optional)', async () => {
    await client.updateStorageConnection('org-1', 'conn-1', {
      name: 'Renamed',
      endpoint_url: null,
    })
    expect(mockCalls).toEqual([
      {
        method: 'PUT',
        endpoint: '/organizations/org-1/storage-connections/conn-1',
        data: { name: 'Renamed', endpoint_url: null },
      },
    ])
  })

  it('deleteStorageConnection DELETEs the connection', async () => {
    await client.deleteStorageConnection('org-1', 'conn-1')
    expect(mockCalls).toEqual([
      {
        method: 'DELETE',
        endpoint: '/organizations/org-1/storage-connections/conn-1',
      },
    ])
  })

  it('testStorageConnection POSTs unsaved params to /test', async () => {
    const body = {
      name: 'x',
      bucket: 'b',
      access_key: 'a',
      secret_key: 's',
    }
    await client.testStorageConnection('org-1', body as any)
    expect(mockCalls).toEqual([
      {
        method: 'POST',
        endpoint: '/organizations/org-1/storage-connections/test',
        data: body,
      },
    ])
  })

  it('testSavedStorageConnection POSTs to the connection /test', async () => {
    await client.testSavedStorageConnection('org-1', 'conn-1')
    expect(mockCalls).toEqual([
      {
        method: 'POST',
        endpoint: '/organizations/org-1/storage-connections/conn-1/test',
        data: {},
      },
    ])
  })

  it('listStorageConnectionObjects passes prefix, token and max_results', async () => {
    mockNextResponse = { objects: [], prefixes: [], next_token: null }
    await client.listStorageConnectionObjects('org-1', 'conn-1', {
      prefix: 'imports/2026/',
      continuationToken: 'tok-1',
      maxResults: 50,
    })
    expect(mockCalls).toEqual([
      {
        method: 'GET',
        endpoint:
          '/organizations/org-1/storage-connections/conn-1/objects?prefix=imports%2F2026%2F&continuation_token=tok-1&max_results=50',
      },
    ])
  })

  it('listStorageConnectionObjects omits absent query params', async () => {
    mockNextResponse = { objects: [], prefixes: [], next_token: null }
    await client.listStorageConnectionObjects('org-1', 'conn-1')
    expect(mockCalls).toEqual([
      {
        method: 'GET',
        endpoint: '/organizations/org-1/storage-connections/conn-1/objects',
      },
    ])
  })

  it('listStorageConnectionObjects keeps an explicit empty prefix', async () => {
    mockNextResponse = { objects: [], prefixes: [], next_token: null }
    await client.listStorageConnectionObjects('org-1', 'conn-1', {
      prefix: '',
    })
    expect(mockCalls).toEqual([
      {
        method: 'GET',
        endpoint:
          '/organizations/org-1/storage-connections/conn-1/objects?prefix=',
      },
    ])
  })
})

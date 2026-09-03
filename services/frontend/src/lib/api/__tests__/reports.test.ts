/**
 * Tests for Report API client
 */

import { apiClient } from '@/lib/api/client'
import {
  getProjectReport,
  getReportData,
  listPublishedReports,
  publishReport,
  refreshReport,
  setReportVisibility,
  unpublishReport,
  updateProjectReport,
} from '../reports'

jest.mock('@/lib/api/client', () => ({
  apiClient: {
    get: jest.fn(),
    post: jest.fn(),
    put: jest.fn(),
    invalidateCache: jest.fn(),
  },
}))

const mockGet = apiClient.get as jest.Mock
const mockPost = apiClient.post as jest.Mock
const mockPut = apiClient.put as jest.Mock
const mockInvalidate = apiClient.invalidateCache as jest.Mock

describe('Report API', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  describe('getProjectReport', () => {
    it('should fetch report for a project and return the body', async () => {
      const mockReport = {
        id: 'r1',
        project_id: 'p1',
        is_published: true,
        is_public: false,
        content: { snapshot: null },
      }
      mockGet.mockResolvedValue(mockReport)

      const result = await getProjectReport('p1')

      expect(mockGet).toHaveBeenCalledWith('/projects/p1/report')
      expect(result).toEqual(mockReport)
    })
  })

  describe('updateProjectReport', () => {
    it('should update report content', async () => {
      const mockContent = {
        sections: {
          project_info: {
            status: 'completed' as const,
            editable: true,
            visible: true,
            title: 'Test',
            description: 'Desc',
          },
          data: {
            status: 'pending' as const,
            editable: true,
            visible: true,
            show_count: true,
          },
          annotations: {
            status: 'pending' as const,
            editable: true,
            visible: true,
            show_count: true,
            show_participants: true,
          },
          generation: {
            status: 'pending' as const,
            editable: true,
            visible: true,
            show_models: true,
            show_config: false,
          },
          evaluation: {
            status: 'pending' as const,
            editable: true,
            visible: true,
          },
        },
        metadata: {
          last_auto_update: '2025-01-01',
          sections_completed: ['project_info'],
          can_publish: false,
        },
      }
      const mockResponse = { id: 'r1', content: mockContent }
      mockPost.mockResolvedValue(mockResponse)

      const result = await updateProjectReport('p1', mockContent)

      expect(mockPost).toHaveBeenCalledWith('/projects/p1/report', {
        content: mockContent,
      })
      expect(result).toEqual(mockResponse)
    })
  })

  describe('publishReport', () => {
    it('publishes for organizations only when no option is given (no body)', async () => {
      const mockResponse = { id: 'r1', is_published: true, is_public: false }
      mockPut.mockResolvedValue(mockResponse)

      const result = await publishReport('p1')

      expect(mockPut).toHaveBeenCalledWith(
        '/projects/p1/report/publish',
        undefined
      )
      expect(result).toEqual(mockResponse)
      expect(mockInvalidate).toHaveBeenCalledWith('/reports')
    })

    it('sends is_public in the body when publishing publicly', async () => {
      mockPut.mockResolvedValue({ id: 'r1', is_published: true, is_public: true })

      await publishReport('p1', { is_public: true })

      expect(mockPut).toHaveBeenCalledWith('/projects/p1/report/publish', {
        is_public: true,
      })
    })

    it('sends is_public=false explicitly when requested', async () => {
      mockPut.mockResolvedValue({ id: 'r1', is_published: true, is_public: false })

      await publishReport('p1', { is_public: false })

      expect(mockPut).toHaveBeenCalledWith('/projects/p1/report/publish', {
        is_public: false,
      })
    })
  })

  describe('unpublishReport', () => {
    it('should unpublish a report', async () => {
      const mockResponse = { id: 'r1', is_published: false }
      mockPut.mockResolvedValue(mockResponse)

      const result = await unpublishReport('p1')

      expect(mockPut).toHaveBeenCalledWith('/projects/p1/report/unpublish')
      expect(result).toEqual(mockResponse)
      expect(mockInvalidate).toHaveBeenCalledWith('/reports')
    })
  })

  describe('setReportVisibility', () => {
    it('PUTs the visibility endpoint with is_public', async () => {
      const mockResponse = { id: 'r1', is_published: true, is_public: true }
      mockPut.mockResolvedValue(mockResponse)

      const result = await setReportVisibility('p1', { is_public: true })

      expect(mockPut).toHaveBeenCalledWith('/projects/p1/report/visibility', {
        is_public: true,
      })
      expect(result).toEqual(mockResponse)
      expect(mockInvalidate).toHaveBeenCalledWith('/reports')
    })

    it('can switch back to organizations only', async () => {
      mockPut.mockResolvedValue({ id: 'r1', is_published: true, is_public: false })

      await setReportVisibility('p1', { is_public: false })

      expect(mockPut).toHaveBeenCalledWith('/projects/p1/report/visibility', {
        is_public: false,
      })
    })
  })

  describe('refreshReport', () => {
    it('POSTs the refresh endpoint and returns the report with the new snapshot', async () => {
      const mockResponse = {
        id: 'r1',
        content: { snapshot: { generated_at: '2026-09-02T00:00:00Z' } },
      }
      mockPost.mockResolvedValue(mockResponse)

      const result = await refreshReport('p1')

      expect(mockPost).toHaveBeenCalledWith('/projects/p1/report/refresh')
      expect(result).toEqual(mockResponse)
    })
  })

  describe('listPublishedReports', () => {
    it('should list published reports (works anonymously; API filters)', async () => {
      const mockReports = [
        { id: 'r1', project_title: 'Report 1', is_public: true, visibility: 'public' },
        { id: 'r2', project_title: 'Report 2', is_public: false, visibility: 'organizations' },
      ]
      mockGet.mockResolvedValue(mockReports)

      const result = await listPublishedReports()

      expect(mockGet).toHaveBeenCalledWith('/reports')
      expect(result).toEqual(mockReports)
    })
  })

  describe('getReportData', () => {
    it('should fetch report + snapshot', async () => {
      const mockData = {
        report: { id: 'r1', is_public: true },
        snapshot: { generated_at: '2026-09-02T00:00:00Z', methods: [] },
      }
      mockGet.mockResolvedValue(mockData)

      const result = await getReportData('r1')

      expect(mockGet).toHaveBeenCalledWith('/reports/r1/data')
      expect(result).toEqual(mockData)
    })
  })
})

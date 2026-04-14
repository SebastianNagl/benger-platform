/**
 * Tests for Report API client
 */

import { apiClient } from '@/lib/api/client'
import {
  getProjectReport,
  getReportData,
  listPublishedReports,
  publishReport,
  unpublishReport,
  updateProjectReport,
} from '../reports'

jest.mock('@/lib/api/client', () => ({
  apiClient: {
    get: jest.fn(),
    post: jest.fn(),
    put: jest.fn(),
  },
}))

const mockGet = apiClient.get as jest.Mock
const mockPost = apiClient.post as jest.Mock
const mockPut = apiClient.put as jest.Mock

describe('Report API', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  describe('getProjectReport', () => {
    it('should fetch report for a project', async () => {
      const mockReport = { id: 'r1', project_id: 'p1', is_published: true }
      mockGet.mockResolvedValue({ data: mockReport })

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
      mockPost.mockResolvedValue({ data: mockResponse })

      const result = await updateProjectReport('p1', mockContent)

      expect(mockPost).toHaveBeenCalledWith('/projects/p1/report', {
        content: mockContent,
      })
      expect(result).toEqual(mockResponse)
    })
  })

  describe('publishReport', () => {
    it('should publish a report', async () => {
      const mockResponse = { id: 'r1', is_published: true }
      mockPut.mockResolvedValue({ data: mockResponse })

      const result = await publishReport('p1')

      expect(mockPut).toHaveBeenCalledWith('/projects/p1/report/publish')
      expect(result).toEqual(mockResponse)
    })
  })

  describe('unpublishReport', () => {
    it('should unpublish a report', async () => {
      const mockResponse = { id: 'r1', is_published: false }
      mockPut.mockResolvedValue({ data: mockResponse })

      const result = await unpublishReport('p1')

      expect(mockPut).toHaveBeenCalledWith('/projects/p1/report/unpublish')
      expect(result).toEqual(mockResponse)
    })
  })

  describe('listPublishedReports', () => {
    it('should list all published reports', async () => {
      const mockReports = [
        { id: 'r1', project_title: 'Report 1' },
        { id: 'r2', project_title: 'Report 2' },
      ]
      mockGet.mockResolvedValue({ data: mockReports })

      const result = await listPublishedReports()

      expect(mockGet).toHaveBeenCalledWith('/reports')
      expect(result).toEqual(mockReports)
    })
  })

  describe('getReportData', () => {
    it('should fetch complete report data', async () => {
      const mockData = {
        report: { id: 'r1' },
        statistics: { task_count: 10 },
        participants: [],
        models: ['gpt-4'],
        evaluation_charts: {},
      }
      mockGet.mockResolvedValue(mockData)

      const result = await getReportData('r1')

      expect(mockGet).toHaveBeenCalledWith('/reports/r1/data')
      expect(result).toEqual(mockData)
    })
  })
})

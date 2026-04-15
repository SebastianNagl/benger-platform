/**
 * Mock implementation of API client
 * Issue #360: Fix frontend test mock issues
 */

// Mock all the main API methods that are commonly used in tests
export const getConsolidatedTaskData = jest.fn().mockResolvedValue({
  items: [],
  total: 0,
  page: 1,
  limit: 50,
  totalPages: 0,
})

export const getTasks = jest.fn().mockResolvedValue([])
export const getTask = jest.fn().mockResolvedValue({})
export const createTask = jest.fn().mockResolvedValue({})
export const updateTask = jest.fn().mockResolvedValue({})
export const deleteTask = jest.fn().mockResolvedValue({})

// Column preferences methods
export const getColumnPreferences = jest.fn().mockResolvedValue({})
export const saveColumnPreferences = jest.fn().mockResolvedValue({})
export const deleteColumnPreferences = jest.fn().mockResolvedValue({})

// User methods
export const getUsers = jest.fn().mockResolvedValue([])
export const updateUserRole = jest.fn().mockResolvedValue({})
export const updateUserSuperadminStatus = jest.fn().mockResolvedValue({})

// Organization methods
export const getOrganizations = jest.fn().mockResolvedValue([])
export const createOrganization = jest.fn().mockResolvedValue({})
export const updateOrganization = jest.fn().mockResolvedValue({})

// Evaluation methods
export const getEvaluations = jest.fn().mockResolvedValue([])
export const getModels = jest.fn().mockResolvedValue([])

// Annotation methods
export const getAnnotationTemplates = jest.fn().mockResolvedValue([])
export const createAnnotationTemplate = jest.fn().mockResolvedValue({})
export const getAnnotationProject = jest.fn().mockResolvedValue({})
export const createAnnotationProject = jest.fn().mockResolvedValue({})

// Auth methods
export const login = jest.fn().mockResolvedValue({})
export const logout = jest.fn().mockResolvedValue({})
export const getProfile = jest.fn().mockResolvedValue({})

// HTTP methods for backward compatibility
export const get = jest.fn().mockResolvedValue({})
export const post = jest.fn().mockResolvedValue({})
export const put = jest.fn().mockResolvedValue({})
export const patch = jest.fn().mockResolvedValue({})

// Mock API client class
class MockApiClient {
  getConsolidatedTaskData = getConsolidatedTaskData
  getTasks = getTasks
  getTask = getTask
  createTask = createTask
  updateTask = updateTask
  deleteTask = deleteTask
  getColumnPreferences = getColumnPreferences
  saveColumnPreferences = saveColumnPreferences
  deleteColumnPreferences = deleteColumnPreferences
  getUsers = getUsers
  updateUserRole = updateUserRole
  updateUserSuperadminStatus = updateUserSuperadminStatus
  getOrganizations = getOrganizations
  createOrganization = createOrganization
  updateOrganization = updateOrganization
  getEvaluations = getEvaluations
  getModels = getModels
  getAnnotationTemplates = getAnnotationTemplates
  createAnnotationTemplate = createAnnotationTemplate
  getAnnotationProject = getAnnotationProject
  createAnnotationProject = createAnnotationProject
  login = login
  logout = logout
  getProfile = getProfile
  get = get
  post = post
  put = put
  patch = patch

  setAuthFailureHandler = jest.fn()
}

// Default export for singleton usage
const mockApiClient = new MockApiClient()
export default mockApiClient

// Named export for API class
export const ApiClient = MockApiClient

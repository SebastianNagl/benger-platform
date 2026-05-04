/**
 * Main API client for BenGER
 * Composes all resource-specific clients and provides a unified interface
 * Replaces the monolithic ApiClient with a modular architecture
 */

import { configureAdminDefaultsClient } from './admin-defaults'
// import { createAnnotationApi } from './annotations' // Removed - old annotation system
import { AuthClient } from './auth'
import { BaseApiClient } from './base'
import { EvaluationsClient } from './evaluations'
import { FeatureFlagsClient } from './feature-flags'
import { InvitationsApiClient } from './invitations'
import { LeaderboardsClient } from './leaderboards'
import { NotificationsClient } from './notifications'
import { OrganizationsClient } from './organizations'
import { UsersClient } from './users'

// Re-export types explicitly to avoid webpack barrel export issues (Issue #123)
export type {
  AddPromptsResponse,
  BatchEvaluationResponse,
  DefaultConfig,
  DefaultPrompts,
  EvaluationRequest,
  EvaluationResult,
  EvaluationType,
  EvaluationUpdate,
  GenerationResponse,
  HumanEvaluationConfigCreate,
  HumanEvaluationConfigResponse,
  HumanEvaluationResultSummary,
  HumanEvaluationSetupResponse,
  Invitation,
  InvitationCreate,
  InvitationResponse,
  LLMModel,
  LLMModelResponse,
  MandatoryProfileStatus,
  NotificationResponse,
  NotificationUpdate,
  Organization,
  OrganizationCreate,
  OrganizationMember,
  OrganizationMemberUpdate,
  OrganizationResponse,
  OrganizationRole,
  OrganizationUpdate,
  ProfileConfirmationResponse,
  ProfileHistoryEntry,
  SyntheticDataGenerationHistory,
  SyntheticDataGenerationRequest,
  SyntheticDataGenerationResponse,
  Task,
  UploadedDataResponse,
  UploadResponse,
  User,
} from './types'

/**
 * Unified API client that provides access to all resource-specific clients
 * while maintaining the same interface as the old monolithic client
 */
export class ApiClient {
  // Resource-specific clients
  private authClient: AuthClient
  private usersClient: UsersClient
  private evaluationsClient: EvaluationsClient
  private organizationsClient: OrganizationsClient
  private notificationsClient: NotificationsClient
  private invitationsClient: InvitationsApiClient
  private featureFlagsClient: FeatureFlagsClient
  private leaderboardsClientInstance: LeaderboardsClient
  // public readonly annotation: ReturnType<typeof createAnnotationApi> // Removed - old annotation system

  // Expose leaderboards client
  get leaderboards(): LeaderboardsClient {
    return this.leaderboardsClientInstance
  }

  // Cache management
  clearCache = () => {
    this.authClient?.clearCache?.()
    this.usersClient?.clearCache?.()
    this.evaluationsClient?.clearCache?.()
    this.organizationsClient?.clearCache?.()
    this.notificationsClient?.clearCache?.()
    this.invitationsClient?.clearCache?.()
    this.featureFlagsClient?.clearCache?.()
    this.leaderboardsClientInstance?.clearCache?.()
  }

  // Clear cache for a specific user
  clearUserCache = (userId: string) => {
    this.authClient?.clearUserCache?.(userId)
    this.usersClient?.clearUserCache?.(userId)
    this.evaluationsClient?.clearUserCache?.(userId)
    this.organizationsClient?.clearUserCache?.(userId)
    this.notificationsClient?.clearUserCache?.(userId)
    this.invitationsClient?.clearUserCache?.(userId)
    this.featureFlagsClient?.clearUserCache?.(userId)
    this.leaderboardsClientInstance?.clearUserCache?.(userId)
  }

  // Method bindings - declare without initialization
  getAnnotationTemplates: any
  getAnnotationTemplate: any
  createAnnotationTemplate: any
  getDefaultAnnotationTemplate: any
  createAnnotationProject: any
  getAnnotationProject: any
  getAnnotationProjectByTask: any
  getAnnotationProjectStatistics: any
  assignAnnotationTask: any
  getUserAnnotationAssignments: any
  createAnnotation: any
  getAnnotation: any
  updateAnnotation: any
  submitAnnotation: any
  listAnnotations: any
  addAnnotationComment: any
  resolveAnnotationComment: any
  validateAnnotationMigration: any
  migrateAnnotationTask: any
  migrateAnnotationBatch: any
  getAnnotationMigrationStatus: any
  createAnnotationWebSocket: any

  constructor() {
    // Initialize clients in constructor to ensure proper initialization
    // Use try-catch to handle test environments where clients might not be available
    try {
      this.authClient = new AuthClient()
      this.usersClient = new UsersClient()
      this.evaluationsClient = new EvaluationsClient()
      this.organizationsClient = new OrganizationsClient()
      this.notificationsClient = new NotificationsClient()
      this.invitationsClient = new InvitationsApiClient()
      this.featureFlagsClient = new FeatureFlagsClient()
      this.leaderboardsClientInstance = new LeaderboardsClient()
    } catch (error) {
      // In test environments, clients might not initialize properly
      // Create stub objects to prevent binding errors
      const createStub = () => ({}) as any
      this.authClient = createStub()
      this.usersClient = createStub()
      this.evaluationsClient = createStub()
      this.organizationsClient = createStub()
      this.notificationsClient = createStub()
      this.invitationsClient = createStub()
      this.featureFlagsClient = createStub()
      this.leaderboardsClientInstance = createStub()
    }
    // Initialize annotation client eagerly to avoid lazy loading issues
    // this.annotation = createAnnotationApi(this) // Removed - old annotation system
    // Bind annotation methods AFTER annotation client is created
    // Removed - old annotation system
    // this.getAnnotationTemplates = this.annotation.templates.list.bind(
    //   this.annotation.templates
    // )
    // this.getAnnotationTemplate = this.annotation.templates.get.bind(
    //   this.annotation.templates
    // )
    // this.createAnnotationTemplate = this.annotation.templates.create.bind(
    //   this.annotation.templates
    // )
    // this.getDefaultAnnotationTemplate =
    //   this.annotation.templates.getDefault.bind(this.annotation.templates)
    // this.createAnnotationProject = this.annotation.projects.create.bind(
    //   this.annotation.projects
    // )
    // this.getAnnotationProject = this.annotation.projects.get.bind(
    //   this.annotation.projects
    // )
    // this.getAnnotationProjectByTask = this.annotation.projects.getByTask.bind(
    //   this.annotation.projects
    // )
    // this.getAnnotationProjectStatistics =
    //   this.annotation.projects.getStatistics.bind(this.annotation.projects)
    // this.assignAnnotationTask = this.annotation.assignments.assign.bind(
    //   this.annotation.assignments
    // )
    // this.getUserAnnotationAssignments =
    //   this.annotation.assignments.getUserAssignments.bind(
    //     this.annotation.assignments
    //   )
    // this.createAnnotation = this.annotation.annotations.create.bind(
    //   this.annotation.annotations
    // )
    // this.getAnnotation = this.annotation.annotations.get.bind(
    //   this.annotation.annotations
    // )
    // this.updateAnnotation = this.annotation.annotations.update.bind(
    //   this.annotation.annotations
    // )
    // this.submitAnnotation = this.annotation.annotations.submit.bind(
    //   this.annotation.annotations
    // )
    // this.listAnnotations = this.annotation.annotations.list.bind(
    //   this.annotation.annotations
    // )
    // this.addAnnotationComment = this.annotation.comments.add.bind(
    //   this.annotation.comments
    // )
    // this.resolveAnnotationComment = this.annotation.comments.resolve.bind(
    //   this.annotation.comments
    // )
    // this.validateAnnotationMigration = this.annotation.migration.validate.bind(
    //   this.annotation.migration
    // )
    // this.migrateAnnotationTask = this.annotation.migration.migrateTask.bind(
    //   this.annotation.migration
    // )
    // this.migrateAnnotationBatch = this.annotation.migration.migrateBatch.bind(
    //   this.annotation.migration
    // )
    // this.getAnnotationMigrationStatus =
    //   this.annotation.migration.getStatus.bind(this.annotation.migration)
    // this.createAnnotationWebSocket = this.annotation.createWebSocket.bind(
    //   this.annotation
    // )

    // Initialize all method bindings with safe binding helper
    const safeBind = (client: any, methodName: string) => {
      if (client && typeof client[methodName] === 'function') {
        return client[methodName].bind(client)
      }
      // Return a no-op function for test environments
      return () => Promise.resolve()
    }

    this.login = safeBind(this.authClient, 'login')
    this.signup = safeBind(this.authClient, 'signup')
    this.getUser = safeBind(this.authClient, 'getUser')
    this.getUserContexts = safeBind(this.authClient, 'getUserContexts')
    this.getCurrentUser = safeBind(this.authClient, 'getCurrentUser')
    this.verifyToken = safeBind(this.authClient, 'verifyToken')
    this.logout = safeBind(this.authClient, 'logout')
    this.getProfile = safeBind(this.authClient, 'getProfile')
    this.updateProfile = safeBind(this.authClient, 'updateProfile')
    this.changePassword = safeBind(this.authClient, 'changePassword')
    this.getMandatoryProfileStatus = safeBind(
      this.authClient,
      'getMandatoryProfileStatus'
    )
    this.confirmProfile = safeBind(this.authClient, 'confirmProfile')
    this.getProfileHistory = safeBind(this.authClient, 'getProfileHistory')
    this.get = safeBind(this.authClient, 'get')
    this.post = safeBind(this.authClient, 'post')
    this.put = safeBind(this.authClient, 'put')
    this.patch = safeBind(this.authClient, 'patch')
    this.delete = safeBind(this.authClient, 'delete')
    this.updateUserRole = safeBind(this.usersClient, 'updateUserRole')
    this.updateUserSuperadminStatus = safeBind(
      this.usersClient,
      'updateUserSuperadminStatus'
    )
    this.updateUserStatus = safeBind(this.usersClient, 'updateUserStatus')
    this.deleteUser = safeBind(this.usersClient, 'deleteUser')
    this.verifyUserEmail = safeBind(this.usersClient, 'verifyUserEmail')
    this.getEvaluations = safeBind(this.evaluationsClient, 'getEvaluations')
    this.getEvaluationStatus = safeBind(
      this.evaluationsClient,
      'getEvaluationStatus'
    )
    this.getGenerationStatus = safeBind(
      this.evaluationsClient,
      'getGenerationStatus'
    )
    this.getTaskGenerationStatuses = safeBind(
      this.evaluationsClient,
      'getTaskGenerationStatuses'
    )
    this.getGenerationResult = safeBind(
      this.evaluationsClient,
      'getGenerationResult'
    )
    this.getTaskEvaluation = safeBind(
      this.evaluationsClient,
      'getTaskEvaluation'
    )
    this.getModels = safeBind(this.evaluationsClient, 'getModels')
    this.getLLMModels = safeBind(this.evaluationsClient, 'getLLMModels')
    this.getLLMModel = safeBind(this.evaluationsClient, 'getLLMModel')
    this.getTaskTypes = safeBind(this.evaluationsClient, 'getTaskTypes')
    this.getTaskType = safeBind(this.evaluationsClient, 'getTaskType')
    this.getEvaluationTypes = safeBind(
      this.evaluationsClient,
      'getEvaluationTypes'
    )
    this.getEvaluationType = safeBind(
      this.evaluationsClient,
      'getEvaluationType'
    )
    // Prompt methods removed in Issue #759 - use generation_structure instead
    this.getSupportedMetrics = safeBind(
      this.evaluationsClient,
      'getSupportedMetrics'
    )
    this.uploadData = safeBind(this.evaluationsClient, 'uploadData')
    this.getUploadedData = safeBind(this.evaluationsClient, 'getUploadedData')
    this.importBulkData = safeBind(this.evaluationsClient, 'importBulkData')
    this.exportBulkData = safeBind(this.evaluationsClient, 'exportBulkData')
    this.deleteUploadedData = safeBind(
      this.evaluationsClient,
      'deleteUploadedData'
    )
    this.importUniversalTemplate = safeBind(
      this.evaluationsClient,
      'importUniversalTemplate'
    )
    this.getProjects = safeBind(this.evaluationsClient, 'getProjects')
    this.getProject = safeBind(this.evaluationsClient, 'getProject')
    this.getProjectTasks = safeBind(this.evaluationsClient, 'getProjectTasks')
    this.getTaskCompletionStats = safeBind(
      this.evaluationsClient,
      'getTaskCompletionStats'
    )
    this.generateSyntheticData = safeBind(
      this.evaluationsClient,
      'generateSyntheticData'
    )
    this.getSyntheticDataGenerations = safeBind(
      this.evaluationsClient,
      'getSyntheticDataGenerations'
    )
    this.getUserAnnotationForItem = safeBind(
      this.evaluationsClient,
      'getUserAnnotationForItem'
    )
    this.getTaskData = safeBind(this.evaluationsClient, 'getTaskData')
    this.getTaskResponses = safeBind(this.evaluationsClient, 'getTaskResponses')
    this.getTaskEvaluations = safeBind(
      this.evaluationsClient,
      'getTaskEvaluations'
    )
    this.getAnnotationOverview = safeBind(
      this.evaluationsClient,
      'getAnnotationOverview'
    )
    this.getTaskOrganizationMembers = safeBind(
      this.evaluationsClient,
      'getTaskOrganizationMembers'
    )
    this.getDashboardStats = safeBind(
      this.evaluationsClient,
      'getDashboardStats'
    )
    this.getUserApiKeys = safeBind(this.evaluationsClient, 'getUserApiKeys')
    this.getUserApiKeyStatus = safeBind(
      this.evaluationsClient,
      'getUserApiKeys'
    )
    this.setUserApiKey = safeBind(this.evaluationsClient, 'setUserApiKey')
    this.removeUserApiKey = safeBind(this.evaluationsClient, 'removeUserApiKey')
    this.testUserApiKey = safeBind(this.evaluationsClient, 'testUserApiKey')
    this.testSavedUserApiKey = safeBind(
      this.evaluationsClient,
      'testSavedUserApiKey'
    )
    this.getAvailableModels = safeBind(
      this.evaluationsClient,
      'getAvailableModels'
    )
    this.getOrganizations = safeBind(
      this.organizationsClient,
      'getOrganizations'
    )
    this.createOrganization = safeBind(
      this.organizationsClient,
      'createOrganization'
    )
    this.getOrganization = safeBind(this.organizationsClient, 'getOrganization')
    this.updateOrganization = safeBind(
      this.organizationsClient,
      'updateOrganization'
    )
    this.deleteOrganization = safeBind(
      this.organizationsClient,
      'deleteOrganization'
    )
    this.getOrganizationMembers = safeBind(
      this.organizationsClient,
      'getOrganizationMembers'
    )
    this.updateMemberRole = safeBind(
      this.organizationsClient,
      'updateMemberRole'
    )
    this.removeMember = safeBind(this.organizationsClient, 'removeMember')
    this.getOrganizationInvitations = safeBind(this.invitationsClient, 'list')
    this.getAllUsers = safeBind(this.organizationsClient, 'getAllUsers')
    this.updateUserGlobalRole = safeBind(
      this.organizationsClient,
      'updateUserGlobalRole'
    )
    this.addUserToOrganization = safeBind(
      this.organizationsClient,
      'addUserToOrganization'
    )
    this.getNotifications = safeBind(
      this.notificationsClient,
      'getNotifications'
    )
    this.getUnreadNotificationCount = safeBind(
      this.notificationsClient,
      'getUnreadCount'
    )
    this.markNotificationAsRead = safeBind(
      this.notificationsClient,
      'markAsRead'
    )
    this.markAllNotificationsAsRead = safeBind(
      this.notificationsClient,
      'markAllAsRead'
    )
    this.getNotificationPreferences = safeBind(
      this.notificationsClient,
      'getPreferences'
    )
    this.updateNotificationPreferences = safeBind(
      this.notificationsClient,
      'updatePreferences'
    )
    this.createNotificationStream = safeBind(
      this.notificationsClient,
      'createNotificationStream'
    )
    this.markNotificationsBulkAsRead = safeBind(
      this.notificationsClient,
      'markBulkAsRead'
    )
    this.deleteNotificationsBulk = safeBind(
      this.notificationsClient,
      'deleteBulk'
    )
    this.getNotificationGroups = safeBind(
      this.notificationsClient,
      'getNotificationGroups'
    )
    this.getNotificationSummary = safeBind(
      this.notificationsClient,
      'getNotificationSummary'
    )
    this.getInvitationByToken = safeBind(this.invitationsClient, 'getByToken')
    this.acceptInvitation = safeBind(this.invitationsClient, 'accept')
    this.createInvitation = safeBind(this.invitationsClient, 'create')
    this.cancelInvitation = safeBind(this.invitationsClient, 'cancel')
    this.convertTaskPredictions = safeBind(
      this.evaluationsClient,
      'convertTaskPredictions'
    )
    this.setupHumanEvaluation = safeBind(
      this.evaluationsClient,
      'setupHumanEvaluation'
    )
    this.getHumanEvaluationConfig = safeBind(
      this.evaluationsClient,
      'getHumanEvaluationConfig'
    )
    this.getHumanEvaluationResults = safeBind(
      this.evaluationsClient,
      'getHumanEvaluationResults'
    )
    this.syncHumanEvaluationResults = safeBind(
      this.evaluationsClient,
      'syncHumanEvaluationResults'
    )
    this.deleteHumanEvaluation = safeBind(
      this.evaluationsClient,
      'deleteHumanEvaluation'
    )

    // Evaluation methods (Phase 8: N:M Field Mapping)
    this.getAvailableEvaluationFields = safeBind(
      this.evaluationsClient,
      'getAvailableEvaluationFields'
    )
    this.runEvaluation = safeBind(
      this.evaluationsClient,
      'runEvaluation'
    )
    // Immediate evaluation: kick off + poll-until-complete (used by the
    // ImmediateEvaluationSlot wrapper after annotation submit).
    this.runImmediateEvaluation = safeBind(
      this.evaluationsClient,
      'runImmediateEvaluation'
    )
    this.pollImmediateEvaluation = safeBind(
      this.evaluationsClient,
      'pollImmediateEvaluation'
    )
    this.getEvaluationDetailResults = safeBind(
      this.evaluationsClient,
      'getEvaluationDetailResults'
    )
    // Phase 9: Project-level evaluation results
    this.getProjectEvaluationResults = safeBind(
      this.evaluationsClient,
      'getProjectEvaluationResults'
    )
    // Per-task/model results matrix
    this.getResultsByTaskModel = safeBind(
      this.evaluationsClient,
      'getResultsByTaskModel'
    )
    // Project-level aggregated per-task/model results
    this.getProjectResultsByTaskModel = safeBind(
      this.evaluationsClient,
      'getProjectResultsByTaskModel'
    )

    this.getFeatureFlags = safeBind(this.featureFlagsClient, 'getFeatureFlags')
    this.getAllFeatureFlagsForAdmin = safeBind(
      this.featureFlagsClient,
      'getAllFeatureFlagsForAdmin'
    )
    this.updateFeatureFlag = safeBind(
      this.featureFlagsClient,
      'updateFeatureFlag'
    )
    this.checkFeatureFlag = safeBind(
      this.featureFlagsClient,
      'checkFeatureFlag'
    )

    // Set up aliases
    this.uploadTaskData = this.uploadData // Alias for backward compatibility
    this.listInvitations = this.getOrganizationInvitations // Alias
  }

  // Authentication methods
  login: any
  signup: any
  getUser: any
  getUserContexts: any
  getCurrentUser: any
  verifyToken: any
  logout: any
  getProfile: any
  updateProfile: any
  changePassword: any
  getMandatoryProfileStatus: any
  confirmProfile: any
  getProfileHistory: any

  // Configuration method for organization context
  setOrganizationContextProvider(provider: () => string | null) {
    this.authClient?.setOrganizationContextProvider?.(provider)
    this.usersClient?.setOrganizationContextProvider?.(provider)
    this.evaluationsClient?.setOrganizationContextProvider?.(provider)
    this.organizationsClient?.setOrganizationContextProvider?.(provider)
    this.notificationsClient?.setOrganizationContextProvider?.(provider)
    this.invitationsClient?.setOrganizationContextProvider?.(provider)
    this.featureFlagsClient?.setOrganizationContextProvider?.(provider)
    // Configure admin-defaults client
    configureAdminDefaultsClient(undefined, provider)
    // Note: annotationApiClient doesn't need organization context as it uses the base client
  }

  // Override setAuthFailureHandler to propagate to all clients
  setAuthFailureHandler(handler: () => void) {
    this.authClient?.setAuthFailureHandler?.(handler)
    this.usersClient?.setAuthFailureHandler?.(handler)
    this.evaluationsClient?.setAuthFailureHandler?.(handler)
    this.organizationsClient?.setAuthFailureHandler?.(handler)
    this.notificationsClient?.setAuthFailureHandler?.(handler)
    this.invitationsClient?.setAuthFailureHandler?.(handler)
    this.featureFlagsClient?.setAuthFailureHandler?.(handler)
    // Configure admin-defaults client
    configureAdminDefaultsClient(handler, undefined)
    // Note: annotationApiClient doesn't need auth failure handler as it uses the base client
  }

  // HTTP convenience methods for backward compatibility and testing
  get: any
  post: any
  put: any
  patch: any
  delete: any

  // User management methods
  updateUserRole: any
  updateUserSuperadminStatus: any
  updateUserStatus: any
  deleteUser: any
  verifyUserEmail: any

  // Task methods (BenGER "Tasks" are actually projects/containers for data)
  // These are kept for backward compatibility but map to project endpoints
  createTask = async (taskData: any) => {
    // Map BenGER Task creation to project creation endpoint
    return this.evaluationsClient.post('/projects/', taskData)
  }
  updateTask = async (taskId: string, updateData: any) => {
    // Map BenGER Task update to project update endpoint
    return this.evaluationsClient.patch(`/projects/${taskId}`, updateData)
  }

  // Evaluation methods
  getEvaluations: any
  getEvaluationStatus: any
  getGenerationStatus: any
  getTaskGenerationStatuses: any
  getGenerationResult: any
  getTaskEvaluation: any
  getModels: any
  getLLMModels: any
  getLLMModel: any
  // createProjectEvaluationConfig =
  //   this.evaluationsClient.createProjectEvaluationConfig.bind(
  //     this.evaluationsClient
  //   )
  // getProjectEvaluationConfigs =
  //   this.evaluationsClient.getProjectEvaluationConfigs.bind(
  //     this.evaluationsClient
  //   )
  // getProjectEvaluationConfig =
  //   this.evaluationsClient.getProjectEvaluationConfig.bind(
  //     this.evaluationsClient
  //   )
  // runBatchEvaluation = this.evaluationsClient.runBatchEvaluation.bind(
  //   this.evaluationsClient
  // )
  // generateResponses = this.evaluationsClient.generateResponses.bind(
  //   this.evaluationsClient
  // )
  // evaluateResponses = this.evaluationsClient.evaluateResponses.bind(
  //   this.evaluationsClient
  // )
  // deleteProjectEvaluationConfig =
  //   this.evaluationsClient.deleteProjectEvaluationConfig.bind(
  //     this.evaluationsClient
  //   )
  // createGenerationConfig = this.evaluationsClient.createGenerationConfig.bind(
  //   this.evaluationsClient
  // )
  // getGenerationConfigs = this.evaluationsClient.getGenerationConfigs.bind(
  //   this.evaluationsClient
  // )
  // generateFromConfig = this.evaluationsClient.generateFromConfig.bind(
  //   this.evaluationsClient
  // )
  // deleteGenerationConfig = this.evaluationsClient.deleteGenerationConfig.bind(
  //   this.evaluationsClient
  // )
  getTaskTypes: any
  getTaskType: any
  getEvaluationTypes: any
  getEvaluationType: any
  // Prompt methods removed in Issue #759 - use generation_structure instead
  getSupportedMetrics: any

  // Data methods
  uploadData: any
  uploadTaskData: any // Alias for backward compatibility
  getUploadedData: any
  importBulkData: any
  exportBulkData: any
  deleteUploadedData: any

  // Universal Template methods
  importUniversalTemplate: any

  getProjects: any
  getProject: any
  getProjectTasks: any
  getTaskCompletionStats: any

  // Synthetic data generation methods
  generateSyntheticData: any
  getSyntheticDataGenerations: any

  // Annotation methods
  getUserAnnotationForItem: any

  // LLM Interactions Dashboard methods
  getTaskData: any
  getTaskResponses: any
  getTaskEvaluations: any
  // getConsolidatedTaskData removed - now using project-based API

  // Annotation Overview methods
  getAnnotationOverview: any
  getTaskOrganizationMembers: any

  // Dashboard statistics
  getDashboardStats: any

  // User API Keys Management
  getUserApiKeys: any
  getUserApiKeyStatus: any
  setUserApiKey: any
  removeUserApiKey: any
  testUserApiKey: any
  testSavedUserApiKey: any
  getAvailableModels: any

  // Organization methods
  getOrganizations: any
  createOrganization: any
  getOrganization: any
  updateOrganization: any
  deleteOrganization: any
  getOrganizationMembers: any
  updateMemberRole: any
  removeMember: any
  getOrganizationInvitations: any
  getAllUsers: any
  updateUserGlobalRole: any
  addUserToOrganization: any

  // Authentication failure handling - see override method above

  // Notification methods
  getNotifications: any
  getUnreadNotificationCount: any
  markNotificationAsRead: any
  markAllNotificationsAsRead: any
  getNotificationPreferences: any
  updateNotificationPreferences: any
  createNotificationStream: any
  markNotificationsBulkAsRead: any
  deleteNotificationsBulk: any
  getNotificationGroups: any
  getNotificationSummary: any

  // Invitation methods
  getInvitationByToken: any
  acceptInvitation: any
  createInvitation: any
  listInvitations: any
  cancelInvitation: any

  convertTaskPredictions: any

  // Human Evaluation methods
  setupHumanEvaluation: any
  getHumanEvaluationConfig: any
  getHumanEvaluationResults: any
  syncHumanEvaluationResults: any
  deleteHumanEvaluation: any

  // Evaluation methods (Phase 8: N:M Field Mapping)
  getAvailableEvaluationFields: any
  runEvaluation: any
  runImmediateEvaluation: any
  pollImmediateEvaluation: any
  getEvaluationDetailResults: any
  // Phase 9: Project-level evaluation results
  getProjectEvaluationResults: any
  // Per-task/model results matrix
  getResultsByTaskModel: any
  // Project-level aggregated per-task/model results
  getProjectResultsByTaskModel: any

  // Task-related methods removed - now using project-based API

  // Feature flag methods
  getFeatureFlags: any
  getAllFeatureFlagsForAdmin: any
  updateFeatureFlag: any
  checkFeatureFlag: any

  // User and organization overrides removed - feature flags are global

  /**
   * Access to individual resource clients for more complex operations
   */
  get auth() {
    return this.authClient
  }

  // tasks getter removed - now using project-based API

  get users() {
    return this.usersClient
  }

  get evaluations() {
    return this.evaluationsClient
  }

  get organizations() {
    return this.organizationsClient
  }

  get notifications() {
    return this.notificationsClient
  }

  get invitations() {
    return this.invitationsClient
  }

  get annotations() {
    // return this.annotation // Removed - old annotation system
    return null
  }

  get featureFlags() {
    return this.featureFlagsClient
  }

  // Add generic HTTP methods for backward compatibility
  // These are needed by projects.ts and other files that expect apiClient.get(), etc.
  private httpClient = new (class extends BaseApiClient {
    // Expose the protected request method through public HTTP methods
    public async doRequest(endpoint: string, options: RequestInit = {}) {
      return this.request(endpoint, options)
    }
  })()

  // HTTP methods for generic API calls
  // NOTE: These methods are commented out as they conflict with the bound methods above (lines 231-235)
  // The bound methods from authClient already provide the same functionality
  // If you need to use these, consider renaming them to avoid conflicts

  // async get(url: string, options?: RequestInit) {
  //   return this.httpClient.doRequest(url, { ...options, method: 'GET' })
  // }

  // async post(url: string, data?: any, options?: RequestInit) {
  //   return this.httpClient.doRequest(url, {
  //     ...options,
  //     method: 'POST',
  //     headers: {
  //       'Content-Type': 'application/json',
  //       ...(options?.headers || {}),
  //     },
  //     body: data ? JSON.stringify(data) : undefined,
  //   })
  // }

  // async patch(url: string, data?: any, options?: RequestInit) {
  //   return this.httpClient.doRequest(url, {
  //     ...options,
  //     method: 'PATCH',
  //     headers: {
  //       'Content-Type': 'application/json',
  //       ...(options?.headers || {}),
  //     },
  //     body: data ? JSON.stringify(data) : undefined,
  //   })
  // }

  // async delete(url: string, options?: RequestInit) {
  //   return this.httpClient.doRequest(url, { ...options, method: 'DELETE' })
  // }
}

// Create and export a default instance
const apiClient = new ApiClient()
export default apiClient

// For backward compatibility, also export the instance as 'api'
export { apiClient as api }

// Export individual clients for direct use if needed
export {
  AuthClient,
  EvaluationsClient,
  FeatureFlagsClient,
  InvitationsApiClient,
  NotificationsClient,
  OrganizationsClient,
  UsersClient,
}

// Re-export admin-defaults functions
export * from './admin-defaults'

/**
 * Legacy function for setting authenticated API client
 * This is no longer needed with cookie-based authentication
 * @deprecated Use the new cookie-based authentication instead
 */
export function setAuthenticatedAPIClient(getToken: () => string | null) {
  // Deprecated function - use cookie-based authentication instead
  // This function is kept for backward compatibility but does nothing
}

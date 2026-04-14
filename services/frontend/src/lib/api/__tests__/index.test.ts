/**
 * Tests for main API client
 * Tests the unified API client that composes all resource-specific clients
 */

import { ApiClient } from '../index'

describe('ApiClient', () => {
  let apiClient: ApiClient

  beforeEach(() => {
    apiClient = new ApiClient()
  })

  describe('Constructor and Initialization', () => {
    it('should initialize without errors', () => {
      expect(apiClient).toBeDefined()
      expect(apiClient).toBeInstanceOf(ApiClient)
    })

    it('should initialize all resource clients', () => {
      expect(apiClient.auth).toBeDefined()
      expect(apiClient.users).toBeDefined()
      expect(apiClient.evaluations).toBeDefined()
      expect(apiClient.organizations).toBeDefined()
      expect(apiClient.notifications).toBeDefined()
      expect(apiClient.invitations).toBeDefined()
      expect(apiClient.featureFlags).toBeDefined()
    })

    it('should bind authentication methods', () => {
      expect(typeof apiClient.login).toBe('function')
      expect(typeof apiClient.signup).toBe('function')
      expect(typeof apiClient.logout).toBe('function')
      expect(typeof apiClient.getUser).toBe('function')
      expect(typeof apiClient.getCurrentUser).toBe('function')
      expect(typeof apiClient.verifyToken).toBe('function')
    })

    it('should bind user management methods', () => {
      expect(typeof apiClient.updateUserRole).toBe('function')
      expect(typeof apiClient.updateUserSuperadminStatus).toBe('function')
      expect(typeof apiClient.updateUserStatus).toBe('function')
      expect(typeof apiClient.deleteUser).toBe('function')
      expect(typeof apiClient.verifyUserEmail).toBe('function')
    })

    it('should bind evaluation methods', () => {
      expect(typeof apiClient.getEvaluations).toBe('function')
      expect(typeof apiClient.getEvaluationStatus).toBe('function')
      expect(typeof apiClient.getModels).toBe('function')
    })

    it('should bind data methods', () => {
      expect(typeof apiClient.uploadData).toBe('function')
      expect(typeof apiClient.uploadTaskData).toBe('function')
      expect(typeof apiClient.getUploadedData).toBe('function')
      expect(typeof apiClient.importBulkData).toBe('function')
      expect(typeof apiClient.exportBulkData).toBe('function')
    })

    it('should bind organization methods', () => {
      expect(typeof apiClient.getOrganizations).toBe('function')
      expect(typeof apiClient.createOrganization).toBe('function')
      expect(typeof apiClient.getOrganization).toBe('function')
      expect(typeof apiClient.updateOrganization).toBe('function')
      expect(typeof apiClient.deleteOrganization).toBe('function')
    })

    it('should bind notification methods', () => {
      expect(typeof apiClient.getNotifications).toBe('function')
      expect(typeof apiClient.getUnreadNotificationCount).toBe('function')
      expect(typeof apiClient.markNotificationAsRead).toBe('function')
      expect(typeof apiClient.markAllNotificationsAsRead).toBe('function')
    })

    it('should bind invitation methods', () => {
      expect(typeof apiClient.getInvitationByToken).toBe('function')
      expect(typeof apiClient.acceptInvitation).toBe('function')
      expect(typeof apiClient.createInvitation).toBe('function')
      expect(typeof apiClient.cancelInvitation).toBe('function')
    })

    it('should bind feature flag methods', () => {
      expect(typeof apiClient.getFeatureFlags).toBe('function')
      expect(typeof apiClient.getAllFeatureFlagsForAdmin).toBe('function')
      expect(typeof apiClient.updateFeatureFlag).toBe('function')
      expect(typeof apiClient.checkFeatureFlag).toBe('function')
    })

    it('should bind HTTP convenience methods', () => {
      expect(typeof apiClient.get).toBe('function')
      expect(typeof apiClient.post).toBe('function')
      expect(typeof apiClient.put).toBe('function')
      expect(typeof apiClient.patch).toBe('function')
      expect(typeof apiClient.delete).toBe('function')
    })
  })

  describe('Cache Management', () => {
    it('should have clearCache method', () => {
      expect(typeof apiClient.clearCache).toBe('function')
    })

    it('should have clearUserCache method', () => {
      expect(typeof apiClient.clearUserCache).toBe('function')
    })

    it('should call clearCache without errors', () => {
      expect(() => apiClient.clearCache()).not.toThrow()
    })

    it('should call clearUserCache without errors', () => {
      expect(() => apiClient.clearUserCache('user-123')).not.toThrow()
    })
  })

  describe('Configuration Methods', () => {
    it('should have setOrganizationContextProvider method', () => {
      expect(typeof apiClient.setOrganizationContextProvider).toBe('function')
    })

    it('should have setAuthFailureHandler method', () => {
      expect(typeof apiClient.setAuthFailureHandler).toBe('function')
    })
  })

  describe('Task Methods (Backward Compatibility)', () => {
    it('should have createTask method', () => {
      expect(typeof apiClient.createTask).toBe('function')
    })

    it('should have updateTask method', () => {
      expect(typeof apiClient.updateTask).toBe('function')
    })
  })

  describe('Project Methods', () => {
    it('should bind project-related methods', () => {
      expect(typeof apiClient.getProjects).toBe('function')
      expect(typeof apiClient.getProject).toBe('function')
      expect(typeof apiClient.getProjectTasks).toBe('function')
      expect(typeof apiClient.getTaskCompletionStats).toBe('function')
    })
  })

  describe('LLM Methods', () => {
    it('should bind LLM model methods', () => {
      expect(typeof apiClient.getLLMModels).toBe('function')
      expect(typeof apiClient.getLLMModel).toBe('function')
      expect(typeof apiClient.getAvailableModels).toBe('function')
    })

    it('should bind task type methods', () => {
      expect(typeof apiClient.getTaskTypes).toBe('function')
      expect(typeof apiClient.getTaskType).toBe('function')
    })

    it('should bind evaluation type methods', () => {
      expect(typeof apiClient.getEvaluationTypes).toBe('function')
      expect(typeof apiClient.getEvaluationType).toBe('function')
    })
  })

  describe('Synthetic Data Generation', () => {
    it('should bind synthetic data methods', () => {
      expect(typeof apiClient.generateSyntheticData).toBe('function')
      expect(typeof apiClient.getSyntheticDataGenerations).toBe('function')
    })
  })

  describe('Human Evaluation Methods', () => {
    it('should bind human evaluation methods', () => {
      expect(typeof apiClient.setupHumanEvaluation).toBe('function')
      expect(typeof apiClient.getHumanEvaluationConfig).toBe('function')
      expect(typeof apiClient.getHumanEvaluationResults).toBe('function')
      expect(typeof apiClient.syncHumanEvaluationResults).toBe('function')
      expect(typeof apiClient.deleteHumanEvaluation).toBe('function')
    })
  })

  describe('API Key Management', () => {
    it('should bind API key methods', () => {
      expect(typeof apiClient.getUserApiKeys).toBe('function')
      expect(typeof apiClient.getUserApiKeyStatus).toBe('function')
      expect(typeof apiClient.setUserApiKey).toBe('function')
      expect(typeof apiClient.removeUserApiKey).toBe('function')
      expect(typeof apiClient.testUserApiKey).toBe('function')
      expect(typeof apiClient.testSavedUserApiKey).toBe('function')
    })
  })

  describe('Dashboard and Statistics', () => {
    it('should bind dashboard methods', () => {
      expect(typeof apiClient.getDashboardStats).toBe('function')
    })

    it('should bind task data methods', () => {
      expect(typeof apiClient.getTaskData).toBe('function')
      expect(typeof apiClient.getTaskResponses).toBe('function')
      expect(typeof apiClient.getTaskEvaluations).toBe('function')
    })

    it('should bind annotation overview methods', () => {
      expect(typeof apiClient.getAnnotationOverview).toBe('function')
      expect(typeof apiClient.getTaskOrganizationMembers).toBe('function')
    })
  })

  describe('Organization Management', () => {
    it('should bind organization member methods', () => {
      expect(typeof apiClient.getOrganizationMembers).toBe('function')
      expect(typeof apiClient.updateMemberRole).toBe('function')
      expect(typeof apiClient.removeMember).toBe('function')
      expect(typeof apiClient.addUserToOrganization).toBe('function')
    })

    it('should bind organization invitation methods', () => {
      expect(typeof apiClient.getOrganizationInvitations).toBe('function')
      expect(typeof apiClient.listInvitations).toBe('function')
    })

    it('should bind user management methods', () => {
      expect(typeof apiClient.getAllUsers).toBe('function')
      expect(typeof apiClient.updateUserGlobalRole).toBe('function')
    })
  })

  describe('Notification Management', () => {
    it('should bind notification preference methods', () => {
      expect(typeof apiClient.getNotificationPreferences).toBe('function')
      expect(typeof apiClient.updateNotificationPreferences).toBe('function')
    })

    it('should bind notification stream method', () => {
      expect(typeof apiClient.createNotificationStream).toBe('function')
    })

    it('should bind bulk notification methods', () => {
      expect(typeof apiClient.markNotificationsBulkAsRead).toBe('function')
      expect(typeof apiClient.deleteNotificationsBulk).toBe('function')
    })

    it('should bind notification grouping methods', () => {
      expect(typeof apiClient.getNotificationGroups).toBe('function')
      expect(typeof apiClient.getNotificationSummary).toBe('function')
    })
  })

  describe('Profile Management', () => {
    it('should bind profile methods', () => {
      expect(typeof apiClient.getProfile).toBe('function')
      expect(typeof apiClient.updateProfile).toBe('function')
      expect(typeof apiClient.changePassword).toBe('function')
    })
  })

  describe('Universal Template Methods', () => {
    it('should bind universal template import', () => {
      expect(typeof apiClient.importUniversalTemplate).toBe('function')
    })
  })

  describe('Metrics Methods', () => {
    it('should bind supported metrics method', () => {
      expect(typeof apiClient.getSupportedMetrics).toBe('function')
    })
  })

  describe('Data Import/Export', () => {
    it('should bind data delete method', () => {
      expect(typeof apiClient.deleteUploadedData).toBe('function')
    })

    it('should bind task prediction conversion', () => {
      expect(typeof apiClient.convertTaskPredictions).toBe('function')
    })
  })

  describe('Generation Methods', () => {
    it('should bind generation status methods', () => {
      expect(typeof apiClient.getGenerationStatus).toBe('function')
      expect(typeof apiClient.getTaskGenerationStatuses).toBe('function')
    })
  })

  describe('Annotation Methods', () => {
    it('should bind user annotation method', () => {
      expect(typeof apiClient.getUserAnnotationForItem).toBe('function')
    })

    it('should have annotations getter', () => {
      expect(apiClient.annotations).toBeDefined()
    })
  })

  describe('Backward Compatibility', () => {
    it('should have uploadTaskData as alias', () => {
      expect(apiClient.uploadTaskData).toBe(apiClient.uploadData)
    })

    it('should have listInvitations as alias', () => {
      expect(apiClient.listInvitations).toBe(
        apiClient.getOrganizationInvitations
      )
    })
  })

  describe('Error Handling in Constructor', () => {
    it('should handle initialization errors gracefully', () => {
      expect(() => new ApiClient()).not.toThrow()
    })
  })

  describe('Method Binding Safety', () => {
    it('should not throw when calling bound methods in test environment', () => {
      expect(() => apiClient.clearCache()).not.toThrow()
      expect(() => apiClient.clearUserCache('test-user')).not.toThrow()
    })
  })

  describe('Client Getters', () => {
    it('should provide access to auth client', () => {
      expect(apiClient.auth).toBeDefined()
    })

    it('should provide access to users client', () => {
      expect(apiClient.users).toBeDefined()
    })

    it('should provide access to evaluations client', () => {
      expect(apiClient.evaluations).toBeDefined()
    })

    it('should provide access to organizations client', () => {
      expect(apiClient.organizations).toBeDefined()
    })

    it('should provide access to notifications client', () => {
      expect(apiClient.notifications).toBeDefined()
    })

    it('should provide access to invitations client', () => {
      expect(apiClient.invitations).toBeDefined()
    })

    it('should provide access to featureFlags client', () => {
      expect(apiClient.featureFlags).toBeDefined()
    })
  })

  describe('Type Safety', () => {
    it('should have proper method signatures', () => {
      expect(apiClient.login).toBeDefined()
      expect(apiClient.signup).toBeDefined()
      expect(apiClient.logout).toBeDefined()
    })
  })

  describe('Integration Points', () => {
    it('should have organization context configuration method', () => {
      expect(typeof apiClient.setOrganizationContextProvider).toBe('function')
    })

    it('should have auth failure handler configuration method', () => {
      expect(typeof apiClient.setAuthFailureHandler).toBe('function')
    })
  })

  describe('Removed Annotation System', () => {
    it('should have annotations getter returning null', () => {
      expect(apiClient.annotations).toBeNull()
    })

    // Note: Annotation system methods have been removed from the API client.
    // The following properties are declared in the interface but not implemented:
    // - getAnnotationTemplates, getAnnotationTemplate, createAnnotationTemplate, etc.
    // - validateAnnotationMigration, migrateAnnotationTask, etc.
    // - createAnnotationWebSocket
    // These tests have been removed as the functionality no longer exists.
  })

  describe('Default Instance Export', () => {
    it('should export default apiClient instance', async () => {
      const { default: defaultClient } = await import('../index')
      expect(defaultClient).toBeDefined()
      expect(defaultClient).toBeInstanceOf(ApiClient)
    })

    it('should export api alias', async () => {
      const { api } = await import('../index')
      expect(api).toBeDefined()
      expect(api).toBeInstanceOf(ApiClient)
    })
  })

  describe('Client Exports', () => {
    it('should export individual client classes', async () => {
      const {
        AuthClient,
        UsersClient,
        EvaluationsClient,
        OrganizationsClient,
        NotificationsClient,
        InvitationsApiClient,
        FeatureFlagsClient,
      } = await import('../index')

      expect(AuthClient).toBeDefined()
      expect(UsersClient).toBeDefined()
      expect(EvaluationsClient).toBeDefined()
      expect(OrganizationsClient).toBeDefined()
      expect(NotificationsClient).toBeDefined()
      expect(InvitationsApiClient).toBeDefined()
      expect(FeatureFlagsClient).toBeDefined()
    })
  })

  describe('Deprecated setAuthenticatedAPIClient', () => {
    it('should export deprecated function', async () => {
      const { setAuthenticatedAPIClient } = await import('../index')
      expect(typeof setAuthenticatedAPIClient).toBe('function')
    })

    it('should not throw when called', async () => {
      const { setAuthenticatedAPIClient } = await import('../index')
      expect(() => setAuthenticatedAPIClient(() => 'token')).not.toThrow()
    })
  })
})

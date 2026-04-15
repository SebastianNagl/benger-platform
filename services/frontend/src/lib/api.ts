/**
 * @deprecated This file is deprecated in favor of the new modular API client structure.
 *
 * The old monolithic ApiClient has been refactored into smaller, resource-specific clients:
 * - AuthClient: Authentication operations
 * - TasksClient: Task management
 * - UsersClient: User management
 * - EvaluationsClient: Evaluation, model, and data operations
 *
 * Key Security Change: JWT authentication now uses HttpOnly cookies instead of localStorage
 * to prevent XSS attacks. No frontend code changes needed for authentication - cookies
 * are handled automatically.
 *
 * For new code, import from './api/index' instead:
 * import apiClient from './api' // or import { api } from './api'
 *
 * For backward compatibility, this file re-exports the new API client
 */

// Import and re-export the default instance
import apiClient from './api/index'
export default apiClient

// Re-export specific named exports for backward compatibility
export { ApiClient, api } from './api/index'
export type {
  LLMModel,
  Organization,
  OrganizationMember,
  OrganizationRole,
  SyntheticDataGenerationRequest,
  Task,
  UploadedDataResponse,
  User,
} from './api/index'

/**
 * Comprehensive tests for admin-defaults.ts
 * Tests default configuration endpoints and client setup
 */

describe('admin-defaults.ts', () => {
  // Store mock methods at describe scope
  const mockGet = jest.fn()
  const mockPost = jest.fn()
  const mockSetAuthFailureHandler = jest.fn()
  const mockSetOrganizationContextProvider = jest.fn()

  // Module references
  let configureAdminDefaultsClient: any
  let getAllDefaultConfigs: any
  let getDefaultConfig: any
  let getDefaultPrompts: any

  beforeAll(() => {
    // Setup mock before requiring module
    jest.doMock('../base', () => ({
      BaseApiClient: jest.fn(() => ({
        get: mockGet,
        post: mockPost,
        setAuthFailureHandler: mockSetAuthFailureHandler,
        setOrganizationContextProvider: mockSetOrganizationContextProvider,
      })),
    }))

    // Now require the module which will use the mocked BaseApiClient
    const adminDefaults = require('../admin-defaults')
    configureAdminDefaultsClient = adminDefaults.configureAdminDefaultsClient
    getAllDefaultConfigs = adminDefaults.getAllDefaultConfigs
    getDefaultConfig = adminDefaults.getDefaultConfig
    getDefaultPrompts = adminDefaults.getDefaultPrompts
  })

  afterAll(() => {
    jest.resetModules()
  })

  beforeEach(() => {
    jest.clearAllMocks()
  })

  describe('configureAdminDefaultsClient', () => {
    it('should configure auth failure handler', () => {
      const authHandler = jest.fn()
      configureAdminDefaultsClient(authHandler, undefined)

      expect(mockSetAuthFailureHandler).toHaveBeenCalledWith(authHandler)
    })

    it('should configure organization context provider', () => {
      const orgProvider = jest.fn(() => 'org-123')
      configureAdminDefaultsClient(undefined, orgProvider)

      expect(mockSetOrganizationContextProvider).toHaveBeenCalledWith(
        orgProvider
      )
    })

    it('should configure both handlers', () => {
      const authHandler = jest.fn()
      const orgProvider = jest.fn(() => 'org-456')
      configureAdminDefaultsClient(authHandler, orgProvider)

      expect(mockSetAuthFailureHandler).toHaveBeenCalledWith(authHandler)
      expect(mockSetOrganizationContextProvider).toHaveBeenCalledWith(
        orgProvider
      )
    })

    it('should handle undefined auth handler gracefully', () => {
      const orgProvider = jest.fn(() => 'org-789')
      configureAdminDefaultsClient(undefined, orgProvider)

      expect(mockSetAuthFailureHandler).not.toHaveBeenCalled()
      expect(mockSetOrganizationContextProvider).toHaveBeenCalledWith(
        orgProvider
      )
    })

    it('should handle undefined org provider gracefully', () => {
      const authHandler = jest.fn()
      configureAdminDefaultsClient(authHandler, undefined)

      expect(mockSetAuthFailureHandler).toHaveBeenCalledWith(authHandler)
      expect(mockSetOrganizationContextProvider).not.toHaveBeenCalled()
    })

    it('should handle both undefined gracefully', () => {
      configureAdminDefaultsClient(undefined, undefined)

      expect(mockSetAuthFailureHandler).not.toHaveBeenCalled()
      expect(mockSetOrganizationContextProvider).not.toHaveBeenCalled()
    })

    it('should allow reconfiguration', () => {
      const authHandler1 = jest.fn()
      const authHandler2 = jest.fn()

      configureAdminDefaultsClient(authHandler1, undefined)
      configureAdminDefaultsClient(authHandler2, undefined)

      expect(mockSetAuthFailureHandler).toHaveBeenCalledTimes(2)
      expect(mockSetAuthFailureHandler).toHaveBeenLastCalledWith(authHandler2)
    })
  })

  describe('getDefaultPrompts', () => {
    it('should fetch default prompts for task type', async () => {
      const mockPrompts = {
        task_type: 'classification',
        system_prompt: 'You are a classifier',
        instruction_prompt: 'Classify the following',
        evaluation_prompt: 'Evaluate the classification',
        updated_at: '2025-01-15T10:00:00Z',
        updated_by: 'admin',
      }

      mockGet.mockResolvedValue(mockPrompts)

      const result = await getDefaultPrompts('classification')

      expect(mockGet).toHaveBeenCalledWith(
        '/api/default-prompts/classification'
      )
      expect(result).toEqual(mockPrompts)
    })

    it('should fetch prompts for different task types', async () => {
      const taskTypes = ['generation', 'summarization', 'translation']

      for (const taskType of taskTypes) {
        mockGet.mockResolvedValue({
          task_type: taskType,
          system_prompt: `System prompt for ${taskType}`,
        })

        const result = await getDefaultPrompts(taskType)

        expect(mockGet).toHaveBeenCalledWith(`/api/default-prompts/${taskType}`)
        expect(result.task_type).toBe(taskType)
      }
    })

    it('should handle prompts without optional fields', async () => {
      const minimalPrompts = {
        task_type: 'classification',
      }

      mockGet.mockResolvedValue(minimalPrompts)

      const result = await getDefaultPrompts('classification')

      expect(result).toEqual(minimalPrompts)
      expect(result.system_prompt).toBeUndefined()
      expect(result.instruction_prompt).toBeUndefined()
      expect(result.evaluation_prompt).toBeUndefined()
    })

    it('should handle API errors', async () => {
      mockGet.mockRejectedValue(new Error('Not found'))

      await expect(getDefaultPrompts('nonexistent')).rejects.toThrow(
        'Not found'
      )
    })

    it('should handle network errors', async () => {
      mockGet.mockRejectedValue(new Error('Network error'))

      await expect(getDefaultPrompts('classification')).rejects.toThrow(
        'Network error'
      )
    })

    it('should handle empty task type', async () => {
      mockGet.mockResolvedValue({
        task_type: '',
      })

      const result = await getDefaultPrompts('')

      expect(mockGet).toHaveBeenCalledWith('/api/default-prompts/')
    })
  })

  describe('getDefaultConfig', () => {
    it('should fetch default config for task type', async () => {
      const mockConfig = {
        task_type: 'classification',
        temperature: 0.7,
        max_tokens: 1000,
        generation_config: {
          top_p: 0.9,
          frequency_penalty: 0.0,
        },
      }

      mockGet.mockResolvedValue(mockConfig)

      const result = await getDefaultConfig('classification')

      expect(mockGet).toHaveBeenCalledWith(
        '/api/defaults/config/classification'
      )
      expect(result).toEqual(mockConfig)
    })

    it('should fetch configs for different task types', async () => {
      const configs = [
        {
          task_type: 'generation',
          temperature: 0.8,
          max_tokens: 2000,
          generation_config: {},
        },
        {
          task_type: 'summarization',
          temperature: 0.5,
          max_tokens: 500,
          generation_config: {},
        },
      ]

      for (const config of configs) {
        mockGet.mockResolvedValue(config)

        const result = await getDefaultConfig(config.task_type)

        expect(mockGet).toHaveBeenCalledWith(
          `/api/defaults/config/${config.task_type}`
        )
        expect(result).toEqual(config)
      }
    })

    it('should handle complex generation config', async () => {
      const complexConfig = {
        task_type: 'advanced',
        temperature: 0.7,
        max_tokens: 1500,
        generation_config: {
          top_p: 0.95,
          top_k: 50,
          frequency_penalty: 0.5,
          presence_penalty: 0.5,
          stop_sequences: ['\n\n', 'END'],
          model_specific: {
            anthropic: { version: '2024-01-01' },
            openai: { organization: 'org-123' },
          },
        },
      }

      mockGet.mockResolvedValue(complexConfig)

      const result = await getDefaultConfig('advanced')

      expect(result.generation_config).toEqual(complexConfig.generation_config)
      expect(result.generation_config.model_specific).toBeDefined()
    })

    it('should handle API errors', async () => {
      mockGet.mockRejectedValue(new Error('Unauthorized'))

      await expect(getDefaultConfig('classification')).rejects.toThrow(
        'Unauthorized'
      )
    })

    it('should handle missing config', async () => {
      mockGet.mockRejectedValue(new Error('Config not found'))

      await expect(getDefaultConfig('unknown')).rejects.toThrow(
        'Config not found'
      )
    })
  })

  describe('getAllDefaultConfigs', () => {
    it('should fetch all default configs', async () => {
      const mockConfigs = {
        classification: {
          task_type: 'classification',
          temperature: 0.7,
          max_tokens: 1000,
          generation_config: {},
        },
        generation: {
          task_type: 'generation',
          temperature: 0.8,
          max_tokens: 2000,
          generation_config: {},
        },
        summarization: {
          task_type: 'summarization',
          temperature: 0.5,
          max_tokens: 500,
          generation_config: {},
        },
      }

      mockGet.mockResolvedValue(mockConfigs)

      const result = await getAllDefaultConfigs()

      expect(mockGet).toHaveBeenCalledWith('/api/defaults/config')
      expect(result).toEqual(mockConfigs)
    })

    it('should handle empty configs', async () => {
      mockGet.mockResolvedValue({})

      const result = await getAllDefaultConfigs()

      expect(result).toEqual({})
      expect(Object.keys(result)).toHaveLength(0)
    })

    it('should handle single config', async () => {
      const singleConfig = {
        classification: {
          task_type: 'classification',
          temperature: 0.7,
          max_tokens: 1000,
          generation_config: {},
        },
      }

      mockGet.mockResolvedValue(singleConfig)

      const result = await getAllDefaultConfigs()

      expect(Object.keys(result)).toHaveLength(1)
      expect(result.classification).toBeDefined()
    })

    it('should handle many configs', async () => {
      const manyConfigs: Record<string, any> = {}
      for (let i = 0; i < 10; i++) {
        manyConfigs[`task_${i}`] = {
          task_type: `task_${i}`,
          temperature: 0.7,
          max_tokens: 1000,
          generation_config: {},
        }
      }

      mockGet.mockResolvedValue(manyConfigs)

      const result = await getAllDefaultConfigs()

      expect(Object.keys(result)).toHaveLength(10)
      expect(result.task_0).toBeDefined()
      expect(result.task_9).toBeDefined()
    })

    it('should handle API errors', async () => {
      mockGet.mockRejectedValue(new Error('Server error'))

      await expect(getAllDefaultConfigs()).rejects.toThrow('Server error')
    })

    it('should preserve config structure', async () => {
      const configs = {
        test: {
          task_type: 'test',
          temperature: 0.9,
          max_tokens: 3000,
          generation_config: {
            nested: {
              deep: {
                value: 'preserved',
              },
            },
          },
        },
      }

      mockGet.mockResolvedValue(configs)

      const result = await getAllDefaultConfigs()

      expect(result.test.generation_config.nested.deep.value).toBe('preserved')
    })
  })

  describe('Type safety', () => {
    it('should enforce DefaultPrompts interface', async () => {
      const validPrompts = {
        task_type: 'test',
        system_prompt: 'system',
        instruction_prompt: 'instruction',
        evaluation_prompt: 'evaluation',
        updated_at: '2025-01-15T10:00:00Z',
        updated_by: 'admin',
      }

      mockGet.mockResolvedValue(validPrompts)

      const result = await getDefaultPrompts('test')

      expect(result).toHaveProperty('task_type')
      expect(typeof result.task_type).toBe('string')
    })

    it('should enforce DefaultConfig interface', async () => {
      const validConfig = {
        task_type: 'test',
        temperature: 0.7,
        max_tokens: 1000,
        generation_config: {},
      }

      mockGet.mockResolvedValue(validConfig)

      const result = await getDefaultConfig('test')

      expect(result).toHaveProperty('task_type')
      expect(result).toHaveProperty('temperature')
      expect(result).toHaveProperty('max_tokens')
      expect(result).toHaveProperty('generation_config')
      expect(typeof result.temperature).toBe('number')
      expect(typeof result.max_tokens).toBe('number')
    })
  })
})

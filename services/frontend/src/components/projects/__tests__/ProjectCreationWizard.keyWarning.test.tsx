/**
 * @jest-environment jsdom
 */

/**
 * ProjectCreationWizard: the missing-key warning appears where the project is
 * confirmed, and never blocks creating it.
 */

import { DEFAULT_MODEL_ID } from '@/lib/modelDefaults'
import '@testing-library/jest-dom'
import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ProjectCreationWizard } from '../ProjectCreationWizard'

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: jest.fn(), replace: jest.fn(), back: jest.fn() }),
}))

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (
      key: string,
      fallback?: string | Record<string, unknown>,
      vars?: Record<string, unknown>,
    ) => {
      const text = typeof fallback === 'string' ? fallback : key
      const values = (typeof fallback === 'string' ? vars : fallback) ?? {}
      return text.replace(/\{(\w+)\}/g, (match, name) =>
        name in values ? String(values[name]) : match,
      )
    },
  }),
}))

jest.mock('@/lib/api/projects', () => ({
  projectsAPI: { importData: jest.fn(), update: jest.fn() },
}))

jest.mock('@/lib/api/client', () => ({
  apiClient: { put: jest.fn() },
}))

const mockCreateProject = jest.fn()
jest.mock('@/stores/projectStore', () => ({
  useProjectStore: () => ({
    createProject: mockCreateProject,
    fetchProject: jest.fn(),
    loading: false,
  }),
}))

jest.mock('@/hooks/useModels', () => ({
  useModels: () => ({
    models: [],
    loading: false,
    error: null,
    refetch: jest.fn(),
    hasApiKeys: false,
    apiKeyStatus: null,
  }),
}))

jest.mock('@/components/shared/Toast', () => ({
  useToast: () => ({ addToast: jest.fn() }),
}))

// A signed-in creator outside any organization context.
jest.mock('@/contexts/AuthContext', () => ({
  useOptionalAuth: () => ({
    user: { is_superadmin: false },
    organizations: [],
    currentOrganization: null,
  }),
}))

const mockGetUserApiKeys = jest.fn()
jest.mock('@/lib/api', () => ({
  __esModule: true,
  default: {
    evaluations: {
      // A judge the config does not name runs on DEFAULT_MODEL_ID.
      getPublicModelCatalog: () =>
        Promise.resolve([
          {
            id: jest.requireActual('@/lib/modelDefaults').DEFAULT_MODEL_ID,
            name: 'GPT-5.4 Mini',
            provider: 'OpenAI',
          },
        ]),
      getUserApiKeys: (...args: unknown[]) => mockGetUserApiKeys(...args),
    },
  },
}))

jest.mock('@/lib/api/organizations', () => ({
  organizationsAPI: {
    getOrganizations: jest.fn(() => Promise.resolve([])),
    getGroups: jest.fn(() => Promise.resolve([])),
    getOrgAvailableModels: jest.fn(() => Promise.resolve([])),
    getOrgApiKeySettings: jest.fn(() =>
      Promise.resolve({ require_private_keys: true }),
    ),
  },
}))

// Name the project, switch evaluation on, pick the classic LLM judge and walk
// to the last step.
async function reachLastStepWithJudge(
  user: ReturnType<typeof userEvent.setup>,
) {
  await user.type(screen.getByTestId('project-create-name-input'), 'Klausur')
  await user.click(
    screen
      .getByTestId('wizard-feature-evaluation')
      .querySelector('input[type="checkbox"]')!,
  )
  await user.click(screen.getByTestId('project-create-next-button'))
  await user.click(
    screen
      .getByTestId('wizard-metric-llm_judge_classic')
      .querySelector('input[type="checkbox"]')!,
  )
  expect(screen.queryByTestId('wizard-key-warning')).not.toBeInTheDocument()
  await user.click(screen.getByTestId('project-create-next-button'))
}

describe('ProjectCreationWizard: missing-key warning', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockCreateProject.mockResolvedValue({ id: 'project-1' })
  })

  it('warns on the last step, and creating the project still works', async () => {
    mockGetUserApiKeys.mockResolvedValue({
      api_key_status: { openai: false },
    })
    const user = userEvent.setup()
    render(<ProjectCreationWizard />)
    await reachLastStepWithJudge(user)

    const item = await screen.findByTestId(
      'wizard-key-warning-evaluation-openai',
    )
    expect(item).toHaveTextContent(`Bewertung mit ${DEFAULT_MODEL_ID}`)

    const submit = screen.getByTestId('project-create-submit-button')
    expect(submit).toBeEnabled()
    await user.click(submit)
    expect(mockCreateProject).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'Klausur', is_private: true }),
    )
  })

  it('shows no warning when the creator holds the key', async () => {
    mockGetUserApiKeys.mockResolvedValue({ api_key_status: { openai: true } })
    const user = userEvent.setup()
    render(<ProjectCreationWizard />)
    await reachLastStepWithJudge(user)
    await act(() => new Promise<void>((resolve) => setTimeout(resolve, 0)))

    expect(mockGetUserApiKeys).toHaveBeenCalledTimes(1)
    expect(screen.getByTestId('project-create-submit-button')).toBeEnabled()
    expect(screen.queryByTestId('wizard-key-warning')).not.toBeInTheDocument()
  })
})

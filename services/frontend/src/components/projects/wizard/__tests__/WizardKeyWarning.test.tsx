/**
 * @jest-environment jsdom
 */

/**
 * WizardKeyWarning: gathers what the key-readiness rule needs and says what
 * to do. It must warn in the provable cases and stay silent otherwise,
 * including whenever a fact could not be loaded.
 */

import '@testing-library/jest-dom'
import { act, render, screen, waitFor } from '@testing-library/react'
import { INITIAL_WIZARD_DATA, type WizardData } from '../types'
import {
  parseCatalog,
  parsePersonalProviders,
  parseProviders,
  parseRequiresPrivateKeys,
  WizardKeyWarning,
} from '../WizardKeyWarning'

const mockGetPublicModelCatalog = jest.fn()
const mockGetUserApiKeys = jest.fn()
jest.mock('@/lib/api', () => ({
  __esModule: true,
  default: {
    evaluations: {
      getPublicModelCatalog: (...args: unknown[]) =>
        mockGetPublicModelCatalog(...args),
      getUserApiKeys: (...args: unknown[]) => mockGetUserApiKeys(...args),
    },
  },
}))

const mockGetOrgAvailableModels = jest.fn()
const mockGetOrgApiKeySettings = jest.fn()
jest.mock('@/lib/api/organizations', () => ({
  organizationsAPI: {
    getOrgAvailableModels: (...args: unknown[]) =>
      mockGetOrgAvailableModels(...args),
    getOrgApiKeySettings: (...args: unknown[]) =>
      mockGetOrgApiKeySettings(...args),
  },
}))

let mockAuth: unknown = null
jest.mock('@/contexts/AuthContext', () => ({
  useOptionalAuth: () => mockAuth,
}))

// The real provider interpolates {name} placeholders into the German default.
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

const CATALOG = [
  { id: 'gpt-4o', name: 'GPT-4o', provider: 'OpenAI' },
  { id: 'claude-sonnet', name: 'Claude Sonnet', provider: 'Anthropic' },
]

const NO_KEYS = {
  api_key_status: { openai: false, anthropic: false },
  available_providers: [],
}

const LMU = {
  id: 'org-lmu',
  name: 'lmu',
  display_name: 'LMU München',
  role: 'CONTRIBUTOR',
  groups: [],
}

const judgedProject = (overrides: Partial<WizardData> = {}): WizardData => ({
  ...INITIAL_WIZARD_DATA,
  title: 'Klausur',
  features: { ...INITIAL_WIZARD_DATA.features, evaluation: true },
  evaluationConfigs: [
    {
      id: 'judge',
      metric: 'llm_judge_classic',
      prediction_fields: ['__all_model__'],
      reference_fields: ['answer'],
      enabled: true,
    },
  ],
  ...overrides,
})

const generatingProject = (): WizardData => ({
  ...INITIAL_WIZARD_DATA,
  title: 'Benchmark',
  features: { ...INITIAL_WIZARD_DATA.features, llmGeneration: true },
  selectedModelIds: ['claude-sonnet'],
})

// Every answer resolves through a few promise hops; a macrotask lets all of
// them land before asserting that nothing rendered.
const settle = () =>
  act(() => new Promise<void>((resolve) => setTimeout(resolve, 0)))

// A signed-in creator without organizations, the default for every test.
const SIGNED_IN = { user: { is_superadmin: false }, organizations: [] }

beforeEach(() => {
  jest.clearAllMocks()
  mockAuth = SIGNED_IN
  mockGetPublicModelCatalog.mockResolvedValue(CATALOG)
  mockGetUserApiKeys.mockResolvedValue(NO_KEYS)
  mockGetOrgAvailableModels.mockResolvedValue([])
  mockGetOrgApiKeySettings.mockResolvedValue({ require_private_keys: false })
})

describe('WizardKeyWarning', () => {
  it('warns about a private project whose judge needs a key its creator lacks', async () => {
    render(<WizardKeyWarning data={judgedProject()} />)

    const item = await screen.findByTestId(
      'wizard-key-warning-evaluation-openai',
    )
    expect(item).toHaveTextContent('Bewertung mit gpt-4o')
    expect(item).toHaveTextContent(
      'Das Projekt gehört keiner Organisation an, daher wird mit Ihrem eigenen OpenAI-Schlüssel bewertet, und Sie haben keinen hinterlegt.',
    )
    expect(item).toHaveTextContent(
      'Wählen Sie im ersten Schritt eine Organisation mit OpenAI-Schlüssel, oder hinterlegen Sie einen eigenen Schlüssel im Profil.',
    )
    expect(
      screen.getByTestId('wizard-key-warning-profile-link'),
    ).toHaveAttribute('href', '/profile')
    expect(screen.getByTestId('wizard-key-warning')).toHaveTextContent(
      'Sie können das Projekt trotzdem erstellen.',
    )
    expect(mockGetOrgAvailableModels).not.toHaveBeenCalled()
  })

  it('stays silent when the creator holds the key', async () => {
    mockGetUserApiKeys.mockResolvedValue({
      api_key_status: { openai: true, anthropic: false },
    })
    render(<WizardKeyWarning data={judgedProject()} />)
    await settle()

    expect(mockGetUserApiKeys).toHaveBeenCalledTimes(1)
    expect(mockGetPublicModelCatalog).toHaveBeenCalledTimes(1)
    expect(screen.queryByTestId('wizard-key-warning')).not.toBeInTheDocument()
  })

  it('stays silent until the signed-in user is known', async () => {
    for (const auth of [null, { user: null, organizations: [] }]) {
      mockAuth = auth
      const { unmount } = render(<WizardKeyWarning data={judgedProject()} />)
      await settle()
      expect(screen.queryByTestId('wizard-key-warning')).not.toBeInTheDocument()
      unmount()
    }
    expect(mockGetPublicModelCatalog).not.toHaveBeenCalled()
    expect(mockGetUserApiKeys).not.toHaveBeenCalled()
  })

  it('makes no request when no feature needs a model', async () => {
    render(
      <WizardKeyWarning
        data={judgedProject({ features: INITIAL_WIZARD_DATA.features })}
      />,
    )
    await settle()

    expect(mockGetPublicModelCatalog).not.toHaveBeenCalled()
    expect(mockGetUserApiKeys).not.toHaveBeenCalled()
    expect(mockGetOrgAvailableModels).not.toHaveBeenCalled()
    expect(screen.queryByTestId('wizard-key-warning')).not.toBeInTheDocument()
  })

  it('stays silent when the organization provides the key', async () => {
    mockAuth = { user: { is_superadmin: false }, organizations: [LMU] }
    mockGetOrgAvailableModels.mockResolvedValue([
      { id: 'gpt-4o', name: 'GPT-4o', provider: 'OpenAI' },
    ])
    render(
      <WizardKeyWarning
        data={judgedProject({
          visibility: 'organization',
          organizationIds: ['org-lmu'],
        })}
      />,
    )
    await settle()

    expect(mockGetOrgAvailableModels).toHaveBeenCalledWith('org-lmu')
    expect(screen.queryByTestId('wizard-key-warning')).not.toBeInTheDocument()
  })

  it('names the organization and its private-key rule when no key is available there', async () => {
    mockAuth = { user: { is_superadmin: false }, organizations: [LMU] }
    mockGetOrgAvailableModels.mockResolvedValue([
      { id: 'claude-sonnet', name: 'Claude Sonnet', provider: 'Anthropic' },
    ])
    mockGetOrgApiKeySettings.mockResolvedValue({ require_private_keys: true })
    render(
      <WizardKeyWarning
        data={judgedProject({
          visibility: 'organization',
          organizationIds: ['org-lmu'],
        })}
      />,
    )

    const item = await screen.findByTestId(
      'wizard-key-warning-evaluation-openai',
    )
    expect(item).toHaveTextContent(
      'In LMU München steht Ihnen kein OpenAI-Schlüssel zur Verfügung.',
    )
    expect(item).toHaveTextContent(
      'Die Organisation verlangt eigene Schlüssel. Hinterlegen Sie einen OpenAI-Schlüssel im Profil.',
    )
    expect(mockGetOrgApiKeySettings).toHaveBeenCalledWith('org-lmu')
  })

  it('asks the admin when the organization pays but holds no key', async () => {
    mockAuth = { user: { is_superadmin: false }, organizations: [LMU] }
    render(
      <WizardKeyWarning
        data={judgedProject({
          visibility: 'organization',
          organizationIds: ['org-lmu'],
        })}
      />,
    )

    expect(
      await screen.findByTestId('wizard-key-warning-evaluation-openai'),
    ).toHaveTextContent(
      'Bitten Sie die Administration der Organisation, einen OpenAI-Schlüssel zu hinterlegen.',
    )
  })

  it('offers both fixes when the organization setting could not be read', async () => {
    mockAuth = { user: { is_superadmin: false }, organizations: [LMU] }
    mockGetOrgApiKeySettings.mockRejectedValue(new Error('403'))
    render(
      <WizardKeyWarning
        data={judgedProject({
          visibility: 'organization',
          organizationIds: ['org-lmu'],
        })}
      />,
    )

    expect(
      await screen.findByTestId('wizard-key-warning-evaluation-openai'),
    ).toHaveTextContent(
      'Bitten Sie die Administration der Organisation um einen OpenAI-Schlüssel, oder hinterlegen Sie einen eigenen im Profil, falls die Organisation eigene Schlüssel verlangt.',
    )
  })

  it("checks only a superadmin's real memberships, and names the organization", async () => {
    mockAuth = {
      user: { is_superadmin: true },
      organizations: [
        { id: 'org-zz', name: 'zz', display_name: 'Zett', role: null },
        {
          id: 'org-lmu',
          name: 'lmu',
          display_name: 'LMU München',
          role: 'ORG_ADMIN',
        },
      ],
    }
    render(
      <WizardKeyWarning
        data={judgedProject({
          visibility: 'organization',
          organizationIds: ['org-zz'],
        })}
      />,
    )

    expect(
      await screen.findByTestId('wizard-key-warning-evaluation-openai'),
    ).toHaveTextContent(
      'In Zett steht Ihnen kein OpenAI-Schlüssel zur Verfügung.',
    )
    expect(mockGetOrgAvailableModels).toHaveBeenCalledTimes(1)
    expect(mockGetOrgAvailableModels).toHaveBeenCalledWith('org-zz')
  })

  it('sees the key of a group the creator belongs to', async () => {
    mockAuth = {
      user: { is_superadmin: false },
      organizations: [
        {
          ...LMU,
          groups: [
            { id: 'group-lehrstuhl', name: 'Lehrstuhl', is_group_admin: false },
          ],
        },
      ],
    }
    render(
      <WizardKeyWarning
        data={judgedProject({
          visibility: 'organization',
          organizationIds: ['org-lmu'],
          organizationGroupIds: { 'org-lmu': 'group-lehrstuhl' },
        })}
      />,
    )

    expect(
      await screen.findByTestId('wizard-key-warning-evaluation-openai'),
    ).toHaveTextContent(
      'Bitten Sie die Administration der Organisation, einen OpenAI-Schlüssel zu hinterlegen.',
    )
  })

  it('shows the organization id when its name is unknown', async () => {
    mockAuth = { user: { is_superadmin: true }, organizations: [] }
    render(
      <WizardKeyWarning
        data={judgedProject({
          visibility: 'organization',
          organizationIds: ['org-zz'],
        })}
      />,
    )

    expect(
      await screen.findByTestId('wizard-key-warning-evaluation-openai'),
    ).toHaveTextContent(
      'In org-zz steht Ihnen kein OpenAI-Schlüssel zur Verfügung.',
    )
  })

  it('names the route of a creator outside every selected organization', async () => {
    mockAuth = { user: { is_superadmin: false }, organizations: [] }
    render(
      <WizardKeyWarning
        data={judgedProject({
          visibility: 'organization',
          organizationIds: ['org-other'],
        })}
      />,
    )

    const item = await screen.findByTestId(
      'wizard-key-warning-evaluation-openai',
    )
    expect(item).toHaveTextContent(
      'Sie sind in keiner der gewählten Organisationen Mitglied, daher wird mit Ihrem eigenen OpenAI-Schlüssel bewertet, und Sie haben keinen hinterlegt.',
    )
    expect(item).toHaveTextContent(
      'Wählen Sie eine Organisation, in der Sie Mitglied sind, oder hinterlegen Sie einen eigenen Schlüssel im Profil.',
    )
    expect(mockGetOrgAvailableModels).not.toHaveBeenCalled()
  })

  it('warns about a generation model that no key of the creator covers', async () => {
    mockAuth = { user: { is_superadmin: false }, organizations: [LMU] }
    mockGetOrgAvailableModels.mockResolvedValue([
      { id: 'gpt-4o', name: 'GPT-4o', provider: 'OpenAI' },
    ])
    render(<WizardKeyWarning data={generatingProject()} />)

    const item = await screen.findByTestId(
      'wizard-key-warning-generation-anthropic',
    )
    expect(item).toHaveTextContent('Generierung mit claude-sonnet')
    expect(item).toHaveTextContent(
      'Weder Ihre eigenen Schlüssel noch Ihre Organisationen stellen einen Anthropic-Schlüssel bereit.',
    )
    expect(item).toHaveTextContent(
      'Hinterlegen Sie einen eigenen Schlüssel im Profil, oder bitten Sie die Administration Ihrer Organisation um einen Anthropic-Schlüssel.',
    )
  })

  it('tells a creator without keys or organizations to add a key', async () => {
    render(<WizardKeyWarning data={generatingProject()} />)

    const item = await screen.findByTestId(
      'wizard-key-warning-generation-anthropic',
    )
    expect(item).toHaveTextContent(
      'Sie haben keinen eigenen Anthropic-Schlüssel hinterlegt und gehören keiner Organisation an.',
    )
    expect(item).toHaveTextContent(
      'Hinterlegen Sie einen eigenen Anthropic-Schlüssel im Profil.',
    )
  })

  it('stays silent when a fact cannot be loaded', async () => {
    mockGetUserApiKeys.mockRejectedValue(new Error('network down'))
    const { unmount } = render(<WizardKeyWarning data={judgedProject()} />)
    await settle()
    expect(screen.queryByTestId('wizard-key-warning')).not.toBeInTheDocument()
    unmount()

    mockGetUserApiKeys.mockResolvedValue(NO_KEYS)
    mockGetPublicModelCatalog.mockResolvedValue({ detail: 'error' })
    render(<WizardKeyWarning data={judgedProject()} />)
    await settle()
    expect(screen.queryByTestId('wizard-key-warning')).not.toBeInTheDocument()
  })

  it('drops answers that arrive after the step was left', async () => {
    let resolveCatalog: (value: unknown) => void = () => {}
    mockGetPublicModelCatalog.mockReturnValue(
      new Promise((resolve) => {
        resolveCatalog = resolve
      }),
    )
    const { unmount } = render(<WizardKeyWarning data={judgedProject()} />)
    unmount()
    await act(async () => {
      resolveCatalog(CATALOG)
      await new Promise((resolve) => setTimeout(resolve, 0))
    })
    expect(screen.queryByTestId('wizard-key-warning')).not.toBeInTheDocument()
  })

  it('asks again for an organization whose answer a new selection dropped', async () => {
    const LMU_B = { ...LMU, id: 'org-b', display_name: 'Org B' }
    mockAuth = { user: { is_superadmin: false }, organizations: [LMU, LMU_B] }
    let resolveFirst: (value: unknown) => void = () => {}
    mockGetOrgAvailableModels
      .mockReturnValueOnce(
        new Promise((resolve) => {
          resolveFirst = resolve
        }),
      )
      .mockResolvedValue([])
    const data = judgedProject({
      visibility: 'organization',
      organizationIds: ['org-lmu'],
    })
    const { rerender } = render(<WizardKeyWarning data={data} />)
    await waitFor(() =>
      expect(mockGetOrgAvailableModels).toHaveBeenCalledWith('org-lmu'),
    )

    rerender(
      <WizardKeyWarning
        data={{ ...data, organizationIds: ['org-lmu', 'org-b'] }}
      />,
    )
    await act(async () => {
      resolveFirst([{ id: 'gpt-4o', name: 'GPT-4o', provider: 'OpenAI' }])
    })

    const item = await screen.findByTestId(
      'wizard-key-warning-evaluation-openai',
    )
    expect(item).toHaveTextContent(
      'In LMU München, Org B steht Ihnen kein OpenAI-Schlüssel zur Verfügung.',
    )
    expect(
      mockGetOrgAvailableModels.mock.calls.map(([id]) => id).sort(),
    ).toEqual(['org-b', 'org-lmu', 'org-lmu'])
  })
})

describe('response parsing', () => {
  it('keeps only well-formed catalog rows', () => {
    expect(parseCatalog(null)).toBeNull()
    expect(parseCatalog({ models: [] })).toBeNull()
    expect(
      parseCatalog([
        { id: 'gpt-4o', provider: 'OpenAI', name: 'GPT-4o' },
        { id: 'broken' },
        null,
      ]),
    ).toEqual([{ id: 'gpt-4o', provider: 'OpenAI' }])
  })

  it('reads the providers the creator holds a key for', () => {
    expect(
      parsePersonalProviders({
        api_key_status: { openai: true, anthropic: false, google: 'yes' },
      }),
    ).toEqual(['openai'])
  })

  it('treats an unreadable key status as unknown', () => {
    expect(parsePersonalProviders(null)).toBeNull()
    expect(parsePersonalProviders({})).toBeNull()
    expect(parsePersonalProviders({ api_key_status: [] })).toBeNull()
    // `{}` is what the endpoint answers when it could not read the user.
    expect(parsePersonalProviders({ api_key_status: {} })).toBeNull()
  })

  it('collects each provider of an organization once', () => {
    expect(parseProviders('nope')).toBeNull()
    expect(
      parseProviders([
        { provider: 'OpenAI' },
        { provider: 'OpenAI' },
        { provider: 7 },
        null,
      ]),
    ).toEqual(['OpenAI'])
  })

  it('reads the private-key setting only when it is a boolean', () => {
    expect(parseRequiresPrivateKeys({ require_private_keys: true })).toBe(true)
    expect(parseRequiresPrivateKeys({ require_private_keys: false })).toBe(
      false,
    )
    expect(
      parseRequiresPrivateKeys({ require_private_keys: 'true' }),
    ).toBeNull()
    expect(parseRequiresPrivateKeys(null)).toBeNull()
  })
})

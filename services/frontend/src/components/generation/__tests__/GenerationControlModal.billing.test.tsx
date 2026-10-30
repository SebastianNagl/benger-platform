/**
 * @jest-environment jsdom
 *
 * "Billed to": the payer picked in the dialog travels with the generate
 * request; without a pick the request leaves the field out (default rule).
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import React from 'react'
import { GenerationControlModal } from '../GenerationControlModal'

jest.mock('@/hooks/useModels', () => {
  const stable = {
    models: [],
    loading: false,
    error: null,
    refetch: jest.fn(),
    hasApiKeys: true,
    apiKeyStatus: null,
  }
  return { useModels: jest.fn(() => stable) }
})

jest.mock('@/components/shared/Toast', () => ({
  useToast: () => ({ addToast: jest.fn() }),
}))

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({ t: (key: string) => key }),
}))

jest.mock('@/components/shared/CostEstimatePanel', () => ({
  CostEstimatePanel: () => null,
}))

jest.mock('@/lib/api/client', () => ({
  apiClient: { post: jest.fn() },
}))

const mockBilling = {
  options: [
    { id: 'org-gsj', name: 'GSJ', providers: ['OpenAI'] },
    { id: 'org-tum', name: 'TUM', providers: ['OpenAI'] },
  ],
  defaultOrganizationId: 'org-tum',
  billingOrganizationId: null as string | null,
  setBillingOrganizationId: jest.fn(),
  loading: false,
}
jest.mock('@/hooks/useBillingOrganization', () => ({
  useBillingOrganization: () => mockBilling,
}))

import { apiClient } from '@/lib/api/client'

// Every generation runs on a prompt structure; with exactly one the modal
// pre-selects it.
const STRUCTURED_PROJECT = {
  id: 'p-structured',
  generation_config: {
    prompt_structures: {
      s0: { name: 'Default', system_prompt: 'S', instruction_prompt: '$text' },
    },
  },
} as any

async function startRun() {
  const user = userEvent.setup()
  ;(apiClient.post as jest.Mock).mockResolvedValue({
    tasks_queued: 1,
    models_count: 1,
    estimated_time_seconds: 60,
  })
  render(
    <GenerationControlModal
      project={STRUCTURED_PROJECT}
      isOpen={true}
      projectId="project-1"
      onClose={jest.fn()}
      models={['gpt-x']}
    />,
  )
  expect(screen.getByTestId('billing-org-select')).toBeInTheDocument()
  await user.click(screen.getByLabelText('gpt-x'))
  await user.click(screen.getByText('generation.controlModal.startGeneration'))
  await waitFor(() => expect(apiClient.post).toHaveBeenCalled())
  return (apiClient.post as jest.Mock).mock.calls[0][1]
}

describe('GenerationControlModal billed-to choice', () => {
  beforeEach(() => {
    ;(apiClient.post as jest.Mock).mockReset()
  })

  it('sends the picked payer', async () => {
    mockBilling.billingOrganizationId = 'org-gsj'
    const body = await startRun()
    expect(body.billing_organization_id).toBe('org-gsj')
  })

  it('leaves the payer out without a pick', async () => {
    mockBilling.billingOrganizationId = null
    const body = await startRun()
    expect(body).not.toHaveProperty('billing_organization_id')
  })
})

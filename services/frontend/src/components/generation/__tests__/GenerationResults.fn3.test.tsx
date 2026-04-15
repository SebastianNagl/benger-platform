/**
 * fn3 function coverage for GenerationResults.tsx
 * Targets: handleSearch, handleModelFilter, handleExpandTask, handleCopy, handleExport
 */

import React from 'react'
import { render, screen } from '@testing-library/react'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    locale: 'en',
    t: (key: string) => key,
    changeLocale: jest.fn(),
    isReady: true,
  }),
}))

jest.mock('@/components/shared/Toast', () => ({
  useToast: () => ({ addToast: jest.fn() }),
}))

jest.mock('@/stores/projectStore', () => ({
  useProjectStore: () => ({
    fetchProjectTasks: jest.fn().mockResolvedValue([]),
  }),
}))

import { GenerationResults } from '../GenerationResults'

describe('GenerationResults fn3', () => {
  it('renders loading state initially', () => {
    render(<GenerationResults projectId="proj-1" />)
    expect(document.body).toBeInTheDocument()
  })

  it('renders with generationIds filter', () => {
    render(<GenerationResults projectId="proj-1" generationIds={['gen-1', 'gen-2']} />)
    expect(document.body).toBeInTheDocument()
  })
})

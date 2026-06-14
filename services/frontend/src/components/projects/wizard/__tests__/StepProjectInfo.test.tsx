/**
 * Behavioral tests for the StepProjectInfo wizard step.
 *
 * Covers uncovered branches: feature checkbox toggling, visibility radio
 * switching, the async organization list (loaded / empty / error), org
 * checkbox multi-select, the public-role section, and inline error display.
 *
 * @jest-environment jsdom
 */

import '@testing-library/jest-dom'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { StepProjectInfo } from '../StepProjectInfo'
import { INITIAL_WIZARD_DATA, WizardData } from '../types'

// Plain key-returning translation mock (mirrors ProjectCreationWizard.test.tsx)
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, fallback?: string) =>
      typeof fallback === 'string' ? fallback : key,
    locale: 'en',
  }),
}))

// Organization list comes from organizationsAPI.getOrganizations()
jest.mock('@/lib/api/organizations', () => ({
  organizationsAPI: {
    getOrganizations: jest.fn(),
  },
}))

import { organizationsAPI } from '@/lib/api/organizations'

const mockGetOrganizations = organizationsAPI.getOrganizations as jest.Mock

function makeData(overrides: Partial<WizardData> = {}): WizardData {
  return { ...INITIAL_WIZARD_DATA, ...overrides }
}

function renderStep(
  overrides: Partial<WizardData> = {},
  errors: Record<string, string> = {}
) {
  const onChange = jest.fn()
  const data = makeData(overrides)
  const utils = render(
    <StepProjectInfo data={data} onChange={onChange} errors={errors} />
  )
  return { onChange, data, ...utils }
}

describe('StepProjectInfo', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockGetOrganizations.mockResolvedValue([])
  })

  describe('basic fields', () => {
    it('emits title changes', () => {
      const { onChange } = renderStep()
      fireEvent.change(screen.getByTestId('project-create-name-input'), {
        target: { value: 'My Project' },
      })
      expect(onChange).toHaveBeenCalledWith({ title: 'My Project' })
    })

    it('emits description changes', () => {
      const { onChange } = renderStep()
      fireEvent.change(
        screen.getByTestId('project-create-description-textarea'),
        { target: { value: 'A description' } }
      )
      expect(onChange).toHaveBeenCalledWith({ description: 'A description' })
    })

    it('renders the inline title error when present', () => {
      renderStep({}, { title: 'Project name is required' })
      expect(screen.getByText('Project name is required')).toBeInTheDocument()
    })
  })

  describe('feature checkboxes', () => {
    it('toggles a feature on when previously off', () => {
      const { onChange } = renderStep({
        features: {
          annotation: false,
          dataImport: false,
          llmGeneration: false,
          evaluation: false,
        },
      })
      const annotationRow = screen.getByTestId('wizard-feature-annotation')
      const checkbox = annotationRow.querySelector(
        'input[type="checkbox"]'
      ) as HTMLInputElement
      expect(checkbox).not.toBeChecked()
      fireEvent.click(checkbox)
      expect(onChange).toHaveBeenCalledWith({
        features: {
          annotation: true,
          dataImport: false,
          llmGeneration: false,
          evaluation: false,
        },
      })
    })

    it('toggles a feature off when previously on', () => {
      const { onChange } = renderStep({
        features: {
          annotation: false,
          dataImport: true,
          llmGeneration: false,
          evaluation: false,
        },
      })
      const row = screen.getByTestId('wizard-feature-dataImport')
      const checkbox = row.querySelector(
        'input[type="checkbox"]'
      ) as HTMLInputElement
      expect(checkbox).toBeChecked()
      fireEvent.click(checkbox)
      expect(onChange).toHaveBeenCalledWith({
        features: {
          annotation: false,
          dataImport: false,
          llmGeneration: false,
          evaluation: false,
        },
      })
    })
  })

  describe('visibility', () => {
    it('switches visibility to organization', () => {
      const { onChange } = renderStep({ visibility: 'private' })
      fireEvent.click(screen.getByTestId('wizard-visibility-organization-radio'))
      expect(onChange).toHaveBeenCalledWith({ visibility: 'organization' })
    })

    it('switches visibility to public', () => {
      const { onChange } = renderStep({ visibility: 'private' })
      fireEvent.click(screen.getByTestId('wizard-visibility-public-radio'))
      expect(onChange).toHaveBeenCalledWith({ visibility: 'public' })
    })

    it('does not render org or public sections when private', () => {
      renderStep({ visibility: 'private' })
      expect(
        screen.queryByTestId('wizard-organization-section')
      ).not.toBeInTheDocument()
      expect(
        screen.queryByTestId('wizard-public-role-section')
      ).not.toBeInTheDocument()
      // Private visibility should not even call the orgs API
      expect(mockGetOrganizations).not.toHaveBeenCalled()
    })
  })

  describe('organization visibility section', () => {
    it('loads organizations and lets the user toggle them', async () => {
      mockGetOrganizations.mockResolvedValue([
        { id: 'org-1', name: 'Org One' },
        { id: 'org-2', name: 'Org Two' },
      ])
      const { onChange } = renderStep({
        visibility: 'organization',
        organizationIds: [],
      })

      // The org list is loaded asynchronously
      await waitFor(() =>
        expect(screen.getByTestId('wizard-organization-list')).toBeInTheDocument()
      )
      expect(screen.getByText('Org One')).toBeInTheDocument()
      expect(screen.getByText('Org Two')).toBeInTheDocument()

      fireEvent.click(screen.getByTestId('wizard-organization-org-2-checkbox'))
      expect(onChange).toHaveBeenCalledWith({ organizationIds: ['org-2'] })
    })

    it('removes an already-selected organization on toggle', async () => {
      mockGetOrganizations.mockResolvedValue([{ id: 'org-1', name: 'Org One' }])
      const { onChange } = renderStep({
        visibility: 'organization',
        organizationIds: ['org-1'],
      })

      await waitFor(() =>
        expect(screen.getByTestId('wizard-organization-list')).toBeInTheDocument()
      )
      const checkbox = screen.getByTestId(
        'wizard-organization-org-1-checkbox'
      ) as HTMLInputElement
      expect(checkbox).toBeChecked()
      fireEvent.click(checkbox)
      expect(onChange).toHaveBeenCalledWith({ organizationIds: [] })
    })

    it('shows the empty-state message when no organizations exist', async () => {
      mockGetOrganizations.mockResolvedValue([])
      renderStep({ visibility: 'organization' })

      await waitFor(() =>
        expect(screen.getByTestId('wizard-organization-section')).toBeInTheDocument()
      )
      expect(screen.getByText('No organizations available.')).toBeInTheDocument()
      expect(
        screen.queryByTestId('wizard-organization-list')
      ).not.toBeInTheDocument()
    })

    it('falls back to an empty list when the orgs request rejects', async () => {
      mockGetOrganizations.mockRejectedValue(new Error('boom'))
      renderStep({ visibility: 'organization' })

      await waitFor(() => expect(mockGetOrganizations).toHaveBeenCalled())
      // Empty-state message renders since orgs stayed []
      await waitFor(() =>
        expect(
          screen.getByText('No organizations available.')
        ).toBeInTheDocument()
      )
    })

    it('renders the organizationIds validation error', async () => {
      mockGetOrganizations.mockResolvedValue([])
      renderStep(
        { visibility: 'organization' },
        { organizationIds: 'Pick at least one organization' }
      )
      await waitFor(() =>
        expect(
          screen.getByText('Pick at least one organization')
        ).toBeInTheDocument()
      )
    })
  })

  describe('public visibility section', () => {
    it('renders the public role options and switches role', () => {
      const { onChange } = renderStep({
        visibility: 'public',
        publicRole: 'ANNOTATOR',
      })
      expect(
        screen.getByTestId('wizard-public-role-section')
      ).toBeInTheDocument()
      fireEvent.click(
        screen.getByTestId('wizard-public-role-contributor-radio')
      )
      expect(onChange).toHaveBeenCalledWith({ publicRole: 'CONTRIBUTOR' })
    })

    it('reflects the currently selected role', () => {
      renderStep({ visibility: 'public', publicRole: 'CONTRIBUTOR' })
      const contributorRadio = screen.getByTestId(
        'wizard-public-role-contributor-radio'
      ) as HTMLInputElement
      const annotatorRadio = screen.getByTestId(
        'wizard-public-role-annotator-radio'
      ) as HTMLInputElement
      expect(contributorRadio).toBeChecked()
      expect(annotatorRadio).not.toBeChecked()
    })
  })
})

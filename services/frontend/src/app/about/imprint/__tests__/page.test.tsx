/**
 * @jest-environment jsdom
 */

import { render, screen } from '@testing-library/react'
import ImprintPage from '../page'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string) => key,
  }),
}))

jest.mock('@/components/layout/LegalPageWrapper', () => ({
  LegalPageWrapper: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="legal-wrapper">{children}</div>
  ),
}))

describe('ImprintPage', () => {
  it('should render the page title', () => {
    render(<ImprintPage />)
    expect(screen.getByText('legal.imprint.title')).toBeInTheDocument()
  })

  it('should render all section headings', () => {
    render(<ImprintPage />)
    expect(screen.getByText('legal.imprint.provider')).toBeInTheDocument()
    expect(screen.getByText('legal.imprint.contact')).toBeInTheDocument()
    expect(screen.getByText('legal.imprint.representedBy')).toBeInTheDocument()
    expect(screen.getByText('legal.imprint.registration')).toBeInTheDocument()
    expect(screen.getByText('legal.imprint.vatId')).toBeInTheDocument()
    expect(screen.getByText('legal.imprint.responsibleForContent')).toBeInTheDocument()
    expect(screen.getByText('legal.imprint.disclaimer')).toBeInTheDocument()
    expect(screen.getByText('legal.imprint.dataProtection')).toBeInTheDocument()
  })

  it('should render disclaimer subsections', () => {
    render(<ImprintPage />)
    expect(screen.getByText('legal.imprint.disclaimerContent')).toBeInTheDocument()
    expect(screen.getByText('legal.imprint.linksTitle')).toBeInTheDocument()
    expect(screen.getByText('legal.imprint.copyrightTitle')).toBeInTheDocument()
  })

  it('should render section content text', () => {
    render(<ImprintPage />)
    expect(screen.getByText('legal.imprint.contactInfo')).toBeInTheDocument()
    expect(screen.getByText('legal.imprint.representedByInfo')).toBeInTheDocument()
    expect(screen.getByText('legal.imprint.registrationInfo')).toBeInTheDocument()
    expect(screen.getByText('legal.imprint.vatIdInfo')).toBeInTheDocument()
    expect(screen.getByText('legal.imprint.disclaimerText')).toBeInTheDocument()
    expect(screen.getByText('legal.imprint.linksText')).toBeInTheDocument()
    expect(screen.getByText('legal.imprint.copyrightText')).toBeInTheDocument()
    expect(screen.getByText('legal.imprint.dataProtectionText')).toBeInTheDocument()
  })

  it('should render lead paragraph', () => {
    render(<ImprintPage />)
    expect(screen.getByText('legal.imprint.lead')).toBeInTheDocument()
  })

  it('should wrap content in LegalPageWrapper', () => {
    render(<ImprintPage />)
    expect(screen.getByTestId('legal-wrapper')).toBeInTheDocument()
  })
})

/**
 * @jest-environment jsdom
 */

import { render, screen } from '@testing-library/react'
import DataProtectionPage from '../page'

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

describe('DataProtectionPage', () => {
  it('should render the page title', () => {
    render(<DataProtectionPage />)
    expect(screen.getByText('legal.dataProtection.title')).toBeInTheDocument()
  })

  it('should render all section headings', () => {
    render(<DataProtectionPage />)
    expect(screen.getByText('legal.dataProtection.overview')).toBeInTheDocument()
    expect(screen.getByText('legal.dataProtection.controller')).toBeInTheDocument()
    expect(screen.getByText('legal.dataProtection.dataProcessing')).toBeInTheDocument()
    expect(screen.getByText('legal.dataProtection.accountData')).toBeInTheDocument()
    expect(screen.getByText('legal.dataProtection.usageData')).toBeInTheDocument()
    expect(screen.getByText('legal.dataProtection.apiKeys')).toBeInTheDocument()
    expect(screen.getByText('legal.dataProtection.cookies')).toBeInTheDocument()
    expect(screen.getByText('legal.dataProtection.dataSharing')).toBeInTheDocument()
    expect(screen.getByText('legal.dataProtection.dataRetention')).toBeInTheDocument()
    expect(screen.getByText('legal.dataProtection.yourRights')).toBeInTheDocument()
    expect(screen.getByText('legal.dataProtection.security')).toBeInTheDocument()
    expect(screen.getByText('legal.dataProtection.contact')).toBeInTheDocument()
  })

  it('should render section text content', () => {
    render(<DataProtectionPage />)
    expect(screen.getByText('legal.dataProtection.overviewText')).toBeInTheDocument()
    expect(screen.getByText('legal.dataProtection.accountDataText')).toBeInTheDocument()
    expect(screen.getByText('legal.dataProtection.usageDataText')).toBeInTheDocument()
    expect(screen.getByText('legal.dataProtection.apiKeysText')).toBeInTheDocument()
    expect(screen.getByText('legal.dataProtection.cookiesText')).toBeInTheDocument()
    expect(screen.getByText('legal.dataProtection.dataSharingText')).toBeInTheDocument()
    expect(screen.getByText('legal.dataProtection.dataRetentionText')).toBeInTheDocument()
    expect(screen.getByText('legal.dataProtection.rightsText')).toBeInTheDocument()
    expect(screen.getByText('legal.dataProtection.securityText')).toBeInTheDocument()
    expect(screen.getByText('legal.dataProtection.contactText')).toBeInTheDocument()
  })

  it('should render lead paragraph', () => {
    render(<DataProtectionPage />)
    expect(screen.getByText('legal.dataProtection.lead')).toBeInTheDocument()
  })

  it('should wrap content in LegalPageWrapper', () => {
    render(<DataProtectionPage />)
    expect(screen.getByTestId('legal-wrapper')).toBeInTheDocument()
  })

  it('should format controller info with line breaks', () => {
    render(<DataProtectionPage />)
    // The formatText function splits on newlines - since mock returns key as-is,
    // it should still render the text
    expect(screen.getByText('legal.dataProtection.controllerInfo')).toBeInTheDocument()
  })
})

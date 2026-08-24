/**
 * /learning-stats — the dedicated "Meine Lernstatistik" page: renders the
 * extended `PersonalAnalyticsPage` slot when registered, and a community
 * edition notice when nothing is registered. (Replaces the former
 * DashboardPersonalSection slot on the dashboard.)
 */

import LearningStatsPage from '@/app/learning-stats/page'
import '@testing-library/jest-dom'
import { render, screen } from '@testing-library/react'
import React from 'react'
import { registerSlot } from '@/lib/extensions/slots'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    locale: 'de',
    t: (key: string, def?: any) => (typeof def === 'string' ? def : key),
    setLocale: jest.fn(),
  }),
}))

describe('Learning stats page', () => {
  afterEach(() => registerSlot('PersonalAnalyticsPage', null as any))

  it('shows the community notice without the slot', () => {
    render(<LearningStatsPage />)
    expect(screen.getByText('Meine Lernstatistik')).toBeInTheDocument()
    expect(screen.getByTestId('learning-stats-unavailable')).toBeInTheDocument()
  })

  it('renders the registered slot component', () => {
    registerSlot('PersonalAnalyticsPage', () => (
      <div data-testid="analytics-body">stats</div>
    ))
    render(<LearningStatsPage />)
    expect(screen.getByTestId('analytics-body')).toBeInTheDocument()
    expect(
      screen.queryByTestId('learning-stats-unavailable')
    ).not.toBeInTheDocument()
  })
})

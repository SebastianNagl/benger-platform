/**
 * @jest-environment jsdom
 *
 * Community-edition smoke tests for the platform student host routes
 * (Issue #35). With no extended slot registered, every route must render the
 * graceful "not available in the community edition" fallback and never crash —
 * mirroring src/app/projects/[id]/review/page.tsx.
 */

import { render, screen, waitFor } from '@testing-library/react'
import React from 'react'

// Stable param mock for the dynamic detail routes.
jest.mock('next/navigation', () => ({
  useParams: () => ({ id: 'abc-123' }),
}))

// Use the REAL i18n so the fallback copy resolves to the actual German string
// from the bundled common.json (the global stub lacks the student namespace).
jest.unmock('@/contexts/I18nContext')

import { I18nProvider } from '@/contexts/I18nContext'
import StudentDashboardPage from '../page'
import StudentExamsListPage from '../exams/page'
import StudentExamDetailPage from '../exams/[id]/page'
import StudentDecksPage from '../decks/page'
import StudentDeckDetailPage from '../decks/[id]/page'
import StudentLeaderboardPage from '../leaderboard/page'

const FALLBACK = 'Diese Funktion ist in der Community-Edition nicht verfügbar.'

const wrap = (ui: React.ReactElement) =>
  render(<I18nProvider>{ui}</I18nProvider>)

describe('student host routes (community edition fallback)', () => {
  it.each([
    ['dashboard', StudentDashboardPage],
    ['exams list', StudentExamsListPage],
    ['exam detail', StudentExamDetailPage],
    ['decks', StudentDecksPage],
    ['deck detail', StudentDeckDetailPage],
    ['leaderboard', StudentLeaderboardPage],
  ])(
    'renders the community fallback for %s without crashing',
    async (_name, Page) => {
      wrap(<Page />)
      await waitFor(() =>
        expect(screen.getByText(FALLBACK)).toBeInTheDocument()
      )
    }
  )
})

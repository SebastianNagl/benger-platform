/**
 * @jest-environment jsdom
 */
import { render } from '@testing-library/react'

jest.mock('@/styles/tailwind.css', () => ({}))

// Control the host the server component resolves ('' → benger).
let mockHost = ''
jest.mock('next/headers', () => ({
  headers: jest.fn(async () => ({
    get: (key: string) => (key === 'x-forwarded-host' ? mockHost || null : null),
  })),
}))

// Stub the two landing branches so we only assert which one is chosen.
jest.mock('../BengerLandingClient', () => ({
  __esModule: true,
  default: () => <div data-testid="benger-landing" />,
}))
jest.mock('../vertretbar/page', () => ({
  __esModule: true,
  default: () => <div data-testid="vertretbar-landing" />,
}))

import Page from '../page'

describe('app/page.tsx server-side host branching', () => {
  it('renders the benger landing on a benger host', async () => {
    mockHost = 'what-a-benger.net'
    const { getByTestId } = render(await Page())
    expect(getByTestId('benger-landing')).toBeInTheDocument()
  })

  it('renders the Vertretbar landing on a vertretbar host', async () => {
    mockHost = 'vertretbar.net'
    const { getByTestId } = render(await Page())
    expect(getByTestId('vertretbar-landing')).toBeInTheDocument()
  })

  it('renders the Vertretbar landing on staging.vertretbar.net', async () => {
    mockHost = 'staging.vertretbar.net'
    const { getByTestId } = render(await Page())
    expect(getByTestId('vertretbar-landing')).toBeInTheDocument()
  })

  it('defaults to the benger landing when the host is absent', async () => {
    mockHost = ''
    const { getByTestId } = render(await Page())
    expect(getByTestId('benger-landing')).toBeInTheDocument()
  })
})

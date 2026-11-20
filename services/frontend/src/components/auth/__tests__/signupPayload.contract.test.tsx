/**
 * @jest-environment jsdom
 *
 * Contract between the signup forms and the API's signup schema.
 *
 * Each case fills a signup form (the landing-page modal or the register
 * wizard), submits it, and captures the exact JSON body the API client
 * sends to POST /auth/signup. That body must equal the committed fixture in
 * services/shared/contracts/signup/. The API suite
 * (services/api/tests/integration/test_signup_payload_contract.py) posts the
 * same fixtures to the real endpoint and validates them against UserCreate,
 * so a form and the schema cannot drift apart unnoticed again.
 *
 * After an intended payload change, regenerate the fixtures with
 * UPDATE_SIGNUP_CONTRACT=1 npx jest signupPayload.contract
 * and let the API test confirm the new payload.
 */

import '@/test-utils/locationMock'

import RegisterPage from '@/app/register/page'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { AuthClient } from '@/lib/api/auth'
import { hasSlot, useSlot } from '@/lib/extensions/slots'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import fs from 'fs'
import { useRouter } from 'next/navigation'
import path from 'path'
import { SignupModal } from '../SignupModal'

jest.mock('@/contexts/AuthContext')
jest.mock('@/contexts/I18nContext')
jest.mock('next/navigation', () => ({ useRouter: jest.fn() }))
jest.mock('@/lib/extensions/slots', () => ({
  useSlot: jest.fn(),
  hasSlot: jest.fn(),
}))
jest.mock('@/components/layout', () => ({
  LanguageSwitcher: () => null,
  ThemeToggle: () => null,
}))
jest.mock('@headlessui/react', () => ({
  Dialog: ({ open, children }: any) =>
    open ? <div role="dialog">{children}</div> : null,
  DialogBackdrop: () => null,
  DialogPanel: ({ children }: any) => <div>{children}</div>,
}))

const CONTRACT_DIR = path.resolve(
  __dirname,
  '../../../../../shared/contracts/signup',
)
const UPDATE = process.env.UPDATE_SIGNUP_CONTRACT === '1'

const ACCOUNT = {
  name: 'Contract User',
  email: 'contract-user@example.com',
  username: 'contractuser',
  password: 'contract-pass-1234',
}

/** The edition's research-consent checkbox, as the extended slot renders it. */
function ConsentCheckbox({
  value,
  onChange,
}: {
  value: boolean
  onChange: (v: boolean) => void
}) {
  return (
    <input
      type="checkbox"
      aria-label="research consent"
      checked={value}
      onChange={(e) => onChange(e.target.checked)}
    />
  )
}

function setEdition(withConsentSlot: boolean) {
  ;(hasSlot as jest.Mock).mockReturnValue(withConsentSlot)
  ;(useSlot as jest.Mock).mockReturnValue(
    withConsentSlot ? ConsentCheckbox : null,
  )
}

let sentBodies: unknown[]

beforeEach(() => {
  jest.clearAllMocks()
  window.history.pushState({}, '', 'http://localhost/')
  sentBodies = []
  // The real API client builds the request body; only the network is cut.
  const client = new AuthClient()
  jest
    .spyOn(client as any, 'request')
    .mockImplementation(async (url: unknown, options: any) => {
      if (url === '/auth/signup') sentBodies.push(JSON.parse(options.body))
      return {}
    })
  ;(useAuth as jest.Mock).mockReturnValue({
    user: null,
    signup: (...args: Parameters<AuthClient['signup']>) =>
      client.signup(...args),
  })
  ;(useI18n as jest.Mock).mockReturnValue({
    t: (key: string) => key,
    locale: 'en',
  })
  ;(useRouter as jest.Mock).mockReturnValue({
    push: jest.fn(),
    replace: jest.fn(),
  })
  setEdition(false)
})

afterEach(() => {
  jest.restoreAllMocks()
})

async function sentBody(): Promise<unknown> {
  await waitFor(() => expect(sentBodies).toHaveLength(1))
  return sentBodies[0]
}

function expectMatchesContract(body: unknown, fixture: string) {
  const file = path.join(CONTRACT_DIR, fixture)
  if (UPDATE) {
    fs.mkdirSync(CONTRACT_DIR, { recursive: true })
    fs.writeFileSync(file, JSON.stringify(body, null, 2) + '\n')
  }
  expect(fs.existsSync(file)).toBe(true)
  expect(body).toEqual(JSON.parse(fs.readFileSync(file, 'utf-8')))
}

async function submitModal(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText('signupModal.fullName'), ACCOUNT.name)
  await user.type(
    screen.getByLabelText('signupModal.emailAddress'),
    ACCOUNT.email,
  )
  await user.type(
    screen.getByLabelText('signupModal.username'),
    ACCOUNT.username,
  )
  await user.type(
    screen.getByLabelText('signupModal.password'),
    ACCOUNT.password,
  )
  await user.type(
    screen.getByLabelText('signupModal.confirmPassword'),
    ACCOUNT.password,
  )
  await user.click(
    screen.getByRole('button', { name: 'signupModal.createAccount' }),
  )
}

async function fillRegisterAccount(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByTestId('auth-register-name-input'), ACCOUNT.name)
  await user.type(
    screen.getByTestId('auth-register-email-input'),
    ACCOUNT.email,
  )
  await user.type(
    screen.getByTestId('auth-register-username-input'),
    ACCOUNT.username,
  )
  await user.type(
    screen.getByTestId('auth-register-password-input'),
    ACCOUNT.password,
  )
  await user.type(
    screen.getByTestId('auth-register-confirm-password-input'),
    ACCOUNT.password,
  )
}

async function chooseLegalBackground(
  user: ReturnType<typeof userEvent.setup>,
  legalExpertiseLevel: string,
  germanProficiency: string,
) {
  await user.click(screen.getByTestId('register-step-indicator-2'))
  await user.selectOptions(
    within(
      screen.getByTestId('auth-register-legal-expertise-select'),
    ).getByRole('combobox'),
    legalExpertiseLevel,
  )
  await user.selectOptions(
    within(
      screen.getByTestId('auth-register-german-proficiency-select'),
    ).getByRole('combobox'),
    germanProficiency,
  )
}

async function submitRegister(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByTestId('register-step-indicator-5'))
  await user.click(screen.getByTestId('auth-register-submit-button'))
}

describe('signup payload contract', () => {
  it('signup modal (community edition)', async () => {
    const user = userEvent.setup()
    render(<SignupModal isOpen onClose={jest.fn()} />)
    await submitModal(user)
    expectMatchesContract(await sentBody(), 'signup_modal.json')
  })

  it('signup modal (edition with research consent)', async () => {
    setEdition(true)
    const user = userEvent.setup()
    render(<SignupModal isOpen onClose={jest.fn()} />)
    await user.click(screen.getByLabelText('research consent'))
    await submitModal(user)
    expectMatchesContract(
      await sentBody(),
      'signup_modal_research_consent.json',
    )
  })

  it('register page, legal background left open', async () => {
    const user = userEvent.setup()
    render(<RegisterPage />)
    await fillRegisterAccount(user)
    await submitRegister(user)
    expectMatchesContract(await sentBody(), 'register_minimal.json')
  })

  it('register page, legal background "not applicable" sends no value', async () => {
    const user = userEvent.setup()
    render(<RegisterPage />)
    await fillRegisterAccount(user)
    await chooseLegalBackground(user, 'not_applicable', 'not_applicable')
    await submitRegister(user)
    // Same request as leaving both selects open: stored as no answer.
    expectMatchesContract(await sentBody(), 'register_minimal.json')
  })

  it('register page, legal background answered', async () => {
    const user = userEvent.setup()
    render(<RegisterPage />)
    await fillRegisterAccount(user)
    await chooseLegalBackground(user, 'law_student', 'c1')
    await submitRegister(user)
    expectMatchesContract(await sentBody(), 'register_legal_background.json')
  })
})

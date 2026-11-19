/**
 * The request record view: the hash check (match, a tampered record, a
 * missing or uncheckable hash), the messages, format, parameters, retry
 * trail and raw requests, and the loader.
 */

import '@testing-library/jest-dom'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { variantViewsAPI } from '@/lib/api/variantViews'
import { makeTrialRequest } from '@/test-utils/variantViewFixtures'
import { RequestRecordLoader, RequestRecordView } from '../RequestRecordView'

jest.mock('@/contexts/I18nContext', () =>
  require('@/test-utils/i18nMock').i18nMock('en'),
)

jest.mock('@/lib/api/variantViews', () => ({
  variantViewsAPI: { getTrialRequest: jest.fn() },
}))

const api = variantViewsAPI as jest.Mocked<typeof variantViewsAPI>

beforeEach(() => jest.clearAllMocks())

describe('RequestRecordView', () => {
  it('shows a matching hash and what was sent', async () => {
    const user = userEvent.setup()
    render(<RequestRecordView view={makeTrialRequest()} />)
    const view = screen.getByTestId('request-record-view')
    expect(within(view).getByTestId('request-hash-ok')).toHaveTextContent(
      'The stored hash matches the record',
    )
    expect(within(view).getAllByText('ab'.repeat(32))).toHaveLength(2)
    expect(within(view).getByText('Answer with a number.')).toBeInTheDocument()
    expect(within(view).getByText(/json_object/)).toBeInTheDocument()
    expect(within(view).getByText(/"temperature": 0/)).toBeInTheDocument()
    expect(
      within(view).getByText('openai · chat.completions'),
    ).toBeInTheDocument()
    expect(within(view).getByText('default')).toBeInTheDocument()
    await user.click(within(view).getByText('Show the requests as sent (1)'))
    expect(within(view).getByTestId('request-raw')).toHaveTextContent(
      '"model": "sim-alpha"',
    )
    await user.click(within(view).getByText('Hide the requests as sent'))
    expect(within(view).queryByTestId('request-raw')).toBeNull()
  })

  it('flags a tampered record', () => {
    render(
      <RequestRecordView
        view={makeTrialRequest({
          computed_sha256: 'cd'.repeat(32),
          hash_matches: false,
        })}
      />,
    )
    expect(screen.getByTestId('request-hash-mismatch')).toHaveTextContent(
      'The stored hash does not match the record',
    )
    expect(screen.getByText('cd'.repeat(32))).toBeInTheDocument()
  })

  it('flags a record with malformed fields without breaking', () => {
    render(
      <RequestRecordView
        view={makeTrialRequest({
          request_record: {
            messages: 'x',
            parameters: 'y',
            requests: 'z',
            model: {},
            provider: { name: 'acme' },
            api: ['x'],
          } as unknown as NonNullable<
            ReturnType<typeof makeTrialRequest>['request_record']
          >,
          computed_sha256: null,
          hash_matches: false,
          hash_check: 'mismatch',
        })}
      />,
    )
    expect(screen.getByTestId('request-hash-mismatch')).toBeInTheDocument()
  })

  it('says when no hash was stored', () => {
    render(
      <RequestRecordView
        view={makeTrialRequest({ request_sha256: null, hash_matches: null })}
      />,
    )
    expect(screen.getByTestId('request-hash-missing')).toBeInTheDocument()
  })

  it('flags a stored hash next to a record with no request to hash', () => {
    render(
      <RequestRecordView
        view={makeTrialRequest({
          request_record: { version: 1, requests: [] },
          computed_sha256: null,
          hash_matches: false,
        })}
      />,
    )
    expect(screen.getByTestId('request-hash-mismatch')).toHaveTextContent(
      'The stored hash does not match the record',
    )
  })

  it('says a stored hash without its record cannot be checked, without a tamper warning', () => {
    render(
      <RequestRecordView
        view={makeTrialRequest({
          request_record: null,
          computed_sha256: null,
          hash_matches: null,
          hash_check: 'record_missing',
        })}
      />,
    )
    expect(screen.getByTestId('request-hash-unverifiable')).toHaveTextContent(
      'Record not available, the hash cannot be checked',
    )
    expect(screen.queryByTestId('request-hash-mismatch')).toBeNull()
    expect(screen.queryByTestId('request-hash-ok')).toBeNull()
    // The kept hash shows the record existed: it was not "generated before
    // it was recorded".
    expect(
      screen.getByText(/Only the hash of this request was kept/),
    ).toBeInTheDocument()
    expect(screen.queryByText(/generated before it was recorded/)).toBeNull()
  })

  it('shows an older answer without a hash check, roles, a retry and a worker call', () => {
    const record = makeTrialRequest().request_record!
    render(
      <RequestRecordView
        view={{
          id: 'g1',
          run_index: 0,
          request_record: {
            ...record,
            capture: 'worker_call',
            provider: null,
            response_format: null,
            parameters: {},
            messages: [
              { role: 'assistant', content: { draft: true } },
              { role: 'user', content: 'Again' },
            ],
            requests: [{}, {}],
          },
          retried: true,
          first_response: 'not json',
          first_response_truncated: true,
        }}
      />,
    )
    expect(screen.queryByTestId('request-hash-ok')).toBeNull()
    expect(screen.queryByTestId('request-hash-mismatch')).toBeNull()
    expect(screen.getByText('Assistant')).toBeInTheDocument()
    expect(screen.getByText(/"draft": true/)).toBeInTheDocument()
    expect(
      screen.getByText('Format retry: 2 requests sent'),
    ).toBeInTheDocument()
    expect(screen.getByText(/not json…/)).toBeInTheDocument()
    expect(
      screen.getByText(/The provider client reported no request/),
    ).toBeInTheDocument()
    expect(screen.queryByText('Response format')).toBeNull()
    expect(screen.queryByText('Request parameters')).toBeNull()
  })

  it('says when the trial has no record', () => {
    render(
      <RequestRecordView
        view={{ id: 'g', run_index: 0, request_record: null }}
      />,
    )
    expect(screen.getByText('No request record')).toBeInTheDocument()
    expect(
      screen.getByText('No request record (generated before it was recorded).'),
    ).toBeInTheDocument()
  })
})

describe('RequestRecordLoader', () => {
  it('loads a trial by id', async () => {
    api.getTrialRequest.mockResolvedValue(makeTrialRequest())
    render(<RequestRecordLoader trialId="g1" />)
    expect(screen.getByRole('status')).toHaveTextContent('Loading the request…')
    expect(await screen.findByTestId('request-hash-ok')).toBeInTheDocument()
    expect(api.getTrialRequest).toHaveBeenCalledWith('g1', undefined)
  })

  it('shows the error of a failed load', async () => {
    api.getTrialRequest.mockRejectedValueOnce(new Error('No access'))
    const { rerender } = render(<RequestRecordLoader trialId="g1" />)
    expect(await screen.findByRole('alert')).toHaveTextContent('No access')
    api.getTrialRequest.mockRejectedValueOnce({})
    rerender(<RequestRecordLoader trialId="g2" generationId="run" />)
    expect(await screen.findByText('The request could not be loaded.'))
  })
})

/**
 * @jest-environment jsdom
 *
 * The access window in the project page's settings card
 * (ProjectAccessWindowSection) and the fields it shares with the creation
 * wizard (AccessWindowFields): switching the window on proposes two hours
 * from now, a window that closes before it opens is flagged and never
 * saved, a valid change is saved on its own after a short delay, a refetch
 * does not overwrite an edit in progress, and a failed save shows a toast.
 */
import '@testing-library/jest-dom'
import { act, fireEvent, render, screen } from '@testing-library/react'

import { AccessWindowFields, isAccessWindowValid } from '../AccessWindowFields'
import {
  ACCESS_WINDOW_SAVE_DELAY_MS,
  ProjectAccessWindowSection,
} from '../ProjectAccessWindowSection'

const mockAddToast = jest.fn()
jest.mock('@/components/shared/Toast', () => ({
  useToast: () => ({ addToast: mockAddToast }),
}))
jest.mock('@/contexts/I18nContext', () =>
  require('@/test-utils/i18nMock').i18nMock('de'),
)

const START = '2030-03-01T08:00:00.000Z'
const END = '2030-03-01T10:00:00.000Z'

const expand = () =>
  fireEvent.click(
    screen.getByRole('button', { name: /Zeitfenster für den Zugriff/ }),
  )

const opensInput = () => screen.getByLabelText('Öffnet') as HTMLInputElement
const closesInput = () => screen.getByLabelText('Schließt') as HTMLInputElement

/** The datetime-local text of an ISO instant in the test's time zone. */
const local = (iso: string) => {
  const d = new Date(iso)
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 16)
}

beforeEach(() => {
  jest.useFakeTimers()
  mockAddToast.mockReset()
})
afterEach(() => {
  jest.useRealTimers()
})

describe('isAccessWindowValid', () => {
  it('accepts no window, one bound and a window that closes after it opens', () => {
    expect(
      isAccessWindowValid({ window_start_at: null, window_end_at: null }),
    ).toBe(true)
    expect(
      isAccessWindowValid({ window_start_at: START, window_end_at: null }),
    ).toBe(true)
    expect(
      isAccessWindowValid({ window_start_at: START, window_end_at: END }),
    ).toBe(true)
  })

  it('refuses a window that closes before or when it opens', () => {
    expect(
      isAccessWindowValid({ window_start_at: END, window_end_at: START }),
    ).toBe(false)
    expect(
      isAccessWindowValid({ window_start_at: START, window_end_at: START }),
    ).toBe(false)
  })
})

describe('AccessWindowFields', () => {
  it('proposes two hours from now when switched on and clears when switched off', () => {
    jest.setSystemTime(new Date('2030-01-01T12:34:56Z'))
    const onChange = jest.fn()
    const { rerender } = render(
      <AccessWindowFields
        value={{ window_start_at: null, window_end_at: null }}
        onChange={onChange}
      />,
    )
    expect(screen.getByText('Zeitfenster für den Zugriff')).toBeInTheDocument()
    expect(screen.queryByLabelText('Öffnet')).not.toBeInTheDocument()

    fireEvent.click(screen.getByTestId('access-window-toggle'))
    expect(onChange).toHaveBeenLastCalledWith({
      window_start_at: '2030-01-01T12:34:00.000Z',
      window_end_at: '2030-01-01T14:34:00.000Z',
    })

    rerender(
      <AccessWindowFields
        value={{ window_start_at: START, window_end_at: END }}
        onChange={onChange}
      />,
    )
    expect(opensInput().value).toBe(local(START))
    expect(closesInput().value).toBe(local(END))
    fireEvent.click(screen.getByTestId('access-window-toggle'))
    expect(onChange).toHaveBeenLastCalledWith({
      window_start_at: null,
      window_end_at: null,
    })
  })

  it('flags a window that closes before it opens', () => {
    render(
      <AccessWindowFields
        value={{ window_start_at: END, window_end_at: START }}
        onChange={jest.fn()}
      />,
    )
    expect(screen.getByRole('alert')).toHaveTextContent(
      'Das Schließdatum muss nach dem Öffnungsdatum liegen.',
    )
  })

  it('leaves the title to the surrounding section when asked', () => {
    render(
      <AccessWindowFields
        value={{ window_start_at: null, window_end_at: null }}
        onChange={jest.fn()}
        showTitle={false}
      />,
    )
    expect(
      screen.queryByText('Zeitfenster für den Zugriff'),
    ).not.toBeInTheDocument()
    expect(screen.getByTestId('access-window-toggle')).toHaveAccessibleName(
      'Zeitfenster für den Zugriff',
    )
  })
})

describe('ProjectAccessWindowSection', () => {
  it('shows the window state as the badge of the collapsed section', () => {
    jest.setSystemTime(new Date('2030-01-01T00:00:00Z'))
    render(
      <ProjectAccessWindowSection
        windowStartAt={START}
        windowEndAt={END}
        onSave={jest.fn()}
      />,
    )
    expect(
      screen.getByText(`Öffnet ${new Date(START).toLocaleDateString('de-DE')}`),
    ).toBeInTheDocument()
    expect(screen.queryByLabelText('Öffnet')).not.toBeInTheDocument()
  })

  it('saves a valid change after the delay, once', async () => {
    const onSave = jest.fn().mockResolvedValue(undefined)
    render(
      <ProjectAccessWindowSection
        windowStartAt={START}
        windowEndAt={END}
        onSave={onSave}
      />,
    )
    expand()
    fireEvent.change(closesInput(), {
      target: { value: local('2030-03-01T12:00:00.000Z') },
    })
    expect(onSave).not.toHaveBeenCalled()
    await act(async () => {
      jest.advanceTimersByTime(ACCESS_WINDOW_SAVE_DELAY_MS)
    })
    expect(onSave).toHaveBeenCalledTimes(1)
    expect(onSave).toHaveBeenCalledWith({
      window_start_at: START,
      window_end_at: '2030-03-01T12:00:00.000Z',
    })
  })

  it('saves clearing the window', async () => {
    const onSave = jest.fn().mockResolvedValue(undefined)
    render(
      <ProjectAccessWindowSection
        windowStartAt={START}
        windowEndAt={END}
        onSave={onSave}
      />,
    )
    expand()
    fireEvent.click(screen.getByTestId('access-window-toggle'))
    await act(async () => {
      jest.advanceTimersByTime(ACCESS_WINDOW_SAVE_DELAY_MS)
    })
    expect(onSave).toHaveBeenCalledWith({
      window_start_at: null,
      window_end_at: null,
    })
  })

  it('never saves a window that closes before it opens', async () => {
    const onSave = jest.fn().mockResolvedValue(undefined)
    render(
      <ProjectAccessWindowSection
        windowStartAt={START}
        windowEndAt={END}
        onSave={onSave}
      />,
    )
    expand()
    fireEvent.change(closesInput(), {
      target: { value: local('2030-03-01T07:00:00.000Z') },
    })
    await act(async () => {
      jest.advanceTimersByTime(ACCESS_WINDOW_SAVE_DELAY_MS * 3)
    })
    expect(onSave).not.toHaveBeenCalled()
    expect(screen.getByRole('alert')).toBeInTheDocument()
  })

  it('does not save without an edit and follows a refetched window', () => {
    const onSave = jest.fn()
    const { rerender } = render(
      <ProjectAccessWindowSection
        windowStartAt={null}
        windowEndAt={null}
        onSave={onSave}
      />,
    )
    rerender(
      <ProjectAccessWindowSection
        windowStartAt={START}
        windowEndAt={END}
        onSave={onSave}
      />,
    )
    expand()
    expect(opensInput().value).toBe(local(START))
    act(() => {
      jest.advanceTimersByTime(ACCESS_WINDOW_SAVE_DELAY_MS * 3)
    })
    expect(onSave).not.toHaveBeenCalled()
  })

  it('keeps an edit in progress when the project is refetched', () => {
    const { rerender } = render(
      <ProjectAccessWindowSection
        windowStartAt={START}
        windowEndAt={END}
        onSave={jest.fn().mockResolvedValue(undefined)}
      />,
    )
    expand()
    const edited = local('2030-03-01T11:00:00.000Z')
    fireEvent.change(closesInput(), { target: { value: edited } })
    rerender(
      <ProjectAccessWindowSection
        windowStartAt={START}
        windowEndAt="2030-03-01T09:00:00.000Z"
        onSave={jest.fn().mockResolvedValue(undefined)}
      />,
    )
    expect(closesInput().value).toBe(edited)
  })

  it('shows a toast when the save fails', async () => {
    const onSave = jest.fn().mockRejectedValue(new Error('kaputt'))
    render(
      <ProjectAccessWindowSection
        windowStartAt={START}
        windowEndAt={END}
        onSave={onSave}
      />,
    )
    expand()
    fireEvent.click(screen.getByTestId('access-window-toggle'))
    await act(async () => {
      jest.advanceTimersByTime(ACCESS_WINDOW_SAVE_DELAY_MS)
    })
    expect(mockAddToast).toHaveBeenCalledWith(
      expect.stringContaining('kaputt'),
      'error',
    )
  })
})

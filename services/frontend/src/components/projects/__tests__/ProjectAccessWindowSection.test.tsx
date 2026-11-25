/**
 * @jest-environment jsdom
 *
 * The access window in the project page's settings card
 * (ProjectAccessWindowSection) and the fields it shares with the creation
 * wizard (AccessWindowFields): switching the window on proposes two hours
 * from now, a window that closes before it opens is flagged and never
 * saved, a time being typed (a partial year such as 0002) is never saved, a
 * finished edit (blur, Enter, the switch) is saved once, a refetch does not
 * overwrite an edit in progress, and a failed save shows a toast and keeps
 * the edit.
 */
import '@testing-library/jest-dom'
import { act, fireEvent, render, screen } from '@testing-library/react'

import { AccessWindowFields, isAccessWindowValid } from '../AccessWindowFields'
import { ProjectAccessWindowSection } from '../ProjectAccessWindowSection'

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
/** Long past any save delay, so a debounced save would have fired. */
const WAIT_MS = 10_000

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

  it('commits on blur, Enter and the switch, never while typing', () => {
    const onChange = jest.fn()
    const onCommit = jest.fn()
    const value = { window_start_at: START, window_end_at: END }
    const { rerender } = render(
      <AccessWindowFields
        value={value}
        onChange={onChange}
        onCommit={onCommit}
      />,
    )
    fireEvent.change(closesInput(), {
      target: { value: local('2030-03-01T12:00:00.000Z') },
    })
    expect(onChange).toHaveBeenCalledTimes(1)
    expect(onCommit).not.toHaveBeenCalled()

    const edited = {
      window_start_at: START,
      window_end_at: '2030-03-01T12:00:00.000Z',
    }
    rerender(
      <AccessWindowFields
        value={edited}
        onChange={onChange}
        onCommit={onCommit}
      />,
    )
    fireEvent.keyDown(closesInput(), { key: 'a' })
    expect(onCommit).not.toHaveBeenCalled()
    fireEvent.keyDown(closesInput(), { key: 'Enter' })
    expect(onCommit).toHaveBeenLastCalledWith(edited)
    fireEvent.blur(opensInput())
    expect(onCommit).toHaveBeenCalledTimes(2)
    fireEvent.click(screen.getByTestId('access-window-toggle'))
    expect(onCommit).toHaveBeenLastCalledWith({
      window_start_at: null,
      window_end_at: null,
    })
  })

  it('keeps the window on and the fields shown when both times are emptied', () => {
    const onChange = jest.fn()
    const { rerender } = render(
      <AccessWindowFields
        value={{ window_start_at: START, window_end_at: END }}
        onChange={onChange}
      />,
    )
    rerender(
      <AccessWindowFields
        value={{ window_start_at: null, window_end_at: null }}
        onChange={onChange}
      />,
    )
    expect(screen.getByTestId('access-window-toggle')).toBeChecked()
    expect(opensInput().value).toBe('')
    expect(closesInput().value).toBe('')
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

  it('never saves a date typed digit by digit, and saves the finished one once on blur', async () => {
    jest.setSystemTime(new Date('2030-01-01T00:00:00Z'))
    const onSave = jest.fn().mockResolvedValue(undefined)
    render(
      <ProjectAccessWindowSection
        windowStartAt={START}
        windowEndAt={END}
        onSave={onSave}
      />,
    )
    expand()
    // The year segment of a datetime-local input, typed digit by digit.
    const finished = local('2030-03-01T09:00:00.000Z')
    for (const year of ['0002', '0020', '0203']) {
      fireEvent.change(opensInput(), {
        target: { value: year + finished.slice(4) },
      })
      await act(async () => {
        jest.advanceTimersByTime(WAIT_MS)
      })
    }
    expect(onSave).not.toHaveBeenCalled()

    fireEvent.change(opensInput(), { target: { value: finished } })
    await act(async () => {
      jest.advanceTimersByTime(WAIT_MS)
    })
    expect(onSave).not.toHaveBeenCalled()

    await act(async () => {
      fireEvent.blur(opensInput())
    })
    expect(onSave).toHaveBeenCalledTimes(1)
    expect(onSave).toHaveBeenCalledWith({
      window_start_at: '2030-03-01T09:00:00.000Z',
      window_end_at: END,
    })
  })

  it('saves on Enter once, even when the field is left right after', async () => {
    let resolve: () => void = () => {}
    const onSave = jest.fn(() => new Promise<void>((r) => (resolve = r)))
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
    fireEvent.keyDown(closesInput(), { key: 'Enter' })
    fireEvent.blur(closesInput())
    await act(async () => resolve())
    expect(onSave).toHaveBeenCalledTimes(1)
    expect(onSave).toHaveBeenCalledWith({
      window_start_at: START,
      window_end_at: '2030-03-01T12:00:00.000Z',
    })
  })

  it('does not save a blur without a change', async () => {
    const onSave = jest.fn().mockResolvedValue(undefined)
    render(
      <ProjectAccessWindowSection
        windowStartAt={START}
        windowEndAt={END}
        onSave={onSave}
      />,
    )
    expand()
    await act(async () => {
      fireEvent.blur(opensInput())
      fireEvent.blur(closesInput())
    })
    expect(onSave).not.toHaveBeenCalled()
  })

  it('saves an open-ended window with only an opening time', async () => {
    const onSave = jest.fn().mockResolvedValue(undefined)
    render(
      <ProjectAccessWindowSection
        windowStartAt={START}
        windowEndAt={null}
        onSave={onSave}
      />,
    )
    expand()
    expect(closesInput().value).toBe('')
    fireEvent.change(opensInput(), {
      target: { value: local('2030-03-02T08:00:00.000Z') },
    })
    await act(async () => {
      fireEvent.blur(opensInput())
    })
    expect(onSave).toHaveBeenCalledTimes(1)
    expect(onSave).toHaveBeenCalledWith({
      window_start_at: '2030-03-02T08:00:00.000Z',
      window_end_at: null,
    })
  })

  it('never saves while a time field is only partly filled', async () => {
    const onSave = jest.fn().mockResolvedValue(undefined)
    render(
      <ProjectAccessWindowSection
        windowStartAt={START}
        windowEndAt={END}
        onSave={onSave}
      />,
    )
    expand()
    // A datetime-local with a cleared segment reports '' and badInput.
    const partlyFilled = (input: HTMLInputElement) => {
      Object.defineProperty(input, 'validity', {
        configurable: true,
        value: { badInput: true },
      })
      fireEvent.change(input, { target: { value: '' } })
    }
    partlyFilled(opensInput())
    await act(async () => {
      fireEvent.blur(opensInput())
      fireEvent.keyDown(opensInput(), { key: 'Enter' })
      // Leaving the complete closing field must not save the half-typed one.
      fireEvent.blur(closesInput())
      fireEvent.keyDown(closesInput(), { key: 'Enter' })
    })
    expect(onSave).not.toHaveBeenCalled()
    expect(closesInput().value).toBe(local(END))
  })

  it('saves clearing the closing time as an open-ended window', async () => {
    const onSave = jest.fn().mockResolvedValue(undefined)
    render(
      <ProjectAccessWindowSection
        windowStartAt={START}
        windowEndAt={END}
        onSave={onSave}
      />,
    )
    expand()
    fireEvent.change(closesInput(), { target: { value: '' } })
    await act(async () => {
      fireEvent.blur(closesInput())
    })
    expect(onSave).toHaveBeenCalledTimes(1)
    expect(onSave).toHaveBeenCalledWith({
      window_start_at: START,
      window_end_at: null,
    })
  })

  it('saves clearing the window when switched off', async () => {
    const onSave = jest.fn().mockResolvedValue(undefined)
    render(
      <ProjectAccessWindowSection
        windowStartAt={START}
        windowEndAt={END}
        onSave={onSave}
      />,
    )
    expand()
    await act(async () => {
      fireEvent.click(screen.getByTestId('access-window-toggle'))
    })
    expect(onSave).toHaveBeenCalledTimes(1)
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
      fireEvent.blur(closesInput())
      fireEvent.keyDown(closesInput(), { key: 'Enter' })
    })
    expect(onSave).not.toHaveBeenCalled()
    expect(screen.getByRole('alert')).toBeInTheDocument()
  })

  it('never saves or hides a stored window whose times are emptied', async () => {
    jest.setSystemTime(new Date('2030-01-01T00:00:00Z'))
    const onSave = jest.fn().mockResolvedValue(undefined)
    render(
      <ProjectAccessWindowSection
        windowStartAt={START}
        windowEndAt={END}
        onSave={onSave}
      />,
    )
    const badge = `Öffnet ${new Date(START).toLocaleDateString('de-DE')}`
    expand()
    await act(async () => {
      fireEvent.change(opensInput(), { target: { value: '' } })
      fireEvent.change(closesInput(), { target: { value: '' } })
      fireEvent.blur(closesInput())
      fireEvent.blur(opensInput())
      fireEvent.keyDown(closesInput(), { key: 'Enter' })
    })
    expect(onSave).not.toHaveBeenCalled()
    expect(screen.getByTestId('access-window-toggle')).toBeChecked()
    expect(opensInput().value).toBe('')
    expect(closesInput().value).toBe('')
    expect(screen.getByText(badge)).toBeInTheDocument()
  })

  it('follows a refetched window without saving', () => {
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
    fireEvent.blur(opensInput())
    expect(onSave).not.toHaveBeenCalled()
  })

  it('never saves a window that was typed but not committed when the section closes', async () => {
    const onSave = jest.fn().mockResolvedValue(undefined)
    render(
      <ProjectAccessWindowSection
        windowStartAt={START}
        windowEndAt={END}
        onSave={onSave}
      />,
    )
    expand()
    fireEvent.change(opensInput(), {
      target: { value: local('2030-03-01T07:00:00.000Z') },
    })
    // Closing the sub-section unmounts the fields without a blur.
    await act(async () => {
      expand()
      jest.advanceTimersByTime(WAIT_MS)
    })
    expect(screen.queryByLabelText('Öffnet')).not.toBeInTheDocument()
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

  it('shows a toast when the save fails and keeps the edit for a retry', async () => {
    const onSave = jest
      .fn()
      .mockRejectedValueOnce(new Error('kaputt'))
      .mockResolvedValue(undefined)
    render(
      <ProjectAccessWindowSection
        windowStartAt={START}
        windowEndAt={END}
        onSave={onSave}
      />,
    )
    expand()
    const edited = local('2030-03-01T12:00:00.000Z')
    fireEvent.change(closesInput(), { target: { value: edited } })
    await act(async () => {
      fireEvent.blur(closesInput())
    })
    expect(mockAddToast).toHaveBeenCalledWith(
      expect.stringContaining('kaputt'),
      'error',
    )
    expect(closesInput().value).toBe(edited)
    await act(async () => {
      fireEvent.blur(closesInput())
    })
    expect(onSave).toHaveBeenCalledTimes(2)
    expect(onSave).toHaveBeenLastCalledWith({
      window_start_at: START,
      window_end_at: '2030-03-01T12:00:00.000Z',
    })
  })
})

/**
 * The shared auto-save (components/shared/AutoSave): one saved toast per
 * batch with an undo that restores and saves the previous values, invalid
 * legs never saved, saves never overlapping, free text saved on commit, and
 * a pending change saved when its section unmounts.
 *
 * @jest-environment jsdom
 */

import {
  AutoSaveStatusProvider,
  useAutoSave,
  useAutoSaveBuffer,
} from '@/components/shared/AutoSave'
import {
  registerSettingRisk,
  settingChanges,
  SettingRiskProvider,
} from '@/components/shared/settingRisk'
import '@testing-library/jest-dom'
import { act, fireEvent, render, screen } from '@testing-library/react'
import { useState } from 'react'

const mockAddToast = jest.fn()
const mockRemoveToast = jest.fn()
jest.mock('@/components/shared/Toast', () => ({
  useToast: () => ({ addToast: mockAddToast, removeToast: mockRemoveToast }),
}))
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({ t: (key: string) => key }),
}))

const savedToasts = () =>
  mockAddToast.mock.calls.filter(([, type]) => type === 'success')

const advance = async (ms: number) => {
  await act(async () => {
    await jest.advanceTimersByTimeAsync(ms)
  })
}

beforeEach(() => {
  jest.useFakeTimers()
  mockAddToast.mockReset()
  mockAddToast.mockImplementation(
    () => `toast-${mockAddToast.mock.calls.length}`,
  )
  mockRemoveToast.mockReset()
})
afterEach(() => {
  jest.useRealTimers()
})

/** A buffer of two legs, like a project page card. */
function Card({
  save,
  isLegValid,
}: {
  save: (legs: string[], values: { a: number; b: string }) => Promise<void>
  isLegValid?: (leg: 'a' | 'b', values: { a: number; b: string }) => boolean
}) {
  const [a, setA] = useState(1)
  const [b, setB] = useState('x')
  const buffer = useAutoSaveBuffer({
    values: { a, b },
    save: (legs, values) => save(legs as string[], values),
    restore: (previous) => {
      if (previous.a !== undefined) setA(previous.a)
      if (previous.b !== undefined) setB(previous.b)
    },
    isLegValid,
  })
  return (
    <div>
      <span data-testid="a">{a}</span>
      <span data-testid="b">{b}</span>
      {buffer.dirty && <span data-testid="dirty" />}
      {buffer.invalid && <span data-testid="invalid" />}
      <button
        data-testid="inc-a"
        onClick={() => {
          buffer.markChanged()
          setA((v) => v + 1)
        }}
      />
      <input
        data-testid="b-input"
        value={b}
        onChange={(e) => {
          buffer.markChanged({ schedule: false })
          setB(e.target.value)
        }}
        onBlur={() => void buffer.commit()}
      />
    </div>
  )
}

describe('useAutoSaveBuffer', () => {
  it('saves a burst of changes as one batch with exactly one toast', async () => {
    const save = jest.fn().mockResolvedValue(undefined)
    render(<Card save={save} />)
    fireEvent.click(screen.getByTestId('inc-a'))
    await advance(500)
    fireEvent.click(screen.getByTestId('inc-a'))
    expect(screen.getByTestId('dirty')).toBeInTheDocument()
    await advance(2100)

    expect(save).toHaveBeenCalledTimes(1)
    expect(save).toHaveBeenCalledWith(['a'], { a: 3, b: 'x' })
    expect(savedToasts()).toHaveLength(1)
    expect(savedToasts()[0][0]).toBe('shared.autoSave.saved')
    expect(screen.queryByTestId('dirty')).not.toBeInTheDocument()
  })

  it('saves nothing (and toasts nothing) when a change is reverted before the delay', async () => {
    const save = jest.fn().mockResolvedValue(undefined)
    render(<Card save={save} />)
    fireEvent.change(screen.getByTestId('b-input'), { target: { value: 'y' } })
    fireEvent.change(screen.getByTestId('b-input'), { target: { value: 'x' } })
    fireEvent.blur(screen.getByTestId('b-input'))
    await advance(2100)
    expect(save).not.toHaveBeenCalled()
    expect(savedToasts()).toHaveLength(0)
  })

  it('saves free text on commit only, never while typing', async () => {
    const save = jest.fn().mockResolvedValue(undefined)
    render(<Card save={save} />)
    fireEvent.change(screen.getByTestId('b-input'), { target: { value: 'yz' } })
    await advance(10_000)
    expect(save).not.toHaveBeenCalled()
    await act(async () => {
      fireEvent.blur(screen.getByTestId('b-input'))
    })
    expect(save).toHaveBeenCalledWith(['b'], { a: 1, b: 'yz' })
  })

  it('undo restores the values from before the batch and saves them', async () => {
    const save = jest.fn().mockResolvedValue(undefined)
    render(<Card save={save} />)
    fireEvent.click(screen.getByTestId('inc-a'))
    await advance(2100)
    expect(screen.getByTestId('a')).toHaveTextContent('2')

    const undo = savedToasts()[0][3].action
    expect(undo.label).toBe('shared.autoSave.undo')
    await act(async () => {
      undo.onClick()
    })
    await advance(0)

    expect(screen.getByTestId('a')).toHaveTextContent('1')
    expect(save).toHaveBeenCalledTimes(2)
    expect(save).toHaveBeenLastCalledWith(['a'], { a: 1, b: 'x' })
  })

  it('never saves an invalid leg; the valid ones save and the card stays unsaved', async () => {
    const save = jest.fn().mockResolvedValue(undefined)
    render(
      <Card
        save={save}
        isLegValid={(leg, values) => leg !== 'b' || values.b !== ''}
      />,
    )
    fireEvent.change(screen.getByTestId('b-input'), { target: { value: '' } })
    fireEvent.click(screen.getByTestId('inc-a'))
    await advance(2100)

    expect(save).toHaveBeenCalledTimes(1)
    expect(save).toHaveBeenCalledWith(['a'], { a: 2, b: '' })
    expect(screen.getByTestId('dirty')).toBeInTheDocument()
    expect(screen.getByTestId('invalid')).toBeInTheDocument()
  })

  it('keeps a failed batch unsaved and shows no saved toast', async () => {
    const save = jest.fn().mockRejectedValue(new Error('down'))
    render(<Card save={save} />)
    fireEvent.click(screen.getByTestId('inc-a'))
    await advance(2100)
    expect(save).toHaveBeenCalledTimes(1)
    expect(savedToasts()).toHaveLength(0)
    expect(screen.getByTestId('dirty')).toBeInTheDocument()
  })

  it('never runs two saves at once: a change during a save lands after it', async () => {
    let finish: () => void = () => {}
    const save = jest
      .fn()
      .mockImplementationOnce(
        () => new Promise<void>((resolve) => (finish = resolve)),
      )
      .mockResolvedValue(undefined)
    render(<Card save={save} />)
    fireEvent.click(screen.getByTestId('inc-a'))
    await advance(2100)
    expect(save).toHaveBeenCalledTimes(1)

    fireEvent.click(screen.getByTestId('inc-a'))
    await advance(5000)
    // Still the first save in flight: the second waits.
    expect(save).toHaveBeenCalledTimes(1)
    await act(async () => finish())
    await advance(1000)
    expect(save).toHaveBeenCalledTimes(2)
    expect(save).toHaveBeenLastCalledWith(['a'], { a: 3, b: 'x' })
  })
})

/** One self-saving section inside a status provider. */
function Section({
  save,
  isValid,
}: {
  save: (value: string) => Promise<void>
  isValid?: (value: string) => boolean
}) {
  const [value, setValue] = useState('a')
  const state = useAutoSave({
    value,
    save,
    isValid,
    onUndo: setValue,
  })
  return (
    <div>
      <input
        data-testid="value"
        value={value}
        onChange={(e) => setValue(e.target.value)}
      />
      {state.invalid && <span data-testid="section-invalid" />}
    </div>
  )
}

function Host({
  save,
  isValid,
}: {
  save: (value: string) => Promise<void>
  isValid?: (value: string) => boolean
}) {
  const [open, setOpen] = useState(true)
  return (
    <AutoSaveStatusProvider>
      {(status) => (
        <div>
          {status.dirty && <span data-testid="card-dirty" />}
          <button data-testid="close" onClick={() => setOpen(false)} />
          {open && <Section save={save} isValid={isValid} />}
        </div>
      )}
    </AutoSaveStatusProvider>
  )
}

describe('useAutoSave', () => {
  it('reports unsaved changes to the enclosing card and saves after the delay', async () => {
    const save = jest.fn().mockResolvedValue(undefined)
    render(<Host save={save} />)
    fireEvent.change(screen.getByTestId('value'), { target: { value: 'b' } })
    await advance(0)
    expect(screen.getByTestId('card-dirty')).toBeInTheDocument()
    await advance(2100)
    expect(save).toHaveBeenCalledWith('b')
    expect(screen.queryByTestId('card-dirty')).not.toBeInTheDocument()
    expect(savedToasts()).toHaveLength(1)
  })

  it('never saves an invalid value', async () => {
    const save = jest.fn().mockResolvedValue(undefined)
    render(<Host save={save} isValid={(v) => v !== ''} />)
    fireEvent.change(screen.getByTestId('value'), { target: { value: '' } })
    await advance(5000)
    expect(save).not.toHaveBeenCalled()
    expect(screen.getByTestId('section-invalid')).toBeInTheDocument()
  })

  it('saves a pending valid change when its section unmounts', async () => {
    const save = jest.fn().mockResolvedValue(undefined)
    render(<Host save={save} />)
    fireEvent.change(screen.getByTestId('value'), { target: { value: 'c' } })
    await advance(0)
    fireEvent.click(screen.getByTestId('close'))
    await advance(0)
    expect(save).toHaveBeenCalledWith('c')
    // The section is gone: its toast offers no undo that could not restore.
    expect(savedToasts()).toHaveLength(1)
    expect(savedToasts()[0][3]).toBeUndefined()
  })

  it('takes the undo away once its section unmounts', async () => {
    const save = jest.fn().mockResolvedValue(undefined)
    render(<Host save={save} />)
    fireEvent.change(screen.getByTestId('value'), { target: { value: 'd' } })
    await advance(2100)
    expect(savedToasts()[0][3].action).toBeDefined()
    const id = mockAddToast.mock.results[0].value
    fireEvent.click(screen.getByTestId('close'))
    expect(mockRemoveToast).toHaveBeenCalledWith(id)
  })
})

/** A buffer with one registered setting; switching it on is risky. */
function RiskyCard({ save }: { save: (on: boolean) => Promise<void> }) {
  const [settings, setSettings] = useState({ test_undo_reveal: true })
  const buffer = useAutoSaveBuffer({
    values: { settings },
    save: (_legs, values) => save(values.settings.test_undo_reveal),
    restore: (previous) => {
      if (previous.settings) setSettings(previous.settings)
    },
    riskChanges: (from, to) =>
      settingChanges(from.settings ?? {}, to.settings ?? {}),
  })
  return (
    <div>
      <span data-testid="reveal">{String(settings.test_undo_reveal)}</span>
      <button
        data-testid="switch-off"
        onClick={() => {
          buffer.markChanged()
          setSettings({ test_undo_reveal: false })
        }}
      />
    </div>
  )
}

describe('undo of a risky change', () => {
  beforeAll(() =>
    registerSettingRisk('test_undo_reveal', {
      isRisky: (_from, to) => to === true,
      label: () => 'reveal',
      consequence: () => 'everyone sees the answers',
    }),
  )

  const renderRisky = (save: (on: boolean) => Promise<void>) =>
    render(
      <SettingRiskProvider
        context={{ project: null, runningExam: false, submittedCount: 0 }}
      >
        <RiskyCard save={save} />
      </SettingRiskProvider>,
    )

  const switchOffAndUndo = async () => {
    fireEvent.click(screen.getByTestId('switch-off'))
    await advance(2100)
    const undo = savedToasts()[0][3].action
    await act(async () => {
      undo.onClick()
    })
  }

  it('asks first and keeps the current value, unsaved, when cancelled', async () => {
    const save = jest.fn().mockResolvedValue(undefined)
    renderRisky(save)
    await switchOffAndUndo()
    expect(screen.getByText(/everyone sees the answers/)).toBeInTheDocument()
    fireEvent.click(screen.getByTestId('confirm-dialog-cancel-button'))
    await advance(5000)
    expect(screen.getByTestId('reveal')).toHaveTextContent('false')
    expect(save).toHaveBeenCalledTimes(1)
    expect(savedToasts()).toHaveLength(1)
  })

  it('restores and saves the previous value once confirmed', async () => {
    const save = jest.fn().mockResolvedValue(undefined)
    renderRisky(save)
    await switchOffAndUndo()
    expect(save).toHaveBeenCalledTimes(1)
    fireEvent.click(screen.getByTestId('confirm-dialog-confirm-button'))
    await advance(0)
    expect(screen.getByTestId('reveal')).toHaveTextContent('true')
    expect(save).toHaveBeenCalledTimes(2)
    expect(save).toHaveBeenLastCalledWith(true)
  })
})

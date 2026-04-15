import { act, render, screen } from '@testing-library/react'
import { AutoSaveIndicator } from '../AutoSaveIndicator'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, vars?: any) => {
      const translations: Record<string, string> = {
        'common.autoSave.justNow': 'Just now',
        'common.autoSave.secondsAgo': '{seconds}s ago',
        'common.autoSave.minutesAgo': '{minutes}m ago',
        'common.autoSave.hoursAgo': '{hours}h ago',
        'common.autoSave.saving': 'Saving...',
        'common.autoSave.saved': 'Saved {displayTime}',
        'common.autoSave.saveFailed': 'Save failed',
        'common.autoSave.lastSaved': 'Last saved:',
      }
      let result = translations[key] || key
      if (vars) {
        Object.entries(vars).forEach(([k, v]) => {
          result = result.replace(`{${k}}`, String(v))
        })
      }
      return result
    },
    locale: 'en',
  }),
}))

describe('AutoSaveIndicator', () => {
  beforeEach(() => {
    jest.useFakeTimers()
  })

  afterEach(() => {
    jest.useRealTimers()
  })

  it('renders nothing when no state to display', () => {
    const { container } = render(
      <AutoSaveIndicator isSaving={false} lastSaved={null} error={null} />
    )
    expect(container.firstChild).toBeNull()
  })

  it('renders error state', () => {
    render(
      <AutoSaveIndicator
        isSaving={false}
        lastSaved={null}
        error="Connection lost"
      />
    )
    expect(screen.getByText('Save failed')).toBeInTheDocument()
  })

  it('renders error with title attribute', () => {
    const { container } = render(
      <AutoSaveIndicator
        isSaving={false}
        lastSaved={null}
        error="Connection lost"
      />
    )
    const errorDiv = container.querySelector('[title="Connection lost"]')
    expect(errorDiv).toBeInTheDocument()
  })

  it('renders saving state', () => {
    render(
      <AutoSaveIndicator isSaving={true} lastSaved={null} error={null} />
    )
    expect(screen.getByText('Saving...')).toBeInTheDocument()
  })

  it('renders saved state with relative time', () => {
    const recentDate = new Date()
    render(
      <AutoSaveIndicator
        isSaving={false}
        lastSaved={recentDate}
        error={null}
      />
    )
    expect(screen.getByText(/Saved/)).toBeInTheDocument()
  })

  it('applies custom className', () => {
    const { container } = render(
      <AutoSaveIndicator
        isSaving={true}
        lastSaved={null}
        error={null}
        className="my-custom-class"
      />
    )
    const div = container.firstChild as HTMLElement
    expect(div.className).toContain('my-custom-class')
  })

  it('error state takes priority over saving state', () => {
    render(
      <AutoSaveIndicator
        isSaving={true}
        lastSaved={null}
        error="Some error"
      />
    )
    expect(screen.getByText('Save failed')).toBeInTheDocument()
    expect(screen.queryByText('Saving...')).not.toBeInTheDocument()
  })

  it('formats relative time as "Just now" for very recent saves', () => {
    const now = new Date()
    render(
      <AutoSaveIndicator isSaving={false} lastSaved={now} error={null} />
    )
    expect(screen.getByText('Saved Just now')).toBeInTheDocument()
  })

  it('formats relative time in seconds', () => {
    const thirtySecondsAgo = new Date(Date.now() - 30000)
    render(
      <AutoSaveIndicator
        isSaving={false}
        lastSaved={thirtySecondsAgo}
        error={null}
      />
    )
    expect(screen.getByText(/Saved.*s ago/)).toBeInTheDocument()
  })

  it('formats relative time in minutes', () => {
    const fiveMinutesAgo = new Date(Date.now() - 5 * 60 * 1000)
    render(
      <AutoSaveIndicator
        isSaving={false}
        lastSaved={fiveMinutesAgo}
        error={null}
      />
    )
    expect(screen.getByText(/Saved.*m ago/)).toBeInTheDocument()
  })

  it('formats relative time in hours', () => {
    const twoHoursAgo = new Date(Date.now() - 2 * 60 * 60 * 1000)
    render(
      <AutoSaveIndicator
        isSaving={false}
        lastSaved={twoHoursAgo}
        error={null}
      />
    )
    expect(screen.getByText(/Saved.*h ago/)).toBeInTheDocument()
  })

  it('formats very old times with locale time string', () => {
    const twoDaysAgo = new Date(Date.now() - 48 * 60 * 60 * 1000)
    render(
      <AutoSaveIndicator
        isSaving={false}
        lastSaved={twoDaysAgo}
        error={null}
      />
    )
    // Should show time string instead of relative time
    expect(screen.getByText(/Saved/)).toBeInTheDocument()
  })

  it('shows title with full date on saved state', () => {
    const date = new Date()
    const { container } = render(
      <AutoSaveIndicator isSaving={false} lastSaved={date} error={null} />
    )
    const div = container.querySelector('[title]')
    expect(div).toBeInTheDocument()
    expect(div?.getAttribute('title')).toContain('Last saved:')
  })

  it('updates display time at interval', () => {
    const recentDate = new Date()
    render(
      <AutoSaveIndicator
        isSaving={false}
        lastSaved={recentDate}
        error={null}
      />
    )

    // Advance past the 10-second update interval
    act(() => {
      jest.advanceTimersByTime(10000)
    })

    // Should still render without errors
    expect(screen.getByText(/Saved/)).toBeInTheDocument()
  })

  it('cleans up interval on unmount', () => {
    const { unmount } = render(
      <AutoSaveIndicator
        isSaving={false}
        lastSaved={new Date()}
        error={null}
      />
    )
    unmount()
    // Should not throw after unmount
    act(() => {
      jest.advanceTimersByTime(20000)
    })
  })

  it('renders error state with correct styling', () => {
    const { container } = render(
      <AutoSaveIndicator
        isSaving={false}
        lastSaved={null}
        error="Error"
      />
    )
    const div = container.firstChild as HTMLElement
    expect(div.className).toContain('text-red-600')
  })

  it('renders saving state with correct styling', () => {
    const { container } = render(
      <AutoSaveIndicator isSaving={true} lastSaved={null} error={null} />
    )
    const div = container.firstChild as HTMLElement
    expect(div.className).toContain('text-zinc-500')
  })
})

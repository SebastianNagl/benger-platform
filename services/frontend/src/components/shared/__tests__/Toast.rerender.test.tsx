/**
 * The toast context value must stay stable so that adding a toast only
 * re-renders the toast container, not every useToast() consumer.
 */

import { useNotificationStore } from '@/stores/notificationStore'
import { act, render, screen } from '@testing-library/react'
import React from 'react'
import { ToastProvider, useToast } from '../Toast'

jest.unmock('@/components/shared/Toast')

jest.mock('framer-motion', () => ({
  motion: {
    div: ({ children, ...props }: any) => <div {...props}>{children}</div>,
  },
  AnimatePresence: ({ children }: any) => <>{children}</>,
}))
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({ t: (key: string) => key, locale: 'en' }),
}))

describe('ToastProvider render isolation', () => {
  beforeEach(() => {
    useNotificationStore.setState({ toasts: [] })
  })

  it('does not re-render consumers when a toast is added or removed', () => {
    // Every render of the consumer reports the context value it saw.
    const onRender = jest.fn<void, [ReturnType<typeof useToast>]>()

    function Consumer() {
      onRender(useToast())
      return <span>consumer</span>
    }

    render(
      <ToastProvider>
        <Consumer />
      </ToastProvider>,
    )
    const rendersAfterMount = onRender.mock.calls.length
    const api = onRender.mock.calls[0][0]

    let id = ''
    act(() => {
      id = api.addToast('first toast', 'info', 0)
    })
    expect(screen.getByText('first toast')).toBeInTheDocument()
    act(() => {
      api.showToast('second toast', 'success', 0)
    })
    expect(screen.getByText('second toast')).toBeInTheDocument()
    act(() => {
      api.removeToast(id)
    })
    expect(screen.queryByText('first toast')).not.toBeInTheDocument()

    expect(onRender).toHaveBeenCalledTimes(rendersAfterMount)
    const values = new Set(onRender.mock.calls.map(([value]) => value))
    expect(values.size).toBe(1)
  })
})

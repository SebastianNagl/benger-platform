'use client'

import { useI18n } from '@/contexts/I18nContext'
import { isDemoHost } from '@/lib/utils/subdomain'
import { XMarkIcon } from '@heroicons/react/24/outline'
import { useEffect, useState } from 'react'

/**
 * Small fixed badge shown on the demo environment hosts
 * (demo.what-a-benger.net / demo.vertretbar.net): tells visitors that the data
 * is showcase content and that self-serve accounts are wiped by the nightly
 * reset. Resolved from the hostname (never a build-time env var — one frontend
 * image serves prod, staging and demo), and only after mount so SSR output is
 * identical across environments.
 */
export function DemoEnvBadge() {
  const { locale } = useI18n()
  const [visible, setVisible] = useState(false)
  const [open, setOpen] = useState(false)

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- host is only known on the client
    setVisible(isDemoHost())
  }, [])

  if (!visible) return null

  const de = locale === 'de'
  const label = de ? 'Demo-Umgebung' : 'Demo environment'
  const body = de
    ? 'Diese Umgebung zeigt Beispielinhalte. Alle Änderungen und neu angelegten Konten werden jede Nacht um 4 Uhr zurückgesetzt.'
    : 'This environment shows sample content. All changes and newly created accounts are reset every night at 4 am (Berlin time).'

  return (
    <>
      <div className="fixed right-4 bottom-4 z-50">
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          className="flex items-center gap-2 rounded-full border border-sky-300 bg-sky-100 px-3 py-1.5 text-xs font-medium text-sky-800 shadow-sm transition-colors duration-200 hover:bg-sky-200 dark:border-sky-700 dark:bg-sky-900/80 dark:text-sky-200 dark:hover:bg-sky-800"
          title={body}
          aria-expanded={open}
        >
          <span className="h-2 w-2 rounded-full bg-sky-500 dark:bg-sky-400" />
          {label}
        </button>
      </div>
      {open && (
        <div className="fixed right-4 bottom-16 z-50">
          <div className="max-w-sm rounded-lg border border-gray-200 bg-white p-4 shadow-lg dark:border-zinc-700 dark:bg-zinc-800">
            <div className="mb-2 flex items-start justify-between gap-4">
              <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100">
                {label}
              </h3>
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="text-gray-400 hover:text-gray-500 dark:text-gray-500 dark:hover:text-gray-400"
                aria-label={de ? 'Schließen' : 'Close'}
              >
                <XMarkIcon className="h-4 w-4" />
              </button>
            </div>
            <p className="text-xs text-gray-600 dark:text-gray-400">{body}</p>
          </div>
        </div>
      )}
    </>
  )
}

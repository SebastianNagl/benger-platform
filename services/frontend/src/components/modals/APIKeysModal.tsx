'use client'

import { Dialog } from '@headlessui/react'
import { XMarkIcon } from '@heroicons/react/24/outline'
import { useEffect, useState } from 'react'

import UserApiKeys from '@/components/shared/UserApiKeys'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { organizationsAPI } from '@/lib/api/organizations'

interface APIKeysModalProps {
  isOpen: boolean
  onClose: () => void
}

export function APIKeysModal({ isOpen, onClose }: APIKeysModalProps) {
  const { t } = useI18n()
  const { currentOrganization } = useAuth()
  const [orgProvidesKeys, setOrgProvidesKeys] = useState(false)

  useEffect(() => {
    if (!isOpen || !currentOrganization) {
      setOrgProvidesKeys(false)
      return
    }

    organizationsAPI
      .getOrgApiKeySettings(currentOrganization.id)
      .then((data) => {
        setOrgProvidesKeys(!data.require_private_keys)
      })
      .catch(() => {
        setOrgProvidesKeys(false)
      })
  }, [isOpen, currentOrganization])

  return (
    <Dialog open={isOpen} onClose={onClose} className="relative z-50">
      {/* Backdrop */}
      <div className="fixed inset-0 bg-black/30" aria-hidden="true" />

      {/* Full-screen container to center the panel */}
      <div className="fixed inset-0 flex items-center justify-center p-4">
        <Dialog.Panel className="mx-auto w-full max-w-2xl rounded-lg bg-white shadow-xl dark:bg-zinc-800">
          {/* Header */}
          <div className="flex items-center justify-between border-b border-zinc-200 px-6 py-4 dark:border-zinc-700">
            <div>
              <Dialog.Title className="text-lg font-semibold text-zinc-900 dark:text-white">
                {t('profile.apiKeysManagement')}
              </Dialog.Title>
              <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
                {t('profile.apiKeysDescription')}
              </p>
            </div>
            <button
              onClick={onClose}
              className="rounded-md p-2 text-zinc-400 transition-colors hover:text-zinc-500 dark:text-zinc-500 dark:hover:text-zinc-400"
              aria-label={t('shared.alertDialog.close')}
            >
              <XMarkIcon className="h-5 w-5" />
            </button>
          </div>

          {/* Content */}
          <div className="max-h-[70vh] overflow-y-auto px-6 py-4">
            <UserApiKeys
              disabled={orgProvidesKeys}
              disabledMessage={
                orgProvidesKeys
                  ? `API keys are managed by your organization (${currentOrganization?.name}).`
                  : undefined
              }
            />
          </div>

          {/* Footer */}
          <div className="flex items-center justify-end border-t border-zinc-200 px-6 py-4 dark:border-zinc-700">
            <button
              onClick={onClose}
              className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-emerald-700 dark:bg-emerald-500 dark:hover:bg-emerald-600"
            >
              {t('common.done')}
            </button>
          </div>
        </Dialog.Panel>
      </div>
    </Dialog>
  )
}

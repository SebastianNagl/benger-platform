'use client'

import { Textarea } from '@/components/shared/Textarea'
import { useI18n } from '@/contexts/I18nContext'
import { User } from '@/lib/api/types'
import { Dialog, Transition } from '@headlessui/react'
import { CheckCircleIcon } from '@heroicons/react/24/outline'
import { Fragment, useState } from 'react'

interface EmailVerificationModalProps {
  isOpen: boolean
  onClose: () => void
  user: User | null
  action: 'verify'
  onConfirm: (reason?: string) => Promise<void>
}

export function EmailVerificationModal({
  isOpen,
  onClose,
  user,
  action,
  onConfirm,
}: EmailVerificationModalProps) {
  const { t } = useI18n()
  const [reason, setReason] = useState('')
  const [loading, setLoading] = useState(false)

  const handleConfirm = async () => {
    setLoading(true)
    try {
      await onConfirm(reason || undefined)
      onClose()
    } catch (error) {
      console.error('Failed to verify email:', error)
    } finally {
      setLoading(false)
      setReason('')
    }
  }

  return (
    <Transition appear show={isOpen} as={Fragment}>
      <Dialog as="div" className="relative z-50" onClose={onClose}>
        <Transition.Child
          as={Fragment}
          enter="ease-out duration-300"
          enterFrom="opacity-0"
          enterTo="opacity-100"
          leave="ease-in duration-200"
          leaveFrom="opacity-100"
          leaveTo="opacity-0"
        >
          <div className="fixed inset-0 bg-black/30 dark:bg-black/50" />
        </Transition.Child>

        <div className="fixed inset-0 overflow-y-auto">
          <div className="flex min-h-full items-center justify-center p-4 text-center">
            <Transition.Child
              as={Fragment}
              enter="ease-out duration-300"
              enterFrom="opacity-0 scale-95"
              enterTo="opacity-100 scale-100"
              leave="ease-in duration-200"
              leaveFrom="opacity-100 scale-100"
              leaveTo="opacity-0 scale-95"
            >
              <Dialog.Panel className="w-full max-w-md transform overflow-hidden rounded-2xl bg-white p-6 text-left align-middle shadow-xl transition-all dark:bg-zinc-800">
                <Dialog.Title
                  as="h3"
                  className="flex items-center gap-2 text-lg leading-6 font-semibold text-zinc-900 dark:text-zinc-100"
                >
                  <CheckCircleIcon className="h-5 w-5 text-emerald-500" />
                  {t('admin.emailVerificationModal.title')}
                </Dialog.Title>

                <div className="mt-4">
                  <p className="text-sm text-zinc-500 dark:text-zinc-400">
                    {t('admin.emailVerificationModal.confirmMessage')}{' '}
                    <span className="font-semibold">{user?.name}</span> (
                    {user?.email})?
                  </p>

                  <div className="mt-4">
                    <label
                      htmlFor="reason"
                      className="block text-sm font-medium text-zinc-700 dark:text-zinc-300"
                    >
                      {t('admin.emailVerificationModal.reasonLabel')}
                    </label>
                    <Textarea
                      id="reason"
                      rows={3}
                      className="mt-1"
                      placeholder={t(
                        'admin.emailVerificationModal.reasonPlaceholder',
                      )}
                      value={reason}
                      onChange={(e) => setReason(e.target.value)}
                    />
                  </div>
                </div>

                <div className="mt-6 flex justify-end gap-3">
                  <button
                    type="button"
                    className="inline-flex h-8 items-center justify-center rounded-full border border-zinc-300 bg-white px-4 text-sm font-medium text-zinc-700 hover:bg-zinc-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-2 dark:border-zinc-600 dark:bg-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-600 dark:focus-visible:ring-offset-zinc-900"
                    onClick={onClose}
                    disabled={loading}
                  >
                    {t('admin.emailVerificationModal.cancel')}
                  </button>
                  <button
                    type="button"
                    className={`inline-flex h-8 items-center justify-center rounded-full border border-transparent bg-zinc-900 px-4 text-sm font-medium text-white hover:bg-zinc-700 dark:bg-emerald-500 dark:hover:bg-emerald-400 ${loading ? 'cursor-not-allowed opacity-50' : ''} focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-zinc-900`}
                    onClick={handleConfirm}
                    disabled={loading}
                  >
                    {loading
                      ? t('admin.emailVerificationModal.processing')
                      : t('admin.emailVerificationModal.verifyEmail')}
                  </button>
                </div>
              </Dialog.Panel>
            </Transition.Child>
          </div>
        </div>
      </Dialog>
    </Transition>
  )
}

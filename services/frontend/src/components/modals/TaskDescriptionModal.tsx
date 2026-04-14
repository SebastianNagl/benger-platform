import { useI18n } from '@/contexts/I18nContext'
import { Dialog } from '@headlessui/react'
import { XMarkIcon } from '@heroicons/react/24/outline'
import { useEffect, useState } from 'react'

interface TaskDescriptionModalProps {
  isOpen: boolean
  onClose: () => void
  onSave: (description: string) => void
  initialValue?: string
}

export function TaskDescriptionModal({
  isOpen,
  onClose,
  onSave,
  initialValue = '',
}: TaskDescriptionModalProps) {
  const { t } = useI18n()
  const [description, setDescription] = useState(initialValue)

  // Update local state when initialValue changes
  useEffect(() => {
    setDescription(initialValue)
  }, [initialValue])

  const handleSave = () => {
    onSave(description.trim())
    onClose()
  }

  const handleCancel = () => {
    // Reset to initial value on cancel
    setDescription(initialValue)
    onClose()
  }

  return (
    <Dialog open={isOpen} onClose={handleCancel} className="relative z-50">
      {/* Backdrop */}
      <div className="fixed inset-0 bg-black/30" aria-hidden="true" />

      {/* Full-screen container to center the panel */}
      <div className="fixed inset-0 flex items-center justify-center p-4">
        <Dialog.Panel className="mx-auto w-full max-w-2xl rounded-lg bg-white shadow-xl dark:bg-zinc-800">
          {/* Header */}
          <div className="flex items-center justify-between border-b border-zinc-200 px-6 py-4 dark:border-zinc-700">
            <div>
              <Dialog.Title className="text-lg font-semibold text-zinc-900 dark:text-white">
                {t('modals.taskDescription.title')}
              </Dialog.Title>
              <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
                {t('modals.taskDescription.subtitle')}
              </p>
            </div>
            <button
              onClick={handleCancel}
              className="rounded-md p-2 text-zinc-400 transition-colors hover:text-zinc-500 dark:text-zinc-500 dark:hover:text-zinc-400"
              aria-label={t('shared.alertDialog.close')}
            >
              <XMarkIcon className="h-5 w-5" />
            </button>
          </div>

          {/* Content */}
          <div className="px-6 py-4">
            <div className="space-y-4">
              <div>
                <label
                  htmlFor="task-description"
                  className="mb-2 block text-sm font-medium text-zinc-900 dark:text-white"
                >
                  {t('modals.taskDescription.textareaLabel')}
                </label>
                <textarea
                  id="task-description"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  rows={6}
                  className="block w-full resize-none rounded-lg border border-zinc-300 bg-white px-3 py-2.5 text-zinc-900 transition-colors placeholder:text-zinc-500 focus:border-emerald-500 focus:ring-2 focus:ring-emerald-500/20 dark:border-zinc-600 dark:bg-zinc-800 dark:text-white dark:placeholder:text-zinc-400 dark:focus:border-emerald-400 dark:focus:ring-emerald-400/20 sm:text-sm"
                  placeholder={t('modals.taskDescription.textareaPlaceholder')}
                />
              </div>

              <div className="rounded-lg bg-blue-50 p-4 dark:bg-blue-900/20">
                <div className="flex">
                  <div className="flex-shrink-0">
                    <svg
                      className="h-5 w-5 text-blue-400"
                      viewBox="0 0 20 20"
                      fill="currentColor"
                    >
                      <path
                        fillRule="evenodd"
                        d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z"
                        clipRule="evenodd"
                      />
                    </svg>
                  </div>
                  <div className="ml-3">
                    <p className="text-sm text-blue-800 dark:text-blue-200">
                      <strong>{t('modals.taskDescription.tipsTitle')}</strong>
                    </p>
                    <ul className="mt-2 list-inside list-disc space-y-1 text-sm text-blue-700 dark:text-blue-300">
                      <li>{t('modals.taskDescription.tipItem1')}</li>
                      <li>{t('modals.taskDescription.tipItem2')}</li>
                      <li>{t('modals.taskDescription.tipItem3')}</li>
                      <li>{t('modals.taskDescription.tipItem4')}</li>
                    </ul>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Footer */}
          <div className="flex items-center justify-end gap-3 border-t border-zinc-200 px-6 py-4 dark:border-zinc-700">
            <button
              onClick={handleCancel}
              className="rounded-lg border border-zinc-300 bg-white px-4 py-2 text-sm font-medium text-zinc-700 transition-colors hover:bg-zinc-50 dark:border-zinc-600 dark:bg-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-600"
            >
              {t('modals.taskDescription.cancel')}
            </button>
            <button
              onClick={handleSave}
              className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-emerald-700 dark:bg-emerald-500 dark:hover:bg-emerald-600"
            >
              {t('modals.taskDescription.save')}
            </button>
          </div>
        </Dialog.Panel>
      </div>
    </Dialog>
  )
}

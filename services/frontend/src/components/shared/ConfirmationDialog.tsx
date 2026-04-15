'use client'

import { useI18n } from '@/contexts/I18nContext'
import { Dialog, Transition } from '@headlessui/react'
import {
  CheckCircleIcon,
  ExclamationTriangleIcon,
  InformationCircleIcon,
  XCircleIcon,
} from '@heroicons/react/24/outline'
import clsx from 'clsx'
import { Fragment } from 'react'
import { Button } from './Button'

interface ConfirmationDialogProps {
  isOpen: boolean
  onClose: () => void
  onConfirm: () => void
  title: string
  message: string
  confirmText?: string
  cancelText?: string
  variant?: 'warning' | 'danger' | 'info' | 'success'
  confirmButtonVariant?: 'primary' | 'filled' | 'outline'
}

const variantStyles = {
  warning: {
    icon: ExclamationTriangleIcon,
    iconColor: 'text-amber-600 dark:text-amber-400',
    iconBg: 'bg-amber-100 dark:bg-amber-900/30',
  },
  danger: {
    icon: XCircleIcon,
    iconColor: 'text-red-600 dark:text-red-400',
    iconBg: 'bg-red-100 dark:bg-red-900/30',
  },
  info: {
    icon: InformationCircleIcon,
    iconColor: 'text-blue-600 dark:text-blue-400',
    iconBg: 'bg-blue-100 dark:bg-blue-900/30',
  },
  success: {
    icon: CheckCircleIcon,
    iconColor: 'text-emerald-600 dark:text-emerald-400',
    iconBg: 'bg-emerald-100 dark:bg-emerald-900/30',
  },
}

export function ConfirmationDialog({
  isOpen,
  onClose,
  onConfirm,
  title,
  message,
  confirmText,
  cancelText,
  variant = 'warning',
  confirmButtonVariant = 'filled',
}: ConfirmationDialogProps) {
  const { t } = useI18n()
  const variantStyle = variantStyles[variant]
  const IconComponent = variantStyle.icon

  const displayConfirmText = confirmText ?? t('common.confirm')
  const displayCancelText = cancelText ?? t('common.cancel')

  const handleConfirm = () => {
    onConfirm()
    onClose()
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
          <div className="fixed inset-0 bg-black bg-opacity-25 dark:bg-opacity-40" />
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
              <Dialog.Panel className="w-full max-w-md transform overflow-hidden rounded-2xl border border-zinc-200 bg-white p-6 text-left align-middle shadow-xl transition-all dark:border-zinc-700 dark:bg-zinc-800">
                <div className="flex items-start">
                  <div
                    className={clsx(
                      'mx-auto flex h-12 w-12 flex-shrink-0 items-center justify-center rounded-full sm:mx-0 sm:h-10 sm:w-10',
                      variantStyle.iconBg
                    )}
                  >
                    <IconComponent
                      className={clsx('h-6 w-6', variantStyle.iconColor)}
                      aria-hidden="true"
                    />
                  </div>
                  <div className="ml-4 mt-0 w-full text-left">
                    <Dialog.Title
                      as="h3"
                      className="text-lg font-semibold leading-6 text-zinc-900 dark:text-white"
                    >
                      {title}
                    </Dialog.Title>
                    <div className="mt-2">
                      <p className="text-sm text-zinc-600 dark:text-zinc-300">
                        {message}
                      </p>
                    </div>
                  </div>
                </div>

                <div className="mt-6 flex justify-end gap-3">
                  <Button
                    variant="outline"
                    onClick={onClose}
                    className="px-4 py-2"
                    data-testid="confirm-dialog-cancel-button"
                  >
                    {displayCancelText}
                  </Button>
                  <Button
                    variant={confirmButtonVariant}
                    onClick={handleConfirm}
                    className="px-4 py-2"
                    data-testid="confirm-dialog-confirm-button"
                  >
                    {displayConfirmText}
                  </Button>
                </div>
              </Dialog.Panel>
            </Transition.Child>
          </div>
        </div>
      </Dialog>
    </Transition>
  )
}

'use client'

import { Dialog as HeadlessDialog, Transition } from '@headlessui/react'
import { XMarkIcon } from '@heroicons/react/24/outline'
import clsx from 'clsx'
import { Fragment, ReactNode } from 'react'

interface DialogProps {
  open?: boolean
  onOpenChange?: (open: boolean) => void
  isOpen?: boolean
  onClose?: () => void
  title?: string
  className?: string
  children: ReactNode
}

interface DialogContentProps {
  children: ReactNode
  className?: string
}

interface DialogHeaderProps {
  children: ReactNode
  className?: string
}

interface DialogTitleProps {
  children: ReactNode
  className?: string
}

interface DialogTriggerProps {
  children: ReactNode
  asChild?: boolean
}

export function Dialog({
  open,
  onOpenChange,
  isOpen,
  onClose,
  title,
  className,
  children,
}: DialogProps) {
  // Support both API styles
  const isDialogOpen = open ?? isOpen ?? false
  const handleClose = onOpenChange
    ? () => onOpenChange(false)
    : onClose || (() => {})

  return (
    <Transition appear show={isDialogOpen} as={Fragment}>
      <HeadlessDialog as="div" className="relative z-50" onClose={handleClose}>
        <Transition.Child
          as={Fragment}
          enter="ease-out duration-300"
          enterFrom="opacity-0"
          enterTo="opacity-100"
          leave="ease-in duration-200"
          leaveFrom="opacity-100"
          leaveTo="opacity-0"
        >
          <div className="fixed inset-0 bg-black bg-opacity-25" />
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
              <HeadlessDialog.Panel
                className={clsx(
                  'w-full max-w-md transform overflow-hidden rounded-2xl bg-white p-6 text-left align-middle shadow-xl transition-all dark:bg-gray-800',
                  className
                )}
              >
                {title && (
                  <div className="mb-4">
                    <HeadlessDialog.Title
                      as="h3"
                      className="text-lg font-medium leading-6 text-gray-900 dark:text-white"
                    >
                      {title}
                    </HeadlessDialog.Title>
                    <button
                      onClick={handleClose}
                      className="absolute right-4 top-4 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
                    >
                      <XMarkIcon className="h-5 w-5" />
                    </button>
                  </div>
                )}
                {children}
              </HeadlessDialog.Panel>
            </Transition.Child>
          </div>
        </div>
      </HeadlessDialog>
    </Transition>
  )
}

export function DialogContent({ children, className }: DialogContentProps) {
  return (
    <HeadlessDialog.Panel
      className={clsx(
        'w-full max-w-md transform overflow-hidden rounded-2xl bg-white p-6 text-left align-middle shadow-xl transition-all dark:bg-gray-800',
        className
      )}
    >
      {children}
    </HeadlessDialog.Panel>
  )
}

export function DialogHeader({ children, className }: DialogHeaderProps) {
  return <div className={clsx('mb-4', className)}>{children}</div>
}

export function DialogTitle({ children, className }: DialogTitleProps) {
  return (
    <HeadlessDialog.Title
      as="h3"
      className={clsx(
        'text-lg font-medium leading-6 text-gray-900 dark:text-white',
        className
      )}
    >
      {children}
    </HeadlessDialog.Title>
  )
}

export function DialogTrigger({ children, asChild }: DialogTriggerProps) {
  // Simple implementation - in a real app you'd want to clone the child and add click handler
  return <>{children}</>
}

'use client'

import { AlertDialog } from '@/components/shared/AlertDialog'
import { ConfirmationDialog } from '@/components/shared/ConfirmationDialog'
import {
  createContext,
  ReactNode,
  useCallback,
  useContext,
  useState,
} from 'react'

interface AlertOptions {
  title: string
  message: string
  buttonText?: string
  variant?: 'success' | 'error' | 'warning' | 'info'
}

interface ConfirmOptions {
  title: string
  message: string
  confirmText?: string
  cancelText?: string
  variant?: 'warning' | 'danger' | 'info' | 'success'
  confirmButtonVariant?: 'primary' | 'filled' | 'outline'
}

interface DialogContextType {
  alert: (options: AlertOptions) => Promise<void>
  confirm: (options: ConfirmOptions) => Promise<boolean>
}

const DialogContext = createContext<DialogContextType | null>(null)

interface DialogState {
  type: 'alert' | 'confirm' | null
  options: AlertOptions | ConfirmOptions | null
  resolve: ((value: any) => void) | null
}

export function DialogProvider({ children }: { children: ReactNode }) {
  const [dialogState, setDialogState] = useState<DialogState>({
    type: null,
    options: null,
    resolve: null,
  })

  const alert = useCallback((options: AlertOptions): Promise<void> => {
    return new Promise((resolve) => {
      setDialogState({
        type: 'alert',
        options,
        resolve,
      })
    })
  }, [])

  const confirm = useCallback((options: ConfirmOptions): Promise<boolean> => {
    return new Promise((resolve) => {
      setDialogState({
        type: 'confirm',
        options,
        resolve,
      })
    })
  }, [])

  const handleClose = useCallback(() => {
    if (dialogState.resolve) {
      if (dialogState.type === 'alert') {
        dialogState.resolve(undefined)
      } else if (dialogState.type === 'confirm') {
        dialogState.resolve(false)
      }
    }
    setDialogState({ type: null, options: null, resolve: null })
  }, [dialogState])

  const handleConfirm = useCallback(() => {
    if (dialogState.resolve && dialogState.type === 'confirm') {
      dialogState.resolve(true)
    }
    setDialogState({ type: null, options: null, resolve: null })
  }, [dialogState])

  const value: DialogContextType = {
    alert,
    confirm,
  }

  return (
    <DialogContext.Provider value={value}>
      {children}

      {dialogState.type === 'alert' && dialogState.options && (
        <AlertDialog
          isOpen={true}
          onClose={handleClose}
          {...(dialogState.options as AlertOptions)}
        />
      )}

      {dialogState.type === 'confirm' && dialogState.options && (
        <ConfirmationDialog
          isOpen={true}
          onClose={handleClose}
          onConfirm={handleConfirm}
          {...(dialogState.options as ConfirmOptions)}
        />
      )}
    </DialogContext.Provider>
  )
}

export function useAlert() {
  const context = useContext(DialogContext)
  if (!context) {
    throw new Error('useAlert must be used within a DialogProvider')
  }
  return context.alert
}

export function useConfirm() {
  const context = useContext(DialogContext)
  if (!context) {
    throw new Error('useConfirm must be used within a DialogProvider')
  }
  return context.confirm
}

// Convenience hooks with pre-configured variants
export function useErrorAlert() {
  const alert = useAlert()
  return useCallback(
    (message: string, title: string = 'Error') => {
      return alert({
        title,
        message,
        variant: 'error',
      })
    },
    [alert]
  )
}

export function useSuccessAlert() {
  const alert = useAlert()
  return useCallback(
    (message: string, title: string = 'Success') => {
      return alert({
        title,
        message,
        variant: 'success',
      })
    },
    [alert]
  )
}

export function useWarningAlert() {
  const alert = useAlert()
  return useCallback(
    (message: string, title: string = 'Warning') => {
      return alert({
        title,
        message,
        variant: 'warning',
      })
    },
    [alert]
  )
}

export function useDeleteConfirm() {
  const confirm = useConfirm()
  return useCallback(
    (itemName: string = 'this item') => {
      return confirm({
        title: 'Confirm Deletion',
        message: `Are you sure you want to delete ${itemName}? This action cannot be undone.`,
        confirmText: 'Delete',
        cancelText: 'Cancel',
        variant: 'danger',
        confirmButtonVariant: 'filled',
      })
    },
    [confirm]
  )
}

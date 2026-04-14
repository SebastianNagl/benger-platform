'use client'

import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { Dialog, DialogBackdrop, DialogPanel } from '@headlessui/react'
import React, { useState } from 'react'

interface SignupModalProps {
  isOpen: boolean
  onClose: () => void
}

export function SignupModal({ isOpen, onClose }: SignupModalProps) {
  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [name, setName] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const { signup } = useAuth()
  const { t } = useI18n()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setIsLoading(true)
    setError(null)

    // Validation
    if (password !== confirmPassword) {
      setError(t('signupModal.passwordMismatch'))
      setIsLoading(false)
      return
    }

    if (password.length < 6) {
      setError(t('signupModal.passwordLength'))
      setIsLoading(false)
      return
    }

    try {
      await signup(username, email, name, password)
      onClose()
      setUsername('')
      setEmail('')
      setName('')
      setPassword('')
      setConfirmPassword('')
    } catch (err) {
      setError(err instanceof Error ? err.message : t('signupModal.signupFailed'))
    } finally {
      setIsLoading(false)
    }
  }

  const handleClose = () => {
    if (!isLoading) {
      onClose()
      setUsername('')
      setEmail('')
      setName('')
      setPassword('')
      setConfirmPassword('')
      setError(null)
    }
  }

  return (
    <Dialog open={isOpen} onClose={handleClose} className="relative z-50">
      <DialogBackdrop className="fixed inset-0 bg-black/50" />

      <div className="fixed inset-0 flex items-center justify-center p-4">
        <DialogPanel className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl dark:bg-zinc-900">
          <div className="mb-6">
            <h2 className="text-xl font-semibold text-zinc-900 dark:text-white">
              {t('signupModal.title')}
            </h2>
            <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
              {t('signupModal.subtitle')}
            </p>
          </div>

          {error && (
            <div className="mb-4 rounded-md border border-red-200 bg-red-50 p-3 dark:border-red-800 dark:bg-red-950/50">
              <p className="text-sm text-red-800 dark:text-red-200">{error}</p>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label
                htmlFor="name"
                className="block text-sm font-medium text-zinc-700 dark:text-zinc-300"
              >
                {t('signupModal.fullName')}
              </label>
              <input
                id="name"
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                disabled={isLoading}
                autoComplete="name"
                className="mt-1 block w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-zinc-900 placeholder-zinc-400 shadow-sm focus:border-emerald-500 focus:outline-none focus:ring-emerald-500 disabled:opacity-50 dark:border-zinc-600 dark:bg-zinc-800 dark:text-white"
                placeholder={t('signupModal.fullNamePlaceholder')}
              />
            </div>

            <div>
              <label
                htmlFor="email"
                className="block text-sm font-medium text-zinc-700 dark:text-zinc-300"
              >
                {t('signupModal.emailAddress')}
              </label>
              <input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                disabled={isLoading}
                autoComplete="email"
                className="mt-1 block w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-zinc-900 placeholder-zinc-400 shadow-sm focus:border-emerald-500 focus:outline-none focus:ring-emerald-500 disabled:opacity-50 dark:border-zinc-600 dark:bg-zinc-800 dark:text-white"
                placeholder={t('signupModal.emailPlaceholder')}
              />
            </div>

            <div>
              <label
                htmlFor="username"
                className="block text-sm font-medium text-zinc-700 dark:text-zinc-300"
              >
                {t('signupModal.username')}
              </label>
              <input
                id="username"
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
                disabled={isLoading}
                autoComplete="username"
                className="mt-1 block w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-zinc-900 placeholder-zinc-400 shadow-sm focus:border-emerald-500 focus:outline-none focus:ring-emerald-500 disabled:opacity-50 dark:border-zinc-600 dark:bg-zinc-800 dark:text-white"
                placeholder={t('signupModal.usernamePlaceholder')}
              />
            </div>

            <div>
              <label
                htmlFor="password"
                className="block text-sm font-medium text-zinc-700 dark:text-zinc-300"
              >
                {t('signupModal.password')}
              </label>
              <input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                disabled={isLoading}
                autoComplete="new-password"
                className="mt-1 block w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-zinc-900 placeholder-zinc-400 shadow-sm focus:border-emerald-500 focus:outline-none focus:ring-emerald-500 disabled:opacity-50 dark:border-zinc-600 dark:bg-zinc-800 dark:text-white"
                placeholder={t('signupModal.passwordPlaceholder')}
              />
            </div>

            <div>
              <label
                htmlFor="confirmPassword"
                className="block text-sm font-medium text-zinc-700 dark:text-zinc-300"
              >
                {t('signupModal.confirmPassword')}
              </label>
              <input
                id="confirmPassword"
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                required
                disabled={isLoading}
                autoComplete="new-password"
                className="mt-1 block w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-zinc-900 placeholder-zinc-400 shadow-sm focus:border-emerald-500 focus:outline-none focus:ring-emerald-500 disabled:opacity-50 dark:border-zinc-600 dark:bg-zinc-800 dark:text-white"
                placeholder={t('signupModal.confirmPasswordPlaceholder')}
              />
            </div>

            <div className="flex gap-3 pt-4">
              <button
                type="button"
                onClick={handleClose}
                disabled={isLoading}
                className="flex-1 rounded-md border border-zinc-300 px-4 py-2 text-zinc-700 transition-colors hover:bg-zinc-50 disabled:opacity-50 dark:border-zinc-600 dark:text-zinc-300 dark:hover:bg-zinc-800"
              >
                {t('signupModal.cancel')}
              </button>
              <button
                type="submit"
                disabled={
                  isLoading ||
                  !username ||
                  !email ||
                  !name ||
                  !password ||
                  !confirmPassword
                }
                className="flex-1 rounded-md bg-emerald-500 px-4 py-2 text-white transition-colors hover:bg-emerald-600 disabled:bg-emerald-300"
              >
                {isLoading ? t('signupModal.creating') : t('signupModal.createAccount')}
              </button>
            </div>
          </form>

          <div className="mt-4 border-t border-zinc-200 pt-4 dark:border-zinc-700">
            <p className="text-center text-xs text-zinc-500 dark:text-zinc-400">
              {t('signupModal.defaultRole')}
            </p>
          </div>
        </DialogPanel>
      </div>
    </Dialog>
  )
}

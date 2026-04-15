'use client'

import { useHydration } from '@/contexts/HydrationContext'
import { useI18n } from '@/contexts/I18nContext'
import { useEffect, useMemo, useState, useSyncExternalStore } from 'react'

interface RotatingTextProps {
  words: string[]
  interval?: number
  className?: string
}

// Subscribe/getSnapshot for reduced motion media query
const reducedMotionQuery = '(prefers-reduced-motion: reduce)'

function subscribeToReducedMotion(callback: () => void) {
  if (typeof window === 'undefined') return () => {}
  const mediaQuery = window.matchMedia(reducedMotionQuery)
  mediaQuery.addEventListener('change', callback)
  return () => mediaQuery.removeEventListener('change', callback)
}

function getReducedMotionSnapshot() {
  if (typeof window === 'undefined') return false
  return window.matchMedia(reducedMotionQuery).matches
}

function getReducedMotionServerSnapshot() {
  return false
}

export function RotatingText({
  words,
  interval = 2000,
  className = '',
}: RotatingTextProps) {
  const { t } = useI18n()
  const [currentWordIndex, setCurrentWordIndex] = useState(0)
  const mounted = useHydration()

  // Use useSyncExternalStore for media query
  const prefersReducedMotion = useSyncExternalStore(
    subscribeToReducedMotion,
    getReducedMotionSnapshot,
    getReducedMotionServerSnapshot
  )

  // Ensure words is always an array
  const safeWords = useMemo(
    () => (Array.isArray(words) ? words : []),
    [words]
  )

  // Handle word rotation
  useEffect(() => {
    // Don't start rotation until mounted and we have words
    if (
      !mounted ||
      !safeWords ||
      safeWords.length <= 1 ||
      prefersReducedMotion
    ) {
      return
    }

    const intervalId = setInterval(() => {
      setCurrentWordIndex((prevIndex) => (prevIndex + 1) % safeWords.length)
    }, interval)

    return () => clearInterval(intervalId)
  }, [safeWords, interval, prefersReducedMotion, mounted])

  if (!safeWords || safeWords.length === 0) {
    return <span className={className}>{t('landing.rotatingText.loading')}</span>
  }

  // Don't use aria-live if there's only one word or reduced motion is preferred
  const shouldRotate = mounted && !prefersReducedMotion && safeWords.length > 1

  return (
    <span
      className={`inline-block ${className}`}
      aria-live={shouldRotate ? 'polite' : 'off'}
      aria-label={!shouldRotate ? safeWords.join(', ') : undefined}
    >
      {safeWords[currentWordIndex]}
    </span>
  )
}

/**
 * Likert Scale Human Evaluation Interface
 *
 * Interface for human evaluators to rate LLM responses using Likert scales
 * across multiple dimensions (accuracy, clarity, relevance, completeness)
 *
 * Issue #483: Comprehensive evaluation configuration system
 */

'use client'

import { Badge } from '@/components/shared/Badge'
import { Button } from '@/components/shared/Button'
import { Card } from '@/components/shared/Card'
import { LoadingSpinner } from '@/components/shared/LoadingSpinner'
import { useToast } from '@/components/shared/Toast'
import { useI18n } from '@/contexts/I18nContext'
import { apiClient } from '@/lib/api/client'
import {
  ArrowRightIcon,
  CheckCircleIcon,
  StarIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline'
import { StarIcon as StarIconSolid } from '@heroicons/react/24/solid'
import { useRouter, useSearchParams } from 'next/navigation'
import { useEffect, useState } from 'react'

interface EvaluationItem {
  id: string
  task_data: any
  response_content: string
  model_id: string
}

interface LikertDimension {
  id: string
  name: string
  description: string
}

interface EvaluationSession {
  id: string
  project_id: string
  project_name: string
  total_items: number
  evaluated_items: number
  dimensions: LikertDimension[]
}

// Default dimensions will use i18n keys
const getDefaultDimensions = (t: any): LikertDimension[] => [
  {
    id: 'accuracy',
    name: t('evaluation.human.likert.accuracy'),
    description: t('evaluation.human.likert.criterion'),
  },
  {
    id: 'clarity',
    name: t('evaluation.human.likert.clarity'),
    description: t('evaluation.human.likert.criterion'),
  },
  {
    id: 'relevance',
    name: t('evaluation.human.likert.relevance'),
    description: t('evaluation.human.likert.criterion'),
  },
  {
    id: 'completeness',
    name: t('evaluation.human.likert.completeness'),
    description: t('evaluation.human.likert.criterion'),
  },
]

export default function LikertEvaluation() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const projectId = searchParams?.get('project')
  const sessionId = searchParams?.get('session')

  const { t } = useI18n()
  const { addToast } = useToast()
  const [loading, setLoading] = useState(true)
  const [session, setSession] = useState<EvaluationSession | null>(null)
  const [currentItem, setCurrentItem] = useState<EvaluationItem | null>(null)
  const [ratings, setRatings] = useState<Record<string, number>>({})
  const [submitting, setSubmitting] = useState(false)
  const [showCompletion, setShowCompletion] = useState(false)

  useEffect(() => {
    if (sessionId) {
      loadSession(sessionId)
    } else if (projectId) {
      createNewSession(projectId)
    } else {
      addToast(t('toasts.humanEvaluation.noProjectOrSession'), 'error')
      router.push('/evaluations')
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, projectId])

  const createNewSession = async (projectId: string) => {
    try {
      const response = await apiClient.post(
        '/evaluations/human/session/start',
        {
          project_id: projectId,
          session_type: 'likert',
          dimensions: getDefaultDimensions(t),
        }
      )

      const newSession = response.data
      setSession(newSession)

      // Update URL with session ID
      router.replace(`/evaluations/human/likert?session=${newSession.id}`)

      // Load first item
      loadNextItem(newSession.id)
    } catch (error) {
      console.error('Failed to create session:', error)
      addToast(t('toasts.humanEvaluation.sessionCreateFailed'), 'error')
      router.push('/evaluations')
    }
  }

  const loadSession = async (sessionId: string) => {
    try {
      const response = await apiClient.get(
        `/evaluations/human/session/${sessionId}`
      )
      setSession(response.data)

      // Load next item
      loadNextItem(sessionId)
    } catch (error) {
      console.error('Failed to load session:', error)
      addToast(t('toasts.humanEvaluation.sessionLoadFailed'), 'error')
      router.push('/evaluations')
    }
  }

  const loadNextItem = async (sessionId: string) => {
    setLoading(true)
    try {
      const response = await apiClient.get(
        `/evaluations/human/session/${sessionId}/next`
      )

      if (response.data.completed) {
        setShowCompletion(true)
      } else {
        setCurrentItem(response.data.item)
        // Reset ratings for new item
        setRatings({})
      }
    } catch (error) {
      console.error('Failed to load next item:', error)
      addToast(t('toasts.humanEvaluation.itemLoadFailed'), 'error')
    } finally {
      setLoading(false)
    }
  }

  const submitRatings = async () => {
    if (!session || !currentItem) return

    // Validate all dimensions are rated
    const missingRatings =
      session.dimensions?.filter((d) => !ratings[d.id]) || []
    if (missingRatings.length > 0) {
      addToast(
        t('evaluations.human.likert.rateAllDimensions', { dimensions: missingRatings.map((d) => d.name).join(', ') }),
        'error'
      )
      return
    }

    setSubmitting(true)
    try {
      await apiClient.post(`/evaluations/human/session/${session.id}/submit`, {
        item_id: currentItem.id,
        evaluation_type: 'likert',
        ratings: ratings,
        metadata: {
          model_id: currentItem.model_id,
          response_length: currentItem.response_content.length,
        },
      })

      // Update session progress
      if (session) {
        setSession({
          ...session,
          evaluated_items: session.evaluated_items + 1,
        })
      }

      // Load next item
      loadNextItem(session.id)
    } catch (error) {
      console.error('Failed to submit ratings:', error)
      addToast(t('toasts.humanEvaluation.submitFailed'), 'error')
    } finally {
      setSubmitting(false)
    }
  }

  const skipItem = async () => {
    if (!session) return

    setLoading(true)
    try {
      await apiClient.post(`/evaluations/human/session/${session.id}/skip`, {
        item_id: currentItem?.id,
      })

      // Load next item
      loadNextItem(session.id)
    } catch (error) {
      console.error('Failed to skip item:', error)
      addToast(t('toasts.humanEvaluation.skipFailed'), 'error')
      setLoading(false)
    }
  }

  const renderStarRating = (dimension: LikertDimension) => {
    const rating = ratings[dimension.id] || 0

    return (
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <label className="text-sm font-medium">{dimension.name}</label>
          <span className="text-xs text-gray-500">
            {rating > 0 ? `${rating}/5` : t('evaluations.human.likert.notRated')}
          </span>
        </div>
        <p className="text-xs text-gray-600">{dimension.description}</p>
        <div className="flex space-x-1">
          {[1, 2, 3, 4, 5].map((star) => (
            <button
              key={star}
              onClick={() => setRatings({ ...ratings, [dimension.id]: star })}
              className="p-1 transition-transform hover:scale-110"
              aria-label={t('evaluations.human.likert.rateStars', { count: String(star) })}
            >
              {star <= rating ? (
                <StarIconSolid className="h-8 w-8 text-yellow-400" />
              ) : (
                <StarIcon className="h-8 w-8 text-gray-300 hover:text-yellow-200" />
              )}
            </button>
          ))}
        </div>
      </div>
    )
  }

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <LoadingSpinner />
      </div>
    )
  }

  if (showCompletion) {
    return (
      <>
        <div className="container mx-auto max-w-4xl px-4 py-8">
          <Card className="p-8 text-center">
            <CheckCircleIcon className="mx-auto mb-4 h-16 w-16 text-green-500" />
            <h2 className="mb-2 text-2xl font-bold">
              {t('evaluation.human.likert.complete')}
            </h2>
            <p className="mb-6 text-gray-600">
              {t('evaluation.human.likert.description')}
            </p>
            <div className="mb-6 space-y-2">
              <p className="text-sm">
                <span className="font-medium">{t('evaluations.human.likert.projectLabel')}:</span>{' '}
                {session?.project_name}
              </p>
              <p className="text-sm">
                <span className="font-medium">{t('evaluations.human.likert.itemsEvaluated')}:</span>{' '}
                {session?.evaluated_items}
              </p>
            </div>
            <Button onClick={() => router.push('/evaluations')}>
              {t('evaluation.human.preference.next')}
            </Button>
          </Card>
        </div>
      </>
    )
  }

  return (
    <>
      <div className="container mx-auto px-4 py-8">
        {/* Progress Header */}
        <div className="mb-6">
          <div className="mb-2 flex items-center justify-between">
            <h1 className="text-2xl font-bold">
              {t('evaluation.human.likert.title')}
            </h1>
            <Button
              variant="outline"
              onClick={() => router.push('/evaluations')}
            >
              <XMarkIcon className="mr-2 h-4 w-4" />
              {t('evaluations.human.likert.exit')}
            </Button>
          </div>
          {session && (
            <div>
              <div className="mb-2 flex items-center justify-between text-sm text-gray-600">
                <span>{session.project_name}</span>
                <span>
                  {t('evaluation.human.preference.progress')}:{' '}
                  {session.evaluated_items + 1} / {session.total_items}
                </span>
              </div>
              <div className="h-2 w-full rounded-full bg-gray-200">
                <div
                  className="h-2 rounded-full bg-blue-600 transition-all"
                  style={{
                    width: `${((session.evaluated_items + 1) / session.total_items) * 100}%`,
                  }}
                />
              </div>
            </div>
          )}
        </div>

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          {/* Task and Response */}
          <div className="space-y-4">
            <Card className="p-6">
              <h3 className="mb-3 font-medium">{t('evaluations.human.likert.taskData')}</h3>
              <div className="rounded-lg bg-gray-50 p-4">
                <pre className="whitespace-pre-wrap text-sm">
                  {currentItem &&
                    JSON.stringify(currentItem.task_data, null, 2)}
                </pre>
              </div>
            </Card>

            <Card className="p-6">
              <div className="mb-3 flex items-center justify-between">
                <h3 className="font-medium">{t('evaluations.human.likert.modelResponse')}</h3>
                <Badge variant="outline">{currentItem?.model_id}</Badge>
              </div>
              <div className="rounded-lg bg-blue-50 p-4">
                <p className="whitespace-pre-wrap text-sm">
                  {currentItem?.response_content}
                </p>
              </div>
            </Card>
          </div>

          {/* Rating Controls */}
          <div className="space-y-4">
            <Card className="p-6">
              <h3 className="mb-4 font-medium">{t('evaluations.human.likert.rateResponse')}</h3>
              <div className="space-y-6">
                {session?.dimensions?.map((dimension) => (
                  <div key={dimension.id}>{renderStarRating(dimension)}</div>
                ))}
              </div>
            </Card>

            {/* Action Buttons */}
            <div className="flex gap-3">
              <Button
                onClick={skipItem}
                variant="outline"
                className="flex-1"
                disabled={submitting}
              >
                {t('evaluations.human.likert.skip')}
              </Button>
              <Button
                onClick={submitRatings}
                className="flex-1"
                disabled={submitting || Object.keys(ratings).length === 0}
              >
                {submitting ? (
                  <LoadingSpinner className="h-4 w-4" />
                ) : (
                  <>
                    {t('evaluation.human.preference.submit')}
                    <ArrowRightIcon className="ml-2 h-4 w-4" />
                  </>
                )}
              </Button>
            </div>

            {/* Instructions */}
            <Card className="border-yellow-200 bg-yellow-50 p-4">
              <h4 className="mb-2 text-sm font-medium">{t('evaluations.human.likert.ratingGuidelines')}</h4>
              <ul className="space-y-1 text-xs text-gray-600">
                <li>• {t('evaluations.human.likert.guidelineRate')}</li>
                <li>• {t('evaluations.human.likert.guidelineConsider')}</li>
                <li>• {t('evaluations.human.likert.guidelineConsistent')}</li>
                <li>• {t('evaluations.human.likert.guidelineSkip')}</li>
              </ul>
            </Card>
          </div>
        </div>
      </div>
    </>
  )
}

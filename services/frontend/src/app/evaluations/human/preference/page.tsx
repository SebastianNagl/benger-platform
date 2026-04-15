/**
 * Preference Ranking Human Evaluation Interface
 *
 * Interface for blind preference ranking where evaluators compare
 * anonymized responses from different models
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
  EqualsIcon,
  EyeSlashIcon,
  TrophyIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline'
import { useRouter, useSearchParams } from 'next/navigation'
import { useEffect, useState } from 'react'

interface PreferenceItem {
  id: string
  task_data: any
  responses: Array<{
    id: string
    content: string
    anonymized_id: string // e.g., "Response A", "Response B"
  }>
}

interface EvaluationSession {
  id: string
  project_id: string
  project_name: string
  total_items: number
  evaluated_items: number
  allow_ties: boolean
}

export default function PreferenceEvaluation() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const projectId = searchParams?.get('project')
  const sessionId = searchParams?.get('session')

  const { t } = useI18n()
  const { addToast } = useToast()
  const [loading, setLoading] = useState(true)
  const [session, setSession] = useState<EvaluationSession | null>(null)
  const [currentItem, setCurrentItem] = useState<PreferenceItem | null>(null)
  const [ranking, setRanking] = useState<string[]>([])
  const [selectedWinner, setSelectedWinner] = useState<string | null>(null)
  const [isTie, setIsTie] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [showCompletion, setShowCompletion] = useState(false)
  const [revealIdentities, setRevealIdentities] = useState(false)

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
          session_type: 'preference',
          config: {
            allow_ties: true,
            anonymize_sources: true,
          },
        }
      )

      const newSession = response.data
      setSession(newSession)

      // Update URL with session ID
      router.replace(`/evaluations/human/preference?session=${newSession.id}`)

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
    setRevealIdentities(false)
    setSelectedWinner(null)
    setIsTie(false)
    setRanking([])

    try {
      const response = await apiClient.get(
        `/evaluations/human/session/${sessionId}/next`
      )

      if (response.data.completed) {
        setShowCompletion(true)
      } else {
        setCurrentItem(response.data.item)
      }
    } catch (error) {
      console.error('Failed to load next item:', error)
      addToast(t('toasts.humanEvaluation.itemLoadFailed'), 'error')
    } finally {
      setLoading(false)
    }
  }

  const selectWinner = (responseId: string) => {
    if (isTie) {
      setIsTie(false)
    }
    setSelectedWinner(responseId)

    // Set ranking based on winner
    const winner = responseId
    const loser = currentItem?.responses.find((r) => r.id !== responseId)?.id
    if (loser) {
      setRanking([winner, loser])
    }
  }

  const selectTie = () => {
    setIsTie(true)
    setSelectedWinner(null)

    // For ties, both responses get the same rank
    if (currentItem) {
      setRanking(currentItem.responses.map((r) => r.id))
    }
  }

  const submitPreference = async () => {
    if (!session || !currentItem) return

    if (!selectedWinner && !isTie) {
      addToast(t('toasts.humanEvaluation.selectWinner'), 'error')
      return
    }

    setSubmitting(true)
    try {
      await apiClient.post(`/evaluations/human/session/${session.id}/submit`, {
        item_id: currentItem.id,
        evaluation_type: 'preference',
        preference_data: {
          winner: selectedWinner,
          is_tie: isTie,
          ranking: ranking,
          response_ids: currentItem.responses.map((r) => r.id),
        },
        metadata: {
          evaluation_time: Date.now(),
          revealed_identities: revealIdentities,
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
      console.error('Failed to submit preference:', error)
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
              {t('evaluation.human.preference.complete')}
            </h2>
            <p className="mb-6 text-gray-600">
              {t('evaluation.human.preference.completionDescription')}
            </p>
            <div className="mb-6 space-y-2">
              <p className="text-sm">
                <span className="font-medium">{t('evaluations.human.preference.projectLabel')}:</span>{' '}
                {session?.project_name}
              </p>
              <p className="text-sm">
                <span className="font-medium">{t('evaluations.human.preference.itemsEvaluated')}:</span>{' '}
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
            <div>
              <h1 className="text-2xl font-bold">
                {t('evaluation.human.preference.title')}
              </h1>
              <div className="mt-1 flex items-center text-sm text-gray-600">
                <EyeSlashIcon className="mr-1 h-4 w-4" />
                <span>{t('evaluation.human.preference.description')}</span>
              </div>
            </div>
            <Button
              variant="outline"
              onClick={() => router.push('/evaluations')}
            >
              <XMarkIcon className="mr-2 h-4 w-4" />
              {t('evaluations.human.preference.exit')}
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

        {/* Task Display */}
        <Card className="mb-6 p-6">
          <h3 className="mb-3 font-medium">{t('evaluations.human.preference.task')}</h3>
          <div className="rounded-lg bg-gray-50 p-4">
            <pre className="whitespace-pre-wrap text-sm">
              {currentItem && JSON.stringify(currentItem.task_data, null, 2)}
            </pre>
          </div>
        </Card>

        {/* Response Comparison */}
        <div className="mb-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
          {currentItem?.responses.map((response, index) => (
            <Card
              key={response.id}
              className={`cursor-pointer p-6 transition-all ${
                selectedWinner === response.id
                  ? 'bg-green-50 ring-2 ring-green-500'
                  : isTie
                    ? 'bg-blue-50 ring-2 ring-blue-500'
                    : 'hover:shadow-lg'
              }`}
              onClick={() => !isTie && selectWinner(response.id)}
            >
              <div className="mb-3 flex items-center justify-between">
                <Badge variant="outline" className="px-3 py-1 text-lg">
                  {response.anonymized_id}
                </Badge>
                {selectedWinner === response.id && (
                  <TrophyIcon className="h-6 w-6 text-green-500" />
                )}
                {isTie && <EqualsIcon className="h-6 w-6 text-blue-500" />}
              </div>
              <div className="rounded-lg border bg-white p-4">
                <p className="whitespace-pre-wrap text-sm">
                  {response.content}
                </p>
              </div>
            </Card>
          ))}
        </div>

        {/* Selection Controls */}
        <Card className="mb-6 p-6">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="font-medium">{t('evaluations.human.preference.yourSelection')}</h3>
            {session?.allow_ties && (
              <Button
                variant={isTie ? 'primary' : 'outline'}
                onClick={selectTie}
              >
                <EqualsIcon className="mr-2 h-4 w-4" />
                {t('evaluation.human.preference.equal')}
              </Button>
            )}
          </div>

          {selectedWinner && !isTie && (
            <div className="rounded-lg border border-green-200 bg-green-50 p-4">
              <p className="text-sm">
                <span className="font-medium">
                  {t('evaluation.human.preference.prefer')}:
                </span>{' '}
                {
                  currentItem?.responses.find((r) => r.id === selectedWinner)
                    ?.anonymized_id
                }
              </p>
            </div>
          )}

          {isTie && (
            <div className="rounded-lg border border-blue-200 bg-blue-50 p-4">
              <p className="text-sm">
                {t('evaluation.human.preference.equalDescription')}
              </p>
            </div>
          )}

          {!selectedWinner && !isTie && (
            <div className="rounded-lg border border-gray-200 bg-gray-50 p-4">
              <p className="text-sm text-gray-600">
                {t('evaluation.human.preference.instructions')}
              </p>
            </div>
          )}
        </Card>

        {/* Action Buttons */}
        <div className="mb-6 flex gap-3">
          <Button
            onClick={() => setRevealIdentities(!revealIdentities)}
            variant="outline"
          >
            {revealIdentities ? t('evaluations.human.preference.hideModelNames') : t('evaluations.human.preference.revealModelNames')}
          </Button>
          <div className="flex-1" />
          <Button onClick={skipItem} variant="outline" disabled={submitting}>
            {t('evaluations.human.preference.skip')}
          </Button>
          <Button
            onClick={submitPreference}
            disabled={submitting || (!selectedWinner && !isTie)}
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
          <h4 className="mb-2 text-sm font-medium">{t('evaluations.human.preference.guidelines')}</h4>
          <ul className="space-y-1 text-xs text-gray-600">
            <li>• {t('evaluations.human.preference.guidelineAnonymized')}</li>
            <li>• {t('evaluations.human.preference.guidelineClick')}</li>
            <li>• {t('evaluations.human.preference.guidelineConsider')}</li>
            <li>• {t('evaluations.human.preference.guidelineTie')}</li>
            <li>• {t('evaluations.human.preference.guidelineReveal')}</li>
          </ul>
        </Card>

        {/* Model Identity Reveal (if enabled) */}
        {revealIdentities && currentItem && (
          <Card className="mt-4 border-purple-200 bg-purple-50 p-4">
            <h4 className="mb-2 text-sm font-medium">{t('evaluations.human.preference.modelIdentities')}</h4>
            <div className="space-y-1">
              {currentItem.responses.map((response) => (
                <p key={response.id} className="text-xs">
                  <span className="font-medium">{response.anonymized_id}:</span>{' '}
                  <Badge variant="outline">
                    Model {response.id.split('-')[0]}
                  </Badge>
                </p>
              ))}
            </div>
          </Card>
        )}
      </div>
    </>
  )
}

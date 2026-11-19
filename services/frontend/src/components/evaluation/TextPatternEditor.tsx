'use client'

import { Textarea } from '@/components/shared/Textarea'
import { useI18n } from '@/contexts/I18nContext'
import { useState } from 'react'

/**
 * Parameters of the `text_pattern` metric: the pattern set (JSON, see
 * docs/features/codes.md) and the code of the set to report. The server
 * checks the set when the configuration is saved; this editor only keeps
 * the JSON parseable and offers the set's codes.
 */
export interface TextPatternParameters {
  pattern_set?: unknown
  code?: string
}

export function patternSetCodes(set: unknown): string[] {
  if (!set || typeof set !== 'object' || Array.isArray(set)) return []
  const s = set as Record<string, unknown>
  if (typeof s.name !== 'string' || typeof s.version !== 'string') return []
  const codes = s.codes
  if (!codes || typeof codes !== 'object' || Array.isArray(codes)) return []
  return Object.keys(codes as Record<string, unknown>)
}

/** Whether the parameters name a code of a well-formed pattern set. */
export function textPatternReady(params: TextPatternParameters): boolean {
  const codes = patternSetCodes(params.pattern_set)
  return typeof params.code === 'string' && codes.includes(params.code)
}

interface Props {
  parameters: TextPatternParameters
  onChange: (patch: TextPatternParameters) => void
}

export function TextPatternEditor({ parameters, onChange }: Props) {
  const { t } = useI18n()
  const [text, setText] = useState(() =>
    parameters.pattern_set === undefined
      ? ''
      : JSON.stringify(parameters.pattern_set, null, 2),
  )
  const [error, setError] = useState<'invalidJson' | 'notASet' | null>(null)
  const codes = patternSetCodes(parameters.pattern_set)

  const update = (value: string) => {
    setText(value)
    let parsed: unknown
    try {
      parsed = JSON.parse(value)
    } catch {
      setError('invalidJson')
      return
    }
    const parsedCodes = patternSetCodes(parsed)
    if (parsedCodes.length === 0) {
      setError('notASet')
      return
    }
    setError(null)
    const code =
      parameters.code && parsedCodes.includes(parameters.code)
        ? parameters.code
        : parsedCodes[0]
    onChange({ pattern_set: parsed, code })
  }

  return (
    <div className="space-y-4">
      <div>
        <label
          htmlFor="text-pattern-set"
          className="mb-1 block text-sm font-medium text-zinc-700 dark:text-zinc-300"
        >
          {t('evaluationBuilder.parameters.textPattern.patternSet')}
        </label>
        <Textarea
          id="text-pattern-set"
          value={text}
          onChange={(e) => update(e.target.value)}
          rows={10}
          className="font-mono text-xs"
          spellCheck={false}
        />
        <p className="mt-1 text-xs text-zinc-500">
          {t('evaluationBuilder.parameters.textPattern.patternSetHelp')}
        </p>
        {error && (
          <p role="alert" className="mt-1 text-xs text-red-600">
            {t(`evaluationBuilder.parameters.textPattern.${error}`)}
          </p>
        )}
      </div>
      <div>
        <label
          htmlFor="text-pattern-code"
          className="mb-1 block text-sm font-medium text-zinc-700 dark:text-zinc-300"
        >
          {t('evaluationBuilder.parameters.textPattern.code')}
        </label>
        <select
          id="text-pattern-code"
          value={parameters.code ?? ''}
          disabled={codes.length === 0}
          onChange={(e) => onChange({ code: e.target.value })}
          className="w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm dark:border-zinc-600 dark:bg-zinc-800"
        >
          {codes.length === 0 && (
            <option value="">
              {t('evaluationBuilder.parameters.textPattern.selectCode')}
            </option>
          )}
          {codes.map((code) => (
            <option key={code} value={code}>
              {code}
            </option>
          ))}
        </select>
      </div>
    </div>
  )
}

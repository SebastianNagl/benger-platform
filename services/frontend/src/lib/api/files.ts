/**
 * Generic file helpers backed by the platform `/files/*` routes.
 *
 * `extractText` turns an uploaded document (.pdf / .docx / .txt / .md) into
 * plain text server-side so data import and structured editors can pre-fill
 * from a file. Moved here from the extended student client: text extraction
 * is generic platform functionality, not a student feature.
 */
import apiClient from '@/lib/api'

export interface ExtractTextResponse {
  text: string
  source_format: string
  warnings: string[]
}

/** Thrown by extractText on a 4xx with a structured `{code, message}` body. */
export class ExtractTextError extends Error {
  code: string
  constructor(code: string, message: string) {
    super(message)
    this.name = 'ExtractTextError'
    this.code = code
  }
}

export const EXTRACTABLE_ACCEPT = '.pdf,.docx,.txt,.md'

export const filesAPI = {
  extractText: async (file: File): Promise<ExtractTextResponse> => {
    const form = new FormData()
    form.append('file', file)
    try {
      return await apiClient.post('/files/extract-text', form)
    } catch (err: any) {
      // The apiClient surfaces the parsed body on `err.data` / `err.body`;
      // an image-only PDF returns 422 {code, message}.
      const body = err?.data ?? err?.body ?? err?.response
      if (body && (body.code || body.message)) {
        throw new ExtractTextError(
          body.code ?? 'extract_failed',
          body.message ?? String(err?.message ?? 'Extraction failed'),
        )
      }
      throw err
    }
  },
}

export default filesAPI

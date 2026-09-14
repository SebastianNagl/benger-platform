import { NextRequest, NextResponse } from 'next/server'

type JsonBodyResult =
  { ok: true; body: unknown } | { ok: false; response: NextResponse }

/**
 * Read a proxied request's JSON body.
 *
 * A body that is not valid JSON is the caller's mistake, not a server fault.
 * The API answers such a request with 422, but a route that let
 * `request.json()` throw into its catch-all turned it into an opaque 500
 * "Internal server error". This answers 422 with a FastAPI-style `detail`
 * instead, before anything is forwarded.
 */
export async function readJsonBody(
  request: NextRequest,
): Promise<JsonBodyResult> {
  try {
    return { ok: true, body: await request.json() }
  } catch {
    return {
      ok: false,
      response: NextResponse.json(
        { detail: 'Request body must be valid JSON.' },
        { status: 422 },
      ),
    }
  }
}

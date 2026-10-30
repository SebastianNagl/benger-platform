/**
 * Credentials a dedicated Next route handler forwards to the API: the
 * session cookie (always, empty when absent, as before) and the caller's
 * `Authorization` header unchanged when one was sent. Access keys
 * (`Authorization: Bearer bgr_...`) work on the whole API since core 2.45,
 * so scripts calling the main host must reach the API with their key even
 * where a dedicated handler (not the catch-all proxy) answers the route.
 */

interface HasHeaders {
  headers: Pick<Headers, 'get'>
}

export function proxyAuthHeaders(request: HasHeaders): Record<string, string> {
  const headers: Record<string, string> = {
    Cookie: request.headers.get('cookie') || '',
  }
  const authorization = request.headers.get('authorization')
  if (authorization) headers.Authorization = authorization
  return headers
}

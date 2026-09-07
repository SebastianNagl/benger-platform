/**
 * Branch coverage tests for proxy.ts
 *
 * Covers: CSS/JS/SVG MIME type branches, subdomain extraction with
 * various hostname patterns, and the no-subdomain path.
 */

import { NextRequest } from 'next/server'

// We must mock the subdomain module before importing proxy
jest.mock('@/lib/utils/subdomain', () => ({
  BASE_DOMAINS: ['benger.localhost', 'what-a-benger.net'],
  isStudentLockedHost: (host?: string | null) =>
    !!host && /(^|\.)vertretbar\.(net|localhost)$/.test(host.split(':')[0]),
}))

import { proxy } from './proxy'

function createRequest(pathname: string, host: string): NextRequest {
  const url = new URL(`http://${host}${pathname}`)
  const req = new NextRequest(url, {
    headers: new Headers({ host }),
  })
  return req
}

describe('proxy', () => {
  describe('MIME type headers', () => {
    it('should set text/css for .css files', () => {
      const res = proxy(createRequest('/styles/app.css', 'benger.localhost'))
      expect(res.headers.get('Content-Type')).toBe('text/css')
    })

    it('should set application/javascript for .js files', () => {
      const res = proxy(createRequest('/scripts/bundle.js', 'benger.localhost'))
      expect(res.headers.get('Content-Type')).toBe('application/javascript')
    })

    it('should set image/svg+xml for .svg files', () => {
      const res = proxy(createRequest('/icons/logo.svg', 'benger.localhost'))
      expect(res.headers.get('Content-Type')).toBe('image/svg+xml')
    })

    it('should NOT set MIME type header for non-static files', () => {
      const res = proxy(createRequest('/dashboard', 'benger.localhost'))
      // The header is set to NextResponse default, not one of the MIME overrides
      expect(res.headers.get('Content-Type')).not.toBe('text/css')
      expect(res.headers.get('Content-Type')).not.toBe('application/javascript')
      expect(res.headers.get('Content-Type')).not.toBe('image/svg+xml')
    })
  })

  describe('org slug extraction from subdomain', () => {
    it('should set x-org-slug for valid subdomain', () => {
      const res = proxy(createRequest('/dashboard', 'tum.benger.localhost'))
      expect(res.headers.get('x-org-slug')).toBe('tum')
    })

    it('should NOT set x-org-slug for base domain without subdomain', () => {
      const res = proxy(createRequest('/dashboard', 'benger.localhost'))
      expect(res.headers.get('x-org-slug')).toBeNull()
    })

    it('should NOT set x-org-slug for multi-level subdomain (contains dot)', () => {
      // "deep.sub.benger.localhost" => subdomain = "deep.sub" which contains '.'
      const res = proxy(createRequest('/dashboard', 'deep.sub.benger.localhost'))
      expect(res.headers.get('x-org-slug')).toBeNull()
    })

    it('should set x-org-slug for production domain subdomain', () => {
      const res = proxy(createRequest('/', 'myorg.what-a-benger.net'))
      expect(res.headers.get('x-org-slug')).toBe('myorg')
    })

    it('should NOT set x-org-slug for unrecognized hostname', () => {
      const res = proxy(createRequest('/', 'example.com'))
      expect(res.headers.get('x-org-slug')).toBeNull()
    })
  })
})

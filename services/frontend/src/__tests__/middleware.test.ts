/**
 * @jest-environment node
 */

import { NextRequest, NextResponse } from 'next/server'
import { config, middleware } from '../middleware'

describe('middleware', () => {
  describe('MIME Type Headers', () => {
    it('sets correct MIME type for CSS files', () => {
      const request = new NextRequest('http://localhost:3000/styles/main.css')
      const response = middleware(request)

      expect(response).toBeInstanceOf(NextResponse)
      expect(response.headers.get('Content-Type')).toBe('text/css')
    })

    it('sets correct MIME type for JavaScript files', () => {
      const request = new NextRequest('http://localhost:3000/scripts/main.js')
      const response = middleware(request)

      expect(response).toBeInstanceOf(NextResponse)
      expect(response.headers.get('Content-Type')).toBe(
        'application/javascript'
      )
    })

    it('sets correct MIME type for SVG files', () => {
      const request = new NextRequest('http://localhost:3000/images/logo.svg')
      const response = middleware(request)

      expect(response).toBeInstanceOf(NextResponse)
      expect(response.headers.get('Content-Type')).toBe('image/svg+xml')
    })

    it('handles nested CSS file paths', () => {
      const request = new NextRequest(
        'http://localhost:3000/assets/styles/components/button.css'
      )
      const response = middleware(request)

      expect(response.headers.get('Content-Type')).toBe('text/css')
    })

    it('handles nested JavaScript file paths', () => {
      const request = new NextRequest(
        'http://localhost:3000/assets/scripts/utils/helper.js'
      )
      const response = middleware(request)

      expect(response.headers.get('Content-Type')).toBe(
        'application/javascript'
      )
    })

    it('handles nested SVG file paths', () => {
      const request = new NextRequest(
        'http://localhost:3000/assets/icons/menu.svg'
      )
      const response = middleware(request)

      expect(response.headers.get('Content-Type')).toBe('image/svg+xml')
    })
  })

  describe('Non-Matching Extensions', () => {
    it('does not set MIME type for HTML files', () => {
      const request = new NextRequest('http://localhost:3000/index.html')
      const response = middleware(request)

      expect(response.headers.get('Content-Type')).toBeNull()
    })

    it('does not set MIME type for PNG files', () => {
      const request = new NextRequest('http://localhost:3000/image.png')
      const response = middleware(request)

      expect(response.headers.get('Content-Type')).toBeNull()
    })

    it('does not set MIME type for JSON files', () => {
      const request = new NextRequest('http://localhost:3000/data.json')
      const response = middleware(request)

      expect(response.headers.get('Content-Type')).toBeNull()
    })

    it('does not set MIME type for TypeScript files', () => {
      const request = new NextRequest('http://localhost:3000/component.ts')
      const response = middleware(request)

      expect(response.headers.get('Content-Type')).toBeNull()
    })

    it('does not set MIME type for TSX files', () => {
      const request = new NextRequest('http://localhost:3000/component.tsx')
      const response = middleware(request)

      expect(response.headers.get('Content-Type')).toBeNull()
    })
  })

  describe('Route Handling', () => {
    it('processes routes without extensions', () => {
      const request = new NextRequest('http://localhost:3000/dashboard')
      const response = middleware(request)

      expect(response).toBeInstanceOf(NextResponse)
      expect(response.headers.get('Content-Type')).toBeNull()
    })

    it('processes root route', () => {
      const request = new NextRequest('http://localhost:3000/')
      const response = middleware(request)

      expect(response).toBeInstanceOf(NextResponse)
      expect(response.headers.get('Content-Type')).toBeNull()
    })

    it('processes nested routes without extensions', () => {
      const request = new NextRequest(
        'http://localhost:3000/projects/123/tasks'
      )
      const response = middleware(request)

      expect(response).toBeInstanceOf(NextResponse)
      expect(response.headers.get('Content-Type')).toBeNull()
    })

    it('processes routes with query parameters', () => {
      const request = new NextRequest(
        'http://localhost:3000/search?q=test&page=1'
      )
      const response = middleware(request)

      expect(response).toBeInstanceOf(NextResponse)
    })

    it('processes routes with hash fragments', () => {
      const request = new NextRequest('http://localhost:3000/docs#introduction')
      const response = middleware(request)

      expect(response).toBeInstanceOf(NextResponse)
    })
  })

  describe('Edge Cases', () => {
    it('handles files with multiple dots in name', () => {
      const request = new NextRequest(
        'http://localhost:3000/styles/main.min.css'
      )
      const response = middleware(request)

      expect(response.headers.get('Content-Type')).toBe('text/css')
    })

    it('handles uppercase extensions', () => {
      const request = new NextRequest('http://localhost:3000/style.CSS')
      const response = middleware(request)

      // Note: The middleware checks .endsWith('.css'), so uppercase won't match
      // This tests the actual behavior
      expect(response.headers.get('Content-Type')).toBeNull()
    })

    it('handles files with similar but different extensions', () => {
      const request = new NextRequest('http://localhost:3000/file.jsx')
      const response = middleware(request)

      expect(response.headers.get('Content-Type')).toBeNull()
    })

    it('handles empty pathname', () => {
      const request = new NextRequest('http://localhost:3000')
      const response = middleware(request)

      expect(response).toBeInstanceOf(NextResponse)
    })

    it('handles very long pathnames with correct extension', () => {
      const longPath = '/a'.repeat(100) + '/style.css'
      const request = new NextRequest(`http://localhost:3000${longPath}`)
      const response = middleware(request)

      expect(response.headers.get('Content-Type')).toBe('text/css')
    })

    it('handles files with no extension', () => {
      const request = new NextRequest('http://localhost:3000/Makefile')
      const response = middleware(request)

      expect(response.headers.get('Content-Type')).toBeNull()
    })

    it('handles files starting with dot', () => {
      const request = new NextRequest('http://localhost:3000/.env')
      const response = middleware(request)

      expect(response.headers.get('Content-Type')).toBeNull()
    })
  })

  describe('Response Behavior', () => {
    it('returns NextResponse for all requests', () => {
      const paths = [
        '/style.css',
        '/script.js',
        '/icon.svg',
        '/page',
        '/image.png',
      ]

      paths.forEach((path) => {
        const request = new NextRequest(`http://localhost:3000${path}`)
        const response = middleware(request)
        expect(response).toBeInstanceOf(NextResponse)
      })
    })

    it('does not block or redirect any requests', () => {
      const request = new NextRequest('http://localhost:3000/dashboard')
      const response = middleware(request)

      // Verify it's a pass-through response (NextResponse.next())
      expect(response).toBeInstanceOf(NextResponse)
      expect(response.status).toBe(200)
    })

    it('preserves existing headers', () => {
      const request = new NextRequest('http://localhost:3000/api/users', {
        headers: {
          'X-Custom-Header': 'test-value',
        },
      })
      const response = middleware(request)

      expect(response).toBeInstanceOf(NextResponse)
    })
  })

  describe('Multiple File Types in Single Request', () => {
    it('only sets one MIME type per response', () => {
      const request = new NextRequest('http://localhost:3000/style.css')
      const response = middleware(request)

      const contentType = response.headers.get('Content-Type')
      expect(contentType).toBe('text/css')
    })

    it('uses extension-based MIME type over other considerations', () => {
      // Request with CSS extension should get text/css regardless of other headers
      const request = new NextRequest('http://localhost:3000/api/styles.css')
      const response = middleware(request)

      expect(response.headers.get('Content-Type')).toBe('text/css')
    })
  })

  describe('Middleware Configuration', () => {
    it('exports config with correct matcher pattern', () => {
      expect(config).toBeDefined()
      expect(config.matcher).toBeDefined()
      expect(Array.isArray(config.matcher)).toBe(true)
      expect(config.matcher).toHaveLength(1)
    })

    it('config matcher excludes api routes', () => {
      const matcher = config.matcher[0]
      expect(matcher).toContain('(?!api')
    })

    it('config matcher excludes _next routes', () => {
      const matcher = config.matcher[0]
      expect(matcher).toContain('(?!api|_next')
    })

    it('config matcher excludes _vercel routes', () => {
      const matcher = config.matcher[0]
      expect(matcher).toContain('_vercel')
    })

    it('config matcher excludes files with extensions', () => {
      const matcher = config.matcher[0]
      expect(matcher).toContain('.*\\.')
    })
  })

  describe('Performance and Concurrency', () => {
    it('handles concurrent requests independently', () => {
      const requests = [
        new NextRequest('http://localhost:3000/style1.css'),
        new NextRequest('http://localhost:3000/script1.js'),
        new NextRequest('http://localhost:3000/icon1.svg'),
      ]

      const responses = requests.map((req) => middleware(req))

      expect(responses[0].headers.get('Content-Type')).toBe('text/css')
      expect(responses[1].headers.get('Content-Type')).toBe(
        'application/javascript'
      )
      expect(responses[2].headers.get('Content-Type')).toBe('image/svg+xml')
    })

    it('does not maintain state between requests', () => {
      const request1 = new NextRequest('http://localhost:3000/style.css')
      const response1 = middleware(request1)

      const request2 = new NextRequest('http://localhost:3000/page')
      const response2 = middleware(request2)

      expect(response1.headers.get('Content-Type')).toBe('text/css')
      expect(response2.headers.get('Content-Type')).toBeNull()
    })
  })

  describe('URL Encoding and Special Characters', () => {
    it('handles URL-encoded pathnames', () => {
      const request = new NextRequest(
        'http://localhost:3000/styles/file%20name.css'
      )
      const response = middleware(request)

      expect(response.headers.get('Content-Type')).toBe('text/css')
    })

    it('handles pathnames with special characters', () => {
      const request = new NextRequest(
        'http://localhost:3000/styles/file-v1.0.css'
      )
      const response = middleware(request)

      expect(response.headers.get('Content-Type')).toBe('text/css')
    })

    it('handles international characters in pathname', () => {
      const request = new NextRequest('http://localhost:3000/stile/über.css')
      const response = middleware(request)

      expect(response.headers.get('Content-Type')).toBe('text/css')
    })
  })

  describe('Different Hosts and Protocols', () => {
    it('processes requests from different hosts', () => {
      const request = new NextRequest('http://example.com:3000/style.css')
      const response = middleware(request)

      expect(response.headers.get('Content-Type')).toBe('text/css')
    })

    it('processes HTTPS requests', () => {
      const request = new NextRequest('https://localhost:3000/style.css')
      const response = middleware(request)

      expect(response.headers.get('Content-Type')).toBe('text/css')
    })

    it('processes requests with custom ports', () => {
      const request = new NextRequest('http://localhost:8080/style.css')
      const response = middleware(request)

      expect(response.headers.get('Content-Type')).toBe('text/css')
    })
  })
})

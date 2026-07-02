import { Providers } from '@/app/providers'
import { DevModeIndicator } from '@/components/dev/DevModeIndicator'
import { ConditionalLayout } from '@/components/layout/ConditionalLayout'
import { type Section } from '@/components/layout/SectionProvider'
import '@/styles/tailwind.css'
import { type Metadata } from 'next'
import { headers } from 'next/headers'

import { isStudentLockedHost } from '@/lib/utils/subdomain'

// Define sections for different pages
const allSections: Record<string, Array<Section>> = {
  '/how-to': [
    { id: 'platform-overview', title: 'Platform Overview' },
    { id: 'projects', title: 'Projects' },
    { id: 'data-import', title: 'Data Import' },
    { id: 'annotation', title: 'Annotation' },
    { id: 'generation', title: 'Generation' },
    { id: 'evaluation', title: 'Evaluation' },
    { id: 'organizations', title: 'Organizations & Roles' },
    { id: 'api-key-management', title: 'API Key Management' },
    { id: 'troubleshooting', title: 'Troubleshooting' },
  ],
}

// Host-aware metadata: Vertretbar branding on the student-locked apex
// (vertretbar.net), BenGER everywhere else — resolved server-side from the
// request host so the tab title/OG never flash benger branding on vertretbar.net.
export async function generateMetadata(): Promise<Metadata> {
  const h = await headers()
  const host = h.get('x-forwarded-host') || h.get('host') || ''
  const vtr = isStudentLockedHost(host)

  const title = vtr
    ? 'Vertretbar – Klausuren üben mit sofortiger KI-Korrektur'
    : 'BenGER - Vertrauensvolle KI-Bewertung für deutsches Recht'
  const description = vtr
    ? 'Übe juristische Klausuren mit sofortiger KI-Korrektur und lerne mit Karteikarten — kein eigener API-Schlüssel nötig.'
    : 'Die führende Plattform für wissenschaftlich fundierte Evaluation von Large Language Models im deutschen Rechtskontext. Entwickelt an der TUM.'

  return {
    title: {
      template: vtr ? '%s · Vertretbar' : '%s - BenGER',
      default: title,
    },
    description,
    keywords: vtr
      ? ['Jura', 'Klausur', 'Falllösung', 'Karteikarten', 'KI-Korrektur', 'Examen']
      : ['Legal AI', 'LLM Evaluation', 'German Law', 'Legal Technology', 'AI Benchmarking'],
    icons: {
      icon: '/icon.svg',
    },
    openGraph: {
      title,
      description,
      url: vtr ? 'https://vertretbar.net' : 'https://what-a-benger.net',
      siteName: vtr ? 'Vertretbar' : 'BenGER',
      locale: 'de_DE',
      type: 'website',
    },
    twitter: {
      card: 'summary_large_image',
      title,
      description,
    },
  }
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="de" className="h-full" suppressHydrationWarning>
      <head>
        {process.env.NODE_ENV === 'development' && process.env.NEXT_PUBLIC_DISABLE_AUTO_LOGIN !== 'true' && (
          <script
            dangerouslySetInnerHTML={{
              __html: `
                // Dev auto-login: login automatically on any page if not authenticated
                (function() {
                  if (sessionStorage.getItem('e2e_test_mode') === 'true') return;
                  if (sessionStorage.getItem('dev_auto_login_done') === 'true') return;
                  sessionStorage.setItem('dev_auto_login_done', 'true');
                  // Check if already authenticated
                  fetch('/api/auth/me', { credentials: 'include' }).then(function(r) {
                    if (r.ok) {
                      // Already logged in — redirect to dashboard if on landing/login
                      localStorage.setItem('auth_verified', 'true');
                      var p = window.location.pathname;
                      if (p === '/' || p === '/login') {
                        window.location.href = '/dashboard';
                      }
                      return;
                    }
                    // Not authenticated — auto-login
                    fetch('/api/auth/login', {
                      method: 'POST',
                      headers: { 'Content-Type': 'application/json' },
                      body: JSON.stringify({ username: 'admin', password: 'admin' }),
                      credentials: 'include',
                    }).then(function(r2) {
                      if (r2.ok) {
                        localStorage.setItem('auth_verified', 'true');
                        window.location.href = '/dashboard';
                      }
                    });
                  }).catch(function() {});
                })();
              `,
            }}
          />
        )}
      </head>
      <body
        className="flex min-h-full w-full bg-white antialiased dark:bg-zinc-900"
        suppressHydrationWarning
      >
        <Providers>
          <ConditionalLayout allSections={allSections}>
            {children}
          </ConditionalLayout>
          <DevModeIndicator />
        </Providers>
      </body>
    </html>
  )
}

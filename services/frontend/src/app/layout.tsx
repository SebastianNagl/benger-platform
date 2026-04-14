import { Providers } from '@/app/providers'
import { DevModeIndicator } from '@/components/dev/DevModeIndicator'
import { ConditionalLayout } from '@/components/layout/ConditionalLayout'
import { type Section } from '@/components/layout/SectionProvider'
import '@/styles/tailwind.css'
import { type Metadata } from 'next'

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

export const metadata: Metadata = {
  title: {
    template: '%s - BenGER',
    default: 'BenGER - Vertrauensvolle KI-Bewertung für deutsches Recht',
  },
  description:
    'Die führende Plattform für wissenschaftlich fundierte Evaluation von Large Language Models im deutschen Rechtskontext. Entwickelt an der TUM.',
  keywords: [
    'Legal AI',
    'LLM Evaluation',
    'German Law',
    'Legal Technology',
    'AI Benchmarking',
  ],
  icons: {
    icon: '/icon.svg',
  },
  openGraph: {
    title: 'BenGER - Vertrauensvolle KI-Bewertung für deutsches Recht',
    description:
      'Die führende Plattform für wissenschaftlich fundierte Evaluation von Large Language Models im deutschen Rechtskontext.',
    url: 'https://what-a-benger.net',
    siteName: 'BenGER',
    locale: 'de_DE',
    type: 'website',
  },
  twitter: {
    card: 'summary_large_image',
    title: 'BenGER - Vertrauensvolle KI-Bewertung für deutsches Recht',
    description:
      'Die führende Plattform für wissenschaftlich fundierte Evaluation von Large Language Models im deutschen Rechtskontext.',
  },
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

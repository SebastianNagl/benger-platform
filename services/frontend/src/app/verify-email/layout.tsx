import { Suspense } from 'react'

export default function VerifyEmailLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return <Suspense fallback={null}>{children}</Suspense>
}

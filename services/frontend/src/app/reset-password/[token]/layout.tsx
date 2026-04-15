import { Suspense } from 'react'

export default function ResetPasswordTokenLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return <Suspense fallback={null}>{children}</Suspense>
}

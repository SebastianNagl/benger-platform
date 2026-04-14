import { Suspense } from 'react'

export default function ResetPasswordLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return <Suspense fallback={null}>{children}</Suspense>
}

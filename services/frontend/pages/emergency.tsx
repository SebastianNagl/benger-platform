export default function EmergencyPage() {
  return (
    <div style={{ padding: '2rem', fontFamily: 'system-ui' }}>
      <h1>Emergency Test Page (Pages Router)</h1>
      <p>This page uses the legacy pages router to bypass app router issues.</p>
      <p>If you can see this, the Next.js installation is working.</p>
      <p>Time: {new Date().toISOString()}</p>
    </div>
  )
}

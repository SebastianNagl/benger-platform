import { NextResponse } from 'next/server'

export async function GET() {
  return NextResponse.json({
    message: 'Frontend API route is working!',
    timestamp: new Date().toISOString(),
    env: process.env.API_BASE_URL,
  })
}

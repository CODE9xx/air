import { NextResponse } from 'next/server';

// Health-check для docker / load balancer.
export async function GET() {
  return NextResponse.json({ status: 'ok' });
}

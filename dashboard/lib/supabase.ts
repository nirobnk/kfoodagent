'use client';

import { createBrowserClient } from '@supabase/ssr';

/**
 * Browser Supabase client. Uses the anon key and the signed-in user's session,
 * so Row Level Security decides what staff can read. The service role key and
 * the WhatsApp token live only in the backend.
 */
/**
 * The browser-safe key. Supabase replaced the anon key with a publishable key
 * (sb_publishable_…); the old name still works and is read as a fallback.
 */
export function publicKey(): string | undefined {
  return (
    process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY ||
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ||
    undefined
  );
}

export function createClient() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = publicKey();

  if (!url || !key) {
    throw new Error(
      'Missing NEXT_PUBLIC_SUPABASE_URL or NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY. ' +
        'Copy .env.local.example to .env.local and fill them in.',
    );
  }

  return createBrowserClient(url, key);
}

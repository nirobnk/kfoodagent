'use client';

import { Suspense, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { createClient } from '@/lib/supabase';

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);

    const supabase = createClient();
    const { error: signInError } = await supabase.auth.signInWithPassword({ email, password });

    if (signInError) {
      setError(signInError.message);
      setBusy(false);
      return;
    }

    router.replace(params.get('next') || '/');
    router.refresh();
  }

  return (
    <div className="w-full max-w-sm">
      <form
        onSubmit={onSubmit}
        className="w-full rounded-2xl bg-white p-8 shadow-sm ring-1 ring-wa-border"
      >
        <div className="mb-6">
          <div className="mb-2 flex h-11 w-11 items-center justify-center rounded-full bg-wa-green text-lg font-semibold text-white">
            K
          </div>
          <h1 className="text-xl font-semibold">K-Food Inbox</h1>
          <p className="mt-1 text-sm text-wa-muted">Staff sign in</p>
        </div>

        <label className="mb-3 block text-sm">
          <span className="mb-1 block font-medium">Email</span>
          <input
            type="email"
            required
            autoComplete="username"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            className="w-full rounded-lg border border-wa-border px-3 py-2 outline-none focus:border-wa-green"
          />
        </label>

        <label className="mb-5 block text-sm">
          <span className="mb-1 block font-medium">Password</span>
          <input
            type="password"
            required
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            className="w-full rounded-lg border border-wa-border px-3 py-2 outline-none focus:border-wa-green"
          />
        </label>

        {error && (
          <p className="mb-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>
        )}

        <button
          type="submit"
          disabled={busy}
          className="w-full rounded-lg bg-wa-green py-2.5 font-medium text-white transition hover:bg-[#0f7a6e] disabled:opacity-60"
        >
          {busy ? 'Signing in…' : 'Sign in'}
        </button>

        <p className="mt-4 text-center text-xs text-wa-muted">
          Accounts are created in Supabase and linked to K-Food in business_members.
        </p>
      </form>
    </div>
  );
}

export default function LoginPage() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-wa-panel px-4">
      {/* useSearchParams needs a suspense boundary when the page is prerendered. */}
      <Suspense fallback={<p className="text-sm text-wa-muted">Loading…</p>}>
        <LoginForm />
      </Suspense>
    </main>
  );
}

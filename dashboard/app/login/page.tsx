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
    <form onSubmit={onSubmit} className="card w-full max-w-sm animate-rise p-8">
      <div className="mb-7">
        <span className="mb-4 flex h-10 w-10 items-center justify-center rounded-md bg-chilli font-display text-base font-extrabold text-white">
          K
        </span>
        <h1 className="font-display text-2xl font-extrabold tracking-tight">K&nbsp;FOOD</h1>
        <p className="mt-0.5 text-sm text-soy">Sign in to the customer book.</p>
      </div>

      <label className="mb-4 block">
        <span className="label mb-1.5">Email</span>
        <input
          type="email"
          required
          autoComplete="username"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          className="field"
        />
      </label>

      <label className="mb-6 block">
        <span className="label mb-1.5">Password</span>
        <input
          type="password"
          required
          autoComplete="current-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          className="field"
        />
      </label>

      {error && (
        <p className="mb-4 rounded-lg border border-chilli/25 bg-chilli-wash px-3 py-2 text-sm text-chilli-dark">
          {error}
        </p>
      )}

      <button type="submit" disabled={busy} className="btn-hot w-full py-2.5">
        {busy ? 'Signing in…' : 'Sign in'}
      </button>

      <p className="mt-5 text-center text-xs leading-relaxed text-soy">
        Accounts are made in Supabase and linked to K FOOD in business_members. If sign-in works
        but nothing loads, that link is what is missing.
      </p>
    </form>
  );
}

export default function LoginPage() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-paper px-4">
      {/* useSearchParams needs a suspense boundary when the page is prerendered. */}
      <Suspense fallback={<p className="text-sm text-soy">Loading…</p>}>
        <LoginForm />
      </Suspense>
    </main>
  );
}

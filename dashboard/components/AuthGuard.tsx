'use client';

import { useEffect, useState } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { createClient } from '@/lib/supabase';

/**
 * The front door, moved into the browser.
 *
 * middleware.ts did this until the dashboard became a static export, which has
 * no server to run middleware on. Row Level Security is still the real
 * boundary — signed-out visitors can reach the HTML but Supabase returns them
 * nothing — so this only decides which screen someone sees.
 */
export function AuthGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [allowed, setAllowed] = useState(false);

  useEffect(() => {
    const supabase = createClient();
    let alive = true;

    function decide(signedIn: boolean) {
      if (!alive) return;
      const onLogin = pathname.startsWith('/login');

      if (!signedIn && !onLogin) {
        setAllowed(false);
        router.replace(`/login?next=${encodeURIComponent(pathname)}`);
        return;
      }
      if (signedIn && onLogin) {
        setAllowed(false);
        router.replace('/');
        return;
      }
      setAllowed(true);
    }

    supabase.auth.getUser().then(({ data }) => decide(Boolean(data.user)));

    // Covers signing in, signing out and a token refresh failing in another tab.
    const { data: listener } = supabase.auth.onAuthStateChange((_event, session) =>
      decide(Boolean(session?.user)),
    );

    return () => {
      alive = false;
      listener.subscription.unsubscribe();
    };
  }, [pathname, router]);

  if (!allowed) {
    return (
      <div className="flex h-screen items-center justify-center bg-paper">
        <p className="font-mono text-2xs uppercase tracking-[0.14em] text-soy">
          Checking your session
        </p>
      </div>
    );
  }

  return <>{children}</>;
}

'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import { createClient } from '@/lib/supabase';
import { api } from '@/lib/api';
import type { Usage } from '@/lib/types';

export function Nav({ email }: { email?: string | null }) {
  const pathname = usePathname();
  const router = useRouter();
  const [usage, setUsage] = useState<Usage | null>(null);

  useEffect(() => {
    let alive = true;
    api
      .usage()
      .then((data) => alive && setUsage(data))
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, []);

  async function signOut() {
    await createClient().auth.signOut();
    router.replace('/login');
    router.refresh();
  }

  const link = (href: string, label: string) => {
    const active = href === '/' ? pathname === '/' : pathname.startsWith(href);
    return (
      <Link
        href={href}
        className={`rounded-lg px-3 py-1.5 text-sm font-medium transition ${
          active ? 'bg-white/20 text-white' : 'text-white/80 hover:bg-white/10'
        }`}
      >
        {label}
      </Link>
    );
  };

  return (
    <header className="flex items-center gap-3 bg-wa-green px-4 py-2.5 text-white">
      <div className="flex items-center gap-2 pr-2">
        <span className="flex h-8 w-8 items-center justify-center rounded-full bg-white/20 text-sm font-bold">
          K
        </span>
        <span className="hidden font-semibold sm:inline">K-Food Inbox</span>
      </div>

      <nav className="flex items-center gap-1">
        {link('/', 'Chats')}
        {link('/orders', 'Orders')}
        {link('/products', 'Catalogue')}
      </nav>

      <div className="ml-auto flex items-center gap-3">
        {usage && (
          <span
            title={`Since ${usage.month_start}. Meta gives 1,000 free service messages per number per month.`}
            className="hidden rounded-full bg-white/15 px-3 py-1 text-xs md:inline"
          >
            {usage.outbound_messages} sent this month
            {usage.free_service_messages_remaining === 0 && ' · free tier used up'}
          </span>
        )}
        {email && <span className="hidden text-xs text-white/80 lg:inline">{email}</span>}
        <button
          onClick={signOut}
          className="rounded-lg px-3 py-1.5 text-sm text-white/90 transition hover:bg-white/10"
        >
          Sign out
        </button>
      </div>
    </header>
  );
}

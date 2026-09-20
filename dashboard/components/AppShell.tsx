'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useCallback, useEffect, useState } from 'react';
import { createClient } from '@/lib/supabase';
import { api } from '@/lib/api';
import { Icon } from './ui/Icon';

/**
 * The frame. Dark rail, light workspace.
 *
 * Staff read this under shop lights all day, so the work itself stays on paper
 * and only the chrome goes dark. Below `md` the rail becomes a drawer rather
 * than a cut-down tab bar: the owner uses this on a phone in the evening and
 * needs the same nine places, not five of them.
 */

interface NavItem {
  href: string;
  label: string;
  icon: string;
  /** Which badge count, if any, sits on this row. */
  badge?: 'unread' | 'tasks' | 'mismatch';
}

const GROUPS: { heading: string; items: NavItem[] }[] = [
  {
    heading: 'Today',
    items: [
      { href: '/', label: 'Overview', icon: 'today' },
      { href: '/inbox', label: 'Chats', icon: 'inbox', badge: 'unread' },
      { href: '/orders', label: 'Orders', icon: 'orders' },
      { href: '/tasks', label: 'Follow-ups', icon: 'tasks', badge: 'tasks' },
    ],
  },
  {
    heading: 'Customers',
    items: [
      { href: '/customers', label: 'Customer book', icon: 'customers' },
      { href: '/insights', label: 'Insights', icon: 'insights' },
    ],
  },
  {
    heading: 'Shop',
    items: [
      { href: '/products', label: 'Catalogue', icon: 'catalogue' },
      { href: '/inventory', label: 'Stock', icon: 'stock' },
      { href: '/bills', label: 'Printed bills', icon: 'bills', badge: 'mismatch' },
    ],
  },
];

export interface ShellCounts {
  unread: number;
  tasks: number;
  mismatch: number;
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [email, setEmail] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [counts, setCounts] = useState<ShellCounts>({ unread: 0, tasks: 0, mismatch: 0 });

  useEffect(() => setOpen(false), [pathname]);

  useEffect(() => {
    const supabase = createClient();
    let alive = true;

    supabase.auth.getUser().then(({ data }) => alive && setEmail(data.user?.email ?? null));

    // Unread comes straight from Supabase under RLS — it is a column, not a
    // derived figure, so there is nothing for the backend to own.
    async function countUnread() {
      const { data } = await supabase.from('contacts').select('unread_count');
      if (!alive) return;
      setCounts((current) => ({
        ...current,
        unread: (data ?? []).reduce(
          (sum, row: { unread_count: number | null }) => sum + (row.unread_count ?? 0),
          0,
        ),
      }));
    }

    async function countWork() {
      const [tasks, invoices] = await Promise.all([
        api.listTasks('open').catch(() => null),
        api.listInvoices(true).catch(() => null),
      ]);
      if (!alive) return;
      setCounts((current) => ({
        ...current,
        tasks: tasks?.overdue_count ?? 0,
        mismatch: invoices?.mismatch_count ?? 0,
      }));
    }

    void countUnread();
    void countWork();
    const timer = setInterval(() => {
      void countUnread();
      void countWork();
    }, 60_000);

    // A busy shift fires this on every inbound message. Only the unread count
    // can have moved — a follow-up falling overdue or a bill arriving is what
    // the minute timer is for — so the two other requests stay out of it.
    const channel = supabase
      .channel('shell-badges')
      .on('postgres_changes', { event: '*', schema: 'public', table: 'contacts' }, () =>
        countUnread(),
      )
      .subscribe();

    return () => {
      alive = false;
      clearInterval(timer);
      void supabase.removeChannel(channel);
    };
  }, []);

  const signOut = useCallback(async () => {
    await createClient().auth.signOut();
    router.replace('/login');
  }, [router]);

  const rail = (
    <nav className="on-ink flex h-full w-[248px] shrink-0 flex-col bg-ink text-white shadow-pop">
      <div className="flex items-center gap-3 border-b border-white/[0.07] px-5 py-[18px]">
        <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-chilli to-chilli-dark font-display text-sm font-extrabold shadow-lg shadow-chilli/20">
          K
        </span>
        <span>
          <span className="block font-display text-base font-extrabold tracking-tight">K&nbsp;FOOD</span>
          <span className="block text-[9px] font-semibold uppercase tracking-[0.16em] text-ink-soft">Operations</span>
        </span>
        <button
          onClick={() => setOpen(false)}
          className="ml-auto rounded-lg p-1.5 text-ink-soft hover:bg-white/10 hover:text-white md:hidden"
          aria-label="Close menu"
        >
          <Icon name="close" className="h-5 w-5" />
        </button>
      </div>

      <div className="scroll-thin flex-1 overflow-y-auto px-3 pb-4 pt-5">
        {GROUPS.map((group) => (
          <div key={group.heading} className="mb-5">
            <p className="px-2 pb-1.5 font-mono text-2xs uppercase tracking-[0.16em] text-ink-soft/70">
              {group.heading}
            </p>
            <ul className="space-y-0.5">
              {group.items.map((item) => {
                const active =
                  item.href === '/' ? pathname === '/' : pathname.startsWith(item.href);
                const badge = item.badge ? counts[item.badge] : 0;
                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      aria-current={active ? 'page' : undefined}
                      className={`relative flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition ${
                        active
                          ? 'bg-white/[0.11] font-semibold text-white shadow-sm'
                          : 'text-ink-soft hover:bg-white/[0.06] hover:text-white'
                      }`}
                    >
                      {active && <span className="absolute inset-y-2 left-0 w-0.5 rounded-full bg-chilli" />}
                      <Icon name={item.icon} className="h-[18px] w-[18px]" />
                      {item.label}
                      {badge > 0 && (
                        <span
                          className={`ml-auto rounded-full px-1.5 py-0.5 font-mono text-2xs tnum ${
                            item.badge === 'unread'
                              ? 'bg-chilli text-white'
                              : 'bg-broth text-ink'
                          }`}
                        >
                          {badge}
                        </span>
                      )}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </div>

      <div className="border-t border-ink-line px-4 py-3.5">
        <div className="flex items-center gap-2.5">
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-white/10 text-xs font-semibold text-white">
            {(email?.[0] ?? 'K').toUpperCase()}
          </span>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-xs font-medium text-white">Staff account</span>
            {email && <span className="block truncate text-[10px] text-ink-soft">{email}</span>}
          </span>
          <button
            onClick={signOut}
            className="rounded-lg p-2 text-ink-soft transition hover:bg-white/10 hover:text-white"
            title="Sign out"
            aria-label="Sign out"
          >
            <Icon name="out" className="h-4 w-4" />
          </button>
        </div>
      </div>
    </nav>
  );

  return (
    <div className="flex h-screen">
      <div className="hidden md:block">{rail}</div>

      {open && (
        <div className="fixed inset-0 z-40 flex md:hidden">
          <div className="animate-rise">{rail}</div>
          <button
            className="flex-1 bg-ink/40"
            onClick={() => setOpen(false)}
            aria-label="Close menu"
          />
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col bg-paper">
        <header className="flex items-center gap-2 border-b border-line bg-card px-3 py-2.5 shadow-card md:hidden">
          <button
            onClick={() => setOpen(true)}
            className="rounded-lg p-1.5 text-soy hover:bg-ink/5 hover:text-ink"
            aria-label="Open menu"
          >
            <Icon name="menu" />
          </button>
          <span className="font-display text-sm font-extrabold tracking-tight">K&nbsp;FOOD</span>
          {counts.unread > 0 && (
            <span className="ml-auto rounded-full bg-chilli px-2 py-0.5 font-mono text-2xs text-white tnum">
              {counts.unread} unread
            </span>
          )}
        </header>

        <main className="min-h-0 flex-1 overflow-y-auto">{children}</main>
      </div>
    </div>
  );
}

/**
 * The top of a page: what it is, in display type, with its controls beside it.
 */
export function PageHeader({
  title,
  lede,
  children,
}: {
  title: string;
  lede?: string;
  children?: React.ReactNode;
}) {
  return (
    <header className="mb-6 flex flex-wrap items-end gap-x-4 gap-y-3 border-b border-line pb-4">
      <div className="min-w-0">
        <h1 className="font-display text-[1.65rem] font-extrabold tracking-tightest">{title}</h1>
        {lede && <p className="mt-1 text-sm text-soy">{lede}</p>}
      </div>
      {children && <div className="ml-auto flex flex-wrap items-center gap-2">{children}</div>}
    </header>
  );
}

/** Every page body sits in the same column. */
export function Page({
  children,
  wide = false,
}: {
  children: React.ReactNode;
  wide?: boolean;
}) {
  return (
    <div className={`mx-auto w-full p-4 sm:p-6 ${wide ? 'max-w-[1400px]' : 'max-w-6xl'}`}>
      {children}
    </div>
  );
}

/**
 * The rail everywhere except the sign-in screen, which has no session to hang
 * a nav off and no page to go back to.
 */
export function Chrome({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  if (pathname.startsWith('/login')) return <>{children}</>;
  return <AppShell>{children}</AppShell>;
}

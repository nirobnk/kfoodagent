'use client';

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import { api, ApiError } from '@/lib/api';
import { Page, PageHeader } from '@/components/AppShell';
import { HeatBars } from '@/components/ui/HeatBars';
import { Icon } from '@/components/ui/Icon';
import { Chip, DayBars, Delta, Empty, Loading, Problem, Stat } from '@/components/ui/Bits';
import { attentionReason, change, dueLabel, isOverdue, lifecycleOf } from '@/lib/crm';
import { contactLabel, formatMoney, formatRelative } from '@/lib/format';
import type { Analytics, CustomerSummary, Task } from '@/lib/types';

/**
 * The landing page answers one question: who needs something from us today.
 *
 * It is not a wall of totals. The takings and the chart are there because the
 * owner opens this at closing time, but the top half is a worklist — unread
 * chats, overdue follow-ups, customers who have gone quiet — and every row on
 * it is a link to the place where something can be done about it.
 */

const ATTENTION_LIMIT = 6;

export default function OverviewPage() {
  const [analytics, setAnalytics] = useState<Analytics | null>(null);
  const [customers, setCustomers] = useState<CustomerSummary[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [figures, book, followUps] = await Promise.all([
        api.analytics(30),
        api.listCustomers(),
        api.listTasks('open'),
      ]);
      setAnalytics(figures);
      setCustomers(book.customers);
      setTasks(followUps.tasks);
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 401
          ? 'Your session expired. Sign in again to load today.'
          : err instanceof Error
            ? err.message
            : 'Could not reach the backend.',
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const needsAttention = customers
    .map((row) => ({
      row,
      reason: attentionReason(row.stats, row.contact.lifecycle, row.contact.unread_count),
    }))
    .filter((entry) => entry.reason !== null)
    // Unread first: somebody is waiting on a reply right now. Then whoever has
    // been quiet longest, because that is the message nobody will send on their own.
    .sort((a, b) => {
      const unread = b.row.contact.unread_count - a.row.contact.unread_count;
      if (unread !== 0) return unread;
      return (b.row.stats.days_since_last_order ?? 0) - (a.row.stats.days_since_last_order ?? 0);
    })
    .slice(0, ATTENTION_LIMIT);

  const overdue = tasks.filter((task) => isOverdue(task));
  const today = analytics?.revenue_by_day.at(-1);
  const current = analytics?.totals.current;
  const previous = analytics?.totals.previous;

  return (
    <Page wide>
      <PageHeader
        title="Today"
        lede="Who is waiting, what is late, and what the shop took."
      >
        <button onClick={load} className="btn-quiet" disabled={loading}>
          <Icon name="refresh" className="h-4 w-4" />
          Refresh
        </button>
      </PageHeader>

      {error && (
        <div className="mb-4">
          <Problem onRetry={load}>{error}</Problem>
        </div>
      )}

      {loading && !analytics && <Loading what="today" />}

      {analytics && current && previous && (
        <>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <Stat
              label="Taken today"
              value={formatMoney(today?.revenue ?? 0)}
              sub={`${today?.orders ?? 0} order${today?.orders === 1 ? '' : 's'}`}
            />
            <Stat
              label="Last 30 days"
              value={formatMoney(current.revenue)}
              sub={<Delta percent={change(current.revenue, previous.revenue)} />}
            />
            <Stat
              label="Customers who ordered"
              value={String(current.customers)}
              sub={`${analytics.acquisition.new_customers} of them for the first time`}
            />
            <Stat
              label="Follow-ups overdue"
              value={String(overdue.length)}
              tone={overdue.length > 0 ? 'hot' : 'plain'}
              sub={`${tasks.length} open in total`}
            />
          </div>

          <div className="mt-5 grid gap-4 lg:grid-cols-[1.35fr_1fr]">
            {/* --- the worklist ------------------------------------------- */}
            <section className="card p-5">
              <div className="mb-4 flex items-baseline gap-3">
                <h2 className="font-display text-lg font-extrabold tracking-tightest">
                  Needs attention
                </h2>
                <Link
                  href="/customers"
                  className="ml-auto text-sm font-medium text-chilli underline underline-offset-4"
                >
                  All customers
                </Link>
              </div>

              {needsAttention.length === 0 ? (
                <Empty title="Nobody is waiting">
                  Every chat is answered and no customer has gone quiet. This list fills itself
                  back up on its own.
                </Empty>
              ) : (
                <ul className="divide-y divide-line">
                  {needsAttention.map(({ row, reason }) => {
                    const stage = lifecycleOf(row.contact.lifecycle);
                    return (
                      <li key={row.contact.id}>
                        <Link
                          href={`/customers?id=${row.contact.id}`}
                          className="-mx-2 flex items-center gap-3 rounded-lg px-2 py-3 transition hover:bg-paper"
                        >
                          <span className="min-w-0 flex-1">
                            <span className="flex items-center gap-2">
                              <span className="truncate font-medium">
                                {contactLabel(row.contact)}
                              </span>
                              <Chip className={stage.chip}>{stage.label}</Chip>
                            </span>
                            <span className="mt-0.5 flex items-center gap-2 text-sm text-soy">
                              {row.contact.unread_count > 0 && (
                                <Icon name="inbox" className="h-3.5 w-3.5 text-chilli" />
                              )}
                              {reason}
                              {row.open_tasks > 0 && ` · ${row.open_tasks} follow-up`}
                            </span>
                          </span>
                          <span className="hidden sm:block">
                            <HeatBars stats={row.stats} showKeys={false} />
                          </span>
                          <span className="w-28 shrink-0 whitespace-nowrap text-right font-mono text-sm tnum">
                            {formatMoney(row.stats.lifetime_value)}
                          </span>
                        </Link>
                      </li>
                    );
                  })}
                </ul>
              )}
            </section>

            {/* --- what is late -------------------------------------------- */}
            <section className="card p-5">
              <div className="mb-4 flex items-baseline gap-3">
                <h2 className="font-display text-lg font-extrabold tracking-tightest">
                  Follow-ups
                </h2>
                <Link
                  href="/tasks"
                  className="ml-auto text-sm font-medium text-chilli underline underline-offset-4"
                >
                  All follow-ups
                </Link>
              </div>

              {tasks.length === 0 ? (
                <Empty
                  title="Nothing promised"
                  action={
                    <Link href="/tasks" className="btn-primary">
                      Add a follow-up
                    </Link>
                  }
                >
                  A follow-up is anything someone said they would do — ring a customer back, chase
                  a delivery, reorder a line that keeps selling out.
                </Empty>
              ) : (
                <ul className="space-y-2.5">
                  {tasks.slice(0, 6).map((task) => {
                    const late = isOverdue(task);
                    return (
                      <li key={task.id} className="flex items-start gap-2.5">
                        <span
                          className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${
                            late ? 'bg-chilli' : task.due_at ? 'bg-broth' : 'bg-ink/20'
                          }`}
                        />
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-sm">{task.title}</span>
                          <span
                            className={`font-mono text-2xs ${late ? 'text-chilli' : 'text-soy'}`}
                          >
                            {dueLabel(task)}
                            {task.assigned_to ? ` · ${task.assigned_to}` : ''}
                          </span>
                        </span>
                      </li>
                    );
                  })}
                </ul>
              )}
            </section>
          </div>

          {/* --- the takings --------------------------------------------- */}
          <section className="card mt-4 p-5">
            <div className="mb-4 flex flex-wrap items-baseline gap-3">
              <h2 className="font-display text-lg font-extrabold tracking-tightest">
                Takings, 30 days
              </h2>
              <p className="text-sm text-soy">
                {formatMoney(current.average_order)} average order
                {current.cancelled > 0 && ` · ${current.cancelled} cancelled`}
              </p>
              <Link
                href="/insights"
                className="ml-auto text-sm font-medium text-chilli underline underline-offset-4"
              >
                Insights
              </Link>
            </div>
            <DayBars points={analytics.revenue_by_day} format={formatMoney} />
            <div className="mt-2 flex justify-between font-mono text-2xs text-soy">
              <span>{analytics.revenue_by_day[0]?.day}</span>
              <span>{analytics.revenue_by_day.at(-1)?.day}</span>
            </div>
          </section>

          <p className="mt-4 text-center font-mono text-2xs text-soy">
            Updated {formatRelative(new Date().toISOString()) || 'now'} · every figure here is
            worked out from the orders themselves
          </p>
        </>
      )}
    </Page>
  );
}

'use client';

import { useCallback, useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { Page, PageHeader } from '@/components/AppShell';
import {
  DayBars,
  Delta,
  Empty,
  Loading,
  Problem,
  Segmented,
  ShareBar,
  Stat,
} from '@/components/ui/Bits';
import { LIFECYCLE, LIFECYCLE_ORDER, SOURCES, change } from '@/lib/crm';
import { formatMoney } from '@/lib/format';
import type { Analytics } from '@/lib/types';

/**
 * Where the money comes from.
 *
 * Every figure is worked out from the orders at read time by backend/crm.py —
 * nothing on this page is stored, so nothing on it can quietly drift away from
 * the orders it claims to describe.
 */

const STATUS_TONE: Record<string, string> = {
  new: 'bg-ink',
  confirmed: 'bg-scallion',
  preparing: 'bg-broth',
  dispatched: 'bg-buldak',
  delivered: 'bg-scallion',
  cancelled: 'bg-soy',
};

export default function InsightsPage() {
  const [days, setDays] = useState<30 | 90 | 365>(30);
  const [data, setData] = useState<Analytics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await api.analytics(days));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load the figures.');
    } finally {
      setLoading(false);
    }
  }, [days]);

  useEffect(() => {
    void load();
  }, [load]);

  const current = data?.totals.current;
  const previous = data?.totals.previous;
  const customersTotal = data
    ? Object.values(data.segments).reduce((sum, count) => sum + (count ?? 0), 0)
    : 0;

  return (
    <Page wide>
      <PageHeader title="Insights" lede="What sold, to whom, and whether it is growing.">
        <Segmented
          value={String(days) as '30' | '90' | '365'}
          onChange={(value) => setDays(Number(value) as 30 | 90 | 365)}
          options={[
            { value: '30', label: '30 days' },
            { value: '90', label: '90 days' },
            { value: '365', label: 'A year' },
          ]}
        />
      </PageHeader>

      {error && (
        <div className="mb-4">
          <Problem onRetry={load}>{error}</Problem>
        </div>
      )}
      {loading && !data && <Loading what="the figures" />}

      {data && current && previous && (
        <>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <Stat
              label={`Revenue, ${days} days`}
              value={formatMoney(current.revenue)}
              sub={<Delta percent={change(current.revenue, previous.revenue)} />}
            />
            <Stat
              label="Orders"
              value={String(current.orders)}
              sub={<Delta percent={change(current.orders, previous.orders)} />}
            />
            <Stat
              label="Average order"
              value={formatMoney(current.average_order)}
              sub={<Delta percent={change(current.average_order, previous.average_order)} />}
            />
            <Stat
              label="Customers who bought"
              value={String(current.customers)}
              sub={<Delta percent={change(current.customers, previous.customers)} />}
            />
          </div>

          <section className="card mt-4 p-5">
            <h2 className="font-display text-lg font-extrabold tracking-tightest">
              Takings by day
            </h2>
            <p className="mb-4 text-sm text-soy">
              Bars, not a line: a shop takes money on separate days, and a line would draw a trend
              through hours that never happened.
            </p>
            <DayBars points={data.revenue_by_day} format={formatMoney} />
            <div className="mt-2 flex justify-between font-mono text-2xs text-soy">
              <span>{data.revenue_by_day[0]?.day}</span>
              <span>{data.revenue_by_day.at(-1)?.day}</span>
            </div>
          </section>

          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            {/* --- what sells -------------------------------------------- */}
            <section className="card p-5">
              <h2 className="mb-4 font-display text-lg font-extrabold tracking-tightest">
                Best sellers
              </h2>
              {data.top_products.length === 0 ? (
                <Empty title="Nothing sold in this window">
                  Widen the window, or check that orders are reaching the dashboard.
                </Empty>
              ) : (
                <ul className="space-y-3">
                  {data.top_products.map((product) => (
                    <li key={product.name}>
                      <div className="flex items-baseline gap-2">
                        <span className="min-w-0 flex-1 truncate text-sm">{product.name}</span>
                        <span className="font-mono text-2xs text-soy tnum">
                          {product.quantity} sold
                        </span>
                        <span className="w-28 shrink-0 whitespace-nowrap text-right font-mono text-sm tnum">
                          {formatMoney(product.revenue)}
                        </span>
                      </div>
                      <div className="mt-1.5">
                        <ShareBar
                          value={product.revenue}
                          total={data.top_products[0].revenue}
                          tone="bg-chilli"
                        />
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            {/* --- new against returning ---------------------------------- */}
            <section className="card p-5">
              <h2 className="font-display text-lg font-extrabold tracking-tightest">
                New against returning
              </h2>
              <p className="mb-4 text-sm text-soy">
                A customer is new on their first order ever, not their first in this window.
              </p>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <p className="eyebrow">New customers</p>
                  <p className="mt-1 font-display text-2xl font-extrabold tracking-tightest tnum">
                    {data.acquisition.new_customers}
                  </p>
                  <p className="font-mono text-2xs text-soy">
                    {formatMoney(data.acquisition.new_revenue)}
                  </p>
                </div>
                <div>
                  <p className="eyebrow">Came back</p>
                  <p className="mt-1 font-display text-2xl font-extrabold tracking-tightest tnum">
                    {data.acquisition.returning_customers}
                  </p>
                  <p className="font-mono text-2xs text-soy">
                    {formatMoney(data.acquisition.returning_revenue)}
                  </p>
                </div>
              </div>

              <div className="mt-4">
                <ShareBar
                  value={data.acquisition.returning_revenue}
                  total={data.acquisition.returning_revenue + data.acquisition.new_revenue}
                  tone="bg-scallion"
                />
                <p className="mt-2 text-xs text-soy">
                  {data.acquisition.returning_revenue + data.acquisition.new_revenue > 0
                    ? `${Math.round(
                        (data.acquisition.returning_revenue /
                          (data.acquisition.returning_revenue + data.acquisition.new_revenue)) *
                          100,
                      )}% of the money came from customers who had bought before.`
                    : 'No money in this window yet.'}
                </p>
              </div>
            </section>

            {/* --- where orders come from --------------------------------- */}
            <section className="card p-5">
              <h2 className="mb-4 font-display text-lg font-extrabold tracking-tightest">
                Where orders come from
              </h2>
              <Mix rows={data.source_mix} labels={SOURCES} tone="bg-ink" />
            </section>

            {/* --- how orders end ----------------------------------------- */}
            <section className="card p-5">
              <h2 className="mb-4 font-display text-lg font-extrabold tracking-tightest">
                How orders end
              </h2>
              <Mix rows={data.status_mix} tones={STATUS_TONE} />
            </section>
          </div>

          {/* --- the book ------------------------------------------------- */}
          <section className="card mt-4 p-5">
            <h2 className="mb-4 font-display text-lg font-extrabold tracking-tightest">
              The customer book
            </h2>
            <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-7">
              {LIFECYCLE_ORDER.map((key) => (
                <div key={key} className="rounded-card border border-line p-3">
                  <span className={`mb-2 block h-1 w-8 rounded-full ${LIFECYCLE[key].band}`} />
                  <p className="font-display text-xl font-extrabold tracking-tightest tnum">
                    {data.segments[key] ?? 0}
                  </p>
                  <p className="text-xs font-medium">{LIFECYCLE[key].label}</p>
                  <p className="mt-1 text-2xs leading-snug text-soy">{LIFECYCLE[key].hint}</p>
                </div>
              ))}
            </div>
            <p className="mt-3 font-mono text-2xs text-soy">
              {customersTotal} customers on the book · {data.messages.outbound} messages sent since{' '}
              {data.messages.month_start} · {data.messages.inbound} received
            </p>
          </section>
        </>
      )}
    </Page>
  );
}

function Mix({
  rows,
  labels,
  tone = 'bg-ink',
  tones,
}: {
  rows: { key: string; orders: number; revenue: number }[];
  labels?: Record<string, string>;
  tone?: string;
  tones?: Record<string, string>;
}) {
  const total = rows.reduce((sum, row) => sum + row.orders, 0);
  if (total === 0) {
    return <Empty title="No orders in this window">Widen the window to see the split.</Empty>;
  }

  return (
    <ul className="space-y-3">
      {rows.map((row) => (
        <li key={row.key}>
          <div className="flex items-baseline gap-2">
            <span className="min-w-0 flex-1 truncate text-sm capitalize">
              {labels?.[row.key] ?? row.key}
            </span>
            <span className="font-mono text-2xs text-soy tnum">
              {Math.round((row.orders / total) * 100)}% · {row.orders}
            </span>
            <span className="w-28 shrink-0 whitespace-nowrap text-right font-mono text-sm tnum">
              {formatMoney(row.revenue)}
            </span>
          </div>
          <div className="mt-1.5">
            <ShareBar value={row.orders} total={total} tone={tones?.[row.key] ?? tone} />
          </div>
        </li>
      ))}
    </ul>
  );
}

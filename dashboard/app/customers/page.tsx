'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { api, ApiError } from '@/lib/api';
import { CustomerPanel } from '@/components/CustomerPanel';
import { HeatBars } from '@/components/ui/HeatBars';
import { Icon } from '@/components/ui/Icon';
import { Chip, Empty, Loading, Problem } from '@/components/ui/Bits';
import { LIFECYCLE, LIFECYCLE_ORDER, lifecycleOf } from '@/lib/crm';
import { contactLabel, formatMoney, formatRelative } from '@/lib/format';
import type { CrmContact, CustomerSummary, Lifecycle } from '@/lib/types';

type Sort = 'attention' | 'value' | 'recent' | 'name';

const SORTS: { value: Sort; label: string }[] = [
  { value: 'attention', label: 'Needs attention' },
  { value: 'value', label: 'Biggest spenders' },
  { value: 'recent', label: 'Recently seen' },
  { value: 'name', label: 'A–Z' },
];

export default function CustomersPage() {
  const [customers, setCustomers] = useState<CustomerSummary[]>([]);
  const [segments, setSegments] = useState<Partial<Record<Lifecycle, number>>>({});
  const [stage, setStage] = useState<Lifecycle | 'all'>('all');
  const [sort, setSort] = useState<Sort>('attention');
  const [query, setQuery] = useState('');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await api.listCustomers();
      setCustomers(result.customers);
      setSegments(result.segments);
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 401
          ? 'Your session expired. Sign in again to load the customer book.'
          : err instanceof Error
            ? err.message
            : 'Could not load the customer book.',
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  // A customer record is worth linking to — from a chat, or in a message to
  // whoever is on shift. Read on mount and written on every change, without
  // useSearchParams, which would need a Suspense boundary in a static export.
  useEffect(() => {
    const id = new URLSearchParams(window.location.search).get('id');
    if (id) setSelectedId(id);
  }, []);

  useEffect(() => {
    const url = new URL(window.location.href);
    if (selectedId) url.searchParams.set('id', selectedId);
    else url.searchParams.delete('id');
    window.history.replaceState(null, '', url);
  }, [selectedId]);

  /** One customer changed under us — patch the row rather than reloading 500. */
  const patchRow = useCallback((contact: CrmContact) => {
    setCustomers((current) =>
      current.map((row) => (row.contact.id === contact.id ? { ...row, contact } : row)),
    );
  }, []);

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const filtered = customers.filter((row) => {
      if (stage !== 'all' && row.contact.lifecycle !== stage) return false;
      if (!needle) return true;
      return (
        contactLabel(row.contact).toLowerCase().includes(needle) ||
        row.contact.wa_id.includes(needle) ||
        (row.contact.city ?? '').toLowerCase().includes(needle)
      );
    });

    const ranked = [...filtered];
    if (sort === 'value') {
      ranked.sort((a, b) => b.stats.lifetime_value - a.stats.lifetime_value);
    } else if (sort === 'recent') {
      ranked.sort((a, b) => Date.parse(b.contact.last_seen) - Date.parse(a.contact.last_seen));
    } else if (sort === 'name') {
      ranked.sort((a, b) => contactLabel(a.contact).localeCompare(contactLabel(b.contact)));
    } else {
      // Attention: unread first, then whoever has been quiet longest. The same
      // order the Today page uses, so the two screens agree about urgency.
      ranked.sort((a, b) => {
        const unread = b.contact.unread_count - a.contact.unread_count;
        if (unread !== 0) return unread;
        const tasks = b.open_tasks - a.open_tasks;
        if (tasks !== 0) return tasks;
        return (b.stats.days_since_last_order ?? -1) - (a.stats.days_since_last_order ?? -1);
      });
    }
    return ranked;
  }, [customers, query, sort, stage]);

  const selected = customers.find((row) => row.contact.id === selectedId) ?? null;
  const total = customers.length;

  return (
    <div className="flex h-full min-h-0">
      {/* --- the book ---------------------------------------------------- */}
      <section
        className={`flex min-h-0 w-full flex-col border-r border-line bg-card lg:w-[400px] ${
          selectedId ? 'hidden lg:flex' : 'flex'
        }`}
      >
        <header className="border-b border-line px-4 pb-3 pt-4">
          <div className="flex items-baseline gap-2">
            <h1 className="font-display text-xl font-extrabold tracking-tightest">
              Customer book
            </h1>
            <span className="font-mono text-2xs text-soy tnum">
              {total} {total === 1 ? 'person' : 'people'}
            </span>
          </div>

          <div className="relative mt-3">
            <Icon
              name="search"
              className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-soy"
            />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search name, number or town"
              className="field bg-paper pl-8"
            />
          </div>

          <div className="scroll-thin -mx-1 mt-3 flex gap-1 overflow-x-auto px-1 pb-1">
            <StageChip
              label="Everyone"
              count={total}
              active={stage === 'all'}
              onClick={() => setStage('all')}
            />
            {LIFECYCLE_ORDER.filter((key) => (segments[key] ?? 0) > 0).map((key) => (
              <StageChip
                key={key}
                label={LIFECYCLE[key].label}
                count={segments[key] ?? 0}
                active={stage === key}
                onClick={() => setStage(key)}
              />
            ))}
          </div>

          <div className="mt-2 flex items-center gap-2">
            <label className="eyebrow" htmlFor="customer-sort">
              Sort
            </label>
            <select
              id="customer-sort"
              value={sort}
              onChange={(event) => setSort(event.target.value as Sort)}
              className="rounded-lg border border-line bg-card px-2 py-1 text-sm"
            >
              {SORTS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            <button onClick={load} className="btn-ghost ml-auto px-2 py-1" title="Reload">
              <Icon name="refresh" className="h-4 w-4" />
            </button>
          </div>
        </header>

        <div className="scroll-thin min-h-0 flex-1 overflow-y-auto">
          {loading && customers.length === 0 && (
            <div className="px-4">
              <Loading what="the customer book" />
            </div>
          )}

          {error && (
            <div className="p-3">
              <Problem onRetry={load}>{error}</Problem>
            </div>
          )}

          {!loading && visible.length === 0 && (
            <div className="p-4">
              <Empty title="No one here">
                {query
                  ? 'Nothing matches that search. Try part of a phone number.'
                  : 'Customers appear the first time they message the WhatsApp number or buy at the counter.'}
              </Empty>
            </div>
          )}

          <ul>
            {visible.map((row) => (
              <CustomerRow
                key={row.contact.id}
                row={row}
                selected={row.contact.id === selectedId}
                onSelect={() => setSelectedId(row.contact.id)}
              />
            ))}
          </ul>
        </div>
      </section>

      {/* --- the record --------------------------------------------------- */}
      <main className={`min-w-0 flex-1 ${selectedId ? 'block' : 'hidden lg:block'}`}>
        {selectedId ? (
          <CustomerPanel
            key={selectedId}
            contactId={selectedId}
            summary={selected}
            onClose={() => setSelectedId(null)}
            onContactSaved={patchRow}
          />
        ) : (
          <div className="flex h-full items-center justify-center p-6">
            <div className="max-w-sm text-center">
              <Icon name="customers" className="mx-auto h-8 w-8 text-ink/25" />
              <p className="mt-3 font-display text-base font-bold">Pick a customer</p>
              <p className="mt-1 text-sm text-soy">
                Every record holds what they have bought, what was said, what we noticed, and what
                someone promised to do next.
              </p>
              <p className="mt-4 inline-flex items-center gap-2 rounded-lg bg-card px-3 py-2 text-xs text-soy ring-1 ring-line">
                <span className="flex gap-[3px]">
                  {[1, 2, 3, 4, 5].map((step) => (
                    <span
                      key={step}
                      className={`h-1.5 w-2.5 rounded-[2px] ${
                        step <= 3 ? 'bg-chilli' : 'bg-ink/10'
                      }`}
                    />
                  ))}
                </span>
                The chilli scale reads R, F and M: how lately, how often, how much.
              </p>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

function StageChip({
  label,
  count,
  active,
  onClick,
}: {
  label: string;
  count: number;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      aria-pressed={active}
      className={`shrink-0 rounded-lg px-2.5 py-1 text-xs font-medium transition ${
        active ? 'bg-ink text-white' : 'bg-paper text-soy hover:text-ink'
      }`}
    >
      {label}
      <span className={`ml-1.5 tnum ${active ? 'text-white/60' : 'text-soy/70'}`}>{count}</span>
    </button>
  );
}

function CustomerRow({
  row,
  selected,
  onSelect,
}: {
  row: CustomerSummary;
  selected: boolean;
  onSelect: () => void;
}) {
  const stage = lifecycleOf(row.contact.lifecycle);

  return (
    <li>
      <button
        onClick={onSelect}
        className={`flex w-full items-start gap-3 border-b border-line px-4 py-3 text-left transition hover:bg-paper ${
          selected ? 'bg-paper' : ''
        }`}
      >
        {/* The stage as a colour stripe, so the book can be read down the edge. */}
        <span className={`mt-0.5 h-9 w-1 shrink-0 rounded-full ${stage.band}`} />

        <span className="min-w-0 flex-1">
          <span className="flex items-center gap-2">
            <span className="truncate font-medium">{contactLabel(row.contact)}</span>
            {row.contact.unread_count > 0 && (
              <span className="shrink-0 rounded-full bg-chilli px-1.5 py-0.5 font-mono text-2xs font-semibold text-white tnum">
                {row.contact.unread_count}
              </span>
            )}
            {row.open_tasks > 0 && (
              <Icon name="tasks" className="h-3.5 w-3.5 shrink-0 text-broth" />
            )}
            <span className="ml-auto shrink-0 whitespace-nowrap font-mono text-sm tnum">
              {formatMoney(row.stats.lifetime_value)}
            </span>
          </span>

          <span className="mt-1 flex items-center gap-2">
            <Chip className={stage.chip}>{stage.label}</Chip>
            <span className="truncate font-mono text-2xs text-soy">
              {row.stats.orders} order{row.stats.orders === 1 ? '' : 's'}
              {row.stats.days_since_last_order !== null
                ? ` · ${row.stats.days_since_last_order}d ago`
                : ' · never'}
            </span>
            <span className="ml-auto shrink-0 text-2xs text-soy">
              {formatRelative(row.contact.last_seen)}
            </span>
          </span>

          <span className="mt-2 block">
            <HeatBars stats={row.stats} />
          </span>
        </span>
      </button>
    </li>
  );
}

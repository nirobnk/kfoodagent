'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { Nav } from '@/components/Nav';
import { api, ApiError } from '@/lib/api';
import type { StockItem, StockMovement, StockReason } from '@/lib/types';

/**
 * Stock, as staff work it.
 *
 * Everything here is counted in SINGLE UNITS, one row per product. A 5 Pack
 * and a carton of 20 are not separate things on a shelf — staff make them up
 * from singles — so entering 100 means a hundred singles, and selling one
 * 5 Pack takes five of them away.
 *
 * The numbers are the sum of a ledger, not a field someone types over, so every
 * figure can be opened up and explained. Tracking is off per product until
 * somebody counts it: an untracked product sells without limit exactly as it
 * did before stock existed, and switching it on before the first count would
 * have the agent telling customers we have none of something the shelf is
 * full of.
 */

const REASONS: { value: Exclude<StockReason, 'sold' | 'count'>; label: string; sign: 1 | -1 }[] = [
  { value: 'received', label: 'Delivery received', sign: 1 },
  { value: 'returned', label: 'Customer returned', sign: 1 },
  { value: 'damaged', label: 'Damaged', sign: -1 },
  { value: 'expired', label: 'Expired', sign: -1 },
  { value: 'adjusted', label: 'Correction', sign: 1 },
];

const LOW_STOCK = 3;

function reasonLabel(reason: StockReason): string {
  const found = REASONS.find((r) => r.value === reason);
  if (found) return found.label;
  return reason === 'sold' ? 'Sold' : reason === 'count' ? 'Stocktake' : reason;
}

export default function InventoryPage() {
  const [items, setItems] = useState<StockItem[]>([]);
  const [movements, setMovements] = useState<StockMovement[]>([]);
  const [selected, setSelected] = useState<StockItem | null>(null);
  const [query, setQuery] = useState('');
  const [trackedOnly, setTrackedOnly] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const { items: rows } = await api.listStock();
      setItems(rows);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not load stock');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const openLedger = useCallback(async (item: StockItem) => {
    setSelected(item);
    setMovements([]);
    try {
      const { movements: rows } = await api.listStockMovements(item.id);
      setMovements(rows);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not load movements');
    }
  }, []);

  async function run(label: string, action: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await action();
      await load();
      if (selected) await openLedger(selected);
      setNotice(label);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'That did not work');
    } finally {
      setBusy(false);
    }
  }

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return items.filter((item) => {
      if (trackedOnly && !item.track_stock) return false;
      if (!needle) return true;
      return `${item.product_name ?? ''} ${item.sku ?? ''} ${item.variant_label ?? ''}`
        .toLowerCase()
        .includes(needle);
    });
  }, [items, query, trackedOnly]);

  const tracked = items.filter((i) => i.track_stock);
  const out = tracked.filter((i) => i.stock_quantity <= 0);
  const low = tracked.filter((i) => i.stock_quantity > 0 && i.stock_quantity <= LOW_STOCK);

  return (
    <div className="flex h-dvh flex-col bg-wa-panel">
      <Nav />

      <div className="flex flex-1 flex-col overflow-hidden lg:flex-row">
        <section className="flex min-w-0 flex-1 flex-col overflow-hidden">
          <div className="flex flex-wrap items-center gap-2 border-b border-black/5 bg-white px-4 py-3">
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search product or SKU"
              className="min-w-40 flex-1 rounded-lg border border-black/10 px-3 py-1.5 text-sm"
            />
            <label className="flex items-center gap-1.5 text-sm text-wa-muted">
              <input
                type="checkbox"
                checked={trackedOnly}
                onChange={(e) => setTrackedOnly(e.target.checked)}
              />
              Tracked only
            </label>
            <button
              onClick={() => run('Stock rebuilt from the ledger.', () => api.recomputeStock())}
              disabled={busy}
              title="Rebuild every quantity from the movements that produced it"
              className="rounded-lg border border-black/10 px-3 py-1.5 text-sm hover:bg-black/5 disabled:opacity-50"
            >
              Recheck totals
            </button>
          </div>

          <div className="flex gap-3 border-b border-black/5 bg-white px-4 py-2 text-xs text-wa-muted">
            <span>{tracked.length} tracked</span>
            {out.length > 0 && (
              <span className="font-medium text-red-600">{out.length} out of stock</span>
            )}
            {low.length > 0 && (
              <span className="font-medium text-amber-700">{low.length} running low</span>
            )}
            {tracked.length === 0 && (
              <span>Nothing is tracked yet — count the singles on the shelf, then switch Track on.</span>
            )}
          </div>

          {error && <p className="bg-red-50 px-4 py-2 text-sm text-red-700">{error}</p>}
          {notice && <p className="bg-emerald-50 px-4 py-2 text-sm text-emerald-800">{notice}</p>}

          <div className="flex-1 overflow-y-auto">
            {loading ? (
              <p className="px-4 py-6 text-sm text-wa-muted">Loading…</p>
            ) : (
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-wa-panel text-left text-xs uppercase text-wa-muted">
                  <tr>
                    <th className="px-4 py-2 font-medium">Product</th>
                    <th className="px-2 py-2 font-medium">Singles on hand</th>
                    <th className="px-2 py-2 font-medium">Track</th>
                    <th className="px-2 py-2 font-medium">Record</th>
                  </tr>
                </thead>
                <tbody>
                  {visible.map((item) => (
                    <StockRow
                      key={item.id}
                      item={item}
                      busy={busy}
                      selected={selected?.id === item.id}
                      onOpen={() => openLedger(item)}
                      onRun={run}
                    />
                  ))}
                  {visible.length === 0 && (
                    <tr>
                      <td colSpan={4} className="px-4 py-6 text-sm text-wa-muted">
                        Nothing matches that.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            )}
          </div>
        </section>

        <aside className="flex w-full flex-col border-t border-black/5 bg-white lg:w-96 lg:border-l lg:border-t-0">
          <div className="border-b border-black/5 px-4 py-3">
            <h2 className="text-sm font-semibold">
              {selected ? selected.product_name : 'Movement history'}
            </h2>
            <p className="text-xs text-wa-muted">
              {selected
                ? `${selected.variant_label ?? ''} · ${selected.sku ?? ''}`
                : 'Pick a product to see why its number is what it is.'}
            </p>
          </div>

          <div className="flex-1 overflow-y-auto">
            {selected && movements.length === 0 && (
              <p className="px-4 py-4 text-sm text-wa-muted">
                No movements recorded yet.
              </p>
            )}
            <ul className="divide-y divide-black/5">
              {movements.map((m) => (
                <li key={m.id} className="px-4 py-2.5 text-sm">
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="font-medium">{reasonLabel(m.reason)}</span>
                    <span
                      className={`font-mono ${m.delta > 0 ? 'text-emerald-700' : 'text-red-600'}`}
                    >
                      {m.delta > 0 ? `+${m.delta}` : m.delta}
                    </span>
                  </div>
                  <div className="text-xs text-wa-muted">
                    {new Date(m.created_at).toLocaleString()} · {m.created_by}
                  </div>
                  {m.note && <div className="mt-0.5 text-xs text-wa-muted">{m.note}</div>}
                </li>
              ))}
            </ul>
          </div>
        </aside>
      </div>
    </div>
  );
}

function StockRow({
  item,
  busy,
  selected,
  onOpen,
  onRun,
}: {
  item: StockItem;
  busy: boolean;
  selected: boolean;
  onOpen: () => void;
  onRun: (label: string, action: () => Promise<unknown>) => Promise<void>;
}) {
  const [amount, setAmount] = useState('');
  const [reason, setReason] = useState<(typeof REASONS)[number]['value']>('received');

  const name = `${item.product_name ?? 'Unknown'}`;
  const qty = item.stock_quantity;
  const state = !item.track_stock
    ? 'text-wa-muted'
    : qty <= 0
      ? 'text-red-600 font-semibold'
      : qty <= LOW_STOCK
        ? 'text-amber-700 font-semibold'
        : 'text-emerald-700 font-semibold';

  function submit() {
    const value = Number(amount);
    if (!Number.isFinite(value) || value === 0) return;
    const sign = REASONS.find((r) => r.value === reason)?.sign ?? 1;
    // A correction is signed by whoever types it; everything else has an
    // obvious direction, so staff enter a plain number and cannot get it wrong.
    const delta = reason === 'adjusted' ? value : Math.abs(value) * sign;
    onRun(`${reasonLabel(reason)}: ${delta > 0 ? '+' : ''}${delta} ${name}`, () =>
      api.recordStockMovement(item.id, delta, reason),
    ).then(() => setAmount(''));
  }

  function count() {
    const value = Number(amount);
    if (!Number.isFinite(value) || value < 0) return;
    onRun(`Stocktake: ${name} set to ${value}`, () => api.countStock(item.id, value)).then(() =>
      setAmount(''),
    );
  }

  return (
    <tr className={`border-b border-black/5 ${selected ? 'bg-wa-panel' : 'hover:bg-black/[0.02]'}`}>
      <td className="px-4 py-2">
        <button onClick={onOpen} className="text-left">
          <div className="font-medium">{name}</div>
          <div className="text-xs text-wa-muted">
            {item.sku} · counted in singles
          </div>
        </button>
      </td>

      <td className={`px-2 py-2 ${state}`}>
        {item.track_stock ? qty : <span title="Not tracked — sells without limit">—</span>}
      </td>

      <td className="px-2 py-2">
        <button
          onClick={() =>
            onRun(
              `${item.track_stock ? 'Stopped' : 'Started'} tracking ${name}`,
              () => api.setStockTracking(item.id, !item.track_stock),
            )
          }
          disabled={busy}
          className={`rounded-full px-2 py-0.5 text-xs font-medium ${
            item.track_stock
              ? 'bg-emerald-50 text-emerald-800 ring-1 ring-emerald-200'
              : 'bg-black/5 text-wa-muted'
          }`}
        >
          {item.track_stock ? 'On' : 'Off'}
        </button>
      </td>

      <td className="px-2 py-2">
        <div className="flex flex-wrap items-center gap-1">
          <select
            value={reason}
            onChange={(e) => setReason(e.target.value as typeof reason)}
            className="rounded border border-black/10 px-1 py-1 text-xs"
          >
            {REASONS.map((r) => (
              <option key={r.value} value={r.value}>
                {r.label}
              </option>
            ))}
          </select>
          <input
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            inputMode="numeric"
            placeholder="0"
            className="w-14 rounded border border-black/10 px-1.5 py-1 text-xs"
          />
          <button
            onClick={submit}
            disabled={busy || !amount}
            className="rounded bg-wa-green px-2 py-1 text-xs font-medium text-white disabled:opacity-40"
          >
            Save
          </button>
          <button
            onClick={count}
            disabled={busy || !amount}
            title="Set this to the number of single units physically on the shelf"
            className="rounded border border-black/10 px-2 py-1 text-xs hover:bg-black/5 disabled:opacity-40"
          >
            Counted
          </button>
        </div>
      </td>
    </tr>
  );
}

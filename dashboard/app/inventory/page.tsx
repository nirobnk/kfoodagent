'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { Page, PageHeader } from '@/components/AppShell';
import { Empty, Loading, Problem } from '@/components/ui/Bits';
import { Icon } from '@/components/ui/Icon';
import { api, ApiError } from '@/lib/api';
import type { StockItem, StockMovement, StockReason } from '@/lib/types';

type StockFilter = 'all' | 'low' | 'out' | 'untracked';
type StockAction = Exclude<StockReason, 'sold'>;

const ACTIONS: { value: StockAction; label: string; hint: string; sign?: 1 | -1 }[] = [
  { value: 'received', label: 'Delivery received', hint: 'Adds units to the shelf', sign: 1 },
  { value: 'returned', label: 'Customer return', hint: 'Adds returned units', sign: 1 },
  { value: 'damaged', label: 'Damaged stock', hint: 'Removes unusable units', sign: -1 },
  { value: 'expired', label: 'Expired stock', hint: 'Removes expired units', sign: -1 },
  { value: 'adjusted', label: 'Manual correction', hint: 'Use + or − to correct the total' },
  { value: 'count', label: 'Full stocktake', hint: 'Sets the exact shelf count' },
];

const LOW_STOCK = 3;

function reasonLabel(reason: StockReason): string {
  if (reason === 'sold') return 'Sold';
  return ACTIONS.find((action) => action.value === reason)?.label ?? reason;
}

function stockState(item: StockItem) {
  if (!item.track_stock) {
    return { label: 'Not tracked', className: 'bg-ink/[0.05] text-soy', dot: 'bg-soy/45' };
  }
  if (item.stock_quantity <= 0) {
    return { label: 'Out of stock', className: 'bg-chilli-wash text-chilli-dark', dot: 'bg-chilli' };
  }
  if (item.stock_quantity <= LOW_STOCK) {
    return { label: 'Low stock', className: 'bg-broth-wash text-broth-dark', dot: 'bg-broth' };
  }
  return { label: 'In stock', className: 'bg-scallion-wash text-scallion', dot: 'bg-scallion' };
}

export default function InventoryPage() {
  const [items, setItems] = useState<StockItem[]>([]);
  const [movements, setMovements] = useState<StockMovement[]>([]);
  const [selected, setSelected] = useState<StockItem | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState<StockFilter>('all');
  const [loading, setLoading] = useState(true);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const { items: rows } = await api.listStock();
      setItems(rows);
      setSelected((current) => rows.find((row) => row.id === current?.id) ?? current);
      setError(null);
      return rows;
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not load stock');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const openLedger = useCallback(async (item: StockItem) => {
    setSelected(item);
    setMovements([]);
    setHistoryLoading(true);
    try {
      const { movements: rows } = await api.listStockMovements(item.id);
      setMovements(rows);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not load stock history');
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  async function run(label: string, action: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await action();
      const rows = await load();
      if (selected) {
        const refreshed = rows?.find((row) => row.id === selected.id) ?? selected;
        await openLedger(refreshed);
      }
      setNotice(label);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'That update could not be saved');
    } finally {
      setBusy(false);
    }
  }

  const summary = useMemo(() => {
    const tracked = items.filter((item) => item.track_stock);
    return {
      tracked: tracked.length,
      units: tracked.reduce((sum, item) => sum + Math.max(0, item.stock_quantity), 0),
      out: tracked.filter((item) => item.stock_quantity <= 0).length,
      low: tracked.filter((item) => item.stock_quantity > 0 && item.stock_quantity <= LOW_STOCK)
        .length,
      untracked: items.length - tracked.length,
    };
  }, [items]);

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return items.filter((item) => {
      if (
        filter === 'low' &&
        (!item.track_stock || item.stock_quantity <= 0 || item.stock_quantity > LOW_STOCK)
      )
        return false;
      if (filter === 'out' && (!item.track_stock || item.stock_quantity > 0)) return false;
      if (filter === 'untracked' && item.track_stock) return false;
      if (!needle) return true;
      return `${item.product_name ?? ''} ${item.sku ?? ''} ${item.variant_label ?? ''} ${item.category ?? ''}`
        .toLowerCase()
        .includes(needle);
    });
  }, [filter, items, query]);

  const filters: { value: StockFilter; label: string; count: number }[] = [
    { value: 'all', label: 'All items', count: items.length },
    { value: 'low', label: 'Low', count: summary.low },
    { value: 'out', label: 'Out', count: summary.out },
    { value: 'untracked', label: 'Untracked', count: summary.untracked },
  ];

  return (
    <Page wide>
      <PageHeader
        title="Inventory"
        lede="Know what is on the shelf and record every change in single units."
      >
        <button
          onClick={() =>
            void run('Stock totals rebuilt from the movement history.', () => api.recomputeStock())
          }
          disabled={busy}
          className="btn-quiet"
          title="Rebuild every quantity from its movement history"
        >
          <Icon name="refresh" className={`h-4 w-4 ${busy ? 'animate-spin' : ''}`} />
          Recheck totals
        </button>
      </PageHeader>

      <div className="mb-5 grid grid-cols-2 gap-3 xl:grid-cols-4">
        <SummaryCard
          label="Tracked products"
          value={summary.tracked}
          detail={`${items.length} products total`}
          icon="package"
        />
        <SummaryCard
          label="Singles on hand"
          value={summary.units}
          detail="Across tracked products"
          icon="stock"
        />
        <SummaryCard
          label="Running low"
          value={summary.low}
          detail={`At ${LOW_STOCK} units or fewer`}
          icon="warn"
          tone={summary.low ? 'warn' : 'good'}
        />
        <SummaryCard
          label="Out of stock"
          value={summary.out}
          detail="Needs attention"
          icon="close"
          tone={summary.out ? 'danger' : 'good'}
        />
      </div>

      {error && (
        <div className="mb-4">
          <Problem onRetry={load}>{error}</Problem>
        </div>
      )}
      {notice && (
        <div className="mb-4 flex items-center gap-2 rounded-card border border-scallion/20 bg-scallion-wash px-3 py-2.5 text-sm text-scallion">
          <Icon name="check" className="h-4 w-4 shrink-0" />
          {notice}
          <button
            onClick={() => setNotice(null)}
            className="ml-auto rounded p-1 hover:bg-scallion/10"
            aria-label="Dismiss"
          >
            <Icon name="close" className="h-3.5 w-3.5" />
          </button>
        </div>
      )}

      <div className="grid min-h-[560px] gap-4 2xl:grid-cols-[minmax(0,1fr)_360px]">
        <section className="card min-w-0 overflow-hidden">
          <div className="flex flex-col gap-3 border-b border-line p-4 lg:flex-row lg:items-center">
            <div className="relative min-w-0 flex-1 lg:max-w-md">
              <Icon
                name="search"
                className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-soy"
              />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search products, categories or SKUs"
                className="field bg-paper pl-9"
              />
            </div>
            <div
              className="scroll-thin flex items-center gap-1 overflow-x-auto rounded-lg bg-paper p-1"
              aria-label="Stock filters"
            >
              {filters.map((option) => (
                <button
                  key={option.value}
                  onClick={() => setFilter(option.value)}
                  aria-pressed={filter === option.value}
                  className={`whitespace-nowrap rounded-md px-2.5 py-1.5 text-xs font-semibold transition ${
                    filter === option.value
                      ? 'bg-card text-ink shadow-card'
                      : 'text-soy hover:text-ink'
                  }`}
                >
                  {option.label}
                  <span className="ml-1.5 font-mono text-2xs opacity-60 tnum">
                    {option.count}
                  </span>
                </button>
              ))}
            </div>
          </div>

          {loading ? (
            <Loading what="inventory" />
          ) : visible.length === 0 ? (
            <div className="p-5">
              <Empty title="No products found">
                Try another search or clear the current stock filter.
              </Empty>
            </div>
          ) : (
            <div>
              <div className="stock-grid-row hidden items-center gap-4 border-b border-line bg-paper/80 px-4 py-2.5 font-mono text-2xs uppercase tracking-[0.08em] text-soy lg:grid">
                <span>Product</span>
                <span>Status</span>
                <span className="text-right">On hand</span>
                <span className="text-right lg:block">Actions</span>
              </div>
              <div className="divide-y divide-line">
                {visible.map((item) => (
                  <StockRow
                    key={item.id}
                    item={item}
                    busy={busy}
                    selected={selected?.id === item.id}
                    editing={editingId === item.id}
                    onEdit={() =>
                      setEditingId((current) => (current === item.id ? null : item.id))
                    }
                    onOpen={() => void openLedger(item)}
                    onRun={run}
                  />
                ))}
              </div>
            </div>
          )}
        </section>

        <StockHistory item={selected} movements={movements} loading={historyLoading} />
      </div>
    </Page>
  );
}

function SummaryCard({
  label,
  value,
  detail,
  icon,
  tone = 'plain',
}: {
  label: string;
  value: number;
  detail: string;
  icon: string;
  tone?: 'plain' | 'good' | 'warn' | 'danger';
}) {
  const palette =
    tone === 'danger'
      ? 'bg-chilli-wash text-chilli'
      : tone === 'warn'
        ? 'bg-broth-wash text-broth-dark'
        : tone === 'good'
          ? 'bg-scallion-wash text-scallion'
          : 'bg-ink/[0.06] text-ink';
  return (
    <div className="card flex min-w-0 items-center gap-3 p-4 sm:p-5">
      <span
        className={`hidden h-10 w-10 shrink-0 items-center justify-center rounded-lg sm:flex ${palette}`}
      >
        <Icon name={icon} className="h-5 w-5" />
      </span>
      <span className="min-w-0">
        <span className="eyebrow block truncate">{label}</span>
        <span className="mt-1 flex items-baseline gap-2">
          <strong className="font-display text-2xl font-extrabold tracking-tightest tnum">
            {value}
          </strong>
          <span className="hidden truncate text-xs text-soy sm:block">{detail}</span>
        </span>
      </span>
    </div>
  );
}

function StockRow({
  item,
  busy,
  selected,
  editing,
  onEdit,
  onOpen,
  onRun,
}: {
  item: StockItem;
  busy: boolean;
  selected: boolean;
  editing: boolean;
  onEdit: () => void;
  onOpen: () => void;
  onRun: (label: string, action: () => Promise<unknown>) => Promise<void>;
}) {
  const [amount, setAmount] = useState('');
  const [action, setAction] = useState<StockAction>('received');
  const name = item.product_name ?? 'Unknown product';
  const status = stockState(item);
  const actionMeta = ACTIONS.find((entry) => entry.value === action)!;

  async function submit() {
    const value = Number(amount);
    if (!Number.isFinite(value)) return;
    if (action === 'count') {
      if (value < 0) return;
      await onRun(`Stocktake saved: ${name} now has ${value} singles.`, () =>
        api.countStock(item.id, value),
      );
    } else {
      if (value === 0) return;
      const delta = actionMeta.sign ? Math.abs(value) * actionMeta.sign : value;
      await onRun(`${reasonLabel(action)} saved: ${delta > 0 ? '+' : ''}${delta} ${name}.`, () =>
        api.recordStockMovement(item.id, delta, action),
      );
    }
    setAmount('');
    onEdit();
  }

  return (
    <article
      className={`${selected ? 'bg-paper/70' : 'bg-card hover:bg-paper/40'} transition-colors`}
    >
      <div className="stock-grid-row grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-2 px-4 py-3.5 lg:gap-4">
        <button onClick={onOpen} className="group min-w-0 text-left">
          <span className="block truncate font-semibold group-hover:text-chilli">{name}</span>
          <span className="mt-0.5 block truncate font-mono text-2xs text-soy">
            {item.sku || 'No SKU'}
            {item.category ? ` · ${item.category}` : ''}
          </span>
        </button>

        <span
          className={`hidden w-fit items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold lg:inline-flex ${status.className}`}
        >
          <span className={`h-1.5 w-1.5 rounded-full ${status.dot}`} />
          {status.label}
        </span>

        <div className="text-right">
          <strong
            className={`font-display text-lg tnum ${
              item.track_stock && item.stock_quantity <= 0 ? 'text-chilli' : ''
            }`}
          >
            {item.track_stock ? item.stock_quantity : '—'}
          </strong>
          <span className="ml-1 text-xs text-soy">singles</span>
        </div>

        <div className="col-span-2 flex items-center justify-between gap-2 lg:col-span-1 lg:justify-end">
          <span
            className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold lg:hidden ${status.className}`}
          >
            <span className={`h-1.5 w-1.5 rounded-full ${status.dot}`} />
            {status.label}
          </span>
          <button
            onClick={() =>
              void onRun(
                `${item.track_stock ? 'Stopped' : 'Started'} tracking ${name}.`,
                () => api.setStockTracking(item.id, !item.track_stock),
              )
            }
            disabled={busy}
            role="switch"
            aria-checked={item.track_stock}
            className="group inline-flex items-center gap-2 text-xs font-medium text-soy disabled:opacity-50"
            title={item.track_stock ? 'Stop limiting sales by stock' : 'Start limiting sales by stock'}
          >
            <span
              className={`relative h-5 w-9 rounded-full transition ${
                item.track_stock ? 'bg-scallion' : 'bg-ink/15'
              }`}
            >
              <span
                className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition ${
                  item.track_stock ? 'left-[18px]' : 'left-0.5'
                }`}
              />
            </span>
            <span className="hidden lg:inline">Track</span>
          </button>
          <button
            onClick={onOpen}
            className="btn-ghost hidden px-2 py-1.5 text-xs lg:inline-flex"
            title="View movement history"
          >
            <Icon name="history" className="h-4 w-4" />
          </button>
          <button
            onClick={onEdit}
            className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition ${
              editing
                ? 'bg-ink text-white'
                : 'border border-line bg-card text-ink hover:border-ink/30'
            }`}
          >
            {editing ? 'Close' : 'Update stock'}
          </button>
        </div>
      </div>

      {editing && (
        <div className="border-t border-line bg-paper/80 px-4 py-4">
          <div className="grid gap-3 sm:grid-cols-[minmax(190px,1fr)_140px_auto] sm:items-end">
            <label>
              <span className="label mb-1.5">What changed?</span>
              <select
                value={action}
                onChange={(event) => setAction(event.target.value as StockAction)}
                className="field bg-card"
              >
                {ACTIONS.map((entry) => (
                  <option key={entry.value} value={entry.value}>
                    {entry.label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span className="label mb-1.5">
                {action === 'count'
                  ? 'Exact count'
                  : action === 'adjusted'
                    ? 'Change (+/−)'
                    : 'Quantity'}
              </span>
              <input
                value={amount}
                onChange={(event) => setAmount(event.target.value)}
                inputMode="numeric"
                type="number"
                min={action === 'count' || actionMeta.sign ? 0 : undefined}
                placeholder={action === 'adjusted' ? '+2 or -2' : '0'}
                className="field bg-card font-mono tnum"
              />
            </label>
            <button
              onClick={() => void submit()}
              disabled={busy || amount === '' || (Number(amount) === 0 && action !== 'count')}
              className="btn-primary min-h-[38px] sm:px-5"
            >
              {busy ? 'Saving…' : action === 'count' ? 'Save count' : 'Record change'}
            </button>
          </div>
          <p className="mt-2 flex items-center gap-1.5 text-xs text-soy">
            <Icon name="info" className="h-3.5 w-3.5" />
            {actionMeta.hint}. All quantities are individual units, not packs.
          </p>
        </div>
      )}
    </article>
  );
}

function StockHistory({
  item,
  movements,
  loading,
}: {
  item: StockItem | null;
  movements: StockMovement[];
  loading: boolean;
}) {
  return (
    <aside className="card flex min-h-[420px] flex-col overflow-hidden 2xl:sticky 2xl:top-6 2xl:max-h-[calc(100vh-48px)]">
      <div className="border-b border-line px-4 py-4">
        <div className="flex items-start gap-3">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-ink/[0.06] text-ink">
            <Icon name="history" className="h-4 w-4" />
          </span>
          <div className="min-w-0">
            <h2 className="font-display font-bold">Movement history</h2>
            <p className="mt-0.5 truncate text-xs text-soy">
              {item
                ? `${item.product_name} · ${item.sku ?? 'No SKU'}`
                : 'Select a product to audit its stock'}
            </p>
          </div>
        </div>
        {item && (
          <div className="mt-4 flex items-end justify-between rounded-lg bg-paper px-3 py-2.5">
            <span>
              <span className="label">Current balance</span>
              <span className="mt-1 block text-xs text-soy">Individual units</span>
            </span>
            <strong className="font-display text-2xl font-extrabold tnum">
              {item.track_stock ? item.stock_quantity : '—'}
            </strong>
          </div>
        )}
      </div>

      <div className="scroll-thin flex-1 overflow-y-auto p-4">
        {!item ? (
          <div className="flex h-full min-h-64 flex-col items-center justify-center text-center">
            <span className="flex h-12 w-12 items-center justify-center rounded-full bg-paper text-soy">
              <Icon name="package" />
            </span>
            <p className="mt-3 text-sm font-semibold">Nothing selected</p>
            <p className="mt-1 max-w-[240px] text-xs leading-5 text-soy">
              Choose any product row to see every delivery, sale, return and stocktake.
            </p>
          </div>
        ) : loading ? (
          <Loading what="movement history" />
        ) : movements.length === 0 ? (
          <div className="py-12 text-center">
            <p className="text-sm font-semibold">No movements yet</p>
            <p className="mt-1 text-xs text-soy">The first stock update will appear here.</p>
          </div>
        ) : (
          <ol className="relative space-y-0 before:absolute before:bottom-3 before:left-[7px] before:top-3 before:w-px before:bg-line">
            {movements.map((movement) => (
              <li key={movement.id} className="relative flex gap-3 pb-5 last:pb-0">
                <span
                  className={`relative z-10 mt-1.5 h-[15px] w-[15px] shrink-0 rounded-full border-[3px] border-card ${
                    movement.delta > 0
                      ? 'bg-scallion'
                      : movement.delta < 0
                        ? 'bg-chilli'
                        : 'bg-broth'
                  }`}
                />
                <div className="min-w-0 flex-1">
                  <div className="flex items-baseline justify-between gap-3">
                    <span className="text-sm font-semibold">{reasonLabel(movement.reason)}</span>
                    <strong
                      className={`font-mono text-sm tnum ${
                        movement.delta > 0
                          ? 'text-scallion'
                          : movement.delta < 0
                            ? 'text-chilli'
                            : 'text-soy'
                      }`}
                    >
                      {movement.delta > 0 ? `+${movement.delta}` : movement.delta}
                    </strong>
                  </div>
                  <p className="mt-0.5 text-2xs text-soy">
                    {new Date(movement.created_at).toLocaleString([], {
                      dateStyle: 'medium',
                      timeStyle: 'short',
                    })}
                  </p>
                  <p className="mt-0.5 truncate text-2xs text-soy">
                    By {movement.created_by}
                    {movement.note ? ` · ${movement.note}` : ''}
                  </p>
                </div>
              </li>
            ))}
          </ol>
        )}
      </div>
    </aside>
  );
}

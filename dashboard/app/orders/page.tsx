'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { createClient } from '@/lib/supabase';
import { Nav } from '@/components/Nav';
import { OrderCard } from '@/components/OrderCard';
import { formatMoney } from '@/lib/format';
import type { Order, OrderStatus } from '@/lib/types';

const FILTERS: { label: string; value: 'open' | 'all' | OrderStatus }[] = [
  { label: 'Open', value: 'open' },
  { label: 'New', value: 'new' },
  { label: 'Preparing', value: 'preparing' },
  { label: 'Dispatched', value: 'dispatched' },
  { label: 'Delivered', value: 'delivered' },
  { label: 'All', value: 'all' },
];

const OPEN_STATUSES: OrderStatus[] = ['new', 'confirmed', 'preparing', 'dispatched'];

export default function OrdersPage() {
  const [orders, setOrders] = useState<Order[]>([]);
  const [filter, setFilter] = useState<'open' | 'all' | OrderStatus>('open');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [email, setEmail] = useState<string | null>(null);

  const upsert = useCallback((order: Order) => {
    setOrders((current) => {
      const index = current.findIndex((existing) => existing.id === order.id);
      if (index < 0) return [order, ...current];
      const next = [...current];
      next[index] = { ...next[index], ...order };
      return next;
    });
  }, []);

  useEffect(() => {
    const supabase = createClient();
    let alive = true;

    supabase.auth.getUser().then(({ data }) => alive && setEmail(data.user?.email ?? null));

    supabase
      .from('orders')
      .select('*, contacts(id,name,wa_id)')
      .order('created_at', { ascending: false })
      .limit(200)
      .then(({ data, error: loadError }) => {
        if (!alive) return;
        if (loadError) setError(loadError.message);
        else setOrders((data ?? []) as Order[]);
        setLoading(false);
      });

    const channel = supabase
      .channel('orders-board')
      .on('postgres_changes', { event: '*', schema: 'public', table: 'orders' }, (payload) => {
        if (payload.eventType === 'DELETE') return;
        upsert(payload.new as Order);
      })
      .subscribe();

    return () => {
      alive = false;
      void supabase.removeChannel(channel);
    };
  }, [upsert]);

  const visible = useMemo(() => {
    if (filter === 'all') return orders;
    if (filter === 'open') return orders.filter((order) => OPEN_STATUSES.includes(order.status));
    return orders.filter((order) => order.status === filter);
  }, [orders, filter]);

  const todayTotal = useMemo(() => {
    const start = new Date();
    start.setHours(0, 0, 0, 0);
    return orders
      .filter(
        (order) => order.status !== 'cancelled' && Date.parse(order.created_at) >= start.getTime(),
      )
      .reduce((sum, order) => sum + Number(order.total || 0), 0);
  }, [orders]);

  return (
    <div className="flex h-screen flex-col">
      <Nav email={email} />

      <div className="flex-1 overflow-y-auto p-4">
        <div className="mx-auto max-w-5xl">
          <div className="mb-4 flex flex-wrap items-center gap-3">
            <h1 className="text-lg font-semibold">Orders</h1>
            <span className="rounded-full bg-white px-3 py-1 text-sm ring-1 ring-wa-border">
              Today: {formatMoney(todayTotal)}
            </span>

            <div className="ml-auto flex flex-wrap gap-1">
              {FILTERS.map((option) => (
                <button
                  key={option.value}
                  onClick={() => setFilter(option.value)}
                  className={`rounded-full px-3 py-1.5 text-sm transition ${
                    filter === option.value
                      ? 'bg-wa-green text-white'
                      : 'bg-white ring-1 ring-wa-border hover:bg-wa-panel'
                  }`}
                >
                  {option.label}
                </button>
              ))}
            </div>
          </div>

          {loading && <p className="text-sm text-wa-muted">Loading orders…</p>}
          {error && <p className="rounded bg-red-50 p-3 text-sm text-red-700">{error}</p>}
          {!loading && visible.length === 0 && (
            <p className="rounded-xl bg-white p-6 text-center text-sm text-wa-muted ring-1 ring-wa-border">
              Nothing here. Orders appear as soon as the agent creates one.
            </p>
          )}

          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {visible.map((order) => (
              <OrderCard key={order.id} order={order} onUpdated={upsert} />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

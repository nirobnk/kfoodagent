'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { createClient } from '@/lib/supabase';
import { Page, PageHeader } from '@/components/AppShell';
import { Empty, Loading, Problem, Segmented } from '@/components/ui/Bits';
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

  const todayOrders = useMemo(() => {
    const start = new Date();
    start.setHours(0, 0, 0, 0);
    return orders.filter(
      (order) => order.status !== 'cancelled' && Date.parse(order.created_at) >= start.getTime(),
    );
  }, [orders]);

  const todayTotal = todayOrders.reduce((sum, order) => sum + Number(order.total || 0), 0);
  const todayCount = todayOrders.length;

  return (
    <Page>
      <PageHeader
        title="Orders"
        lede={`${formatMoney(todayTotal)} taken today across ${todayCount} order${
          todayCount === 1 ? '' : 's'
        }.`}
      >
        <Segmented value={filter} onChange={setFilter} options={FILTERS} />
      </PageHeader>

      {loading && <Loading what="orders" />}
      {error && <Problem>{error}</Problem>}
      {!loading && visible.length === 0 && (
        <Empty title="Nothing here">
          Orders appear the moment the agent creates one, or the counter sends a bill.
        </Empty>
      )}

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {visible.map((order) => (
          <OrderCard key={order.id} order={order} onUpdated={upsert} />
        ))}
      </div>
    </Page>
  );
}

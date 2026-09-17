'use client';

import { useState } from 'react';
import { api } from '@/lib/api';
import { formatMoney, formatRelative, orderSummary } from '@/lib/format';
import type { Order, OrderStatus } from '@/lib/types';

const FLOW: OrderStatus[] = ['new', 'confirmed', 'preparing', 'dispatched', 'delivered'];

const STATUS_STYLE: Record<OrderStatus, string> = {
  new: 'bg-blue-100 text-blue-800',
  confirmed: 'bg-indigo-100 text-indigo-800',
  preparing: 'bg-amber-100 text-amber-800',
  dispatched: 'bg-purple-100 text-purple-800',
  delivered: 'bg-emerald-100 text-emerald-800',
  cancelled: 'bg-gray-200 text-gray-700',
};

// Which status changes send the customer a WhatsApp message.
const NOTIFIES: OrderStatus[] = ['confirmed', 'preparing', 'dispatched', 'delivered', 'cancelled'];

export function OrderCard({ order, onUpdated }: { order: Order; onUpdated: (order: Order) => void }) {
  const [busy, setBusy] = useState<OrderStatus | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const next = FLOW[FLOW.indexOf(order.status) + 1];

  async function change(status: OrderStatus) {
    setBusy(status);
    setError(null);
    setNote(null);
    try {
      const result = await api.setOrderStatus(order.id, status, NOTIFIES.includes(status));
      onUpdated(result.order);
      setNote(
        result.notified
          ? 'Customer notified on WhatsApp.'
          : result.notify_reason === 'window_closed'
            ? 'Status saved. The customer was not notified: the 24-hour window is closed and no approved template was available.'
            : 'Status saved.',
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not update the order');
    } finally {
      setBusy(null);
    }
  }

  return (
    <article className="rounded-xl bg-white p-4 shadow-sm ring-1 ring-wa-border">
      <header className="flex items-start gap-2">
        <div className="min-w-0">
          <h3 className="font-semibold">Order #{order.order_number}</h3>
          <p className="truncate text-sm text-wa-muted">
            {order.contacts?.name || `+${order.contacts?.wa_id ?? ''}`} · {formatRelative(order.created_at)} ago
          </p>
        </div>
        <span
          className={`ml-auto shrink-0 rounded-full px-2.5 py-1 text-xs font-medium ${STATUS_STYLE[order.status]}`}
        >
          {order.status}
        </span>
      </header>

      <p className="mt-3 text-sm">{orderSummary(order)}</p>
      {order.notes && <p className="mt-1 text-xs text-wa-muted">Address / note: {order.notes}</p>}

      <div className="mt-2 text-sm">
        {Number(order.delivery_fee) > 0 ? (
          <p className="text-xs text-wa-muted">
            Items {formatMoney(order.subtotal)} + delivery {formatMoney(order.delivery_fee)}
          </p>
        ) : (
          <p className="text-xs text-wa-muted">
            Items {formatMoney(order.subtotal)} · delivery free
          </p>
        )}
        <p className="font-semibold">{formatMoney(order.total)}</p>
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        {next && (
          <button
            onClick={() => change(next)}
            disabled={busy !== null}
            className="rounded-lg bg-wa-green px-3 py-1.5 text-sm font-medium text-white transition hover:bg-[#0f7a6e] disabled:opacity-50"
          >
            {busy === next ? 'Saving…' : `Mark ${next}`}
          </button>
        )}
        {order.status !== 'cancelled' && order.status !== 'delivered' && (
          <button
            onClick={() => change('cancelled')}
            disabled={busy !== null}
            className="rounded-lg border border-wa-border px-3 py-1.5 text-sm transition hover:bg-wa-panel disabled:opacity-50"
          >
            Cancel
          </button>
        )}
      </div>

      {note && <p className="mt-2 text-xs text-wa-muted">{note}</p>}
      {error && <p className="mt-2 text-xs text-red-600">{error}</p>}
    </article>
  );
}

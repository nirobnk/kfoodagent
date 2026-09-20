'use client';

import Link from 'next/link';
import { useState } from 'react';
import { api } from '@/lib/api';
import { Chip } from './ui/Bits';
import { Icon } from './ui/Icon';
import { formatMoney, formatRelative, orderSummary } from '@/lib/format';
import type { Order, OrderStatus, PaymentStatus } from '@/lib/types';

const FLOW: OrderStatus[] = ['new', 'confirmed', 'preparing', 'dispatched', 'delivered'];

const STATUS_STYLE: Record<OrderStatus, string> = {
  new: 'bg-ink/[0.08] text-ink',
  confirmed: 'bg-scallion-wash text-scallion',
  preparing: 'bg-broth-wash text-broth-dark',
  dispatched: 'bg-buldak-wash text-buldak-dark',
  delivered: 'bg-scallion-wash text-scallion',
  cancelled: 'bg-soy/[0.12] text-soy',
};

// Which status changes send the customer a WhatsApp message.
const NOTIFIES: OrderStatus[] = ['confirmed', 'preparing', 'dispatched', 'delivered', 'cancelled'];

// Money is a second axis, not another order status. 'receipt_received' is the
// one that needs a human: the agent takes the slip a customer sends but
// cannot open it, so nothing is paid until someone has seen the account.
const PAYMENT_LABEL: Record<PaymentStatus, string> = {
  unpaid: 'unpaid',
  receipt_received: 'slip to check',
  verified: 'paid',
  refunded: 'refunded',
};

const PAYMENT_STYLE: Record<PaymentStatus, string> = {
  unpaid: 'bg-soy/[0.12] text-soy',
  receipt_received: 'bg-buldak-wash text-buldak-dark',
  verified: 'bg-scallion-wash text-scallion',
  refunded: 'bg-ink/[0.08] text-ink',
};

export function OrderCard({ order, onUpdated }: { order: Order; onUpdated: (order: Order) => void }) {
  const [busy, setBusy] = useState<OrderStatus | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const next = FLOW[FLOW.indexOf(order.status) + 1];
  const payment: PaymentStatus = order.payment_status ?? 'unpaid';

  async function changePayment(paymentStatus: PaymentStatus) {
    setBusy('new');
    setError(null);
    setNote(null);
    try {
      const result = await api.setOrderPayment(order.id, paymentStatus);
      onUpdated(result.order);
      setNote(paymentStatus === 'verified' ? 'Marked paid.' : 'Payment status saved.');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not update the payment.');
    } finally {
      setBusy(null);
    }
  }

  async function change(status: OrderStatus) {
    setBusy(status);
    setError(null);
    setNote(null);
    try {
      const result = await api.setOrderStatus(order.id, status, NOTIFIES.includes(status));
      onUpdated(result.order);
      setNote(
        result.notified
          ? 'Customer told on WhatsApp.'
          : result.notify_reason === 'window_closed'
            ? 'Saved. The customer was not told: the 24-hour window is closed and no approved template fitted.'
            : 'Saved.',
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not update the order.');
    } finally {
      setBusy(null);
    }
  }

  return (
    <article className="card flex flex-col p-4">
      <header className="flex items-start gap-2">
        <div className="min-w-0">
          <h3 className="font-display text-base font-bold tracking-tightest">
            Order #{order.order_number}
          </h3>
          {order.contacts ? (
            <Link
              href={`/customers?id=${order.contacts.id}`}
              className="block truncate text-sm text-soy underline decoration-line underline-offset-2 hover:text-ink"
            >
              {order.contacts.name || `+${order.contacts.wa_id}`}
            </Link>
          ) : (
            <p className="truncate text-sm text-soy">Customer not linked</p>
          )}
        </div>
        <span className="ml-auto shrink-0 text-right">
          <Chip className={STATUS_STYLE[order.status]}>{order.status}</Chip>
          <Chip className={`ml-1 ${PAYMENT_STYLE[payment]}`}>{PAYMENT_LABEL[payment]}</Chip>
          <span className="mt-1 block font-mono text-2xs text-soy">
            {formatRelative(order.created_at)} ago
          </span>
        </span>
      </header>

      <p className="mt-3 text-sm">{orderSummary(order)}</p>
      {order.payment_note && (
        <p className="mt-1 whitespace-pre-wrap text-xs text-buldak-dark">{order.payment_note}</p>
      )}
      {order.notes && (
        <p className="mt-1 whitespace-pre-wrap text-xs text-soy">{order.notes}</p>
      )}

      <div className="mt-3 border-t border-line pt-2">
        <p className="font-mono text-2xs text-soy">
          Items {formatMoney(order.subtotal)}
          {Number(order.delivery_fee) > 0
            ? ` + delivery ${formatMoney(order.delivery_fee)}`
            : ' · delivery free'}
        </p>
        <p className="font-display text-lg font-extrabold tracking-tightest tnum">
          {formatMoney(order.total)}
        </p>
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        {next && (
          <button onClick={() => change(next)} disabled={busy !== null} className="btn-hot">
            {busy === next ? 'Saving…' : `Mark ${next}`}
          </button>
        )}
        {payment !== 'verified' && payment !== 'refunded' && (
          <button
            onClick={() => changePayment('verified')}
            disabled={busy !== null}
            className="btn-quiet"
          >
            Mark paid
          </button>
        )}
        {order.status !== 'cancelled' && order.status !== 'delivered' && (
          <button
            onClick={() => change('cancelled')}
            disabled={busy !== null}
            className="btn-quiet"
          >
            Cancel
          </button>
        )}
      </div>

      {note && (
        <p className="mt-2 flex items-start gap-1.5 text-xs text-soy">
          <Icon name="check" className="mt-0.5 h-3.5 w-3.5 shrink-0 text-scallion" />
          {note}
        </p>
      )}
      {error && <p className="mt-2 text-xs text-chilli">{error}</p>}
    </article>
  );
}

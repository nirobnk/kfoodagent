import type { CustomerStats, Invoice, Lifecycle, Order, Task } from './types';

/**
 * How each stage looks and what it means, in one place.
 *
 * `hint` is the sentence shown next to the stage on the customer record. It is
 * written for whoever is reading the screen at 7pm deciding who to message, not
 * as a definition of the term.
 */
export const LIFECYCLE: Record<
  Lifecycle,
  { label: string; hint: string; chip: string; band: string }
> = {
  lead: {
    label: 'Lead',
    hint: 'Has messaged us but never ordered.',
    chip: 'bg-ink/[0.08] text-ink',
    band: 'bg-ink',
  },
  active: {
    label: 'Active',
    hint: 'Ordering, but not often enough to call a regular yet.',
    chip: 'bg-scallion-wash text-scallion',
    band: 'bg-scallion',
  },
  regular: {
    label: 'Regular',
    hint: 'Comes back on their own. Keep the shelf stocked.',
    chip: 'bg-scallion-wash text-scallion',
    band: 'bg-scallion',
  },
  vip: {
    label: 'VIP',
    hint: 'Orders often and spends the most. Worth knowing by name.',
    chip: 'bg-buldak-wash text-buldak-dark',
    band: 'bg-buldak',
  },
  at_risk: {
    label: 'At risk',
    hint: 'Quiet for longer than they usually go. Message them today.',
    chip: 'bg-broth-wash text-broth-dark',
    band: 'bg-broth',
  },
  lost: {
    label: 'Lost',
    hint: 'Months of silence. Only a real offer will bring them back.',
    chip: 'bg-soy/[0.12] text-soy',
    band: 'bg-soy',
  },
  blocked: {
    label: 'Blocked',
    hint: 'The agent stays quiet and nobody should message this number.',
    chip: 'bg-chilli-wash text-chilli',
    band: 'bg-chilli',
  },
};

export const LIFECYCLE_ORDER: Lifecycle[] = [
  'vip',
  'regular',
  'active',
  'at_risk',
  'lost',
  'lead',
  'blocked',
];

export const SOURCES: Record<string, string> = {
  whatsapp: 'WhatsApp',
  pos: 'Shop counter',
  web: 'Website',
  referral: 'Referral',
  walk_in: 'Walk-in',
  other: 'Other',
};

export const TASK_PRIORITY = {
  high: { label: 'High', chip: 'bg-chilli-wash text-chilli' },
  normal: { label: 'Normal', chip: 'bg-ink/[0.08] text-ink' },
  low: { label: 'Low', chip: 'bg-soy/[0.12] text-soy' },
} as const;

export function lifecycleOf(value: string | null | undefined) {
  return LIFECYCLE[(value as Lifecycle) ?? 'lead'] ?? LIFECYCLE.lead;
}

/** The three bars, in the order they are printed on the pack: R, F, M. */
export function heatScores(stats: CustomerStats) {
  return [
    { key: 'R', score: stats.recency_score, label: 'Recency — how lately they ordered' },
    { key: 'F', score: stats.frequency_score, label: 'Frequency — how many orders' },
    { key: 'M', score: stats.monetary_score, label: 'Money — what they have spent' },
  ];
}

/** Why a customer is on the "needs attention" list, in one short phrase. */
export function attentionReason(
  stats: CustomerStats,
  contactLifecycle: Lifecycle,
  unread: number,
): string | null {
  if (unread > 0) return `${unread} unread message${unread === 1 ? '' : 's'}`;
  if (contactLifecycle === 'at_risk' || stats.suggested_lifecycle === 'at_risk') {
    const days = stats.days_since_last_order;
    return days === null ? 'Gone quiet' : `Quiet for ${days} days`;
  }
  if (stats.suggested_lifecycle === 'lead' && stats.orders === 0) return 'Never ordered';
  return null;
}

/** The stage the orders suggest, when it disagrees with the one on the record. */
export function stageDisagreement(
  stats: CustomerStats,
  current: Lifecycle,
): Lifecycle | null {
  if (current === 'blocked') return null; // a human decision the orders cannot overrule
  return stats.suggested_lifecycle === current ? null : stats.suggested_lifecycle;
}

export function isOverdue(task: Task, now = Date.now()): boolean {
  return !task.done_at && !!task.due_at && Date.parse(task.due_at) < now;
}

export function dueLabel(task: Task, now = Date.now()): string {
  if (!task.due_at) return 'No date';
  const due = Date.parse(task.due_at);
  const days = Math.round((due - now) / 86400000);
  if (days < -1) return `${Math.abs(days)} days late`;
  if (days === -1 || (days === 0 && due < now)) return 'Overdue';
  if (days === 0) return 'Today';
  if (days === 1) return 'Tomorrow';
  if (days < 7) return `In ${days} days`;
  return new Date(due).toLocaleDateString([], { day: 'numeric', month: 'short' });
}

/** What the paper and the server disagree by, in rupees. */
export function invoiceGap(invoice: Invoice): number {
  return Number(invoice.paper_total || 0) - Number(invoice.server_total || 0);
}

export function orderTotal(order: Order): number {
  return Number(order.total || 0);
}

/** Change against the period before, as a percentage. Null when there is no base. */
export function change(current: number, previous: number): number | null {
  if (!previous) return null;
  return ((current - previous) / previous) * 100;
}

export function toLocalInput(iso: string | null): string {
  if (!iso) return '';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  const offset = date.getTimezoneOffset() * 60000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}

export function fromLocalInput(value: string): string | null {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date.toISOString();
}

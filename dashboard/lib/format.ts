import type { Contact, Message, Order, Product, ProductGroup } from './types';

export const WINDOW_MS = 24 * 60 * 60 * 1000;

export function windowExpiresAt(contact: Pick<Contact, 'last_customer_message_at'>): number | null {
  if (!contact.last_customer_message_at) return null;
  const last = Date.parse(contact.last_customer_message_at);
  return Number.isNaN(last) ? null : last + WINDOW_MS;
}

export function windowRemainingMs(
  contact: Pick<Contact, 'last_customer_message_at'>,
  now = Date.now(),
): number {
  const expires = windowExpiresAt(contact);
  if (expires === null) return 0;
  return Math.max(0, expires - now);
}

export function canSendFreeText(
  contact: Pick<Contact, 'last_customer_message_at'>,
  now = Date.now(),
): boolean {
  return windowRemainingMs(contact, now) > 0;
}

export function formatRemaining(ms: number): string {
  if (ms <= 0) return 'closed';
  const minutes = Math.floor(ms / 60000);
  const hours = Math.floor(minutes / 60);
  return hours > 0 ? `${hours}h ${minutes % 60}m` : `${minutes}m`;
}

export function formatTime(iso: string): string {
  const date = new Date(iso);
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

export function formatDayLabel(iso: string): string {
  const date = new Date(iso);
  const today = new Date();
  const yesterday = new Date(today.getTime() - 86400000);
  const sameDay = (a: Date, b: Date) => a.toDateString() === b.toDateString();

  if (sameDay(date, today)) return 'Today';
  if (sameDay(date, yesterday)) return 'Yesterday';
  return date.toLocaleDateString([], { day: 'numeric', month: 'short', year: 'numeric' });
}

export function formatRelative(iso: string | null): string {
  if (!iso) return '';
  const diff = Date.now() - Date.parse(iso);
  if (Number.isNaN(diff)) return '';
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return 'now';
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h`;
  const days = Math.floor(hours / 24);
  return days < 7 ? `${days}d` : new Date(iso).toLocaleDateString([], { day: 'numeric', month: 'short' });
}

export function formatMoney(value: number | string): string {
  const amount = typeof value === 'string' ? Number.parseFloat(value) : value;
  if (Number.isNaN(amount)) return 'Rs. 0';
  return `Rs. ${amount.toLocaleString('en-LK', { maximumFractionDigits: 0 })}`;
}

export function contactLabel(contact: Pick<Contact, 'name' | 'wa_id'>): string {
  return contact.name?.trim() || `+${contact.wa_id}`;
}

export function messagePreview(message: Message | undefined): string {
  if (!message) return 'No messages yet';
  if (message.body) return message.body;
  return `[${message.message_type}]`;
}

export function orderSummary(order: Order): string {
  if (!order.items?.length) return 'No items';
  return order.items.map((item) => `${item.quantity}x ${item.name}`).join(', ');
}

export function groupProducts(variants: Product[]): ProductGroup[] {
  const groups = new Map<string, ProductGroup>();
  for (const variant of variants) {
    let group = groups.get(variant.handle);
    if (!group) {
      group = {
        handle: variant.handle,
        product_name: variant.product_name,
        brand: variant.brand,
        korean_name: variant.korean_name,
        category: variant.category,
        pack_size: variant.pack_size,
        heat_level: variant.heat_level,
        badge: variant.badge,
        short_description: variant.short_description,
        allergens: variant.allergens,
        image_url: variant.image_url,
        image_file: variant.image_file,
        product_url: variant.product_url,
        variants: [],
      };
      groups.set(variant.handle, group);
    }
    group.variants.push(variant);
  }
  for (const group of groups.values()) {
    group.variants.sort((a, b) => Number(a.price) - Number(b.price));
  }
  return [...groups.values()];
}

export function heatLabel(level: number | null): string {
  if (level === null || level === undefined) return '';
  return '🌶️'.repeat(Math.max(0, Math.min(5, level))) || 'mild';
}

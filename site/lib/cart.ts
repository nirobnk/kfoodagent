/* The cart: localStorage only, no backend. Checkout = a WhatsApp order
   message to the shop. No order minimum — any cart with at least one item
   can check out.

   Two things here are contracts with people, not implementation details:
     - STORAGE_KEY: customers' existing carts live under it.
     - orderMessage(): staff and the WhatsApp agent read this text every day,
       and the agent recognises it by its first line. Change it character by
       character or not at all. */

import { DELIVERY_FEE, FREE_DELIVERY_OVER, type CartItem } from "./catalog";
import { fmt } from "./format";

export const STORAGE_KEY = "kfood_cart_v1";
const CHANGE_EVENT = "kfood:cart";

export interface Line {
  sku: string;
  qty: number;
}

export interface DetailedLine extends Line {
  item: CartItem;
  lineTotal: number;
}

/* amount = goods subtotal, delivery = courier, total = what the customer pays */
export interface Totals {
  amount: number;
  itemCount: number;
  delivery: number;
  total: number;
}

export interface DeliveryDetails {
  name: string;
  phone: string;
  address: string;
  city: string;
  district: string;
  postal: string;
  notes: string;
  pay: string;
}

/* ---------- storage ---------- */

/* Lines for products that no longer exist are dropped on read, exactly as the
   old cart.js did, so a renamed SKU cannot sit in a cart forever. */
export function parseLines(raw: string | null, isKnown: (sku: string) => boolean): Line[] {
  try {
    const arr: unknown = raw ? JSON.parse(raw) : [];
    if (!Array.isArray(arr)) return [];
    return arr.filter(
      (l): l is Line => !!l && typeof l.sku === "string" && isKnown(l.sku) && l.qty > 0
    );
  } catch {
    return [];
  }
}

export function readRaw(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

export function writeLines(lines: Line[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(lines));
  } catch {
    /* private mode or a full quota: the cart just does not persist */
  }
  window.dispatchEvent(new Event(CHANGE_EVENT));
}

/* For useSyncExternalStore: this tab's changes, and other tabs' too. */
export function subscribe(onChange: () => void) {
  window.addEventListener(CHANGE_EVENT, onChange);
  window.addEventListener("storage", onChange);
  return () => {
    window.removeEventListener(CHANGE_EVENT, onChange);
    window.removeEventListener("storage", onChange);
  };
}

/* Lines are kept as stored when adding from a product or shop page; the cart
   page, which knows the whole catalogue, is what prunes unknown SKUs. */
function storedLines(): Line[] {
  return parseLines(readRaw(), () => true);
}

export function addToCart(sku: string, qty = 1) {
  const lines = storedLines();
  const hit = lines.find((l) => l.sku === sku);
  if (hit) hit.qty += qty;
  else lines.push({ sku, qty });
  writeLines(lines);
}

/* ---------- arithmetic ---------- */

export function detailed(lines: Line[], index: Record<string, CartItem>): DetailedLine[] {
  return lines.map((l) => {
    const item = index[l.sku];
    return { ...l, item, lineTotal: item.price * l.qty };
  });
}

export function totals(det: DetailedLine[]): Totals {
  let amount = 0;
  let itemCount = 0;
  for (const d of det) {
    amount += d.lineTotal;
    itemCount += d.qty;
  }
  const delivery = itemCount === 0 || amount >= FREE_DELIVERY_OVER ? 0 : DELIVERY_FEE;
  return { amount, itemCount, delivery, total: amount + delivery };
}

/* ---------- the WhatsApp order ---------- */

export function orderMessage(det: DetailedLine[], t: Totals, f: DeliveryDetails): string {
  let msg = "🍜 NEW ORDER — kfoods.lk\n\n";
  det.forEach((d, i) => {
    msg += (i + 1) + ". " + d.item.name + " — " + d.item.label +
           " × " + d.qty + " = " + fmt(d.lineTotal) + "\n";
  });
  msg += "\nItems: " + t.itemCount + "\n";
  msg += "Subtotal: " + fmt(t.amount) + "\n";
  msg += t.delivery === 0
    ? "Delivery: FREE (order over " + fmt(FREE_DELIVERY_OVER) + ")\n"
    : "Delivery: " + fmt(t.delivery) + "\n";
  msg += "TOTAL: " + fmt(t.total) + "\n";
  msg += "\n— Delivery details —\n";
  msg += "Name: " + f.name + "\n";
  msg += "Phone: " + f.phone + "\n";
  msg += "Address: " + f.address + ", " + f.city + "\n";
  msg += "District: " + f.district + "\n";
  if (f.postal) msg += "Postal code: " + f.postal + "\n";
  msg += "Payment: " + f.pay + "\n";
  if (f.notes) msg += "Notes: " + f.notes + "\n";
  msg += "\n(Sent from kfoods.lk online store)";
  return msg;
}

export const whatsappUrl = (number: string, msg: string) =>
  "https://wa.me/" + number + "?text=" + encodeURIComponent(msg);

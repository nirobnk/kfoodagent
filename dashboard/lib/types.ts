export type Direction = 'in' | 'out';
export type Sender = 'customer' | 'agent' | 'human' | 'system';
export type MessageStatus = 'queued' | 'sent' | 'delivered' | 'read' | 'failed';
export type OrderStatus =
  | 'new'
  | 'confirmed'
  | 'preparing'
  | 'dispatched'
  | 'delivered'
  | 'cancelled';

export interface Contact {
  id: string;
  business_id: string;
  wa_id: string;
  name: string | null;
  language: string | null;
  tags: string[] | null;
  human_takeover: boolean;
  takeover_started_at: string | null;
  takeover_by: string | null;
  last_customer_message_at: string | null;
  unread_count: number;
  first_seen: string;
  last_seen: string;
}

export interface Message {
  id: string;
  business_id: string;
  contact_id: string;
  direction: Direction;
  sender: Sender;
  body: string | null;
  media_url: string | null;
  message_type: string;
  template_name: string | null;
  wa_message_id: string | null;
  status: MessageStatus;
  error: string | null;
  created_at: string;
}

export interface OrderItem {
  name: string;
  quantity: number;
  sku?: string;
  product?: string;
  variant?: string;
  unit_price?: number;
  subtotal?: number;
}

export interface Order {
  id: string;
  business_id: string;
  contact_id: string;
  order_number: number;
  items: OrderItem[];
  subtotal: number;
  delivery_fee: number;
  total: number;
  status: OrderStatus;
  notes: string | null;
  created_at: string;
  updated_at: string;
  contacts?: Pick<Contact, 'id' | 'name' | 'wa_id'> | null;
}

export interface Template {
  id: string;
  key: string;
  name: string;
  language: string;
  variables: string[];
  body_preview: string | null;
  approved: boolean;
}

export interface Usage {
  month_start: string;
  outbound_messages: number;
  inbound_messages: number;
  free_service_messages_remaining: number;
}

export interface Product {
  id: string;
  sku: string;
  handle: string;
  name: string;
  product_name: string;
  variant_label: string;
  units: number;
  price: number;
  unit_price: number;
  brand: string | null;
  korean_name: string | null;
  category: string | null;
  pack_size: string | null;
  heat_level: number | null;
  cook_time: string | null;
  badge: string | null;
  short_description: string | null;
  allergens: string | null;
  image_url: string | null;
  image_file: string | null;
  product_url: string | null;
  available: boolean;
  sort_order: number;
}

/** One product with its three pack sizes, the way staff think about it. */
export interface ProductGroup {
  handle: string;
  product_name: string;
  brand: string | null;
  korean_name: string | null;
  category: string | null;
  pack_size: string | null;
  heat_level: number | null;
  badge: string | null;
  short_description: string | null;
  allergens: string | null;
  image_url: string | null;
  image_file: string | null;
  product_url: string | null;
  variants: Product[];
}

export type StockReason =
  | 'received'
  | 'sold'
  | 'returned'
  | 'damaged'
  | 'expired'
  | 'adjusted'
  | 'count';

/** One SKU's current position. track_stock off means unlimited, as before. */
export interface StockItem {
  id: string;
  sku: string | null;
  handle: string | null;
  /** Always 1: stock is held on the product's single-unit row. */
  units: number;
  product_name: string | null;
  variant_label: string | null;
  category: string | null;
  track_stock: boolean;
  /** Counted in single units. A 5 Pack sale removes five of these. */
  stock_quantity: number;
  available: boolean;
}

/** One line of the ledger — why the number is what it is. */
export interface StockMovement {
  id: string;
  menu_item_id: string;
  delta: number;
  reason: StockReason;
  order_id: string | null;
  note: string | null;
  created_by: string;
  created_at: string;
}

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

// ---------------------------------------------------------------------------
// CRM
// ---------------------------------------------------------------------------
export type Lifecycle =
  | 'lead'
  | 'active'
  | 'regular'
  | 'vip'
  | 'at_risk'
  | 'lost'
  | 'blocked';

export type ContactSource = 'whatsapp' | 'pos' | 'web' | 'referral' | 'walk_in' | 'other';

/** The fields 0008_crm.sql added to contacts — the record staff actually edit. */
export interface CrmContact extends Contact {
  lifecycle: Lifecycle;
  owner: string | null;
  email: string | null;
  address: string | null;
  city: string | null;
  birthday: string | null;
  marketing_opt_in: boolean;
  source: ContactSource;
}

export interface FavouriteItem {
  name: string;
  sku: string | null;
  quantity: number;
  orders: number;
}

/** Computed from the orders on every read — never stored. See backend/crm.py. */
export interface CustomerStats {
  orders: number;
  cancelled_orders: number;
  lifetime_value: number;
  average_order: number;
  largest_order: number;
  items_bought: number;
  first_order_at: string | null;
  last_order_at: string | null;
  days_since_last_order: number | null;
  days_as_customer: number | null;
  average_gap_days: number | null;
  recency_score: number;
  frequency_score: number;
  monetary_score: number;
  suggested_lifecycle: Lifecycle;
  favourites: FavouriteItem[];
}

export interface CustomerSummary {
  contact: CrmContact;
  stats: CustomerStats;
  open_tasks: number;
  next_due_at: string | null;
}

export interface Note {
  id: string;
  business_id: string;
  contact_id: string;
  note: string;
  created_by: string;
  pinned: boolean;
  created_at: string;
}

export type TaskPriority = 'low' | 'normal' | 'high';

export interface Task {
  id: string;
  business_id: string;
  contact_id: string | null;
  order_id: string | null;
  title: string;
  detail: string | null;
  due_at: string | null;
  priority: TaskPriority;
  done_at: string | null;
  done_by: string | null;
  assigned_to: string | null;
  created_by: string;
  created_at: string;
  updated_at: string;
}

/** A printed POS bill, and what the server thought it should have said. */
export interface Invoice {
  id: string;
  order_id: string;
  device_id: string;
  bill_no: string;
  printed_at: string;
  received_at: string;
  paper_total: number;
  paper_subtotal: number;
  paper_discount: number;
  paper_delivery: number;
  server_total: number;
  server_subtotal: number;
  server_discount: number;
  server_delivery: number;
  mismatch: boolean;
  mismatch_detail: { sku?: string; printed?: number; server?: number; reason?: string }[];
  reviewed_at: string | null;
  reviewed_by: string | null;
  payment_method: string | null;
  lines: OrderItem[];
  created_by: string;
}

export interface CustomerDetail {
  contact: CrmContact;
  stats: CustomerStats;
  orders: Order[];
  notes: Note[];
  tasks: Task[];
  invoices: Invoice[];
  messages: Message[];
  window_open: boolean;
  window_remaining_human: string;
}

export interface Analytics {
  days: number;
  totals: {
    days: number;
    current: AnalyticsPeriod;
    previous: AnalyticsPeriod;
  };
  revenue_by_day: { day: string; revenue: number; orders: number }[];
  top_products: { name: string; revenue: number; quantity: number }[];
  status_mix: { key: string; orders: number; revenue: number }[];
  source_mix: { key: string; orders: number; revenue: number }[];
  acquisition: {
    days: number;
    new_customers: number;
    returning_customers: number;
    new_revenue: number;
    returning_revenue: number;
  };
  segments: Partial<Record<Lifecycle, number>>;
  messages: { month_start: string; outbound: number; inbound: number };
}

export interface AnalyticsPeriod {
  orders: number;
  revenue: number;
  average_order: number;
  customers: number;
  cancelled: number;
}

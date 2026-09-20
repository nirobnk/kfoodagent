'use client';

import { createClient } from './supabase';
import type {
  Analytics,
  ContactSource,
  CrmContact,
  CustomerDetail,
  CustomerSummary,
  Invoice,
  Lifecycle,
  Note,
  Order,
  OrderStatus,
  PaymentStatus,
  StockItem,
  StockMovement,
  StockReason,
  Task,
  TaskPriority,
  Template,
  Usage,
} from './types';

const BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

/**
 * Every write goes to the backend, never straight to the database: the backend
 * owns the WhatsApp token, the 24-hour window check and the message log.
 */
async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const supabase = createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();

  if (!session) {
    throw new ApiError('Your session expired. Please sign in again.', 401);
  }

  const response = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${session.access_token}`,
      ...(init.headers ?? {}),
    },
    cache: 'no-store',
  });

  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      if (typeof body.detail === 'string') detail = body.detail;
    } catch {
      /* keep the default message */
    }
    throw new ApiError(detail, response.status);
  }

  return (await response.json()) as T;
}

export interface SendResult {
  ok: boolean;
  wa_message_id: string | null;
  template_name: string | null;
  reason: string | null;
}

export const api = {
  sendMessage(contactId: string, body: string, takeOver = true) {
    return request<SendResult>('/messages/send', {
      method: 'POST',
      body: JSON.stringify({ contact_id: contactId, body, take_over: takeOver }),
    });
  },

  sendTemplate(contactId: string, templateKey: string, variables: string[]) {
    return request<SendResult>('/messages/send-template', {
      method: 'POST',
      body: JSON.stringify({ contact_id: contactId, template_key: templateKey, variables }),
    });
  },

  setTakeover(contactId: string, enabled: boolean) {
    return request<{ contact: Record<string, unknown> }>(`/contacts/${contactId}/takeover`, {
      method: 'POST',
      body: JSON.stringify({ enabled }),
    });
  },

  markRead(contactId: string) {
    return request<{ contact: Record<string, unknown> }>(`/contacts/${contactId}/read`, {
      method: 'POST',
    });
  },

  listTemplates() {
    return request<{ templates: Template[] }>('/templates');
  },

  listOrders(status?: string) {
    const query = status ? `?status=${encodeURIComponent(status)}` : '';
    return request<{ orders: Order[] }>(`/orders${query}`);
  },

  setOrderStatus(orderId: string, status: OrderStatus, notify = true) {
    return request<{ order: Order; notified: boolean; notify_reason: string | null }>(
      `/orders/${orderId}/status`,
      { method: 'PATCH', body: JSON.stringify({ status, notify }) },
    );
  },

  setOrderPayment(orderId: string, paymentStatus: PaymentStatus, note?: string) {
    return request<{ order: Order }>(`/orders/${orderId}/payment`, {
      method: 'PATCH',
      body: JSON.stringify({ payment_status: paymentStatus, note }),
    });
  },

  usage() {
    return request<Usage>('/stats/usage');
  },

  listStock(trackedOnly = false) {
    const query = trackedOnly ? '?tracked_only=true' : '';
    return request<{ items: StockItem[] }>(`/inventory${query}`);
  },

  listStockMovements(menuItemId?: string, limit = 50) {
    const params = new URLSearchParams({ limit: String(limit) });
    if (menuItemId) params.set('menu_item_id', menuItemId);
    return request<{ movements: StockMovement[] }>(`/inventory/movements?${params}`);
  },

  recordStockMovement(menuItemId: string, delta: number, reason: StockReason, note?: string) {
    return request<StockChange>('/inventory/movements', {
      method: 'POST',
      body: JSON.stringify({ menu_item_id: menuItemId, delta, reason, note }),
    });
  },

  countStock(menuItemId: string, counted: number, note?: string) {
    return request<StockChange>('/inventory/count', {
      method: 'POST',
      body: JSON.stringify({ menu_item_id: menuItemId, counted, note }),
    });
  },

  setStockTracking(menuItemId: string, trackStock: boolean) {
    return request<StockChange>('/inventory/tracking', {
      method: 'PATCH',
      body: JSON.stringify({ menu_item_id: menuItemId, track_stock: trackStock }),
    });
  },

  recomputeStock() {
    return request<{ ok: boolean; rows_corrected: number }>('/inventory/recompute', {
      method: 'POST',
    });
  },

  // --- CRM ----------------------------------------------------------------
  // Reads could go straight to Supabase under RLS, the way the inbox does, but
  // every figure below is derived from the orders by backend/crm.py. Deriving
  // them twice, in two languages, is how the two copies start to disagree.

  listCustomers(options: { search?: string; lifecycle?: Lifecycle } = {}) {
    const params = new URLSearchParams();
    if (options.search) params.set('search', options.search);
    if (options.lifecycle) params.set('lifecycle', options.lifecycle);
    const query = params.toString();
    return request<CustomerListResult>(`/crm/customers${query ? `?${query}` : ''}`);
  },

  customer(contactId: string) {
    return request<CustomerDetail>(`/crm/customers/${contactId}`);
  },

  updateCustomer(contactId: string, patch: CustomerPatch) {
    return request<{ contact: CrmContact }>(`/crm/customers/${contactId}`, {
      method: 'PATCH',
      body: JSON.stringify(patch),
    });
  },

  addNote(contactId: string, note: string, pinned = false) {
    return request<{ note: Note }>(`/crm/customers/${contactId}/notes`, {
      method: 'POST',
      body: JSON.stringify({ note, pinned }),
    });
  },

  pinNote(noteId: string, pinned: boolean) {
    return request<{ note: Note }>(`/crm/notes/${noteId}`, {
      method: 'PATCH',
      body: JSON.stringify({ pinned }),
    });
  },

  listTasks(state: 'open' | 'done' | 'all' = 'open', contactId?: string) {
    const params = new URLSearchParams({ state });
    if (contactId) params.set('contact_id', contactId);
    return request<TaskListResult>(`/crm/tasks?${params}`);
  },

  createTask(task: NewTask) {
    return request<{ task: Task }>('/crm/tasks', {
      method: 'POST',
      body: JSON.stringify(task),
    });
  },

  updateTask(taskId: string, patch: TaskPatch) {
    return request<{ task: Task }>(`/crm/tasks/${taskId}`, {
      method: 'PATCH',
      body: JSON.stringify(patch),
    });
  },

  analytics(days = 30) {
    return request<Analytics>(`/crm/analytics?days=${days}`);
  },

  listInvoices(mismatchedOnly = false) {
    const query = mismatchedOnly ? '?mismatched_only=true' : '';
    return request<InvoiceListResult>(`/crm/invoices${query}`);
  },

  reviewInvoice(invoiceId: string) {
    return request<{ invoice: Invoice }>(`/crm/invoices/${invoiceId}/review`, {
      method: 'POST',
    });
  },
};

export interface CustomerListResult {
  customers: CustomerSummary[];
  segments: Partial<Record<Lifecycle, number>>;
}

export interface TaskListResult {
  tasks: Task[];
  open_count: number;
  overdue_count: number;
}

export interface InvoiceListResult {
  invoices: Invoice[];
  mismatch_count: number;
}

/** Only the fields sent are written, so every one of these is optional. */
export interface CustomerPatch {
  name?: string | null;
  email?: string | null;
  address?: string | null;
  city?: string | null;
  birthday?: string | null;
  language?: 'en' | 'si' | 'ta';
  lifecycle?: Lifecycle;
  owner?: string | null;
  source?: ContactSource;
  tags?: string[];
  marketing_opt_in?: boolean;
}

export interface NewTask {
  title: string;
  contact_id?: string | null;
  order_id?: string | null;
  detail?: string | null;
  due_at?: string | null;
  priority?: TaskPriority;
  assigned_to?: string | null;
}

export interface TaskPatch {
  title?: string;
  detail?: string | null;
  due_at?: string | null;
  priority?: TaskPriority;
  assigned_to?: string | null;
  done?: boolean;
}

export interface StockChange {
  ok: boolean;
  menu_item_id: string;
  stock_quantity: number;
  movement: StockMovement | null;
  reason: string | null;
}

/** Friendlier wording for the reasons the backend refuses a send. */
export function explainSendFailure(reason: string | null): string {
  switch (reason) {
    case 'window_closed':
      return 'The 24-hour window has closed. Send an approved template instead.';
    case 'template_unavailable':
      return 'That template is not approved by Meta yet.';
    case 'template_variable_mismatch':
      return 'That template needs a different number of values.';
    case 'empty_body':
      return 'Type a message first.';
    default:
      return reason?.startsWith('send_failed')
        ? 'WhatsApp rejected the message. Check the logs.'
        : 'The message could not be sent.';
  }
}

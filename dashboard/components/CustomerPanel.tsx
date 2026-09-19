'use client';

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { HeatBars } from './ui/HeatBars';
import { Icon } from './ui/Icon';
import { Chip, Empty, Loading, Problem } from './ui/Bits';
import {
  LIFECYCLE,
  LIFECYCLE_ORDER,
  SOURCES,
  TASK_PRIORITY,
  dueLabel,
  fromLocalInput,
  isOverdue,
  lifecycleOf,
  stageDisagreement,
  toLocalInput,
} from '@/lib/crm';
import { contactLabel, formatMoney, formatRelative, orderSummary } from '@/lib/format';
import type {
  ContactSource,
  CrmContact,
  CustomerDetail,
  CustomerSummary,
  Lifecycle,
  Note,
  Task,
} from '@/lib/types';

/**
 * One customer, everything we know.
 *
 * The header is the only place in this app that spends any colour: a flat band
 * in the stage's colour with the name set in the display face, the way the
 * front of a ramen sleeve carries its name. Below it the screen goes quiet and
 * becomes a record.
 */

type Tab = 'timeline' | 'orders' | 'notes' | 'tasks' | 'details';

const TABS: { value: Tab; label: string }[] = [
  { value: 'timeline', label: 'Timeline' },
  { value: 'orders', label: 'Orders' },
  { value: 'notes', label: 'Notes' },
  { value: 'tasks', label: 'Follow-ups' },
  { value: 'details', label: 'Details' },
];

export function CustomerPanel({
  contactId,
  summary,
  onClose,
  onContactSaved,
}: {
  contactId: string;
  summary: CustomerSummary | null;
  onClose: () => void;
  onContactSaved: (contact: CrmContact) => void;
}) {
  const [detail, setDetail] = useState<CustomerDetail | null>(null);
  const [tab, setTab] = useState<Tab>('timeline');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setDetail(await api.customer(contactId));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load this customer.');
    } finally {
      setLoading(false);
    }
  }, [contactId]);

  useEffect(() => {
    void load();
  }, [load]);

  const saveContact = useCallback(
    (contact: CrmContact) => {
      setDetail((current) => (current ? { ...current, contact } : current));
      onContactSaved(contact);
    },
    [onContactSaved],
  );

  // The summary row already has the name and the stats, so the header can be
  // drawn before the detail request lands rather than flashing a spinner.
  const contact = detail?.contact ?? summary?.contact ?? null;
  const stats = detail?.stats ?? summary?.stats ?? null;

  if (!contact || !stats) {
    return (
      <div className="p-6">
        {error ? <Problem onRetry={load}>{error}</Problem> : <Loading what="this customer" />}
      </div>
    );
  }

  const stage = lifecycleOf(contact.lifecycle);
  const suggested = stageDisagreement(stats, contact.lifecycle);

  return (
    <div className="scroll-thin flex h-full min-h-0 flex-col overflow-y-auto">
      {/* --- the band ---------------------------------------------------- */}
      <header className={`${stage.band} px-5 py-5 text-white`}>
        <div className="mx-auto flex max-w-4xl flex-wrap items-start gap-3">
          <button
            onClick={onClose}
            className="-ml-1 rounded-lg p-1 text-white/70 hover:bg-white/15 hover:text-white lg:hidden"
            aria-label="Back to the customer book"
          >
            <Icon name="back" />
          </button>

          <div className="min-w-0 flex-1">
            <p className="font-mono text-2xs uppercase tracking-[0.16em] text-white/70">
              {stage.label} · {SOURCES[contact.source] ?? contact.source}
            </p>
            <h2 className="mt-1 truncate font-display text-3xl font-extrabold tracking-tightest">
              {contactLabel(contact)}
            </h2>
            <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-xs text-white/80">
              <span className="inline-flex items-center gap-1">
                <Icon name="phone" className="h-3.5 w-3.5" />+{contact.wa_id}
              </span>
              {contact.city && <span>{contact.city}</span>}
              {contact.owner && <span>looked after by {contact.owner}</span>}
            </p>
          </div>

          <div className="flex shrink-0 gap-2">
            <Link
              href={`/inbox?id=${contact.id}`}
              className="rounded-lg bg-white/15 px-3 py-2 text-sm font-medium backdrop-blur transition hover:bg-white/25"
            >
              Open chat
            </Link>
            <button
              onClick={() => setTab('tasks')}
              className="rounded-lg bg-white px-3 py-2 text-sm font-semibold text-ink transition hover:bg-white/90"
            >
              Add follow-up
            </button>
          </div>
        </div>
      </header>

      {/* --- the read-out ------------------------------------------------ */}
      <div className="border-b border-line bg-card px-5 py-4">
        <div className="mx-auto max-w-4xl">
          <div className="grid gap-4 sm:grid-cols-4">
            <Figure label="Spent with us" value={formatMoney(stats.lifetime_value)} />
            <Figure
              label="Orders"
              value={String(stats.orders)}
              note={stats.cancelled_orders > 0 ? `${stats.cancelled_orders} cancelled` : undefined}
            />
            <Figure label="Average order" value={formatMoney(stats.average_order)} />
            <Figure
              label="Last order"
              value={
                stats.days_since_last_order === null
                  ? 'Never'
                  : `${stats.days_since_last_order} days ago`
              }
              note={
                stats.average_gap_days !== null
                  ? `usually every ${stats.average_gap_days} days`
                  : undefined
              }
            />
          </div>

          <div className="mt-4 flex flex-wrap items-center gap-x-6 gap-y-3 border-t border-line pt-4">
            <HeatBars stats={stats} size="lg" />
            {detail && (
              <span
                className={`rounded-lg px-2.5 py-1.5 font-mono text-2xs font-semibold uppercase tracking-[0.06em] ${
                  detail.window_open
                    ? 'bg-scallion-wash text-scallion'
                    : 'bg-chilli-wash text-chilli-dark'
                }`}
              >
                {detail.window_open
                  ? `${detail.window_remaining_human} to reply free`
                  : 'Reply window closed'}
              </span>
            )}
            {stats.favourites.length > 0 && (
              <p className="text-sm text-soy">
                Keeps buying{' '}
                <span className="font-medium text-ink">{stats.favourites[0].name}</span>
                {stats.favourites[0].orders > 1 && ` — ${stats.favourites[0].orders} times`}
              </p>
            )}
          </div>

          {suggested && (
            <StageSuggestion
              contact={contact}
              suggested={suggested}
              onSaved={saveContact}
            />
          )}
        </div>
      </div>

      {/* --- tabs --------------------------------------------------------- */}
      <nav className="sticky top-0 z-10 border-b border-line bg-paper/95 px-5 backdrop-blur">
        <div className="scroll-thin mx-auto flex max-w-4xl gap-1 overflow-x-auto">
          {TABS.map((option) => {
            const active = option.value === tab;
            const count =
              option.value === 'orders'
                ? detail?.orders.length
                : option.value === 'notes'
                  ? detail?.notes.length
                  : option.value === 'tasks'
                    ? detail?.tasks.filter((task) => !task.done_at).length
                    : undefined;
            return (
              <button
                key={option.value}
                onClick={() => setTab(option.value)}
                aria-current={active ? 'page' : undefined}
                className={`shrink-0 border-b-2 px-3 py-3 text-sm font-medium transition ${
                  active
                    ? 'border-chilli text-ink'
                    : 'border-transparent text-soy hover:text-ink'
                }`}
              >
                {option.label}
                {count !== undefined && count > 0 && (
                  <span className="ml-1.5 font-mono text-2xs text-soy tnum">{count}</span>
                )}
              </button>
            );
          })}
        </div>
      </nav>

      <div className="mx-auto w-full max-w-4xl flex-1 p-5">
        {loading && !detail && <Loading what="the record" />}
        {error && <Problem onRetry={load}>{error}</Problem>}

        {detail && tab === 'timeline' && <Timeline detail={detail} />}
        {detail && tab === 'orders' && <Orders detail={detail} />}
        {detail && tab === 'notes' && (
          <Notes detail={detail} contactId={contactId} onChanged={setDetail} />
        )}
        {detail && tab === 'tasks' && (
          <Tasks detail={detail} contactId={contactId} onChanged={setDetail} />
        )}
        {detail && tab === 'details' && <Details contact={detail.contact} onSaved={saveContact} />}
      </div>
    </div>
  );
}

function Figure({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div>
      <p className="eyebrow">{label}</p>
      <p className="mt-1 font-display text-xl font-extrabold tracking-tightest tnum">{value}</p>
      {note && <p className="font-mono text-2xs text-soy">{note}</p>}
    </div>
  );
}

/**
 * The orders disagree with the stage on the record. Offer the change; never
 * make it. Staff know things the orders do not.
 */
function StageSuggestion({
  contact,
  suggested,
  onSaved,
}: {
  contact: CrmContact;
  suggested: Lifecycle;
  onSaved: (contact: CrmContact) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [dismissed, setDismissed] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (dismissed) return null;

  async function apply() {
    setBusy(true);
    setError(null);
    try {
      const result = await api.updateCustomer(contact.id, { lifecycle: suggested });
      onSaved(result.contact);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save the stage.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mt-4 flex flex-wrap items-center gap-3 rounded-card border border-broth/30 bg-broth-wash px-3 py-2.5 text-sm">
      <Icon name="warn" className="h-4 w-4 shrink-0 text-broth" />
      <p className="min-w-0 flex-1">
        The orders look like <strong>{LIFECYCLE[suggested].label}</strong>, not{' '}
        {lifecycleOf(contact.lifecycle).label}. {LIFECYCLE[suggested].hint}
      </p>
      {error && <span className="text-xs text-chilli">{error}</span>}
      <button onClick={apply} disabled={busy} className="btn-primary py-1.5 text-xs">
        {busy ? 'Saving…' : `Move to ${LIFECYCLE[suggested].label}`}
      </button>
      <button onClick={() => setDismissed(true)} className="btn-ghost py-1.5 text-xs">
        Leave it
      </button>
    </div>
  );
}

/** Everything that has happened, newest first, whatever kind of thing it was. */
function Timeline({ detail }: { detail: CustomerDetail }) {
  type Entry = {
    at: string;
    kind: 'order' | 'note' | 'message' | 'bill' | 'task';
    title: string;
    body?: string;
    tone: string;
  };

  const entries: Entry[] = [
    ...detail.orders.map((order) => ({
      at: order.created_at,
      kind: 'order' as const,
      title: `Order #${order.order_number} · ${formatMoney(order.total)} · ${order.status}`,
      body: orderSummary(order),
      tone: 'bg-scallion',
    })),
    ...detail.notes.map((note) => ({
      at: note.created_at,
      kind: 'note' as const,
      title: `Note by ${note.created_by}`,
      body: note.note,
      tone: 'bg-broth',
    })),
    ...detail.invoices.map((invoice) => ({
      at: invoice.printed_at,
      kind: 'bill' as const,
      title: `Bill ${invoice.bill_no} printed on ${invoice.device_id}`,
      body: invoice.mismatch ? 'Printed price did not match the catalogue.' : undefined,
      tone: invoice.mismatch ? 'bg-chilli' : 'bg-ink/30',
    })),
    ...detail.tasks.map((task) => ({
      at: task.created_at,
      kind: 'task' as const,
      title: task.done_at ? `Done: ${task.title}` : `Follow-up: ${task.title}`,
      body: task.detail ?? undefined,
      tone: task.done_at ? 'bg-ink/30' : 'bg-buldak',
    })),
    ...detail.messages.map((message) => ({
      at: message.created_at,
      kind: 'message' as const,
      title:
        message.direction === 'in'
          ? 'Customer wrote'
          : `${message.sender === 'agent' ? 'Agent' : 'Staff'} replied`,
      body: message.body ?? `[${message.message_type}]`,
      tone: 'bg-ink/20',
    })),
  ].sort((a, b) => Date.parse(b.at) - Date.parse(a.at));

  if (entries.length === 0) {
    return (
      <Empty title="Nothing yet">
        This record fills itself as the customer messages, orders and gets served.
      </Empty>
    );
  }

  return (
    <ol className="relative space-y-4 border-l border-line pl-5">
      {entries.map((entry, index) => (
        <li key={`${entry.kind}-${entry.at}-${index}`} className="relative">
          <span
            className={`absolute -left-[26px] top-1.5 h-2.5 w-2.5 rounded-full ring-4 ring-paper ${entry.tone}`}
          />
          <p className="flex flex-wrap items-baseline gap-2">
            <span className="text-sm font-medium">{entry.title}</span>
            <span className="font-mono text-2xs text-soy">
              {formatRelative(entry.at)} ago ·{' '}
              {new Date(entry.at).toLocaleDateString([], { day: 'numeric', month: 'short' })}
            </span>
          </p>
          {entry.body && (
            <p className="mt-0.5 whitespace-pre-wrap break-words text-sm text-soy">{entry.body}</p>
          )}
        </li>
      ))}
    </ol>
  );
}

function Orders({ detail }: { detail: CustomerDetail }) {
  if (detail.orders.length === 0) {
    return (
      <Empty title="No orders yet">
        This customer has messaged but never bought. That is what the Lead stage means.
      </Empty>
    );
  }

  const billsByOrder = new Map(detail.invoices.map((invoice) => [invoice.order_id, invoice]));

  return (
    <ul className="space-y-3">
      {detail.orders.map((order) => {
        const bill = billsByOrder.get(order.id);
        return (
          <li key={order.id} className="card p-4">
            <div className="flex flex-wrap items-baseline gap-2">
              <h3 className="font-display text-base font-bold tracking-tightest">
                Order #{order.order_number}
              </h3>
              <Chip
                className={
                  order.status === 'cancelled'
                    ? 'bg-soy/[0.12] text-soy'
                    : order.status === 'delivered'
                      ? 'bg-scallion-wash text-scallion'
                      : 'bg-broth-wash text-broth'
                }
              >
                {order.status}
              </Chip>
              <span className="font-mono text-2xs text-soy">
                {new Date(order.created_at).toLocaleDateString([], {
                  day: 'numeric',
                  month: 'short',
                  year: 'numeric',
                })}
              </span>
              <span className="ml-auto font-mono text-sm font-semibold tnum">
                {formatMoney(order.total)}
              </span>
            </div>

            <ul className="mt-2 space-y-0.5 text-sm text-soy">
              {(order.items ?? []).map((item, index) => (
                <li key={index} className="flex gap-2">
                  <span className="font-mono tnum">{item.quantity}×</span>
                  <span className="min-w-0 flex-1 truncate">{item.name}</span>
                  {item.subtotal !== undefined && (
                    <span className="font-mono tnum">{formatMoney(item.subtotal)}</span>
                  )}
                </li>
              ))}
            </ul>

            {order.notes && <p className="mt-2 text-xs text-soy">{order.notes}</p>}

            {bill && (
              <p className="mt-2 flex items-center gap-2 border-t border-line pt-2 font-mono text-2xs text-soy">
                <Icon name="bills" className="h-3.5 w-3.5" />
                {bill.bill_no}
                {bill.mismatch && (
                  <span className="font-semibold text-chilli">
                    printed {formatMoney(bill.paper_total)} vs {formatMoney(bill.server_total)}
                  </span>
                )}
              </p>
            )}
          </li>
        );
      })}
    </ul>
  );
}

function Notes({
  detail,
  contactId,
  onChanged,
}: {
  detail: CustomerDetail;
  contactId: string;
  onChanged: (detail: CustomerDetail) => void;
}) {
  const [text, setText] = useState('');
  const [pinned, setPinned] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function add(event: React.FormEvent) {
    event.preventDefault();
    if (!text.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const { note } = await api.addNote(contactId, text.trim(), pinned);
      onChanged({ ...detail, notes: sortNotes([note, ...detail.notes]) });
      setText('');
      setPinned(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save the note.');
    } finally {
      setBusy(false);
    }
  }

  async function togglePin(note: Note) {
    try {
      const result = await api.pinNote(note.id, !note.pinned);
      onChanged({
        ...detail,
        notes: sortNotes(detail.notes.map((n) => (n.id === note.id ? result.note : n))),
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not change the pin.');
    }
  }

  return (
    <div>
      <form onSubmit={add} className="card p-3">
        <label className="label mb-1.5" htmlFor="new-note">
          What should the next person know?
        </label>
        <textarea
          id="new-note"
          value={text}
          onChange={(event) => setText(event.target.value)}
          rows={3}
          placeholder="Allergic to shellfish. Always pays on delivery. Asks for the black pack."
          className="field resize-y"
        />
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-2 text-sm text-soy">
            <input
              type="checkbox"
              checked={pinned}
              onChange={(event) => setPinned(event.target.checked)}
              className="h-4 w-4 accent-chilli"
            />
            Pin it above the rest
          </label>
          <button type="submit" disabled={busy || !text.trim()} className="btn-primary ml-auto">
            {busy ? 'Saving…' : 'Save note'}
          </button>
        </div>
        <p className="mt-2 text-2xs text-soy">
          The agent reads these notes when it answers, so what you write here changes what the
          customer is told next time.
        </p>
      </form>

      {error && (
        <div className="mt-3">
          <Problem>{error}</Problem>
        </div>
      )}

      {detail.notes.length === 0 ? (
        <div className="mt-4">
          <Empty title="No notes yet">
            The first note is usually the useful one: how they like to be delivered to, or what
            they always order.
          </Empty>
        </div>
      ) : (
        <ul className="mt-4 space-y-2">
          {detail.notes.map((note) => (
            <li
              key={note.id}
              className={`card flex items-start gap-3 p-3 ${
                note.pinned ? 'border-broth/40 bg-broth-wash' : ''
              }`}
            >
              <div className="min-w-0 flex-1">
                <p className="whitespace-pre-wrap break-words text-sm">{note.note}</p>
                <p className="mt-1 font-mono text-2xs text-soy">
                  {note.created_by} · {formatRelative(note.created_at)} ago
                </p>
              </div>
              <button
                onClick={() => togglePin(note)}
                title={note.pinned ? 'Unpin this note' : 'Pin this note to the top'}
                className={`rounded-lg p-1.5 transition ${
                  note.pinned ? 'text-broth' : 'text-soy hover:bg-ink/5 hover:text-ink'
                }`}
              >
                <Icon name="pin" className="h-4 w-4" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function sortNotes(notes: Note[]): Note[] {
  const pinned = notes.filter((note) => note.pinned);
  const rest = notes.filter((note) => !note.pinned);
  const newest = (a: Note, b: Note) => Date.parse(b.created_at) - Date.parse(a.created_at);
  return [...pinned.sort(newest), ...rest.sort(newest)];
}

function Tasks({
  detail,
  contactId,
  onChanged,
}: {
  detail: CustomerDetail;
  contactId: string;
  onChanged: (detail: CustomerDetail) => void;
}) {
  const [title, setTitle] = useState('');
  const [due, setDue] = useState('');
  const [priority, setPriority] = useState<keyof typeof TASK_PRIORITY>('normal');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function add(event: React.FormEvent) {
    event.preventDefault();
    if (!title.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const { task } = await api.createTask({
        title: title.trim(),
        contact_id: contactId,
        due_at: fromLocalInput(due),
        priority,
      });
      onChanged({ ...detail, tasks: [task, ...detail.tasks] });
      setTitle('');
      setDue('');
      setPriority('normal');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save the follow-up.');
    } finally {
      setBusy(false);
    }
  }

  async function toggle(task: Task) {
    try {
      const result = await api.updateTask(task.id, { done: !task.done_at });
      onChanged({
        ...detail,
        tasks: detail.tasks.map((existing) => (existing.id === task.id ? result.task : existing)),
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not update the follow-up.');
    }
  }

  const open = detail.tasks.filter((task) => !task.done_at);
  const done = detail.tasks.filter((task) => task.done_at);

  return (
    <div>
      <form onSubmit={add} className="card p-3">
        <label className="label mb-1.5" htmlFor="new-task">
          What did we promise?
        </label>
        <input
          id="new-task"
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          placeholder="Ring back once the Buldak carbonara lands"
          className="field"
        />
        <div className="mt-2 flex flex-wrap items-end gap-3">
          <label className="text-sm">
            <span className="label mb-1">Due</span>
            <input
              type="datetime-local"
              value={due}
              onChange={(event) => setDue(event.target.value)}
              className="field"
            />
          </label>
          <label className="text-sm">
            <span className="label mb-1">Priority</span>
            <select
              value={priority}
              onChange={(event) => setPriority(event.target.value as keyof typeof TASK_PRIORITY)}
              className="field"
            >
              <option value="low">Low</option>
              <option value="normal">Normal</option>
              <option value="high">High</option>
            </select>
          </label>
          <button type="submit" disabled={busy || !title.trim()} className="btn-primary ml-auto">
            {busy ? 'Saving…' : 'Add follow-up'}
          </button>
        </div>
      </form>

      {error && (
        <div className="mt-3">
          <Problem>{error}</Problem>
        </div>
      )}

      {open.length === 0 && done.length === 0 ? (
        <div className="mt-4">
          <Empty title="Nothing promised to this customer">
            Follow-ups are how a promise survives the end of a shift.
          </Empty>
        </div>
      ) : (
        <div className="mt-4 space-y-2">
          {open.map((task) => (
            <TaskRow key={task.id} task={task} onToggle={() => toggle(task)} />
          ))}
          {done.length > 0 && (
            <>
              <p className="eyebrow pt-3">Done</p>
              {done.map((task) => (
                <TaskRow key={task.id} task={task} onToggle={() => toggle(task)} />
              ))}
            </>
          )}
        </div>
      )}
    </div>
  );
}

export function TaskRow({
  task,
  onToggle,
  customer,
}: {
  task: Task;
  onToggle: () => void;
  customer?: React.ReactNode;
}) {
  const late = isOverdue(task);
  const done = Boolean(task.done_at);

  return (
    <div className={`card flex items-start gap-3 p-3 ${done ? 'opacity-60' : ''}`}>
      <button
        onClick={onToggle}
        aria-pressed={done}
        aria-label={done ? 'Reopen this follow-up' : 'Mark this follow-up done'}
        className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-md border transition ${
          done ? 'border-scallion bg-scallion text-white' : 'border-line hover:border-ink'
        }`}
      >
        {done && <Icon name="check" className="h-3.5 w-3.5" />}
      </button>

      <div className="min-w-0 flex-1">
        <p className={`text-sm ${done ? 'line-through' : ''}`}>{task.title}</p>
        {task.detail && <p className="mt-0.5 text-xs text-soy">{task.detail}</p>}
        <p className="mt-1 flex flex-wrap items-center gap-2">
          {customer}
          <span className={`font-mono text-2xs ${late ? 'text-chilli' : 'text-soy'}`}>
            {done ? `Done by ${task.done_by}` : dueLabel(task)}
          </span>
          {task.assigned_to && !done && (
            <span className="font-mono text-2xs text-soy">· {task.assigned_to}</span>
          )}
        </p>
      </div>

      {!done && task.priority !== 'normal' && (
        <Chip className={TASK_PRIORITY[task.priority].chip}>
          {TASK_PRIORITY[task.priority].label}
        </Chip>
      )}
    </div>
  );
}

/** The record staff fill in. Everything optional; only what changed is sent. */
function Details({
  contact,
  onSaved,
}: {
  contact: CrmContact;
  onSaved: (contact: CrmContact) => void;
}) {
  const [form, setForm] = useState({
    name: contact.name ?? '',
    email: contact.email ?? '',
    address: contact.address ?? '',
    city: contact.city ?? '',
    birthday: contact.birthday ?? '',
    owner: contact.owner ?? '',
    language: contact.language ?? 'en',
    lifecycle: contact.lifecycle,
    source: contact.source,
    marketing_opt_in: contact.marketing_opt_in,
    tags: (contact.tags ?? []).join(', '),
  });
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function set<K extends keyof typeof form>(key: K, value: (typeof form)[K]) {
    setForm((current) => ({ ...current, [key]: value }));
    setSaved(false);
  }

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const result = await api.updateCustomer(contact.id, {
        name: form.name.trim() || null,
        email: form.email.trim() || null,
        address: form.address.trim() || null,
        city: form.city.trim() || null,
        birthday: form.birthday || null,
        owner: form.owner.trim() || null,
        language: form.language as 'en' | 'si' | 'ta',
        lifecycle: form.lifecycle,
        source: form.source,
        marketing_opt_in: form.marketing_opt_in,
        tags: form.tags
          .split(',')
          .map((tag) => tag.trim())
          .filter(Boolean),
      });
      onSaved(result.contact);
      setSaved(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save this record.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={save} className="card space-y-4 p-5">
      <div className="grid gap-4 sm:grid-cols-2">
        <Text label="Name" value={form.name} onChange={(v) => set('name', v)} />
        <Text
          label="Phone"
          value={`+${contact.wa_id}`}
          readOnly
          hint="WhatsApp owns this number. It cannot be edited here."
        />
        <Text label="Email" value={form.email} onChange={(v) => set('email', v)} type="email" />
        <Text label="Town" value={form.city} onChange={(v) => set('city', v)} />
        <div className="sm:col-span-2">
          <label className="label mb-1.5">Delivery address</label>
          <textarea
            value={form.address}
            onChange={(event) => set('address', event.target.value)}
            rows={2}
            className="field resize-y"
            placeholder="Written on the courier slip exactly as typed."
          />
        </div>
        <Text
          label="Birthday"
          value={form.birthday}
          onChange={(v) => set('birthday', v)}
          type="date"
        />
        <Text
          label="Looked after by"
          value={form.owner}
          onChange={(v) => set('owner', v)}
          hint="Whoever knows this customer best."
        />

        <Select
          label="Stage"
          value={form.lifecycle}
          onChange={(v) => set('lifecycle', v as Lifecycle)}
          options={LIFECYCLE_ORDER.map((key) => ({ value: key, label: LIFECYCLE[key].label }))}
          hint={LIFECYCLE[form.lifecycle].hint}
        />
        <Select
          label="Came to us through"
          value={form.source}
          onChange={(v) => set('source', v as ContactSource)}
          options={Object.entries(SOURCES).map(([value, label]) => ({ value, label }))}
        />
        <Select
          label="Writes to us in"
          value={form.language}
          onChange={(v) => set('language', v)}
          options={[
            { value: 'en', label: 'English' },
            { value: 'si', label: 'Sinhala' },
            { value: 'ta', label: 'Tamil' },
          ]}
        />
        <Text
          label="Tags"
          value={form.tags}
          onChange={(v) => set('tags', v)}
          hint="Comma separated — wholesale, office, spicy only."
        />
      </div>

      <label className="flex items-start gap-2.5 border-t border-line pt-4 text-sm">
        <input
          type="checkbox"
          checked={form.marketing_opt_in}
          onChange={(event) => set('marketing_opt_in', event.target.checked)}
          className="mt-0.5 h-4 w-4 accent-chilli"
        />
        <span>
          Happy to receive offers
          <span className="block text-xs text-soy">
            Only tick this if they said so. Meta closes numbers that send unwanted marketing.
          </span>
        </span>
      </label>

      {error && <Problem>{error}</Problem>}

      <div className="flex items-center gap-3">
        <button type="submit" disabled={busy} className="btn-primary">
          {busy ? 'Saving…' : 'Save record'}
        </button>
        {saved && (
          <span className="flex items-center gap-1.5 text-sm text-scallion">
            <Icon name="check" className="h-4 w-4" />
            Saved
          </span>
        )}
      </div>
    </form>
  );
}

function Text({
  label,
  value,
  onChange,
  type = 'text',
  hint,
  readOnly,
}: {
  label: string;
  value: string;
  onChange?: (value: string) => void;
  type?: string;
  hint?: string;
  readOnly?: boolean;
}) {
  return (
    <label className="block">
      <span className="label mb-1.5">{label}</span>
      <input
        type={type}
        value={value}
        readOnly={readOnly}
        onChange={(event) => onChange?.(event.target.value)}
        className={`field ${readOnly ? 'bg-paper font-mono text-soy' : ''}`}
      />
      {hint && <span className="mt-1 block text-2xs text-soy">{hint}</span>}
    </label>
  );
}

function Select({
  label,
  value,
  onChange,
  options,
  hint,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: { value: string; label: string }[];
  hint?: string;
}) {
  return (
    <label className="block">
      <span className="label mb-1.5">{label}</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="field"
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      {hint && <span className="mt-1 block text-2xs text-soy">{hint}</span>}
    </label>
  );
}

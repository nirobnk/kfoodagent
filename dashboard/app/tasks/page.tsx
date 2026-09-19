'use client';

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '@/lib/api';
import { Page, PageHeader } from '@/components/AppShell';
import { TaskRow } from '@/components/CustomerPanel';
import { Empty, Loading, Problem, Segmented } from '@/components/ui/Bits';
import { TASK_PRIORITY, fromLocalInput, isOverdue } from '@/lib/crm';
import { contactLabel } from '@/lib/format';
import type { CustomerSummary, Task } from '@/lib/types';

/**
 * Follow-ups: the promises that have to survive the end of a shift.
 *
 * Grouped by when they are due rather than by customer, because the question
 * this page answers is "what do I have to do before I go home", not "what do we
 * owe this person" — that one is answered on the customer's own record.
 */

type View = 'open' | 'done';

export default function TasksPage() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [customers, setCustomers] = useState<CustomerSummary[]>([]);
  const [view, setView] = useState<View>('open');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [all, book] = await Promise.all([api.listTasks('all'), api.listCustomers()]);
      setTasks(all.tasks);
      setCustomers(book.customers);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load the follow-ups.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const names = useMemo(
    () => new Map(customers.map((row) => [row.contact.id, contactLabel(row.contact)])),
    [customers],
  );

  const upsert = useCallback((task: Task) => {
    setTasks((current) => {
      const index = current.findIndex((existing) => existing.id === task.id);
      if (index < 0) return [task, ...current];
      const next = [...current];
      next[index] = task;
      return next;
    });
  }, []);

  async function toggle(task: Task) {
    try {
      const result = await api.updateTask(task.id, { done: !task.done_at });
      upsert(result.task);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not update the follow-up.');
    }
  }

  const open = tasks.filter((task) => !task.done_at);
  const done = tasks
    .filter((task) => task.done_at)
    .sort((a, b) => Date.parse(b.done_at!) - Date.parse(a.done_at!));

  const groups = useMemo(() => {
    const now = Date.now();
    const endOfToday = new Date();
    endOfToday.setHours(23, 59, 59, 999);
    const endOfWeek = endOfToday.getTime() + 6 * 86400000;

    const late: Task[] = [];
    const today: Task[] = [];
    const week: Task[] = [];
    const later: Task[] = [];
    const undated: Task[] = [];

    for (const task of open) {
      if (!task.due_at) undated.push(task);
      else if (isOverdue(task, now)) late.push(task);
      else if (Date.parse(task.due_at) <= endOfToday.getTime()) today.push(task);
      else if (Date.parse(task.due_at) <= endOfWeek) week.push(task);
      else later.push(task);
    }

    return [
      { heading: 'Late', tasks: late, tone: 'text-chilli' },
      { heading: 'Today', tasks: today, tone: 'text-ink' },
      { heading: 'This week', tasks: week, tone: 'text-ink' },
      { heading: 'Later', tasks: later, tone: 'text-soy' },
      { heading: 'No date', tasks: undated, tone: 'text-soy' },
    ].filter((group) => group.tasks.length > 0);
  }, [open]);

  return (
    <Page>
      <PageHeader title="Follow-ups" lede="What someone said we would do.">
        <Segmented
          value={view}
          onChange={setView}
          options={[
            { value: 'open', label: 'Open', count: open.length },
            { value: 'done', label: 'Done', count: done.length },
          ]}
        />
      </PageHeader>

      <NewTask customers={customers} onCreated={upsert} />

      {error && (
        <div className="mt-4">
          <Problem onRetry={load}>{error}</Problem>
        </div>
      )}
      {loading && tasks.length === 0 && <Loading what="the follow-ups" />}

      {view === 'open' ? (
        groups.length === 0 && !loading ? (
          <div className="mt-4">
            <Empty title="Nothing outstanding">
              Everything promised has been done. Add the next one above.
            </Empty>
          </div>
        ) : (
          <div className="mt-6 space-y-6">
            {groups.map((group) => (
              <section key={group.heading}>
                <h2 className={`eyebrow mb-2 ${group.tone}`}>
                  {group.heading} · {group.tasks.length}
                </h2>
                <div className="space-y-2">
                  {group.tasks.map((task) => (
                    <TaskRow
                      key={task.id}
                      task={task}
                      onToggle={() => toggle(task)}
                      customer={<CustomerLink task={task} names={names} />}
                    />
                  ))}
                </div>
              </section>
            ))}
          </div>
        )
      ) : done.length === 0 ? (
        <div className="mt-4">
          <Empty title="Nothing ticked off yet">
            Completed follow-ups stay here so there is a record of what was actually done.
          </Empty>
        </div>
      ) : (
        <div className="mt-6 space-y-2">
          {done.map((task) => (
            <TaskRow
              key={task.id}
              task={task}
              onToggle={() => toggle(task)}
              customer={<CustomerLink task={task} names={names} />}
            />
          ))}
        </div>
      )}
    </Page>
  );
}

function CustomerLink({ task, names }: { task: Task; names: Map<string, string> }) {
  if (!task.contact_id) return null;
  const name = names.get(task.contact_id);
  if (!name) return null;
  return (
    <Link
      href={`/customers?id=${task.contact_id}`}
      className="text-2xs font-medium text-chilli underline underline-offset-2"
    >
      {name}
    </Link>
  );
}

function NewTask({
  customers,
  onCreated,
}: {
  customers: CustomerSummary[];
  onCreated: (task: Task) => void;
}) {
  const [title, setTitle] = useState('');
  const [contactId, setContactId] = useState('');
  const [due, setDue] = useState('');
  const [priority, setPriority] = useState<keyof typeof TASK_PRIORITY>('normal');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!title.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const { task } = await api.createTask({
        title: title.trim(),
        contact_id: contactId || null,
        due_at: fromLocalInput(due),
        priority,
      });
      onCreated(task);
      setTitle('');
      setContactId('');
      setDue('');
      setPriority('normal');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save the follow-up.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="card p-4">
      <label className="label mb-1.5" htmlFor="task-title">
        Add a follow-up
      </label>
      <input
        id="task-title"
        value={title}
        onChange={(event) => setTitle(event.target.value)}
        placeholder="Ring Kasun back about the wholesale price"
        className="field"
      />

      <div className="mt-3 grid gap-3 sm:grid-cols-4">
        <label className="sm:col-span-2">
          <span className="label mb-1">Customer</span>
          <select
            value={contactId}
            onChange={(event) => setContactId(event.target.value)}
            className="field"
          >
            <option value="">Not about a customer</option>
            {customers.map((row) => (
              <option key={row.contact.id} value={row.contact.id}>
                {contactLabel(row.contact)}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span className="label mb-1">Due</span>
          <input
            type="datetime-local"
            value={due}
            onChange={(event) => setDue(event.target.value)}
            className="field"
          />
        </label>
        <label>
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
      </div>

      {error && (
        <div className="mt-3">
          <Problem>{error}</Problem>
        </div>
      )}

      <button type="submit" disabled={busy || !title.trim()} className="btn-primary mt-3">
        {busy ? 'Saving…' : 'Add follow-up'}
      </button>
    </form>
  );
}

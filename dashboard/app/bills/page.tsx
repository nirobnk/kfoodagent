'use client';

import { useCallback, useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { Page, PageHeader } from '@/components/AppShell';
import { Icon } from '@/components/ui/Icon';
import { Chip, Empty, Loading, Problem, Segmented, Stat } from '@/components/ui/Bits';
import { invoiceGap } from '@/lib/crm';
import { formatMoney, formatRelative } from '@/lib/format';
import type { Invoice } from '@/lib/types';

/**
 * The bills the shop Mac actually printed.
 *
 * Until now these were reachable only by the device that wrote them, so a bill
 * whose printed price did not match the catalogue had nowhere to be looked at.
 * That is the whole job of this page: show the paper, show what the server
 * thought, and let a human say they have seen it.
 *
 * Reviewing changes no figure. The paper is in a customer's parcel and says
 * what it says — rewriting it here would destroy the only evidence of what was
 * charged.
 */

type View = 'mismatched' | 'all';

export default function BillsPage() {
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [view, setView] = useState<View>('mismatched');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await api.listInvoices(false);
      setInvoices(result.invoices);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load the printed bills.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function review(invoice: Invoice) {
    setBusyId(invoice.id);
    setError(null);
    try {
      const result = await api.reviewInvoice(invoice.id);
      setInvoices((current) =>
        current.map((row) => (row.id === invoice.id ? result.invoice : row)),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not record the review.');
    } finally {
      setBusyId(null);
    }
  }

  const mismatched = invoices.filter((invoice) => invoice.mismatch);
  const waiting = mismatched.filter((invoice) => !invoice.reviewed_at);
  const visible = view === 'mismatched' ? mismatched : invoices;

  const printedToday = invoices.filter(
    (invoice) => new Date(invoice.printed_at).toDateString() === new Date().toDateString(),
  );

  return (
    <Page>
      <PageHeader
        title="Printed bills"
        lede="What came out of the printer, next to what the catalogue says it should have."
      >
        <Segmented
          value={view}
          onChange={setView}
          options={[
            { value: 'mismatched', label: 'Price mismatches', count: mismatched.length },
            { value: 'all', label: 'All bills', count: invoices.length },
          ]}
        />
      </PageHeader>

      <div className="mb-5 grid gap-3 sm:grid-cols-3">
        <Stat label="Printed today" value={String(printedToday.length)} />
        <Stat
          label="Waiting on review"
          value={String(waiting.length)}
          tone={waiting.length > 0 ? 'hot' : 'plain'}
          sub={waiting.length > 0 ? 'A person needs to look at these' : 'Nothing outstanding'}
        />
        <Stat
          label="Bills held"
          value={String(invoices.length)}
          sub="The most recent 100 the tills sent"
        />
      </div>

      {error && (
        <div className="mb-4">
          <Problem onRetry={load}>{error}</Problem>
        </div>
      )}
      {loading && invoices.length === 0 && <Loading what="the printed bills" />}

      {!loading && visible.length === 0 && (
        <Empty title={view === 'mismatched' ? 'Every price matched' : 'No bills yet'}>
          {view === 'mismatched'
            ? 'Every bill the tills printed was priced from the current catalogue.'
            : 'Bills appear here as soon as the shop Mac prints one and reaches the internet.'}
        </Empty>
      )}

      <ul className="space-y-3">
        {visible.map((invoice) => {
          const gap = invoiceGap(invoice);
          return (
            <li key={invoice.id} className="card p-4">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-sm font-semibold">{invoice.bill_no}</span>
                <Chip className="bg-ink/[0.08] text-ink">{invoice.device_id}</Chip>
                {invoice.mismatch ? (
                  <Chip className="bg-chilli-wash text-chilli">price mismatch</Chip>
                ) : (
                  <Chip className="bg-scallion-wash text-scallion">matched</Chip>
                )}
                {invoice.reviewed_at && (
                  <Chip className="bg-soy/[0.12] text-soy">
                    reviewed by {invoice.reviewed_by}
                  </Chip>
                )}
                <span className="ml-auto font-mono text-2xs text-soy">
                  printed {formatRelative(invoice.printed_at)} ago
                </span>
              </div>

              <div className="mt-3 grid gap-4 sm:grid-cols-3">
                <Money label="On the paper" value={invoice.paper_total} />
                <Money label="Catalogue says" value={invoice.server_total} />
                <div>
                  <p className="eyebrow">Difference</p>
                  <p
                    className={`mt-1 font-display text-xl font-extrabold tracking-tightest tnum ${
                      gap === 0 ? 'text-ink' : 'text-chilli'
                    }`}
                  >
                    {gap === 0 ? '—' : `${gap > 0 ? '+' : ''}${formatMoney(gap)}`}
                  </p>
                  {gap !== 0 && (
                    <p className="text-2xs text-soy">
                      {gap > 0 ? 'The customer paid more' : 'The customer paid less'}
                    </p>
                  )}
                </div>
              </div>

              {invoice.mismatch_detail.length > 0 && (
                <ul className="mt-3 space-y-1 border-t border-line pt-3 font-mono text-2xs text-soy">
                  {invoice.mismatch_detail.map((row, index) => (
                    <li key={index} className="flex flex-wrap gap-2">
                      <span className="font-semibold text-ink">{row.sku ?? 'line'}</span>
                      {row.printed !== undefined && <span>printed {formatMoney(row.printed)}</span>}
                      {row.server !== undefined && <span>· catalogue {formatMoney(row.server)}</span>}
                      {row.reason && <span>· {row.reason}</span>}
                    </li>
                  ))}
                </ul>
              )}

              {invoice.mismatch && !invoice.reviewed_at && (
                <div className="mt-3 flex flex-wrap items-center gap-3 border-t border-line pt-3">
                  <p className="min-w-0 flex-1 text-xs text-soy">
                    Reviewing records that you looked. It changes neither figure — the paper in the
                    parcel is what the customer was charged.
                  </p>
                  <button
                    onClick={() => review(invoice)}
                    disabled={busyId === invoice.id}
                    className="btn-primary py-1.5 text-xs"
                  >
                    <Icon name="check" className="h-4 w-4" />
                    {busyId === invoice.id ? 'Saving…' : 'I have seen this'}
                  </button>
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </Page>
  );
}

function Money({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <p className="eyebrow">{label}</p>
      <p className="mt-1 font-display text-xl font-extrabold tracking-tightest tnum">
        {formatMoney(value)}
      </p>
    </div>
  );
}

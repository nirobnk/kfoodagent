'use client';

import { Icon } from './Icon';

/** A labelled figure. The eyebrow above, the number in display type below. */
export function Stat({
  label,
  value,
  sub,
  tone = 'plain',
}: {
  label: string;
  value: string;
  sub?: React.ReactNode;
  tone?: 'plain' | 'hot' | 'good';
}) {
  const colour =
    tone === 'hot' ? 'text-chilli' : tone === 'good' ? 'text-scallion' : 'text-ink';
  return (
    <div className="card p-4">
      <p className="eyebrow">{label}</p>
      <p className={`mt-2 font-display text-2xl font-extrabold tracking-tightest tnum ${colour}`}>
        {value}
      </p>
      {sub && <div className="mt-1 text-xs text-soy">{sub}</div>}
    </div>
  );
}

/** Change against the period before. Silent when there is nothing to compare. */
export function Delta({ percent }: { percent: number | null }) {
  if (percent === null) return <span className="text-soy">no earlier period</span>;
  const up = percent >= 0;
  return (
    <span className={up ? 'text-scallion' : 'text-chilli'}>
      {up ? '▲' : '▼'} {Math.abs(percent).toFixed(0)}%{' '}
      <span className="text-soy">vs previous</span>
    </span>
  );
}

export function Chip({
  children,
  className = 'bg-ink/[0.08] text-ink',
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return <span className={`tag ${className}`}>{children}</span>;
}

/** An empty screen is an invitation to act, so each one says what to do next. */
export function Empty({
  title,
  children,
  action,
}: {
  title: string;
  children?: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <div className="card flex flex-col items-center gap-2 px-6 py-12 text-center">
      <p className="font-display text-base font-bold">{title}</p>
      {children && <p className="max-w-sm text-sm text-soy">{children}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

export function Loading({ what }: { what: string }) {
  return (
    <div className="flex items-center gap-2 px-1 py-8 text-sm text-soy">
      <span className="h-3 w-3 animate-spin rounded-full border-2 border-ink/20 border-t-ink" />
      Loading {what}…
    </div>
  );
}

/** Errors explain what happened and how to fix it. They do not apologise. */
export function Problem({ children, onRetry }: { children: React.ReactNode; onRetry?: () => void }) {
  return (
    <div className="flex items-start gap-3 rounded-card border border-chilli/25 bg-chilli-wash p-3 text-sm text-chilli-dark">
      <Icon name="warn" className="mt-0.5 h-4 w-4 shrink-0" />
      <div className="min-w-0 flex-1">{children}</div>
      {onRetry && (
        <button onClick={onRetry} className="shrink-0 font-medium underline underline-offset-2">
          Try again
        </button>
      )}
    </div>
  );
}

/** A row of filter buttons. One is always on. */
export function Segmented<T extends string>({
  options,
  value,
  onChange,
}: {
  options: { value: T; label: string; count?: number }[];
  value: T;
  onChange: (value: T) => void;
}) {
  return (
    <div className="flex flex-wrap gap-1">
      {options.map((option) => {
        const active = option.value === value;
        return (
          <button
            key={option.value}
            onClick={() => onChange(option.value)}
            aria-pressed={active}
            className={`rounded-lg px-2.5 py-1.5 text-sm font-medium transition ${
              active ? 'bg-ink text-white' : 'text-soy hover:bg-ink/5 hover:text-ink'
            }`}
          >
            {option.label}
            {option.count !== undefined && (
              <span className={`ml-1.5 tnum ${active ? 'text-white/60' : 'text-soy/70'}`}>
                {option.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

/**
 * A bar chart drawn as bars, not as a line.
 *
 * Daily takings at a shop are counts of separate days, and a line between two
 * of them draws a trend through hours that never happened.
 */
export function DayBars({
  points,
  format,
}: {
  points: { day: string; revenue: number; orders: number }[];
  format: (value: number) => string;
}) {
  const peak = Math.max(1, ...points.map((point) => point.revenue));

  return (
    <div className="flex h-40 items-end gap-[3px]">
      {points.map((point) => {
        const height = (point.revenue / peak) * 100;
        const date = new Date(`${point.day}T00:00:00`);
        return (
          <div key={point.day} className="group relative flex h-full flex-1 items-end">
            <div
              className={`w-full rounded-t-[3px] transition-colors ${
                point.revenue > 0 ? 'bg-chilli/[0.85] group-hover:bg-chilli' : 'bg-ink/[0.08]'
              }`}
              style={{ height: `${Math.max(height, point.revenue > 0 ? 3 : 2)}%` }}
            />
            <div className="pointer-events-none absolute bottom-full left-1/2 z-10 mb-1 hidden -translate-x-1/2 whitespace-nowrap rounded-lg bg-ink px-2 py-1 text-2xs text-white shadow-pop group-hover:block">
              <span className="font-mono tnum">{format(point.revenue)}</span>
              <span className="text-white/60">
                {' '}
                · {point.orders} order{point.orders === 1 ? '' : 's'} ·{' '}
                {date.toLocaleDateString([], { day: 'numeric', month: 'short' })}
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

/** A proportional bar for a share of a whole — a status mix, a top seller. */
export function ShareBar({
  value,
  total,
  tone = 'bg-ink',
}: {
  value: number;
  total: number;
  tone?: string;
}) {
  const percent = total > 0 ? Math.max(2, (value / total) * 100) : 0;
  return (
    <span className="block h-1.5 w-full overflow-hidden rounded-full bg-ink/[0.08]">
      <span className={`block h-full rounded-full ${tone}`} style={{ width: `${percent}%` }} />
    </span>
  );
}

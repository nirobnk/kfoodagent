'use client';

import { heatScores } from '@/lib/crm';
import type { CustomerStats } from '@/lib/types';

/**
 * The heat scale, borrowed off the front of the pack.
 *
 * Every ramen sleeve on this shop's shelf prints a five-segment chilli scale,
 * and staff read it a hundred times a day without thinking. The same scale
 * carries the three things worth knowing about a customer: how lately they
 * ordered, how often, and how much. Three bars, five segments, no legend
 * needed after the first time someone points at it.
 *
 * The scores come from backend/crm.py, which computes them from the orders —
 * so a bar that looks wrong can always be traced to the orders behind it.
 */
export function HeatBars({
  stats,
  size = 'sm',
  showKeys = true,
}: {
  stats: CustomerStats;
  size?: 'sm' | 'lg';
  showKeys?: boolean;
}) {
  const segment = size === 'lg' ? 'h-2.5 w-4' : 'h-1.5 w-2.5';
  const gap = size === 'lg' ? 'gap-1' : 'gap-[2px]';

  return (
    <div
      className={
        size === 'lg'
          ? // Three wide groups do not fit a phone on one line, and a clipped
            // M bar is worse than a wrapped one.
            'flex flex-wrap gap-x-5 gap-y-2'
          : showKeys
            ? 'flex gap-3'
            : 'flex gap-2.5'
      }
    >
      {heatScores(stats).map(({ key, score, label }) => (
        <div key={key} className="flex items-center gap-1.5" title={`${label}: ${score} of 5`}>
          {showKeys && (
            <span
              className={`font-mono uppercase text-soy ${
                size === 'lg' ? 'text-xs' : 'text-2xs'
              }`}
            >
              {key}
            </span>
          )}
          <span className={`flex ${gap}`} role="img" aria-label={`${label}: ${score} of 5`}>
            {[1, 2, 3, 4, 5].map((step) => (
              <span
                key={step}
                className={`${segment} rounded-[2px] ${
                  step <= score ? 'bg-chilli' : 'bg-ink/10'
                }`}
              />
            ))}
          </span>
        </div>
      ))}
    </div>
  );
}

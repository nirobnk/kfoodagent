'use client';

import { useState } from 'react';
import { formatMoney, heatLabel } from '@/lib/format';
import type { ProductGroup } from '@/lib/types';

export function ProductCard({ product }: { product: ProductGroup }) {
  const [open, setOpen] = useState(false);
  const [sourceIndex, setSourceIndex] = useState(0);

  // The studio photos ship with the dashboard (public/assets/products); kfoods.lk
  // only carries the older web shots, and not for every product. Prefer ours and
  // fall back to the site, so a missing file downgrades instead of breaking.
  const sources = [
    product.image_file ? `/${product.image_file}` : null,
    product.image_url,
  ].filter((source): source is string => Boolean(source));
  const photo = sources[sourceIndex];

  return (
    <article className="overflow-hidden rounded-xl bg-white shadow-sm ring-1 ring-wa-border">
      <div className="flex aspect-[4/3] items-center justify-center bg-wa-panel">
        {photo ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            key={photo}
            src={photo}
            alt={product.product_name}
            loading="lazy"
            onError={() => setSourceIndex((index) => index + 1)}
            className="h-full w-full object-contain"
          />
        ) : (
          <span className="px-4 text-center text-xs text-wa-muted">
            {sources.length > 0 ? 'Photo failed to load' : 'Photo coming soon'}
          </span>
        )}
      </div>

      <div className="p-4">
        <div className="flex items-start gap-2">
          <div className="min-w-0">
            <h3 className="truncate font-semibold">{product.product_name}</h3>
            <p className="truncate text-xs text-wa-muted">
              {[product.brand, product.korean_name, product.pack_size].filter(Boolean).join(' · ')}
            </p>
          </div>
          {product.badge && (
            <span className="ml-auto shrink-0 rounded-full bg-emerald-100 px-2 py-0.5 text-[11px] font-medium text-emerald-800">
              {product.badge}
            </span>
          )}
        </div>

        {product.heat_level !== null && product.heat_level > 0 && (
          <p className="mt-1 text-xs" title={`Heat ${product.heat_level} of 5`}>
            {heatLabel(product.heat_level)}
          </p>
        )}

        <ul className="mt-3 space-y-1 text-sm">
          {product.variants.map((variant) => (
            <li key={variant.sku} className="flex items-center gap-2">
              <span className="text-wa-muted">{variant.variant_label}</span>
              <span className="ml-auto font-medium">{formatMoney(variant.price)}</span>
              <code className="text-[10px] text-wa-muted">{variant.sku}</code>
            </li>
          ))}
        </ul>

        <button
          onClick={() => setOpen((value) => !value)}
          className="mt-3 text-xs font-medium text-wa-green hover:underline"
        >
          {open ? 'Hide details' : 'Details'}
        </button>

        {open && (
          <div className="mt-2 space-y-2 border-t border-wa-border pt-2 text-xs text-wa-muted">
            {product.short_description && <p>{product.short_description}</p>}
            {product.allergens && (
              <p>
                <span className="font-medium text-wa-text">Allergens: </span>
                {product.allergens}
              </p>
            )}
            {product.product_url && (
              <a
                href={product.product_url}
                target="_blank"
                rel="noreferrer"
                className="inline-block text-wa-green hover:underline"
              >
                Open on kfoods.lk ↗
              </a>
            )}
          </div>
        )}
      </div>
    </article>
  );
}

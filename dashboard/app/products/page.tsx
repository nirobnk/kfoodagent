'use client';

import { useEffect, useMemo, useState } from 'react';
import { createClient } from '@/lib/supabase';
import { Nav } from '@/components/Nav';
import { ProductCard } from '@/components/ProductCard';
import { groupProducts } from '@/lib/format';
import type { Product } from '@/lib/types';

/**
 * The catalogue as staff see it: the same rows, prices and allergen lines the
 * agent quotes from. If something is wrong here, it is wrong on WhatsApp too.
 */
export default function ProductsPage() {
  const [variants, setVariants] = useState<Product[]>([]);
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState<string>('All');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [email, setEmail] = useState<string | null>(null);

  useEffect(() => {
    const supabase = createClient();
    let alive = true;

    supabase.auth.getUser().then(({ data }) => alive && setEmail(data.user?.email ?? null));

    supabase
      .from('menu_items')
      .select('*')
      .order('sort_order', { ascending: true })
      .then(({ data, error: loadError }) => {
        if (!alive) return;
        if (loadError) setError(loadError.message);
        else setVariants((data ?? []) as Product[]);
        setLoading(false);
      });

    return () => {
      alive = false;
    };
  }, []);

  const products = useMemo(() => groupProducts(variants), [variants]);

  const categories = useMemo(
    () => ['All', ...new Set(products.map((p) => p.category).filter(Boolean) as string[])],
    [products],
  );

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return products.filter((product) => {
      if (category !== 'All' && product.category !== category) return false;
      if (!needle) return true;
      return [product.product_name, product.brand, product.korean_name, product.short_description]
        .filter(Boolean)
        .some((field) => String(field).toLowerCase().includes(needle));
    });
  }, [products, query, category]);

  const withoutPhoto = products.filter((product) => !product.image_file && !product.image_url).length;

  return (
    <div className="flex h-screen flex-col">
      <Nav email={email} />

      <div className="flex-1 overflow-y-auto p-4">
        <div className="mx-auto max-w-6xl">
          <div className="mb-4 flex flex-wrap items-center gap-3">
            <h1 className="text-lg font-semibold">Catalogue</h1>
            <span className="rounded-full bg-white px-3 py-1 text-sm ring-1 ring-wa-border">
              {products.length} products · {variants.length} pack sizes
            </span>
            {withoutPhoto > 0 && (
              <span
                title="These products show a placeholder on kfoods.lk"
                className="rounded-full bg-amber-100 px-3 py-1 text-sm text-amber-800"
              >
                {withoutPhoto} without a photo
              </span>
            )}

            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search product or brand"
              className="ml-auto w-full rounded-lg bg-white px-3 py-2 text-sm ring-1 ring-wa-border outline-none focus:ring-wa-green sm:w-64"
            />
          </div>

          <div className="mb-4 flex flex-wrap gap-1">
            {categories.map((option) => (
              <button
                key={option}
                onClick={() => setCategory(option)}
                className={`rounded-full px-3 py-1.5 text-sm transition ${
                  category === option
                    ? 'bg-wa-green text-white'
                    : 'bg-white ring-1 ring-wa-border hover:bg-wa-panel'
                }`}
              >
                {option}
              </button>
            ))}
          </div>

          {loading && <p className="text-sm text-wa-muted">Loading the catalogue…</p>}
          {error && <p className="rounded bg-red-50 p-3 text-sm text-red-700">{error}</p>}
          {!loading && visible.length === 0 && (
            <p className="rounded-xl bg-white p-6 text-center text-sm text-wa-muted ring-1 ring-wa-border">
              Nothing matches. If the catalogue is empty, run supabase/seed_catalog.sql.
            </p>
          )}

          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {visible.map((product) => (
              <ProductCard key={product.handle} product={product} />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

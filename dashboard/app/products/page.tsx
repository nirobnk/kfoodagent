'use client';

import { useEffect, useMemo, useState } from 'react';
import { createClient } from '@/lib/supabase';
import { Page, PageHeader } from '@/components/AppShell';
import { Icon } from '@/components/ui/Icon';
import { Empty, Loading, Problem } from '@/components/ui/Bits';
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

  useEffect(() => {
    const supabase = createClient();
    let alive = true;

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
    <Page wide>
      <PageHeader
        title="Catalogue"
        lede={`${products.length} products, ${variants.length} pack sizes${
          withoutPhoto > 0 ? ` · ${withoutPhoto} still without a photo` : ''
        }.`}
      >
        <div className="relative w-full sm:w-64">
          <Icon
            name="search"
            className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-soy"
          />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search product or brand"
            className="field pl-8"
          />
        </div>
      </PageHeader>

      <div className="mb-4 flex flex-wrap gap-1">
        {categories.map((option) => (
          <button
            key={option}
            onClick={() => setCategory(option)}
            className={`rounded-lg px-2.5 py-1.5 text-sm font-medium transition ${
              category === option ? 'bg-ink text-white' : 'text-soy hover:bg-ink/5 hover:text-ink'
            }`}
          >
            {option}
          </button>
        ))}
      </div>

      {loading && <Loading what="the catalogue" />}
      {error && <Problem>{error}</Problem>}
      {!loading && visible.length === 0 && (
        <Empty title="Nothing matches">
          Try a shorter search. If the catalogue is empty altogether, run
          supabase/seed_catalog.sql.
        </Empty>
      )}

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {visible.map((product) => (
          <ProductCard key={product.handle} product={product} />
        ))}
      </div>
    </Page>
  );
}

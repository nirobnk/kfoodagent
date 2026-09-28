"use client";

import { useMemo, useSyncExternalStore } from "react";
import { parseLines, readRaw, subscribe } from "@/lib/cart";

/* The item count on the Cart button. Prerendered as a hidden 0 — the page
   cannot know a visitor's cart — and filled in once the browser has it. */
export default function CartBadge({ skus }: { skus: string[] }) {
  const raw = useSyncExternalStore(subscribe, () => readRaw() ?? "", () => null);
  const known = useMemo(() => new Set(skus), [skus]);
  const count = raw === null ? 0 : parseLines(raw, (s) => known.has(s)).reduce((n, l) => n + l.qty, 0);
  return (
    <span className="cart-badge" data-cart-count="" hidden={count === 0}>
      {count}
    </span>
  );
}

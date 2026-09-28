"use client";

import { Fragment, useEffect, useState } from "react";

const TABS = [
  { filter: "all", label: null },
  { filter: "Instant Noodles", label: "Ramyeon packs" },
  { filter: "Cup Noodles", label: "Cup noodles" },
  { filter: "Beverages", label: "K-Drinks" },
];

/* The category chips above the home page grid. The cards themselves are
   server-rendered and never re-render, so filtering toggles their `hidden`
   attribute directly rather than shipping thirty cards to the browser as JS. */
export default function ShopFilters({ total }: { total: number }) {
  const [active, setActive] = useState("all");

  useEffect(() => {
    document.querySelectorAll<HTMLElement>("[data-category]").forEach((card) => {
      card.hidden = active !== "all" && card.getAttribute("data-category") !== active;
    });
  }, [active]);

  return (
    <div className="shop__filters" role="tablist" aria-label="Filter products">
      {TABS.map((t, i) => (
        <Fragment key={t.filter}>
          {i > 0 && " "}
          <button
            type="button"
            className={t.filter === active ? "chip is-active" : "chip"}
            data-filter={t.filter}
            role="tab"
            aria-selected={t.filter === active ? "true" : "false"}
            onClick={() => setActive(t.filter)}
          >
            {t.label ?? `All (${total})`}
          </button>
        </Fragment>
      ))}
    </div>
  );
}

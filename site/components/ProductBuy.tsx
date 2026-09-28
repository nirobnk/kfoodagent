"use client";

import { useState } from "react";
import type { Variant } from "@/lib/catalog";
import { addToCart } from "@/lib/cart";
import { fmt } from "@/lib/format";
import { track } from "@/lib/pixel";
import { toast } from "@/lib/toast";

/* The buy box on a product page: pick a size, pick a quantity, add. */
export default function ProductBuy({ name, pack, variants }: { name: string; pack: string; variants: Variant[] }) {
  const [sku, setSku] = useState(variants[0].sku);
  const [qty, setQty] = useState("1");
  const variant = variants.find((v) => v.sku === sku) ?? variants[0];

  const step = (by: number) => setQty(String(Math.max(1, (parseInt(qty, 10) || 1) + by)));

  const add = () => {
    const n = Math.max(1, parseInt(qty, 10) || 1);
    addToCart(variant.sku, n);
    track("AddToCart", {
      content_ids: [variant.sku],
      content_type: "product",
      content_name: name,
      contents: [{ id: variant.sku, quantity: n }],
      value: variant.price * n,
      currency: "LKR",
    });
    toast(`Added ${name} (${variant.label}) to cart.`);
  };

  return (
    <form className="pd__buy" onSubmit={(e) => e.preventDefault()}>
      <fieldset className="pd__variants">
        <legend className="pd__legend">Choose your size</legend>
        {variants.map((v) => (
          <label key={v.sku} className={v.sku === sku ? "pd__variant is-active" : "pd__variant"}>
            <input type="radio" name="pd-variant" value={v.sku} checked={v.sku === sku} onChange={() => setSku(v.sku)} />{" "}
            <span className="pd__variant-label">{v.label}</span>{" "}
            <span className="pd__variant-units">{v.units > 1 ? `${v.units} × ${pack}` : pack}</span>{" "}
            <span className="pd__variant-price">{fmt(v.price)}</span>
          </label>
        ))}
      </fieldset>

      <div className="pd__buyrow">
        <div className="pd__qty">
          <button type="button" className="qty__btn" data-qty-step="-1" aria-label="Decrease quantity" onClick={() => step(-1)}>
            −
          </button>{" "}
          <input
            id="pd-qty"
            type="number"
            min="1"
            value={qty}
            inputMode="numeric"
            aria-label="Quantity"
            onChange={(e) => setQty(e.target.value)}
          />{" "}
          <button type="button" className="qty__btn" data-qty-step="1" aria-label="Increase quantity" onClick={() => step(1)}>
            +
          </button>
        </div>{" "}
        <button
          id="pd-add"
          type="button"
          className="btn btn--red pd__add"
          data-add-sku={variant.sku}
          data-use-qty=""
          data-cart-href="/cart.html"
          onClick={add}
        >
          Add to cart — <span id="pd-price">{fmt(variant.price)}</span>
        </button>
      </div>
      <p className="pd__minnote">No minimum order · Free delivery on orders over LKR 5,000.</p>
    </form>
  );
}

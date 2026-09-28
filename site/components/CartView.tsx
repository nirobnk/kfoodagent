"use client";

import { useEffect, useMemo, useRef, useSyncExternalStore } from "react";
import { FREE_DELIVERY_OVER, type CartItem } from "@/lib/catalog";
import {
  detailed, orderMessage, parseLines, readRaw, subscribe, totals, whatsappUrl, writeLines,
  type DeliveryDetails, type Line,
} from "@/lib/cart";
import { fmt } from "@/lib/format";
import { track } from "@/lib/pixel";

const DISTRICTS = [
  "Ampara", "Anuradhapura", "Badulla", "Batticaloa", "Colombo", "Galle", "Gampaha",
  "Hambantota", "Jaffna", "Kalutara", "Kandy", "Kegalle", "Kilinochchi", "Kurunegala",
  "Mannar", "Matale", "Matara", "Monaragala", "Mullaitivu", "Nuwara Eliya", "Polonnaruwa",
  "Puttalam", "Ratnapura", "Trincomalee", "Vavuniya",
];

/* The cart page below its heading. Prerendered with both the empty state and
   the summary hidden — the page cannot know a visitor's cart — and filled in
   once the browser has read it. */
export default function CartView({ index, whatsapp }: { index: Record<string, CartItem>; whatsapp: string }) {
  const raw = useSyncExternalStore(subscribe, () => readRaw() ?? "", () => null);
  const loaded = raw !== null;
  const lines = useMemo(() => parseLines(raw, (s) => s in index), [raw, index]);
  const det = detailed(lines, index);
  const t = totals(det);
  const empty = t.itemCount === 0;

  /* InitiateCheckout, once per page view, the first time the cart has items */
  const checkoutTracked = useRef(false);
  useEffect(() => {
    if (!loaded || checkoutTracked.current || t.itemCount === 0) return;
    checkoutTracked.current = true;
    track("InitiateCheckout", {
      num_items: t.itemCount,
      value: t.total,
      currency: "LKR",
      content_type: "product",
      contents: det.map((d) => ({ id: d.sku, quantity: d.qty })),
    });
  });

  const setQty = (sku: string, qty: number) =>
    writeLines(lines.map((l): Line => (l.sku === sku ? { ...l, qty } : l)).filter((l) => l.qty > 0));
  const remove = (sku: string) => writeLines(lines.filter((l) => l.sku !== sku));

  const checkout = (ev: React.FormEvent<HTMLFormElement>) => {
    ev.preventDefault();
    if (empty) return;
    const form = ev.currentTarget;
    const v = (id: string) => {
      const el = form.querySelector<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>(`#${id}`);
      return el ? (el.value || "").trim() : "";
    };
    const pay = form.querySelector<HTMLInputElement>("input[name='f-pay']:checked");
    const details: DeliveryDetails = {
      name: v("f-name"), phone: v("f-phone"), address: v("f-address"), city: v("f-city"),
      district: v("f-district"), postal: v("f-postal"), notes: v("f-notes"),
      pay: pay ? pay.value : "Bank Transfer",
    };

    /* Lead, not Purchase: the order is not confirmed or paid until the
       bank transfer lands. */
    track("Lead", { value: t.total, currency: "LKR", content_name: "WhatsApp order sent" });
    track("WhatsAppOrderSubmitted", { value: t.total, currency: "LKR", num_items: t.itemCount }, true);

    window.location.href = whatsappUrl(whatsapp, orderMessage(det, t, details));
  };

  return (
    <>
      <div id="cart-empty" className="cart-empty" hidden={!loaded || !empty}>
        <p>Your cart is empty — the ramyeon shelf is this way.</p>
        <a className="btn btn--red" href="/#shop">Browse the shop</a>
      </div>

      <div id="cart-summary" className="cart-layout" hidden={!loaded || empty}>
        <section className="cart-list" aria-label="Cart items">
          <ul id="cart-lines" className="clines">
            {det.map((d) => (
              <li key={d.sku} className="cline">
                <a className="cline__media" href={`/products/${d.item.handle}.html`}>
                  {/* eslint-disable-next-line @next/next/no-img-element -- plain <img>, as on every page */}
                  <img src={`/${d.item.image}`} alt="" width={72} height={72} loading="lazy" />
                </a>
                <div className="cline__info">
                  <a className="cline__name" href={`/products/${d.item.handle}.html`}>{d.item.name}</a>
                  <p className="cline__meta">{d.item.label} · {fmt(d.item.price)}</p>
                  <button className="cline__remove" type="button" onClick={() => remove(d.sku)}>Remove</button>
                </div>
                <div className="cline__qty">
                  <button type="button" className="qty__btn" data-step="-1" aria-label="Decrease quantity" onClick={() => setQty(d.sku, d.qty - 1)}>−</button>
                  <span className="qty__num" aria-live="polite">{d.qty}</span>
                  <button type="button" className="qty__btn" data-step="1" aria-label="Increase quantity" onClick={() => setQty(d.sku, d.qty + 1)}>+</button>
                </div>
                <p className="cline__total">{fmt(d.lineTotal)}</p>
              </li>
            ))}
          </ul>

          <dl className="cart-sums">
            <div className="cart-sums__row">
              <dt>
                Subtotal{" "}
                <span className="cart-sums__count" id="cart-items">
                  {loaded ? `(${t.itemCount}${t.itemCount === 1 ? " item)" : " items)"}` : "(0 items)"}
                </span>
              </dt>
              <dd id="cart-subtotal">{fmt(t.amount)}</dd>
            </div>
            <div className="cart-sums__row">
              <dt>Delivery</dt>
              <dd id="cart-delivery" className={loaded && t.delivery === 0 ? "is-free" : undefined}>
                {!loaded ? "LKR 400" : t.delivery === 0 ? "Free" : fmt(t.delivery)}
              </dd>
            </div>
            <div className="cart-sums__row cart-sums__row--total">
              <dt>Total</dt>
              <dd id="cart-total">{fmt(t.total)}</dd>
            </div>
          </dl>
          <p className="cart-shipnote" id="cart-shipnote">
            {!loaded
              ? "Delivery is a flat LKR 400 island-wide, free on orders over LKR 5,000."
              : t.delivery === 0
                ? `✓ Free delivery — your order is over ${fmt(FREE_DELIVERY_OVER)}.`
                : `Add ${fmt(FREE_DELIVERY_OVER - t.amount)} more to get free delivery.`}
          </p>
        </section>

        <section className="checkout" aria-label="Delivery details">
          <h2 className="checkout__title">Delivery details</h2>
          <form id="checkout-form" className="checkout__form" onSubmit={checkout}>
            <div className="field-row">
              <label className="field">
                <span className="field__label">Full name *</span>{" "}
                <input id="f-name" type="text" required autoComplete="name" placeholder="Your name" />
              </label>{" "}
              <label className="field">
                <span className="field__label">Phone (WhatsApp) *</span>{" "}
                <input id="f-phone" type="tel" required autoComplete="tel" placeholder="07X XXX XXXX" pattern="[0-9+ ]{9,15}" />
              </label>
            </div>
            <label className="field">
              <span className="field__label">Address *</span>{" "}
              <input id="f-address" type="text" required autoComplete="street-address" placeholder="House no & street" />
            </label>
            <div className="field-row">
              <label className="field">
                <span className="field__label">City / town *</span>{" "}
                <input id="f-city" type="text" required autoComplete="address-level2" placeholder="e.g. Colombo" />
              </label>{" "}
              <label className="field">
                <span className="field__label">District *</span>{" "}
                <select id="f-district" required defaultValue="">
                  <option value="" disabled>Select district</option>
                  {DISTRICTS.map((d) => <option key={d}>{d}</option>)}
                </select>
              </label>
            </div>

            <label className="field">
              <span className="field__label">Postal code (optional)</span>{" "}
              <input id="f-postal" type="text" autoComplete="postal-code" inputMode="numeric" placeholder="e.g. 60000" pattern="[0-9]{4,5}" />
            </label>

            <fieldset className="field pay">
              <legend className="field__label">Payment method *</legend>
              <div className="pay__opts">
                {/* Cash on delivery is hidden for now — restore this line and drop the
                    `defaultChecked` below to bring it back:
                <label className="pay__opt"><input type="radio" name="f-pay" value="Cash on Delivery" defaultChecked /> <span>Cash on delivery</span></label>
                */}
                <label className="pay__opt"><input type="radio" name="f-pay" value="Bank Transfer" defaultChecked /> <span>Bank transfer</span></label>
              </div>

              <div className="bank">
                <p className="bank__lead">Transfer the total to:</p>
                <dl className="bank__rows">
                  <div className="bank__row"><dt>Bank</dt><dd>Hatton National Bank (HNB)</dd></div>
                  <div className="bank__row"><dt>Branch</dt><dd>Alawwa</dd></div>
                  <div className="bank__row"><dt>Account name</dt><dd>Kumarasinghe H G B N</dd></div>
                  <div className="bank__row"><dt>Account no.</dt><dd><span className="bank__acc">123020163895</span></dd></div>
                </dl>
                <p className="bank__note">Pay once we confirm your total on WhatsApp, then send us the receipt in the same chat.</p>
              </div>
            </fieldset>

            <label className="field">
              <span className="field__label">Notes (optional)</span>{" "}
              <textarea id="f-notes" rows={2} placeholder="Landmark, delivery time, etc."></textarea>
            </label>

            <button id="checkout-btn" type="submit" className="btn btn--red checkout__btn" disabled={empty} aria-disabled={empty ? "true" : "false"}>
              <span>Checkout on WhatsApp</span>
              <span className="checkout__btn-total" id="checkout-btn-total">{loaded && !empty ? fmt(t.total) : ""}</span>
            </button>
            <p className="checkout__note">
              Checkout opens WhatsApp with your order pre-filled — nothing is charged
              on this website. We confirm stock and the delivery date, then you transfer
              the total to the account above and send us the receipt.
            </p>
          </form>
        </section>
      </div>
    </>
  );
}

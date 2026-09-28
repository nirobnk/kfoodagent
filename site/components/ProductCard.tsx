import { fullName, src, thumb, type Product } from "@/lib/catalog";
import { fmt } from "@/lib/format";
import AddToCartButton from "./AddToCartButton";

export function Heat({ heat }: { heat?: number | null }) {
  if (heat === null || heat === undefined) return null;
  if (heat === 0) return <p className="pcard__heat pcard__heat--none">Not spicy · kid friendly</p>;
  return (
    <p className="pcard__heat" aria-label={`Heat level ${heat} of 5`}>
      <span>{"🌶".repeat(heat)}</span>
      {heat < 5 && <span className="card__heat-dim">{"🌶".repeat(5 - heat)}</span>}
    </p>
  );
}

function Price({ amount }: { amount: number }) {
  return (
    <p className="pcard__price">
      <span className="pcard__from">From</span>{" "}
      <span className="pcard__amount">{fmt(amount)}</span>
    </p>
  );
}

/* A card in the home page grid. */
export default function ProductCard({ p }: { p: Product }) {
  const v0 = p.variants[0];
  const alt = `${fullName(p)} ${p.pack}${p.category === "Beverages" ? "" : " pack"} — buy online in Sri Lanka`;
  const href = `/products/${p.handle}.html`;
  return (
    <article className="pcard reveal" data-category={p.category}>
      <a className="pcard__media" href={href} tabIndex={-1} aria-hidden="true">
        {/* eslint-disable-next-line @next/next/no-img-element -- plain <img>: indexed URLs must not change */}
        <img src={src(thumb(p.image))} alt={alt} width={450} height={450} loading="lazy" decoding="async" />{" "}
        {p.badge && <span className="pcard__badge">{p.badge}</span>}
      </a>
      <div className="pcard__body">
        <p className="pcard__brand">{p.brand} · {p.pack}</p>
        <h3 className="pcard__name"><a href={href}>{p.name}</a></h3>
        <Heat heat={p.heat} />
        <div className="pcard__buy">
          <Price amount={v0.price} />{" "}
          <AddToCartButton
            className="btn btn--tiny btn--red pcard__add"
            sku={v0.sku}
            name={p.name}
            label={v0.label}
            price={v0.price}
          >
            Add to cart
          </AddToCartButton>
        </div>
      </div>
    </article>
  );
}

/* "You might also like" on a product page: no heat, no badge, no button. */
export function RelatedCard({ p }: { p: Product }) {
  return (
    <article className="pcard">
      <a className="pcard__media" href={`/products/${p.handle}.html`} tabIndex={-1} aria-hidden="true">
        {/* eslint-disable-next-line @next/next/no-img-element -- plain <img>: indexed URLs must not change */}
        <img src={src(thumb(p.image))} alt={fullName(p)} width={450} height={450} loading="lazy" decoding="async" />
      </a>
      <div className="pcard__body">
        <p className="pcard__brand">{p.brand} · {p.pack}</p>
        <h3 className="pcard__name"><a href={`/products/${p.handle}.html`}>{p.name}</a></h3>
        <div className="pcard__buy">
          <Price amount={p.variants[0].price} />
        </div>
      </div>
    </article>
  );
}

import { allSkus } from "@/lib/catalog";
import CartBadge from "./CartBadge";

/* The home page links to its own sections; every other page links back to them. */
export default function SiteHeader({ home = false, current }: { home?: boolean; current?: "price" | "cart" }) {
  const at = (hash: string) => (home ? hash : `/${hash}`);
  return (
    <header className="nav" id={home ? "top" : undefined}>
      <a className="nav__brand" href="/" aria-label="K FOOD Sri Lanka — home">
        <span className="nav__k">K</span>{" "}
        <span className="nav__brand-text">
          <span className="nav__food">fOOD</span>{" "}
          <span className="nav__tag">Taste of Korean Food</span>
        </span>
      </a>{" "}
      <nav className="nav__links" aria-label="Main">
        <a href={at("#shop")}>Shop</a>{" "}
        <a href="/korean-ramen-price-sri-lanka.html" aria-current={current === "price" ? "page" : undefined}>
          Price list
        </a>{" "}
        <a href={at("#how")}>How to order</a>{" "}
        <a href={at("#faq")}>FAQ</a>{" "}
        <a href={at("#contact")}>Contact</a>
      </nav>{" "}
      <a className="btn btn--nav btn--cart" href="/cart.html" aria-current={current === "cart" ? "page" : undefined}>
        Cart <CartBadge skus={allSkus()} />
      </a>
    </header>
  );
}

import { Fragment } from "react";
import { WHATSAPP } from "@/lib/catalog";

type FooterLink = "shop" | "prices" | "cart" | "faq" | "whatsapp";

/* Pages list different footer links; `links` keeps each page's set as it was. */
export default function SiteFooter({ home = false, links }: { home?: boolean; links: FooterLink[] }) {
  const at = (hash: string) => (home ? hash : `/${hash}`);
  const items: Record<FooterLink, React.ReactNode> = {
    shop: <a href={at("#shop")}>Shop Korean ramen</a>,
    prices: <a href="/korean-ramen-price-sri-lanka.html">Ramen price list</a>,
    cart: <a href="/cart.html">Cart</a>,
    faq: <a href={at("#faq")}>Delivery FAQ</a>,
    whatsapp: (
      <a href={`https://wa.me/${WHATSAPP}`} target="_blank" rel="noopener">
        WhatsApp us
      </a>
    ),
  };
  return (
    <footer className="footer">
      <div className="footer__brand">
        <span className="footer__k">K</span>{" "}
        <span className="footer__food">fOOD</span>
      </div>
      <p className="footer__tag">Taste of Korean Food · Sri Lanka</p>
      <p className="footer__links">
        {links.map((key, i) => (
          <Fragment key={key}>
            {i > 0 && " · "}
            {items[key]}
          </Fragment>
        ))}
      </p>
      <p className="footer__legal">© 2026 K FOOD (kfoods.lk) · Online Korean food store · Sri Lanka · Island-wide delivery.</p>
    </footer>
  );
}

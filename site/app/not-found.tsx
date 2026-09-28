import SiteFooter from "@/components/SiteFooter";
import SiteHeader from "@/components/SiteHeader";

/* Exported as out/404.html, which Netlify serves for any unknown URL with a
   404 status. Next marks it noindex. Built only from the cart page's styles,
   so a customer who follows a dead link still lands in the shop. */
export default function NotFound() {
  return (
    <>
      <title>Page not found — K FOOD Sri Lanka</title>
      <SiteHeader />
      <main className="cartpage">
        <div className="section__head">
          <p className="eyebrow"><span lang="ko">404</span> Not found</p>
          <h1 className="section__title">That page isn&apos;t on the shelf</h1>
        </div>
        <div className="cart-empty">
          <p>The link may be old, or the product may have moved.</p>
          <a className="btn btn--red" href="/#shop">Browse the shop</a>
        </div>
      </main>
      <SiteFooter links={["shop", "prices", "cart", "whatsapp"]} />
    </>
  );
}

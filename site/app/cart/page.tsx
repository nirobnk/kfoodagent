import CartView from "@/components/CartView";
import PageHead from "@/components/PageHead";
import SiteFooter from "@/components/SiteFooter";
import SiteHeader from "@/components/SiteHeader";
import { SITE, WHATSAPP, cartIndex } from "@/lib/catalog";

export default function CartPage() {
  return (
    <>
      <PageHead
        title="Your Cart — K FOOD Sri Lanka | kfoods.lk"
        description="Review your Korean ramen order and check out via WhatsApp. No minimum order — island-wide delivery across Sri Lanka, pay by bank transfer."
        canonical={`${SITE}/cart.html`}
        robots="noindex, follow"
        appleIcon={false}
      />

      <SiteHeader current="cart" />

      <main className="cartpage" id="cart-root">
        <div className="section__head">
          <p className="eyebrow"><span lang="ko">장바구니</span> Your cart</p>
          <h1 className="section__title">Almost at your door</h1>
        </div>

        <CartView index={cartIndex()} whatsapp={WHATSAPP} />
      </main>

      <SiteFooter links={["shop", "prices", "faq", "whatsapp"]} />
    </>
  );
}

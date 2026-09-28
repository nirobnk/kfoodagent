import { Fragment } from "react";
import JsonLd from "@/components/JsonLd";
import PageHead from "@/components/PageHead";
import ProductCard from "@/components/ProductCard";
import RevealOnScroll from "@/components/RevealOnScroll";
import ShopFilters from "@/components/ShopFilters";
import SiteFooter from "@/components/SiteFooter";
import SiteHeader from "@/components/SiteHeader";
import { DELIVERY_FEE, FREE_DELIVERY_OVER, PRODUCTS, SITE, WHATSAPP } from "@/lib/catalog";
import { fmt } from "@/lib/format";
import { shopItemListLd, siteGraphLd } from "@/lib/seo";

const TICKER: { text: string; ko?: boolean }[] = [
  { text: "Island-wide delivery" },
  { text: "라면", ko: true },
  { text: "Shin Ramyun" },
  { text: "신라면", ko: true },
  { text: "Hot Dak fire noodles" },
  { text: "핫닭", ko: true },
  { text: "K-Drinks" },
];

function TickerGroup() {
  return (
    <span className="ticker__group">
      {TICKER.map((t, i) => (
        <Fragment key={t.text}>
          {i > 0 && " "}
          <span lang={t.ko ? "ko" : undefined}>{t.text}</span>
          <span className="ticker__dot">●</span>
        </Fragment>
      ))}
    </span>
  );
}

export default function Home() {
  const shin = PRODUCTS.find((p) => p.handle === "shin-ramyun")!;
  const packSingles = PRODUCTS.filter((p) => p.category === "Instant Noodles").map((p) => p.variants[0].price);
  const fee = fmt(DELIVERY_FEE);
  const freeOver = fmt(FREE_DELIVERY_OVER);

  return (
    <>
      <PageHead
        title="Buy Korean Ramen Online in Sri Lanka | K FOOD"
        description="Shop Korean ramen online in Sri Lanka from LKR 560. Compare Shin Ramyun, spicy noodle and cup noodle prices, with island-wide delivery from K FOOD."
        canonical={`${SITE}/`}
        robots="index, follow, max-image-preview:large"
        og={{
          type: "website",
          title: "Buy Korean Ramen Online in Sri Lanka | K FOOD",
          description: "Compare Korean ramen prices and order Shin Ramyun, spicy noodles and cup noodles for island-wide delivery in Sri Lanka.",
          url: `${SITE}/`,
          image: `${SITE}/images/og-cover.jpg`,
          imageWidth: 1200,
          imageHeight: 669,
          imageType: "image/jpeg",
          locale: "en_LK",
        }}
        twitter={{
          title: "Buy Korean Ramen Online in Sri Lanka | K FOOD",
          description: "Compare Korean ramen prices and order Shin Ramyun, spicy noodles and cup noodles for island-wide delivery in Sri Lanka.",
          image: `${SITE}/images/og-cover.jpg`,
        }}
      />
      <JsonLd data={siteGraphLd()} />

      <SiteHeader home />

      <main>
        {/* ============ HERO ============ */}
        <section className="hero">
          <div className="hero__inner">
            <div className="hero__copy">
              <p className="hero__eyebrow"><span lang="ko">라면</span> · Korean food store · Sri Lanka</p>
              <h1 className="hero__title">
                Buy Korean ramen<br />{"\n"}
                <em>online in Sri Lanka.</em>
              </h1>
              <p className="hero__sub">
                Buy Korean ramen online at the best price in Sri Lanka —
                Shin Ramyun, Hot Dak fire noodles, cup ramyeon and K-drinks,
                straight from Korea to your door, anywhere in the island.
                Order online, confirm on WhatsApp, pay by bank transfer.
              </p>
              <div className="hero__actions">
                <a className="btn btn--solid" href="#shop">Shop the range</a>{" "}
                <a className="btn btn--ghost" href="/korean-ramen-price-sri-lanka.html">View ramen prices</a>
              </div>
              <p className="hero__note">No minimum order · Delivery to all 25 districts</p>
            </div>

            <div className="hero__visual" aria-hidden="true">
              {/* eslint-disable @next/next/no-img-element -- plain <img>: indexed URLs must not change */}
              <img className="hero__img" src="/images/hero-ramen.webp" alt="" width={900} height={490} fetchPriority="high" />{" "}
              <img className="hero__product hero__product--pack" src="/images/shin-pack-cutout.webp" alt="" decoding="async" fetchPriority="low" />{" "}
              <img className="hero__product hero__product--cup" src="/images/shin-cup-cutout.webp" alt="" decoding="async" fetchPriority="low" />
              {/* eslint-enable @next/next/no-img-element */}
            </div>
          </div>
        </section>

        {/* ============ TICKER ============ */}
        <div className="ticker" aria-hidden="true">
          <div className="ticker__track">
            <TickerGroup />{" "}
            <TickerGroup />
          </div>
        </div>

        {/* ============ SHOP ============ */}
        <section className="shop" id="shop">
          <div className="section__head reveal">
            <p className="eyebrow"><span lang="ko">메뉴</span> The shop</p>
            <h2 className="section__title">Korean ramen and noodle prices in Sri Lanka</h2>
            <p className="section__lead">
              Compare current prices for Shin Ramyun, spicy Korean noodles, cup noodles
              and K-drinks. Choose a single pack, 5 Pack or carton with no minimum order.{" "}
              <a href="/korean-ramen-price-sri-lanka.html">See the full Korean ramen price list</a>.
            </p>
          </div>

          <ShopFilters total={PRODUCTS.length} />

          <JsonLd data={shopItemListLd()} />
          <div className="shop__grid">
            {PRODUCTS.map((p) => <ProductCard key={p.handle} p={p} />)}
          </div>

          <p className="shop__note reveal">
            All prices in Sri Lankan rupees. Ingredients, allergens and nutrition
            are listed on each product page.
          </p>
        </section>

        {/* ============ HOW TO ORDER ============ */}
        <section className="how" id="how">
          <div className="section__head reveal">
            <p className="eyebrow"><span lang="ko">방법</span> How to order</p>
            <h2 className="section__title">From our shelf to your door</h2>
            <p className="section__lead">
              No card, no sign-up. Your cart becomes a WhatsApp message and we
              take it from there.
            </p>
          </div>

          <ol className="steps">
            <li className="step reveal">
              <span className="step__num">1</span>
              <h3 className="step__title">Fill your cart</h3>
              <p className="step__text">Pick whatever you like — singles, 5 Packs, cartons or drinks. No minimum order.</p>
            </li>
            <li className="step reveal">
              <span className="step__num">2</span>
              <h3 className="step__title">Add your address</h3>
              <p className="step__text">Enter your name, phone and delivery address at checkout. Anywhere in Sri Lanka.</p>
            </li>
            <li className="step reveal">
              <span className="step__num">3</span>
              <h3 className="step__title">Send on WhatsApp</h3>
              <p className="step__text">Checkout opens WhatsApp with your order ready to send. We confirm stock and delivery.</p>
            </li>
            <li className="step reveal">
              <span className="step__num">4</span>
              <h3 className="step__title">Pay &amp; receive</h3>
              <p className="step__text">Pay by bank transfer once we confirm the total — our account details are on the checkout page. Your ramyeon is on its way.</p>
            </li>
          </ol>
        </section>

        {/* ============ DELIVERY ============ */}
        <section className="opening" id="delivery">
          <div className="opening__inner opening__inner--single">
            <div className="opening__copy reveal">
              <p className="eyebrow eyebrow--light"><span lang="ko">배송</span> Delivery</p>
              <h2 className="opening__date">All 25 districts</h2>
              <p className="opening__text">
                Colombo to Jaffna, Galle to Trincomalee — every order is confirmed
                on WhatsApp, packed and couriered island-wide. Stock up with
                5 Packs and cartons for the best per-pack prices.
              </p>
              <p className="opening__free">🚚 Flat {fee} courier · 2–4 days · free over {freeOver}</p>
              <a className="btn btn--gold" href="#shop">Start your order</a>
            </div>
          </div>
        </section>

        {/* ============ FAQ ============ */}
        {/* Every answer here has a twin in siteGraphLd() — Google requires the
            visible FAQ and the FAQPage markup to say the same thing. */}
        <section className="faq" id="faq">
          <div className="section__head reveal">
            <p className="eyebrow"><span lang="ko">질문</span> FAQ</p>
            <h2 className="section__title">Ordering Korean food in Sri Lanka</h2>
          </div>

          <div className="faq__list">
            <details className="faq__item reveal">
              <summary>Where does K FOOD deliver?</summary>
              <p>Everywhere in Sri Lanka. Whether you&apos;re in Colombo, Kandy, Galle, Kurunegala, Gampaha, Malabe, Kegalle, Matara, Anuradhapura or Jaffna — we courier to all 25 districts. Courier is a <strong>flat {fee}</strong> island-wide and <strong>free on orders over {freeOver}</strong>. Most orders arrive in <strong>2–4 days</strong>.</p>
            </details>
            <details className="faq__item reveal">
              <summary>Is there a minimum order?</summary>
              <p><strong>No minimum</strong> — order as much or as little as you like, from a single pack or one drink to a full carton. Delivery is flat <strong>{fee}</strong> island-wide and <strong>free over {freeOver}</strong>.</p>
            </details>
            <details className="faq__item reveal">
              <summary>How do I pay?</summary>
              <p>After you send your order on WhatsApp we confirm the total, then you pay by <strong>bank transfer</strong> to <strong>Hatton National Bank (HNB)</strong>, <strong>Alawwa</strong> branch, account name <strong>Kumarasinghe H G B N</strong>, account number <strong>123020163895</strong>. Send us the receipt on WhatsApp and we dispatch. There&apos;s no online card payment at this stage.</p>
            </details>
            <details className="faq__item reveal">
              <summary>What if something arrives damaged?</summary>
              <p>Message us on WhatsApp within <strong>7 days</strong> of delivery. If an item is damaged, expired or wrong, we collect it at our cost and send a replacement or a <strong>full refund</strong>. Unopened items in original condition can be returned in the same window; opened food packs can&apos;t be returned, for food-safety reasons.</p>
            </details>
            <details className="faq__item reveal">
              <summary>Are these the real Korean products?</summary>
              <p>Yes — genuine Nongshim, Migawon, Binggrae and OKF products imported from South Korea. Every product page lists the pack&apos;s ingredients and allergens.</p>
            </details>
            <details className="faq__item reveal">
              <summary>What is the Shin Ramyun price in Sri Lanka at K FOOD?</summary>
              <p><strong>Shin Ramyun Original 120g is {fmt(shin.variants[0].price)}</strong> per pack, {fmt(shin.variants[1].price)} for a 5 Pack and {fmt(shin.variants[2].price)} for a 20-pack carton at kfoods.lk. Most Korean ramen packs here are {fmt(Math.min(...packSingles))}–{Math.max(...packSingles).toLocaleString("en-LK")}, and every product page lists the best price for singles, 5 Packs and cartons.</p>
            </details>
            <details className="faq__item reveal">
              <summary>Is kfoods.lk an online-only store?</summary>
              <p>Yes — kfoods.lk is an <strong>online Korean food store</strong> for Sri Lanka. You order on the website, confirm on WhatsApp (<strong>077 295 3107</strong>) and we courier your ramyeon and drinks to your door, anywhere on the island.</p>
            </details>
          </div>
        </section>

        {/* ============ CONTACT ============ */}
        <section className="visit" id="contact">
          <div className="section__head reveal">
            <p className="eyebrow"><span lang="ko">연락</span> Contact</p>
            <h2 className="section__title">Talk to K FOOD</h2>
          </div>

          <div className="visit__grid">
            <div className="visit__block reveal">
              <h3 className="visit__label">WhatsApp</h3>
              <p className="visit__value visit__value--mono">
                <a href={`https://wa.me/${WHATSAPP}`} target="_blank" rel="noopener">077 295 3107</a>
              </p>
              <p className="visit__value">Orders, stock checks and delivery questions — the fastest way to reach us.</p>
            </div>
            <div className="visit__block reveal">
              <h3 className="visit__label">Email</h3>
              <p className="visit__value visit__value--mono">
                <a href="mailto:kfoodslk@gmail.com">kfoodslk@gmail.com</a>
              </p>
              <p className="visit__value">We reply to email within one working day.</p>
            </div>
            <div className="visit__block reveal">
              <h3 className="visit__label">Follow us</h3>
              <p className="visit__value">New arrivals and restocks land on our socials first.</p>
              <div className="visit__social">
                <a href="https://web.facebook.com/kfoodslk" target="_blank" rel="noopener" aria-label="K FOOD on Facebook">Facebook</a>{" "}
                <a href="https://www.instagram.com/kfoodslk/" target="_blank" rel="noopener" aria-label="K FOOD on Instagram">Instagram</a>{" "}
                <a href="https://www.tiktok.com/@kfoodslk" target="_blank" rel="noopener" aria-label="K FOOD on TikTok">TikTok</a>
              </div>
            </div>
          </div>
        </section>
      </main>

      <SiteFooter home links={["shop", "prices", "cart", "faq", "whatsapp"]} />
      <RevealOnScroll />
    </>
  );
}

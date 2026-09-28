import { Fragment } from "react";
import AddToCartButton from "@/components/AddToCartButton";
import JsonLd from "@/components/JsonLd";
import PageHead from "@/components/PageHead";
import SiteFooter from "@/components/SiteFooter";
import SiteHeader from "@/components/SiteHeader";
import { PRODUCTS, SITE, fullName, getProduct, isNoodle } from "@/lib/catalog";
import { fmt } from "@/lib/format";
import { priceBreadcrumbLd, priceItemListLd } from "@/lib/seo";

/* The date the prices were published — the build date, as it always was. */
const TODAY = new Date().toISOString().slice(0, 10);

export default function PricePage() {
  const noodles = PRODUCTS.filter(isNoodle);
  const instantNoodles = noodles.filter((p) => p.category === "Instant Noodles");
  const cupNoodles = noodles.filter((p) => p.category === "Cup Noodles");
  const lowestSingle = Math.min(...noodles.map((p) => p.variants[0].price));
  const lowestPacket = Math.min(...instantNoodles.map((p) => p.variants[0].price));
  const shin = getProduct("shin-ramyun")!;
  const updated = new Date(TODAY + "T00:00:00Z").toLocaleDateString("en-LK", {
    year: "numeric", month: "long", day: "numeric", timeZone: "UTC",
  });

  return (
    <>
      <PageHead
        title="Korean Ramen Price in Sri Lanka | K FOOD Price List"
        description={`Compare Korean ramen prices in Sri Lanka from LKR ${lowestSingle.toLocaleString("en-LK")}. See current Shin Ramyun, spicy noodle, cup noodle, 5-pack and carton prices and order online.`}
        canonical={`${SITE}/korean-ramen-price-sri-lanka.html`}
        robots="index, follow, max-image-preview:large"
        og={{
          type: "website",
          title: "Korean Ramen Price in Sri Lanka | K FOOD Price List",
          description: "Compare current prices for Shin Ramyun, spicy Korean noodles, cup noodles, 5 Packs and cartons in Sri Lanka.",
          url: `${SITE}/korean-ramen-price-sri-lanka.html`,
          image: `${SITE}/images/og-cover.jpg`,
          locale: "en_LK",
        }}
        twitter={{
          title: "Korean Ramen Price in Sri Lanka | K FOOD",
          description: "Compare Korean ramen and cup noodle prices, then order online for island-wide delivery.",
          image: `${SITE}/images/og-cover.jpg`,
        }}
      />
      <JsonLd data={priceItemListLd(noodles)} />
      <JsonLd data={priceBreadcrumbLd()} />

      <SiteHeader current="price" />

      <main className="pricepage">
        <nav className="pd__crumbs" aria-label="Breadcrumb">
          <a href="/">Home</a> <span aria-hidden="true">›</span> <span aria-current="page">Korean ramen prices</span>
        </nav>

        <header className="pricehero">
          <p className="eyebrow"><span lang="ko">라면 가격</span> Current price guide</p>
          <h1>Korean ramen price in Sri Lanka</h1>
          <p>Compare current K FOOD prices for authentic Korean instant ramen, spicy stir-fry noodles and cup noodles. Single cups start at {fmt(lowestSingle)}, while packet ramen starts at {fmt(lowestPacket)}. Order online and confirm stock through WhatsApp.</p>
          <div className="pricehero__actions">
            <a className="btn btn--red" href="#ramen-price-list">Compare all prices</a>{" "}
            <a className="btn btn--outline" href="/#shop">Shop with photos</a>
          </div>
        </header>

        <section className="pricefacts" aria-label="Korean ramen shop facts">
          <div><strong>{noodles.length}</strong><span>ramen choices</span></div>
          <div><strong>{fmt(lowestSingle)}</strong><span>lowest single price</span></div>
          <div><strong>LKR 400</strong><span>island-wide delivery</span></div>
          <div><strong>Free</strong><span>delivery over LKR 5,000</span></div>
        </section>

        <section className="pricecontent" id="ramen-price-list">
          <div className="section__head">
            <p className="eyebrow">Price comparison</p>
            <h2 className="section__title">Korean ramen and noodle price list</h2>
            <p className="section__lead">Prices are in Sri Lankan rupees. Select a product for ingredients, allergens, cooking directions and the full offer. Last updated <time dateTime={TODAY}>{updated}</time>.</p>
          </div>
          <div className="pricetable-wrap">
            <table className="pricetable">
              <caption>Current Korean ramen prices at K FOOD Sri Lanka</caption>
              <thead>
                <tr>
                  <th scope="col">Product</th><th scope="col">Heat</th><th scope="col">Single</th><th scope="col">5 Pack</th><th scope="col">Carton</th>
                  <th scope="col"><span className="visually-hidden">Add to cart</span></th>
                </tr>
              </thead>
              <tbody>
                {noodles.map((p) => {
                  const [single, five, carton] = p.variants;
                  return (
                    <tr key={p.handle}>
                      <th scope="row">
                        <a href={`/products/${p.handle}.html`}>{fullName(p)}</a>
                        <small>{p.pack} · {p.category}</small>
                      </th>
                      <td>{p.heat === 0 ? "Not spicy" : `${p.heat}/5`}</td>
                      <td>{fmt(single.price)}</td>
                      <td>{five ? fmt(five.price) : "—"}</td>
                      <td>{carton ? fmt(carton.price) : "—"}</td>
                      <td>
                        <AddToCartButton className="btn btn--tiny btn--red" sku={single.sku} name={p.name} label={single.label} price={single.price}>
                          Add
                        </AddToCartButton>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="price-note">Stock is confirmed on WhatsApp before payment. Product prices can change when new imported stock arrives.</p>
        </section>

        <section className="priceguide">
          <article>
            <h2>Shin Ramyun price in Sri Lanka</h2>
            <p><a href="/products/shin-ramyun.html">Nongshim Shin Ramyun Original 120g</a> is {fmt(shin.variants[0].price)} for one pack, {fmt(shin.variants[1].price)} for a 5 Pack and {fmt(shin.variants[2].price)} for a 20-pack carton. You can also compare <a href="/products/shin-ramyun-black.html">Shin Ramyun Black</a>, <a href="/products/super-spicy.html">Shin Red Super Spicy</a>, cheese and Toomba flavours.</p>
          </article>
          <article>
            <h2>Spicy Korean noodles and cheese ramen</h2>
            <p>Choose soup ramen for a rich broth or stir-fry noodles for a thicker sauce. The range includes <a href="/products/stir-fry-spicy.html">Shin Ramyun Stir Fry</a>, <a href="/products/stir-fry-cheese.html">Stir Fry Cheese</a>, <a href="/products/toomba.html">creamy Toomba</a> and Hot Dak fire noodles, with heat ratings shown on every product page.</p>
          </article>
          <article>
            <h2>Korean cup noodles in Sri Lanka</h2>
            <p>
              For a quick meal, compare{" "}
              {cupNoodles.map((p, i) => (
                <Fragment key={p.handle}>
                  {i > 0 && " and "}
                  <a href={`/products/${p.handle}.html`}>{fullName(p)} {p.pack}</a>
                </Fragment>
              ))}
              . Add hot water and they are ready in about three minutes.
            </p>
          </article>
          <article>
            <h2>How to order Korean ramen online</h2>
            <p>Add single packs, 5 Packs or cartons to your cart, enter your Sri Lankan delivery address and send the prepared order through WhatsApp. Delivery is LKR 400 to all 25 districts and free when the product subtotal reaches LKR 5,000. Payment is by bank transfer after stock is confirmed.</p>
          </article>
        </section>

        <section className="faq pricefaq">
          <div className="section__head"><p className="eyebrow">Buying questions</p><h2 className="section__title">Korean ramen prices and delivery</h2></div>
          <div className="faq__list">
            <details className="faq__item"><summary>How much does Korean ramen cost in Sri Lanka?</summary><p>At K FOOD, single Korean cup noodles start at {fmt(lowestSingle)} and packet ramen starts at {fmt(lowestPacket)}. The exact price depends on the product and whether you buy one, a 5 Pack or a carton.</p></details>
            <details className="faq__item"><summary>Where can I buy Korean ramen online in Sri Lanka?</summary><p>You can order from K FOOD through this website. Build your cart, add your delivery details and send the order on WhatsApp for stock confirmation and island-wide courier delivery.</p></details>
            <details className="faq__item"><summary>Are ramen and ramyun the same search?</summary><p>Ramen is the spelling most Sri Lankan shoppers use online. Ramyun or ramyeon is the Korean term commonly printed on Korean instant noodle products, so this shop uses both where helpful.</p></details>
          </div>
        </section>
      </main>

      <SiteFooter links={["shop", "prices", "cart", "whatsapp"]} />
    </>
  );
}

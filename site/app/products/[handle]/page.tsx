import { notFound } from "next/navigation";
import JsonLd from "@/components/JsonLd";
import PageHead from "@/components/PageHead";
import ProductBuy from "@/components/ProductBuy";
import ProductMedia from "@/components/ProductMedia";
import { RelatedCard } from "@/components/ProductCard";
import SiteFooter from "@/components/SiteFooter";
import SiteHeader from "@/components/SiteHeader";
import {
  PRODUCTS, SITE, fullName, getProduct, isNoodle, related, shots, src, thumb, unitWord, type Product,
} from "@/lib/catalog";
import { fmt } from "@/lib/format";
import { productBreadcrumbLd, productLd, productUrl } from "@/lib/seo";

/* One static page per product, at /products/<handle>.html. Any handle not in
   the catalogue is a 404 — there is no server to render it on demand. */
export const dynamicParams = false;

export function generateStaticParams() {
  return PRODUCTS.map((p) => ({ handle: p.handle }));
}

function NutritionTable({ p }: { p: Product }) {
  if (!p.nutrition) {
    return <p className="pd__nut-note">⚠ Nutrition figures for this product are still being verified against the pack label — see the printed pack for exact values.</p>;
  }
  const n = p.nutrition;
  const rows: [string, string | undefined][] = [
    ["Energy", n.energy], ["Total fat", n.fat], ["Saturated fat", n.satFat], ["Carbohydrate", n.carbs],
    ["Fibre", n.fibre], ["Sugars", n.sugars], ["Protein", n.protein], ["Sodium", n.sodium],
  ];
  return (
    <div className="pd__table-wrap">
      <table className="pd__table">
        <caption>{n.basis}</caption>
        <tbody>
          {rows.filter(([, v]) => v).map(([k, v]) => (
            <tr key={k}><th scope="row">{k}</th><td>{v}</td></tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* Visible price copy — matches how people actually search ("<product> price Sri Lanka") */
function PriceBlock({ p }: { p: Product }) {
  const v0 = p.variants[0];
  const rest = p.variants.slice(1).map((v) => `${fmt(v.price)} for the ${v.label}`).join(" and ");
  return (
    <section className="pd__block">
      <h2>{fullName(p)} price in Sri Lanka</h2>
      <p>The {fullName(p)} {p.pack} price in Sri Lanka is {fmt(v0.price)} per {unitWord(p)} at K FOOD{rest ? `, with bulk deals at ${rest}` : ""}. Buy online at kfoods.lk at the best price — island-wide delivery across Sri Lanka in 2–3 days, free on orders over LKR 5,000.</p>
    </section>
  );
}

export default async function ProductPage({ params }: { params: Promise<{ handle: string }> }) {
  const { handle } = await params;
  const p = getProduct(handle);
  if (!p) notFound();

  const noodle = isNoodle(p);
  const title = noodle
    ? `${fullName(p)} Price in Sri Lanka | K FOOD`
    : `${fullName(p)} ${p.pack} | Buy Online Sri Lanka | K FOOD`;
  const description = `Buy ${fullName(p)} ${p.pack} online at the best price in Sri Lanka — ${fmt(p.variants[0].price)} per ${unitWord(p)} with 5-pack and carton deals. Genuine Korean ${noodle ? "ramen" : "drinks"}, island-wide delivery from K FOOD (kfoods.lk).`;
  const alt = `${fullName(p)} ${p.pack} — Korean ${noodle ? "ramen" : "drink"} available in Sri Lanka`;

  /* ViewContent, inline so it fires once, as the page is parsed */
  const viewContent = `window.fbq && fbq("track", "ViewContent", ${JSON.stringify({
    content_ids: [p.variants[0].sku],
    content_type: "product",
    content_name: p.name,
    content_category: p.category,
    value: p.variants[0].price,
    currency: "LKR",
  })});`;

  return (
    <>
      <PageHead
        title={title}
        description={description}
        canonical={productUrl(p)}
        robots="index, follow, max-image-preview:large"
        og={{
          type: "product",
          title,
          description: p.short,
          url: productUrl(p),
          image: `${SITE}/${p.image}`,
        }}
      />
      <JsonLd data={productLd(p)} />
      <JsonLd data={productBreadcrumbLd(p)} />

      <SiteHeader />

      <main className="pd">
        <nav className="pd__crumbs" aria-label="Breadcrumb">
          <a href="/">Home</a> <span aria-hidden="true">›</span>{" "}
          <a href={noodle ? "/korean-ramen-price-sri-lanka.html" : "/#shop"}>{noodle ? "Korean ramen prices" : "Shop"}</a>{" "}
          <span aria-hidden="true">›</span>{" "}
          <span aria-current="page">{p.name}</span>
        </nav>

        <div className="pd__layout">
          <ProductMedia images={shots(p).map((s) => ({ full: src(s), thumb: src(thumb(s)) }))} alt={alt} />

          <div className="pd__info">
            <p className="pd__brand">{p.brand}{p.badge && <> <span className="pd__badge">{p.badge}</span></>}</p>
            <h1 className="pd__name">{p.name}{p.ko && <> <span className="pd__ko" lang="ko">{p.ko}</span></>}</h1>

            <ul className="pd__facts">
              <li><strong>{p.pack}</strong> {noodle ? "pack" : ""}</li>
              {p.heat !== null && p.heat !== undefined && (
                <li>Heat {p.heat === 0 ? "0/5 — not spicy" : `${p.heat}/5 ${"🌶".repeat(p.heat)}`}</li>
              )}
              {p.cook && <li>Ready in {p.cook}</li>}
              <li>From South Korea</li>
            </ul>

            <p className="pd__short">{p.short}</p>

            <ProductBuy name={p.name} pack={p.pack} variants={p.variants} />
          </div>
        </div>

        <div className="pd__details">
          <section className="pd__block">
            <h2>About this {noodle ? "ramyeon" : "drink"}</h2>
            <p>{p.long}</p>
          </section>
          <section className="pd__block">
            <h2>How to {noodle ? "cook" : "serve"}</h2>
            <p>{p.serve}</p>
          </section>
          <section className="pd__block">
            <h2>Ingredients &amp; allergens</h2>
            <p>{p.ingredients}</p>
            <p className="pd__allergens"><strong>Allergens:</strong> {p.allergens}</p>
          </section>
          <section className="pd__block">
            <h2>Nutrition</h2>
            <NutritionTable p={p} />
          </section>
          <PriceBlock p={p} />
        </div>

        <section className="pd__related">
          <h2 className="pd__related-title">You might also like</h2>
          <div className="shop__grid shop__grid--related">
            {related(p).map((q) => <RelatedCard key={q.handle} p={q} />)}
          </div>
        </section>
      </main>

      <SiteFooter links={["shop", "prices", "cart", "whatsapp"]} />
      <script dangerouslySetInnerHTML={{ __html: viewContent }} />
    </>
  );
}

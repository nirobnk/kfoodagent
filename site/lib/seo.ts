/* Structured data. Ported line for line from the old build.mjs and the
   hand-written graph in index.html — scripts/seo-snapshot.mjs compares
   every object here against what the static site published. */

import { FREE_DELIVERY_OVER, DELIVERY_FEE, PRODUCTS, SITE, fullName, shots, type Product } from "./catalog";
import { fmt } from "./format";

/* Merchant-listing facts used in the Product JSON-LD.
   Keep these in sync with the visible Delivery + FAQ copy. */
const PRICE_VALID_FROM = "2026-08-26";

/* A year from the build. A fixed date expires on a day nobody is watching,
   and Google then treats every offer as stale. Every deploy moves this
   forward; `npm run seo:check` fails if it is ever within 60 days. */
const PRICE_VALID_UNTIL = (() => {
  const d = new Date();
  d.setUTCFullYear(d.getUTCFullYear() + 1);
  return d.toISOString().slice(0, 10);
})();

const SHIPPING_DETAILS = {
  "@type": "OfferShippingDetails",
  shippingRate: { "@type": "MonetaryAmount", value: DELIVERY_FEE, currency: "LKR" },
  shippingDestination: { "@type": "DefinedRegion", addressCountry: "LK" },
  deliveryTime: {
    "@type": "ShippingDeliveryTime",
    handlingTime: { "@type": "QuantitativeValue", minValue: 0, maxValue: 1, unitCode: "DAY" },
    transitTime: { "@type": "QuantitativeValue", minValue: 2, maxValue: 3, unitCode: "DAY" }
  }
};

const RETURN_POLICY = {
  "@type": "MerchantReturnPolicy",
  applicableCountry: "LK",
  returnPolicyCategory: "https://schema.org/MerchantReturnFiniteReturnWindow",
  merchantReturnDays: 7,
  returnMethod: "https://schema.org/ReturnByMail",
  returnFees: "https://schema.org/FreeReturn",
  refundType: "https://schema.org/FullRefund"
};

export const productUrl = (p: Product) => `${SITE}/products/${p.handle}.html`;

export const productLd = (p: Product) => ({
  "@context": "https://schema.org",
  "@type": "Product",
  name: `${fullName(p)} ${p.pack}`,
  image: shots(p).map((s) => `${SITE}/${s}`),
  description: p.short,
  sku: p.variants[0].sku,
  brand: { "@type": "Brand", name: p.brand },
  category: p.category,
  url: productUrl(p),
  offers: p.variants.map((v) => ({
    "@type": "Offer",
    sku: v.sku,
    name: v.label,
    price: v.price,
    priceCurrency: "LKR",
    validFrom: PRICE_VALID_FROM,
    priceValidUntil: PRICE_VALID_UNTIL,
    itemCondition: "https://schema.org/NewCondition",
    availability: "https://schema.org/InStock",
    url: productUrl(p),
    seller: { "@type": "Organization", name: "K FOOD Sri Lanka" },
    shippingDetails: SHIPPING_DETAILS,
    hasMerchantReturnPolicy: RETURN_POLICY
  }))
});

export const productBreadcrumbLd = (p: Product) => ({
  "@context": "https://schema.org",
  "@type": "BreadcrumbList",
  itemListElement: [
    { "@type": "ListItem", position: 1, name: "Home", item: `${SITE}/` },
    p.category === "Beverages"
      ? { "@type": "ListItem", position: 2, name: "Shop", item: `${SITE}/#shop` }
      : { "@type": "ListItem", position: 2, name: "Korean ramen prices", item: `${SITE}/korean-ramen-price-sri-lanka.html` },
    { "@type": "ListItem", position: 3, name: fullName(p) }
  ]
});

export const shopItemListLd = () => ({
  "@context": "https://schema.org",
  "@type": "ItemList",
  name: "Korean ramen noodles & drinks online in Sri Lanka — K FOOD",
  numberOfItems: PRODUCTS.length,
  itemListElement: PRODUCTS.map((p, i) => ({
    "@type": "ListItem",
    position: i + 1,
    name: fullName(p),
    url: productUrl(p)
  }))
});

export const priceItemListLd = (noodles: Product[]) => ({
  "@context": "https://schema.org",
  "@type": "ItemList",
  name: "Korean ramen price list in Sri Lanka",
  numberOfItems: noodles.length,
  itemListElement: noodles.map((p, i) => ({
    "@type": "ListItem",
    position: i + 1,
    name: fullName(p),
    url: productUrl(p)
  }))
});

export const priceBreadcrumbLd = () => ({
  "@context": "https://schema.org",
  "@type": "BreadcrumbList",
  itemListElement: [
    { "@type": "ListItem", position: 1, name: "Home", item: `${SITE}/` },
    { "@type": "ListItem", position: 2, name: "Korean ramen prices in Sri Lanka" }
  ]
});

/* The home page's @graph: the site, the store, and the FAQ. The FAQ answers
   must say the same thing as the visible <details> on the home page. */
export function siteGraphLd() {
  const shin = PRODUCTS.find((p) => p.handle === "shin-ramyun")!;
  const [single, five, carton] = shin.variants.map((v) => fmt(v.price));
  const prices = PRODUCTS.flatMap((p) => p.variants.map((v) => v.price));
  return {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "WebSite",
        "@id": `${SITE}/#website`,
        url: `${SITE}/`,
        name: "K FOOD",
        alternateName: ["K FOOD Sri Lanka", "kfoods.lk"],
        publisher: { "@id": `${SITE}/#store` },
        inLanguage: "en-LK"
      },
      {
        "@type": "OnlineStore",
        "@id": `${SITE}/#store`,
        name: "K FOOD Sri Lanka",
        alternateName: ["K FOOD", "KFood", "K Foods", "kfoods.lk"],
        url: `${SITE}/`,
        logo: `${SITE}/images/kfood-logo.png`,
        image: `${SITE}/images/hero-ramen.webp`,
        description: "Buy Korean ramen online at the best price in Sri Lanka. Shin Ramyun, Hot Dak fire noodles, cup ramyeon and Korean drinks with island-wide delivery.",
        telephone: "+94772953107",
        email: "kfoodslk@gmail.com",
        priceRange: `${fmt(Math.min(...prices))} – ${fmt(Math.max(...prices))}`,
        currenciesAccepted: "LKR",
        paymentAccepted: "Bank Transfer",
        areaServed: { "@type": "Country", name: "Sri Lanka" },
        sameAs: [
          "https://web.facebook.com/kfoodslk",
          "https://www.instagram.com/kfoodslk/",
          "https://www.tiktok.com/@kfoodslk"
        ]
      },
      {
        "@type": "FAQPage",
        "@id": `${SITE}/#faq`,
        mainEntity: [
          {
            "@type": "Question",
            name: "Does K FOOD deliver Korean ramen island-wide in Sri Lanka?",
            acceptedAnswer: { "@type": "Answer", text: `Yes. K FOOD (kfoods.lk) delivers Korean ramyeon and drinks to every district in Sri Lanka — Colombo, Kandy, Galle, Kurunegala, Gampaha, Malabe, Kegalle, Jaffna and everywhere in between. Delivery is a flat ${fmt(DELIVERY_FEE)} island-wide and free for orders over ${fmt(FREE_DELIVERY_OVER)}. Orders arrive in 2–4 days.` }
          },
          {
            "@type": "Question",
            name: "What is K FOOD's return policy?",
            acceptedAnswer: { "@type": "Answer", text: "If an item arrives damaged, expired or is not what you ordered, tell us on WhatsApp within 7 days of delivery. We collect it at our cost and send a replacement or a full refund. Unopened items in original condition can be returned within the same 7 days; opened food packs cannot be returned for food-safety reasons." }
          },
          {
            "@type": "Question",
            name: "Is there a minimum order?",
            acceptedAnswer: { "@type": "Answer", text: `No. Order as much or as little as you like — a single pack, a 5 Pack, a carton or just a drink. Delivery is a flat ${fmt(DELIVERY_FEE)} island-wide and free on orders over ${fmt(FREE_DELIVERY_OVER)}.` }
          },
          {
            "@type": "Question",
            name: "How do I pay?",
            acceptedAnswer: { "@type": "Answer", text: "Checkout sends your order to our WhatsApp Business number. We confirm stock and delivery, then you pay by bank transfer to Hatton National Bank (HNB), Alawwa branch, account name Kumarasinghe H G B N, account number 123020163895. Send us the receipt on WhatsApp and we dispatch. No card is needed on the website." }
          },
          {
            "@type": "Question",
            name: "What is the Shin Ramyun price in Sri Lanka at K FOOD?",
            acceptedAnswer: { "@type": "Answer", text: `Shin Ramyun Original 120g is ${single} per pack, ${five} for a 5 Pack and ${carton} for a 20-pack carton at kfoods.lk. Prices for the full range are listed on each product page.` }
          },
          {
            "@type": "Question",
            name: "Is kfoods.lk an online-only store?",
            acceptedAnswer: { "@type": "Answer", text: "Yes — kfoods.lk is an online Korean food store for Sri Lanka. You order on the website, confirm on WhatsApp (077 295 3107) and we courier your ramyeon and drinks to your door, anywhere on the island." }
          }
        ]
      }
    ]
  };
}

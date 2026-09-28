import type { MetadataRoute } from "next";
import { PRODUCTS, SITE } from "@/lib/catalog";

export const dynamic = "force-static";

const TODAY = new Date().toISOString().slice(0, 10);

/* cart.html is deliberately left out: it is noindex, and listing it here
   would contradict that. */
export default function sitemap(): MetadataRoute.Sitemap {
  return [
    { url: `${SITE}/`, lastModified: TODAY, changeFrequency: "weekly", priority: 1.0 },
    { url: `${SITE}/korean-ramen-price-sri-lanka.html`, lastModified: TODAY, changeFrequency: "weekly", priority: 0.9 },
    ...PRODUCTS.map((p) => ({
      url: `${SITE}/products/${p.handle}.html`,
      lastModified: TODAY,
      changeFrequency: "weekly" as const,
      priority: 0.8,
    })),
  ];
}
